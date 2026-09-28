from datetime import datetime, timedelta

import bcrypt
import jwt
from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

import logging
from core.config import settings

logger = logging.getLogger(__name__)

SECRET_KEY = settings.SECRET_KEY
if SECRET_KEY in ["super-secret-enterprise-key-for-balitowerops", "super-secret-enterprise-key-for-autorestock-agent"] and settings.APP_ENV != "development":
    logger.warning("SECURITY WARNING: Using default hardcoded SECRET_KEY in non-development environment! Set SECRET_KEY in .env.")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

security = HTTPBearer()

class TokenData(BaseModel):
    username: str
    role: str
    tenant_id: str

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
    except ValueError:
        return False

def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def get_current_user(credentials: HTTPAuthorizationCredentials = Security(security)) -> TokenData:
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        role: str = payload.get("role")
        tenant_id: str = payload.get("tenant_id")
        if username is None or role is None or tenant_id is None:
            raise HTTPException(status_code=401, detail="Invalid authentication credentials")
        token_data = TokenData(username=username, role=role, tenant_id=tenant_id)
        return token_data
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

def get_current_admin(current_user: TokenData = Security(get_current_user)) -> TokenData:
    if current_user.role != "ADMIN":
        raise HTTPException(status_code=403, detail="Not enough permissions. Admin required.")
    return current_user
