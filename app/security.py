from enum import StrEnum
from fastapi import Header, HTTPException

class Role(StrEnum):
    VIEWER = "viewer"
    ANALYST = "analyst"
    COMMANDER = "commander"
    ADMIN = "admin"

ROLE_LEVEL = {
    Role.VIEWER: 1,
    Role.ANALYST: 2,
    Role.COMMANDER: 3,
    Role.ADMIN: 4,
}

def require_role(minimum: Role):
    def dependency(x_role: str = Header(default="viewer")):
        try:
            role = Role(x_role)
        except ValueError:
            raise HTTPException(status_code=403, detail="invalid role")
        if ROLE_LEVEL[role] < ROLE_LEVEL[minimum]:
            raise HTTPException(status_code=403, detail="insufficient role")
        return role
    return dependency
