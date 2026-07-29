from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import app.database as database_module  # noqa: E402
from app.database import fetch_one  # noqa: E402
from app.main import app  # noqa: E402


class TransactionalConnection:
    def __init__(self, connection):
        self._connection = connection

    def cursor(self, *args, **kwargs):
        return self._connection.cursor(*args, **kwargs)

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None

    def close(self) -> None:
        return None

    def __getattr__(self, name: str):
        return getattr(self._connection, name)


@pytest.fixture(autouse=True)
def isolated_db_transaction(monkeypatch):
    connection = database_module.get_connection()
    wrapped = TransactionalConnection(connection)
    monkeypatch.setattr(database_module, "get_connection", lambda: wrapped)
    try:
        yield
    finally:
        connection.rollback()
        connection.close()


def require_row(
    sql: str, params: tuple[object, ...] | None = None
) -> dict[str, object]:
    row = fetch_one(sql, params)
    assert row is not None, f"Expected sample row for query: {sql}"
    return row


def as_int(value: object) -> int:
    return int(cast(int | str, value))


def as_str(value: object) -> str:
    return str(cast(Any, value))


@pytest.fixture(scope="session")
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(scope="session")
def active_user_id() -> int:
    row = require_row(
        """
        SELECT u.id
        FROM users AS u
        JOIN member_accounts AS ma ON ma.user_id = u.id
        WHERE u.status_code <> 'inactive'
        ORDER BY u.id ASC
        LIMIT 1
        """
    )
    return as_int(row["id"])


@pytest.fixture(scope="session")
def auth_headers(active_user_id: int) -> dict[str, str]:
    return {"X-User-Id": str(active_user_id)}


@pytest.fixture(scope="session")
def hotel_context() -> dict[str, object]:
    row = require_row(
        """
        SELECT
            h.id AS hotel_id,
            h.area_id,
            rt.id AS room_type_id,
            d1.business_date AS check_in_date,
            DATE_ADD(d1.business_date, INTERVAL 1 DAY) AS check_out_date,
            d1.currency_code
        FROM hotels AS h
        JOIN hotel_room_types AS rt
          ON rt.hotel_id = h.id
         AND rt.status_code = 'active'
        JOIN hotel_room_daily AS d1
          ON d1.room_type_id = rt.id
         AND d1.status_code = 'active'
         AND d1.available_inventory > 0
        JOIN hotel_room_daily AS d2
          ON d2.room_type_id = rt.id
         AND d2.business_date = DATE_ADD(d1.business_date, INTERVAL 1 DAY)
         AND d2.status_code = 'active'
         AND d2.available_inventory > 0
        WHERE h.status_code = 'active'
        ORDER BY h.id ASC, rt.id ASC, d1.business_date ASC
        LIMIT 1
        """
    )
    return {
        "hotelId": as_int(row["hotel_id"]),
        "areaId": as_int(row["area_id"]),
        "roomTypeId": as_int(row["room_type_id"]),
        "checkInDate": as_str(row["check_in_date"]),
        "checkOutDate": as_str(row["check_out_date"]),
        "currencyCode": as_str(row["currency_code"]),
    }


@pytest.fixture(scope="session")
def scenic_context() -> dict[str, object]:
    row = require_row(
        """
        SELECT
            s.id AS scenic_spot_id,
            s.area_id,
            t.id AS ticket_type_id,
            d.business_date AS travel_date,
            d.currency_code
        FROM scenic_spots AS s
        JOIN scenic_ticket_types AS t
          ON t.scenic_spot_id = s.id
         AND t.status_code = 'active'
        JOIN scenic_ticket_daily AS d
          ON d.ticket_type_id = t.id
         AND d.status_code = 'active'
         AND d.available_inventory > 0
        WHERE s.status_code = 'active'
        ORDER BY s.id ASC, t.id ASC, d.business_date ASC
        LIMIT 1
        """
    )
    return {
        "scenicSpotId": as_int(row["scenic_spot_id"]),
        "areaId": as_int(row["area_id"]),
        "ticketTypeId": as_int(row["ticket_type_id"]),
        "travelDate": as_str(row["travel_date"]),
        "travelTime": f"{as_str(row['travel_date'])} 09:00:00",
        "currencyCode": as_str(row["currency_code"]),
    }


@pytest.fixture(scope="session")
def flight_context() -> dict[str, object]:
    row = require_row(
        """
        SELECT
            d.id AS departure_id,
            i.id AS cabin_inventory_id,
            r.departure_area_id,
            r.arrival_area_id,
            DATE(d.departure_time) AS departure_date,
            d.departure_time,
            i.currency_code
        FROM flight_departures AS d
        JOIN flight_routes AS r ON r.id = d.flight_route_id
        JOIN flight_cabin_inventory AS i
          ON i.flight_departure_id = d.id
         AND i.status_code = 'active'
         AND i.available_inventory > 0
        WHERE d.status_code = 'scheduled'
          AND r.status_code = 'active'
        ORDER BY d.departure_time ASC, d.id ASC
        LIMIT 1
        """
    )
    return {
        "departureId": as_int(row["departure_id"]),
        "cabinInventoryId": as_int(row["cabin_inventory_id"]),
        "departureAreaId": as_int(row["departure_area_id"]),
        "arrivalAreaId": as_int(row["arrival_area_id"]),
        "departureDate": as_str(row["departure_date"]),
        "travelTime": as_str(row["departure_time"]),
        "currencyCode": as_str(row["currency_code"]),
    }


