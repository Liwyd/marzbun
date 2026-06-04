import re
from typing import Optional, Union

import typer
from decouple import UndefinedValueError, config
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app.db import GetDB, crud
from app.db.models import Admin, User
from app.models.admin import AdminCreate, AdminPartialModify
from app.utils.system import readable_size

from . import utils

app = typer.Typer(no_args_is_help=True)

# Regex for human-readable sizes: e.g. "150GB", "5 TB", "500 mb"
_SIZE_RE = re.compile(
    r"^\s*(?P<value>[\d.]+)\s*(?P<unit>[KMGTPE]?B?)\s*$",
    re.IGNORECASE,
)
_SIZE_UNITS = {
    "b": 1,
    "kb": 1024,
    "mb": 1024 ** 2,
    "gb": 1024 ** 3,
    "tb": 1024 ** 4,
    "pb": 1024 ** 5,
}


def parse_quota(value: str) -> Optional[int]:
    """Parse a human-readable size string into bytes.

    Accepts: 150GB, 5 TB, 500mb, 1024, etc.
    Returns None for '0', 'unlimited', or empty string.
    """
    if not value or value.strip().lower() in ("0", "unlimited", "none", "inf"):
        return None

    m = _SIZE_RE.match(value)
    if not m:
        # Try plain integer (bytes)
        try:
            v = int(value.strip())
            return v if v > 0 else None
        except ValueError:
            raise typer.BadParameter(
                f"Cannot parse quota '{value}'. "
                "Use formats like '150GB', '5TB', '500MB', or a plain byte count."
            )

    num = float(m.group("value"))
    unit = m.group("unit").lower().rstrip("b") + "b"
    if unit == "b":
        unit = "b"
    multiplier = _SIZE_UNITS.get(unit)
    if multiplier is None:
        raise typer.BadParameter(f"Unknown unit '{m.group('unit')}'.")

    return int(num * multiplier)


def format_quota(bytes_val: Optional[int]) -> str:
    if bytes_val is None:
        return "Unlimited"
    return readable_size(bytes_val)


def validate_telegram_id(value: Union[int, str]) -> Union[int, None]:
    if not value:
        return 0
    if not isinstance(value, int) and not value.isdigit():
        raise typer.BadParameter("Telegram ID must be an integer.")
    if int(value) < 0:
        raise typer.BadParameter("Telegram ID must be a positive integer.")
    return value


def validate_discord_webhook(value: str) -> Union[str, None]:
    if not value or value == "0":
        return ""
    if not value.startswith("https://discord.com/api/webhooks/"):
        utils.error("Discord webhook must start with 'https://discord.com/api/webhooks/'")
    return value


def calculate_admin_usage(admin_id: int) -> str:
    with GetDB() as db:
        usage = db.query(func.sum(User.used_traffic)).filter_by(admin_id=admin_id).first()[0]
        return readable_size(int(usage or 0))


def calculate_admin_reseted_usage(admin_id: int) -> str:
    with GetDB() as db:
        usage = db.query(func.sum(User.reseted_usage)).filter_by(admin_id=admin_id).scalar()
        return readable_size(int(usage or 0))


@app.command(name="list")
def list_admins(
    offset: Optional[int] = typer.Option(None, *utils.FLAGS["offset"]),
    limit: Optional[int] = typer.Option(None, *utils.FLAGS["limit"]),
    username: Optional[str] = typer.Option(None, *utils.FLAGS["username"], help="Search by username"),
):
    """Displays a table of admins"""
    with GetDB() as db:
        admins: list[Admin] = crud.get_admins(db, offset=offset, limit=limit, username=username)
        utils.print_table(
            table=Table(
                "Username", "Usage", "Reseted usage", "Users Usage", "Is sudo",
                "Quota Limit", "Allocated", "Remaining", "Created at",
                "Telegram ID", "Discord Webhook",
            ),
            rows=[
                (
                    str(admin.username),
                    calculate_admin_usage(admin.id),
                    calculate_admin_reseted_usage(admin.id),
                    readable_size(admin.users_usage),
                    "✔️" if admin.is_sudo else "✖️",
                    format_quota(admin.creation_quota_bytes),
                    readable_size(admin.allocated_quota_bytes or 0),
                    (
                        "Unlimited" if admin.creation_quota_bytes is None
                        else readable_size(
                            max(0, admin.creation_quota_bytes - (admin.allocated_quota_bytes or 0))
                        )
                    ),
                    utils.readable_datetime(admin.created_at),
                    str(admin.telegram_id or "✖️"),
                    str(admin.discord_webhook or "✖️"),
                )
                for admin in admins
            ]
        )


