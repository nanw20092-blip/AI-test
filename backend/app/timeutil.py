from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo


def local_parts(issued_at: datetime, tz_name: str) -> tuple[str, date]:
    """Tenant-local stamp and calendar date for an aware timestamp."""
    if issued_at.tzinfo is None:
        issued_at = issued_at.replace(tzinfo=timezone.utc)
    local = issued_at.astimezone(ZoneInfo(tz_name))
    return local.strftime("%Y-%m-%d %H:%M"), local.date()


def iso_z(issued_at: datetime) -> str:
    if issued_at.tzinfo is None:
        issued_at = issued_at.replace(tzinfo=timezone.utc)
    issued_at = issued_at.astimezone(timezone.utc).replace(microsecond=0)
    return issued_at.strftime("%Y-%m-%dT%H:%M:%SZ")
