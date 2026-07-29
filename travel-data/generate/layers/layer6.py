"""第六层：交易与资金。"""

import json
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal

from ..config import GENERATION_DEFAULTS
from ..db import db
from ..generator_support import (
    ORDER_PRODUCT_TYPES,
    RANDOM,
    bulk_insert,
    fetch_rows,
    make_code,
    maybe,
    quantize_money,
    random_datetime_between,
    reset_tables,
    split_amount,
)
from .base import BaseGenerator
from .validations import validate_layer6

POINTS_PER_CNY = 100
BOOKING_MAX_ADVANCE_DAYS = {
    "hotel_room": 120,
    "scenic_ticket": 30,
    "flight_cabin": 180,
    "train_seat": 45,
    "bus_seat": 15,
    "transfer_service": 30,
}
COMPLETION_MAX_LAG_DAYS = {
    "hotel_room": 3,
    "scenic_ticket": 2,
    "flight_cabin": 5,
    "train_seat": 3,
    "bus_seat": 2,
    "transfer_service": 2,
}
REFUND_MAX_LAG_DAYS = {
    "hotel_room": 7,
    "scenic_ticket": 3,
    "flight_cabin": 14,
    "train_seat": 7,
    "bus_seat": 3,
    "transfer_service": 3,
}
TRANSPORT_CURRENT_WINDOW_BUFFER_HOURS = 6


