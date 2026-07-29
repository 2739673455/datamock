import json
import math
import random
import re
import string
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from .config import GENERATION_DEFAULTS
from .db import db
from .progress import (
    advance_table_progress,
    finish_table_progress,
    start_table_progress,
)

RANDOM = random.Random(42)
MONEY = Decimal("0.01")

FIRST_NAMES = list("赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦许何吕施张孔曹严华金魏陶姜")
LAST_NAMES = [
    "晨",
    "轩",
    "雨",
    "诺",
    "萌",
    "安",
    "涛",
    "磊",
    "洋",
    "媛",
    "洁",
    "宇",
    "雯",
    "宁",
    "辰",
    "睿",
    "涵",
    "瑶",
    "彤",
    "萱",
    "怡",
    "佳",
    "可",
    "然",
    "霖",
    "航",
    "铭",
    "凯",
    "俊",
    "博",
    "瑞",
    "琪",
    "璇",
    "妍",
    "欣",
    "乐",
    "言",
    "宸",
    "希",
    "朗",
    "昕",
    "桐",
    "璟",
]
HOTEL_BRANDS = [
    "云栖",
    "山海",
    "悦居",
    "轻旅",
    "橙宿",
    "天际",
    "远行",
    "泊心",
    "澜庭",
    "栖野",
    "沐光",
    "知行",
    "云汐",
    "禾木",
    "星屿",
    "观澜",
    "逸舍",
    "合景",
    "泊云",
    "青岚",
    "望舒",
    "行舟",
    "松间",
    "听海",
    "隐庐",
    "悦庭",
    "澄舍",
    "锦程",
    "安泊",
    "泊岸",
]
SCENIC_PREFIXES = [
    "国家公园",
    "文化古城",
    "山水景区",
    "森林乐园",
    "温泉度假区",
    "滨海公园",
]
AIRLINES = ["MU", "CA", "CZ", "HO", "3U", "HU", "FM"]
TRAIN_PREFIXES = ["G", "D", "C"]
BUS_COMPANIES = ["城际快线", "旅运集团", "巴士联盟", "畅行客运"]
TRANSFER_TYPES = [
    "airport_pickup",
    "airport_dropoff",
    "charter_daily",
    "station_transfer",
]
CHANNEL_CODES = ["app", "web", "miniapp", "h5"]
ORDER_PRODUCT_TYPES = [
    "hotel_room",
    "scenic_ticket",
    "flight_cabin",
    "train_seat",
    "bus_seat",
    "transfer_service",
]


def quantize_money(value: float | Decimal) -> Decimal:
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


def random_name() -> str:
    return (
        RANDOM.choice(FIRST_NAMES)
        + RANDOM.choice(LAST_NAMES)
        + RANDOM.choice(LAST_NAMES)
    )


def random_phone() -> str:
    return "1" + "".join(RANDOM.choice(string.digits) for _ in range(10))


def unique_phone(index: int, prefix: str = "13") -> str:
    return f"{prefix}{index:09d}"[-11:]


def random_email(name: str, index: int) -> str:
    handle = "".join(ch for ch in name.lower() if ch.isascii()) or f"user{index}"
    return f"{handle}{index}@example.com"


def random_id_no(seed: int, birth_date: date | None = None) -> str:
    if birth_date is None:
        birth_date = random_business_date(18000)
    base = f"110101{birth_date:%Y%m%d}{seed % 10000:04d}"
    return base + str(seed % 10)


def random_datetime_between(start: datetime, end: datetime) -> datetime:
    delta = int((end - start).total_seconds())
    if delta <= 0:
        return start
    return start + timedelta(seconds=RANDOM.randint(0, delta))


def random_past_datetime(
    now: datetime | None = None,
    min_days_ago: int = 1,
    max_days_ago: int = 365,
) -> datetime:
    now = now or datetime.now()
    start = now - timedelta(days=max_days_ago)
    end = now - timedelta(days=min_days_ago)
    return random_datetime_between(start, end)


def lifecycle_timestamps(
    now: datetime | None = None,
    min_days_ago: int = 1,
    max_days_ago: int = 365,
) -> tuple[datetime, datetime]:
    now = now or datetime.now()
    created_at = random_past_datetime(
        now, min_days_ago=min_days_ago, max_days_ago=max_days_ago
    )
    updated_at = random_datetime_between(created_at, now)
    return created_at, updated_at


