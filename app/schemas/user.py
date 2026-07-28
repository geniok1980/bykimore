from typing import Optional

from pydantic import BaseModel, ConfigDict


class UserBase(BaseModel):
    username: str
    tenant_id: str
    role: str = "user"


class UserCreate(UserBase):
    password: str


class UserUpdate(BaseModel):
    username: Optional[str] = None
    password: Optional[str] = None
    role: Optional[str] = None


class UserInDBBase(UserBase):
    id: int
    model_config = ConfigDict(from_attributes=True)


class User(UserInDBBase):
    pass


class UserInDB(UserInDBBase):
    password: str # Hashed
