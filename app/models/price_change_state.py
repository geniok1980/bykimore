from sqlalchemy import Column, Integer, DateTime, UniqueConstraint

from app.db.base_class import Base


class PriceChangeState(Base):
    __tablename__ = "price_change_state"

    # dish_id: блюдо, для которого мы храним следующее допустимое время изменения цены
    dish_id = Column(Integer, nullable=False, index=True)
    next_change_allowed_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("dish_id", name="uq_price_change_state_dish_id"),
    )