def dated_record_timestamps(
    business_date: date | datetime,
    now: datetime | None = None,
    lead_days_min: int = 1,
    lead_days_max: int = 45,
) -> tuple[datetime, datetime]:
    now = now or datetime.now()
    anchor = (
        business_date
        if isinstance(business_date, datetime)
        else datetime.combine(business_date, time(hour=12))
    )
    latest_updated_at = min(now, anchor + timedelta(hours=6))
    created_upper_bound = min(latest_updated_at, anchor - timedelta(hours=1))
    created_lower_bound = created_upper_bound - timedelta(
        days=RANDOM.randint(lead_days_min, lead_days_max),
        hours=RANDOM.randint(0, 23),
        minutes=RANDOM.randint(0, 59),
    )
    if created_lower_bound > created_upper_bound:
        created_lower_bound = created_upper_bound
    created_at = random_datetime_between(created_lower_bound, created_upper_bound)
    updated_at = random_datetime_between(created_at, latest_updated_at)
    return created_at, updated_at


def weighted_recent_day(history_days: int) -> int:
    sample = RANDOM.random()
    return min(history_days - 1, int((sample**2.6) * history_days))


def random_business_date(history_days: int) -> date:
    today = datetime.now().date()
    offset = weighted_recent_day(history_days)
    return today - timedelta(days=offset)


def json_text(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False)


def chunks(rows: list[tuple], batch_size: int | None = None):
    size = batch_size or GENERATION_DEFAULTS["batch_size"]
    for start in range(0, len(rows), size):
        yield rows[start : start + size]


def _insert_table_name(sql: str) -> str | None:
    match = re.search(r"INSERT\s+INTO\s+`?([A-Za-z0-9_]+)`?", sql, re.IGNORECASE)
    return match.group(1) if match else None


def bulk_insert(
    sql: str,
    rows: list[tuple],
    batch_size: int | None = None,
    *,
    finalize: bool = True,
) -> int:
    count = 0
    table_name = _insert_table_name(sql)
    if table_name is not None:
        start_table_progress(table_name, len(rows) if finalize else 0)
    try:
        for batch in chunks(rows, batch_size):
            inserted = db.executemany(sql, batch)
            count += inserted
            if table_name is not None:
                advance_table_progress(table_name, inserted)
    finally:
        if table_name is not None and finalize:
            finish_table_progress(table_name, count)
    return count


def bulk_insert_stream(
    sql: str,
    rows,
    *,
    total_rows: int | None = None,
    build_step_name: str | None = None,
    batch_size: int | None = None,
    finalize: bool = True,
) -> int:
    size = batch_size or GENERATION_DEFAULTS["batch_size"]
    count = 0
    batch: list[tuple] = []
    table_name = _insert_table_name(sql)
    if table_name is not None:
        start_table_progress(table_name, (total_rows or 0) if finalize else 0)
    try:
        for row in rows:
            batch.append(row)
            if len(batch) >= size:
                inserted = db.executemany(sql, batch)
                count += inserted
                if table_name is not None:
                    advance_table_progress(table_name, inserted)
                batch.clear()
        if batch:
            inserted = db.executemany(sql, batch)
            count += inserted
            if table_name is not None:
                advance_table_progress(table_name, inserted)
    finally:
        if table_name is not None and finalize:
            finish_table_progress(table_name, count)
    return count


def reset_tables(*tables: str) -> None:
    db.execute("SET FOREIGN_KEY_CHECKS = 0")
    for table in tables:
        db.execute(f"TRUNCATE TABLE `{table}`")
    db.execute("SET FOREIGN_KEY_CHECKS = 1")


def fetch_ids(table: str, where: str | None = None) -> list[int]:
    sql = f"SELECT id FROM {table}"
    if where:
        sql += f" WHERE {where}"
    return [row["id"] for row in db.fetch_all(sql)]


def fetch_rows(sql: str) -> list[dict[str, Any]]:
    return list(db.fetch_all(sql))


def make_code(prefix: str, seq: int, width: int = 6) -> str:
    return f"{prefix}{seq:0{width}d}"


def choose_many(items: list, minimum: int, maximum: int) -> list:
    if not items:
        return []
    count = RANDOM.randint(minimum, min(maximum, len(items)))
    return RANDOM.sample(items, count)


def maybe(probability: float) -> bool:
    return RANDOM.random() < probability


def split_amount(amount: Decimal, ratio: float) -> Decimal:
    return quantize_money(amount * Decimal(str(ratio)))


def safe_div(a: int, b: int) -> int:
    return max(1, math.ceil(a / max(1, b)))


def random_time_window(start_hour: int, end_hour: int, minute_step: int = 5) -> time:
    hour = RANDOM.randint(start_hour, end_hour)
    minute = RANDOM.choice(range(0, 60, minute_step))
    return time(hour=hour, minute=minute)