@app.command(name="delete")
def delete_admin(
    username: str = typer.Option(..., *utils.FLAGS["username"], prompt=True),
    yes_to_all: bool = typer.Option(False, *utils.FLAGS["yes_to_all"], help="Skips confirmations")
):
    """
    Deletes the specified admin

    Confirmations can be skipped using `--yes/-y` option.
    """
    with GetDB() as db:
        admin: Union[Admin, None] = crud.get_admin(db, username=username)
        if not admin:
            utils.error(f"There's no admin with username \"{username}\"!")

        if yes_to_all or typer.confirm(f'Are you sure about deleting "{username}"?', default=False):
            crud.remove_admin(db, admin)
            utils.success(f'"{username}" deleted successfully.')
        else:
            utils.error("Operation aborted!")


@app.command(name="create")
def create_admin(
    username: str = typer.Option(..., *utils.FLAGS["username"], show_default=False, prompt=True),
    is_sudo: bool = typer.Option(False, *utils.FLAGS["is_sudo"], prompt=True),
    password: str = typer.Option(
        ..., prompt=True, confirmation_prompt=True,
        hide_input=True, hidden=True, envvar=utils.PASSWORD_ENVIRON_NAME,
    ),
    telegram_id: str = typer.Option(
        '', *utils.FLAGS["telegram_id"], prompt="Telegram ID",
        show_default=False, callback=validate_telegram_id,
    ),
    discord_webhook: str = typer.Option(
        '', *utils.FLAGS["discord_webhook"], prompt=True,
        show_default=False, callback=validate_discord_webhook,
    ),
    quota: Optional[str] = typer.Option(
        None, "--quota", "-q",
        help="Creation quota (e.g. 150GB, 5TB, 500MB). Omit or use 'unlimited' for no limit.",
    ),
):
    """
    Creates an admin

    Password can also be set using the `MARZBAN_ADMIN_PASSWORD` environment variable for non-interactive usages.

    Examples:
      marzban-cli admin create --username alice --quota 150GB
      marzban-cli admin create --username bob --quota unlimited
    """
    quota_bytes: Optional[int] = None
    if quota is not None:
        try:
            quota_bytes = parse_quota(quota)
        except typer.BadParameter as e:
            utils.error(str(e))

    with GetDB() as db:
        try:
            crud.create_admin(db, AdminCreate(
                username=username,
                password=password,
                is_sudo=is_sudo,
                telegram_id=telegram_id,
                discord_webhook=discord_webhook,
                creation_quota_bytes=quota_bytes,
            ))
            quota_display = "Unlimited" if quota_bytes is None else readable_size(quota_bytes)
            utils.success(f'Admin "{username}" created successfully. Quota: {quota_display}')
        except IntegrityError:
            utils.error(f'Admin "{username}" already exists!')


@app.command(name="update")
def update_admin(username: str = typer.Option(..., *utils.FLAGS["username"], prompt=True, show_default=False)):
    """
    Updates the specified admin

    NOTE: This command CAN NOT be used non-interactively.
    """

    def _get_modify_model(admin: Admin):
        Console().print(
            Panel(f'Editing "{username}". Just press "Enter" to leave each field unchanged.')
        )

        is_sudo: bool = typer.confirm("Is sudo", default=admin.is_sudo)
        new_password: Union[str, None] = typer.prompt(
            "New password",
            default="",
            show_default=False,
            confirmation_prompt=True,
            hide_input=True
        ) or None

        telegram_id: str = typer.prompt(
            "Telegram ID (Enter 0 to clear current value)",
            default=admin.telegram_id or "",
        )
        telegram_id = validate_telegram_id(telegram_id)

        discord_webhook: str = typer.prompt(
            "Discord webhook (Enter 0 to clear current value)",
            default=admin.discord_webhook or "",
        )
        discord_webhook = validate_discord_webhook(discord_webhook)

        current_quota = (
            "Unlimited" if admin.creation_quota_bytes is None
            else readable_size(admin.creation_quota_bytes)
        )
        quota_str: str = typer.prompt(
            f"Creation quota (current: {current_quota}; enter 'unlimited' to remove, e.g. 150GB)",
            default="" if admin.creation_quota_bytes is None else readable_size(admin.creation_quota_bytes),
            show_default=False,
        )

        # -1 = sentinel meaning "leave unchanged"; we always update quota here
        quota_bytes: Optional[int]
        if quota_str.strip() == "":
            quota_bytes = admin.creation_quota_bytes  # unchanged
        else:
            try:
                quota_bytes = parse_quota(quota_str)
            except typer.BadParameter as e:
                utils.error(str(e))

        return AdminPartialModify(
            is_sudo=is_sudo,
            password=new_password,
            telegram_id=telegram_id,
            discord_webhook=discord_webhook,
            creation_quota_bytes=quota_bytes,
        )

    with GetDB() as db:
        admin: Union[Admin, None] = crud.get_admin(db, username=username)
        if not admin:
            utils.error(f"There's no admin with username \"{username}\"!")

        crud.partial_update_admin(db, admin, _get_modify_model(admin))
        utils.success(f'Admin "{username}" updated successfully.')


