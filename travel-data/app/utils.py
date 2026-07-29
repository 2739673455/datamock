from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

LOCAL_TZ = ZoneInfo("Asia/Shanghai")


def parse_date(value: str, field_name: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f"{field_name} 格式必须为 YYYY-MM-DD") from exc


def parse_datetime(value: str, field_name: str) -> datetime:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise ValueError(f"{field_name} 格式必须为 YYYY-MM-DD HH:MM:SS")


def offset_limit(page_no: int, page_size: int) -> tuple[int, int]:
    page_no = max(page_no, 1)
    page_size = max(min(page_size, 100), 1)
    return (page_no - 1) * page_size, page_size


def masked_identity(identity_no: str | None) -> str | None:
    if not identity_no:
        return None
    if len(identity_no) <= 4:
        return "*" * len(identity_no)
    if len(identity_no) <= 8:
        return identity_no[:2] + "*" * (len(identity_no) - 4) + identity_no[-2:]
    return identity_no[:3] + "*" * (len(identity_no) - 7) + identity_no[-4:]


def normalize_identity(identity_no: str) -> str:
    return identity_no.replace(" ", "").upper()


def make_no(prefix: str) -> str:
    return f"{prefix}{local_now().strftime('%Y%m%d%H%M%S%f')}"


def local_now() -> datetime:
    return datetime.now(LOCAL_TZ).replace(tzinfo=None)


def decimal_to_float(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def first_or_none(items: list[dict[str, Any]]) -> dict[str, Any] | None:
    return items[0] if items else None


def format_datetime(value: datetime | None) -> str | None:
    return value.strftime("%Y-%m-%d %H:%M:%S") if value is not None else None


def format_date(value: date | None) -> str | None:
    return value.strftime("%Y-%m-%d") if value is not None else None


def money(value: Decimal | float | int | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return float(Decimal(str(value)))


def count_total(sql: str, params: Any | None = None) -> int:
    from .database import fetch_one

    row = fetch_one(sql, params)
    if row is None or row["total"] is None:
        return 0
    return int(row["total"])
