from __future__ import annotations

import time
from typing import Annotated, Any, Dict, List

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from app.core.config import settings
from app.utils.logger import setup_logger
from app.services.iiko_cloud import extract_stoplist_names_from_webhook
from pathlib import Path
import json

router = APIRouter()
logger = setup_logger(__name__)


def _write_stoplist_cache_to_disk(names: list[str]) -> None:
    try:
        project_root = Path(__file__).resolve().parents[2]
        p = project_root / "storage" / "stoplist_cache.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        payload = {"ts": time.time(), "names": list(names)}
        p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("[Webhook] updated disk stoplist cache (%d items)", len(names))
    except Exception as e:
        logger.warning(f"[Webhook] write stoplist disk cache failed: {e}")


@router.post("/webhook")
async def iiko_webhook_handler(
    request: Request,
    x_iiko_webhook_secret: Annotated[str | None, Header(alias="X-Iiko-Webhook-Secret")] = None,
):
    """
    Receive iikoCloud webhook events. We only process StopListUpdate to avoid polling.

    Security:
    - If settings.IIKO_WEBHOOK_SECRET is set, we require it in the X-Iiko-Webhook-Secret header
      or as a query param (?token=...). Otherwise, the endpoint is open.
    """
    # Verify secret if configured
    expected = getattr(settings, "IIKO_WEBHOOK_SECRET", None)
    token_q = request.query_params.get("token")
    if expected:
        presented = x_iiko_webhook_secret or token_q
        if not presented or presented != expected:
            logger.warning("[Webhook] unauthorized: secret mismatch")
            raise HTTPException(status_code=401, detail="Unauthorized")

    # Accept single event or list of events
    try:
        body: Any = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    events: List[Dict[str, Any]] = []
    if isinstance(body, list):
        events = [e for e in body if isinstance(e, dict)]
    elif isinstance(body, dict):
        events = [body]
    else:
        raise HTTPException(status_code=400, detail="Invalid JSON structure")

    # Filter allowed organization ids if configured
    allowed_orgs = getattr(settings, "IIKO_WEBHOOK_ALLOWED_ORGS", []) or []
    if allowed_orgs:
        events = [e for e in events if str(e.get("organizationId") or "") in allowed_orgs]

    # Process StopListUpdate events
    collected_names: set[str] = set()
    stoplist_update_seen = False
    for ev in events:
        event_type = str(ev.get("eventType") or ev.get("event_type") or "").strip()
        if event_type != "StopListUpdate":
            continue
        stoplist_update_seen = True
        names = extract_stoplist_names_from_webhook(ev)
        for n in names:
            if isinstance(n, str) and n.strip():
                collected_names.add(n.strip())

    logger.info("[Webhook] StopListUpdate events processed=%d, names collected=%d", int(stoplist_update_seen), len(collected_names))

    # If webhook didn't include item names (some payloads only signal an update), trigger refresh via cloud API helpers
    if stoplist_update_seen and len(collected_names) == 0:
        try:
            from app.services.iiko_service import IikoService
            svc = IikoService()
            # Вызов с from_webhook=True разрешает единичный запрос к клауду в серверном режиме
            # только по сигналу вебхука, чтобы избежать постоянного дерганья клауд-API
            refreshed = await svc.fetch_stoplist_names(from_webhook=True)
            for n in refreshed:
                if isinstance(n, str) and n.strip():
                    collected_names.add(n.strip())
            logger.info("[Webhook] stoplist refreshed from cloud API: %d items", len(refreshed))
        except Exception as e:
            logger.warning(f"[Webhook] failed to refresh stoplist via cloud API: {e}")

    names = sorted(list(collected_names))
    logger.info("[Webhook] StopListUpdate total names=%d", len(names))

    # Update in-memory cache to make it effective immediately
    try:
        from app.services.iiko_service import _CACHE as IIKO_CACHE  # type: ignore
        IIKO_CACHE["stoplist_names"] = list(names)
        IIKO_CACHE["stoplist_ts"] = time.time()
        IIKO_CACHE["cooldown_until"] = 0.0  # clear cooldown on push update
        logger.info("[Webhook] in-memory stoplist cache updated (%d items)", len(names))
    except Exception as e:
        logger.warning(f"[Webhook] failed to update in-memory cache: {e}")

    # Persist to disk so other processes can reuse during cooldowns
    if len(names) > 0:
        _write_stoplist_cache_to_disk(names)

    if not stoplist_update_seen:
        return {"status": "ignored", "reason": "no StopListUpdate events"}
    return {"status": "ok", "events": len(events), "collected": len(names)}