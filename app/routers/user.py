from datetime import datetime, timedelta, timezone
from typing import List, Optional, Union

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError

from app import logger, xray
from app.db import Session, crud, get_db, QuotaExceededError, UnlimitedUserQuotaError
from app.db.crud import _effective_data_limit
from app.dependencies import get_expired_users_list, get_validated_user, validate_dates
from app.models.admin import Admin
from app.models.quota import AdminQuotaLogType
from app.models.user import (
    UserCreate,
    UserModify,
    UserResponse,
    UsersResponse,
    UserStatus,
    UsersUsagesResponse,
    UserUsagesResponse,
)
from app.utils import report, responses

router = APIRouter(tags=["User"], prefix="/api", responses={401: responses._401})


@router.post("/user", response_model=UserResponse, responses={400: responses._400, 409: responses._409})
def add_user(
    new_user: UserCreate,
    bg: BackgroundTasks,
    db: Session = Depends(get_db),
    admin: Admin = Depends(Admin.get_current),
):
    """
    Add a new user

    - **username**: 3 to 32 characters, can include a-z, 0-9, and underscores.
    - **status**: User's status, defaults to `active`. Special rules if `on_hold`.
    - **expire**: UTC timestamp for account expiration. Use `0` for unlimited.
    - **data_limit**: Max data usage in bytes (e.g., `1073741824` for 1GB). `0` means unlimited.
    - **data_limit_reset_strategy**: Defines how/if data limit resets. `no_reset` means it never resets.
    - **proxies**: Dictionary of protocol settings (e.g., `vmess`, `vless`).
    - **inbounds**: Dictionary of protocol tags to specify inbound connections.
    - **note**: Optional text field for additional user information or notes.
    - **on_hold_timeout**: UTC timestamp when `on_hold` status should start or end.
    - **on_hold_expire_duration**: Duration (in seconds) for how long the user should stay in `on_hold` status.
    - **next_plan**: Next user plan (resets after use).
    """

    # TODO expire should be datetime instead of timestamp

    for proxy_type in new_user.proxies:
        if not xray.config.inbounds_by_protocol.get(proxy_type):
            raise HTTPException(
                status_code=400,
                detail=f"Protocol {proxy_type} is disabled on your server",
            )

    dbadmin = crud.get_admin(db, admin.username)
    effective_limit = _effective_data_limit(new_user.data_limit)

    if dbadmin and dbadmin.creation_quota_bytes is not None:
        # Quota-limited admin: unlimited users are not allowed
        if effective_limit is None:
            raise HTTPException(
                status_code=400,
                detail="Your admin account has a creation quota. Users with unlimited data are not allowed.",
            )
        try:
            crud.check_admin_quota(db, dbadmin, effective_limit)
        except QuotaExceededError as e:
            raise HTTPException(status_code=400, detail=str(e))

    try:
        dbuser = crud.create_user(db, new_user, admin=dbadmin)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="User already exists")

    # Adjust quota after successful creation (within a new transaction)
    if dbadmin and dbadmin.creation_quota_bytes is not None and effective_limit:
        crud.adjust_admin_quota(
            db, dbadmin.id,
            delta_bytes=effective_limit,
            event_type=AdminQuotaLogType.user_created,
            user_id=dbuser.id,
            new_data_limit=effective_limit,
        )

    bg.add_task(xray.operations.add_user, dbuser=dbuser)
    user = UserResponse.model_validate(dbuser)
    report.user_created(user=user, user_id=dbuser.id, by=admin, user_admin=dbuser.admin)
    logger.info(f'New user "{dbuser.username}" added')
    return user


@router.get("/user/{username}", response_model=UserResponse, responses={403: responses._403, 404: responses._404})
def get_user(dbuser: UserResponse = Depends(get_validated_user)):
    """Get user information"""
    return dbuser


