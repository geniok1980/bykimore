from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.api.deps import get_user_service
from app.core.config import settings
from app.core.security import create_access_token
from app.schemas.token import Token
from app.schemas.user import UserCreate
from app.services.user import UserService

router = APIRouter()


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login", response_model=Token)
async def login_access_token(
    user_service: Annotated[UserService, Depends(get_user_service)],
    body: LoginRequest,
) -> Token:
    try:
        user = await user_service.authenticate(
            username=body.username, password=body.password
        )
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        return Token(
            access_token=create_access_token(
                subject=str(user.id), role=user.role, expires_delta=access_token_expires
            ),
            token_type="bearer",
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register_user(
    *,
    user_in: UserCreate,
    user_service: UserService = Depends(get_user_service)
) -> dict:
    # Проверка существования пользователя
    user = await user_service.get_by_username(username=user_in.username)
    if user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered",
        )
    
    # Проверка количества пользователей
    user_count = await user_service.count_users()
    
    # Если это первый пользователь - делаем его superadmin
    # Иначе - проверяем, что роль не была изменена (регулярная регистрация без роли)
    if user_count == 0:
        user_in.role = "superadmin"
    else:
        # Обычные пользователи не могут регистрироваться сами
        # Регистрация закрыта, только админы могут создавать пользователей
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Registration is closed. Please contact an administrator."
        )
    
    await user_service.create(obj_in=user_in)
    return {"message": "User registered successfully"}
