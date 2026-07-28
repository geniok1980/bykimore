from datetime import datetime
from pydantic import BaseModel


class PriceBase(BaseModel):
    dish_id: int
    value: float


class PriceCreate(PriceBase):
    pass


class PriceRead(BaseModel):
    id: int
    dish_id: int
    value: float
    created_at: datetime

    class Config:
        from_attributes = True