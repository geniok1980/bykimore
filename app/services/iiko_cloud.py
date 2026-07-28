from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple

import httpx

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


# =============================
# Shared iikoCloud helpers
# =============================

DEFAULT_CLOUD_BASE = "https://api-ru.iiko.services"


async def get_access_token(api_key: str, base_url: str | None = None, verify_ssl: bool = True) -> str | None:
    """Obtain iikoCloud access token using API key.

    Attempts both payload shapes (apiLogin, apiKey) for compatibility.
    Returns token string or None on failure.
    """
    base = (base_url or DEFAULT_CLOUD_BASE).rstrip("/")
    url = f"{base}/api/1/access_token"
    try:
        async with httpx.AsyncClient(verify=verify_ssl, timeout=10.0) as client:
            try:
                logger.info("[iikoCloud] POST %s (apiLogin)", url)
            except Exception:
                pass
            resp = await client.post(url, json={"apiLogin": api_key})
            if resp.status_code == 200:
                data = resp.json() or {}
                token = data.get("token") or data.get("access_token")
                if isinstance(token, str) and token:
                    logger.info("✅ [iikoCloud] access_token received: %s…", token[:6])
                    return token

            # Fallback payload name used by some installations
            try:
                logger.info("[iikoCloud] POST %s (apiKey)", url)
            except Exception:
                pass
            resp2 = await client.post(url, json={"apiKey": api_key})
            if resp2.status_code == 200:
                data = resp2.json() or {}
                token = data.get("token") or data.get("access_token")
                if isinstance(token, str) and token:
                    logger.info("✅ [iikoCloud] access_token received: %s…", token[:6])
                    return token
    except Exception as e:
        logger.warning(f"get_access_token failed: {e}")
    return None


async def get_terminal_groups(token: str, organization_id: str, base_url: str | None = None, verify_ssl: bool = True) -> List[str]:
    """Fetch terminal group IDs for an organization.

    Tries to handle several common response shapes.
    """
    base = (base_url or DEFAULT_CLOUD_BASE).rstrip("/")
    url = f"{base}/api/1/terminal_groups"
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"organizationIds": [organization_id], "includeDisabled": True}
    try:
        async with httpx.AsyncClient(verify=verify_ssl, timeout=10.0) as client:
            logger.info("[iikoCloud] POST %s", url)
            resp = await client.post(url, headers=headers, json=payload)
            body: Dict[str, Any] | None = None
            try:
                body = resp.json()
            except Exception:
                body = None
            logger.info("⬅️ [iikoCloud] terminal_groups status=%s", resp.status_code)

            if resp.status_code != 200:
                if body is not None:
                    logger.info("terminal_groups body: %s", json.dumps(body, ensure_ascii=False)[:500])
                else:
                    logger.info("terminal_groups body (TEXT): %s", (resp.text or "")[:500])
                return []

            data = body or {}
            ids: List[str] = []
            # Possible top-level keys
            root = data.get("terminalGroups") or data.get("groups") or data.get("items") or []
            if isinstance(root, list):
                for entry in root:
                    sub = None
                    try:
                        sub = entry.get("terminalGroups") or entry.get("items") or entry.get("groups")
                    except Exception:
                        sub = None
                    if isinstance(sub, list):
                        for g in sub:
                            tg = None
                            try:
                                tg = (
                                    g.get("id")
                                    or g.get("terminalGroupId")
                                    or (g.get("terminalGroup") or {}).get("id")
                                )
                            except Exception:
                                tg = None
                            if tg:
                                ids.append(str(tg))
                    else:
                        try:
                            tg = entry.get("id") or entry.get("terminalGroupId")
                        except Exception:
                            tg = None
                        if tg:
                            ids.append(str(tg))
            elif isinstance(root, dict):
                items = root.get("items")
                if isinstance(items, list):
                    for g in items:
                        tg = g.get("id") or g.get("terminalGroupId")
                        if tg:
                            ids.append(str(tg))
            return ids
    except Exception as e:
        logger.warning(f"get_terminal_groups failed: {e}")
    return []