@pytest.fixture(scope="session")
def train_context() -> dict[str, object]:
    row = require_row(
        """
        SELECT
            d.id AS departure_id,
            i.id AS seat_inventory_id,
            r.departure_area_id,
            r.arrival_area_id,
            DATE(d.departure_time) AS departure_date,
            d.departure_time,
            i.currency_code
        FROM train_departures AS d
        JOIN train_routes AS r ON r.id = d.train_route_id
        JOIN train_seat_inventory AS i
          ON i.train_departure_id = d.id
         AND i.status_code = 'active'
         AND i.available_inventory > 0
        WHERE d.status_code = 'scheduled'
          AND r.status_code = 'active'
        ORDER BY d.departure_time ASC, d.id ASC
        LIMIT 1
        """
    )
    return {
        "departureId": as_int(row["departure_id"]),
        "seatInventoryId": as_int(row["seat_inventory_id"]),
        "departureAreaId": as_int(row["departure_area_id"]),
        "arrivalAreaId": as_int(row["arrival_area_id"]),
        "departureDate": as_str(row["departure_date"]),
        "travelTime": as_str(row["departure_time"]),
        "currencyCode": as_str(row["currency_code"]),
    }


@pytest.fixture(scope="session")
def bus_context() -> dict[str, object]:
    row = require_row(
        """
        SELECT
            d.id AS departure_id,
            i.id AS seat_inventory_id,
            r.departure_area_id,
            r.arrival_area_id,
            DATE(d.departure_time) AS departure_date,
            d.departure_time,
            i.currency_code
        FROM bus_departures AS d
        JOIN bus_routes AS r ON r.id = d.bus_route_id
        JOIN bus_seat_inventory AS i
          ON i.bus_departure_id = d.id
         AND i.status_code = 'active'
         AND i.available_inventory > 0
        WHERE d.status_code = 'scheduled'
          AND r.status_code = 'active'
        ORDER BY d.departure_time ASC, d.id ASC
        LIMIT 1
        """
    )
    return {
        "departureId": as_int(row["departure_id"]),
        "seatInventoryId": as_int(row["seat_inventory_id"]),
        "departureAreaId": as_int(row["departure_area_id"]),
        "arrivalAreaId": as_int(row["arrival_area_id"]),
        "departureDate": as_str(row["departure_date"]),
        "travelTime": as_str(row["departure_time"]),
        "currencyCode": as_str(row["currency_code"]),
    }


@pytest.fixture(scope="session")
def transfer_context() -> dict[str, object]:
    row = require_row(
        """
        SELECT
            s.id AS service_id,
            s.area_id,
            c.business_date,
            r.pickup_area_id,
            r.dropoff_area_id
        FROM transfer_services AS s
        JOIN transfer_capacity_calendar AS c
          ON c.transfer_service_id = s.id
         AND c.status_code = 'active'
         AND c.available_inventory > 0
        JOIN transfer_service_area_rules AS r
          ON r.transfer_service_id = s.id
         AND r.status_code = 'active'
        WHERE s.status_code = 'active'
        ORDER BY s.id ASC, c.business_date ASC, r.id ASC
        LIMIT 1
        """
    )
    return {
        "serviceId": as_int(row["service_id"]),
        "areaId": as_int(row["area_id"]),
        "businessDate": as_str(row["business_date"]),
        "travelTime": f"{as_str(row['business_date'])} 09:00:00",
        "pickupAreaId": as_int(row["pickup_area_id"]),
        "dropoffAreaId": as_int(row["dropoff_area_id"]),
        "currencyCode": "CNY",
    }


@pytest.fixture(scope="session")
def marketing_user_context() -> dict[str, object]:
    row = require_row(
        """
        SELECT
            u.id AS user_id,
            ct.id AS template_id
        FROM users AS u
        JOIN member_accounts AS ma ON ma.user_id = u.id
        JOIN coupon_templates AS ct
          ON ct.status_code = 'active'
         AND NOW() BETWEEN ct.valid_from AND ct.valid_until
        LEFT JOIN user_coupons AS uc
          ON uc.template_id = ct.id
         AND uc.user_id = u.id
        WHERE u.status_code <> 'inactive'
        GROUP BY u.id, ct.id, ct.per_user_limit
        HAVING COUNT(uc.id) < ct.per_user_limit
        ORDER BY u.id ASC, ct.id ASC
        LIMIT 1
        """
    )
    return {"userId": as_int(row["user_id"]), "templateId": as_int(row["template_id"])}


@pytest.fixture(scope="session")
def marketing_headers(marketing_user_context: dict[str, object]) -> dict[str, str]:
    return {"X-User-Id": str(marketing_user_context["userId"])}


@pytest.fixture(scope="session")
def sample_user_coupon(marketing_user_context: dict[str, object]) -> dict[str, object]:
    row = require_row(
        """
        SELECT id, template_id
        FROM user_coupons
        WHERE user_id = %s
        ORDER BY id ASC
        LIMIT 1
        """,
        (marketing_user_context["userId"],),
    )
    return {"userCouponId": as_int(row["id"]), "templateId": as_int(row["template_id"])}


@pytest.fixture(scope="session")
def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d%H%M%S")
