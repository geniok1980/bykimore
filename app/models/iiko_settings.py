from sqlalchemy import Column, Integer, String, Boolean, DateTime, func
from app.db.base_class import Base


class IikoSettings(Base):
    __tablename__ = "iiko_settings"

    id = Column(Integer, primary_key=True, index=True)
    server_host = Column(String, nullable=True)
    server_login = Column(String, nullable=True)
    server_password = Column(String, nullable=True)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    last_sync_at = Column(DateTime(timezone=True), nullable=True)