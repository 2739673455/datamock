"""Layer-level validation helpers."""

from datetime import datetime

from ..config import LAYERS
from ..db import db


def _scalar_int(sql: str, params: tuple | None = None) -> int:
    row = db.fetch_one(sql, params)
    if not row:
        return 0
    return int(next(iter(row.values())))


def _assert_zero(label: str, sql: str, params: tuple | None = None) -> None:
    count = _scalar_int(sql, params)
    if count != 0:
        raise ValueError(f"{label}: expected 0, got {count}")


def _assert_positive(label: str, sql: str, params: tuple | None = None) -> None:
    count = _scalar_int(sql, params)
    if count <= 0:
        raise ValueError(f"{label}: expected > 0, got {count}")


def _local_now_sql() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def validate_layer1() -> list[str]:
    checks: list[str] = []

    _assert_zero(
        "areas level/parent relationship",
        """
        SELECT COUNT(*) AS count
        FROM areas a
        LEFT JOIN areas p ON p.id = a.parent_id
        WHERE (a.level = 1 AND a.parent_id IS NOT NULL)
           OR (a.level > 1 AND a.parent_id IS NULL)
           OR (a.level > 1 AND (p.id IS NULL OR p.level >= a.level))
        """,
    )
    checks.append("areas hierarchy")

    _assert_zero(
        "transport_hubs city area level",
        """
        SELECT COUNT(*) AS count
        FROM transport_hubs h
        JOIN areas a ON a.id = h.city_area_id
        WHERE a.level <> 2
        """,
    )
    checks.append("transport_hubs city linkage")

    for supplier_type in ("hotel", "scenic", "flight", "train", "bus", "transfer"):
        _assert_positive(
            f"suppliers coverage for {supplier_type}",
            "SELECT COUNT(*) AS count FROM suppliers WHERE supplier_type_code = %s",
            (supplier_type,),
        )
    checks.append("supplier type coverage")

    return checks


