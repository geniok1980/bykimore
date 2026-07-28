from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin, get_current_user
from app.db.session import get_db
from app.models.dish import Dish
from app.models.price import Price
from app.models.rate import Rate
from app.schemas.dish import DishCreate, DishRead

router = APIRouter()


@router.get("/", response_model=list[DishRead])
async def list_dishes(
    # Для просмотра списка блюд достаточно быть аутентифицированным пользователем
    current_user: Annotated[object, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[DishRead]:
    result = await db.execute(select(Dish))
    dishes = result.scalars().all()
    return dishes


@router.post("/", status_code=status.HTTP_201_CREATED, response_model=DishRead)
async def add_dish(
    dish_in: DishCreate,
    current_user: Annotated[object, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DishRead:
    # Проверка на существование по имени
    existing = await db.execute(select(Dish).where(Dish.name == dish_in.name))
    if existing.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Блюдо с таким названием уже существует",
        )

    try:
        dish = Dish(name=dish_in.name)
        db.add(dish)
        # Получим id, не коммитя транзакцию
        await db.flush()

        # Если переданы начальные значения, добавим их в одной транзакции
        if dish_in.initial_price is not None:
            db.add(Price(dish_id=dish.id, value=float(dish_in.initial_price)))
        if dish_in.initial_rate is not None:
            db.add(Rate(dish_id=dish.id, value=float(dish_in.initial_rate)))

        await db.commit()
        await db.refresh(dish)
        return dish
    except Exception:
        # В случае ошибки откатим транзакцию и пробросим дальше
        await db.rollback()
        raise


@router.delete("/{dish_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_dish_by_id(
    dish_id: int,
    current_user: Annotated[object, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(select(Dish).where(Dish.id == dish_id))
    dish = result.scalars().first()
    if not dish:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Блюдо не найдено")

    await db.delete(dish)
    await db.commit()


@router.delete("/by-name/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_dish_by_name(
    name: str,
    current_user: Annotated[object, Depends(get_current_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    result = await db.execute(select(Dish).where(Dish.name == name))
    dish = result.scalars().first()
    if not dish:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Блюдо не найдено")

    await db.delete(dish)
    await db.commit()