from __future__ import annotations

import asyncio
import datetime as dt
from typing import Dict, Any, Optional, List
import hashlib
import random

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.core.config import settings
from app.utils.logger import setup_logger
from app.models.dish import Dish
from app.models.dish_settings import DishSettings
from app.models.price import Price
from app.models.price_change_state import PriceChangeState
from app.services.iiko_auth import get_iiko_server_auth_manager
from app.services.iiko_service import IikoService


logger = setup_logger(__name__)


class SalesPricingWorker:
    """
    Фоновый воркер динамического ценообразования.
    - Читает продажи из iikoServer OLAP по preset_id (env: IIKO_OLAP_PRESET_ID)
    - Идентифицирует блюда по Dish.product_id
    - Учитывает iikoCloud стоп‑лист через IikoService.fetch_stoplist_names(from_webhook=False)
    - Соблюдает TTL: хранит next_change_allowed_at в таблице price_change_state
    """

    def __init__(self, db_session_factory) -> None:
        self._db_session_factory = db_session_factory
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._loop_interval_seconds = int(settings.SALES_PRICING_LOOP_INTERVAL_SECONDS or 60)
        self._preset_id = settings.IIKO_OLAP_PRESET_ID
        # Последний слепок продаж по именам блюд (для фолбэка, если в OLAP нет productId)
        self._last_sales_by_name: Dict[str, int] = {}
        # Защита от параллельных OLAP-запросов и кэширование результатов на TTL
        self._olap_locks: Dict[str, asyncio.Lock] = {}
        self._olap_cache_rows: Dict[str, Dict[str, Any]] = {}
        self._olap_cache_counts: Dict[str, Dict[str, Any]] = {}
        # TTL для OLAP-запросов. По требованию — берём минимальное TTL из БД (DishSettings.ttl_minutes)
        # и используем его, чтобы не дергать OLAP чаще этого периода. Здесь задаём только безопасный
        # дефолт (10 минут), который будет переопределён в каждом цикле по данным из БД.
        self._olap_ttl_seconds = 600
        self._parent_cache: Dict[str, Optional[str]] = {}
        self._last_push_parent: Dict[str, Optional[str]] = {}

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run_loop(self) -> None:
        while self._running:
            try:
                await self._single_cycle()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("SalesPricingWorker cycle error: %s", e)
            await asyncio.sleep(self._loop_interval_seconds)

    async def _single_cycle(self) -> None:
        if not self._preset_id:
            return

        async with self._db_session_factory() as db:  # type: AsyncSession
            # 1) Подтянем стоп‑лист, чтобы исключить блюда (по product_id)
            stoplist_ids: List[str] = []
            try:
                svc = IikoService()
                stoplist_ids = await svc.fetch_stoplist_ids(from_webhook=False)
            except Exception:
                pass

            # 2) Прочитаем настройки блюд
            dishes = await db.execute(select(Dish))
            dishes_list: List[Dish] = dishes.scalars().all()

            # 2a) Если у блюд отсутствует product_id — попробуем автоматически заполнить его,
            #      сопоставив по названию с номенклатурой iiko (Cloud/Server).
            try:
                missing_dishes = [d for d in dishes_list if not getattr(d, "product_id", None)]
                if missing_dishes:
                    svc = IikoService()
                    products = await svc.fetch_products()
                    # Построим карту name(lower)->[product_id,...], чтобы выявлять дубликаты имён
                    name_to_ids: Dict[str, List[str]] = {}
                    for p in products:
                        try:
                            nm = str(p.get("name") or "").strip().lower()
                            pid = p.get("id")
                            if nm and pid:
                                name_to_ids.setdefault(nm, []).append(str(pid))
                        except Exception:
                            continue
                    # Пройдёмся по блюдам без product_id и заполним, если найден ровно один id по имени
                    for d in missing_dishes:
                        nm_key = (d.name or "").strip().lower()
                        ids = name_to_ids.get(nm_key) or []
                        if len(ids) == 1:
                            try:
                                new_pid = ids[0]
                                await db.execute(
                                    update(Dish)
                                    .where(Dish.id == d.id)
                                    .values(product_id=new_pid)
                                )
                                # Также обновим объект в памяти, чтобы текущий цикл сразу использовал pid
                                d.product_id = new_pid
                            except Exception as e:
                                logger.error(
                                    "Failed to set product_id for dish_id=%s name='%s': %s",
                                    d.id,
                                    (d.name or ""),
                                    e,
                                )
                        elif len(ids) > 1:
                            pass
                        else:
                            pass
            except Exception as e:
                # Не блокируем цикл, но фиксируем диагностическое сообщение
                try:
                    logger.error("Autofill product_id step failed: %s", e)
                except Exception:
                    pass

            # 3) Определим начало окна как минимальное время последней смены цены среди активных блюд
            def _get_local_tz() -> dt.tzinfo:
                try:
                    tzname = settings.LOCAL_TIMEZONE
                    if tzname:
                        try:
                            from zoneinfo import ZoneInfo
                            return ZoneInfo(str(tzname))
                        except Exception:
                            pass
                except Exception:
                    pass
                try:
                    return dt.datetime.now().astimezone().tzinfo  # type: ignore[return-value]
                except Exception:
                    return dt.timezone.utc

            local_tz = _get_local_tz()
            now = dt.datetime.now(local_tz)
            last_changes: Dict[int, Optional[dt.datetime]] = {}
            min_last_change: Optional[dt.datetime] = None
            ttl_candidates: List[int] = []  # ttl в минутах из DishSettings по активным блюдам
            for dish in dishes_list:
                ds = await db.execute(select(DishSettings).where(DishSettings.dish_id == dish.id))
                settings_row: Optional[DishSettings] = ds.scalars().first()
                if not settings_row or not settings_row.active:
                    last_changes[dish.id] = None
                    continue
                # Соберём TTL‑кандидаты из настроек блюда
                try:
                    ttl_m = int(settings_row.ttl_minutes) if settings_row.ttl_minutes is not None else 0
                    if ttl_m and ttl_m > 0:
                        ttl_candidates.append(ttl_m)
                except Exception:
                    pass
                last_price_res = await db.execute(
                    select(Price).where(Price.dish_id == dish.id).order_by(Price.created_at.desc())
                )
                last_price = last_price_res.scalars().first()
                lc = getattr(last_price, "created_at", None)
                last_changes[dish.id] = lc
                if lc is not None:
                    if min_last_change is None or lc < min_last_change:
                        min_last_change = lc
            # Фолбэк: если нет ни одной записи цены, берём старт вчера 00:00 локальной TZ
            if min_last_change is None:
                prev_day = (now.date() - dt.timedelta(days=1))
                start_dt_global = dt.datetime.combine(prev_day, dt.time.min).replace(tzinfo=local_tz)
            else:
                start_dt_global = (
                    min_last_change.astimezone(local_tz)
                    if min_last_change.tzinfo is not None
                    else min_last_change.replace(tzinfo=local_tz)
                )

            # 3a) Минимальный TTL из БД: используем как период обновления для OLAP (в секундах)
            if ttl_candidates:
                # Нижняя граница TTL: не менее 60 секунд, даже если в БД задано меньше
                base_ttl_sec = int(min(ttl_candidates) * 60)
                new_ttl_sec = max(base_ttl_sec, 60)
                if new_ttl_sec != self._olap_ttl_seconds:
                    self._olap_ttl_seconds = new_ttl_sec
            else:
                # Если в БД ни у одного блюда не задан TTL — держим безопасный дефолт (10 минут)
                self._olap_ttl_seconds = max(self._olap_ttl_seconds, 600)

            # 4) Получим нормализованные строки OLAP за единый интервал [start_dt_global, now)
            olap_rows = await self.get_olap_rows(self._preset_id, start_dt_global, now)
            try:
                logger.info(
                    "OLAP rows summary: local_window=[%s, %s) total_rows=%d",
                    start_dt_global,
                    now,
                    (len(olap_rows) if isinstance(olap_rows, list) else 0),
                )
            except Exception:
                pass
            # Построим индексы для быстрого доступа
            by_pid: Dict[str, List[Dict[str, Any]]] = {}
            by_name: Dict[str, List[Dict[str, Any]]] = {}
            for r in olap_rows:
                if not isinstance(r, dict):
                    continue
                pid = r.get("product_id")
                nm = str(r.get("name") or "").strip().lower()
                if pid:
                    by_pid.setdefault(str(pid), []).append(r)
                if nm:
                    by_name.setdefault(nm, []).append(r)

            # Дополнительный фолбэк: агрегированные продажи по пресету за вчера->сейчас
            # Используем как защиту от промаха окна или несовпадения product_id/имён
            try:
                preset_counts = await self.get_dish_sales_count_by_preset(self._preset_id)
            except Exception:
                preset_counts = {}

            # 4) Пройдёмся по блюдам и применим бизнес‑логику изменения цены (скелет)
            for dish in dishes_list:
                # Если нет product_id — не выходим сразу: возможно, удастся использовать продажи по имени (фолбэк)
                missing_pid = not getattr(dish, "product_id", None)
                # Пропускаем блюда из стоп‑листа по product_id
                pid_str = (str(dish.product_id).strip() if getattr(dish, "product_id", None) is not None else "")
                if pid_str and (pid_str in set(stoplist_ids)):
                    continue

                # Настройки блюда
                ds = await db.execute(select(DishSettings).where(DishSettings.dish_id == dish.id))
                settings_row: Optional[DishSettings] = ds.scalars().first()
                if not settings_row or not settings_row.active:
                    continue

                # TTL: проверка окна
                pcs_res = await db.execute(select(PriceChangeState).where(PriceChangeState.dish_id == dish.id))
                pcs: Optional[PriceChangeState] = pcs_res.scalars().first()
                if pcs and pcs.next_change_allowed_at:
                    na = pcs.next_change_allowed_at
                    na_local = na.astimezone(local_tz) if na.tzinfo is not None else na.replace(tzinfo=local_tz)
                    if now < na_local:
                        continue

                # Продажи за интервал: считаем за последние ttl_minutes от текущего момента
                ttl_min = int(settings_row.ttl_minutes or 0)
                if ttl_min > 0:
                    dish_start = now - dt.timedelta(minutes=ttl_min)
                else:
                    dish_start = dt.datetime.combine((now.date() - dt.timedelta(days=1)), dt.time.min).replace(tzinfo=local_tz)
                nm_key = (dish.name or "").strip().lower()
                sales_sum = 0.0
                matched_rows = []
                try:
                    logger.info(
                        "Sales window: dish_id=%s name='%s' pid=%s ttl_min=%d window=[%s, %s)",
                        dish.id,
                        (dish.name or ""),
                        (str(dish.product_id) if getattr(dish, "product_id", None) else None),
                        ttl_min,
                        dish_start,
                        now,
                    )
                except Exception:
                    pass
                
                # По product_id
                pid_str = str(dish.product_id) if getattr(dish, "product_id", None) else None
                if pid_str:
                    all_rows_for_pid = by_pid.get(pid_str, []) or []
                    try:
                        before_cnt = 0
                        in_cnt = 0
                        after_cnt = 0
                        times_sample = []
                        for row in all_rows_for_pid[:50]:
                            ct = row.get("close_time")
                            if ct is None:
                                continue
                            ct_local = ct.astimezone(local_tz) if ct.tzinfo is not None else ct.replace(tzinfo=local_tz)
                            times_sample.append(ct_local)
                            if ct_local < dish_start:
                                before_cnt += 1
                            elif dish_start <= ct_local < now:
                                in_cnt += 1
                            else:
                                after_cnt += 1
                        try:
                            mn = min(times_sample) if times_sample else None
                            mx = max(times_sample) if times_sample else None
                        except Exception:
                            mn = None
                            mx = None
                        logger.info(
                            "PID diag: dish_id=%s pid=%s rows=%d in=%d before=%d after=%d min_ct=%s max_ct=%s",
                            dish.id,
                            pid_str,
                            len(all_rows_for_pid),
                            in_cnt,
                            before_cnt,
                            after_cnt,
                            mn,
                            mx,
                        )
                    except Exception:
                        pass
                   
                    for row in all_rows_for_pid:
                        ct = row.get("close_time")
                        amount = row.get("amount", 0.0)
                        if ct is not None:
                            # Приводим время к UTC для сравнения
                            if ct.tzinfo is not None:
                                ct_local = ct.astimezone(local_tz)
                            else:
                                ct_local = ct.replace(tzinfo=local_tz)
                            in_window = dish_start <= ct_local < now
                            try:
                                logger.info(
                                    "Row check (pid): dish_id=%s time=%s in_window=%s amount=%s",
                                    dish.id,
                                    ct_local,
                                    in_window,
                                    (float(amount or 0.0)),
                                )
                            except Exception:
                                pass
                            if in_window:
                                try:
                                    sales_sum += float(amount or 0.0)
                                    matched_rows.append({"time": ct_local, "amount": float(amount or 0.0)})
                                except Exception as e:
                                    logger.error("Failed to add sales amount: %s", e)
                        else:
                            pass
                
                # Фолбэк по имени, если product_id отсутствует или продаж по product_id не найдено
                if sales_sum == 0.0:
                    all_rows_for_name = by_name.get(nm_key, []) or []
                    try:
                        before_cnt = 0
                        in_cnt = 0
                        after_cnt = 0
                        times_sample = []
                        for row in all_rows_for_name[:50]:
                            ct = row.get("close_time")
                            if ct is None:
                                continue
                            ct_local = ct.astimezone(local_tz) if ct.tzinfo is not None else ct.replace(tzinfo=local_tz)
                            times_sample.append(ct_local)
                            if ct_local < dish_start:
                                before_cnt += 1
                            elif dish_start <= ct_local < now:
                                in_cnt += 1
                            else:
                                after_cnt += 1
                        try:
                            mn = min(times_sample) if times_sample else None
                            mx = max(times_sample) if times_sample else None
                        except Exception:
                            mn = None
                            mx = None
                        logger.info(
                            "NAME diag: dish_id=%s name_key='%s' rows=%d in=%d before=%d after=%d min_ct=%s max_ct=%s",
                            dish.id,
                            nm_key,
                            len(all_rows_for_name),
                            in_cnt,
                            before_cnt,
                            after_cnt,
                            mn,
                            mx,
                        )
                    except Exception:
                        pass
                   
                    for row in all_rows_for_name:
                        ct = row.get("close_time")
                        amount = row.get("amount", 0.0)
                        if ct is not None:
                            # Приводим время к UTC для сравнения
                            if ct.tzinfo is not None:
                                ct_local = ct.astimezone(local_tz)
                            else:
                                ct_local = ct.replace(tzinfo=local_tz)
                            in_window = dish_start <= ct_local < now
                            try:
                                logger.info(
                                    "Row check (name): dish_id=%s time=%s in_window=%s amount=%s",
                                    dish.id,
                                    ct_local,
                                    in_window,
                                    (float(amount or 0.0)),
                                )
                            except Exception:
                                pass
                            if in_window:
                                try:
                                    sales_sum += float(amount or 0.0)
                                    matched_rows.append({"time": ct_local, "amount": float(amount or 0.0)})
                                except Exception as e:
                                    logger.error("Failed to add sales amount (by name): %s", e)
                        else:
                            pass
                
                sales_count = int(sales_sum)
                
                # Логируем итоговую информацию о найденных продажах
                if matched_rows:
                    logger.info(
                        "Sales matched: dish_id=%s name='%s' pid=%s matched_rows=%d total_amount=%.2f details=%s",
                        dish.id,
                        (dish.name or ""),
                        pid_str,
                        len(matched_rows),
                        float(sales_sum),
                        matched_rows,
                    )
                else:
                    logger.info(
                        "Sales matched: dish_id=%s name='%s' pid=%s matched_rows=0 total_amount=0.00 (no sales in window [%s, %s))",
                        dish.id,
                        (dish.name or ""),
                        pid_str,
                        dish_start,
                        now,
                    )
                # ВАЖНО: НЕ используем fallback данные для принятия решений об изменении цены!
                # Fallback данные могут быть устаревшими и не соответствовать текущему периоду TTL.
                # Используем только реальные продажи за текущий период [dish_start, now).
                # Fallback данные оставляем только для диагностики/логирования.
                fallback_info = ""
                if sales_count == 0:
                    try:
                        nm_key = (dish.name or "").strip().lower()
                        fallback_by_name = int(self._last_sales_by_name.get(nm_key) or 0)
                        if fallback_by_name > 0:
                            fallback_info = f" (fallback by name would be {fallback_by_name}, but not used)"
                    except Exception:
                        pass
                # Дополнительный фолбэк: счётчик из агрегированного отчёта по пресету (только для диагностики)
                if sales_count == 0 and getattr(dish, "product_id", None):
                    try:
                        pid_str = str(dish.product_id)
                        agg = int(preset_counts.get(pid_str) or 0)
                        if agg > 0:
                            if not fallback_info:
                                fallback_info = f" (fallback by preset would be {agg}, but not used)"
                    except Exception:
                        pass

                # Если нет product_id и при этом не удалось получить продажи по имени — пропускаем блюдо
                if missing_pid and sales_count == 0:
                    continue

                # Логика изменения цены: если продажи >= порога — увеличиваем, иначе — уменьшаем
                new_price: Optional[float] = None
                base_value: Optional[float] = None
                try:
                    sales_qty_threshold = int(settings_row.sales_quantity or 0) if settings_row.sales_quantity else 0
                    # Получим последнюю цену (используется для расчёта новой цены на шаг),
                    # но курс ВСЕГДА считаем строго от базовой цены из DishSettings
                    last_price_res = await db.execute(select(Price).where(Price.dish_id == dish.id).order_by(Price.created_at.desc()))
                    last_price = last_price_res.scalars().first()
                    base = float(last_price.value) if last_price else float(settings_row.base_price or 0)
                    # Базовая цена для расчёта курса берём строго из настроек блюда
                    base_value = float(settings_row.base_price or 0)
                    step = float(settings_row.step or 0)
                    
                    if sales_qty_threshold > 0 and sales_count >= sales_qty_threshold:
                        # Продажи >= порога — увеличиваем цену на шаг
                        cand = base + abs(step)
                        if settings_row.min_price is not None:
                            cand = max(cand, float(settings_row.min_price))
                        if settings_row.max_price is not None:
                            cand = min(cand, float(settings_row.max_price))
                        new_price = cand
                    else:
                        # Продажи < порога (или порог не задан) — уменьшаем цену на шаг
                        cand = base - abs(step)
                        if settings_row.min_price is not None:
                            cand = max(cand, float(settings_row.min_price))
                        if settings_row.max_price is not None:
                            cand = min(cand, float(settings_row.max_price))
                        new_price = cand
                except Exception:
                    new_price = None

                # ВАЖНО: запись цен в iiko ЗАПРЕЩЕНА — проект работает с iiko только на чтение.
                # Динамическое ценообразование отключено, _push_price_to_iiko удалён.
                # Ничего не отправляем в iiko, в локальную БД цены/курсы тоже не пишем.
                # TTL как расписание: следующий допуск к попытке изменения цены (локальная БД)
                next_allowed = (now + dt.timedelta(minutes=ttl_min)) if ttl_min > 0 else None
                if new_price is not None:
                    logger.info(
                        "Price change skipped (write to iiko disabled): dish_id=%s new_price=%.2f",
                        dish.id,
                        float(new_price),
                    )

                # TTL: независимо от успеха пуша и даже при отсутствии изменения цены, ведём TTL как расписание
                # Это гарантирует попытку изменения цены не чаще одного окна TTL
                if ttl_min > 0:
                    if pcs:
                        pcs.next_change_allowed_at = next_allowed
                        db.add(pcs)
                    else:
                        db.add(PriceChangeState(dish_id=dish.id, next_change_allowed_at=next_allowed))

            await db.commit()

            try:
                async with self._db_session_factory() as db:
                    from app.models.iiko_settings import IikoSettings
                    result = await db.execute(select(IikoSettings).order_by(IikoSettings.id.asc()))
                    stored = result.scalars().first()
                    if stored and stored.active and stored.server_host:
                        mgr = get_iiko_server_auth_manager()
                        mgr.configure(stored.server_host, stored.server_login or "", stored.server_password or "")
                        await mgr.logout()
            except Exception:
                pass

    async def get_dish_sales_count_by_preset(self, preset_id: str) -> Dict[str, int]:
        """
        Запрос к iikoServer OLAP по сохранённому пресету (byPresetId) и возврат {product_id: sales_count} за период.

        Требование пользователя: жёстко зафиксировать диапазон дат — начало это предыдущая дата, конец это текущая дата.
        Реализация:
        - Авторизуемся через IikoServerAuthManager (переиспользуем session key и cookie)
        - GET /resto/api/v2/reports/olap/byPresetId/{presetId}?key=...&dateFrom=YYYY-MM-DD&dateTo=YYYY-MM-DD&summary=false
        - Ответ может быть в одном из форматов: data (строки), rows/columns/values (пивот), cells (плоский список)
        - В каждой записи учитываем только те столбцы/строки, где CloseTime попадает в интервал [start_dt, end_dt)
        - Идентифицируем блюдо по имени, затем маппим на product_id из нашей БД
        """
        # 1) Подготовка дат: начало — предыдущий день 00:00 локальной TZ, конец — текущее локальное время
        def _get_local_tz_counts() -> dt.tzinfo:
            try:
                tzname = settings.LOCAL_TIMEZONE
                if tzname:
                    try:
                        from zoneinfo import ZoneInfo
                        return ZoneInfo(str(tzname))
                    except Exception:
                        pass
            except Exception:
                pass
            try:
                return dt.datetime.now().astimezone().tzinfo  # type: ignore[return-value]
            except Exception:
                return dt.timezone.utc

        local_tz_counts = _get_local_tz_counts()
        now = dt.datetime.now(local_tz_counts)
        prev_day = (now.date() - dt.timedelta(days=1))
        start_dt = dt.datetime.combine(prev_day, dt.time.min).replace(tzinfo=local_tz_counts)
        end_dt = now

        # 2) Авторизация на iikoServer и подготовка HTTP‑клиента
        mgr = get_iiko_server_auth_manager()
        try:
            await mgr.ensure_authenticated()
        except Exception as e:
            logger.error("Unable to authenticate to iikoServer for OLAP preset: %s", e)
            return {}

        session_key = mgr.get_session_key()
        # Читаем host из БД, а не из .env
        base = ""
        try:
            async with self._db_session_factory() as db:
                from app.models.iiko_settings import IikoSettings
                result = await db.execute(select(IikoSettings).order_by(IikoSettings.id.asc()))
                stored = result.scalars().first()
                if stored and stored.server_host:
                    base = stored.server_host.rstrip("/")
        except Exception:
            pass
        if not base:
            logger.error("IIKO_SERVER_HOST is not configured in DB settings; cannot query OLAP by preset")
            return {}

        # Нормализуем базовый URL: убираем завершающий '/resto'
        if base.lower().endswith("/resto"):
            base = base[:-len("/resto")]
        report_url = f"{base}/resto/api/v2/reports/olap/byPresetId/{preset_id}"

        # Важно: dateFrom и dateTo должны быть разными датами, иначе сервер вернёт 409 Conflict
        # Всегда используем предыдущий день для dateFrom, чтобы гарантировать разные даты
        # Важно: сервер принимает только даты; верхняя граница эксклюзивная.
        # Чтобы включить текущий день, берём следующий день как dateTo.
        date_to = (end_dt + dt.timedelta(days=1)).date()
        date_from = date_to - dt.timedelta(days=1)
        
        # Принудительно убеждаемся, что даты разные
        if date_from >= date_to:
            date_from = date_to - dt.timedelta(days=1)
        
        params = {
            "key": session_key or "",
            "dateFrom": date_from.isoformat(),
            "dateTo": date_to.isoformat(),
            "summary": "false",
        }
        

        # Ключ кэша для агрегатов: отчёт зависит от пресета и диапазона дат
        cache_key = f"counts|{preset_id}|{params['dateFrom']}|{params['dateTo']}"
        now_utc = dt.datetime.now(local_tz_counts)
        cached_counts = self._olap_cache_counts.get(cache_key)
        if cached_counts and isinstance(cached_counts, dict):
            ts = cached_counts.get("ts")
            data = cached_counts.get("data")
            try:
                age = (now_utc - ts).total_seconds() if isinstance(ts, dt.datetime) else None
            except Exception:
                age = None
            if age is not None and age < self._olap_ttl_seconds and isinstance(data, dict):
                return data

        # 3) Загрузим маппинг названия блюда -> product_id из нашей БД
        name_to_pid: Dict[str, str] = {}
        try:
            async with self._db_session_factory() as db:  # type: AsyncSession
                res = await db.execute(select(Dish))
                for d in res.scalars().all():
                    if not d or not getattr(d, "product_id", None):
                        continue
                    nm = (d.name or "").strip().lower()
                    if nm:
                        name_to_pid[nm] = str(d.product_id)
        except Exception as e:
            pass

        # 4) Вспомогательные функции парсинга и фильтрации по CloseTime
        def parse_close_time(s: Any) -> Optional[dt.datetime]:
            if s is None:
                return None
            if isinstance(s, dt.datetime):
                if s.tzinfo is not None:
                    return s.astimezone(local_tz_counts)
                else:
                    return s.replace(tzinfo=local_tz_counts)
            try:
                txt = str(s).strip().replace('\u00a0', ' ').replace('\xa0', ' ')
            except Exception:
                return None
            fmts = [
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%dT%H:%M:%S.%f",
                "%d.%m.%y %H:%M",
                "%d.%m.%Y %H:%M",
            ]
            for fmt in fmts:
                try:
                    parsed = dt.datetime.strptime(txt, fmt)
                    return parsed.replace(tzinfo=local_tz_counts)
                except Exception:
                    pass
            # Попробуем урезать секунды
            try:
                if ":" in txt:
                    parts = txt.split(":")
                    if len(parts) >= 2:
                        candidate = ":".join(parts[:2])
                        for fmt2 in ("%Y-%m-%dT%H:%M", "%d.%m.%y %H:%M", "%d.%m.%Y %H:%M"):
                            try:
                                parsed = dt.datetime.strptime(candidate, fmt2)
                                return parsed.replace(tzinfo=local_tz_counts)
                            except Exception:
                                pass
            except Exception:
                pass
            return None

        def in_range(t: Optional[dt.datetime]) -> bool:
            if t is None:
                return False
            t_local = t.astimezone(local_tz_counts) if t.tzinfo is not None else t.replace(tzinfo=local_tz_counts)
            start_local = start_dt if start_dt.tzinfo is not None else start_dt.replace(tzinfo=local_tz_counts)
            end_local = end_dt if end_dt.tzinfo is not None else end_dt.replace(tzinfo=local_tz_counts)
            return start_local <= t_local < end_local

        def norm_name(x: Any) -> str:
            try:
                return str(x or "").strip().lower()
            except Exception:
                return ""

        def try_add_by_pid(target: Dict[str, float], pid: Optional[str], val: Any) -> None:
            try:
                if not pid:
                    return
                if val is None:
                    return
                f = float(val)
                target[str(pid)] = target.get(str(pid), 0.0) + f
            except Exception:
                return

        def try_add_by_name(target: Dict[str, float], name: Any, val: Any) -> None:
            try:
                nm = norm_name(name)
                pid = name_to_pid.get(nm)
                if not pid:
                    # Всегда аккумулируем в name_map, чтобы был доступен фолбэк по имени
                    if val is not None:
                        try:
                            f = float(val)
                            name_map[nm] = name_map.get(nm, 0.0) + f
                        except Exception:
                            pass
                    return
                if val is None:
                    return
                f = float(val)
                target[pid] = target.get(pid, 0.0) + f
                # Также ведём суммирование по имени для диагностики/фолбэка
                name_map[nm] = name_map.get(nm, 0.0) + f
            except Exception:
                return

        # 5) Выполним запрос и распарсим ответ в единый мап {product_id: qty}
        result_map: Dict[str, float] = {}
        client = await mgr.get_client()
        # Защита от параллельных вызовов по одному и тому же пресету и диапазону
        lock = self._olap_locks.setdefault(cache_key, asyncio.Lock())
        async with lock:
            # Повторно проверим кэш после ожидания локера
            cached_counts2 = self._olap_cache_counts.get(cache_key)
            if cached_counts2 and isinstance(cached_counts2, dict):
                ts2 = cached_counts2.get("ts")
                data2 = cached_counts2.get("data")
                try:
                    age2 = (dt.datetime.now(local_tz_counts) - ts2).total_seconds() if isinstance(ts2, dt.datetime) else None
                except Exception:
                    age2 = None
                if age2 is not None and age2 < self._olap_ttl_seconds and isinstance(data2, dict):
                    return data2

        async def do_request() -> Dict[str, float]:
            try:
                # Логируем URL и параметры (маскируем ключ)
                masked_params = dict(params)
                try:
                    if masked_params.get("key"):
                        k = str(masked_params["key"]) 
                        masked_params["key"] = (k[:6] + "…") if len(k) > 6 else "<set>"
                except Exception:
                    pass

                headers = {"Cookie": f"key={session_key}"} if session_key else None
                resp = await client.get(report_url, params=params, headers=headers, timeout=30)
                resp.raise_for_status()
                payload = resp.json()

                try:
                    print(
                        "OLAP counts response: status=%s url=%s dateFrom=%s dateTo=%s payload_sample=%s" % (
                            resp.status_code,
                        )
                    )
                except Exception:
                    pass

                try:
                    ctype = resp.headers.get("Content-Type", "")
                    size = None
                    try:
                        size = len(payload)  # type: ignore[arg-type]
                    except Exception:
                        size = None
                except Exception:
                    pass

                # Вариант 1: плоские строки в data
                if isinstance(payload, dict):
                    rows = payload.get("data")
                    if isinstance(rows, list):
                        # Лёгкая диагностика содержимого
                        try:
                            sample_keys = list(rows[0].keys())[:8] if rows else []
                        except Exception:
                            sample_keys = []
                        for row in rows:
                            if not isinstance(row, dict):
                                continue
                            # Предпочитаем productId, если он присутствует в строке ответа
                            pid = row.get("productId") or row.get("ProductId") or row.get("itemId") or row.get("ItemId")
                            nm = row.get("DishName") or row.get("name")
                            ct = parse_close_time(row.get("CloseTime"))
                            if in_range(ct):
                                val = row.get("DishAmountInt") or row.get("value") or row.get("Amount") or row.get("qty")
                                if pid:
                                    try_add_by_pid(result_map, str(pid), val)
                                else:
                                    try_add_by_name(result_map, nm, val)
                        return result_map

                    # Вариант 2: пивот rows/columns/values
                    rows2 = payload.get("rows")
                    cols2 = payload.get("columns")
                    vals2 = payload.get("values") or payload.get("cells") or payload.get("table")
                    row_idx_by_name: Dict[str, int] = {}
                    col_idxs_in_range: List[int] = []
                    if isinstance(rows2, list):
                        for i, r in enumerate(rows2):
                            nm = None
                            if isinstance(r, dict):
                                nm = r.get("DishName") or r.get("name")
                            else:
                                try:
                                    nm = str(r)
                                except Exception:
                                    nm = None
                            if nm:
                                row_idx_by_name[str(nm).strip().lower()] = i
                    if isinstance(cols2, list):
                        for j, c in enumerate(cols2):
                            ct_val = c.get("CloseTime") if isinstance(c, dict) else c
                            if ct_val is None and isinstance(c, dict):
                                ct_val = c.get("name") or c.get("value")
                            ct = parse_close_time(ct_val)
                            if in_range(ct):
                                col_idxs_in_range.append(j)
                    if row_idx_by_name and col_idxs_in_range and isinstance(vals2, list):
                        for nm_lower, i in row_idx_by_name.items():
                            if i < 0 or i >= len(vals2):
                                continue
                            row_vals = vals2[i]
                            if not isinstance(row_vals, list):
                                continue
                            for j in col_idxs_in_range:
                                if j < 0 or j >= len(row_vals):
                                    continue
                                cell = row_vals[j]
                                val = None
                                if isinstance(cell, (int, float)):
                                    val = float(cell)
                                elif isinstance(cell, dict):
                                    val = cell.get("DishAmountInt") or cell.get("value")
                                if val is not None:
                                    # nm_lower уже нормализовано — используем по имени
                                    try_add_by_name(result_map, nm_lower, val)
                        return result_map

                    # Вариант 3: плоский список cells
                    cells = payload.get("cells")
                    if isinstance(cells, list):
                        try:
                            sample_keys = list(cells[0].keys())[:8] if cells and isinstance(cells[0], dict) else []
                        except Exception:
                            sample_keys = []
                        for c in cells:
                            if not isinstance(c, dict):
                                continue
                            pid = c.get("productId") or c.get("ProductId") or c.get("itemId") or c.get("ItemId")
                            nm = c.get("DishName") or c.get("name")
                            ct = parse_close_time(c.get("CloseTime") or c.get("name") or c.get("column"))
                            if in_range(ct):
                                val = c.get("DishAmountInt") or c.get("value") or c.get("Amount") or c.get("qty")
                                if pid:
                                    try_add_by_pid(result_map, str(pid), val)
                                else:
                                    try_add_by_name(result_map, nm, val)
                        return result_map

                elif isinstance(payload, list):
                    try:
                        sample_keys = list(payload[0].keys())[:8] if payload and isinstance(payload[0], dict) else []
                    except Exception:
                        sample_keys = []
                    for row in payload:
                        if not isinstance(row, dict):
                            continue
                        pid = row.get("productId") or row.get("ProductId") or row.get("itemId") or row.get("ItemId")
                        nm = row.get("DishName") or row.get("name")
                        ct = parse_close_time(row.get("CloseTime") or row.get("name"))
                        if in_range(ct):
                            val = row.get("DishAmountInt") or row.get("value") or row.get("Amount") or row.get("qty")
                            if pid:
                                try_add_by_pid(result_map, str(pid), val)
                            else:
                                try_add_by_name(result_map, nm, val)
                    return result_map

                return result_map
            except httpx.HTTPStatusError as e:
                # на 401/403 попробуем переавторизоваться и повторить один раз
                code = e.response.status_code if e.response is not None else None
                if code in (401, 403):
                    await mgr.reauthenticate()
                    return await do_request()
                logger.error("OLAP preset HTTP error: %s", e)
                return result_map
            except Exception as e:
                # Транспортная ошибка (например, недоступен хост/порт, DNS, SSL).
                # Логируем URL, параметры и тип исключения для упрощения диагностики.
                try:
                    err_type = type(e).__name__
                except Exception:
                    err_type = "Exception"
                logger.error(
                    "OLAP preset request failed: %s (%s) url=%s params=%s",
                    e,
                    err_type,
                    report_url,
                    params,
                )
                return result_map

        final_map = await do_request()
        # Сохраняем фолбэк по именам для последующего цикла применения (и диагностики)
        try:
            sample_names = list(name_map.items())[:5]
        except Exception:
            sample_names = []
        # Преобразуем в int и сохраняем в поле для использования как фолбэк
        try:
            self._last_sales_by_name = {k: int(name_map.get(k, 0.0)) for k in (name_map or {}).keys()}
        except Exception:
            self._last_sales_by_name = {}
        try:
            sample_items = list(final_map.items())[:5]
        except Exception:
            sample_items = []
        # Округлим до int (DishAmountInt всегда целое количество)
        int_map = {pid: int(final_map.get(pid, 0.0)) for pid in final_map.keys()}
        # Кэшируем результат, чтобы не ходить в OLAP чаще TTL
        try:
            self._olap_cache_counts[cache_key] = {"ts": dt.datetime.now(local_tz_counts), "data": dict(int_map)}
        except Exception:
            pass
        return int_map

    async def get_olap_rows(self, preset_id: str, start_dt: dt.datetime, end_dt: dt.datetime) -> List[Dict[str, Any]]:
        """
        Единичный запрос к iikoServer OLAP по сохранённому пресету с нормализацией в список строк:
        [{product_id, name, close_time, amount}], отфильтрованный по [start_dt, end_dt).

        Это позволяет дальше считать продажи в точном окне для каждого блюда без дополнительных запросов.
        """
        rows_out: List[Dict[str, Any]] = []
        mgr = get_iiko_server_auth_manager()
        try:
            await mgr.ensure_authenticated()
        except Exception as e:
            logger.error("Unable to authenticate to iikoServer for OLAP rows: %s", e)
            return rows_out

        session_key = mgr.get_session_key()
        # Читаем host из БД, а не из .env
        base = ""
        try:
            async with self._db_session_factory() as db:
                from app.models.iiko_settings import IikoSettings
                result = await db.execute(select(IikoSettings).order_by(IikoSettings.id.asc()))
                stored = result.scalars().first()
                if stored and stored.server_host:
                    base = stored.server_host.rstrip("/")
        except Exception:
            pass
        if not base:
            logger.error("IIKO_SERVER_HOST is not configured in DB settings; cannot query OLAP by preset")
            return rows_out
        if base.lower().endswith("/resto"):
            base = base[:-len("/resto")]
        report_url = f"{base}/resto/api/v2/reports/olap/byPresetId/{preset_id}"

        # Важно: dateFrom и dateTo должны быть разными датами, иначе сервер вернёт 409 Conflict
        # Всегда используем предыдущий день для dateFrom, чтобы гарантировать разные даты
        # Важно: сервер принимает только даты; верхняя граница эксклюзивная.
        # Чтобы включить текущий день, берём следующий день как dateTo.
        date_to = (end_dt + dt.timedelta(days=1)).date()
        date_from = date_to - dt.timedelta(days=1)
        
        # Принудительно убеждаемся, что даты разные
        if date_from >= date_to:
            date_from = date_to - dt.timedelta(days=1)
        
        params = {
            "key": session_key or "",
            "dateFrom": date_from.isoformat(),
            "dateTo": date_to.isoformat(),
            "summary": "false",
        }
        

        # Ключ кэша: набор строк зависит от пресета и дат
        rows_cache_key = f"rows|{preset_id}|{params['dateFrom']}|{params['dateTo']}"
        def _get_local_tz_rows() -> dt.tzinfo:
            try:
                tzname = settings.LOCAL_TIMEZONE
                if tzname:
                    try:
                        from zoneinfo import ZoneInfo
                        return ZoneInfo(str(tzname))
                    except Exception:
                        pass
            except Exception:
                pass
            try:
                return dt.datetime.now().astimezone().tzinfo  # type: ignore[return-value]
            except Exception:
                return dt.timezone.utc
        local_tz_rows = _get_local_tz_rows()
        now_rows = dt.datetime.now(local_tz_rows)
        cached_rows = self._olap_cache_rows.get(rows_cache_key)
        if cached_rows and isinstance(cached_rows, dict):
            tsr = cached_rows.get("ts")
            datar = cached_rows.get("data")
            try:
                age_r = (now_rows - tsr).total_seconds() if isinstance(tsr, dt.datetime) else None
            except Exception:
                age_r = None
            if age_r is not None and age_r < self._olap_ttl_seconds and isinstance(datar, list):
                return [r for r in datar if isinstance(r, dict)]

        def parse_close_time(s: Any) -> Optional[dt.datetime]:
            if s is None:
                return None
            if isinstance(s, dt.datetime):
                if s.tzinfo is not None:
                    return s.astimezone(local_tz_rows)
                else:
                    return s.replace(tzinfo=local_tz_rows)
            try:
                txt = str(s).strip().replace('\u00a0', ' ').replace('\xa0', ' ')
            except Exception:
                return None
            fmts = [
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%dT%H:%M:%S.%f",
                "%d.%m.%y %H:%M",
                "%d.%m.%Y %H:%M",
            ]
            for fmt in fmts:
                try:
                    parsed = dt.datetime.strptime(txt, fmt)
                    return parsed.replace(tzinfo=local_tz_rows)
                except Exception:
                    pass
            try:
                if ":" in txt:
                    parts = txt.split(":")
                    if len(parts) >= 2:
                        candidate = ":".join(parts[:2])
                        for fmt2 in ("%Y-%m-%dT%H:%M", "%d.%m.%y %H:%M", "%d.%m.%Y %H:%M"):
                            try:
                                parsed = dt.datetime.strptime(candidate, fmt2)
                                return parsed.replace(tzinfo=local_tz_rows)
                            except Exception:
                                pass
            except Exception:
                pass
            return None

        def in_range(t: Optional[dt.datetime]) -> bool:
            if t is None:
                return False
            t_local = t.astimezone(local_tz_rows) if t.tzinfo is not None else t.replace(tzinfo=local_tz_rows)
            start_local = start_dt if start_dt.tzinfo is not None else start_dt.replace(tzinfo=local_tz_rows)
            end_local = end_dt if end_dt.tzinfo is not None else end_dt.replace(tzinfo=local_tz_rows)
            return start_local <= t_local < end_local

        client = await mgr.get_client()
        # Лок от параллельных вызовов по одному и тому же ключу
        rows_lock = self._olap_locks.setdefault(rows_cache_key, asyncio.Lock())
        async with rows_lock:
            cached_rows2 = self._olap_cache_rows.get(rows_cache_key)
            if cached_rows2 and isinstance(cached_rows2, dict):
                tsr2 = cached_rows2.get("ts")
                datar2 = cached_rows2.get("data")
                try:
                    age_r2 = (dt.datetime.now(local_tz_rows) - tsr2).total_seconds() if isinstance(tsr2, dt.datetime) else None
                except Exception:
                    age_r2 = None
                if age_r2 is not None and age_r2 < self._olap_ttl_seconds and isinstance(datar2, list):
                    return [r for r in datar2 if isinstance(r, dict)]

        async def do_request() -> None:
            try:
                headers = {"Cookie": f"key={session_key}"} if session_key else None
                resp = await client.get(report_url, params=params, headers=headers, timeout=30)
                resp.raise_for_status()
                payload = resp.json()

                try:
                    print(
                        "OLAP rows response: status=%s" % (
                            resp.status_code,
                        )
                    )
                except Exception:
                    pass

                # data rows
                if isinstance(payload, dict):
                    data_rows = payload.get("data")
                    if isinstance(data_rows, list):
                        for row in data_rows:
                            if not isinstance(row, dict):
                                continue
                            pid = row.get("productId") or row.get("ProductId") or row.get("itemId") or row.get("ItemId")
                            nm = row.get("DishName") or row.get("name")
                            ct = parse_close_time(row.get("CloseTime"))
                            if in_range(ct):
                                val = row.get("DishAmountInt") or row.get("value") or row.get("Amount") or row.get("qty")
                                try:
                                    amount = float(val or 0.0)
                                except Exception:
                                    amount = 0.0
                                rows_out.append({
                                    "product_id": (str(pid) if pid else None),
                                    "name": nm,
                                    "close_time": ct,
                                    "amount": amount,
                                })
                        return

                    # pivot rows/columns/values or cells
                    rows2 = payload.get("rows")
                    cols2 = payload.get("columns")
                    vals2 = payload.get("values") or payload.get("cells") or payload.get("table")
                    # build row name index and columns in range
                    row_names: List[str] = []
                    if isinstance(rows2, list):
                        for r in rows2:
                            nm = None
                            if isinstance(r, dict):
                                nm = r.get("DishName") or r.get("name")
                            else:
                                try:
                                    nm = str(r)
                                except Exception:
                                    nm = None
                            row_names.append((str(nm).strip().lower()) if nm else "")
                    col_idxs_in_range: List[int] = []
                    if isinstance(cols2, list):
                        for j, c in enumerate(cols2):
                            ct_val = c.get("CloseTime") if isinstance(c, dict) else c
                            if ct_val is None and isinstance(c, dict):
                                ct_val = c.get("name") or c.get("value")
                            ct = parse_close_time(ct_val)
                            if in_range(ct):
                                col_idxs_in_range.append(j)
                    if row_names and col_idxs_in_range and isinstance(vals2, list):
                        for i, nm_lower in enumerate(row_names):
                            if i < 0 or i >= len(vals2):
                                continue
                            row_vals = vals2[i]
                            if not isinstance(row_vals, list):
                                continue
                            for j in col_idxs_in_range:
                                if j < 0 or j >= len(row_vals):
                                    continue
                                cell = row_vals[j]
                                # Получим фактическое время из столбца j
                                c = cols2[j] if isinstance(cols2, list) and j < len(cols2) else None
                                ct_val = c.get("CloseTime") if isinstance(c, dict) else c
                                if ct_val is None and isinstance(c, dict):
                                    ct_val = c.get("name") or c.get("value")
                                ct = parse_close_time(ct_val)
                                val = None
                                if isinstance(cell, (int, float)):
                                    val = float(cell)
                                elif isinstance(cell, dict):
                                    val = cell.get("DishAmountInt") or cell.get("value")
                                try:
                                    amount = float(val or 0.0)
                                except Exception:
                                    amount = 0.0
                                rows_out.append({
                                    "product_id": None,
                                    "name": nm_lower,
                                    "close_time": ct,
                                    "amount": amount,
                                })
                        return

                    # flat cells
                    cells = payload.get("cells")
                    if isinstance(cells, list):
                        for c in cells:
                            if not isinstance(c, dict):
                                continue
                            pid = c.get("productId") or c.get("ProductId") or c.get("itemId") or c.get("ItemId")
                            nm = c.get("DishName") or c.get("name")
                            ct = parse_close_time(c.get("CloseTime") or c.get("name") or c.get("column"))
                            if in_range(ct):
                                val = c.get("DishAmountInt") or c.get("value") or c.get("Amount") or c.get("qty")
                                try:
                                    amount = float(val or 0.0)
                                except Exception:
                                    amount = 0.0
                                rows_out.append({
                                    "product_id": (str(pid) if pid else None),
                                    "name": nm,
                                    "close_time": ct,
                                    "amount": amount,
                                })
                        return

                elif isinstance(payload, list):
                    for row in payload:
                        if not isinstance(row, dict):
                            continue
                        pid = row.get("productId") or row.get("ProductId") or row.get("itemId") or row.get("ItemId")
                        nm = row.get("DishName") or row.get("name")
                        ct = parse_close_time(row.get("CloseTime") or row.get("name"))
                        if in_range(ct):
                            val = row.get("DishAmountInt") or row.get("value") or row.get("Amount") or row.get("qty")
                            try:
                                amount = float(val or 0.0)
                            except Exception:
                                amount = 0.0
                            rows_out.append({
                                "product_id": (str(pid) if pid else None),
                                "name": nm,
                                "close_time": ct,
                                "amount": amount,
                            })
                    return

            except httpx.HTTPStatusError as e:
                code = e.response.status_code if e.response is not None else None
                if code in (401, 403):
                    await mgr.reauthenticate()
                    return await do_request()
                pass
            except Exception as e:
                pass

        await do_request()
        # Кэшируем результат
        try:
            self._olap_cache_rows[rows_cache_key] = {"ts": dt.datetime.now(local_tz_rows), "data": list(rows_out)}
        except Exception:
            pass
        return rows_out