@router.put("/user/{username}", response_model=UserResponse, responses={400: responses._400, 403: responses._403, 404: responses._404})
def modify_user(
    modified_user: UserModify,
    bg: BackgroundTasks,
    db: Session = Depends(get_db),
    dbuser: UsersResponse = Depends(get_validated_user),
    admin: Admin = Depends(Admin.get_current),
):
    """
    Modify an existing user

    - **username**: Cannot be changed. Used to identify the user.
    - **status**: User's new status. Can be 'active', 'disabled', 'on_hold', 'limited', or 'expired'.
    - **expire**: UTC timestamp for new account expiration. Set to `0` for unlimited, `null` for no change.
    - **data_limit**: New max data usage in bytes (e.g., `1073741824` for 1GB). Set to `0` for unlimited, `null` for no change.
    - **data_limit_reset_strategy**: New strategy for data limit reset. Options include 'daily', 'weekly', 'monthly', or 'no_reset'.
    - **proxies**: Dictionary of new protocol settings (e.g., `vmess`, `vless`). Empty dictionary means no change.
    - **inbounds**: Dictionary of new protocol tags to specify inbound connections. Empty dictionary means no change.
    - **note**: New optional text for additional user information or notes. `null` means no change.
    - **on_hold_timeout**: New UTC timestamp for when `on_hold` status should start or end. Only applicable if status is changed to 'on_hold'.
    - **on_hold_expire_duration**: New duration (in seconds) for how long the user should stay in `on_hold` status. Only applicable if status is changed to 'on_hold'.
    - **next_plan**: Next user plan (resets after use).

    Note: Fields set to `null` or omitted will not be modified.
    """

    for proxy_type in modified_user.proxies:
        if not xray.config.inbounds_by_protocol.get(proxy_type):
            raise HTTPException(
                status_code=400,
                detail=f"Protocol {proxy_type} is disabled on your server",
            )

    # Quota check when data_limit is being changed
    old_limit = _effective_data_limit(dbuser.data_limit)
    new_limit = _effective_data_limit(modified_user.data_limit) if modified_user.data_limit is not None else old_limit

    if modified_user.data_limit is not None and new_limit != old_limit:
        owner_admin = dbuser.admin
        if owner_admin and owner_admin.creation_quota_bytes is not None:
            if new_limit is None:
                raise HTTPException(
                    status_code=400,
                    detail="Your admin account has a creation quota. Users with unlimited data are not allowed.",
                )
            delta = (new_limit or 0) - (old_limit or 0)
            if delta > 0:
                try:
                    crud.check_admin_quota(db, owner_admin, delta)
                except QuotaExceededError as e:
                    raise HTTPException(status_code=400, detail=str(e))

    old_status = dbuser.status
    dbuser = crud.update_user(db, dbuser, modified_user)
    user = UserResponse.model_validate(dbuser)

    # Adjust quota after successful update
    if modified_user.data_limit is not None and new_limit != old_limit:
        owner_admin = dbuser.admin
        if owner_admin and owner_admin.creation_quota_bytes is not None:
            delta = (new_limit or 0) - (old_limit or 0)
            crud.adjust_admin_quota(
                db, owner_admin.id,
                delta_bytes=delta,
                event_type=AdminQuotaLogType.user_updated,
                user_id=dbuser.id,
                old_data_limit=old_limit,
                new_data_limit=new_limit,
            )

    if user.status in [UserStatus.active, UserStatus.on_hold]:
        bg.add_task(xray.operations.update_user, dbuser=dbuser)
    else:
        bg.add_task(xray.operations.remove_user, dbuser=dbuser)

    bg.add_task(report.user_updated, user=user, user_admin=dbuser.admin, by=admin)

    logger.info(f'User "{user.username}" modified')

    if user.status != old_status:
        bg.add_task(
            report.status_change,
            username=user.username,
            status=user.status,
            user=user,
            user_admin=dbuser.admin,
            by=admin,
        )
        logger.info(
            f'User "{dbuser.username}" status changed from {old_status} to {user.status}'
        )

    return user


@router.delete("/user/{username}", responses={403: responses._403, 404: responses._404})
def remove_user(
    bg: BackgroundTasks,
    db: Session = Depends(get_db),
    dbuser: UserResponse = Depends(get_validated_user),
    admin: Admin = Depends(Admin.get_current),
):
    """Remove a user"""
    # Capture quota info before deletion
    owner_admin = dbuser.admin
    released_limit = _effective_data_limit(dbuser.data_limit)
    user_id = dbuser.id

    crud.remove_user(db, dbuser)

    # Release quota after deletion
    if owner_admin and owner_admin.creation_quota_bytes is not None and released_limit:
        crud.adjust_admin_quota(
            db, owner_admin.id,
            delta_bytes=-released_limit,
            event_type=AdminQuotaLogType.user_deleted,
            user_id=user_id,
            old_data_limit=released_limit,
        )

    bg.add_task(xray.operations.remove_user, dbuser=dbuser)

    bg.add_task(
        report.user_deleted, username=dbuser.username, user_admin=Admin.model_validate(owner_admin), by=admin
    )

    logger.info(f'User "{dbuser.username}" deleted')
    return {"detail": "User successfully deleted"}


@router.post("/user/{username}/reset", response_model=UserResponse, responses={403: responses._403, 404: responses._404})
def reset_user_data_usage(
    bg: BackgroundTasks,
    db: Session = Depends(get_db),
    dbuser: UserResponse = Depends(get_validated_user),
    admin: Admin = Depends(Admin.get_current),
):
    """Reset user data usage"""
    dbuser = crud.reset_user_data_usage(db=db, dbuser=dbuser)
    if dbuser.status in [UserStatus.active, UserStatus.on_hold]:
        bg.add_task(xray.operations.add_user, dbuser=dbuser)

    user = UserResponse.model_validate(dbuser)
    bg.add_task(
        report.user_data_usage_reset, user=user, user_admin=dbuser.admin, by=admin
    )

    logger.info(f'User "{dbuser.username}"\'s usage was reset')
    return dbuser


