from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin, get_current_user
from app.db.session import get_db
from app.models.dish import Dish
from app.models.rate import Rate
from app.schemas.rate import RateCreate, RateRead

router = APIRouter()


@router.get("/", response_model=list[RateRead])
async def list_rates(
    current_user: Annotated[object, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[RateRead]:
    result = await db.execute(select(Rate))
    return result.scalars().all()


@router.post("/", status_code=status.HTTP_201_CREATED, response_model=RateRead)
async def add_rate(
    rate_in: RateCreate,
    current_user: Annotated[object, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RateRead:
    # Проверяем, что блюдо существует
    dish_res = await db.execute(select(Dish).where(Dish.id == rate_in.dish_id))
    if not dish_res.scalars().first():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Блюдо не найдено")

    rate = Rate(dish_id=rate_in.dish_id, value=rate_in.value)
    db.add(rate)
    await db.commit()
    await db.refresh(rate)
    return rate