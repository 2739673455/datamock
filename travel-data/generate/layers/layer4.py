"""第四层：用户与会员。"""

from datetime import datetime, timedelta

from ..config import GENERATION_DEFAULTS
from ..generator_support import (
    RANDOM,
    bulk_insert,
    fetch_rows,
    json_text,
    random_business_date,
    random_email,
    random_id_no,
    random_name,
    reset_tables,
    unique_phone,
)
from .base import BaseGenerator
from .validations import validate_layer4


class Layer4Generator(BaseGenerator):
    layer = 4
    layer_name = "用户与会员"

    def run(self) -> None:
        self.header()
        reset_tables(
            "member_point_ledger",
            "member_accounts",
            "travelers",
            "user_profiles",
            "users",
        )
        cities = fetch_rows(
            """
            SELECT
                id,
                area_name AS name,
                area_full_name AS full_name
            FROM areas
            WHERE level = 2
            ORDER BY id
            """
        )
        user_count = GENERATION_DEFAULTS["users"]
        history_days = GENERATION_DEFAULTS["history_days"]
        now = datetime.now()
        users = []
        profiles = []
        travelers = []
        accounts = []
        ledgers = []
        for index in range(1, user_count + 1):
            city = cities[(index - 1) % len(cities)]
            user_name = random_name()
            user_created = now - timedelta(
                days=RANDOM.randint(1, history_days),
                hours=RANDOM.randint(0, 23),
                minutes=RANDOM.randint(0, 59),
            )
            user_updated = user_created + timedelta(
                days=RANDOM.randint(0, max(0, (now - user_created).days)),
                hours=RANDOM.randint(0, 23),
                minutes=RANDOM.randint(0, 59),
            )
            if user_updated > now:
                user_updated = now
            phone = unique_phone(index)
            email = random_email("user", index)
            birth_date = random_business_date(12000)
            user_gender_code = RANDOM.choice(["male", "female", "unknown"])
            profile_identity_no = random_id_no(index, birth_date)
            profile_identity_type_code = RANDOM.choice(["id_card", "passport"])
            profile_created = user_created + timedelta(minutes=RANDOM.randint(0, 180))
            profile_updated = max(profile_created, user_updated)
            joined_at = user_created + timedelta(minutes=RANDOM.randint(0, 120))
            account_updated = max(joined_at, user_updated)
            users.append(
                (
                    user_name,
                    f"https://example.com/avatar/{index}.jpg",
                    phone,
                    email,
                    user_gender_code,
                    birth_date,
                    city["id"],
                    RANDOM.choice(["normal", "vip", "inactive"]),
                    user_created,
                    user_updated,
                )
            )
            growth_value = RANDOM.randint(0, 20000)
            total_points = growth_value + RANDOM.randint(0, 10000)
            points_balance = RANDOM.randint(50, max(100, total_points))
            level_code = (
                "gold"
                if growth_value >= 12000
                else "silver"
                if growth_value >= 5000
                else "normal"
            )
            profiles.append(
                (
                    index,
                    user_name,
                    profile_identity_no,
                    profile_identity_type_code,
                    city["full_name"] or city["name"],
                    RANDOM.choice(["白领", "教师", "学生", "自由职业", "个体经营"]),
                    json_text({"preferred_language": "zh-CN"}),
                    profile_created,
                    profile_updated,
                )
            )
            traveler_count = RANDOM.randint(1, 3)
            accounts.append(
                (
                    index,
                    level_code,
                    points_balance,
                    total_points,
                    growth_value,
                    joined_at,
                    account_updated,
                )
            )
            ledger_occurred_at = joined_at + timedelta(minutes=RANDOM.randint(0, 30))
            ledgers.append(
                (
                    index,
                    "signup_bonus",
                    points_balance,
                    points_balance,
                    ledger_occurred_at,
                )
            )
            self_traveler_created = profile_created
            self_traveler_updated = max(self_traveler_created, user_updated)
            travelers.append(
                (
                    index,
                    user_name,
                    profile_identity_no,
                    profile_identity_type_code,
                    user_gender_code
                    if user_gender_code in {"male", "female"}
                    else RANDOM.choice(["male", "female"]),
                    birth_date,
                    phone,
                    "active",
                    self_traveler_created,
                    self_traveler_updated,
                )
            )
            for traveler_index in range(traveler_count - 1):
                traveler_name = random_name()
                traveler_birth_date = random_business_date(18000)
                traveler_created = user_created + timedelta(
                    days=RANDOM.randint(0, max(0, (now - user_created).days)),
                    hours=RANDOM.randint(0, 23),
                    minutes=RANDOM.randint(0, 59),
                )
                if traveler_created > now:
                    traveler_created = now
                traveler_updated = max(traveler_created, user_updated)
                travelers.append(
                    (
                        index,
                        traveler_name,
                        random_id_no(index * 10 + traveler_index, traveler_birth_date),
                        RANDOM.choice(["id_card", "passport"]),
                        RANDOM.choice(["male", "female"]),
                        traveler_birth_date,
                        unique_phone(index * 10 + traveler_index, prefix="15"),
                        "active",
                        traveler_created,
                        traveler_updated,
                    )
                )
        bulk_insert(
            """
            INSERT INTO users (
                nickname, avatar_url, phone, email, gender_code, birth_date,
                register_area_id, status_code, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            users,
        )
        bulk_insert(
            """
            INSERT INTO user_profiles (
                user_id, real_name, identity_no, identity_type_code,
                residence_city_name, occupation, preference_payload, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            profiles,
        )
        bulk_insert(
            """
            INSERT INTO travelers (
                user_id, traveler_name, identity_no, identity_type_code, gender_code,
                birth_date, phone, status_code, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            travelers,
        )
        bulk_insert(
            """
            INSERT INTO member_accounts (
                user_id, member_level_code, points_balance, total_points, growth_value,
                created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            accounts,
        )
        bulk_insert(
            """
            INSERT INTO member_point_ledger (
                user_id, ledger_type_code, points_delta, balance_after, created_at
            ) VALUES (%s, %s, %s, %s, %s)
            """,
            ledgers,
        )
        self.log_table_counts(
            {
                "users": len(users),
                "user_profiles": len(profiles),
                "travelers": len(travelers),
                "member_accounts": len(accounts),
                "member_point_ledger": len(ledgers),
            }
        )
        checks = validate_layer4()
        for check in checks:
            self.log(f"  [OK] validation: {check}")
