from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple
import time
import json
from pathlib import Path
import os

import httpx
from httpx import HTTPStatusError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.utils.logger import setup_logger
from app.models.dish import Dish
from app.models.price import Price
from app.services.iiko_auth import get_iiko_server_auth_manager
from app.services.iiko_cloud import (
    extract_stoplist_names_and_ids,
    extract_nomenclature_id_to_name,
)

logger = setup_logger(__name__)

# --- Simple in-memory caches to avoid hammering iikoCloud and to survive frequent frontend polling ---
# We use monotonic time to compute TTLs.
_CACHE: Dict[str, Any] = {
    "cloud_token": None,
    "cloud_token_ts": 0.0,
    "terminal_group_ids": None,
    "terminal_group_ids_ts": 0.0,
    "nomenclature_map": None,  # Dict[str, str] productId -> name
    "nomenclature_ts": 0.0,
    "stoplist_names": None,  # List[str]
    "stoplist_ids": None,    # List[str]
    "stoplist_ts": 0.0,
    "cooldown_until": 0.0,  # when > now, we avoid calling cloud APIs due to recent 429
}

# Cache TTLs (seconds)
_TOKEN_TTL = 3600           # 1 hour — aligns with iikoCloud token lifetime to reduce /access_token calls
_TERMINAL_GROUPS_TTL = 600  # 10 minutes
_NOMENCLATURE_TTL = 600     # 10 minutes
# Stop-list in-memory TTL: driven by env IIKO_STOPLIST_REFRESH_INTERVAL_MINUTES when set (>0), otherwise default ~45 seconds
_STOPLIST_TTL = int(settings.IIKO_STOPLIST_REFRESH_INTERVAL_MINUTES or 0) * 60 or 45
_COOLDOWN_SECONDS = 120     # 2 minutes cool-down on 429 Too Many Requests

# Shared disk-backed cache (to bridge multiple processes like API server and fetcher script)
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_STOPLIST_CACHE_FILE = _PROJECT_ROOT / "storage" / "stoplist_cache.json"
_STOPLIST_DISK_TTL = 300  # 5 minutes TTL for disk cache

def _now() -> float:
    try:
        return time.monotonic()
    except Exception:
        return time.time()


