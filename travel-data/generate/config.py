import os
from contextlib import contextmanager
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
SEEDS_DIR = ROOT_DIR / "seeds"
SQL_DIR = ROOT_DIR / "sql"

load_dotenv(ROOT_DIR / ".env")

DB_CONFIG = {
    "host": os.environ["DB_HOST"],
    "port": int(os.environ["DB_PORT"]),
    "user": os.environ["DB_USER"],
    "password": os.environ["DB_PASSWORD"],
    "database": os.environ["DB_NAME"],
    "charset": "utf8mb4",
    "autocommit": False,
}

LAYERS = {
    1: {
        "name": "维度与基础主数据",
        "tables": [
            "areas",
            "currencies",
            "channels",
            "transport_hubs",
            "suppliers",
        ],
    },
    2: {
        "name": "商品主数据",
        "tables": [
            "hotels",
            "hotel_room_types",
            "hotel_booking_rules",
            "scenic_spots",
            "scenic_ticket_types",
            "scenic_booking_rules",
            "flight_routes",
            "train_routes",
            "bus_routes",
            "transfer_services",
            "transfer_service_area_rules",
        ],
    },
    3: {
        "name": "价格库存与班期",
        "tables": [
            "hotel_room_daily",
            "scenic_ticket_daily",
            "flight_departures",
            "flight_cabin_inventory",
            "train_departures",
            "train_seat_inventory",
            "bus_departures",
            "bus_seat_inventory",
            "transfer_capacity_calendar",
        ],
    },
    4: {
        "name": "用户与会员",
        "tables": [
            "users",
            "user_profiles",
            "travelers",
            "member_accounts",
            "member_point_ledger",
        ],
    },
    5: {
        "name": "营销",
        "tables": [
            "coupon_templates",
            "user_coupons",
            "promotions",
            "promotion_rules",
            "promotion_bindings",
        ],
    },
    6: {
        "name": "交易与资金",
        "tables": [
            "orders",
            "order_items",
            "order_coupon_usages",
            "order_promotion_details",
            "order_point_usages",
            "payments",
            "refund_requests",
            "refund_records",
        ],
    },
}

GENERATION_PROFILES = {
    "full": {
        "batch_size": 2000,
        "history_days": 730,
        "future_days": 90,
        "users": 100000,
        "orders": 500000,
    },
    "smoke": {
        "batch_size": 500,
        "history_days": 60,
        "future_days": 14,
        "users": 300,
        "orders": 600,
    },
}

GENERATION_DEFAULTS = dict(GENERATION_PROFILES["full"])


@contextmanager
def generation_profile(profile: str):
    original = dict(GENERATION_DEFAULTS)
    overrides = GENERATION_PROFILES[profile]
    GENERATION_DEFAULTS.clear()
    GENERATION_DEFAULTS.update(overrides)
    try:
        yield GENERATION_DEFAULTS
    finally:
        GENERATION_DEFAULTS.clear()
        GENERATION_DEFAULTS.update(original)
