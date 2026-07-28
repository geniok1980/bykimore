from typing import Optional, Union

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_password_hash, verify_password
from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class UserService:
    """
    Lightweight per-request service wrapper around AsyncSession.
    IMPORTANT: Do NOT use a singleton here. AsyncSession instances
    are scoped per request and must not be reused across requests.
    Reusing the same session causes InvalidRequestError when the
    session is closed/rolled back by the request lifecycle.
    """

    def __init__(self, db: AsyncSession):
        # Always store the provided session; no global/singleton state
        self.db = db

    async def get(self, user_id: int) -> Optional[User]:
        query = select(User).where(User.id == user_id)
        result = await self.db.execute(query)
        return result.scalars().first()
    
    async def get_by_username(self, username: str) -> Optional[User]:
        query = select(User).where(User.username == username)
        result = await self.db.execute(query)
        return result.scalars().first()
    
    async def create(self, obj_in: UserCreate) -> User:
        user_data = obj_in.model_dump() if isinstance(obj_in, UserCreate) else obj_in
        user = User(**user_data)

        password = get_password_hash(user_data["password"])
        user.password = password

        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)

        return user
    
    async def update(
        self, *, db_obj: User, obj_in: Union[UserUpdate, dict]
    ) -> User:
        if isinstance(obj_in, dict):
            update_data = obj_in
        else:
            update_data = obj_in.model_dump(exclude_unset=True)
        
        if update_data.get("password"):
            password = get_password_hash(update_data["password"])
            del update_data["password"]
            update_data["password"] = password
        
        for field, value in update_data.items():
            setattr(db_obj, field, value)
        
        self.db.add(db_obj)
        await self.db.commit()
        await self.db.refresh(db_obj)
        return db_obj
    
    async def authenticate(
        self, *, username: str, password: str
    ) -> Optional[User]:
        user = await self.get_by_username(username=username)
        if not user:
            return None
        if not verify_password(password, user.password):
            return None
        return user
    
    async def count_users(self) -> int:
        """Подсчитать количество пользователей в системе"""
        query = select(User)
        result = await self.db.execute(query)
        return len(result.scalars().all())
    
    async def get_all_users(self) -> list[User]:
        """Получить всех пользователей"""
        query = select(User)
        result = await self.db.execute(query)
        return result.scalars().all()