class IikoService:
    """
    Service for integrating with iiko APIs.
    Supports two modes:
    - cloud: iikoCloud public API (recommended)
    - server: on-prem iikoServer API (experimental placeholder)
    """

    def __init__(self) -> None:
        self.mode = (settings.IIKO_MODE or "cloud").lower()
        self.base_url = settings.IIKO_BASE_URL.rstrip("/") if settings.IIKO_BASE_URL else ""
        # Основной ключ из настроек. Если он отсутствует, попробуем алиас переменной окружения API_CLOUD
        self.api_key = settings.IIKO_API_KEY
        if not self.api_key:
            try:
                import os
                alias_key = os.getenv("API_CLOUD")
                if alias_key:
                    self.api_key = alias_key
                    logger.info("IikoService: using API_CLOUD env alias as IIKO_API_KEY")
            except Exception:
                # Безопасно игнорируем, просто остаёмся без ключа
                pass
        self.organization_id = settings.IIKO_ORGANIZATION_ID
        self.server_host = settings.IIKO_SERVER_HOST
        self.server_login = settings.IIKO_SERVER_LOGIN
        self.server_password = settings.IIKO_SERVER_PASSWORD

    def _normalize_server_base(self) -> str:
        """Normalize server host to a base URL suitable for iikoServer.
        - Ensure scheme (default to http:// if missing)
        - Strip trailing slashes
        - Remove trailing '/resto' if user included it
        """
        host = (self.server_host or "").strip()
        if not host:
            return ""
        # Add scheme if missing
        if not host.lower().startswith("http://") and not host.lower().startswith("https://"):
            host = f"http://{host}"
        # Trim trailing slash
        host = host.rstrip("/")
        # If user provided .../resto, drop it to avoid duplicating in auth path
        if host.lower().endswith("/resto"):
            host = host[:-len("/resto")]
        logger.info(f"iikoServer host normalized to: {host}")
        return host

    async def _get_cloud_access_token(self, client: httpx.AsyncClient) -> str:
        """Obtain iikoCloud access token.
        Some deployments expect the parameter name 'apiLogin' instead of 'apiKey'.
        We try multiple variants (POST/GET, apiLogin/apiKey) to maximize compatibility.
        """
        if not self.api_key:
            raise ValueError("IIKO_API_KEY is not configured")
        # Cache: reuse token if still fresh
        now = _now()
        tok = _CACHE.get("cloud_token")
        ts = _CACHE.get("cloud_token_ts") or 0.0
        if isinstance(tok, str) and now - ts < _TOKEN_TTL:
            try:
                logger.info("iikoCloud access_token: using cached token")
            except Exception:
                pass
            return tok
        url = f"{self.base_url}/api/1/access_token"
        # Attempt 1: POST with apiLogin in JSON body (per current iikoCloud docs)
        try:
            logger.info("iikoCloud access_token: POST {apiLogin}")
            resp = await client.post(url, json={"apiLogin": self.api_key}, timeout=30)
            if resp.status_code < 400:
                token = resp.json()
            else:
                raise httpx.HTTPStatusError("POST apiLogin failed", request=resp.request, response=resp)
        except Exception:
            # Attempt 2: GET with apiLogin as query
            logger.info("iikoCloud access_token: GET {apiLogin} fallback")
            resp = await client.get(url, params={"apiLogin": self.api_key}, timeout=30)
            if resp.status_code >= 400:
                # Attempt 3: GET with apiKey (legacy/alias)
                logger.info("iikoCloud access_token: GET {apiKey} fallback")
                resp = await client.get(url, params={"apiKey": self.api_key}, timeout=30)
            resp.raise_for_status()
            token = resp.json()
        if isinstance(token, dict):
            # Some proxies wrap token in {token: '...'}
            token = token.get("token") or token.get("access_token")
        if not isinstance(token, str):
            raise RuntimeError(f"Unexpected access_token response: {resp.text}")
        # Store in cache
        _CACHE["cloud_token"] = token
        _CACHE["cloud_token_ts"] = _now()
        return token

    async def _fetch_cloud_nomenclature(self, client: httpx.AsyncClient, access_token: str) -> Dict[str, Any]:
        if not self.organization_id:
            raise ValueError("IIKO_ORGANIZATION_ID is not configured")
        url = f"{self.base_url}/api/1/nomenclature"
        headers = {"Authorization": f"Bearer {access_token}"}
        payload = {
            "organizationId": self.organization_id,
            "startRevision": 0,
        }
        resp = await client.post(url, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        return resp.json()

    async def _fetch_server_nomenclature(self, client: httpx.AsyncClient) -> Dict[str, Any]:
        """Experimental: attempt to fetch nomenclature from iikoServer.
        Implementation may vary by installation; this uses common endpoints.
        """
        if not self.server_host or not self.server_login or not self.server_password:
            raise ValueError("IIKO_SERVER_HOST, IIKO_SERVER_LOGIN, IIKO_SERVER_PASSWORD must be configured")
        base = self._normalize_server_base()
        # Use singleton auth manager: authenticate once and reuse persistent session/cookies
        mgr = get_iiko_server_auth_manager()
        mgr.configure(base, self.server_login, self.server_password)
        await mgr.ensure_authenticated()
        persistent_client = await mgr.get_client()
        # Inspect auth state and log it for diagnostics
        key = mgr.get_session_key()
        cookie_key = None
        try:
            cookie_key = persistent_client.cookies.get("key")  # type: ignore[attr-defined]
        except Exception:
            cookie_key = None
        if not key and not cookie_key:
            logger.warning("iikoServer auth state: no session key and no 'key' cookie present; forcing reauthentication")
            await mgr.reauthenticate()
            key = mgr.get_session_key()
            try:
                cookie_key = persistent_client.cookies.get("key")  # type: ignore[attr-defined]
            except Exception:
                cookie_key = None
        logger.info(
            "iikoServer auth state: key=%s, cookie_key=%s",
            (key[:8] + "…") if key else "<none>",
            "present" if cookie_key else "<none>",
        )
        # Try entities/products/list using form-urlencoded as per working test script
        post_url = f"{base}/resto/api/v2/entities/products/list"
        # Include session key from auth if available
        params = {"key": key} if key else None
        form_headers = {
            "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
            "Accept": "application/json, text/xml;q=0.9, */*;q=0.1",
        }
        form_data = {
            "includeDeleted": "false",
            "revisionFrom": "-1",
        }
        try:
            logger.info("Requesting iikoServer products via POST form-urlencoded /resto/api/v2/entities/products/list")
            resp = await persistent_client.post(post_url, params=params, headers=form_headers, data=form_data, timeout=60)
            resp.raise_for_status()
            logger.info(f"iikoServer products HTTP {resp.status_code}")
            # Оптимизация: ожидаем корректный JSON и разбираем только его
            return resp.json()
        except HTTPStatusError as e:
            code = e.response.status_code if e.response is not None else None
            # If unauthorized, reauthenticate once and retry
            if code in (401, 403):
                logger.warning("iikoServer returned %s for nomenclature, reauthenticating and retrying once", code)
                await mgr.reauthenticate()
                resp2 = await persistent_client.post(post_url, params=params, headers=form_headers, data=form_data, timeout=60)
                try:
                    resp2.raise_for_status()
                    try:
                        return resp2.json()
                    except Exception:
                        txt2 = resp2.text or ""
                        if txt2.strip().startswith("<"):
                            return {"xml": txt2}
                        raise RuntimeError("Unexpected response format from iikoServer products endpoint after retry")
                except Exception:
                    raise RuntimeError(f"iikoServer products HTTP error after retry: {resp2.status_code}")
            # Log response details for diagnostics
            try:
                body = (e.response.text or "") if e.response is not None else ""
                ctype = e.response.headers.get("Content-Type", "") if e.response is not None else ""
                url = str(e.response.request.url) if e.response is not None else post_url
                logger.error(
                    "iikoServer products HTTP error %s; URL=%s; Content-Type=%s; Body=%s",
                    code,
                    url,
                    ctype,
                    body[:300].replace("\n", " ")
                )
            except Exception:
                pass
            raise RuntimeError("Unable to fetch iikoServer products due to connectivity or server error.")
        except Exception:
            raise RuntimeError("Unable to fetch iikoServer products due to connectivity or server error.")

    @staticmethod
    def _extract_products_cloud(nomenclature: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract product entries with a best-effort price from iikoCloud response."""
        products = nomenclature.get("products") or []
        result: List[Dict[str, Any]] = []
        for p in products:
            name = p.get("name") or ""
            prod_id = p.get("id")
            price_value: float = 0.0
            # price could be in sizePrices[].price.currentPrice or sizePrices[].price.fixedPrice
            sizes = p.get("sizePrices") or []
            if sizes:
                price_obj = sizes[0].get("price") or {}
                current = price_obj.get("currentPrice")
                fixed = price_obj.get("fixedPrice")
                if isinstance(current, (int, float)):
                    price_value = float(current)
                elif isinstance(fixed, (int, float)):
                    price_value = float(fixed)
            elif isinstance(p.get("price"), (int, float)):
                price_value = float(p["price"])  # fallback
            code = p.get("code") or p.get("sku") or p.get("num") or p.get("nomenclatureCode")
            result.append({"id": prod_id, "name": name, "price": price_value, "code": code})
        return result

    @staticmethod
    def _extract_products_server(nomenclature: Any) -> List[Dict[str, Any]]:
        """Извлекает продукты из ответа iikoServer (устойчиво к различным форматам).
        Поддерживает:
        - верхнеуровневый список
        - объект с ключами items/products/result/data (списки)
        - для цены учитывает поля price/currentPrice/salePrice/defaultSalePrice,
          а также структуру sizePrices[*].price.{currentPrice|fixedPrice} и коллекции prices/priceList.
        """
        # 1) Нормализуем список элементов
        items: List[Dict[str, Any]] = []
        if isinstance(nomenclature, list):
            items = [p for p in nomenclature if isinstance(p, dict)]
        elif isinstance(nomenclature, dict):
            for key in ("items", "products", "result", "data"):
                val = nomenclature.get(key)
                if isinstance(val, list):
                    items = [p for p in val if isinstance(p, dict)]
                    if items:
                        break
        else:
            return []

        def to_float(x: Any) -> Optional[float]:
            if isinstance(x, (int, float)):
                try:
                    return float(x)
                except Exception:
                    return None
            if isinstance(x, str):
                try:
                    return float(x.replace(",", "."))
                except Exception:
                    return None
            return None

        def compute_price(p: Dict[str, Any]) -> float:
            # Простые ключи или вложенные объекты цены
            for key in ("currentPrice", "salePrice", "defaultSalePrice", "price"):
                v = p.get(key)
                if isinstance(v, dict):
                    for kk in ("currentPrice", "fixedPrice", "value", "amount"):
                        vv = to_float(v.get(kk))
                        if vv and vv > 0:
                            return vv
                else:
                    vv = to_float(v)
                    if vv and vv > 0:
                        return vv
            # sizePrices
            sizes = p.get("sizePrices")
            if isinstance(sizes, list) and sizes:
                candidates: List[float] = []
                for sp in sizes:
                    if not isinstance(sp, dict):
                        continue
                    v = sp.get("price")
                    if isinstance(v, dict):
                        for kk in ("currentPrice", "fixedPrice", "value", "amount"):
                            vv = to_float(v.get(kk))
                            if vv and vv > 0:
                                candidates.append(vv)
                    else:
                        vv = to_float(v)
                        if vv and vv > 0:
                            candidates.append(vv)
                if candidates:
                    return max(candidates)
            # prices / priceList
            for coll_key in ("prices", "priceList"):
                coll = p.get(coll_key)
                if isinstance(coll, list) and coll:
                    candidates: List[float] = []
                    for el in coll:
                        if not isinstance(el, dict):
                            continue
                        v = el.get("price") or el.get("value") or el.get("amount")
                        vv = to_float(v)
                        if vv and vv > 0:
                            candidates.append(vv)
                        elif isinstance(v, dict):
                            for kk in ("currentPrice", "fixedPrice", "value", "amount"):
                                vv2 = to_float(v.get(kk))
                                if vv2 and vv2 > 0:
                                    candidates.append(vv2)
                    if candidates:
                        return max(candidates)
            return 0.0

        result: List[Dict[str, Any]] = []
        for p in items:
            prod_id = p.get("id") or p.get("guid") or p.get("uuid") or p.get("productId")
            name = p.get("name") or p.get("productName") or ""
            price_value = compute_price(p)
            code = p.get("code") or p.get("num") or p.get("sku") or p.get("nomenclatureCode")
            result.append({"id": prod_id, "name": name, "price": price_value, "code": code})
        return result

    async def fetch_products(self) -> List[Dict[str, Any]]:
        """Fetch products with prices from the configured iiko API."""
        async with httpx.AsyncClient() as client:
            if self.mode == "cloud":
                token = await self._get_cloud_access_token(client)
                nom = await self._fetch_cloud_nomenclature(client, token)
                return self._extract_products_cloud(nom)
            elif self.mode == "server":
                nom = await self._fetch_server_nomenclature(client)
                return self._extract_products_server(nom)
            else:
                raise ValueError(f"Unsupported IIKO_MODE: {self.mode}")

    async def fetch_stoplist_names(self, from_webhook: bool = False) -> List[str]:
        """
        Получить список наименований блюд, попавших в стоп‑лист через iikoCloud.
        Возвращает список имен блюд (str). Если режим не cloud или что-то пошло не так — возвращает пустой список.
        """
        try:
            # Диагностика входных параметров, чтобы легче было отслеживать источник вызова
            try:
                logger.info("fetch_stoplist_names: mode=%s, from_webhook=%s", self.mode, from_webhook)
            except Exception:
                pass
            # Пробуем iikoCloud только когда:
            # - режим cloud
            # - ИЛИ вызов инициирован вебхуком (from_webhook=True)
            # В остальных случаях (например, IIKO_MODE=server) не дергаем клауд без сигнала вебхука,
            # а используем кэш, обновлённый вебхуком, чтобы избежать лишних запросов и 429.
            if not self.base_url or not self.api_key or not self.organization_id:
                logger.warning("fetch_stoplist_names: iikoCloud is not fully configured")
                return []
            # Периодический опрос по интервалу: если задан (>0) и кэш устарел,
            # разрешаем единичный вызов iikoCloud даже в серверном режиме (без вебхука).
            force_cloud_due_to_interval = False
            try:
                interval_min = int(settings.IIKO_STOPLIST_REFRESH_INTERVAL_MINUTES or 0)
            except Exception:
                interval_min = 0
            if interval_min > 0:
                now_check = _now()
                last_ts = float(_CACHE.get("stoplist_ts") or 0.0)
                if last_ts <= 0.0:
                    # Попробуем прочитать возраст из дискового кэша
                    try:
                        p = _STOPLIST_CACHE_FILE
                        if p.exists():
                            raw = p.read_text(encoding="utf-8")
                            data = json.loads(raw)
                            last_ts = float(data.get("ts") or 0.0)
                    except Exception:
                        last_ts = 0.0
                age_sec = (now_check - last_ts) if last_ts > 0.0 else (interval_min * 60 + 1)
                if age_sec >= interval_min * 60:
                    force_cloud_due_to_interval = True
                    try:
                        logger.info(
                            "fetch_stoplist_names(server-mode): refresh interval %d min expired (age=%ds), will call iikoCloud",
                            interval_min,
                            int(age_sec),
                        )
                    except Exception:
                        pass
            if self.mode != "cloud" and not (from_webhook or force_cloud_due_to_interval):
                # Не клауд-режим и вызов не из вебхука — возвращаем кэш, не дергаем клауд
                now_nc = _now()
                cached_stop = _CACHE.get("stoplist_names")
                cached_stop_ts = _CACHE.get("stoplist_ts") or 0.0
                if isinstance(cached_stop, list) and now_nc - cached_stop_ts < _STOPLIST_TTL:
                    if len(cached_stop) > 0:
                        logger.info("fetch_stoplist_names(server-mode): using cached stoplist (%d items)", len(cached_stop))
                        return list(cached_stop)
                # Fallback на диск
                def _read_stoplist_cache_from_disk_local() -> Optional[List[str]]:
                    try:
                        p = _STOPLIST_CACHE_FILE
                        if not p.exists():
                            return None
                        raw = p.read_text(encoding="utf-8")
                        data = json.loads(raw)
                        names = data.get("names") or []
                        if not isinstance(names, list):
                            return None
                        names_out = [str(n).strip() for n in names if isinstance(n, str) and str(n).strip()]
                        logger.info("fetch_stoplist_names(server-mode): using disk stoplist cache (%d items)", len(names_out))
                        return names_out
                    except Exception:
                        return None
                disk_cached_nc = _read_stoplist_cache_from_disk_local()
                if disk_cached_nc:
                    return disk_cached_nc
                # Нет кэша — возвращаем пусто, чтобы фронт показал SOLD OUT только на основании серверного API
                logger.info("fetch_stoplist_names(server-mode): no cache available, returning empty list")
                return []
            if self.mode != "cloud" and from_webhook:
                logger.info(
                    "fetch_stoplist_names: attempting iikoCloud stop-list in server mode due to webhook signal"
                )

            now = _now()

            def _read_stoplist_cache_from_disk(allow_stale: bool = False) -> Optional[List[str]]:
                try:
                    p = _STOPLIST_CACHE_FILE
                    if not p.exists():
                        return None
                    raw = p.read_text(encoding="utf-8")
                    data = json.loads(raw)
                    ts = float(data.get("ts") or 0.0)
                    names = data.get("names") or []
                    if not isinstance(names, list):
                        return None
                    age = int(now - ts)
                    names_out = [str(n).strip() for n in names if isinstance(n, str) and str(n).strip()]
                    if age > _STOPLIST_DISK_TTL:
                        # If cooldown is active or caller explicitly allows stale cache, use it to avoid empty results
                        if allow_stale and len(names_out) > 0:
                            logger.warning(
                                "fetch_stoplist_names: disk cache expired (%ds old), using STALE cache due to cooldown (%d items)",
                                age,
                                len(names_out),
                            )
                            return names_out
                        logger.info("fetch_stoplist_names: disk cache expired (%ds old)", age)
                        return None
                    logger.info("fetch_stoplist_names: using disk stoplist cache (%d items)", len(names_out))
                    return names_out
                except Exception as e:
                    logger.warning(f"fetch_stoplist_names: read stoplist disk cache failed: {e}")
                    return None

            def _write_stoplist_cache_to_disk(names: List[str], ids: Optional[List[str]] = None) -> None:
                try:
                    p = _STOPLIST_CACHE_FILE
                    p.parent.mkdir(parents=True, exist_ok=True)
                    payload = {"ts": now, "names": list(names)}
                    if isinstance(ids, list):
                        payload["ids"] = list(ids)
                    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                    logger.info("fetch_stoplist_names: updated disk stoplist cache (%d items)", len(names))
                except Exception as e:
                    logger.warning(f"fetch_stoplist_names: write stoplist disk cache failed: {e}")
            # Если недавно был 429, не шлём запросы и пытаемся вернуть кэш
            cooldown_until = _CACHE.get("cooldown_until") or 0.0
            cooldown_active = now < cooldown_until
            if cooldown_active:
                cached = _CACHE.get("stoplist_names") or []
                if isinstance(cached, list) and len(cached) > 0:
                    logger.warning(
                        "fetch_stoplist_names: cooldown active (until %.0f), returning cached stoplist (%d items)",
                        cooldown_until,
                        len(cached),
                    )
                    return list(cached)
                logger.warning(
                    "fetch_stoplist_names: cooldown active (until %.0f), no cached stoplist available",
                    cooldown_until,
                )
                # Fallback to disk-backed cache to avoid empty result during cooldown
                disk_cached = _read_stoplist_cache_from_disk(allow_stale=True)
                if disk_cached:
                    return disk_cached
                return []

            # Быстрый кэш: если стоп-лист свежий — возвращаем его сразу
            cached_stop = _CACHE.get("stoplist_names")
            cached_stop_ts = _CACHE.get("stoplist_ts") or 0.0
            if isinstance(cached_stop, list) and now - cached_stop_ts < _STOPLIST_TTL:
                if len(cached_stop) > 0:
                    logger.info("fetch_stoplist_names: using cached stoplist (%d items)", len(cached_stop))
                    return list(cached_stop)
                else:
                    logger.info("fetch_stoplist_names: cached stoplist is empty; ignoring memory cache and trying disk/fresh fetch")
            # Fallback: try disk cache if memory cache is missing or stale
            disk_cached = _read_stoplist_cache_from_disk()
            if disk_cached:
                return disk_cached

            async with httpx.AsyncClient(timeout=30) as client:
                # 1) Получаем access_token
                token = await self._get_cloud_access_token(client)
                headers = {"Authorization": f"Bearer {token}"}

                # 2) Получаем terminal group ids (нужны для запроса стоп-листа)
                # Сначала пробуем кэш
                group_ids: List[str] = []
                cached_tg_ids = _CACHE.get("terminal_group_ids")
                cached_tg_ts = _CACHE.get("terminal_group_ids_ts") or 0.0
                if isinstance(cached_tg_ids, list) and now - cached_tg_ts < _TERMINAL_GROUPS_TTL:
                    group_ids = list(cached_tg_ids)
                    logger.info("fetch_stoplist_names: using cached terminal group ids (%d)", len(group_ids))
                else:
                    tg_url = f"{self.base_url}/api/1/terminal_groups"
                    # terminal_groups expects organizationIds (array of GUIDs)
                    tg_payload = {"organizationIds": [self.organization_id]}
                    try:
                        logger.info(
                            "[iikoCloud] POST %s payload: organizationIds=%s",
                            tg_url,
                            tg_payload.get("organizationIds")
                        )
                    except Exception:
                        pass
                    try:
                        tg_resp = await client.post(tg_url, headers=headers, json=tg_payload)
                        tg_resp.raise_for_status()
                    except HTTPStatusError as e:
                        if e.response is not None and e.response.status_code == 429:
                            _CACHE["cooldown_until"] = _now() + _COOLDOWN_SECONDS
                            cached = _CACHE.get("stoplist_names") or []
                            logger.warning("iikoCloud terminal_groups: 429 Too Many Requests; activating cooldown for %ds", _COOLDOWN_SECONDS)
                            return list(cached)
                        raise
                    tg_data = tg_resp.json() or {}
                    # Ответ может иметь разные формы, попробуем извлечь id из известных мест
                    try:
                        # Формат: { "terminalGroups": [ { "items": [ { "id": "..." }, ... ] } ] }
                        # или { "terminalGroups": [ { "id": "..." }, ... ] }
                        tgs = tg_data.get("terminalGroups") or tg_data.get("items") or tg_data
                        if isinstance(tgs, list):
                            for g in tgs:
                                # Если внутри есть items — берём id из них
                                inner_items = g.get("items")
                                if isinstance(inner_items, list):
                                    for gi in inner_items:
                                        gid = gi.get("id") or gi.get("groupId") or gi.get("terminalGroupId")
                                        if gid:
                                            group_ids.append(str(gid))
                                else:
                                    gid = g.get("id") or g.get("groupId") or g.get("terminalGroupId")
                                    if gid:
                                        group_ids.append(str(gid))
                        elif isinstance(tgs, dict):
                            # иногда { "items": [ ... ] }
                            items = tgs.get("items")
                            if isinstance(items, list):
                                for g in items:
                                    gid = g.get("id") or g.get("groupId") or g.get("terminalGroupId")
                                    if gid:
                                        group_ids.append(str(gid))
                    except Exception:
                        pass
                    if not group_ids:
                        logger.warning("fetch_stoplist_names: no terminal group ids found")
                        return []
                    # Сохраняем кэш терминальных групп
                    _CACHE["terminal_group_ids"] = list(group_ids)
                    _CACHE["terminal_group_ids_ts"] = _now()

                # 3) Запрос стоп-листа
                sl_url = f"{self.base_url}/api/1/stop_lists"
                # stop_lists expects organizationIds (array), not singular organizationId
                sl_payload = {"organizationIds": [self.organization_id], "terminalGroupIds": group_ids}
                try:
                    logger.info(
                        "[iikoCloud] POST %s payload: organizationIds=%s, terminalGroupIds=%s",
                        sl_url,
                        sl_payload.get("organizationIds"),
                        sl_payload.get("terminalGroupIds")
                    )
                except Exception:
                    pass
                try:
                    sl_resp = await client.post(sl_url, headers=headers, json=sl_payload)
                    sl_resp.raise_for_status()
                except HTTPStatusError as e:
                    if e.response is not None and e.response.status_code == 429:
                        _CACHE["cooldown_until"] = _now() + _COOLDOWN_SECONDS
                        cached = _CACHE.get("stoplist_names") or []
                        logger.warning("iikoCloud stop_lists: 429 Too Many Requests; activating cooldown for %ds", _COOLDOWN_SECONDS)
                        if isinstance(cached, list) and len(cached) > 0:
                            return list(cached)
                        # During cooldown, allow using stale disk cache if available
                        disk_cached = _read_stoplist_cache_from_disk(allow_stale=True)
                        if disk_cached:
                            return disk_cached
                        return []
                    raise
                sl_data = sl_resp.json() or {}
                # Единообразный парсинг форматов stop_lists через общий модуль
                names, product_ids = extract_stoplist_names_and_ids(sl_data)

                # Диагностика: собрали ли productId и имена из стоп-листа
                try:
                    if product_ids:
                        logger.info(
                            "fetch_stoplist_names: collected %d productIds from stop_lists (sample: %s)",
                            len(product_ids),
                            ", ".join(product_ids[:5])
                        )
                    if names:
                        logger.info(
                            "fetch_stoplist_names: collected %d names from stop_lists (sample: %s)",
                            len(names),
                            ", ".join(names[:5])
                        )
                except Exception:
                    pass

                # Если имена отсутствуют, но есть productId — разрешим имена через номенклатуру
                unique_names = {n for n in names if isinstance(n, str) and n.strip()}
                if not unique_names and product_ids:
                    # Попробуем использовать кэш номенклатуры
                    now2 = _now()
                    id_to_name: Dict[str, str] = {}
                    cached_map = _CACHE.get("nomenclature_map")
                    cached_map_ts = _CACHE.get("nomenclature_ts") or 0.0
                    if isinstance(cached_map, dict) and len(cached_map) > 0 and now2 - cached_map_ts < _NOMENCLATURE_TTL:
                        id_to_name = dict(cached_map)
                        logger.info("fetch_stoplist_names: using cached nomenclature map (%d items)", len(id_to_name))
                    elif isinstance(cached_map, dict) and len(cached_map) == 0 and now2 - cached_map_ts < _NOMENCLATURE_TTL:
                        logger.info("fetch_stoplist_names: cached nomenclature map is empty; fetching fresh")
                    else:
                        try:
                            nom = await self._fetch_cloud_nomenclature(client, token)
                        except HTTPStatusError as e:
                            if e.response is not None and e.response.status_code == 429:
                                _CACHE["cooldown_until"] = _now() + _COOLDOWN_SECONDS
                                cached = _CACHE.get("stoplist_names") or []
                                logger.warning("iikoCloud nomenclature: 429 Too Many Requests; activating cooldown for %ds", _COOLDOWN_SECONDS)
                                return list(cached)
                            raise
                        except Exception as e:
                            logger.warning(f"fetch_stoplist_names: nomenclature fetch failed: {e}")
                            nom = {}
                        # Построим словарь productId -> name (в любых вложенных структурах) и положим в кэш
                        id_to_name = extract_nomenclature_id_to_name(nom)
                        if len(id_to_name) > 0:
                            _CACHE["nomenclature_map"] = dict(id_to_name)
                            _CACHE["nomenclature_ts"] = _now()
                            logger.info("fetch_stoplist_names: rebuilt nomenclature map (%d items)", len(id_to_name))
                        else:
                            logger.warning("fetch_stoplist_names: nomenclature map is empty after fetch; will not cache empty map")

                    for pid in product_ids:
                        nm = id_to_name.get(pid)
                        if nm:
                            unique_names.add(nm)
                    # Диагностика соответствий ID→name
                    try:
                        mapped_samples = []
                        for pid in product_ids[:5]:
                            nm = id_to_name.get(pid)
                            if nm:
                                mapped_samples.append(f"{pid}->{nm}")
                        if mapped_samples:
                            logger.info(
                                "fetch_stoplist_names: resolved %d names via nomenclature fallback (sample: %s)",
                                len(unique_names),
                                ", ".join(mapped_samples)
                            )
                    except Exception:
                        pass

                final_names = sorted(list(unique_names))
                logger.info(f"fetch_stoplist_names: collected {len(final_names)} items in stop-list")
                # Кэшируем финальный список стоп-листа (только если непустой)
                if len(final_names) > 0:
                    _CACHE["stoplist_names"] = list(final_names)
                    _CACHE["stoplist_ts"] = _now()
                    # Persist to disk to share across processes and survive cooldowns
                    try:
                        _write_stoplist_cache_to_disk(final_names, product_ids)
                    except Exception:
                        _write_stoplist_cache_to_disk(final_names)
                return final_names
        except Exception as e:
            logger.warning(f"fetch_stoplist_names failed: {e}")
            return []

    async def fetch_stoplist_ids(self, from_webhook: bool = False) -> List[str]:
        """
        Получить список product_id блюд из стоп-листа через iikoCloud.
        Возвращает список строковых product_id. Если режим не cloud или что-то пошло не так — возвращает пустой список.
        Логика кеширования и cooldown аналогична fetch_stoplist_names, но без обращения к /nomenclature.
        """
        try:
            try:
                logger.info("fetch_stoplist_ids: mode=%s, from_webhook=%s", self.mode, from_webhook)
            except Exception:
                pass
            if not self.base_url or not self.api_key or not self.organization_id:
                logger.warning("fetch_stoplist_ids: iikoCloud is not fully configured")
                return []

            # Периодический опрос по интервалу
            force_cloud_due_to_interval = False
            try:
                interval_min = int(settings.IIKO_STOPLIST_REFRESH_INTERVAL_MINUTES or 0)
            except Exception:
                interval_min = 0
            if interval_min > 0:
                now_check = _now()
                last_ts = float(_CACHE.get("stoplist_ts") or 0.0)
                if last_ts <= 0.0:
                    # Попробуем прочитать возраст из дискового кэша
                    try:
                        p = _STOPLIST_CACHE_FILE
                        if p.exists():
                            raw = p.read_text(encoding="utf-8")
                            data = json.loads(raw)
                            last_ts = float(data.get("ts") or 0.0)
                    except Exception:
                        last_ts = 0.0
                age_sec = (now_check - last_ts) if last_ts > 0.0 else (interval_min * 60 + 1)
                if age_sec >= interval_min * 60:
                    force_cloud_due_to_interval = True
                    try:
                        logger.info(
                            "fetch_stoplist_ids(server-mode): refresh interval %d min expired (age=%ds), will call iikoCloud",
                            interval_min,
                            int(age_sec),
                        )
                    except Exception:
                        pass
            if self.mode != "cloud" and not (from_webhook or force_cloud_due_to_interval):
                # Не клауд-режим и вызов не из вебхука — возвращаем кэш, не дергаем клауд
                now_nc = _now()
                cached_ids = _CACHE.get("stoplist_ids")
                cached_ts = _CACHE.get("stoplist_ts") or 0.0
                if isinstance(cached_ids, list) and now_nc - cached_ts < _STOPLIST_TTL:
                    if len(cached_ids) > 0:
                        logger.info("fetch_stoplist_ids(server-mode): using cached stoplist ids (%d items)", len(cached_ids))
                        return list(cached_ids)
                # Fallback на диск
                def _read_stoplist_ids_from_disk_local() -> Optional[List[str]]:
                    try:
                        p = _STOPLIST_CACHE_FILE
                        if not p.exists():
                            return None
                        raw = p.read_text(encoding="utf-8")
                        data = json.loads(raw)
                        ids = data.get("ids") or []
                        if not isinstance(ids, list):
                            return None
                        ids_out = [str(n).strip() for n in ids if isinstance(n, (str, int)) and str(n).strip()]
                        logger.info("fetch_stoplist_ids(server-mode): using disk stoplist ids cache (%d items)", len(ids_out))
                        return ids_out
                    except Exception:
                        return None
                disk_cached_nc = _read_stoplist_ids_from_disk_local()
                if disk_cached_nc:
                    return disk_cached_nc
                logger.info("fetch_stoplist_ids(server-mode): no cache available, returning empty list")
                return []
            if self.mode != "cloud" and from_webhook:
                logger.info("fetch_stoplist_ids: attempting iikoCloud stop-list in server mode due to webhook signal")

            now = _now()

            def _read_stoplist_ids_from_disk(allow_stale: bool = False) -> Optional[List[str]]:
                try:
                    p = _STOPLIST_CACHE_FILE
                    if not p.exists():
                        return None
                    raw = p.read_text(encoding="utf-8")
                    data = json.loads(raw)
                    ts = float(data.get("ts") or 0.0)
                    ids = data.get("ids") or []
                    if not isinstance(ids, list):
                        return None
                    age = int(now - ts)
                    ids_out = [str(n).strip() for n in ids if isinstance(n, (str, int)) and str(n).strip()]
                    if age > _STOPLIST_DISK_TTL:
                        if allow_stale and len(ids_out) > 0:
                            logger.warning(
                                "fetch_stoplist_ids: disk cache expired (%ds old), using STALE cache due to cooldown (%d items)",
                                age,
                                len(ids_out),
                            )
                            return ids_out
                        logger.info("fetch_stoplist_ids: disk cache expired (%ds old)", age)
                        return None
                    logger.info("fetch_stoplist_ids: using disk stoplist ids cache (%d items)", len(ids_out))
                    return ids_out
                except Exception as e:
                    logger.warning(f"fetch_stoplist_ids: read stoplist disk cache failed: {e}")
                    return None

            def _write_stoplist_cache_to_disk(ids: List[str], names: Optional[List[str]] = None) -> None:
                try:
                    p = _STOPLIST_CACHE_FILE
                    p.parent.mkdir(parents=True, exist_ok=True)
                    payload = {"ts": now, "ids": list(ids)}
                    if isinstance(names, list):
                        payload["names"] = list(names)
                    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                    logger.info("fetch_stoplist_ids: updated disk stoplist ids cache (%d items)", len(ids))
                except Exception as e:
                    logger.warning(f"fetch_stoplist_ids: write stoplist disk cache failed: {e}")

            # Cooldown handling
            cooldown_until = _CACHE.get("cooldown_until") or 0.0
            cooldown_active = now < cooldown_until
            if cooldown_active:
                cached = _CACHE.get("stoplist_ids") or []
                if isinstance(cached, list) and len(cached) > 0:
                    logger.warning(
                        "fetch_stoplist_ids: cooldown active (until %.0f), returning cached stoplist ids (%d items)",
                        cooldown_until,
                        len(cached),
                    )
                    return list(cached)
                logger.warning(
                    "fetch_stoplist_ids: cooldown active (until %.0f), no cached stoplist ids available",
                    cooldown_until,
                )
                disk_cached = _read_stoplist_ids_from_disk(allow_stale=True)
                if disk_cached:
                    return disk_cached
                return []

            # Memory cache check
            cached_ids = _CACHE.get("stoplist_ids")
            cached_ts = _CACHE.get("stoplist_ts") or 0.0
            if isinstance(cached_ids, list) and now - cached_ts < _STOPLIST_TTL:
                if len(cached_ids) > 0:
                    logger.info("fetch_stoplist_ids: using cached stoplist ids (%d items)", len(cached_ids))
                    return list(cached_ids)
                else:
                    logger.info("fetch_stoplist_ids: cached stoplist ids is empty; trying disk/fresh fetch")
            disk_cached = _read_stoplist_ids_from_disk()
            if disk_cached:
                return disk_cached

            async with httpx.AsyncClient(timeout=30) as client:
                token = await self._get_cloud_access_token(client)
                headers = {"Authorization": f"Bearer {token}"}

                # Terminal groups
                group_ids: List[str] = []
                cached_tg_ids = _CACHE.get("terminal_group_ids")
                cached_tg_ts = _CACHE.get("terminal_group_ids_ts") or 0.0
                if isinstance(cached_tg_ids, list) and now - cached_tg_ts < _TERMINAL_GROUPS_TTL:
                    group_ids = list(cached_tg_ids)
                    logger.info("fetch_stoplist_ids: using cached terminal group ids (%d)", len(group_ids))
                else:
                    tg_url = f"{self.base_url}/api/1/terminal_groups"
                    tg_payload = {"organizationIds": [self.organization_id]}
                    try:
                        logger.info("[iikoCloud] POST %s payload: organizationIds=%s", tg_url, tg_payload.get("organizationIds"))
                    except Exception:
                        pass
                    try:
                        tg_resp = await client.post(tg_url, headers=headers, json=tg_payload)
                        tg_resp.raise_for_status()
                    except HTTPStatusError as e:
                        if e.response is not None and e.response.status_code == 429:
                            _CACHE["cooldown_until"] = _now() + _COOLDOWN_SECONDS
                            cached = _CACHE.get("stoplist_ids") or []
                            logger.warning("iikoCloud terminal_groups: 429 Too Many Requests; activating cooldown for %ds", _COOLDOWN_SECONDS)
                            return list(cached)
                        raise
                    tg_data = tg_resp.json() or {}
                    try:
                        tgs = tg_data.get("terminalGroups") or tg_data.get("items") or tg_data
                        if isinstance(tgs, list):
                            for g in tgs:
                                inner_items = g.get("items")
                                if isinstance(inner_items, list):
                                    for gi in inner_items:
                                        gid = gi.get("id") or gi.get("groupId") or gi.get("terminalGroupId")
                                        if gid:
                                            group_ids.append(str(gid))
                                else:
                                    gid = g.get("id") or g.get("groupId") or g.get("terminalGroupId")
                                    if gid:
                                        group_ids.append(str(gid))
                        elif isinstance(tgs, dict):
                            items = tgs.get("items")
                            if isinstance(items, list):
                                for g in items:
                                    gid = g.get("id") or g.get("groupId") or g.get("terminalGroupId")
                                    if gid:
                                        group_ids.append(str(gid))
                    except Exception:
                        pass
                    if not group_ids:
                        logger.warning("fetch_stoplist_ids: no terminal group ids found")
                        return []
                    _CACHE["terminal_group_ids"] = list(group_ids)
                    _CACHE["terminal_group_ids_ts"] = _now()

                # Stop-lists
                sl_url = f"{self.base_url}/api/1/stop_lists"
                sl_payload = {"organizationIds": [self.organization_id], "terminalGroupIds": group_ids}
                try:
                    logger.info("[iikoCloud] POST %s payload: organizationIds=%s, terminalGroupIds=%s", sl_url, sl_payload.get("organizationIds"), sl_payload.get("terminalGroupIds"))
                except Exception:
                    pass
                try:
                    sl_resp = await client.post(sl_url, headers=headers, json=sl_payload)
                    sl_resp.raise_for_status()
                except HTTPStatusError as e:
                    if e.response is not None and e.response.status_code == 429:
                        _CACHE["cooldown_until"] = _now() + _COOLDOWN_SECONDS
                        cached = _CACHE.get("stoplist_ids") or []
                        logger.warning("iikoCloud stop_lists: 429 Too Many Requests; activating cooldown for %ds", _COOLDOWN_SECONDS)
                        if isinstance(cached, list) and len(cached) > 0:
                            return list(cached)
                        disk_cached = _read_stoplist_ids_from_disk(allow_stale=True)
                        if disk_cached:
                            return disk_cached
                        return []
                    raise
                sl_data = sl_resp.json() or {}
                names, product_ids = extract_stoplist_names_and_ids(sl_data)
                unique_ids = {str(pid).strip() for pid in product_ids if pid is not None and str(pid).strip()}
                final_ids = sorted(list(unique_ids))
                logger.info(f"fetch_stoplist_ids: collected {len(final_ids)} productIds in stop-list")
                if len(final_ids) > 0:
                    _CACHE["stoplist_ids"] = list(final_ids)
                    _CACHE["stoplist_ts"] = _now()
                    _write_stoplist_cache_to_disk(final_ids, names)
                return final_ids
        except Exception as e:
            logger.warning(f"fetch_stoplist_ids failed: {e}")
            return []

    async def test_connection(self) -> Dict[str, Any]:
        """Lightweight connectivity test without leaking sensitive data.
        - For cloud mode: obtains an access token.
        - For server mode: performs auth only.
        Returns dict: { ok: bool, mode: str, message?: str }
        """
        async with httpx.AsyncClient() as client:
            try:
                if self.mode == "cloud":
                    _ = await self._get_cloud_access_token(client)
                    return {"ok": True, "mode": "cloud"}
                elif self.mode == "server":
                    base = self._normalize_server_base()
                    if not base or not self.server_login or not self.server_password:
                        return {"ok": False, "mode": "server", "message": "Missing or invalid server host/login/password"}
                    try:
                        logger.info("Testing iikoServer connection: auth at startup manager")
                        mgr = get_iiko_server_auth_manager()
                        mgr.configure(base, self.server_login, self.server_password)
                        await mgr.ensure_authenticated()
                        return {"ok": True, "mode": "server"}
                    except RuntimeError as e:
                        logger.error(f"iikoServer auth test failed: {e}")
                        return {"ok": False, "mode": "server", "message": str(e)}
                    except Exception:
                        logger.error("iikoServer auth test failed: generic connectivity error")
                        return {"ok": False, "mode": "server", "message": "Unable to reach iikoServer"}
                else:
                    return {"ok": False, "mode": self.mode, "message": "Unsupported IIKO_MODE"}
            except Exception as e:
                # Sanitize any unexpected errors
                return {"ok": False, "mode": self.mode, "message": str(e)}

    async def _server_auth(self, client: httpx.AsyncClient, base: str) -> None:
        """Attempt iikoServer auth using GET first, then POST as fallback.
        Raises RuntimeError with sanitized messages on failure.
        """
        auth_url = f"{base}/resto/api/auth"
        alt_auth_url = f"{base}/api/auth"  # rare installations
        login_url = f"{base}/resto/api/login"  # some installations use /login
        basic_auth = httpx.BasicAuth(self.server_login, self.server_password)
        # Try GET
        try:
            logger.info("Attempting iikoServer auth (GET /resto/api/auth)")
            resp = await client.get(auth_url, params={"login": self.server_login, "pass": self.server_password}, timeout=30)
            logger.info(f"iikoServer auth GET status: {resp.status_code}")
            if resp.status_code == 200:
                txt = resp.text or ""
                low = txt.strip().lower()
                if "invalid password" in low or "invalid login" in low:
                    raise RuntimeError("Authentication failed: invalid login or password")
                # Success: cookies/session should be stored in client
                return
            elif resp.status_code in (401, 403):
                # Some iikoServer installs require HTTP Basic Auth; try it if indicated
                wa = resp.headers.get("www-authenticate", "").lower()
                if "basic" in wa:
                    try:
                        logger.info("iikoServer indicates Basic auth; attempting GET with BasicAuth")
                        resp2 = await client.get(auth_url, auth=basic_auth, timeout=30)
                        logger.info(f"iikoServer auth GET (Basic) status: {resp2.status_code}")
                        if resp2.status_code == 200:
                            return
                    except Exception:
                        logger.error("iikoServer auth GET (Basic) failed, continuing")
                # try alternative login path quickly
                try:
                    logger.info("Attempting iikoServer auth via /resto/api/login")
                    resp3 = await client.post(login_url, data={"login": self.server_login, "pass": self.server_password}, timeout=30)
                    logger.info(f"iikoServer /login POST status: {resp3.status_code}")
                    if resp3.status_code == 200:
                        return
                except Exception:
                    logger.error("iikoServer /login POST attempt failed")
                raise RuntimeError("Authentication failed (401/403)")
            elif resp.status_code == 500:
                raise RuntimeError("Upstream server error (500)")
            # Fallback to POST for other statuses
        except httpx.ConnectTimeout:
            # Continue to POST fallback
            logger.error("iikoServer auth GET timeout")
            pass
        except httpx.ReadTimeout:
            # Continue to POST fallback
            logger.error("iikoServer auth GET read timeout")
            pass
        except httpx.ConnectError:
            # Continue to POST fallback
            logger.error("iikoServer auth GET network error")
            pass
        except HTTPStatusError as e:
            code = e.response.status_code if e.response is not None else None
            if code in (401, 403):
                raise RuntimeError("Authentication failed (401/403)")
            elif code == 500:
                raise RuntimeError("Upstream server error (500)")
            # Continue to POST fallback
        except Exception:
            # Continue to POST fallback on other errors
            logger.error("iikoServer auth GET unknown error, trying POST fallback")
            pass

        # Try POST fallback
        try:
            # Some installations expect form-encoded body, not query string
            logger.info("Attempting iikoServer auth (POST /resto/api/auth)")
            resp = await client.post(
                auth_url,
                data={"login": self.server_login, "pass": self.server_password},
                timeout=30,
            )
            logger.info(f"iikoServer auth POST status: {resp.status_code}")
            if resp.status_code == 200:
                txt = resp.text or ""
                low = txt.strip().lower()
                if "invalid password" in low or "invalid login" in low:
                    raise RuntimeError("Authentication failed: invalid login or password")
                return
            elif resp.status_code in (401, 403):
                # Try Basic auth with POST
                try:
                    logger.info("Attempting iikoServer auth POST with BasicAuth")
                    resp2 = await client.post(auth_url, auth=basic_auth, timeout=30)
                    logger.info(f"iikoServer auth POST (Basic) status: {resp2.status_code}")
                    if resp2.status_code == 200:
                        return
                except Exception:
                    logger.error("iikoServer auth POST (Basic) failed")
                # Try alternative form field name 'password'
                try:
                    logger.info("Attempting iikoServer auth POST using 'password' field name")
                    resp_pw = await client.post(
                        auth_url,
                        data={"login": self.server_login, "password": self.server_password},
                        timeout=30,
                    )
                    logger.info(f"iikoServer auth POST (password field) status: {resp_pw.status_code}")
                    if resp_pw.status_code == 200:
                        return
                except Exception:
                    logger.error("iikoServer auth POST (password field) attempt failed")
                # Try /login path as well
                try:
                    logger.info("Attempting iikoServer auth via /resto/api/login (POST)")
                    resp3 = await client.post(login_url, data={"login": self.server_login, "pass": self.server_password}, timeout=30)
                    logger.info(f"iikoServer /login POST status: {resp3.status_code}")
                    if resp3.status_code == 200:
                        return
                except Exception:
                    logger.error("iikoServer /login POST attempt failed")
                raise RuntimeError("Authentication failed (401/403)")
            elif resp.status_code == 500:
                raise RuntimeError("Upstream server error (500)")
            else:
                raise RuntimeError(f"iikoServer auth HTTP error: {resp.status_code}")
        except HTTPStatusError as e:
            code = e.response.status_code if e.response is not None else None
            if code in (401, 403):
                raise RuntimeError("Authentication failed (401/403)")
            elif code == 500:
                raise RuntimeError("Upstream server error (500)")
            else:
                raise RuntimeError(f"iikoServer auth HTTP error: {code}")
        except httpx.ConnectTimeout:
            raise RuntimeError("Connection timeout to iikoServer auth endpoint")
        except httpx.ReadTimeout:
            raise RuntimeError("Read timeout from iikoServer auth endpoint")
        except httpx.ConnectError:
            raise RuntimeError("Network error: failed to connect to iikoServer auth endpoint")
        except Exception:
            # Try alternative path as a last resort
            try:
                logger.info("Attempting alternative iikoServer auth (GET /api/auth)")
                resp = await client.get(alt_auth_url, params={"login": self.server_login, "pass": self.server_password}, timeout=30)
                logger.info(f"iikoServer alt auth GET status: {resp.status_code}")
                if resp.status_code == 200:
                    txt = resp.text or ""
                    low = txt.strip().lower()
                    if "invalid password" in low or "invalid login" in low:
                        raise RuntimeError("Authentication failed: invalid login or password")
                    return
                # Try Basic auth on alternative path
                if resp.status_code in (401, 403):
                    try:
                        logger.info("Attempting alternative iikoServer auth (Basic GET /api/auth)")
                        resp2 = await client.get(alt_auth_url, auth=basic_auth, timeout=30)
                        logger.info(f"iikoServer alt auth GET (Basic) status: {resp2.status_code}")
                        if resp2.status_code == 200:
                            return
                    except Exception:
                        logger.error("Alternative iikoServer auth GET (Basic) failed")
            except Exception:
                pass
            raise RuntimeError("Unable to reach iikoServer auth endpoint. Check server host and connectivity.")

    async def upsert_into_db(self, db: AsyncSession, products: List[Dict[str, Any]]) -> Tuple[int, int]:
        """
        Upsert dishes and append price records.
        Returns (created_dishes, appended_prices).
        """
        created_dishes = 0
        appended_prices = 0

        for prod in products:
            prod_id = (prod.get("id") or "").strip() if isinstance(prod.get("id"), str) else None
            name = (prod.get("name") or "").strip()
            if not name:
                continue
            price_value = prod.get("price")
            try:
                price_value = float(price_value) if price_value is not None else None
            except Exception:
                price_value = None

            # Check existing dish: сначала по product_id, затем по name (fallback)
            dish = None
            if prod_id:
                dish_res = await db.execute(select(Dish).where(Dish.product_id == prod_id))
                dish = dish_res.scalars().first()
            if not dish:
                dish_res = await db.execute(select(Dish).where(Dish.name == name))
                dish = dish_res.scalars().first()
            if not dish:
                dish = Dish(name=name, product_id=prod_id)
                db.add(dish)
                await db.flush()  # get dish.id without commit
                created_dishes += 1
            else:
                # Если нашли по имени и product_id ещё не установлен — запишем его
                try:
                    if (not getattr(dish, "product_id", None)) and prod_id:
                        dish.product_id = prod_id
                        db.add(dish)
                except Exception:
                    pass

            # Append price if available
            if price_value is not None:
                db.add(Price(dish_id=dish.id, value=price_value))
                appended_prices += 1

        await db.commit()
        return created_dishes, appended_prices
