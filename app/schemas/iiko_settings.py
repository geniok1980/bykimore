from pydantic import BaseModel
from typing import Optional


class IikoSettingsBase(BaseModel):
    server_host: Optional[str] = None
    server_login: Optional[str] = None
    server_password: Optional[str] = None
    active: Optional[bool] = True


class IikoSettingsCreate(IikoSettingsBase):
    pass


class IikoSettingsUpdate(IikoSettingsBase):
    pass


class IikoSettingsRead(BaseModel):
    id: int
    server_host: Optional[str] = None
    server_login: Optional[str] = None
    server_password: Optional[str] = None
    active: bool
    last_sync_at: Optional[str] = None

    class Config:
        from_attributes = True