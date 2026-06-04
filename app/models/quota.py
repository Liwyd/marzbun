from enum import Enum


class AdminQuotaLogType(str, Enum):
    user_created = "user_created"
    user_updated = "user_updated"
    user_deleted = "user_deleted"
    user_transferred_in = "user_transferred_in"
    user_transferred_out = "user_transferred_out"
    quota_adjusted = "quota_adjusted"
