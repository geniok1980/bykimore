from datetime import datetime
from pydantic import BaseModel


class RateBase(BaseModel):
    dish_id: int
    value: float


class RateCreate(RateBase):
    pass


class RateRead(BaseModel):
    id: int
    dish_id: int
    value: float
    created_at: datetime

    class Config:
        from_attributes = True