def validate_layer2() -> list[str]:
    checks: list[str] = []

    _assert_positive("hotels rows", "SELECT COUNT(*) AS count FROM hotels")
    _assert_positive(
        "hotel_room_types rows", "SELECT COUNT(*) AS count FROM hotel_room_types"
    )
    _assert_positive(
        "hotel_booking_rules rows", "SELECT COUNT(*) AS count FROM hotel_booking_rules"
    )
    _assert_zero(
        "hotels area/supplier relationship",
        """
        SELECT COUNT(*) AS count
        FROM hotels h
        JOIN areas a ON a.id = h.area_id
        JOIN suppliers s ON s.id = h.supplier_id
        WHERE a.level <> 2 OR s.supplier_type_code <> 'hotel'
        """,
    )
    _assert_zero(
        "hotel room type category/name mapping",
        """
        SELECT COUNT(*) AS count
        FROM hotel_room_types
        WHERE (room_type_category_code = 'double' AND room_type_name <> '大床房')
           OR (room_type_category_code = 'twin' AND room_type_name <> '双床房')
           OR (room_type_category_code = 'suite' AND room_type_name <> '套房')
           OR (room_type_category_code = 'family' AND room_type_name <> '家庭房')
        """,
    )
    _assert_zero(
        "hotel booking rules one-to-one completeness",
        """
        SELECT COUNT(*) AS count
        FROM hotels h
        LEFT JOIN hotel_booking_rules r ON r.hotel_id = h.id
        WHERE r.id IS NULL
        """,
    )
    checks.append("hotel domain")

    _assert_positive("scenic_spots rows", "SELECT COUNT(*) AS count FROM scenic_spots")
    _assert_positive(
        "scenic_ticket_types rows", "SELECT COUNT(*) AS count FROM scenic_ticket_types"
    )
    _assert_positive(
        "scenic_booking_rules rows",
        "SELECT COUNT(*) AS count FROM scenic_booking_rules",
    )
    _assert_zero(
        "scenic area/supplier relationship",
        """
        SELECT COUNT(*) AS count
        FROM scenic_spots s
        JOIN areas a ON a.id = s.area_id
        JOIN suppliers sp ON sp.id = s.supplier_id
        WHERE a.level <> 2 OR sp.supplier_type_code <> 'scenic'
        """,
    )
    _assert_zero(
        "scenic ticket category/name mapping",
        """
        SELECT COUNT(*) AS count
        FROM scenic_ticket_types
        WHERE (ticket_category_code = 'adult' AND ticket_type_name <> '成人票')
           OR (ticket_category_code = 'student' AND ticket_type_name <> '学生票')
           OR (ticket_category_code = 'family' AND ticket_type_name <> '家庭票')
           OR (ticket_category_code = 'night' AND ticket_type_name <> '夜场票')
        """,
    )
    _assert_zero(
        "scenic booking rules one-to-one completeness",
        """
        SELECT COUNT(*) AS count
        FROM scenic_spots s
        LEFT JOIN scenic_booking_rules r ON r.scenic_spot_id = s.id
        WHERE r.id IS NULL
        """,
    )
    checks.append("scenic domain")

    _assert_positive(
        "flight_routes rows", "SELECT COUNT(*) AS count FROM flight_routes"
    )
    _assert_positive("train_routes rows", "SELECT COUNT(*) AS count FROM train_routes")
    _assert_positive("bus_routes rows", "SELECT COUNT(*) AS count FROM bus_routes")
    _assert_zero(
        "flight route hub/city/supplier relationship",
        """
        SELECT COUNT(*) AS count
        FROM flight_routes r
        JOIN transport_hubs dh ON dh.id = r.departure_hub_id
        JOIN transport_hubs ah ON ah.id = r.arrival_hub_id
        JOIN suppliers s ON s.id = r.supplier_id
        JOIN areas da ON da.id = r.departure_area_id
        JOIN areas aa ON aa.id = r.arrival_area_id
        WHERE dh.hub_type_code <> 'airport'
           OR ah.hub_type_code <> 'airport'
           OR dh.city_area_id <> r.departure_area_id
           OR ah.city_area_id <> r.arrival_area_id
           OR da.level <> 2
           OR aa.level <> 2
           OR s.supplier_type_code <> 'flight'
           OR r.departure_area_id = r.arrival_area_id
        """,
    )
    _assert_zero(
        "train route hub/city/supplier relationship",
        """
        SELECT COUNT(*) AS count
        FROM train_routes r
        JOIN transport_hubs dh ON dh.id = r.departure_hub_id
        JOIN transport_hubs ah ON ah.id = r.arrival_hub_id
        JOIN suppliers s ON s.id = r.supplier_id
        JOIN areas da ON da.id = r.departure_area_id
        JOIN areas aa ON aa.id = r.arrival_area_id
        WHERE dh.hub_type_code <> 'railway_station'
           OR ah.hub_type_code <> 'railway_station'
           OR dh.city_area_id <> r.departure_area_id
           OR ah.city_area_id <> r.arrival_area_id
           OR da.level <> 2
           OR aa.level <> 2
           OR s.supplier_type_code <> 'train'
           OR r.departure_area_id = r.arrival_area_id
        """,
    )
    _assert_zero(
        "bus route hub/city/supplier relationship",
        """
        SELECT COUNT(*) AS count
        FROM bus_routes r
        JOIN transport_hubs dh ON dh.id = r.departure_hub_id
        JOIN transport_hubs ah ON ah.id = r.arrival_hub_id
        JOIN suppliers s ON s.id = r.supplier_id
        JOIN areas da ON da.id = r.departure_area_id
        JOIN areas aa ON aa.id = r.arrival_area_id
        WHERE dh.hub_type_code <> 'bus_station'
           OR ah.hub_type_code <> 'bus_station'
           OR dh.city_area_id <> r.departure_area_id
           OR ah.city_area_id <> r.arrival_area_id
           OR da.level <> 2
           OR aa.level <> 2
           OR s.supplier_type_code <> 'bus'
           OR r.departure_area_id = r.arrival_area_id
        """,
    )
    checks.append("transport domain")

    _assert_positive(
        "transfer_services rows", "SELECT COUNT(*) AS count FROM transfer_services"
    )
    _assert_positive(
        "transfer_service_area_rules rows",
        "SELECT COUNT(*) AS count FROM transfer_service_area_rules",
    )
    _assert_zero(
        "transfer service area/supplier relationship",
        """
        SELECT COUNT(*) AS count
        FROM transfer_services s
        JOIN areas a ON a.id = s.area_id
        JOIN suppliers sp ON sp.id = s.supplier_id
        WHERE a.level <> 2 OR sp.supplier_type_code <> 'transfer'
        """,
    )
    _assert_zero(
        "transfer service area rules constraints",
        """
        SELECT COUNT(*) AS count
        FROM transfer_service_area_rules r
        JOIN areas pa ON pa.id = r.pickup_area_id
        JOIN areas da ON da.id = r.dropoff_area_id
        WHERE r.price_amount < r.min_price_amount
           OR r.min_price_amount < 0
           OR pa.level <> 2
           OR da.level <> 2
        """,
    )
    checks.append("transfer domain")

    return checks


