from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Union

from jose import jwt
import bcrypt

from app.core.config import settings

ALGORITHM = settings.ALGORITHM

pwd_context = None


def create_access_token(
    subject: Union[str, Any], role: str = "user", expires_delta: Optional[timedelta] = None
) -> str:
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )
    to_encode = {"exp": int(expire.timestamp()), "sub": str(subject), "role": role}
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def verify_password(plain_password: str, password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), password.encode("utf-8"))
    except Exception:
        return False


def get_password_hash(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode()
