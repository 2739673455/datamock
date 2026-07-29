"""第五层：营销。"""

from datetime import datetime, timedelta

from ..config import GENERATION_DEFAULTS
from ..db import db
from ..generator_support import (
    RANDOM,
    fetch_rows,
    make_code,
    random_datetime_between,
    reset_tables,
)
from .base import BaseGenerator
from .seed_importer import SeedImporter
from .validations import validate_layer5

COUPON_WINDOW_DAYS = 120
COUPON_WINDOW_STEP_DAYS = 45


class Layer5Generator(BaseGenerator):
    layer = 5
    layer_name = "营销"

    def run(self) -> None:
        self.header()
        reset_tables(
            "promotion_bindings",
            "promotion_rules",
            "promotions",
            "user_coupons",
            "coupon_templates",
        )
        now = datetime.now()
        counts: dict[str, int] = {}
        counts.update(self._generate_coupon_templates())
        counts.update(self._generate_user_coupons(now))
        counts.update(self._generate_promotions())
        self.log_table_counts(counts)
        checks = validate_layer5()
        for check in checks:
            self.log(f"  [OK] validation: {check}")

    def _generate_coupon_templates(self) -> dict[str, int]:
        importer = SeedImporter()
        file_path = importer.require_table_file("coupon_templates", self.layer)
        columns, rows = importer.load_csv(file_path, "coupon_templates")
        now = datetime.now()
        history_days = GENERATION_DEFAULTS["history_days"]
        future_days = GENERATION_DEFAULTS["future_days"]
        timeline_start = now - timedelta(days=history_days)
        timeline_end = now + timedelta(days=future_days)

        generated_columns = [
            *columns,
            "valid_from",
            "valid_until",
            "created_at",
            "updated_at",
        ]
        generated_rows = []
        for index, row in enumerate(rows):
            window_start = timeline_start + timedelta(
                days=(index * COUPON_WINDOW_STEP_DAYS) % max(1, history_days)
            )
            if window_start > now:
                window_start = now - timedelta(days=COUPON_WINDOW_DAYS // 2)
            window_end = min(
                timeline_end, window_start + timedelta(days=COUPON_WINDOW_DAYS)
            )
            if window_end < now and index % 4 == 0:
                window_end = min(timeline_end, now + timedelta(days=30))
                window_start = window_end - timedelta(days=COUPON_WINDOW_DAYS)
            created_at = window_start - timedelta(days=RANDOM.randint(7, 30))
            updated_at = min(now, max(created_at, window_start + timedelta(days=1)))
            generated_rows.append(
                [
                    *row,
                    window_start,
                    window_end,
                    created_at,
                    updated_at,
                ]
            )

        count = db.executemany(
            importer.build_insert_sql("coupon_templates", generated_columns),
            generated_rows,
        )
        return {"coupon_templates": count}

    def _generate_user_coupons(self, now: datetime) -> dict[str, int]:
        users = fetch_rows("SELECT id FROM users ORDER BY id")
        templates = fetch_rows(
            """
            SELECT id, currency_code, min_spend_amount, discount_amount, max_discount_amount,
                   valid_from, valid_until, created_at
            FROM coupon_templates
            ORDER BY id
            """
        )

        sampled_by_template = [
            (
                template,
                RANDOM.sample(users, min(len(users), RANDOM.randint(1200, 2600))),
            )
            for template in templates
        ]
        total_rows = sum(len(sampled_users) for _, sampled_users in sampled_by_template)

        def rows():
            seq = 1
            for template, sampled_users in sampled_by_template:
                used_quota = max(1, int(len(sampled_users) * 0.22))
                for sample_index, user in enumerate(sampled_users):
                    created_at = random_datetime_between(
                        max(
                            template["created_at"],
                            template["valid_from"] - timedelta(days=15),
                        ),
                        min(now, template["valid_from"]),
                    )
                    should_mark_used = (
                        sample_index < used_quota and template["valid_from"] <= now
                    )
                    if should_mark_used:
                        status_code = "used"
                        used_at = random_datetime_between(
                            max(created_at, template["valid_from"]),
                            min(template["valid_until"], now),
                        )
                        updated_at = used_at
                    elif template["valid_until"] < now:
                        status_code = "expired"
                        used_at = None
                        updated_at = min(template["valid_until"], now)
                    elif RANDOM.random() < 0.18:
                        status_code = "used"
                        used_at = random_datetime_between(
                            max(created_at, template["valid_from"]),
                            min(template["valid_until"], now),
                        )
                        updated_at = used_at
                    else:
                        status_code = "available"
                        used_at = None
                        updated_at = created_at
                    yield (
                        template["id"],
                        user["id"],
                        make_code("UCN", seq, 10),
                        template["currency_code"],
                        template["min_spend_amount"],
                        template["discount_amount"],
                        template["max_discount_amount"],
                        template["valid_from"],
                        template["valid_until"],
                        status_code,
                        used_at,
                        created_at,
                        updated_at,
                    )
                    seq += 1

        count = self.stream_rows(
            """
            INSERT INTO user_coupons (
                template_id, user_id, coupon_code, currency_code, min_spend_amount,
                discount_amount, max_discount_amount, valid_from, valid_until,
                status_code, used_at, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            rows(),
            total_rows=total_rows,
            build_step_name="build user_coupons",
        )
        return {"user_coupons": count}

    def _generate_promotions(self) -> dict[str, int]:
        importer = SeedImporter()
        return {
            "promotions": importer.import_required_table(
                "promotions", self.layer, clear=False
            ),
            "promotion_rules": importer.import_required_table(
                "promotion_rules", self.layer, clear=False
            ),
            "promotion_bindings": importer.import_required_table(
                "promotion_bindings", self.layer, clear=False
            ),
        }
