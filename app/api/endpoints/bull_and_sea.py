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


async def _fetch_weights(client, base: str, session_key, rows) -> dict[int, int]:
    """Вес порций (unitWeight, кг → граммы) для блюд → {dish_id: grams}."""
    weight_results: dict[int, int] = {}
    pid_list = [str(dish.product_id) for _, dish in rows]
    if not pid_list:
        return weight_results
    url = f"{base}/resto/api/v2/entities/products/list"
    params: dict = {"ids": pid_list}
    if session_key:
        params["key"] = session_key
    try:
        resp = await client.get(url, params=params, timeout=60)
        if resp.status_code == 200:
            data = resp.json()
            pid_to_grams: dict[str, int] = {}
            for item in data if isinstance(data, list) else []:
                pid = str(item.get("id") or "")
                uw = item.get("unitWeight")
                if pid and isinstance(uw, (int, float)) and uw > 0:
                    pid_to_grams[pid] = max(1, int(round(uw * 1000)))
            for _settings_row, dish in rows:
                pid = str(dish.product_id)
                grams = pid_to_grams.get(pid, 0)
                weight_results[dish.id] = grams
                if grams == 0:
                    logger.warning(
                        "Вес не найден для dish=%s product=%s (unitWeight отсутствует)",
                        dish.id, pid,
                    )
        else:
            logger.warning(
                "Номенклатура (веса) HTTP %s: %s",
                resp.status_code, resp.text[:300],
            )
    except Exception as e:
        logger.warning("Ошибка запроса номенклатуры (веса): %s", e)
    return weight_results


async def _fetch_sales_map(client, base: str, session_key, preset_id: str, date_from, date_to, dish_name_to_id: dict[str, int]) -> dict[int, int]:
    """OLAP-отчёт за период → {dish_id: количество}."""
    sales_map: dict[int, int] = {}
    report_url = f"{base}/resto/api/v2/reports/olap/byPresetId/{preset_id}"
    olap_params = {
        "key": session_key or "",
        "dateFrom": date_from.isoformat(),
        "dateTo": date_to.isoformat(),
        "summary": "true",
    }
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
    return sales_map


async def _read_today_sales(app, today, date_to) -> dict[int, int]:
    """OLAP-продажи за текущий день → {dish_id: amount}. Для инкремента автосинхронизации."""
    preset_id = settings.IIKO_OLAP_PRESET_ID
    if not preset_id:
        return {}
    from app.models.iiko_settings import IikoSettings
    from sqlalchemy import select

    iiko_host = iiko_login = iiko_password = ""
    try:
        async with app.state.db_session_factory() as db:
            result = await db.execute(select(IikoSettings).order_by(IikoSettings.id.asc()))
            stored = result.scalars().first()
            if stored and stored.server_host:
                iiko_host = stored.server_host.rstrip("/")
                iiko_login = stored.server_login or ""
                iiko_password = stored.server_password or ""
            res = await db.execute(
                select(DishSettings, Dish)
                .join(Dish, DishSettings.dish_id == Dish.id)
                .where(
                    DishSettings.active == True,
                    Dish.product_id.is_not(None),
                )
            )
            rows = res.all()
    except Exception:
        return {}
    if not iiko_host or not rows:
        return {}

    base = iiko_host
    if base.lower().endswith("/resto"):
        base = base[: -len("/resto")]
    mgr = get_iiko_server_auth_manager()
    try:
        mgr.configure(base, iiko_login, iiko_password)
        await mgr.ensure_authenticated()
    except Exception as e:
        logger.warning("auto-sync: ошибка авторизации: %s", e)
        return {}
    client = await mgr.get_client()
    session_key = mgr.get_session_key()

    dish_name_to_id: dict[str, int] = {}
    for _sr, dish in rows:
        nm = (dish.name or "").strip().lower()
        if nm:
            dish_name_to_id[nm] = dish.id
    return await _fetch_sales_map(client, base, session_key, preset_id, today, date_to, dish_name_to_id)


async def _run_sync(
    db_session_factory,
    date_from: dt.date,
    date_to: dt.date,
    incremental: dict[int, tuple[int, int]] | None = None,
    skip_sales_olap: bool = False,
) -> dict:
    """
    Основная логика синхронизации. Вынесена в отдельную функцию для переиспользования
    в ручном режиме и в автосинхронизации.
    Возвращает словарь с результатами.
    """
    preset_id = settings.IIKO_OLAP_PRESET_ID
    # Читаем host из БД
    iiko_host = ""
    iiko_login = ""
    iiko_password = ""
    try:
        async with db_session_factory() as db:
            from app.models.iiko_settings import IikoSettings
            from sqlalchemy import select
            result = await db.execute(select(IikoSettings).order_by(IikoSettings.id.asc()))
            stored = result.scalars().first()
            if stored and stored.server_host:
                iiko_host = stored.server_host.rstrip("/")
                iiko_login = stored.server_login or ""
                iiko_password = stored.server_password or ""
    except Exception:
        pass
    if not preset_id or not iiko_host:
        return {"updated": 0, "total": 0, "error": "OLAP preset или host не настроены"}

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
            base_url = iiko_host
            if base_url.lower().endswith("/resto"):
                base_url = base_url[: -len("/resto")]
            mgr.configure(base_url, iiko_login, iiko_password)
            await mgr.ensure_authenticated()
        except Exception as e:
            return {"updated": 0, "total": len(rows), "error": f"Ошибка авторизации iikoServer: {e}"}

        client = await mgr.get_client()
        session_key = mgr.get_session_key()

        base = iiko_host.rstrip("/")
        if base.lower().endswith("/resto"):
            base = base[: -len("/resto")]

        # 3. Запросить веса из номенклатуры (unitWeight — вес одной единицы в кг)
        weight_results = await _fetch_weights(client, base, session_key, rows)

        # 4. Маппинг названия блюда -> dish_id
        dish_name_to_id: dict[str, int] = {}
        for _settings_row, dish in rows:
            nm = (dish.name or "").strip().lower()
            if nm:
                dish_name_to_id[nm] = dish.id

        # 5. Продажи: полный OLAP за период либо инкремент за текущий день
        if incremental is not None:
            # sales = sales_в_БД - продажи_за_последний_тик + продажи_сегодня
            sales_map: dict[int, int] = {}
            for settings_row, dish in rows:
                last_v, today_v = incremental.get(dish.id, (0, 0))
                sales_map[dish.id] = (settings_row.sales_quantity or 0) - last_v + today_v
        elif not skip_sales_olap:
            sales_map = await _fetch_sales_map(client, base, session_key, preset_id, date_from, date_to, dish_name_to_id)
        else:
            sales_map = {}

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
    # Читаем host из БД
    iiko_host = ""
    try:
        from app.models.iiko_settings import IikoSettings
        from sqlalchemy import select
        result = await db.execute(select(IikoSettings).order_by(IikoSettings.id.asc()))
        stored = result.scalars().first()
        if stored and stored.server_host:
            iiko_host = stored.server_host.rstrip("/")
    except Exception:
        pass
    if not iiko_host:
        raise HTTPException(status_code=400, detail="IIKO host не настроен. Заполните настройки интеграции")

    local_tz = _get_local_tz()
    now = dt.datetime.now(local_tz)

    try:
        actual_from = (
            dt.date.fromisoformat(date_from)
            if date_from
            else (
                dt.date.fromisoformat(settings.IIKO_SYNC_START_DATE)
                if settings.IIKO_SYNC_START_DATE
                else (now - dt.timedelta(days=30)).date()
            )
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="date_from должен быть в формате YYYY-MM-DD")

    try:
        actual_to = dt.date.fromisoformat(date_to) if date_to else (now + dt.timedelta(days=1)).date()
    except ValueError:
        raise HTTPException(status_code=400, detail="date_to должен быть в формате YYYY-MM-DD")

    if actual_from >= actual_to:
        actual_from = actual_to - dt.timedelta(days=1)

    if not hasattr(request.app.state, "db_session_factory"):
        from app.db.session import AsyncSessionLocal

        request.app.state.db_session_factory = AsyncSessionLocal

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
    """Фоновый цикл: каждые AUTO_SYNC_INTERVAL секунд выполняет инкремент продаж за текущий день.

    Полный счётчик (за период с даты открытия) задаётся ручной синхронизацией.
    Автосинхронизация каждый тик запрашивает OLAP только за текущий день и
    добавляет прирост к счётчику без двойного счёта:
    sales = sales_в_БД - продажи_за_последний_тик + продажи_сейчас.
    """
    while True:
        try:
            await asyncio.sleep(AUTO_SYNC_INTERVAL)
            enabled = getattr(app.state, AUTO_SYNC_ENABLED_KEY, False)
            if not enabled:
                continue

            local_tz = _get_local_tz()
            now = dt.datetime.now(local_tz)
            today = now.date()
            date_to = today + dt.timedelta(days=1)

            last = getattr(app.state, "bull_and_sea_last_today", None)
            if last is None:
                # Первый тик: фиксируем продажи за текущий день (уже учтённые в счётчике).
                # Последующие тики будут добавлять только прирост за сегодня.
                today_map = await _read_today_sales(app, today, date_to)
                setattr(app.state, "bull_and_sea_last_today", {"date": today.isoformat(), "values": today_map})
                logger.info("auto-sync: инициализация за %s (%s блюд с продажами)", today, len(today_map))
                continue

            today_map = await _read_today_sales(app, today, date_to)
            # Прошлый last_today (продажи за последний обработанный день — вчера или сегодня)
            # уже учтён в счётчике: вычитаем его и добавляем текущие продажи за сегодня.
            last_values = last.get("values", {})

            dish_ids = set(list(last_values.keys()) + list(today_map.keys()))
            incremental = {
                dish_id: (last_values.get(dish_id, 0), today_map.get(dish_id, 0))
                for dish_id in dish_ids
            }
            result = await _run_sync(
                db_session_factory=app.state.db_session_factory,
                date_from=today,
                date_to=date_to,
                incremental=incremental,
                skip_sales_olap=True,
            )
            setattr(app.state, "bull_and_sea_last_today", {"date": today.isoformat(), "values": today_map})
            logger.info("auto-sync: инкремент за %s → %s", today, result.get("message", result))
        except asyncio.CancelledError:
            logger.info("auto-sync: цикл остановлен")
            break
        except Exception as e:
            logger.error("auto-sync: ошибка в цикле: %s", e)


@router.post("/auto-sync/start")
async def auto_sync_start(
    current_admin: Annotated[object, Depends(get_current_admin)],
    request: Request,
    date_from: str | None = Query(None, description="Начало периода автосинхронизации (YYYY-MM-DD). По умолчанию IIKO_SYNC_START_DATE"),
):
    """Запустить автоматическую синхронизацию каждые 5 минут."""
    start = date_from or settings.IIKO_SYNC_START_DATE
    if not start:
        raise HTTPException(status_code=400, detail="Укажите date_from или IIKO_SYNC_START_DATE в .env")
    try:
        parsed_from = dt.date.fromisoformat(start)
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
    # Сбрасываем инкрементальную базу, чтобы при новом старте инициализация прошла заново
    setattr(app.state, "bull_and_sea_last_today", None)


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
