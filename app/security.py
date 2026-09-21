import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum

import jwt
from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .models import User

class Role(StrEnum):
    VIEWER = "viewer"
    ANALYST = "analyst"
    COMMANDER = "commander"
    ADMIN = "admin"

ROLE_LEVEL = {Role.VIEWER: 1, Role.ANALYST: 2, Role.COMMANDER: 3, Role.ADMIN: 4}

@dataclass
class CurrentUser:
    uid: str
    username: str | None
    role: Role
    db_id: int | None = None

def _secret() -> str:
    return os.getenv("APP_SECRET", "dev-only-change-me")

def issue_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user.pi_uid,
        "username": user.username,
        "role": user.role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=12)).timestamp()),
    }
    return jwt.encode(payload, _secret(), algorithm="HS256")

def _dev_user(x_role: str | None) -> CurrentUser | None:
    if os.getenv("APP_ENV", "development") != "development":
        return None
    if os.getenv("DEV_AUTH_BYPASS", "false").lower() != "true":
        return None
    try:
        role = Role(x_role or "admin")
    except ValueError:
        role = Role.ADMIN
    return CurrentUser(uid="dev-user", username="Development User", role=role)

def get_current_user(
    authorization: str | None = Header(default=None),
    x_role: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> CurrentUser:
    dev = _dev_user(x_role)
    if dev and not authorization:
        return dev
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="authentication required")
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = jwt.decode(token, _secret(), algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="invalid or expired session")
    uid = payload.get("sub")
    if not uid:
        raise HTTPException(status_code=401, detail="invalid session")
    user = db.scalar(select(User).where(User.pi_uid == uid))
    if not user or not user.is_active:
        raise HTTPException(status_code=403, detail="user disabled")
    try:
        role = Role(user.role)
    except ValueError:
        role = Role.VIEWER
    return CurrentUser(uid=user.pi_uid, username=user.username, role=role, db_id=user.id)

def require_role(minimum: Role):
    def dependency(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if ROLE_LEVEL[user.role] < ROLE_LEVEL[minimum]:
            raise HTTPException(status_code=403, detail="insufficient role")
        return user
    return dependency
