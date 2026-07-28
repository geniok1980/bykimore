from typing import Optional
from pydantic import BaseModel, ConfigDict


class DishSettingsBase(BaseModel):
    dish_id: int
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    step: Optional[float] = None
    base_price: Optional[float] = None
    sales_quantity: Optional[int] = None
    weight_grams: Optional[int] = None
    ttl_minutes: Optional[int] = None
    active: bool = True


class DishSettingsCreate(DishSettingsBase):
    pass


class DishSettingsUpdate(BaseModel):
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    step: Optional[float] = None
    base_price: Optional[float] = None
    sales_quantity: Optional[int] = None
    weight_grams: Optional[int] = None
    ttl_minutes: Optional[int] = None
    active: Optional[bool] = None


class DishSettingsRead(BaseModel):
    id: int
    dish_id: int
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    step: Optional[float] = None
    base_price: Optional[float] = None
    sales_quantity: Optional[int] = None
    weight_grams: Optional[int] = None
    ttl_minutes: Optional[int] = None
    active: bool

    model_config = ConfigDict(from_attributes=True)
