"""
JWT Authentication for FinComply API.
Simple username/password auth with JWT tokens.
"""
import os
import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# ─── Config ───────────────────────────────────────────────────
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "fincomply-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = int(os.getenv("TOKEN_EXPIRE_HOURS", "24"))

# ─── Users (in production, store in DB) ───────────────────────
# Format: {username: hashed_password}
pwd_context = CryptContext(schemes=["sha256_crypt"], deprecated="auto")

def get_users() -> dict:
    """Load users from environment variables."""
    users = {}
    admin_password = os.getenv("ADMIN_PASSWORD")
    if not admin_password:
        raise ValueError("ADMIN_PASSWORD environment variable is required")
    users["admin"] = {
        "username": "admin",
        "hashed_password": pwd_context.hash(admin_password),
        "role": "admin",
    }
    # Additional users from env
    extra_user = os.getenv("VIEWER_USERNAME", "")
    extra_pass = os.getenv("VIEWER_PASSWORD", "")
    if extra_user and extra_pass:
        users[extra_user] = {
            "username": extra_user,
            "hashed_password": pwd_context.hash(extra_pass),
            "role": "viewer",
        }
    return users

# ─── Schemas ──────────────────────────────────────────────────
class LoginRequest(BaseModel):
    username: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    role: str
    expires_in: int

# ─── Core auth functions ───────────────────────────────────────
def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def authenticate_user(username: str, password: str) -> Optional[dict]:
    users = get_users()
    user = users.get(username)
    if not user:
        return None
    if not verify_password(password, user["hashed_password"]):
        return None
    return user

def create_access_token(data: dict) -> str:
    payload = data.copy()
    expire = datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    payload["exp"] = expire
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

# ─── FastAPI dependency ────────────────────────────────────────
security = HTTPBearer(auto_error=False)

def get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> dict:
    """Validate JWT token and return current user."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if not username:
            raise HTTPException(status_code=401, detail="Invalid token")
        return {"username": username, "role": payload.get("role", "viewer")}
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user