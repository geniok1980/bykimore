from sqlalchemy import Column, Integer, String

from app.db.base_class import Base


class Dish(Base):
    __tablename__ = "dishes"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False, index=True)
    # iiko product GUID (для идентификации блюд по productId в отчётах/стоп-листе)
    # Замечание: уникальность будет обеспечена индексом на уровне БД (SQLite) через лёгкую миграцию.
    product_id = Column(String, nullable=True, index=True)