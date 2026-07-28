from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_admin
from app.db.session import get_db
from app.models.iiko_settings import IikoSettings
from app.schemas.iiko_settings import (
    IikoSettingsRead,
    IikoSettingsCreate,
)

router = APIRouter()


@router.get("/", response_model=IikoSettingsRead | None)
async def get_iiko_settings(
    current_admin: Annotated[object, Depends(get_current_admin)],
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(IikoSettings).order_by(IikoSettings.id.asc()))
    settings = result.scalars().first()
    return settings


@router.post("/", response_model=IikoSettingsRead)
async def upsert_iiko_settings(
    payload: IikoSettingsCreate,
    current_admin: Annotated[object, Depends(get_current_admin)],
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(IikoSettings).order_by(IikoSettings.id.asc()))
    settings = result.scalars().first()
    if settings:
        if payload.server_host is not None:
            settings.server_host = payload.server_host
        if payload.server_login is not None:
            settings.server_login = payload.server_login
        if payload.server_password is not None:
            settings.server_password = payload.server_password
        if payload.active is not None:
            settings.active = payload.active
    else:
        settings = IikoSettings(
            server_host=payload.server_host,
            server_login=payload.server_login,
            server_password=payload.server_password,
            active=payload.active if payload.active is not None else True,
        )
        db.add(settings)
    await db.commit()
    await db.refresh(settings)
    return settings