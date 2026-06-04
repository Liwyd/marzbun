from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from passlib.context import CryptContext
from pydantic import BaseModel, ConfigDict, field_validator

from app.db import Session, crud, get_db
from app.models.quota import AdminQuotaLogType  # noqa: re-exported for convenience
from app.utils.jwt import get_admin_payload
from config import SUDOERS

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/admin/token")  # Admin view url


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class Admin(BaseModel):
    username: str
    is_sudo: bool
    telegram_id: Optional[int] = None
    discord_webhook: Optional[str] = None
    users_usage: Optional[int] = None
    # Quota fields — None means unlimited
    creation_quota_bytes: Optional[int] = None
    allocated_quota_bytes: int = 0
    model_config = ConfigDict(from_attributes=True)

    @field_validator("users_usage", "creation_quota_bytes", "allocated_quota_bytes", mode='before')
    def cast_to_int(cls, v):
        if v is None:  # Allow None values
            return v
        if isinstance(v, float):  # Allow float to int conversion
            return int(v)
        if isinstance(v, int):  # Allow integers directly
            return v
        raise ValueError("must be an integer or a float, not a string")  # Reject strings

    @classmethod
    def get_admin(cls, token: str, db: Session):
        payload = get_admin_payload(token)
        if not payload:
            return

        if payload['username'] in SUDOERS and payload['is_sudo'] is True:
            return cls(username=payload['username'], is_sudo=True)

        dbadmin = crud.get_admin(db, payload['username'])
        if not dbadmin:
            return

        if dbadmin.password_reset_at:
            if not payload.get("created_at"):
                return
            if dbadmin.password_reset_at > payload.get("created_at"):
                return

        return cls.model_validate(dbadmin)

    @classmethod
    def get_current(cls,
                    db: Session = Depends(get_db),
                    token: str = Depends(oauth2_scheme)):
        admin = cls.get_admin(token, db)
        if not admin:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return admin

    @classmethod
    def check_sudo_admin(cls,
                         db: Session = Depends(get_db),
                         token: str = Depends(oauth2_scheme)):
        admin = cls.get_admin(token, db)
        if not admin:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if not admin.is_sudo:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You're not allowed"
            )
        return admin


class AdminCreate(Admin):
    password: str
    telegram_id: Optional[int] = None
    discord_webhook: Optional[str] = None
    # creation_quota_bytes inherited from Admin (None = unlimited)

    @property
    def hashed_password(self):
        return pwd_context.hash(self.password)

    @field_validator("discord_webhook")
    @classmethod
    def validate_discord_webhook(cls, value):
        if value and not value.startswith("https://discord.com"):
            raise ValueError("Discord webhook must start with 'https://discord.com'")
        return value


class AdminModify(BaseModel):
    password: Optional[str] = None
    is_sudo: bool
    telegram_id: Optional[int] = None
    discord_webhook: Optional[str] = None
    # Use sentinel to distinguish "not sent" from "explicitly set to None"
    creation_quota_bytes: Optional[int] = -1  # -1 = not provided (leave unchanged)

    @property
    def hashed_password(self):
        if self.password:
            return pwd_context.hash(self.password)

    @field_validator("discord_webhook")
    @classmethod
    def validate_discord_webhook(cls, value):
        if value and not value.startswith("https://discord.com"):
            raise ValueError("Discord webhook must start with 'https://discord.com'")
        return value

    @field_validator("creation_quota_bytes", mode='before')
    @classmethod
    def validate_quota(cls, v):
        if v is None or v == -1:
            return v
        if isinstance(v, float):
            v = int(v)
        if isinstance(v, int) and v < 0:
            raise ValueError("creation_quota_bytes must be a positive integer or null (unlimited)")
        return v


class AdminPartialModify(AdminModify):
    __annotations__ = {k: Optional[v] for k, v in AdminModify.__annotations__.items()}


class AdminQuotaResponse(BaseModel):
    """Quota status for an admin."""
    admin_username: str
    is_unlimited: bool
    quota_limit: Optional[int] = None    # bytes; None = unlimited
    allocated: int                        # bytes currently allocated across owned users
    remaining: Optional[int] = None      # bytes still available; None = unlimited
    usage_percent: Optional[float] = None  # 0–100; None = unlimited

    model_config = ConfigDict(from_attributes=False)


class AdminInDB(Admin):
    username: str
    hashed_password: str

    def verify_password(self, plain_password):
        return pwd_context.verify(plain_password, self.hashed_password)


class AdminValidationResult(BaseModel):
    username: str
    is_sudo: bool