@router.post("/user/{username}/revoke_sub", response_model=UserResponse, responses={403: responses._403, 404: responses._404})
def revoke_user_subscription(
    bg: BackgroundTasks,
    db: Session = Depends(get_db),
    dbuser: UserResponse = Depends(get_validated_user),
    admin: Admin = Depends(Admin.get_current),
):
    """Revoke users subscription (Subscription link and proxies)"""
    dbuser = crud.revoke_user_sub(db=db, dbuser=dbuser)

    if dbuser.status in [UserStatus.active, UserStatus.on_hold]:
        bg.add_task(xray.operations.update_user, dbuser=dbuser)
    user = UserResponse.model_validate(dbuser)
    bg.add_task(
        report.user_subscription_revoked, user=user, user_admin=dbuser.admin, by=admin
    )

    logger.info(f'User "{dbuser.username}" subscription revoked')

    return user


@router.get("/users", response_model=UsersResponse, responses={400: responses._400, 403: responses._403, 404: responses._404})
def get_users(
    offset: int = None,
    limit: int = None,
    username: List[str] = Query(None),
    search: Union[str, None] = None,
    owner: Union[List[str], None] = Query(None, alias="admin"),
    status: UserStatus = None,
    sort: str = None,
    db: Session = Depends(get_db),
    admin: Admin = Depends(Admin.get_current),
):
    """Get all users"""
    if sort is not None:
        opts = sort.strip(",").split(",")
        sort = []
        for opt in opts:
            try:
                sort.append(crud.UsersSortingOptions[opt])
            except KeyError:
                raise HTTPException(
                    status_code=400, detail=f'"{opt}" is not a valid sort option'
                )

    users, count = crud.get_users(
        db=db,
        offset=offset,
        limit=limit,
        search=search,
        usernames=username,
        status=status,
        sort=sort,
        admins=owner if admin.is_sudo else [admin.username],
        return_with_count=True,
    )

    return {"users": users, "total": count}


@router.post("/users/reset", responses={403: responses._403, 404: responses._404})
def reset_users_data_usage(
    db: Session = Depends(get_db), admin: Admin = Depends(Admin.check_sudo_admin)
):
    """Reset all users data usage"""
    dbadmin = crud.get_admin(db, admin.username)
    crud.reset_all_users_data_usage(db=db, admin=dbadmin)
    startup_config = xray.config.include_db_users()
    xray.core.restart(startup_config)
    for node_id, node in list(xray.nodes.items()):
        if node.connected:
            xray.operations.restart_node(node_id, startup_config)
    return {"detail": "Users successfully reset."}


@router.get("/user/{username}/usage", response_model=UserUsagesResponse, responses={403: responses._403, 404: responses._404})
def get_user_usage(
    dbuser: UserResponse = Depends(get_validated_user),
    start: str = "",
    end: str = "",
    db: Session = Depends(get_db),
):
    """Get users usage"""
    start, end = validate_dates(start, end)

    usages = crud.get_user_usages(db, dbuser, start, end)

    return {"usages": usages, "username": dbuser.username}


@router.post("/user/{username}/active-next", response_model=UserResponse, responses={403: responses._403, 404: responses._404})
def active_next_plan(
    bg: BackgroundTasks,
    db: Session = Depends(get_db),
    dbuser: UserResponse = Depends(get_validated_user),
):
    """Reset user by next plan"""
    dbuser = crud.reset_user_by_next(db=db, dbuser=dbuser)

    if (dbuser is None or dbuser.next_plan is None):
        raise HTTPException(
            status_code=404,
            detail=f"User doesn't have next plan",
        )

    if dbuser.status in [UserStatus.active, UserStatus.on_hold]:
        bg.add_task(xray.operations.add_user, dbuser=dbuser)

    user = UserResponse.model_validate(dbuser)
    bg.add_task(
        report.user_data_reset_by_next, user=user, user_admin=dbuser.admin,
    )

    logger.info(f'User "{dbuser.username}"\'s usage was reset by next plan')
    return dbuser


@router.get("/users/usage", response_model=UsersUsagesResponse)
def get_users_usage(
    start: str = "",
    end: str = "",
    db: Session = Depends(get_db),
    owner: Union[List[str], None] = Query(None, alias="admin"),
    admin: Admin = Depends(Admin.get_current),
):
    """Get all users usage"""
    start, end = validate_dates(start, end)

    usages = crud.get_all_users_usages(
        db=db, start=start, end=end, admin=owner if admin.is_sudo else [admin.username]
    )

    return {"usages": usages}


