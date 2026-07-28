from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_admin, get_current_user, get_user_service
from app.models.user import User as DBUser
from app.schemas.user import User, UserCreate, UserUpdate
from app.services.user import UserService

router = APIRouter()


@router.get("/me", response_model=User)
async def read_users_me(
    current_user: Annotated[DBUser, Depends(get_current_user)],
) -> User:
    return current_user


@router.put("/me", response_model=User)
async def update_user_me(
    *,
    user_in: UserUpdate,
    current_user: Annotated[DBUser, Depends(get_current_user)],
    user_service: UserService = Depends(get_user_service)
) -> User:
    user = await user_service.update(db_obj=current_user, obj_in=user_in)
    return user


@router.get("/{user_id}", response_model=User)
async def read_user_by_id(
    user_id: int,
    current_user: Annotated[DBUser, Depends(get_current_user)],
    user_service: UserService = Depends(get_user_service)
) -> User:
    user = await user_service.get(user_id=user_id)

    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == current_user.id:
        return user

    raise HTTPException(status_code=403, detail="Not enough permissions")


@router.get("/", response_model=list[User])
async def read_all_users(
    current_user: Annotated[DBUser, Depends(get_current_admin)],
    user_service: UserService = Depends(get_user_service)
) -> list[User]:
    """Получить список всех пользователей (только для админов)"""
    users = await user_service.get_all_users()
    return users


@router.post("/", status_code=201, response_model=User)
async def create_user(
    *,
    user_in: UserCreate,
    current_user: Annotated[DBUser, Depends(get_current_admin)],
    user_service: UserService = Depends(get_user_service)
) -> User:
    """Создать нового пользователя (только для админов)"""
    # Проверка существования пользователя
    user = await user_service.get_by_username(username=user_in.username)
    if user:
        raise HTTPException(
            status_code=400,
            detail="Username already registered"
        )
    
    # Ограничение ролей для админов
    if current_user.role == "admin" and user_in.role == "superadmin":
        raise HTTPException(
            status_code=403,
            detail="Admins cannot create superadmin users"
        )
    
    user = await user_service.create(obj_in=user_in)
    return user


@router.put("/{user_id}", response_model=User)
async def update_user(
    *,
    user_id: int,
    user_in: UserUpdate,
    current_user: Annotated[DBUser, Depends(get_current_admin)],
    user_service: UserService = Depends(get_user_service)
) -> User:
    """Обновить пользователя (только для админов)"""
    user = await user_service.get(user_id=user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Проверка прав
    if current_user.role == "admin":
        # Админы не могут изменять суперадминов
        if user.role == "superadmin":
            raise HTTPException(status_code=403, detail="Cannot modify superadmin")
        # Админы не могут повысить кого-то до суперадмина
        if user_in.role == "superadmin":
            raise HTTPException(status_code=403, detail="Cannot create superadmin")
    
    user = await user_service.update(db_obj=user, obj_in=user_in)
    return user


@router.delete("/{user_id}", status_code=204)
async def delete_user(
    user_id: int,
    current_user: Annotated[DBUser, Depends(get_current_admin)],
    user_service: UserService = Depends(get_user_service)
):
    """Удалить пользователя (только для админов)"""
    user = await user_service.get(user_id=user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Нельзя удалить себя
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    
    # Админы не могут удалить суперадминов
    if current_user.role == "admin" and user.role == "superadmin":
        raise HTTPException(status_code=403, detail="Cannot delete superadmin")
    
    await user_service.db.delete(user)
    await user_service.db.commit()
