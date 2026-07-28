from pydantic import BaseModel


class BeerExchangeItem(BaseModel):
    id: int
    name: str
    price: float | None = None
    rate: float | None = None
    # Признак, что блюдо в стоп-листе (распродано/недоступно)
    stoplisted: bool = False