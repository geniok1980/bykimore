from typing import Annotated

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import ALGORITHM
from app.db.session import get_db
from app.models.user import User
from app.schemas.token import TokenPayload
from app.services.user import UserService
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

reusable_oauth2 = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/auth/login"
)


async def get_user_service(
    db: Annotated[AsyncSession, Depends(get_db)]
) -> UserService:
    return UserService(db)


def get_vector_store():
    """Заглушка для vector store"""
    return None

async def get_current_user(
    user_service: Annotated[UserService, Depends(get_user_service)],
    request: Request,
) -> User:
    logger.info("=== TOKEN VALIDATION STARTED ===")
    # Try Authorization: Bearer <token> first
    auth_header = request.headers.get("Authorization") or ""
    token = ""
    if auth_header.lower().startswith("bearer "):
        token = auth_header.split(" ", 1)[1].strip()
    # Fallback to cookie 'access_token' if header missing
    if not token:
        token = request.cookies.get("access_token") or ""
    logger.info(f"Token received (first 20 chars): {token[:20]}...")
    
    try:
        logger.info("Attempting to decode JWT token...")
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[ALGORITHM]
        )
        logger.info(f"Token payload decoded successfully: {payload}")
        
        token_data = TokenPayload(**payload)
        logger.info(f"Token data created: sub={token_data.sub}, exp={token_data.exp}")
        
    except JWTError as e:
        logger.error(f"JWT Error during token validation: {str(e)}")
        logger.error(f"JWT Error type: {type(e).__name__}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials - JWT Error",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except ValidationError as e:
        logger.error(f"Validation Error during token parsing: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials - Validation Error",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        logger.error(f"Unexpected error during token validation: {str(e)}")
        logger.error(f"Error type: {type(e).__name__}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials - Unexpected Error",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user_id = int(token_data.sub)
    logger.info(f"Looking for user with ID: {user_id}")
    
    user = await user_service.get(user_id=user_id)
    
    if not user:
        logger.error(f"User not found for ID: {user_id}")
        raise HTTPException(status_code=404, detail="User not found")
        
    logger.info(f"User found successfully: {user.username} (ID: {user.id})")
    logger.info("=== TOKEN VALIDATION COMPLETED SUCCESSFULLY ===")
    return user


async def get_current_admin(
    current_user: Annotated[User, Depends(get_current_user)]
) -> User:
    """Зависимость для проверки прав администратора"""
    if current_user.role not in ["admin", "superadmin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    return current_user


async def get_current_superadmin(
    current_user: Annotated[User, Depends(get_current_user)]
) -> User:
    """Зависимость для проверки прав суперадмина"""
    if current_user.role != "superadmin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    return current_user