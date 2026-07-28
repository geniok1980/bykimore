from typing import Optional
from pydantic import BaseModel, ConfigDict


class DishBase(BaseModel):
    name: str
    product_id: Optional[str] = None


class DishCreate(DishBase):
    # Вариант 1: создание блюда и опционально начальных значений цены и курса
    initial_price: Optional[float] = None
    initial_rate: Optional[float] = None


class DishRead(DishBase):
    id: int
    model_config = ConfigDict(from_attributes=True)