def validate_layer3() -> list[str]:
    checks: list[str] = []
    local_now = _local_now_sql()

    for table in (
        "hotel_room_daily",
        "scenic_ticket_daily",
        "flight_cabin_inventory",
        "train_seat_inventory",
        "bus_seat_inventory",
        "transfer_capacity_calendar",
    ):
        _assert_zero(
            f"{table} inventory balance",
            f"""
            SELECT COUNT(*) AS count
            FROM {table}
            WHERE available_inventory + reserved_inventory + sold_inventory <> total_inventory
            """,
        )

    for table in (
        "hotel_room_daily",
        "scenic_ticket_daily",
        "flight_cabin_inventory",
        "train_seat_inventory",
        "bus_seat_inventory",
    ):
        _assert_zero(
            f"{table} price relationship",
            f"""
            SELECT COUNT(*) AS count
            FROM {table}
            WHERE settlement_price_amount > sale_price_amount
            """,
        )
    checks.append("inventory and price constraints")

    _assert_zero(
        "hotel_room_daily business date timing",
        """
        SELECT COUNT(*) AS count
        FROM hotel_room_daily
        WHERE business_date < DATE(created_at)
        """,
    )
    _assert_zero(
        "scenic_ticket_daily business date timing",
        """
        SELECT COUNT(*) AS count
        FROM scenic_ticket_daily
        WHERE business_date < DATE(created_at)
        """,
    )
    _assert_zero(
        "transfer_capacity_calendar business date timing",
        """
        SELECT COUNT(*) AS count
        FROM transfer_capacity_calendar
        WHERE business_date < DATE(created_at)
        """,
    )
    checks.append("daily calendar timing")

    for table in ("flight_departures", "train_departures", "bus_departures"):
        _assert_zero(
            f"{table} departure/arrival order",
            f"""
            SELECT COUNT(*) AS count
            FROM {table}
            WHERE arrival_time <= departure_time OR departure_time <= created_at
            """,
        )
        _assert_zero(
            f"{table} stale scheduled status",
            f"""
            SELECT COUNT(*) AS count
            FROM {table}
            WHERE status_code = 'scheduled'
              AND arrival_time < TIMESTAMP('{local_now}') - INTERVAL 12 HOUR
            """,
        )
        _assert_zero(
            f"{table} future done status",
            f"""
            SELECT COUNT(*) AS count
            FROM {table}
            WHERE status_code = 'done'
              AND arrival_time > TIMESTAMP('{local_now}')
            """,
        )
        _assert_zero(
            f"{table} invalid status",
            f"""
            SELECT COUNT(*) AS count
            FROM {table}
            WHERE status_code NOT IN ('scheduled', 'cancelled', 'done')
            """,
        )
        _assert_zero(
            f"{table} cancellation timing",
            f"""
            SELECT COUNT(*) AS count
            FROM {table}
            WHERE status_code = 'cancelled'
              AND (updated_at > departure_time OR updated_at > TIMESTAMP('{local_now}'))
            """,
        )
    checks.append("departure timing")

    for table, fk in (
        ("flight_cabin_inventory", "flight_departure_id"),
        ("train_seat_inventory", "train_departure_id"),
        ("bus_seat_inventory", "bus_departure_id"),
    ):
        departure_table = table.replace("_inventory", "s")
        if table == "flight_cabin_inventory":
            departure_table = "flight_departures"
        elif table == "train_seat_inventory":
            departure_table = "train_departures"
        elif table == "bus_seat_inventory":
            departure_table = "bus_departures"
        _assert_zero(
            f"{table} created before departure",
            f"""
            SELECT COUNT(*) AS count
            FROM {table} i
            JOIN {departure_table} d ON d.id = i.{fk}
            WHERE i.created_at > d.departure_time
            """,
        )
    checks.append("inventory timing")

    return checks


def validate_layer4() -> list[str]:
    checks: list[str] = []

    _assert_zero(
        "users register area level",
        """
        SELECT COUNT(*) AS count
        FROM users u
        JOIN areas a ON a.id = u.register_area_id
        WHERE a.level <> 2 OR u.updated_at < u.created_at
        """,
    )
    checks.append("users")

    _assert_zero(
        "user_profiles one-to-one completeness",
        """
        SELECT COUNT(*) AS count
        FROM users u
        LEFT JOIN user_profiles p ON p.user_id = u.id
        WHERE p.id IS NULL OR p.created_at < u.created_at OR p.updated_at < p.created_at
        """,
    )
    checks.append("user profiles")

    _assert_zero(
        "travelers timing and status",
        """
        SELECT COUNT(*) AS count
        FROM travelers t
        JOIN users u ON u.id = t.user_id
        WHERE t.created_at < u.created_at OR t.updated_at < t.created_at
        """,
    )
    _assert_zero(
        "users without travelers",
        """
        SELECT COUNT(*) AS count
        FROM users u
        LEFT JOIN travelers t ON t.user_id = u.id
        WHERE t.id IS NULL
        """,
    )
    _assert_zero(
        "users without self traveler",
        """
        SELECT COUNT(*) AS count
        FROM users u
        JOIN user_profiles p ON p.user_id = u.id
        LEFT JOIN travelers t
          ON t.user_id = u.id
         AND t.identity_type_code = p.identity_type_code
         AND t.identity_no = p.identity_no
        WHERE t.id IS NULL
        """,
    )
    checks.append("travelers")

    _assert_zero(
        "member accounts one-to-one and level mapping",
        """
        SELECT COUNT(*) AS count
        FROM member_accounts a
        WHERE (a.member_level_code = 'normal' AND a.growth_value >= 5000)
           OR (a.member_level_code = 'silver' AND (a.growth_value < 5000 OR a.growth_value >= 12000))
           OR (a.member_level_code = 'gold' AND a.growth_value < 12000)
           OR a.updated_at < a.created_at
        """,
    )
    _assert_zero(
        "users without member accounts",
        """
        SELECT COUNT(*) AS count
        FROM users u
        LEFT JOIN member_accounts a ON a.user_id = u.id
        WHERE a.id IS NULL
        """,
    )
    checks.append("member accounts")

    _assert_zero(
        "member point ledger zero delta",
        """
        SELECT COUNT(*) AS count
        FROM member_point_ledger
        WHERE points_delta = 0
        """,
    )
    _assert_zero(
        "member point ledger signup timing",
        """
        SELECT COUNT(*) AS count
        FROM member_point_ledger l
        JOIN member_accounts a ON a.user_id = l.user_id
        WHERE l.ledger_type_code = 'signup_bonus'
          AND l.created_at < a.created_at
        """,
    )
    _assert_zero(
        "member point ledger/account balance mismatch",
        """
        SELECT COUNT(*) AS count
        FROM member_accounts a
        JOIN (
            SELECT l.user_id, l.balance_after
            FROM member_point_ledger l
            JOIN (
                SELECT user_id, MAX(created_at) AS max_created_at, MAX(id) AS max_id
                FROM member_point_ledger
                GROUP BY user_id
            ) last_row
              ON last_row.user_id = l.user_id
             AND last_row.max_created_at = l.created_at
             AND last_row.max_id = l.id
        ) last_ledger ON last_ledger.user_id = a.user_id
        WHERE last_ledger.balance_after <> a.points_balance
        """,
    )
    checks.append("member point ledger")

    return checks


