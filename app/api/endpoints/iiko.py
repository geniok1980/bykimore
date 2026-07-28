from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin
from app.db.session import get_db
from app.services.iiko_service import IikoService
from app.services.iiko_auth import get_iiko_server_auth_manager
from pydantic import BaseModel
from sqlalchemy import select
from app.models.iiko_settings import IikoSettings
from app.models.dish import Dish
from app.models.price import Price
from app.utils.logger import setup_logger

router = APIRouter()
logger = setup_logger(__name__)


class IikoProduct(BaseModel):
    id: str | None = None
    name: str
    price: float | None = None
    code: str | None = None


@router.post("/sync")
async def sync_iiko_menu(
    current_admin: Annotated[object, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Synchronize dishes and prices from iiko into local DB.
    Requires admin auth.
    """
    try:
        svc = IikoService()
        products = await svc.fetch_products()
        created_dishes, appended_prices = await svc.upsert_into_db(db, products)
        return {
            "status": "ok",
            "mode": svc.mode,
            "created_dishes": created_dishes,
            "appended_prices": appended_prices,
            "total_products": len(products),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Sync failed: {e}")


@router.get("/products", response_model=list[IikoProduct])
async def list_iiko_products(
    current_admin: Annotated[object, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """List products from iiko using configured settings. Admin-only.
    If iiko server settings exist in DB, use server mode with those credentials.
    """
    try:
        logger.info("GET /iiko/products invoked")
        svc = IikoService()
        # Try to load DB-stored server settings
        result = await db.execute(select(IikoSettings).order_by(IikoSettings.id.asc()))
        stored = result.scalars().first()
        if stored and stored.active and stored.server_host and stored.server_login and stored.server_password:
            logger.info("Using iikoServer settings from DB for products fetch")
            svc.mode = "server"
            svc.server_host = stored.server_host
            svc.server_login = stored.server_login
            svc.server_password = stored.server_password
        else:
            logger.info(f"Using iiko mode from environment: {svc.mode}")
        products = await svc.fetch_products()
        logger.info(f"Fetched {len(products)} products from iiko ({svc.mode})")
        # Normalize fields first
        normalized: list[IikoProduct] = []
        for p in products:
            if isinstance(p, dict):
                normalized.append(IikoProduct(id=p.get("id"), name=p.get("name") or "", price=p.get("price"), code=p.get("code")))
            else:
                logger.warning("Skipping non-dict product element: %s", type(p).__name__)

        # Fallback: if price is missing or zero, try to use latest local price for matching dish name
        try:
            # Build latest price map per dish id, and keep dishes list for fuzzy matching
            dishes_result = await db.execute(select(Dish))
            all_dishes = dishes_result.scalars().all()

            prices_result = await db.execute(select(Price))
            all_prices = prices_result.scalars().all()

            # latest price by dish id
            latest_by_id: dict[int, tuple[float, float]] = {}
            for pr in all_prices:
                ts = float(pr.created_at.timestamp()) if pr.created_at else 0.0
                prev = latest_by_id.get(pr.dish_id)
                if not prev or ts > prev[1]:
                    latest_by_id[pr.dish_id] = (float(pr.value), ts)

            def norm(s: str) -> str:
                return " ".join((s or "").lower().split())

            # Apply fallback using fuzzy name match: equal, includes, or startswith
            for item in normalized:
                val = item.price
                if isinstance(val, (int, float)) and float(val) > 0.0:
                    continue
                name_norm = norm(item.name)
                best_price: Optional[float] = None
                best_len: int = 0
                for d in all_dishes:
                    dn = norm(d.name or "")
                    matched = False
                    if dn == name_norm:
                        matched = True
                    elif dn.startswith(name_norm) or name_norm.startswith(dn):
                        matched = True
                    elif dn.find(name_norm) >= 0 or name_norm.find(dn) >= 0:
                        matched = True
                    if matched:
                        latest = latest_by_id.get(d.id)
                        if latest:
                            # Prefer longer match (to avoid overly generic matches)
                            match_len = max(len(dn), len(name_norm))
                            if best_price is None or match_len > best_len:
                                best_price = float(latest[0])
                                best_len = match_len
                if best_price is not None:
                    item.price = best_price
        except Exception as e:
            logger.warning(f"Failed to apply local price fallback for iiko products: {e}")

        return normalized
    except Exception as e:
        # Sanitize errors
        msg = str(e)
        logger.error(f"Fetch products failed: {msg}")
        raise HTTPException(status_code=400, detail=f"Fetch products failed: {msg}")


@router.post("/logout")
async def iiko_logout_endpoint(
    current_admin: Annotated[object, Depends(get_current_admin)],
):
    """Explicitly logout from iikoServer to free license slot (server mode only).
    Safe to call even if cloud mode is configured or no active session exists.
    """
    try:
        svc = IikoService()
        if (svc.mode or "").lower() != "server":
            return {"status": "skipped", "mode": svc.mode}
        mgr = get_iiko_server_auth_manager()
        ok = await mgr.logout()
        return {"status": "ok" if ok else "failed", "mode": "server"}
    except Exception as e:
        msg = str(e)
        logger.error(f"Logout failed: {msg}")
        raise HTTPException(status_code=400, detail=f"Logout failed: {msg}")


@router.get("/test-connection")
async def test_iiko_connection(
    current_admin: Annotated[object, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Lightweight connectivity test using configured settings. Admin-only.
    - For cloud mode: verifies access token retrieval
    - For server mode: verifies auth endpoint
    """
    logger.info("GET /iiko/test-connection invoked")
    svc = IikoService()
    # Load DB settings if present and active
    result = await db.execute(select(IikoSettings).order_by(IikoSettings.id.asc()))
    stored = result.scalars().first()
    if stored and stored.active and stored.server_host and stored.server_login and stored.server_password:
        logger.info("Using iikoServer settings from DB for connection test")
        svc.mode = "server"
        svc.server_host = stored.server_host
        svc.server_login = stored.server_login
        svc.server_password = stored.server_password
    else:
        logger.info(f"Using iiko mode from environment: {svc.mode}")
    outcome = await svc.test_connection()
    if outcome.get("ok"):
        logger.info(f"iiko connection OK (mode={outcome.get('mode')})")
        return {"status": "ok", "mode": outcome.get("mode")}
    else:
        # Return sanitized message
        msg = outcome.get("message") or "Connection failed"
        logger.error(f"iiko connection failed: {msg}")
        raise HTTPException(status_code=400, detail=msg)
