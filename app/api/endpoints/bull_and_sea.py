from typing import Annotated, Optional
import asyncio
import datetime as dt
import re
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from httpx import AsyncClient

from app.api.deps import get_current_admin
from app.db.session import get_db
from app.models.dish_settings import DishSettings
from app.models.dish import Dish
from app.services.iiko_auth import get_iiko_server_auth_manager
from app.core.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Ключи для хранения состояния автосинхронизации в app.state
AUTO_SYNC_ENABLED_KEY = "bull_and_sea_auto_sync_enabled"
AUTO_SYNC_TASK_KEY = "bull_and_sea_auto_sync_task"
AUTO_SYNC_DATE_FROM_KEY = "bull_and_sea_auto_sync_date_from"
AUTO_SYNC_INTERVAL = 300  # 5 минут в секундах

router = APIRouter()


def _get_local_tz() -> dt.tzinfo:
    tzname = getattr(settings, "LOCAL_TIMEZONE", None) or "Europe/Moscow"
    try:
        return ZoneInfo(tzname)
    except Exception:
        return dt.timezone.utc


def _parse_output_comment_weight(output_comment: str | None) -> int:
    """Парсит outputComment из технологической карты iiko.
    Формат: строка вида "0,2" (кг, запятая как разделитель).
    Возвращает вес в граммах (int). Если не удалось распарсить — 0.
    """
    if not output_comment:
        return 0
    cleaned = output_comment.strip().replace(",", ".").replace(" ", "")
    m = re.search(r"(\d+\.?\d*)", cleaned)
    if m:
        try:
            kg = float(m.group(1))
            return max(1, int(round(kg * 1000)))
        except (ValueError, TypeError):
            pass
    return 0


async def _run_sync(
    db_session_factory,
    date_from: dt.date,
    date_to: dt.date,
) -> dict:
    """
    Основная логика синхронизации. Вынесена в отдельную функцию для переиспользования
    в ручном режиме и в автосинхронизации.
    Возвращает словарь с результатами.
    """
    preset_id = settings.IIKO_OLAP_PRESET_ID
    iiko_host = settings.IIKO_SERVER_HOST
    if not preset_id or not iiko_host:
        return {"updated": 0, "total": 0, "error": "OLAP preset или IIKO_SERVER_HOST не настроены"}

    async with db_session_factory() as db:
        # 1. Получить все dish_settings с dish + product_id
        res = await db.execute(
            select(DishSettings, Dish)
            .join(Dish, DishSettings.dish_id == Dish.id)
            .where(
                DishSettings.active == True,
                Dish.product_id.is_not(None),
            )
        )
        rows = res.all()
        if not rows:
            return {"updated": 0, "total": 0, "message": "Нет активных блюд с product_id"}

        # 2. Авторизация в iikoServer
        mgr = get_iiko_server_auth_manager()
        try:
            await mgr.ensure_authenticated()
        except Exception as e:
            return {"updated": 0, "total": len(rows), "error": f"Ошибка авторизации iikoServer: {e}"}

        client = await mgr.get_client()
        session_key = mgr.get_session_key()

        base = iiko_host.rstrip("/")
        if base.lower().endswith("/resto"):
            base = base[: -len("/resto")]

        # 3. Запросить веса из assemblyCharts для каждого блюда
        weight_results: dict[int, int] = {}

        async def fetch_weight(dish: Dish) -> tuple[int, int]:
            pid = str(dish.product_id)
            url = f"{base}/resto/api/v2/assemblyCharts/byId"
            params: dict = {"id": pid}
            if session_key:
                params["key"] = session_key
            try:
                resp = await client.get(url, params=params, timeout=30)
                if resp.status_code == 200:
                    data = resp.json()
                    comment = data.get("outputComment")
                    grams = _parse_output_comment_weight(comment)
                    if grams > 0:
                        return (dish.id, grams)
                    logger.warning(
                        "assemblyCharts dish=%s product=%s: outputComment='%s' не распознан",
                        dish.id, pid, comment,
                    )
                else:
                    logger.warning(
                        "assemblyCharts dish=%s product=%s: HTTP %s",
                        dish.id, pid, resp.status_code,
                    )
            except Exception as e:
                logger.warning("Ошибка assemblyCharts dish=%s product=%s: %s", dish.id, pid, e)
            return (dish.id, 0)

        tasks = [fetch_weight(dish) for _, dish in rows]
        results = await asyncio.gather(*tasks)
        for dish_id, grams in results:
            weight_results[dish_id] = grams

        # 4. Маппинг названия блюда -> dish_id
        dish_name_to_id: dict[str, int] = {}
        for _settings_row, dish in rows:
            nm = (dish.name or "").strip().lower()
            if nm:
                dish_name_to_id[nm] = dish.id

        # 5. Запрос OLAP
        report_url = f"{base}/resto/api/v2/reports/olap/byPresetId/{preset_id}"
        olap_params = {
            "key": session_key or "",
            "dateFrom": date_from.isoformat(),
            "dateTo": date_to.isoformat(),
            "summary": "true",
        }

        sales_map: dict[int, int] = {}

        logger.info("OLAP запрос: %s dateFrom=%s dateTo=%s", report_url, date_from, date_to)

        try:
            resp = await client.get(report_url, params=olap_params, timeout=60)
            if resp.status_code == 200:
                data = resp.json()
                raw_rows: list = []

                if isinstance(data, dict) and "data" in data and isinstance(data["data"], list):
                    raw_rows = data["data"]
                if not raw_rows and isinstance(data, dict):
                    rows_data = data.get("rows") or data.get("Row") or data.get("rowsList") or []
                    if isinstance(rows_data, list):
                        raw_rows = rows_data
                if not raw_rows and isinstance(data, list):
                    raw_rows = data

                for row in raw_rows:
                    if not isinstance(row, dict):
                        continue
                    row_name = None
                    row_amount = None
                    for k, v in row.items():
                        kl = k.lower()
                        if kl in ("name", "dish", "dishname", "dish_name", "product", "productname"):
                            row_name = str(v).strip().lower() if v else None
                        elif kl in ("close_time", "closetime", "date", "datetime"):
                            pass
                        else:
                            if isinstance(v, (int, float)) and v is not None:
                                row_amount = int(v)
                    if not row_name:
                        continue
                    dish_id = dish_name_to_id.get(row_name)
                    if dish_id and row_amount is not None:
                        sales_map[dish_id] = sales_map.get(dish_id, 0) + row_amount

                logger.info("OLAP: %s строк, продаж для %s блюд", len(raw_rows), len(sales_map))
            else:
                logger.warning("OLAP HTTP %s: %s", resp.status_code, resp.text[:300])
        except Exception as e:
            logger.error("Ошибка OLAP: %s", e)

        # 6. Обновляем dish_settings
        updated_count = 0
        for settings_row, dish in rows:
            changed = False
            grams = weight_results.get(dish.id, 0)
            if grams > 0 and grams != (settings_row.weight_grams or 0):
                settings_row.weight_grams = grams
                changed = True
            sales = sales_map.get(dish.id, 0)
            if sales != (settings_row.sales_quantity or 0):
                settings_row.sales_quantity = sales
                changed = True
            if changed:
                updated_count += 1

        await db.commit()

        return {
            "updated": updated_count,
            "total": len(rows),
            "message": f"Обновлено {updated_count} из {len(rows)} блюд",
            "details": {
                "weights_found": sum(1 for g in weight_results.values() if g > 0),
                "sales_found": len(sales_map),
            },
        }


