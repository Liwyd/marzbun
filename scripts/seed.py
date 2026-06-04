"""
Seed script: creates dev admin accounts and sample users.

Usage (from project root, with .env loaded):
    python scripts/seed.py

Idempotent: skips records that already exist.
"""

import os
import sys
from datetime import datetime, timedelta

# Ensure the project root is on sys.path regardless of where the script is called from.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load the .env file before importing any app modules.
from dotenv import load_dotenv
load_dotenv()

from sqlalchemy.exc import IntegrityError

from app.db import GetDB, crud
from app.db.models import Admin, User
from app.models.admin import AdminCreate
from app.models.user import UserDataLimitResetStrategy, UserStatus
from app.utils.crypto import get_password_hash


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_admin(db, username: str, password: str, is_sudo: bool) -> Admin:
    existing = crud.get_admin(db, username=username)
    if existing:
        print(f"  [skip] admin '{username}' already exists")
        return existing
    admin = crud.create_admin(db, AdminCreate(
        username=username,
        password=password,
        is_sudo=is_sudo,
    ))
    role = "sudo" if is_sudo else "regular"
    print(f"  [ok]   admin '{username}' created ({role})")
    return admin


def _create_user(
    db,
    username: str,
    admin: Admin,
    status: UserStatus,
    data_limit: int | None = None,
    expire_days: int | None = None,
    note: str = "",
) -> User:
    from app.db import crud as _crud
    existing = _crud.get_user(db, username=username)
    if existing:
        print(f"  [skip] user '{username}' already exists")
        return existing

    expire_ts: int | None = None
    if expire_days is not None:
        expire_ts = int((datetime.utcnow() + timedelta(days=expire_days)).timestamp())

    user = User(
        username=username,
        status=status,
        data_limit=data_limit,
        expire=expire_ts,
        admin=admin,
        data_limit_reset_strategy=UserDataLimitResetStrategy.no_reset,
        note=note,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    print(f"  [ok]   user '{username}' created (status={status.value})")
    return user


# ---------------------------------------------------------------------------
# Seed
# ---------------------------------------------------------------------------

def seed():
    print("\n=== Seeding database ===\n")

    with GetDB() as db:
        # ── Admins ──────────────────────────────────────────────────────────
        print("Admins:")
        sudo_admin = _create_admin(db, username="admin",     password="admin123", is_sudo=True)
        _create_admin(            db, username="testadmin",  password="admin123", is_sudo=False)

        # ── Sample users (owned by sudo admin) ──────────────────────────────
        print("\nUsers:")

        # Active user with a 10 GB data limit, expires in 30 days
        _create_user(
            db,
            username="user_limited",
            admin=sudo_admin,
            status=UserStatus.active,
            data_limit=10 * 1024 ** 3,   # 10 GB
            expire_days=30,
            note="Limited user — 10 GB / 30 days",
        )

        # Active user with no data limit and no expiry
        _create_user(
            db,
            username="user_unlimited",
            admin=sudo_admin,
            status=UserStatus.active,
            data_limit=None,
            expire_days=None,
            note="Unlimited user — no data cap, no expiry",
        )

        # Expired user (expiry date is in the past)
        with GetDB() as db2:
            existing = crud.get_user(db2, username="user_expired")
            if existing:
                print("  [skip] user 'user_expired' already exists")
            else:
                past_ts = int((datetime.utcnow() - timedelta(days=1)).timestamp())
                user_expired = User(
                    username="user_expired",
                    status=UserStatus.expired,
                    data_limit=5 * 1024 ** 3,
                    expire=past_ts,
                    admin=sudo_admin,
                    data_limit_reset_strategy=UserDataLimitResetStrategy.no_reset,
                    note="Expired user — expiry was yesterday",
                )
                db2.add(user_expired)
                db2.commit()
                print("  [ok]   user 'user_expired' created (status=expired)")

        # Disabled user
        _create_user(
            db,
            username="user_disabled",
            admin=sudo_admin,
            status=UserStatus.disabled,
            data_limit=None,
            expire_days=None,
            note="Disabled user — manually disabled",
        )

        # On-hold user (waiting to be activated)
        _create_user(
            db,
            username="user_onhold",
            admin=sudo_admin,
            status=UserStatus.on_hold,
            data_limit=3 * 1024 ** 3,    # 3 GB
            expire_days=None,
            note="On-hold user — 3 GB, starts on first connection",
        )

    print("\n=== Seed complete ===")
    print("\nLogin credentials:")
    print("  Sudo admin  →  username: admin      password: admin123")
    print("  Test admin  →  username: testadmin  password: admin123")
    print("\nDashboard: http://127.0.0.1:8000/dashboard/")
    print("Swagger UI: http://127.0.0.1:8000/docs  (requires DOCS=True)\n")


if __name__ == "__main__":
    seed()
