from sqlalchemy import Column, Integer, String, Boolean, DateTime, func
from app.db.base_class import Base


class StreamSettings(Base):
    __tablename__ = "stream_settings"

    id = Column(Integer, primary_key=True, index=True)
    hls_url = Column(String, nullable=True)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)