async def get_stop_lists(token: str, organization_id: str, terminal_group_ids: List[str], base_url: str | None = None, verify_ssl: bool = True) -> Dict[str, Any]:
    """Call stop_lists endpoint and return raw JSON (or empty dict on failure)."""
    base = (base_url or DEFAULT_CLOUD_BASE).rstrip("/")
    url = f"{base}/api/1/stop_lists"
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"organizationIds": [organization_id], "terminalGroupIds": terminal_group_ids}
    try:
        async with httpx.AsyncClient(verify=verify_ssl, timeout=15.0) as client:
            logger.info("[iikoCloud] POST %s", url)
            resp = await client.post(url, headers=headers, json=payload)
            logger.info("⬅️ [iikoCloud] stop_lists status=%s", resp.status_code)
            if resp.status_code == 200:
                try:
                    return resp.json() or {}
                except Exception:
                    return {}
            else:
                # Log truncated body for diagnostics
                try:
                    body = resp.json()
                    logger.info("stop_lists body: %s", json.dumps(body, ensure_ascii=False)[:500])
                except Exception:
                    logger.info("stop_lists body (TEXT): %s", (resp.text or "")[:500])
    except Exception as e:
        logger.warning(f"get_stop_lists failed: {e}")
    return {}


def extract_stoplist_names_and_ids(raw: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    """Parse iikoCloud stop_lists raw JSON into (names, product_ids).

    Handles multiple known payload shapes to reduce discrepancies across processes.
    """
    names: List[str] = []
    product_ids: List[str] = []
    # Common shapes
    try:
        items = raw.get("items") or raw.get("stopLists") or []
        for it in items:
            prod = it.get("product") or {}
            name = prod.get("name") or it.get("name") or it.get("productName")
            pid = prod.get("id") or it.get("productId") or it.get("id")
            if isinstance(name, str) and name.strip():
                names.append(name.strip())
            if isinstance(pid, str) and pid.strip():
                product_ids.append(pid.strip())
    except Exception:
        pass

    # Alternative nested shapes per terminal groups
    try:
        tg_lists = raw.get("terminalGroupStopLists") or raw.get("groups") or []
        for entry in tg_lists:
            lst = entry.get("items") or entry.get("products") or []
            for it in lst:
                if isinstance(it, dict) and isinstance(it.get("items"), list):
                    for dit in it.get("items"):
                        prod = dit.get("product") or {}
                        name = prod.get("name") or dit.get("name") or dit.get("productName")
                        pid = prod.get("id") or dit.get("productId") or dit.get("id")
                        if isinstance(name, str) and name.strip():
                            names.append(name.strip())
                        if isinstance(pid, str) and pid.strip():
                            product_ids.append(pid.strip())
                else:
                    prod = it.get("product") or {}
                    name = prod.get("name") or it.get("name") or it.get("productName")
                    pid = prod.get("id") or it.get("productId") or it.get("id")
                    if isinstance(name, str) and name.strip():
                        names.append(name.strip())
                    if isinstance(pid, str) and pid.strip():
                        product_ids.append(pid.strip())
    except Exception:
        pass

    return names, product_ids


def extract_nomenclature_id_to_name(raw: Dict[str, Any]) -> Dict[str, str]:
    """Walk nomenclature JSON and build {productId -> name} mapping."""
    by_id: Dict[str, str] = {}

    def _walk(obj: Any) -> None:
        try:
            if isinstance(obj, dict):
                pid = obj.get("id") or obj.get("productId")
                nm = obj.get("name") or obj.get("productName")
                if isinstance(pid, str) and pid.strip() and isinstance(nm, str) and nm.strip():
                    by_id[pid.strip()] = nm.strip()
                for v in obj.values():
                    _walk(v)
            elif isinstance(obj, list):
                for el in obj:
                    _walk(el)
        except Exception:
            pass

    _walk(raw or {})
    return by_id


def extract_stoplist_names_from_webhook(event_payload: Dict[str, Any]) -> List[str]:
    """
    Extract stop-list product names from an iikoCloud WebHook payload (eventType=StopListUpdate).

    iikoCloud's webhook payloads can vary by version. We traverse eventInfo recursively
    and collect any reasonable name keys. This function is resilient to different shapes:
    - eventInfo.stopList.items[].product.name
    - eventInfo.items[].name or productName
    - nested structures containing "product" or "dish" objects with a "name" field

    Returns a sorted list of unique names.
    """
    info = event_payload.get("eventInfo") or event_payload.get("event_info") or event_payload
    names: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            # Product-like nested object
            prod = node.get("product") or node.get("dish") or None
            if isinstance(prod, dict):
                nm = prod.get("name") or prod.get("productName") or prod.get("title")
                if isinstance(nm, str) and nm.strip():
                    names.add(nm.strip())
            # Direct name fields on items
            for key in ("name", "productName", "dishName", "itemName"):
                nm2 = node.get(key)
                if isinstance(nm2, str) and nm2.strip():
                    names.add(nm2.strip())
            # Recurse
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for el in node:
                walk(el)

    walk(info)
    return sorted(list(names))