def validate_layer5() -> list[str]:
    checks: list[str] = []

    _assert_positive(
        "coupon templates rows", "SELECT COUNT(*) AS count FROM coupon_templates"
    )
    _assert_zero(
        "coupon template discount rules",
        """
        SELECT COUNT(*) AS count
        FROM coupon_templates
        WHERE (coupon_type_code LIKE '%_CASH' AND (discount_amount <= 0 OR max_discount_amount IS NOT NULL))
           OR (coupon_type_code LIKE '%_DISCOUNT' AND (discount_amount <= 0 OR discount_amount >= 1 OR max_discount_amount IS NULL))
           OR valid_from >= valid_until
           OR updated_at < created_at
        """,
    )
    checks.append("coupon templates")

    _assert_positive("user coupons rows", "SELECT COUNT(*) AS count FROM user_coupons")
    _assert_zero(
        "user coupon status and timing",
        """
        SELECT COUNT(*) AS count
        FROM user_coupons
        WHERE created_at > updated_at
           OR created_at > valid_until
           OR (status_code = 'used' AND (used_at IS NULL OR used_at < created_at OR used_at < valid_from OR used_at > valid_until))
           OR (status_code <> 'used' AND used_at IS NOT NULL)
           OR status_code NOT IN ('available', 'used', 'expired')
        """,
    )
    checks.append("user coupons")

    _assert_positive("promotions rows", "SELECT COUNT(*) AS count FROM promotions")
    _assert_positive(
        "promotion rules rows", "SELECT COUNT(*) AS count FROM promotion_rules"
    )
    _assert_positive(
        "promotion bindings rows", "SELECT COUNT(*) AS count FROM promotion_bindings"
    )
    _assert_zero(
        "promotions timing",
        """
        SELECT COUNT(*) AS count
        FROM promotions
        WHERE start_time >= end_time OR updated_at < created_at
        """,
    )
    _assert_zero(
        "promotion rules timing",
        """
        SELECT COUNT(*) AS count
        FROM promotion_rules
        WHERE updated_at < created_at
        """,
    )
    checks.append("promotions and rules")

    _assert_zero(
        "promotion binding targets",
        """
        SELECT COUNT(*) AS count
        FROM promotion_bindings pb
        LEFT JOIN hotel_room_types hrt
          ON pb.product_type_code = 'hotel_room' AND hrt.id = pb.target_id
        LEFT JOIN scenic_ticket_types stt
          ON pb.product_type_code = 'scenic_ticket' AND stt.id = pb.target_id
        LEFT JOIN flight_cabin_inventory fci
          ON pb.product_type_code = 'flight_cabin' AND fci.id = pb.target_id
        LEFT JOIN train_seat_inventory tsi
          ON pb.product_type_code = 'train_seat' AND tsi.id = pb.target_id
        LEFT JOIN bus_seat_inventory bsi
          ON pb.product_type_code = 'bus_seat' AND bsi.id = pb.target_id
        LEFT JOIN transfer_services ts
          ON pb.product_type_code = 'transfer_service' AND ts.id = pb.target_id
        WHERE (pb.product_type_code = 'hotel_room' AND hrt.id IS NULL)
           OR (pb.product_type_code = 'scenic_ticket' AND stt.id IS NULL)
           OR (pb.product_type_code = 'flight_cabin' AND fci.id IS NULL)
           OR (pb.product_type_code = 'train_seat' AND tsi.id IS NULL)
           OR (pb.product_type_code = 'bus_seat' AND bsi.id IS NULL)
           OR (pb.product_type_code = 'transfer_service' AND ts.id IS NULL)
        """,
    )
    checks.append("promotion bindings")

    return checks


