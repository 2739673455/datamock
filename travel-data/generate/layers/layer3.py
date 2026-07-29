"""第三层：价格库存与班期。"""

from datetime import datetime, timedelta
from decimal import Decimal

from ..config import GENERATION_DEFAULTS
from ..generator_support import (
    RANDOM,
    bulk_insert,
    dated_record_timestamps,
    fetch_rows,
    json_text,
    quantize_money,
    random_datetime_between,
    random_time_window,
    reset_tables,
)
from .base import BaseGenerator
from .validations import validate_layer3


class Layer3Generator(BaseGenerator):
    layer = 3
    layer_name = "价格库存与班期"

    def run(self) -> None:
        self.header()
        reset_tables(
            "transfer_capacity_calendar",
            "bus_seat_inventory",
            "bus_departures",
            "train_seat_inventory",
            "train_departures",
            "flight_cabin_inventory",
            "flight_departures",
            "scenic_ticket_daily",
            "hotel_room_daily",
        )
        counts: dict[str, int] = {}
        counts.update(self._generate_hotel_supply())
        counts.update(self._generate_scenic_supply())
        counts.update(self._generate_transport_supply())
        counts.update(self._generate_transfer_capacity())
        self.log_table_counts(counts)
        checks = validate_layer3()
        for check in checks:
            self.log(f"  [OK] validation: {check}")

    def _date_range(self) -> list:
        today = datetime.now().date()
        history = GENERATION_DEFAULTS["history_days"]
        future = GENERATION_DEFAULTS["future_days"]
        return [
            today + timedelta(days=offset) for offset in range(-history, future + 1)
        ]

    def _transport_departure_status(
        self,
        departure_dt: datetime,
        arrival_dt: datetime,
        now: datetime,
    ) -> str:
        if arrival_dt <= now - timedelta(hours=12):
            return "cancelled" if RANDOM.random() < 0.015 else "done"
        return "cancelled" if RANDOM.random() < 0.01 else "scheduled"

    def _transport_departure_timestamps(
        self,
        departure_dt: datetime,
        status_code: str,
        now: datetime,
    ) -> tuple[datetime, datetime]:
        created_at, updated_at = dated_record_timestamps(departure_dt, now=now)
        if status_code != "cancelled":
            return created_at, updated_at
        latest_cancel_at = min(now, departure_dt - timedelta(minutes=30))
        if latest_cancel_at < created_at:
            latest_cancel_at = created_at
        return created_at, random_datetime_between(created_at, latest_cancel_at)

    def _generate_hotel_supply(self) -> dict[str, int]:
        room_types = fetch_rows("SELECT id FROM hotel_room_types")

        def rows():
            for room_type in room_types:
                base_price = quantize_money(RANDOM.randint(180, 1800))
                for business_date in self._date_range():
                    is_weekend = business_date.weekday() >= 4
                    price = quantize_money(
                        base_price
                        * (Decimal("1.18") if is_weekend else Decimal("1.00"))
                    )
                    total = RANDOM.randint(8, 50)
                    sold = RANDOM.randint(0, int(total * 0.7))
                    reserved = RANDOM.randint(0, max(0, total - sold))
                    available = max(0, total - sold - reserved)
                    created_at, updated_at = dated_record_timestamps(business_date)
                    yield (
                        room_type["id"],
                        business_date,
                        total,
                        available,
                        reserved,
                        sold,
                        "CNY",
                        price,
                        quantize_money(price * Decimal("0.68")),
                        "active",
                        created_at,
                        updated_at,
                    )

        count = self.stream_rows(
            """
            INSERT INTO hotel_room_daily (
                room_type_id, business_date, total_inventory, available_inventory, reserved_inventory,
                sold_inventory, currency_code, sale_price_amount, settlement_price_amount,
                status_code, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            rows(),
            total_rows=len(room_types) * len(self._date_range()),
            build_step_name="build hotel_room_daily",
        )
        return {"hotel_room_daily": count}

    def _generate_scenic_supply(self) -> dict[str, int]:
        ticket_types = fetch_rows("SELECT id FROM scenic_ticket_types")

        def rows():
            for ticket in ticket_types:
                base_price = quantize_money(RANDOM.randint(40, 380))
                for business_date in self._date_range():
                    holiday_ratio = (
                        Decimal("1.25")
                        if business_date.weekday() >= 5
                        else Decimal("1.00")
                    )
                    price = quantize_money(base_price * holiday_ratio)
                    total = RANDOM.randint(50, 500)
                    sold = RANDOM.randint(0, int(total * 0.8))
                    reserved = RANDOM.randint(0, max(0, total - sold))
                    available = max(0, total - sold - reserved)
                    created_at, updated_at = dated_record_timestamps(business_date)
                    yield (
                        ticket["id"],
                        business_date,
                        total,
                        available,
                        reserved,
                        sold,
                        "CNY",
                        price,
                        quantize_money(price * Decimal("0.70")),
                        "active",
                        created_at,
                        updated_at,
                    )

        count = self.stream_rows(
            """
            INSERT INTO scenic_ticket_daily (
                ticket_type_id, business_date, total_inventory, available_inventory, reserved_inventory,
                sold_inventory, currency_code, sale_price_amount, settlement_price_amount,
                status_code, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            rows(),
            total_rows=len(ticket_types) * len(self._date_range()),
            build_step_name="build scenic_ticket_daily",
        )
        return {"scenic_ticket_daily": count}

    def _generate_transport_supply(self) -> dict[str, int]:
        transport_dates = self._date_range()
        now = datetime.now()
        flight_departures = []
        flight_inventory = []
        for route in fetch_rows("SELECT id, duration_minutes FROM flight_routes"):
            for departure_date in transport_dates:
                departure_dt = datetime.combine(
                    departure_date, random_time_window(6, 22)
                )
                arrival_dt = departure_dt + timedelta(minutes=route["duration_minutes"])
                departure_id = len(flight_departures) + 1
                status_code = self._transport_departure_status(
                    departure_dt, arrival_dt, now
                )
                departure_created_at, departure_updated_at = (
                    self._transport_departure_timestamps(
                        departure_dt,
                        status_code,
                        now,
                    )
                )
                rule_payload = json_text(
                    {
                        "free_checked_baggage": RANDOM.choice(
                            [
                                {"weight": 20, "piece": 1},
                                {"weight": 23, "piece": 1},
                                {"weight": 23, "piece": 2},
                            ]
                        ),
                        "free_cabin_baggage": {"weight": 5, "size": "40x30x20"},
                        "meal": RANDOM.choice([True, False]),
                    }
                )
                flight_departures.append(
                    (
                        route["id"],
                        f"{departure_dt:%Y%m%d}-{route['id']}",
                        departure_dt,
                        arrival_dt,
                        rule_payload,
                        status_code,
                        departure_created_at,
                        departure_updated_at,
                    )
                )
                for cabin_type in ("economy", "business"):
                    total = (
                        RANDOM.randint(12, 180)
                        if cabin_type == "economy"
                        else RANDOM.randint(8, 42)
                    )
                    sold = RANDOM.randint(0, int(total * 0.8))
                    reserved = RANDOM.randint(0, max(0, total - sold))
                    inventory_created_at, inventory_updated_at = (
                        dated_record_timestamps(departure_dt)
                    )
                    sale_price = quantize_money(RANDOM.randint(300, 2800))
                    flight_inventory.append(
                        (
                            departure_id,
                            cabin_type,
                            "CNY",
                            sale_price,
                            quantize_money(sale_price * Decimal("0.78")),
                            total,
                            max(0, total - sold - reserved),
                            reserved,
                            sold,
                            "active",
                            inventory_created_at,
                            inventory_updated_at,
                        )
                    )
        train_departures = []
        train_inventory = []
        for route in fetch_rows("SELECT id, duration_minutes FROM train_routes"):
            for departure_date in transport_dates:
                departure_dt = datetime.combine(
                    departure_date, random_time_window(5, 21)
                )
                arrival_dt = departure_dt + timedelta(minutes=route["duration_minutes"])
                departure_id = len(train_departures) + 1
                status_code = self._transport_departure_status(
                    departure_dt, arrival_dt, now
                )
                departure_created_at, departure_updated_at = (
                    self._transport_departure_timestamps(
                        departure_dt,
                        status_code,
                        now,
                    )
                )
                train_departures.append(
                    (
                        route["id"],
                        f"{departure_dt:%Y%m%d}-{route['id']}",
                        departure_dt,
                        arrival_dt,
                        status_code,
                        departure_created_at,
                        departure_updated_at,
                    )
                )
                for seat_type in ("second_class", "first_class", "business"):
                    total = RANDOM.randint(40, 800)
                    sold = RANDOM.randint(0, int(total * 0.8))
                    reserved = RANDOM.randint(0, max(0, total - sold))
                    inventory_created_at, inventory_updated_at = (
                        dated_record_timestamps(departure_dt)
                    )
                    sale_price = quantize_money(RANDOM.randint(80, 1800))
                    train_inventory.append(
                        (
                            departure_id,
                            seat_type,
                            "CNY",
                            sale_price,
                            quantize_money(sale_price * Decimal("0.82")),
                            total,
                            max(0, total - sold - reserved),
                            reserved,
                            sold,
                            "active",
                            inventory_created_at,
                            inventory_updated_at,
                        )
                    )
        bus_departures = []
        bus_inventory = []
        for route in fetch_rows("SELECT id, duration_minutes FROM bus_routes"):
            for departure_date in transport_dates:
                departure_dt = datetime.combine(
                    departure_date, random_time_window(6, 20)
                )
                arrival_dt = departure_dt + timedelta(minutes=route["duration_minutes"])
                departure_id = len(bus_departures) + 1
                status_code = self._transport_departure_status(
                    departure_dt, arrival_dt, now
                )
                departure_created_at, departure_updated_at = (
                    self._transport_departure_timestamps(
                        departure_dt,
                        status_code,
                        now,
                    )
                )
                bus_departures.append(
                    (
                        route["id"],
                        f"{departure_dt:%Y%m%d}-{route['id']}",
                        departure_dt,
                        arrival_dt,
                        status_code,
                        departure_created_at,
                        departure_updated_at,
                    )
                )
                total = RANDOM.randint(18, 58)
                sold = RANDOM.randint(0, int(total * 0.8))
                reserved = RANDOM.randint(0, max(0, total - sold))
                inventory_created_at, inventory_updated_at = dated_record_timestamps(
                    departure_dt
                )
                sale_price = quantize_money(RANDOM.randint(20, 350))
                bus_inventory.append(
                    (
                        departure_id,
                        "coach",
                        "CNY",
                        sale_price,
                        quantize_money(sale_price * Decimal("0.75")),
                        total,
                        max(0, total - sold - reserved),
                        reserved,
                        sold,
                        "active",
                        inventory_created_at,
                        inventory_updated_at,
                    )
                )
        bulk_insert(
            """
            INSERT INTO flight_departures (
                flight_route_id, departure_instance_code, departure_time, arrival_time,
                rule_payload, status_code, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            flight_departures,
        )
        bulk_insert(
            """
            INSERT INTO flight_cabin_inventory (
                flight_departure_id, cabin_class_code, currency_code, sale_price_amount,
                settlement_price_amount, total_inventory, available_inventory, reserved_inventory,
                sold_inventory, status_code, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            flight_inventory,
        )
        bulk_insert(
            """
            INSERT INTO train_departures (
                train_route_id, departure_instance_code, departure_time, arrival_time,
                status_code, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            train_departures,
        )
        bulk_insert(
            """
            INSERT INTO train_seat_inventory (
                train_departure_id, seat_class_code, currency_code, sale_price_amount,
                settlement_price_amount, total_inventory, available_inventory, reserved_inventory,
                sold_inventory, status_code, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            train_inventory,
        )
        bulk_insert(
            """
            INSERT INTO bus_departures (
                bus_route_id, departure_instance_code, departure_time, arrival_time,
                status_code, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            bus_departures,
        )
        bulk_insert(
            """
            INSERT INTO bus_seat_inventory (
                bus_departure_id, seat_class_code, currency_code, sale_price_amount,
                settlement_price_amount, total_inventory, available_inventory, reserved_inventory,
                sold_inventory, status_code, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            bus_inventory,
        )
        return {
            "flight_departures": len(flight_departures),
            "flight_cabin_inventory": len(flight_inventory),
            "train_departures": len(train_departures),
            "train_seat_inventory": len(train_inventory),
            "bus_departures": len(bus_departures),
            "bus_seat_inventory": len(bus_inventory),
        }

    def _generate_transfer_capacity(self) -> dict[str, int]:
        rows = []
        for service in fetch_rows("SELECT id FROM transfer_services"):
            for business_date in self._date_range():
                total = RANDOM.randint(4, 40)
                sold = RANDOM.randint(0, int(total * 0.7))
                reserved = RANDOM.randint(0, max(0, total - sold))
                created_at, updated_at = dated_record_timestamps(business_date)
                rows.append(
                    (
                        service["id"],
                        business_date,
                        total,
                        max(0, total - sold - reserved),
                        reserved,
                        sold,
                        "active",
                        created_at,
                        updated_at,
                    )
                )
        bulk_insert(
            """
            INSERT INTO transfer_capacity_calendar (
                transfer_service_id, business_date, total_inventory, available_inventory,
                reserved_inventory, sold_inventory, status_code, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            rows,
        )
        return {"transfer_capacity_calendar": len(rows)}
