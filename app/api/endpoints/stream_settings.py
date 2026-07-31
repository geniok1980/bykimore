from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.stream_settings import StreamSettings
from app.schemas.stream_settings import (
    StreamSettingsRead,
    StreamSettingsCreate,
)

router = APIRouter()


@router.get("", response_model=StreamSettingsRead | None)
async def get_stream_settings(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(StreamSettings).order_by(StreamSettings.id.asc()))
    settings = result.scalars().first()
    return settings


@router.post("", response_model=StreamSettingsRead)
async def upsert_stream_settings(payload: StreamSettingsCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(StreamSettings).order_by(StreamSettings.id.asc()))
    settings = result.scalars().first()
    if settings:
        if payload.hls_url is not None:
            settings.hls_url = payload.hls_url
        if payload.active is not None:
            settings.active = payload.active
    else:
        settings = StreamSettings(
            hls_url=payload.hls_url,
            active=payload.active if payload.active is not None else True,
        )
        db.add(settings)
    await db.commit()
    await db.refresh(settings)
    return settings