def validate_layer6() -> list[str]:
    checks: list[str] = []
    local_now = _local_now_sql()

    _assert_positive("orders rows", "SELECT COUNT(*) AS count FROM orders")
    _assert_positive("order items rows", "SELECT COUNT(*) AS count FROM order_items")
    _assert_zero(
        "orders amount and status constraints",
        f"""
        SELECT COUNT(*) AS count
        FROM orders o
        WHERE o.goods_amount <> o.marketing_discount_amount + o.coupon_discount_amount + o.point_discount_amount + o.payable_amount
           OR o.payable_amount < 0
           OR o.updated_at < o.created_at
           OR (
                o.status_code = 'pending_payment'
                AND EXISTS (
                    SELECT 1
                    FROM payments p
                    WHERE p.order_id = o.id
                      AND p.status_code = 'pending'
                    GROUP BY p.order_id
                    HAVING MAX(p.created_at) < TIMESTAMP('{local_now}') - INTERVAL 15 MINUTE
                )
              )
           OR (o.status_code = 'pending_payment' AND (o.paid_at IS NOT NULL OR o.paid_amount IS NOT NULL OR o.finalized_at IS NOT NULL))
           OR (o.status_code = 'cancelled' AND (o.paid_at IS NOT NULL OR o.paid_amount IS NOT NULL OR o.finalized_at IS NULL OR o.finalized_at < o.created_at))
           OR (o.status_code = 'paid' AND (o.paid_at IS NULL OR o.paid_amount IS NULL OR o.finalized_at IS NOT NULL))
           OR (o.status_code = 'in_progress' AND (o.paid_at IS NULL OR o.paid_amount IS NULL OR o.finalized_at IS NOT NULL))
           OR (o.status_code = 'finished' AND (o.paid_at IS NULL OR o.paid_amount IS NULL OR o.finalized_at IS NULL OR o.settlement_amount IS NULL))
        """,
    )
    checks.append("orders")

    _assert_zero(
        "order items status, traveler and timing constraints",
        f"""
        SELECT COUNT(*) AS count
        FROM order_items oi
        JOIN orders o ON o.id = oi.order_id
        WHERE oi.updated_at < oi.created_at
           OR oi.created_at < o.created_at
           OR oi.user_id <> o.user_id
           OR oi.product_type_code <> o.order_type_code
           OR oi.travel_time < o.created_at
           OR (oi.product_type_code = 'hotel_room' AND (oi.travel_end_time IS NULL OR oi.travel_end_time <= oi.travel_time))
           OR (oi.product_type_code <> 'hotel_room' AND oi.travel_end_time IS NOT NULL)
           OR (
                oi.status_code = 'pending_payment'
                AND EXISTS (
                    SELECT 1
                    FROM payments p
                    WHERE p.order_id = oi.order_id
                      AND p.status_code = 'pending'
                    GROUP BY p.order_id
                    HAVING MAX(p.created_at) < TIMESTAMP('{local_now}') - INTERVAL 15 MINUTE
                )
              )
           OR (
                oi.status_code IN ('paid', 'ticketed')
                AND (
                    CASE
                        WHEN oi.product_type_code = 'hotel_room' THEN oi.travel_end_time
                        ELSE oi.travel_time
                    END
                ) < TIMESTAMP('{local_now}') - INTERVAL 2 HOUR
              )
           OR (oi.status_code IN ('ticketed', 'completed', 'refunded') AND oi.paid_at IS NULL)
           OR (oi.status_code = 'cancelled' AND oi.cancelled_at IS NULL)
           OR (oi.status_code = 'completed' AND oi.completed_at IS NULL)
           OR (oi.status_code = 'refunded' AND oi.refunded_at IS NULL)
           OR (oi.product_type_code IN ('flight_cabin', 'train_seat', 'bus_seat') AND oi.traveler_id IS NULL)
        """,
    )
    _assert_zero(
        "order booking lead constraints",
        """
        SELECT COUNT(*) AS count
        FROM orders o
        JOIN order_items oi ON oi.order_id = o.id
        WHERE TIMESTAMPDIFF(DAY, o.created_at, oi.travel_time) >
              CASE oi.product_type_code
                  WHEN 'hotel_room' THEN 120
                  WHEN 'scenic_ticket' THEN 30
                  WHEN 'flight_cabin' THEN 180
                  WHEN 'train_seat' THEN 45
                  WHEN 'bus_seat' THEN 15
                  WHEN 'transfer_service' THEN 30
                  ELSE 180
              END
        """,
    )
    checks.append("order items")

    _assert_zero(
        "cancelled transport order lifecycle",
        """
        SELECT COUNT(*) AS count
        FROM orders o
        JOIN order_items oi ON oi.order_id = o.id
        LEFT JOIN flight_cabin_inventory fci
          ON oi.product_type_code = 'flight_cabin' AND fci.id = oi.product_id
        LEFT JOIN flight_departures fd
          ON fd.id = fci.flight_departure_id
        LEFT JOIN train_seat_inventory tsi
          ON oi.product_type_code = 'train_seat' AND tsi.id = oi.product_id
        LEFT JOIN train_departures td
          ON td.id = tsi.train_departure_id
        LEFT JOIN bus_seat_inventory bsi
          ON oi.product_type_code = 'bus_seat' AND bsi.id = oi.product_id
        LEFT JOIN bus_departures bd
          ON bd.id = bsi.bus_departure_id
        LEFT JOIN refund_requests rr ON rr.order_item_id = oi.id
        WHERE (
                (oi.product_type_code = 'flight_cabin' AND fd.status_code = 'cancelled')
             OR (oi.product_type_code = 'train_seat' AND td.status_code = 'cancelled')
             OR (oi.product_type_code = 'bus_seat' AND bd.status_code = 'cancelled')
        )
          AND NOT (
              (
                  o.status_code = 'cancelled'
                  AND oi.status_code = 'cancelled'
                  AND oi.cancelled_at <= COALESCE(fd.updated_at, td.updated_at, bd.updated_at)
                  AND o.paid_at IS NULL
              )
              OR (
                  o.status_code = 'finished'
                  AND oi.status_code = 'refunded'
                  AND oi.refunded_amount = o.paid_amount
                  AND oi.settlement_amount = 0
                  AND o.settlement_amount = 0
                  AND rr.id IS NOT NULL
                  AND o.created_at < COALESCE(fd.updated_at, td.updated_at, bd.updated_at)
                  AND oi.paid_at <= COALESCE(fd.updated_at, td.updated_at, bd.updated_at)
                  AND rr.requested_at >= COALESCE(fd.updated_at, td.updated_at, bd.updated_at)
              )
          )
        """,
    )
    checks.append("transport order linkage")

    _assert_positive(
        "order coupon usages rows", "SELECT COUNT(*) AS count FROM order_coupon_usages"
    )
    _assert_zero(
        "coupon, promotion and points rollup",
        """
        SELECT COUNT(*) AS count
        FROM orders o
        LEFT JOIN (
            SELECT order_id, COALESCE(SUM(discount_amount), 0) AS coupon_amount
            FROM order_coupon_usages
            GROUP BY order_id
        ) cu ON cu.order_id = o.id
        LEFT JOIN (
            SELECT order_id, COALESCE(SUM(discount_amount), 0) AS promotion_amount
            FROM order_promotion_details
            GROUP BY order_id
        ) pd ON pd.order_id = o.id
        LEFT JOIN (
            SELECT order_id, COALESCE(SUM(discount_amount), 0) AS point_amount
            FROM order_point_usages
            GROUP BY order_id
        ) pu ON pu.order_id = o.id
        WHERE COALESCE(cu.coupon_amount, 0) <> o.coupon_discount_amount
           OR COALESCE(pd.promotion_amount, 0) <> o.marketing_discount_amount
           OR COALESCE(pu.point_amount, 0) <> o.point_discount_amount
        """,
    )
    checks.append("discount rollup")

    _assert_zero(
        "payments amount and timing constraints",
        """
        SELECT COUNT(*) AS count
        FROM orders o
        LEFT JOIN (
            SELECT order_id,
                   COALESCE(SUM(CASE WHEN status_code = 'success' THEN amount ELSE 0 END), 0) AS success_amount,
                   SUM(CASE WHEN status_code = 'success' THEN 1 ELSE 0 END) AS success_count
            FROM payments
            GROUP BY order_id
        ) p ON p.order_id = o.id
        WHERE COALESCE(p.success_amount, 0) <> COALESCE(o.paid_amount, 0)
           OR (o.paid_at IS NOT NULL AND COALESCE(p.success_count, 0) = 0)
           OR (o.paid_at IS NULL AND COALESCE(p.success_count, 0) > 0)
        """,
    )
    _assert_zero(
        "payment status timing",
        """
        SELECT COUNT(*) AS count
        FROM payments
        WHERE (status_code = 'success' AND paid_at IS NULL)
           OR (status_code <> 'success' AND paid_at IS NOT NULL)
           OR updated_at < created_at
        """,
    )
    checks.append("payments")

    _assert_zero(
        "refund amount and payment linkage",
        """
        SELECT COUNT(*) AS count
        FROM refund_requests rr
        JOIN order_items oi ON oi.id = rr.order_item_id
        JOIN orders o ON o.id = rr.order_id
        LEFT JOIN refund_records r ON r.refund_request_id = rr.id
        LEFT JOIN payments p ON p.id = r.payment_id
        WHERE rr.order_id <> oi.order_id
           OR rr.user_id <> o.user_id
           OR rr.requested_at < oi.paid_at
           OR rr.requested_amount > oi.sale_amount - COALESCE(oi.refunded_amount, 0) + COALESCE(rr.approved_amount, 0)
           OR (rr.status_code = 'pending' AND rr.processed_at IS NOT NULL)
           OR (rr.status_code IN ('approved', 'rejected', 'success') AND rr.processed_at IS NULL)
           OR (r.id IS NOT NULL AND r.payment_id IS NULL)
           OR (r.id IS NOT NULL AND p.order_id <> rr.order_id)
        """,
    )
    _assert_zero(
        "completion and refund timing",
        """
        SELECT COUNT(*) AS count
        FROM orders o
        JOIN order_items oi ON oi.order_id = o.id
        LEFT JOIN refund_requests rr ON rr.order_item_id = oi.id
        LEFT JOIN refund_records r ON r.refund_request_id = rr.id
        WHERE (
                oi.completed_at IS NOT NULL
                AND oi.completed_at <
                    CASE
                        WHEN oi.product_type_code = 'hotel_room' THEN oi.travel_end_time
                        ELSE oi.travel_time
                    END
              )
           OR (
                oi.completed_at IS NOT NULL
                AND TIMESTAMPDIFF(
                    DAY,
                    CASE
                        WHEN oi.product_type_code = 'hotel_room' THEN oi.travel_end_time
                        ELSE oi.travel_time
                    END,
                    oi.completed_at
                ) >
                    CASE oi.product_type_code
                        WHEN 'hotel_room' THEN 3
                        WHEN 'scenic_ticket' THEN 2
                        WHEN 'flight_cabin' THEN 5
                        WHEN 'train_seat' THEN 3
                        WHEN 'bus_seat' THEN 2
                        WHEN 'transfer_service' THEN 2
                        ELSE 7
                    END
           )
           OR (
                r.processed_at IS NOT NULL
                AND TIMESTAMPDIFF(
                    DAY,
                    CASE
                        WHEN oi.product_type_code = 'hotel_room' THEN oi.travel_end_time
                        ELSE oi.travel_time
                    END,
                    r.processed_at
                ) >
                    CASE oi.product_type_code
                        WHEN 'hotel_room' THEN 7
                        WHEN 'scenic_ticket' THEN 3
                        WHEN 'flight_cabin' THEN 14
                        WHEN 'train_seat' THEN 7
                        WHEN 'bus_seat' THEN 3
                        WHEN 'transfer_service' THEN 3
                        ELSE 14
                    END
           )
        """,
    )
    _assert_zero(
        "refund and settlement rollup",
        """
        SELECT COUNT(*) AS count
        FROM (
            SELECT
                o.id,
                COALESCE(rr.refunded_amount, 0) AS refund_record_amount,
                COALESCE(o.refunded_amount, 0) AS order_refunded_amount,
                COALESCE(o.settlement_amount, 0) AS order_settlement_amount,
                SUM(COALESCE(oi.refunded_amount, 0)) AS item_refunded_amount,
                SUM(COALESCE(oi.settlement_amount, 0)) AS item_settlement_amount
            FROM orders o
            JOIN order_items oi ON oi.order_id = o.id
            LEFT JOIN (
                SELECT order_id, COALESCE(SUM(amount), 0) AS refunded_amount
                FROM refund_records
                WHERE status_code = 'success'
                GROUP BY order_id
            ) rr ON rr.order_id = o.id
            GROUP BY o.id, o.refunded_amount, o.settlement_amount, rr.refunded_amount
        ) mismatches
        WHERE refund_record_amount <> order_refunded_amount
           OR item_refunded_amount <> order_refunded_amount
           OR item_settlement_amount <> order_settlement_amount
        """,
    )
    checks.append("refunds")

    _assert_zero(
        "point usage and ledger constraints",
        """
        SELECT COUNT(*) AS count
        FROM order_point_usages pu
        JOIN member_point_ledger l ON l.id = pu.point_ledger_id
        WHERE pu.user_id <> l.user_id
           OR pu.points_used <= 0
           OR pu.discount_amount <= 0
           OR l.ledger_type_code <> 'point_redeem'
           OR l.points_delta >= 0
           OR l.balance_after < 0
        """,
    )
    _assert_zero(
        "member account latest ledger balance mismatch",
        """
        SELECT COUNT(*) AS count
        FROM member_accounts a
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
        ) last_ledger ON last_ledger.user_id = a.user_id
        WHERE a.points_balance <> last_ledger.balance_after
        """,
    )
    checks.append("points")

    return checks


