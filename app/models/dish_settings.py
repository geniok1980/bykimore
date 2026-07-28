from sqlalchemy import Column, Integer, Float, Boolean, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import relationship, backref

from app.db.base_class import Base


class DishSettings(Base):
    __tablename__ = "dish_settings"

    id = Column(Integer, primary_key=True, index=True)
    dish_id = Column(Integer, ForeignKey("dishes.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)

    min_price = Column(Float, nullable=True)
    max_price = Column(Float, nullable=True)
    step = Column(Float, nullable=True)
    # Базовая цена (используется как стартовая/эталонная цена для расчётов)
    base_price = Column(Float, nullable=True)
    # Количество продаж (агрегированное значение для блюд)
    sales_quantity = Column(Integer, nullable=True, default=0)
    # Вес одной порции в граммах (для подсчёта общей массы стейков)
    weight_grams = Column(Integer, nullable=True, default=0)
    ttl_minutes = Column(Integer, nullable=True)
    active = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    dish = relationship("Dish", backref=backref("settings", passive_deletes=True))

    __table_args__ = (
        UniqueConstraint('dish_id', name='uq_dish_settings_dish'),
    )