@app.command(name="import-from-env")
def import_from_env(yes_to_all: bool = typer.Option(False, *utils.FLAGS["yes_to_all"], help="Skips confirmations")):
    """
    Imports the sudo admin from env

    Confirmations can be skipped using `--yes/-y` option.

    What does it do?
      - Creates a sudo admin according to `SUDO_USERNAME` and `SUDO_PASSWORD`.
      - Links any user which doesn't have an `admin_id` to the imported sudo admin.
    """
    try:
        username, password = config("SUDO_USERNAME"), config("SUDO_PASSWORD")
    except UndefinedValueError:
        utils.error(
            "Unable to get SUDO_USERNAME and/or SUDO_PASSWORD.\n"
            "Make sure you have set them in the env file or as environment variables."
        )

    if not (username and password):
        utils.error("Unable to retrieve username and password.\n"
                    "Make sure both SUDO_USERNAME and SUDO_PASSWORD are set.")

    with GetDB() as db:
        admin: Union[None, Admin] = None

        # If env admin already exists
        if current_admin := crud.get_admin(db, username=username):
            if not yes_to_all and not typer.confirm(
                f'Admin "{username}" already exists. Do you want to sync it with env?', default=None
            ):
                utils.error("Aborted.")

            admin = crud.partial_update_admin(
                db,
                current_admin,
                AdminPartialModify(password=password, is_sudo=True)
            )
        # If env admin does not exist yet
        else:
            admin = crud.create_admin(db, AdminCreate(
                username=username,
                password=password,
                is_sudo=True
            ))

        updated_user_count = db.query(User).filter_by(admin_id=None).update({"admin_id": admin.id})
        db.commit()

        utils.success(
            f'Admin "{username}" imported successfully.\n'
            f"{updated_user_count} users' admin_id set to the {username}'s id.\n"
            'You must delete SUDO_USERNAME and SUDO_PASSWORD from your env file now.'
        )


@app.command(name="quota-rebuild")
def quota_rebuild(
    username: Optional[str] = typer.Option(
        None, *utils.FLAGS["username"],
        help="Rebuild for a specific admin only. Omit to rebuild all quota-limited admins.",
    ),
    yes_to_all: bool = typer.Option(False, *utils.FLAGS["yes_to_all"], help="Skips confirmations"),
):
    """
    Rebuild allocated quota counters from actual user data_limits.

    Use this to repair corrupted counters after direct DB edits, migrations,
    imports, or any operation that bypassed the normal API.

    Only admins with a creation quota set are affected.
    """
    if not yes_to_all and not typer.confirm(
        "This will recalculate allocated_quota_bytes for all quota-limited admins. Continue?",
        default=True,
    ):
        utils.error("Aborted.")

    with GetDB() as db:
        admin_id: Optional[int] = None
        if username:
            admin = crud.get_admin(db, username=username)
            if not admin:
                utils.error(f'Admin "{username}" not found!')
            if admin.creation_quota_bytes is None:
                utils.success(f'Admin "{username}" is unlimited — nothing to rebuild.')
            admin_id = admin.id

        results = crud.rebuild_admin_quota(db, admin_id=admin_id)

        if not results:
            utils.success("No quota-limited admins found. Nothing to rebuild.")

        Console().print(
            Panel(
                "\n".join(
                    f"  admin_id={aid}  allocated={readable_size(bytes_val)}"
                    for aid, bytes_val in results.items()
                ),
                title="Quota Rebuild Results",
            )
        )
        utils.success(f"Rebuilt quota counters for {len(results)} admin(s).")
