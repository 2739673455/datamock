from __future__ import annotations

from decimal import Decimal
from typing import cast

import pytest

from app.database import fetch_one

PRODUCT_TYPES = [
    "hotel_room",
    "scenic_ticket",
    "flight_cabin",
    "train_seat",
    "bus_seat",
    "transfer_service",
]


def amount(value: object) -> Decimal:
    return Decimal(str(value))


def int_value(value: object) -> int:
    return int(cast(int | str, value or 0))


def as_inventory(row: dict[str, object]) -> dict[str, int]:
    return {
        "available": int_value(row["available_inventory"]),
        "reserved": int_value(row["reserved_inventory"]),
    }


def create_traveler(client, auth_headers, now_stamp: str, suffix: str) -> int:
    response = client.post(
        "/api/v1/me/travelers",
        headers=auth_headers,
        json={
            "travelerName": f"矩阵出行人{suffix}",
            "identityTypeCode": "passport",
            "identityNo": f"P{now_stamp}{suffix}",
            "genderCode": "male",
            "birthDate": "1992-03-04",
            "phone": "13800009999",
        },
    )
    assert response.status_code == 200, response.text
    return int(response.json()["travelerId"])


def product_case(
    product_type: str,
    hotel_context,
    scenic_context,
    flight_context,
    train_context,
    bus_context,
    transfer_context,
) -> dict[str, object]:
    if product_type == "hotel_room":
        return {
            "productId": hotel_context["roomTypeId"],
            "productName": "矩阵酒店房型",
            "currencyCode": hotel_context["currencyCode"],
            "checkInDate": hotel_context["checkInDate"],
            "checkOutDate": hotel_context["checkOutDate"],
        }
    if product_type == "scenic_ticket":
        return {
            "productId": scenic_context["ticketTypeId"],
            "productName": "矩阵景点票",
            "currencyCode": scenic_context["currencyCode"],
            "travelTime": scenic_context["travelTime"],
        }
    if product_type == "flight_cabin":
        return {
            "productId": flight_context["cabinInventoryId"],
            "productName": "矩阵机票",
            "currencyCode": flight_context["currencyCode"],
            "travelTime": flight_context["travelTime"],
            "requiresTraveler": True,
        }
    if product_type == "train_seat":
        return {
            "productId": train_context["seatInventoryId"],
            "productName": "矩阵火车票",
            "currencyCode": train_context["currencyCode"],
            "travelTime": train_context["travelTime"],
            "requiresTraveler": True,
        }
    if product_type == "bus_seat":
        return {
            "productId": bus_context["seatInventoryId"],
            "productName": "矩阵汽车票",
            "currencyCode": bus_context["currencyCode"],
            "travelTime": bus_context["travelTime"],
            "requiresTraveler": True,
        }
    return {
        "productId": transfer_context["serviceId"],
        "productName": "矩阵接送服务",
        "currencyCode": transfer_context["currencyCode"],
        "travelTime": transfer_context["travelTime"],
    }


def inventory_for(product_type: str, case: dict[str, object]) -> dict[str, int]:
    if product_type == "hotel_room":
        row = fetch_one(
            """
            SELECT
                SUM(available_inventory) AS available_inventory,
                SUM(reserved_inventory) AS reserved_inventory
            FROM hotel_room_daily
            WHERE room_type_id = %s
              AND business_date >= %s
              AND business_date < %s
            """,
            (case["productId"], case["checkInDate"], case["checkOutDate"]),
        )
    elif product_type == "scenic_ticket":
        row = fetch_one(
            """
            SELECT available_inventory, reserved_inventory
            FROM scenic_ticket_daily
            WHERE ticket_type_id = %s AND business_date = DATE(%s)
            """,
            (case["productId"], case["travelTime"]),
        )
    elif product_type == "flight_cabin":
        row = fetch_one(
            """
            SELECT available_inventory, reserved_inventory
            FROM flight_cabin_inventory
            WHERE id = %s
            """,
            (case["productId"],),
        )
    elif product_type == "train_seat":
        row = fetch_one(
            """
            SELECT available_inventory, reserved_inventory
            FROM train_seat_inventory
            WHERE id = %s
            """,
            (case["productId"],),
        )
    elif product_type == "bus_seat":
        row = fetch_one(
            """
            SELECT available_inventory, reserved_inventory
            FROM bus_seat_inventory
            WHERE id = %s
            """,
            (case["productId"],),
        )
    else:
        row = fetch_one(
            """
            SELECT available_inventory, reserved_inventory
            FROM transfer_capacity_calendar
            WHERE transfer_service_id = %s AND business_date = DATE(%s)
            """,
            (case["productId"], case["travelTime"]),
        )
    assert row is not None
    return as_inventory(row)


def order_item_payload(case: dict[str, object]) -> dict[str, object]:
    item = {
        "productTypeCode": case["productTypeCode"],
        "productId": case["productId"],
        "productName": case["productName"],
        "quantity": 1,
        "travelerIds": case.get("travelerIds", []),
    }
    if case.get("travelTime") is not None:
        item["travelTime"] = case["travelTime"]
    if case.get("checkInDate") is not None:
        item["checkInDate"] = case["checkInDate"]
        item["checkOutDate"] = case["checkOutDate"]
    return item


@pytest.mark.parametrize("product_type", PRODUCT_TYPES)
def test_create_and_cancel_order_inventory_contract(
    client,
    auth_headers,
    now_stamp,
    product_type,
    hotel_context,
    scenic_context,
    flight_context,
    train_context,
    bus_context,
    transfer_context,
):
    case = product_case(
        product_type,
        hotel_context,
        scenic_context,
        flight_context,
        train_context,
        bus_context,
        transfer_context,
    )
    case["productTypeCode"] = product_type
    if case.get("requiresTraveler"):
        traveler_id = create_traveler(
            client, auth_headers, now_stamp, product_type.upper()[:4]
        )
        case["travelerIds"] = [traveler_id]

    before_inventory = inventory_for(product_type, case)
    create_response = client.post(
        "/api/v1/orders",
        headers=auth_headers,
        json={
            "orderTypeCode": product_type,
            "sourceChannelCode": "app",
            "currencyCode": case["currencyCode"],
            "items": [order_item_payload(case)],
            "userCouponIds": [],
            "usePoints": False,
        },
    )

    assert create_response.status_code == 200, create_response.text
    created = create_response.json()
    assert created["orderTypeCode"] == product_type
    assert created["statusCode"] == "pending_payment"

    reserved_inventory = inventory_for(product_type, case)
    assert reserved_inventory["available"] == before_inventory["available"] - 1
    assert reserved_inventory["reserved"] == before_inventory["reserved"] + 1

    order = fetch_one(
        """
        SELECT
            goods_amount,
            marketing_discount_amount,
            coupon_discount_amount,
            point_discount_amount,
            payable_amount
        FROM orders
        WHERE id = %s
        """,
        (created["orderId"],),
    )
    assert order is not None
    assert amount(order["goods_amount"]) - amount(
        order["marketing_discount_amount"]
    ) - amount(order["coupon_discount_amount"]) - amount(
        order["point_discount_amount"]
    ) == amount(
        order["payable_amount"]
    )
    assert amount(created["payableAmount"]) == amount(order["payable_amount"])

    cancel_response = client.post(
        f"/api/v1/orders/{created['orderId']}/cancel",
        headers=auth_headers,
        json={"cancelReason": "矩阵测试取消"},
    )
    assert cancel_response.status_code == 200, cancel_response.text
    assert cancel_response.json()["statusCode"] == "cancelled"
    assert inventory_for(product_type, case) == before_inventory
