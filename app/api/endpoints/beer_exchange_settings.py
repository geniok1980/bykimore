from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin, get_current_user
from app.db.session import get_db
from app.models.dish import Dish
from app.models.dish_settings import DishSettings
from app.schemas.dish_settings import (
    DishSettingsCreate,
    DishSettingsRead,
    DishSettingsUpdate,
)
from app.services.iiko_service import IikoService
from app.services.iiko_auth import get_iiko_server_auth_manager
from app.utils.logger import setup_logger
logger = setup_logger(__name__)

router = APIRouter()


@router.get("/", response_model=list[DishSettingsRead])
async def list_settings(
    current_user: Annotated[object, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[DishSettingsRead]:
    res = await db.execute(select(DishSettings))
    return res.scalars().all()


@router.get("/by-dish/{dish_id}", response_model=Optional[DishSettingsRead])
async def get_settings_by_dish(
    dish_id: int,
    current_user: Annotated[object, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Optional[DishSettingsRead]:
    res = await db.execute(select(DishSettings).where(DishSettings.dish_id == dish_id))
    return res.scalars().first()


@router.post("/", status_code=status.HTTP_201_CREATED, response_model=DishSettingsRead)
async def upsert_settings(
    settings_in: DishSettingsCreate,
    current_admin: Annotated[object, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DishSettingsRead:
    # Ensure dish exists
    dish_res = await db.execute(select(Dish).where(Dish.id == settings_in.dish_id))
    dish = dish_res.scalars().first()
    if not dish:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Блюдо не найдено")

    existing_res = await db.execute(select(DishSettings).where(DishSettings.dish_id == settings_in.dish_id))
    existing = existing_res.scalars().first()

    if existing:
        # Update existing (запрещаем редактирование base_price: сохраняем исходную)
        existing.min_price = settings_in.min_price
        existing.max_price = settings_in.max_price
        existing.step = settings_in.step
        # Базовая цена устанавливается только один раз при создании. Если она отсутствует, можно задать.
        if existing.base_price is None and settings_in.base_price is not None:
            existing.base_price = settings_in.base_price
        existing.sales_quantity = settings_in.sales_quantity
        existing.weight_grams = settings_in.weight_grams
        existing.ttl_minutes = settings_in.ttl_minutes
        existing.active = settings_in.active
        db.add(existing)
        await db.commit()
        await db.refresh(existing)
        # After saving settings, if iikoServer mode is active, perform logout to free license slot
        try:
            svc = IikoService()
            if (svc.mode or "").lower() == "server":
                mgr = get_iiko_server_auth_manager()
                await mgr.logout()
        except Exception:
            # Non-fatal: ignore logout failures
            pass
        return existing
    else:
        # При создании допускаем установку base_price (загружается из iiko)
        obj = DishSettings(
            dish_id=settings_in.dish_id,
            min_price=settings_in.min_price,
            max_price=settings_in.max_price,
            step=settings_in.step,
            base_price=settings_in.base_price,
            sales_quantity=settings_in.sales_quantity,
            weight_grams=settings_in.weight_grams,
            ttl_minutes=settings_in.ttl_minutes,
            active=settings_in.active,
        )
        db.add(obj)
        await db.commit()
        await db.refresh(obj)
        # After creating settings, if iikoServer mode is active, perform logout to free license slot
        try:
            svc = IikoService()
            if (svc.mode or "").lower() == "server":
                mgr = get_iiko_server_auth_manager()
                await mgr.logout()
        except Exception:
            # Non-fatal: ignore logout failures
            pass
        return obj


@router.patch("/{settings_id}", response_model=DishSettingsRead)
async def patch_settings(
    settings_id: int,
    patch: DishSettingsUpdate,
    current_admin: Annotated[object, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DishSettingsRead:
    res = await db.execute(select(DishSettings).where(DishSettings.id == settings_id))
    obj = res.scalars().first()
    if not obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Настройки не найдены")

    if patch.min_price is not None:
        obj.min_price = patch.min_price
    if patch.max_price is not None:
        obj.max_price = patch.max_price
    if patch.step is not None:
        obj.step = patch.step
    # Базовую цену нельзя редактировать через PATCH — игнорируем patch.base_price
    if patch.sales_quantity is not None:
        obj.sales_quantity = patch.sales_quantity
    if patch.weight_grams is not None:
        obj.weight_grams = patch.weight_grams
    if patch.ttl_minutes is not None:
        obj.ttl_minutes = patch.ttl_minutes
    if patch.active is not None:
        obj.active = patch.active

    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj



