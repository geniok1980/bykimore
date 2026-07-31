from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin, get_current_user
from app.db.session import get_db
from app.models.dish import Dish
from app.models.price import Price
from app.schemas.price import PriceCreate, PriceRead

router = APIRouter()


@router.get("", response_model=list[PriceRead])
async def list_prices(
    current_user: Annotated[object, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[PriceRead]:
    result = await db.execute(select(Price))
    return result.scalars().all()


@router.post("", status_code=status.HTTP_201_CREATED, response_model=PriceRead)
async def add_price(
    price_in: PriceCreate,
    current_user: Annotated[object, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PriceRead:
    # Проверяем, что блюдо существует
    dish_res = await db.execute(select(Dish).where(Dish.id == price_in.dish_id))
    if not dish_res.scalars().first():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Блюдо не найдено")

    price = Price(dish_id=price_in.dish_id, value=price_in.value)
    db.add(price)
    await db.commit()
    await db.refresh(price)
    return price