# ──────────────────────────────────────────────
#  РУЧНАЯ СИНХРОНИЗАЦИЯ
# ──────────────────────────────────────────────

@router.get("/stats")
async def bull_and_sea_stats(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Публичный endpoint. Агрегированные данные для страницы «Бык и Море»."""
    res = await db.execute(select(DishSettings).where(DishSettings.active == True))
    rows = res.scalars().all()
    total_pieces = 0
    total_weight_kg = 0.0
    for s in rows:
        qty = s.sales_quantity or 0
        weight = s.weight_grams or 0
        total_pieces += qty
        total_weight_kg += qty * (weight / 1000.0)
    return {"total_pieces": total_pieces, "total_weight_kg": round(total_weight_kg, 1)}


@router.post("/sync-sales")
async def sync_sales(
    current_admin: Annotated[object, Depends(get_current_admin)],
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    date_from: Optional[str] = Query(None, description="Начало периода (YYYY-MM-DD). По умолчанию 30 дней назад"),
    date_to: Optional[str] = Query(None, description="Конец периода (YYYY-MM-DD). По умолчанию сегодня+1"),
):
    """
    Ручная синхронизация продаж из iiko за указанный период.
    - Запрашивает технологические карты (assemblyCharts) для веса порций
    - Запрашивает OLAP-отчёт по пресету за указанный период для количества продаж
    - Обновляет dish_settings
    """
    preset_id = settings.IIKO_OLAP_PRESET_ID
    if not preset_id:
        raise HTTPException(status_code=400, detail="OLAP preset не настроен. Укажите IIKO_OLAP_PRESET_ID в .env")
    if not settings.IIKO_SERVER_HOST:
        raise HTTPException(status_code=400, detail="IIKO_SERVER_HOST не настроен")

    local_tz = _get_local_tz()
    now = dt.datetime.now(local_tz)

    try:
        actual_from = dt.date.fromisoformat(date_from) if date_from else (now - dt.timedelta(days=30)).date()
    except ValueError:
        raise HTTPException(status_code=400, detail="date_from должен быть в формате YYYY-MM-DD")

    try:
        actual_to = dt.date.fromisoformat(date_to) if date_to else (now + dt.timedelta(days=1)).date()
    except ValueError:
        raise HTTPException(status_code=400, detail="date_to должен быть в формате YYYY-MM-DD")

    if actual_from >= actual_to:
        actual_from = actual_to - dt.timedelta(days=1)

    result = await _run_sync(
        db_session_factory=request.app.state.db_session_factory,
        date_from=actual_from,
        date_to=actual_to,
    )
    if "error" in result:
        raise HTTPException(status_code=502, detail=result["error"])
    return result


# ──────────────────────────────────────────────
#  АВТОМАТИЧЕСКАЯ СИНХРОНИЗАЦИЯ (каждые 5 мин)
# ──────────────────────────────────────────────

async def _auto_sync_loop(app):
    """Фоновый цикл: каждые AUTO_SYNC_INTERVAL секунд выполняет синхронизацию."""
    while True:
        try:
            await asyncio.sleep(AUTO_SYNC_INTERVAL)
            enabled = getattr(app.state, AUTO_SYNC_ENABLED_KEY, False)
            if not enabled:
                continue

            date_from = getattr(app.state, AUTO_SYNC_DATE_FROM_KEY, None)
            if not date_from:
                logger.warning("auto-sync: date_from не установлен, останавливаю")
                setattr(app.state, AUTO_SYNC_ENABLED_KEY, False)
                continue

            local_tz = _get_local_tz()
            now = dt.datetime.now(local_tz)
            date_to = (now + dt.timedelta(days=1)).date()

            logger.info("auto-sync: запуск синхронизации %s → %s", date_from, date_to)
            result = await _run_sync(
                db_session_factory=app.state.db_session_factory,
                date_from=date_from,
                date_to=date_to,
            )
            logger.info("auto-sync: результат %s", result.get("message", result))
        except asyncio.CancelledError:
            logger.info("auto-sync: цикл остановлен")
            break
        except Exception as e:
            logger.error("auto-sync: ошибка в цикле: %s", e)


@router.post("/auto-sync/start")
async def auto_sync_start(
    current_admin: Annotated[object, Depends(get_current_admin)],
    request: Request,
    date_from: str = Query(..., description="Начало периода автосинхронизации (YYYY-MM-DD)"),
):
    """Запустить автоматическую синхронизацию каждые 5 минут."""
    try:
        parsed_from = dt.date.fromisoformat(date_from)
    except ValueError:
        raise HTTPException(status_code=400, detail="date_from должен быть в формате YYYY-MM-DD")

    # Останавливаем предыдущий цикл если был
    await _auto_sync_stop_inner(request.app)

    setattr(request.app.state, AUTO_SYNC_ENABLED_KEY, True)
    setattr(request.app.state, AUTO_SYNC_DATE_FROM_KEY, parsed_from)

    # Сохраняем фабрику сессий для использования в фоновом цикле
    if not hasattr(request.app.state, "db_session_factory"):
        from app.db.session import AsyncSessionLocal
        request.app.state.db_session_factory = AsyncSessionLocal

    task = asyncio.create_task(_auto_sync_loop(request.app))
    setattr(request.app.state, AUTO_SYNC_TASK_KEY, task)

    logger.info("auto-sync: запущен с date_from=%s", date_from)
    return {"enabled": True, "date_from": date_from, "interval_seconds": AUTO_SYNC_INTERVAL}


async def _auto_sync_stop_inner(app):
    """Внутренняя остановка цикла."""
    setattr(app.state, AUTO_SYNC_ENABLED_KEY, False)
    task = getattr(app.state, AUTO_SYNC_TASK_KEY, None)
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    setattr(app.state, AUTO_SYNC_TASK_KEY, None)


@router.post("/auto-sync/stop")
async def auto_sync_stop(
    current_admin: Annotated[object, Depends(get_current_admin)],
    request: Request,
):
    """Остановить автоматическую синхронизацию."""
    await _auto_sync_stop_inner(request.app)
    logger.info("auto-sync: остановлен")
    return {"enabled": False}


@router.get("/auto-sync/status")
async def auto_sync_status(
    current_admin: Annotated[object, Depends(get_current_admin)],
    request: Request,
):
    """Проверить статус автоматической синхронизации."""
    enabled = getattr(request.app.state, AUTO_SYNC_ENABLED_KEY, False)
    date_from = getattr(request.app.state, AUTO_SYNC_DATE_FROM_KEY, None)
    task = getattr(request.app.state, AUTO_SYNC_TASK_KEY, None)
    return {
        "enabled": enabled,
        "date_from": str(date_from) if date_from else None,
        "interval_seconds": AUTO_SYNC_INTERVAL,
        "task_running": bool(task and not task.done()),
    }
