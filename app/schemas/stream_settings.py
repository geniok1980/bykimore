from pydantic import BaseModel, HttpUrl
from typing import Optional


class StreamSettingsBase(BaseModel):
    hls_url: Optional[str] = None
    active: Optional[bool] = True


class StreamSettingsCreate(StreamSettingsBase):
    pass


class StreamSettingsUpdate(StreamSettingsBase):
    pass


class StreamSettingsRead(BaseModel):
    id: int
    hls_url: Optional[str] = None
    active: bool

    class Config:
        from_attributes = True