class Layer6Generator(BaseGenerator):
    layer = 6
    layer_name = "交易与资金"

    def run(self) -> None:
        self.header()
        reset_tables(
            "refund_records",
            "refund_requests",
            "payments",
            "order_point_usages",
            "order_promotion_details",
            "order_coupon_usages",
            "order_items",
            "orders",
        )
        self._generate_orders(self._load_context())
        self._sync_member_points_balance()
        checks = validate_layer6()
        for check in checks:
            self.log(f"  [OK] validation: {check}")

    def _load_context(self) -> dict:
        history_days = GENERATION_DEFAULTS["history_days"]
        users = fetch_rows(
            """
            SELECT u.id,
                   u.created_at AS user_created_at,
                   ma.created_at AS member_account_created_at,
                   COALESCE(ma.points_balance, 0) AS points_balance
            FROM users u
            LEFT JOIN member_accounts ma ON ma.user_id = u.id
            ORDER BY u.id
            """
        )
        return {
            "users": users,
            "user_points_balance": {
                row["id"]: int(row["points_balance"]) for row in users
            },
            "travelers_by_user": self._group_rows(
                fetch_rows(
                    "SELECT id, user_id, traveler_name, identity_no, phone FROM travelers"
                )
            ),
            "product_rows": self._load_product_rows(history_days),
            "coupons_by_user_type": self._group_coupon_rows(),
            "promotions_by_type": self._group_promotion_rows(),
            "next_ledger_id": self._next_ledger_id(),
        }

    def _orderable_product_rows(
        self, product_rows: dict[str, list[dict]], now: datetime
    ) -> dict[str, list[dict]]:
        orderable: dict[str, list[dict]] = {}
        for product_type, rows in product_rows.items():
            max_advance = BOOKING_MAX_ADVANCE_DAYS[product_type]
            latest_travel_at = now + timedelta(days=max_advance)
            filtered_rows: list[dict] = []
            for row in rows:
                travel_at = (
                    row["business_date"]
                    if isinstance(row["business_date"], datetime)
                    else datetime.combine(row["business_date"], datetime.min.time())
                )
                is_transport = product_type in {
                    "flight_cabin",
                    "train_seat",
                    "bus_seat",
                }
                is_cancelled = row.get("departure_status_code") == "cancelled"
                is_near_current_departure = (
                    now - timedelta(hours=2)
                    < travel_at
                    <= now + timedelta(hours=TRANSPORT_CURRENT_WINDOW_BUFFER_HOURS)
                )
                if is_transport and not is_cancelled and is_near_current_departure:
                    continue
                if travel_at <= latest_travel_at:
                    filtered_rows.append(row)
            orderable[product_type] = filtered_rows
        return orderable

    def _product_travel_at(self, product: dict) -> datetime:
        return (
            product["business_date"]
            if isinstance(product["business_date"], datetime)
            else datetime.combine(product["business_date"], datetime.min.time())
        )

    def _is_cancelled_transport_product(self, product: dict) -> bool:
        return product.get("departure_status_code") == "cancelled"

    def _can_user_order_product(
        self, product: dict, account_created_at: datetime
    ) -> bool:
        travel_at = self._product_travel_at(product)
        if travel_at < account_created_at:
            return False
        if not self._is_cancelled_transport_product(product):
            return True
        cancellation_at = product.get("departure_status_updated_at")
        product_type = product["product_type"]
        booking_window_start = travel_at - timedelta(
            days=BOOKING_MAX_ADVANCE_DAYS[product_type]
        )
        return (
            cancellation_at is not None
            and cancellation_at > account_created_at + timedelta(minutes=30)
            and cancellation_at > booking_window_start + timedelta(minutes=30)
        )

    def _choose_product(
        self, products: list[dict], account_created_at: datetime
    ) -> dict:
        for _ in range(20):
            product = RANDOM.choice(products)
            if self._can_user_order_product(product, account_created_at):
                return product
        candidates = [
            product
            for product in products
            if self._can_user_order_product(product, account_created_at)
        ]
        if not candidates:
            raise ValueError("No orderable product candidate for user and product type")
        return RANDOM.choice(candidates)

    def _load_product_rows(self, history_days: int) -> dict[str, list[dict]]:
        history_start = datetime.now().date() - timedelta(days=history_days)
        return {
            "hotel_room": fetch_rows(
                f"""
                SELECT d.room_type_id AS target_id, d.business_date,
                       d.sale_price_amount, d.settlement_price_amount,
                       'hotel_room' AS product_type,
                       t.room_type_name AS product_name
                FROM hotel_room_daily d
                JOIN hotel_room_types t ON t.id = d.room_type_id
                WHERE d.business_date >= '{history_start:%Y-%m-%d}'
                """
            ),
            "scenic_ticket": fetch_rows(
                f"""
                SELECT d.ticket_type_id AS target_id, d.business_date,
                       d.sale_price_amount, d.settlement_price_amount,
                       'scenic_ticket' AS product_type,
                       t.ticket_type_name AS product_name
                FROM scenic_ticket_daily d
                JOIN scenic_ticket_types t ON t.id = d.ticket_type_id
                WHERE d.business_date >= '{history_start:%Y-%m-%d}'
                """
            ),
            "flight_cabin": fetch_rows(
                f"""
                SELECT i.id AS target_id, dep.departure_time AS business_date,
                       i.sale_price_amount, i.settlement_price_amount,
                       'flight_cabin' AS product_type,
                       CONCAT(r.flight_no, '-', i.cabin_class_code) AS product_name,
                       dep.status_code AS departure_status_code,
                       dep.updated_at AS departure_status_updated_at
                FROM flight_cabin_inventory i
                JOIN flight_departures dep ON dep.id = i.flight_departure_id
                JOIN flight_routes r ON r.id = dep.flight_route_id
                WHERE DATE(dep.departure_time) >= '{history_start:%Y-%m-%d}'
                """
            ),
            "train_seat": fetch_rows(
                f"""
                SELECT i.id AS target_id, dep.departure_time AS business_date,
                       i.sale_price_amount, i.settlement_price_amount,
                       'train_seat' AS product_type,
                       CONCAT(r.train_no, '-', i.seat_class_code) AS product_name,
                       dep.status_code AS departure_status_code,
                       dep.updated_at AS departure_status_updated_at
                FROM train_seat_inventory i
                JOIN train_departures dep ON dep.id = i.train_departure_id
                JOIN train_routes r ON r.id = dep.train_route_id
                WHERE DATE(dep.departure_time) >= '{history_start:%Y-%m-%d}'
                """
            ),
            "bus_seat": fetch_rows(
                f"""
                SELECT i.id AS target_id, dep.departure_time AS business_date,
                       i.sale_price_amount, i.settlement_price_amount,
                       'bus_seat' AS product_type,
                       CONCAT(r.route_name, '-', i.seat_class_code) AS product_name,
                       dep.status_code AS departure_status_code,
                       dep.updated_at AS departure_status_updated_at
                FROM bus_seat_inventory i
                JOIN bus_departures dep ON dep.id = i.bus_departure_id
                JOIN bus_routes r ON r.id = dep.bus_route_id
                WHERE DATE(dep.departure_time) >= '{history_start:%Y-%m-%d}'
                """
            ),
            "transfer_service": fetch_rows(
                f"""
                SELECT c.transfer_service_id AS target_id,
                       c.business_date,
                       COALESCE(MIN(r.price_amount), 120.00) AS sale_price_amount,
                       COALESCE(MIN(r.min_price_amount), 90.00) AS settlement_price_amount,
                       'transfer_service' AS product_type,
                       s.service_name AS product_name
                FROM transfer_capacity_calendar c
                JOIN transfer_services s ON s.id = c.transfer_service_id
                LEFT JOIN transfer_service_area_rules r ON r.transfer_service_id = s.id
                WHERE c.business_date >= '{history_start:%Y-%m-%d}'
                GROUP BY c.transfer_service_id, c.business_date, s.service_name
                """
            ),
        }

    def _group_rows(self, rows: list[dict]) -> dict[int, list[dict]]:
        grouped: dict[int, list[dict]] = defaultdict(list)
        for row in rows:
            grouped[row["user_id"]].append(row)
        return grouped

    def _group_coupon_rows(self) -> dict[tuple[int, str], list[dict]]:
        grouped: dict[tuple[int, str], list[dict]] = defaultdict(list)
        rows = fetch_rows(
            """
            SELECT uc.id, uc.user_id, uc.template_id, uc.status_code,
                   ct.applicable_product_type, ct.coupon_type_code,
                   uc.min_spend_amount, uc.discount_amount, uc.max_discount_amount,
                   uc.valid_from, uc.valid_until, uc.created_at
            FROM user_coupons uc
            JOIN coupon_templates ct ON ct.id = uc.template_id
            WHERE uc.status_code IN ('available', 'expired')
            ORDER BY uc.id
            """
        )
        for row in rows:
            grouped[(row["user_id"], row["applicable_product_type"])].append(row)
        return grouped

    def _group_promotion_rows(self) -> dict[str, list[dict]]:
        grouped: dict[str, list[dict]] = defaultdict(list)
        rows = fetch_rows(
            """
            SELECT pb.id AS promotion_binding_id, pb.promotion_id, pb.product_type_code,
                   pb.target_id, pr.id AS promotion_rule_id, pr.benefit_type_code, pr.benefit_payload
            FROM promotion_bindings pb
            LEFT JOIN promotion_rules pr ON pr.promotion_id = pb.promotion_id
            ORDER BY pb.id, pr.id
            """
        )
        for row in rows:
            grouped[row["product_type_code"]].append(row)
        return grouped

    def _next_ledger_id(self) -> int:
        row = db.fetch_one(
            "SELECT COALESCE(MAX(id), 0) AS max_id FROM member_point_ledger"
        )
        max_id = 0 if row is None else int(row["max_id"])
        return max_id + 1

    def _coupon_discount_amount(self, coupon: dict, sale_amount: Decimal) -> Decimal:
        coupon_type = coupon["coupon_type_code"]
        discount_value = quantize_money(Decimal(str(coupon["discount_amount"])))
        max_discount = (
            quantize_money(Decimal(str(coupon["max_discount_amount"])))
            if coupon["max_discount_amount"] is not None
            else None
        )
        if coupon_type.endswith("_DISCOUNT"):
            amount = quantize_money(sale_amount * (Decimal("1.00") - discount_value))
            if max_discount is not None:
                amount = min(amount, max_discount)
            return max(Decimal("0.00"), amount)
        return min(sale_amount, discount_value)

    def _promotion_discount_amount(
        self, promotion: dict, sale_amount: Decimal
    ) -> Decimal:
        if not promotion["benefit_payload"]:
            return Decimal("0.00")
        payload = promotion["benefit_payload"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        if promotion["benefit_type_code"] == "discount_rate":
            rate = Decimal(str(payload.get("discount_rate", "0.90")))
            return quantize_money(sale_amount * (Decimal("1.00") - rate))
        return min(
            sale_amount, quantize_money(Decimal(str(payload.get("discount_amount", 0))))
        )

    def _requires_traveler(self, product_type: str) -> bool:
        return product_type in {"flight_cabin", "train_seat", "bus_seat"}

    def _booking_window_start(
        self,
        product_type: str,
        travel_at: datetime,
        account_created_at: datetime,
        now: datetime,
        history_days: int,
    ) -> datetime:
        max_advance_days = BOOKING_MAX_ADVANCE_DAYS[product_type]
        return max(
            now - timedelta(days=history_days),
            travel_at - timedelta(days=max_advance_days),
            account_created_at,
        )

    def _completion_deadline(
        self, product_type: str, travel_at: datetime, now: datetime
    ) -> datetime:
        return min(
            now, travel_at + timedelta(days=COMPLETION_MAX_LAG_DAYS[product_type])
        )

    def _refund_deadline(
        self, product_type: str, travel_at: datetime, now: datetime
    ) -> datetime:
        return min(now, travel_at + timedelta(days=REFUND_MAX_LAG_DAYS[product_type]))

    def _generate_orders(self, context: dict) -> None:
        batch_size = GENERATION_DEFAULTS["batch_size"]
        order_total = GENERATION_DEFAULTS["orders"]
        history_days = GENERATION_DEFAULTS["history_days"]
        now = datetime.now()
        counters = {
            "orders": 0,
            "order_items": 0,
            "order_coupon_usages": 0,
            "order_promotion_details": 0,
            "order_point_usages": 0,
            "payments": 0,
            "refund_requests": 0,
            "refund_records": 0,
            "member_point_ledger": 0,
        }

        orders: list[tuple] = []
        items: list[tuple] = []
        order_coupon_usages: list[tuple] = []
        order_promotion_details: list[tuple] = []
        order_point_usages: list[tuple] = []
        point_ledgers: list[tuple] = []
        payments: list[tuple] = []
        refund_requests: list[tuple] = []
        refund_record_specs: list[tuple] = []
        coupon_updates: list[tuple] = []

        consumed_coupon_ids: set[int] = set()
        user_point_balance = context["user_points_balance"]
        orderable_products = self._orderable_product_rows(context["product_rows"], now)

        for order_index in range(1, order_total + 1):
            user = context["users"][(order_index - 1) % len(context["users"])]
            user_id = user["id"]
            product_type = ORDER_PRODUCT_TYPES[
                (order_index - 1) % len(ORDER_PRODUCT_TYPES)
            ]
            account_created_at = (
                user["member_account_created_at"] or user["user_created_at"]
            )
            product = self._choose_product(
                orderable_products[product_type], account_created_at
            )
            travel_at = self._product_travel_at(product)
            is_cancelled_transport = self._is_cancelled_transport_product(product)
            cancellation_at = product.get("departure_status_updated_at")
            latest_created_at = min(
                now,
                travel_at - timedelta(minutes=30) if travel_at > now else travel_at,
            )
            if is_cancelled_transport and cancellation_at is not None:
                latest_created_at = min(
                    latest_created_at, cancellation_at - timedelta(minutes=10)
                )
            earliest_created_at = self._booking_window_start(
                product_type,
                travel_at,
                account_created_at,
                now,
                history_days,
            )
            if earliest_created_at > latest_created_at:
                earliest_created_at = latest_created_at
            created_at = random_datetime_between(earliest_created_at, latest_created_at)

            sale_amount = quantize_money(Decimal(str(product["sale_price_amount"])))
            base_settlement_amount = quantize_money(
                Decimal(str(product["settlement_price_amount"]))
            )
            travel_end_at = None
            lifecycle_anchor = travel_at
            if product_type == "hotel_room":
                stay_nights = RANDOM.randint(1, 3)
                travel_end_at = travel_at + timedelta(days=stay_nights)
                sale_amount = quantize_money(sale_amount * Decimal(stay_nights))
                base_settlement_amount = quantize_money(
                    base_settlement_amount * Decimal(stay_nights)
                )
                lifecycle_anchor = travel_end_at

            coupon_usage = None
            coupon_discount = Decimal("0.00")
            promotion_usage = None
            marketing_discount = Decimal("0.00")
            points_discount = Decimal("0.00")
            point_ledger_id = None
            points_used = 0

            payable_amount = max(
                Decimal("0.00"),
                sale_amount - marketing_discount - coupon_discount - points_discount,
            )
            status_code = "paid"
            paid_at = None
            finalized_at = None
            cancel_reason = None
            cancelled_at = None
            requested_at = None
            processed_at = None
            refunded_amount = None
            settlement_amount = None

            can_remain_pending = (
                order_index > order_total - batch_size
                and not is_cancelled_transport
                and latest_created_at >= datetime.now() - timedelta(minutes=30)
            )
            if can_remain_pending and maybe(0.05):
                pending_now = datetime.now()
                pending_earliest_at = max(
                    earliest_created_at,
                    pending_now - timedelta(minutes=30),
                )
                pending_latest_at = min(latest_created_at, pending_now)
                created_at = random_datetime_between(
                    pending_earliest_at, pending_latest_at
                )
                status_code = "pending_payment"
            elif maybe(0.07):
                status_code = "cancelled"
                cancel_reason = "库存释放或用户主动取消"
                cancelled_at = min(now, created_at + timedelta(minutes=10))
                finalized_at = cancelled_at
            else:
                coupon_candidates = [
                    row
                    for row in context["coupons_by_user_type"].get(
                        (user_id, product_type), []
                    )
                    if row["id"] not in consumed_coupon_ids
                    and row["created_at"] <= created_at
                    and row["valid_from"] <= created_at <= row["valid_until"]
                    and sale_amount
                    >= quantize_money(Decimal(str(row["min_spend_amount"])))
                ]
                if coupon_candidates and maybe(0.35):
                    coupon_usage = RANDOM.choice(coupon_candidates)
                    coupon_discount = self._coupon_discount_amount(
                        coupon_usage, sale_amount
                    )
                    consumed_coupon_ids.add(coupon_usage["id"])

                promotion_candidates = [
                    row
                    for row in context["promotions_by_type"].get(product_type, [])
                    if row["target_id"] == product["target_id"]
                ]
                if promotion_candidates and maybe(0.35):
                    promotion_usage = RANDOM.choice(promotion_candidates)
                    marketing_discount = self._promotion_discount_amount(
                        promotion_usage, sale_amount
                    )

                if maybe(0.25) and user_point_balance.get(user_id, 0) >= POINTS_PER_CNY:
                    max_deductible = min(
                        sale_amount - marketing_discount - coupon_discount,
                        quantize_money(
                            Decimal(user_point_balance[user_id])
                            / Decimal(POINTS_PER_CNY)
                        ),
                    )
                    if max_deductible > Decimal("0.00"):
                        points_discount = min(
                            max_deductible,
                            quantize_money(RANDOM.randint(1, 30)),
                        )
                        points_used = int(points_discount * POINTS_PER_CNY)
                        points_used = min(points_used, user_point_balance[user_id])
                        points_discount = quantize_money(
                            Decimal(points_used) / Decimal(POINTS_PER_CNY)
                        )
                        if points_used > 0:
                            point_ledger_id = context["next_ledger_id"]
                            context["next_ledger_id"] += 1
                            user_point_balance[user_id] -= points_used
                            point_ledgers.append(
                                (
                                    point_ledger_id,
                                    user_id,
                                    "point_redeem",
                                    -points_used,
                                    user_point_balance[user_id],
                                    created_at,
                                )
                            )

                payable_amount = max(
                    Decimal("0.00"),
                    sale_amount
                    - marketing_discount
                    - coupon_discount
                    - points_discount,
                )
                paid_at = min(
                    now,
                    created_at
                    + timedelta(
                        minutes=RANDOM.randint(3, 120), seconds=RANDOM.randint(0, 59)
                    ),
                )
                if is_cancelled_transport:
                    status_code = "refunded"
                    if cancellation_at is not None:
                        paid_at = min(paid_at, cancellation_at - timedelta(minutes=1))
                    if paid_at <= created_at:
                        paid_at = created_at + timedelta(minutes=RANDOM.randint(3, 30))
                    refunded_amount = payable_amount
                    settlement_amount = Decimal("0.00")
                    requested_start = max(paid_at, cancellation_at or paid_at)
                    requested_at = random_datetime_between(
                        requested_start,
                        min(now, requested_start + timedelta(hours=12)),
                    )
                    processed_at = random_datetime_between(
                        requested_at,
                        min(now, requested_at + timedelta(days=2)),
                    )
                    finalized_at = processed_at
                elif lifecycle_anchor <= now - timedelta(hours=2):
                    if maybe(0.09):
                        status_code = "refunded"
                        refunded_amount = split_amount(
                            payable_amount
                            if payable_amount > Decimal("0.00")
                            else sale_amount,
                            RANDOM.uniform(0.3, 1.0),
                        )
                        refund_ratio = (
                            refunded_amount / payable_amount
                            if payable_amount > Decimal("0.00")
                            else Decimal("1.00")
                        )
                        settlement_amount = quantize_money(
                            max(
                                Decimal("0.00"),
                                base_settlement_amount
                                * (Decimal("1.00") - refund_ratio),
                            )
                        )
                        refund_deadline = self._refund_deadline(
                            product_type, lifecycle_anchor, now
                        )
                        requested_at = random_datetime_between(
                            paid_at,
                            max(paid_at, refund_deadline - timedelta(hours=12)),
                        )
                        processed_at = random_datetime_between(
                            requested_at,
                            max(requested_at, refund_deadline),
                        )
                        finalized_at = processed_at
                    else:
                        status_code = "completed"
                        settlement_amount = base_settlement_amount
                        completion_deadline = self._completion_deadline(
                            product_type, lifecycle_anchor, now
                        )
                        finalized_at = random_datetime_between(
                            max(paid_at, lifecycle_anchor + timedelta(hours=2)),
                            max(
                                max(paid_at, lifecycle_anchor + timedelta(hours=2)),
                                completion_deadline,
                            ),
                        )
                elif product_type in {
                    "flight_cabin",
                    "train_seat",
                    "bus_seat",
                } and maybe(0.55):
                    status_code = "ticketed"

            order_updated_at = (
                processed_at or finalized_at or cancelled_at or paid_at or created_at
            )
            if status_code == "cancelled":
                order_status_code = "cancelled"
            elif status_code == "pending_payment":
                order_status_code = "pending_payment"
            elif status_code in {"completed", "refunded"}:
                order_status_code = "finished"
            elif status_code == "ticketed":
                order_status_code = "in_progress"
            else:
                order_status_code = "paid"

            traveler_options = context["travelers_by_user"].get(user_id, [])
            selected_traveler = (
                RANDOM.choice(traveler_options) if traveler_options else None
            )
            traveler_id = (
                selected_traveler["id"]
                if selected_traveler
                and (self._requires_traveler(product_type) or maybe(0.5))
                else None
            )

            item_completed_at = finalized_at if status_code == "completed" else None
            item_refunded_at = processed_at if status_code == "refunded" else None

            orders.append(
                (
                    make_code("ORD", order_index, 10),
                    user_id,
                    product_type,
                    order_status_code,
                    "CNY",
                    sale_amount,
                    marketing_discount,
                    coupon_discount,
                    points_discount,
                    payable_amount,
                    payable_amount if paid_at else None,
                    refunded_amount,
                    settlement_amount,
                    RANDOM.choice(["app", "web", "miniapp"]),
                    cancel_reason,
                    paid_at,
                    finalized_at,
                    created_at,
                    order_updated_at,
                )
            )
            items.append(
                (
                    order_index,
                    user_id,
                    traveler_id,
                    product_type,
                    product["target_id"],
                    product["product_name"],
                    sale_amount,
                    refunded_amount,
                    settlement_amount,
                    status_code,
                    travel_at,
                    travel_end_at,
                    cancelled_at,
                    paid_at,
                    item_refunded_at,
                    item_completed_at,
                    created_at,
                    order_updated_at,
                )
            )
            if coupon_usage and coupon_discount > Decimal("0.00"):
                order_coupon_usages.append(
                    (
                        order_index,
                        order_index,
                        user_id,
                        coupon_usage["template_id"],
                        coupon_usage["id"],
                        product_type,
                        coupon_discount,
                        created_at,
                        order_updated_at,
                    )
                )
                coupon_updates.append(
                    (paid_at or created_at, order_updated_at, coupon_usage["id"])
                )
            if promotion_usage and marketing_discount > Decimal("0.00"):
                order_promotion_details.append(
                    (
                        order_index,
                        order_index,
                        product_type,
                        promotion_usage["promotion_id"],
                        promotion_usage["promotion_binding_id"],
                        promotion_usage["promotion_rule_id"],
                        marketing_discount,
                        created_at,
                        order_updated_at,
                    )
                )
            if point_ledger_id is not None and points_discount > Decimal("0.00"):
                order_point_usages.append(
                    (
                        order_index,
                        user_id,
                        point_ledger_id,
                        points_used,
                        points_discount,
                        created_at,
                        order_updated_at,
                    )
                )
            if paid_at:
                payment_created_at = min(created_at + timedelta(minutes=1), paid_at)
                payment_no = make_code("PAY", order_index, 10)
                payments.append(
                    (
                        payment_no,
                        order_index,
                        user_id,
                        RANDOM.choice(["alipay", "wechat", "unionpay"]),
                        "CNY",
                        payable_amount,
                        "success",
                        paid_at,
                        payment_created_at,
                        paid_at,
                    )
                )
                if status_code == "refunded":
                    refund_request_no = make_code("RFDQ", order_index, 10)
                    refund_requests.append(
                        (
                            refund_request_no,
                            order_index,
                            order_index,
                            user_id,
                            refunded_amount,
                            refunded_amount,
                            "success",
                            requested_at,
                            processed_at,
                            requested_at,
                            processed_at,
                        )
                    )
                    refund_record_specs.append(
                        (
                            make_code("RFDR", order_index, 10),
                            refund_request_no,
                            order_index,
                            order_index,
                            user_id,
                            payment_no,
                            "CNY",
                            refunded_amount,
                            "success",
                            processed_at,
                            requested_at,
                            processed_at,
                        )
                    )

            if len(orders) >= batch_size:
                self._flush_batch(
                    orders,
                    items,
                    order_coupon_usages,
                    order_promotion_details,
                    point_ledgers,
                    order_point_usages,
                    payments,
                    refund_requests,
                    refund_record_specs,
                    coupon_updates,
                    counters,
                )

        self._flush_batch(
            orders,
            items,
            order_coupon_usages,
            order_promotion_details,
            point_ledgers,
            order_point_usages,
            payments,
            refund_requests,
            refund_record_specs,
            coupon_updates,
            counters,
        )
        self.log_table_counts(counters)

    def _flush_batch(
        self,
        orders: list[tuple],
        items: list[tuple],
        order_coupon_usages: list[tuple],
        order_promotion_details: list[tuple],
        point_ledgers: list[tuple],
        order_point_usages: list[tuple],
        payments: list[tuple],
        refund_requests: list[tuple],
        refund_record_specs: list[tuple],
        coupon_updates: list[tuple],
        counters: dict[str, int],
    ) -> None:
        if not orders:
            return
        counters["orders"] += bulk_insert(
            """
            INSERT INTO orders (
                order_no, user_id, order_type_code, status_code, currency_code, goods_amount,
                marketing_discount_amount, coupon_discount_amount, point_discount_amount,
                payable_amount, paid_amount, refunded_amount, settlement_amount,
                source_channel_code, cancel_reason, paid_at, finalized_at, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            orders,
            finalize=False,
        )
        counters["order_items"] += bulk_insert(
            """
            INSERT INTO order_items (
                order_id, user_id, traveler_id, product_type_code, product_id, product_name,
                sale_amount, refunded_amount, settlement_amount, status_code, travel_time,
                travel_end_time, cancelled_at, paid_at, refunded_at, completed_at, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            items,
            finalize=False,
        )
        if point_ledgers:
            counters["member_point_ledger"] += bulk_insert(
                """
                INSERT INTO member_point_ledger (
                    id, user_id, ledger_type_code, points_delta, balance_after, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s)
                """,
                point_ledgers,
                finalize=False,
            )
        if order_coupon_usages:
            counters["order_coupon_usages"] += bulk_insert(
                """
                INSERT INTO order_coupon_usages (
                    order_id, order_item_id, user_id, template_id, user_coupon_id,
                    order_type_code, discount_amount, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                order_coupon_usages,
                finalize=False,
            )
        if order_promotion_details:
            counters["order_promotion_details"] += bulk_insert(
                """
                INSERT INTO order_promotion_details (
                    order_id, order_item_id, order_type_code, promotion_id,
                    promotion_binding_id, promotion_rule_id, discount_amount, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                order_promotion_details,
                finalize=False,
            )
        if order_point_usages:
            counters["order_point_usages"] += bulk_insert(
                """
                INSERT INTO order_point_usages (
                    order_id, user_id, point_ledger_id, points_used, discount_amount, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                order_point_usages,
                finalize=False,
            )
        payment_id_by_no: dict[str, int] = {}
        if payments:
            counters["payments"] += bulk_insert(
                """
                INSERT INTO payments (
                    payment_no, order_id, user_id, payment_method_code, currency_code,
                    amount, status_code, paid_at, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                payments,
                finalize=False,
            )
            payment_nos = [row[0] for row in payments]
            placeholder = ", ".join(["%s"] * len(payment_nos))
            payment_rows = db.fetch_all(
                f"SELECT id, payment_no FROM payments WHERE payment_no IN ({placeholder})",
                payment_nos,
            )
            payment_id_by_no = {row["payment_no"]: row["id"] for row in payment_rows}
        if refund_requests:
            counters["refund_requests"] += bulk_insert(
                """
                INSERT INTO refund_requests (
                    refund_request_no, order_id, order_item_id, user_id,
                    requested_amount, approved_amount, status_code, requested_at,
                    processed_at, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                refund_requests,
                finalize=False,
            )
            request_nos = [row[0] for row in refund_requests]
            placeholder = ", ".join(["%s"] * len(request_nos))
            request_rows = db.fetch_all(
                f"SELECT id, refund_request_no FROM refund_requests WHERE refund_request_no IN ({placeholder})",
                request_nos,
            )
            request_id_by_no = {
                row["refund_request_no"]: row["id"] for row in request_rows
            }
            refund_records = [
                (
                    refund_no,
                    request_id_by_no[refund_request_no],
                    order_id,
                    order_item_id,
                    user_id,
                    payment_id_by_no[payment_no],
                    currency_code,
                    amount,
                    status_code,
                    processed_at,
                    created_at,
                    updated_at,
                )
                for (
                    refund_no,
                    refund_request_no,
                    order_id,
                    order_item_id,
                    user_id,
                    payment_no,
                    currency_code,
                    amount,
                    status_code,
                    processed_at,
                    created_at,
                    updated_at,
                ) in refund_record_specs
            ]
            counters["refund_records"] += bulk_insert(
                """
                INSERT INTO refund_records (
                    refund_no, refund_request_id, order_id, order_item_id, user_id, payment_id,
                    currency_code, amount, status_code, processed_at, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                refund_records,
                finalize=False,
            )
        if coupon_updates:
            db.executemany(
                """
                UPDATE user_coupons
                SET status_code = 'used', used_at = %s, updated_at = %s
                WHERE id = %s
                """,
                coupon_updates,
            )
        orders.clear()
        items.clear()
        order_coupon_usages.clear()
        order_promotion_details.clear()
        point_ledgers.clear()
        order_point_usages.clear()
        payments.clear()
        refund_requests.clear()
        refund_record_specs.clear()
        coupon_updates.clear()

    def _sync_member_points_balance(self) -> None:
        db.execute(
            """
            UPDATE member_accounts a
            JOIN (
                SELECT l.user_id, l.balance_after
                FROM member_point_ledger l
                JOIN (
                    SELECT user_id, MAX(id) AS max_id
                    FROM member_point_ledger
                    GROUP BY user_id
                ) latest
                  ON latest.user_id = l.user_id
                 AND latest.max_id = l.id
            ) ledger ON ledger.user_id = a.user_id
            SET a.points_balance = ledger.balance_after,
                a.updated_at = GREATEST(a.updated_at, %s)
            """,
            (datetime.now(),),
        )