@router.put("/user/{username}/set-owner", response_model=UserResponse)
def set_owner(
    admin_username: str,
    dbuser: UserResponse = Depends(get_validated_user),
    db: Session = Depends(get_db),
    admin: Admin = Depends(Admin.check_sudo_admin),
):
    """Set a new owner (admin) for a user."""
    new_admin = crud.get_admin(db, username=admin_username)
    if not new_admin:
        raise HTTPException(status_code=404, detail="Admin not found")

    old_admin = dbuser.admin
    user_limit = _effective_data_limit(dbuser.data_limit)

    # Quota check on receiving admin
    if new_admin.creation_quota_bytes is not None:
        if user_limit is None:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Admin \"{new_admin.username}\" has a creation quota. "
                    "Cannot transfer a user with unlimited data to this admin."
                ),
            )
        try:
            crud.check_admin_quota(db, new_admin, user_limit)
        except QuotaExceededError as e:
            raise HTTPException(status_code=400, detail=str(e))

    dbuser = crud.set_owner(db, dbuser, new_admin)
    user = UserResponse.model_validate(dbuser)

    # Adjust quotas after transfer
    if user_limit:
        if old_admin and old_admin.creation_quota_bytes is not None:
            crud.adjust_admin_quota(
                db, old_admin.id,
                delta_bytes=-user_limit,
                event_type=AdminQuotaLogType.user_transferred_out,
                user_id=dbuser.id,
                old_data_limit=user_limit,
            )
        if new_admin.creation_quota_bytes is not None:
            crud.adjust_admin_quota(
                db, new_admin.id,
                delta_bytes=user_limit,
                event_type=AdminQuotaLogType.user_transferred_in,
                user_id=dbuser.id,
                new_data_limit=user_limit,
            )

    logger.info(f'{user.username} owner successfully set to {admin_username}')

    return user


@router.get("/users/expired", response_model=List[str])
def get_expired_users(
    expired_after: Optional[datetime] = Query(None, example="2024-01-01T00:00:00"),
    expired_before: Optional[datetime] = Query(None, example="2024-01-31T23:59:59"),
    db: Session = Depends(get_db),
    admin: Admin = Depends(Admin.get_current),
):
    """
    Get users who have expired within the specified date range.

    - **expired_after** UTC datetime (optional)
    - **expired_before** UTC datetime (optional)
    - At least one of expired_after or expired_before must be provided for filtering
    - If both are omitted, returns all expired users
    """

    expired_after, expired_before = validate_dates(expired_after, expired_before)

    expired_users = get_expired_users_list(db, admin, expired_after, expired_before)
    return [u.username for u in expired_users]


@router.delete("/users/expired", response_model=List[str])
def delete_expired_users(
    bg: BackgroundTasks,
    expired_after: Optional[datetime] = Query(None, example="2024-01-01T00:00:00"),
    expired_before: Optional[datetime] = Query(None, example="2024-01-31T23:59:59"),
    db: Session = Depends(get_db),
    admin: Admin = Depends(Admin.get_current),
):
    """
    Delete users who have expired within the specified date range.

    - **expired_after** UTC datetime (optional)
    - **expired_before** UTC datetime (optional)
    - At least one of expired_after or expired_before must be provided
    """
    expired_after, expired_before = validate_dates(expired_after, expired_before)

    expired_users = get_expired_users_list(db, admin, expired_after, expired_before)
    removed_users = [u.username for u in expired_users]

    if not removed_users:
        raise HTTPException(
            status_code=404, detail="No expired users found in the specified date range"
        )

    # Capture quota release info before deletion (group by admin)
    quota_releases: dict = {}  # admin_id → (admin_obj, total_delta)
    for u in expired_users:
        lim = _effective_data_limit(u.data_limit)
        if lim and u.admin and u.admin.creation_quota_bytes is not None:
            aid = u.admin.id
            if aid not in quota_releases:
                quota_releases[aid] = (u.admin, 0)
            quota_releases[aid] = (u.admin, quota_releases[aid][1] + lim)

    crud.remove_users(db, expired_users)

    # Release quota after bulk deletion
    for aid, (owner_admin, total_delta) in quota_releases.items():
        crud.adjust_admin_quota(
            db, aid,
            delta_bytes=-total_delta,
            event_type=AdminQuotaLogType.user_deleted,
        )

    for removed_user in removed_users:
        logger.info(f'User "{removed_user}" deleted')
        bg.add_task(
            report.user_deleted,
            username=removed_user,
            user_admin=next(
                (u.admin for u in expired_users if u.username == removed_user), None
            ),
            by=admin,
        )

    return removed_users