def validate_stage7_acceptance() -> list[str]:
    checks: list[str] = []

    critical_tables = [
        "areas",
        "currencies",
        "channels",
        "transport_hubs",
        "suppliers",
        "hotels",
        "scenic_spots",
        "flight_routes",
        "train_routes",
        "bus_routes",
        "transfer_services",
        "hotel_room_daily",
        "scenic_ticket_daily",
        "flight_departures",
        "train_departures",
        "bus_departures",
        "transfer_capacity_calendar",
        "users",
        "user_profiles",
        "travelers",
        "member_accounts",
        "member_point_ledger",
        "coupon_templates",
        "user_coupons",
        "promotions",
        "promotion_rules",
        "promotion_bindings",
        "orders",
        "order_items",
        "order_promotion_details",
        "order_point_usages",
        "payments",
        "refund_requests",
        "refund_records",
    ]
    for table in critical_tables:
        _assert_positive(f"{table} non-empty", f"SELECT COUNT(*) AS count FROM {table}")
    checks.append("critical tables")

    unique_checks = {
        "areas area_code": "SELECT COUNT(*) - COUNT(DISTINCT area_code) AS count FROM areas",
        "transport_hubs hub_code": "SELECT COUNT(*) - COUNT(DISTINCT hub_code) AS count FROM transport_hubs",
        "suppliers supplier_code": "SELECT COUNT(*) - COUNT(DISTINCT supplier_code) AS count FROM suppliers",
        "users phone": "SELECT COUNT(*) - COUNT(DISTINCT phone) AS count FROM users",
        "users email": "SELECT COUNT(*) - COUNT(DISTINCT email) AS count FROM users",
        "hotels hotel_code": "SELECT COUNT(*) - COUNT(DISTINCT hotel_code) AS count FROM hotels",
        "scenic_spots scenic_code": "SELECT COUNT(*) - COUNT(DISTINCT scenic_code) AS count FROM scenic_spots",
        "coupon_templates template_code": "SELECT COUNT(*) - COUNT(DISTINCT template_code) AS count FROM coupon_templates",
        "user_coupons coupon_code": "SELECT COUNT(*) - COUNT(DISTINCT coupon_code) AS count FROM user_coupons",
        "promotions promotion_code": "SELECT COUNT(*) - COUNT(DISTINCT promotion_code) AS count FROM promotions",
        "orders order_no": "SELECT COUNT(*) - COUNT(DISTINCT order_no) AS count FROM orders",
        "payments payment_no": "SELECT COUNT(*) - COUNT(DISTINCT payment_no) AS count FROM payments",
        "refund_requests refund_request_no": "SELECT COUNT(*) - COUNT(DISTINCT refund_request_no) AS count FROM refund_requests",
        "refund_records refund_no": "SELECT COUNT(*) - COUNT(DISTINCT refund_no) AS count FROM refund_records",
        "flight_departures instance_code": "SELECT COUNT(*) - COUNT(DISTINCT departure_instance_code) AS count FROM flight_departures",
        "train_departures instance_code": "SELECT COUNT(*) - COUNT(DISTINCT departure_instance_code) AS count FROM train_departures",
        "bus_departures instance_code": "SELECT COUNT(*) - COUNT(DISTINCT departure_instance_code) AS count FROM bus_departures",
    }
    for label, sql in unique_checks.items():
        _assert_zero(f"{label} uniqueness", sql)
    checks.append("uniqueness")

    _assert_zero(
        "cross-domain foreign key completeness",
        """
        SELECT COUNT(*) AS count
        FROM order_items oi
        LEFT JOIN travelers t ON t.id = oi.traveler_id
        LEFT JOIN payments p ON p.order_id = oi.order_id AND p.user_id = oi.user_id AND p.status_code = 'success'
        LEFT JOIN refund_requests rr ON rr.order_item_id = oi.id
        LEFT JOIN refund_records r ON r.order_item_id = oi.id
        WHERE (oi.traveler_id IS NOT NULL AND (t.id IS NULL OR t.user_id <> oi.user_id))
           OR (rr.id IS NOT NULL AND rr.order_id <> oi.order_id)
           OR (r.id IS NOT NULL AND r.order_id <> oi.order_id)
           OR (r.id IS NOT NULL AND r.payment_id IS NULL)
           OR (oi.status_code IN ('paid', 'ticketed', 'completed', 'refunded') AND p.id IS NULL)
        """,
    )
    checks.append("foreign key completeness")

    _assert_zero(
        "enum completeness",
        """
        SELECT COUNT(*) AS count
        FROM (
            SELECT status_code AS enum_value FROM orders WHERE status_code NOT IN ('pending_payment', 'cancelled', 'paid', 'in_progress', 'finished')
            UNION ALL
            SELECT status_code FROM order_items WHERE status_code NOT IN ('pending_payment', 'cancelled', 'paid', 'ticketed', 'completed', 'refunded')
            UNION ALL
            SELECT status_code FROM payments WHERE status_code NOT IN ('pending', 'success', 'failed', 'closed')
            UNION ALL
            SELECT status_code FROM refund_requests WHERE status_code NOT IN ('pending', 'approved', 'rejected', 'success')
            UNION ALL
            SELECT status_code FROM refund_records WHERE status_code NOT IN ('pending', 'success', 'failed')
            UNION ALL
            SELECT member_level_code FROM member_accounts WHERE member_level_code NOT IN ('normal', 'silver', 'gold')
        ) invalid_enums
        """,
    )
    checks.append("enum completeness")

    _assert_zero(
        "layer failure localization",
        """
        SELECT COUNT(*) AS count
        FROM (
            SELECT 1 FROM orders WHERE order_no IS NULL
            UNION ALL
            SELECT 1 FROM order_items WHERE order_id IS NULL
            UNION ALL
            SELECT 1 FROM payments WHERE order_id IS NULL
            UNION ALL
            SELECT 1 FROM refund_requests WHERE order_item_id IS NULL
            UNION ALL
            SELECT 1 FROM refund_records WHERE refund_request_id IS NULL
        ) broken_rows
        """,
    )
    checks.append("failure localization")

    _assert_zero(
        "smoke/full product coverage",
        """
        SELECT 6 - COUNT(DISTINCT order_type_code) AS count
        FROM orders
        """,
    )
    _assert_zero(
        "missing layer table definitions",
        f"""
        SELECT COUNT(*) AS count
        FROM (
            {" UNION ALL ".join([f"SELECT '{table}' AS table_name" for layer in LAYERS.values() for table in layer["tables"]])}
        ) planned
        LEFT JOIN information_schema.tables t
          ON t.table_schema = DATABASE()
         AND t.table_name = planned.table_name
        WHERE t.table_name IS NULL
        """,
    )
    checks.append("execution coverage")

    return checks
