from __future__ import annotations

import json
from datetime import datetime, timedelta
from decimal import ROUND_DOWN, Decimal
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, Header, Path, Query
from pydantic import BaseModel, Field

from ..config import DEMO_PAYMENT_SIGNATURE
from ..database import db_cursor, fetch_all, fetch_one
from ..dependencies import get_current_user_id
from ..errors import bad_request, conflict, not_found, unauthorized
from ..utils import (
    count_total,
    format_datetime,
    local_now,
    make_no,
    money,
    offset_limit,
    parse_date,
    parse_datetime,
)

router = APIRouter(prefix="/api/v1", tags=["orders"])

VALID_PRODUCT_TYPES = {
    "hotel_room",
    "scenic_ticket",
    "flight_cabin",
    "train_seat",
    "bus_seat",
    "transfer_service",
}
REQUIRES_TRAVELER = {"flight_cabin", "train_seat", "bus_seat"}
PAYMENT_METHODS = {"alipay", "wechat", "unionpay"}
POINTS_PER_CURRENCY = Decimal("10")
PRODUCT_TYPE_ENUM_DESC = (
    "取值：hotel_room=酒店房型，scenic_ticket=景点票种，flight_cabin=航班舱位，"
    "train_seat=火车席位，bus_seat=汽车席位，transfer_service=接送服务。"
)
ORDER_STATUS_ENUM_DESC = "取值：pending_payment=待支付，cancelled=已取消，paid=已支付，in_progress=进行中，finished=已结束。"
PAYMENT_METHOD_ENUM_DESC = "取值：alipay=支付宝，wechat=微信支付，unionpay=银联。"
PAYMENT_STATUS_ENUM_DESC = (
    "取值：pending=待支付，success=支付成功，failed=支付失败，closed=已关闭。"
)
CHANNEL_ENUM_DESC = "取值：app=App，web=Web站，miniapp=小程序，h5=H5页。"
CURRENCY_ENUM_DESC = "取值：CNY=人民币，USD=美元，HKD=港币。"
CLIENT_TYPE_ENUM_DESC = "取值：app=App，web=Web站，miniapp=小程序，h5=H5页。"
PAYMENT_CALLBACK_STATUS_CODES = {"success", "failed", "closed"}
PAYMENT_EXPIRE_MINUTES = 15


class OrderCreateItem(BaseModel):
    productTypeCode: str = Field(
        description=f"商品类型编码，必须与订单 orderTypeCode 一致。{PRODUCT_TYPE_ENUM_DESC}"
    )
    productId: int = Field(
        description="商品库存/价格对象 ID；酒店为 hotel_room_types.id，景点为 scenic_ticket_types.id，交通和接送为对应库存或服务 ID。"
    )
    productName: str = Field(
        description="前端展示用商品名称；服务端仍会重新读取数据库商品快照并校验价格。"
    )
    quantity: int = Field(
        default=1,
        ge=1,
        description="购买数量，必须大于等于 1；需要出行人的商品要求 travelerIds 数量与 quantity 一致。",
    )
    travelTime: str | None = Field(
        default=None,
        description="出行时间，非酒店商品必填，格式 YYYY-MM-DD HH:mm:ss 或 YYYY-MM-DDTHH:mm:ss。",
    )
    checkInDate: str | None = Field(
        default=None, description="酒店入住日期，仅 hotel_room 必填，格式 YYYY-MM-DD。"
    )
    checkOutDate: str | None = Field(
        default=None,
        description="酒店离店日期，仅 hotel_room 必填，格式 YYYY-MM-DD；必须晚于 checkInDate。",
    )
    travelerIds: list[int] = Field(
        default_factory=list,
        description="出行人 ID 列表，必须属于当前用户且状态为 active；机票、火车票、汽车票每个购买单元必须传一个。",
    )


class OrderCreateRequest(BaseModel):
    orderTypeCode: str = Field(description=f"订单类型编码，{PRODUCT_TYPE_ENUM_DESC}")
    sourceChannelCode: str = Field(
        description=f"下单渠道编码，对应 channels.channel_code。{CHANNEL_ENUM_DESC}"
    )
    currencyCode: str = Field(
        description=f"订单币种编码，对应 currencies.currency_code。{CURRENCY_ENUM_DESC}"
    )
    items: list[OrderCreateItem] = Field(
        description="订单明细列表；当前接口要求所有明细 productTypeCode 与 orderTypeCode 一致。"
    )
    userCouponIds: list[int] = Field(
        default_factory=list,
        description="用户券 ID 列表，对应 user_coupons.id；必须属于当前用户且可用于当前订单。",
    )
    usePoints: bool = Field(
        default=False,
        description="是否使用会员积分抵扣；true 时服务端按当前积分余额和订单金额重新计算可抵扣额度。",
    )


class OrderCancelRequest(BaseModel):
    cancelReason: str = Field(description="取消原因，会写入 orders.cancel_reason。")


class OrderPayRequest(BaseModel):
    paymentMethodCode: str = Field(
        description=f"支付方式编码，{PAYMENT_METHOD_ENUM_DESC}"
    )
    clientType: str = Field(
        description=f"支付发起客户端类型，用于生成模拟支付拉起参数。{CLIENT_TYPE_ENUM_DESC}"
    )


class PaymentCallbackRequest(BaseModel):
    paymentNo: str = Field(description="支付单号，对应 payments.payment_no。")
    orderId: int = Field(
        description="订单 ID，对应 payments.order_id；必须与支付单所属订单一致。"
    )
    paymentMethodCode: str = Field(
        description=f"支付方式编码，必须与支付单一致。{PAYMENT_METHOD_ENUM_DESC}"
    )
    amount: Decimal = Field(
        description="支付渠道回传金额，必须与 payments.amount 完全一致。"
    )
    statusCode: str = Field(
        description="支付渠道回传状态；取值：success=支付成功，failed=支付失败，closed=支付关闭。"
    )
    paidAt: str | None = Field(
        default=None,
        description="支付成功时间；statusCode=success 时必填，格式 YYYY-MM-DD HH:mm:ss 或 YYYY-MM-DDTHH:mm:ss。",
    )
    channelTradeNo: str | None = Field(
        default=None,
        description="支付渠道交易号；演示数据库未单独存储，仅用于接口入参完整表达。",
    )


class PaymentCloseRequest(BaseModel):
    closeReason: str = Field(
        description="关闭原因；当前演示接口记录支付关闭状态，不单独存储关闭原因。"
    )


def _loads(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, (dict, list)):
        return value
    return json.loads(value)


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value))


def _cursor_fetchone_dict(cursor) -> dict[str, Any] | None:
    return cast(dict[str, Any] | None, cursor.fetchone())


def _cursor_fetchall_dicts(cursor) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], list(cursor.fetchall()))


def _point_discount(points_balance: int, remaining: Decimal) -> tuple[int, Decimal]:
    if points_balance <= 0 or remaining <= Decimal("0.00"):
        return 0, Decimal("0.00")
    max_points = int(
        (remaining * POINTS_PER_CURRENCY).to_integral_value(rounding=ROUND_DOWN)
    )
    points_used = min(points_balance, max_points)
    points_used -= points_used % int(POINTS_PER_CURRENCY)
    discount = (Decimal(points_used) / POINTS_PER_CURRENCY).quantize(Decimal("0.01"))
    return points_used, discount


def _coupon_discount_amount(coupon: dict[str, Any], sale_amount: Decimal) -> Decimal:
    discount_value = _decimal(coupon["discount_amount"])
    if coupon["coupon_type_code"].endswith("_DISCOUNT"):
        amount = (sale_amount * (Decimal("1.00") - discount_value)).quantize(
            Decimal("0.01")
        )
        if coupon["max_discount_amount"] is not None:
            amount = min(amount, _decimal(coupon["max_discount_amount"]))
        return max(Decimal("0.00"), amount)
    return min(sale_amount, discount_value)


def _promotion_discount_amount(rule: dict[str, Any], sale_amount: Decimal) -> Decimal:
    payload = _loads(rule["benefit_payload"], {})
    if rule["benefit_type_code"] == "discount_rate":
        rate = Decimal(str(payload.get("discount_rate", "1.00")))
        return max(
            Decimal("0.00"),
            (sale_amount * (Decimal("1.00") - rate)).quantize(Decimal("0.01")),
        )
    return min(sale_amount, _decimal(payload.get("discount_amount", 0)))


def _ensure_order_owned(order_id: int, current_user_id: int) -> dict[str, Any]:
    order = fetch_one(
        """
        SELECT *
        FROM orders
        WHERE id = %s AND user_id = %s
        """,
        (order_id, current_user_id),
    )
    if order is None:
        raise not_found("订单不存在")
    return order


def _ensure_payment_owned(payment_id: int, current_user_id: int) -> dict[str, Any]:
    payment = fetch_one(
        """
        SELECT *
        FROM payments
        WHERE id = %s AND user_id = %s
        """,
        (payment_id, current_user_id),
    )
    if payment is None:
        raise not_found("支付记录不存在")
    return payment


def _payment_status_payload(payment: dict[str, Any]) -> dict[str, Any]:
    return {
        "paymentId": payment["id"],
        "paymentNo": payment["payment_no"],
        "orderId": payment["order_id"],
        "paymentMethodCode": payment["payment_method_code"],
        "amount": money(payment["amount"]),
        "statusCode": payment["status_code"],
        "paidAt": format_datetime(payment["paid_at"]),
        "createdAt": format_datetime(payment["created_at"]),
    }


def _ensure_channel(channel_code: str) -> None:
    row = fetch_one(
        """
        SELECT channel_code
        FROM channels
        WHERE channel_code = %s AND status_code = 'active'
        """,
        (channel_code,),
    )
    if row is None:
        raise bad_request("sourceChannelCode 不合法")


def _validate_travelers(
    product_type: str, traveler_ids: list[int], quantity: int, current_user_id: int
) -> list[int]:
    if product_type in REQUIRES_TRAVELER and len(traveler_ids) != quantity:
        raise bad_request("当前商品类型必须为每个购买单元传入一个 travelerId")
    if not traveler_ids:
        return []
    placeholders = ", ".join(["%s"] * len(traveler_ids))
    rows = fetch_all(
        f"""
        SELECT id
        FROM travelers
        WHERE user_id = %s AND status_code = 'active' AND id IN ({placeholders})
        """,
        tuple([current_user_id] + traveler_ids),
    )
    existing_ids = {int(row["id"]) for row in rows}
    if existing_ids != set(traveler_ids):
        raise bad_request("travelerIds 中存在无效出行人")
    return traveler_ids


def _hotel_product(
    product_id: int, check_in_date: str, check_out_date: str
) -> dict[str, Any]:
    check_in = parse_date(check_in_date, "checkInDate")
    check_out = parse_date(check_out_date, "checkOutDate")
    if check_in >= check_out:
        raise bad_request("checkInDate 必须早于 checkOutDate")
    rows = fetch_all(
        """
        SELECT
            rt.id AS product_id,
            CONCAT(h.hotel_name, '-', rt.room_type_name) AS product_name,
            d.business_date,
            d.sale_price_amount,
            d.settlement_price_amount,
            d.currency_code
        FROM hotel_room_types rt
        JOIN hotels h ON h.id = rt.hotel_id AND h.status_code = 'active'
        JOIN hotel_room_daily d
          ON d.room_type_id = rt.id
         AND d.business_date >= %s
         AND d.business_date < %s
         AND d.status_code = 'active'
         AND d.available_inventory > 0
        WHERE rt.id = %s AND rt.status_code = 'active'
        ORDER BY d.business_date ASC
        """,
        (check_in_date, check_out_date, product_id),
    )
    stay_nights = (check_out - check_in).days
    if len(rows) != stay_nights:
        raise conflict("酒店商品不可售或库存不足")
    return {
        "product_id": rows[0]["product_id"],
        "product_name": rows[0]["product_name"],
        "sale_price_amount": sum(_decimal(row["sale_price_amount"]) for row in rows),
        "settlement_price_amount": sum(
            _decimal(row["settlement_price_amount"]) for row in rows
        ),
        "currency_code": rows[0]["currency_code"],
        "travel_time": datetime.strptime(
            f"{check_in_date} 00:00:00", "%Y-%m-%d %H:%M:%S"
        ),
        "travel_end_time": datetime.strptime(
            f"{check_out_date} 00:00:00", "%Y-%m-%d %H:%M:%S"
        ),
    }


def _scenic_product(product_id: int, travel_time: datetime) -> dict[str, Any]:
    row = fetch_one(
        """
        SELECT
            t.id AS product_id,
            CONCAT(s.scenic_name, '-', t.ticket_type_name) AS product_name,
            d.sale_price_amount,
            d.settlement_price_amount,
            d.currency_code
        FROM scenic_ticket_types t
        JOIN scenic_spots s ON s.id = t.scenic_spot_id AND s.status_code = 'active'
        JOIN scenic_ticket_daily d
          ON d.ticket_type_id = t.id
         AND d.business_date = DATE(%s)
         AND d.status_code = 'active'
         AND d.available_inventory > 0
        WHERE t.id = %s AND t.status_code = 'active'
        """,
        (travel_time, product_id),
    )
    if row is None:
        raise conflict("景点商品不可售或库存不足")
    return row


def _flight_product(product_id: int) -> dict[str, Any]:
    row = fetch_one(
        """
        SELECT
            i.id AS product_id,
            CONCAT(r.flight_no, '-', i.cabin_class_code) AS product_name,
            i.sale_price_amount,
            i.settlement_price_amount,
            i.currency_code,
            d.departure_time AS travel_time
        FROM flight_cabin_inventory i
        JOIN flight_departures d ON d.id = i.flight_departure_id AND d.status_code = 'scheduled'
        JOIN flight_routes r ON r.id = d.flight_route_id AND r.status_code = 'active'
        WHERE i.id = %s AND i.status_code = 'active' AND i.available_inventory > 0
        """,
        (product_id,),
    )
    if row is None:
        raise conflict("机票商品不可售或库存不足")
    return row


def _train_product(product_id: int) -> dict[str, Any]:
    row = fetch_one(
        """
        SELECT
            i.id AS product_id,
            CONCAT(r.train_no, '-', i.seat_class_code) AS product_name,
            i.sale_price_amount,
            i.settlement_price_amount,
            i.currency_code,
            d.departure_time AS travel_time
        FROM train_seat_inventory i
        JOIN train_departures d ON d.id = i.train_departure_id AND d.status_code = 'scheduled'
        JOIN train_routes r ON r.id = d.train_route_id AND r.status_code = 'active'
        WHERE i.id = %s AND i.status_code = 'active' AND i.available_inventory > 0
        """,
        (product_id,),
    )
    if row is None:
        raise conflict("火车票商品不可售或库存不足")
    return row


def _bus_product(product_id: int) -> dict[str, Any]:
    row = fetch_one(
        """
        SELECT
            i.id AS product_id,
            CONCAT(r.route_name, '-', i.seat_class_code) AS product_name,
            i.sale_price_amount,
            i.settlement_price_amount,
            i.currency_code,
            d.departure_time AS travel_time
        FROM bus_seat_inventory i
        JOIN bus_departures d ON d.id = i.bus_departure_id AND d.status_code = 'scheduled'
        JOIN bus_routes r ON r.id = d.bus_route_id AND r.status_code = 'active'
        WHERE i.id = %s AND i.status_code = 'active' AND i.available_inventory > 0
        """,
        (product_id,),
    )
    if row is None:
        raise conflict("汽车票商品不可售或库存不足")
    return row


def _transfer_product(product_id: int, travel_time: datetime) -> dict[str, Any]:
    row = fetch_one(
        """
        SELECT
            s.id AS product_id,
            s.service_name AS product_name,
            COALESCE(MIN(r.price_amount), 0.00) AS sale_price_amount,
            COALESCE(MIN(r.min_price_amount), 0.00) AS settlement_price_amount,
            'CNY' AS currency_code
        FROM transfer_services s
        JOIN transfer_capacity_calendar c
          ON c.transfer_service_id = s.id
         AND c.business_date = DATE(%s)
         AND c.status_code = 'active'
         AND c.available_inventory > 0
        LEFT JOIN transfer_service_area_rules r
          ON r.transfer_service_id = s.id
         AND r.status_code = 'active'
        WHERE s.id = %s AND s.status_code = 'active'
        GROUP BY s.id
        """,
        (travel_time, product_id),
    )
    if row is None:
        raise conflict("接送服务商品不可售或库存不足")
    return row


def _fetch_product_snapshot(
    product_type: str,
    product_id: int,
    travel_time: datetime | None = None,
    check_in_date: str | None = None,
    check_out_date: str | None = None,
) -> dict[str, Any]:
    if product_type == "hotel_room":
        if not check_in_date or not check_out_date:
            raise bad_request("酒店商品下单必须传入 checkInDate 和 checkOutDate")
        return _hotel_product(product_id, check_in_date, check_out_date)
    if product_type == "scenic_ticket":
        if travel_time is None:
            raise bad_request("travelTime 不能为空")
        return _scenic_product(product_id, travel_time)
    if product_type == "flight_cabin":
        return _flight_product(product_id)
    if product_type == "train_seat":
        return _train_product(product_id)
    if product_type == "bus_seat":
        return _bus_product(product_id)
    if product_type == "transfer_service":
        if travel_time is None:
            raise bad_request("travelTime 不能为空")
        return _transfer_product(product_id, travel_time)
    raise bad_request("productTypeCode 不合法")


def _reserve_inventory(
    cursor,
    product_type: str,
    product_id: int,
    travel_time: datetime,
    travel_end_time: datetime | None = None,
    now: datetime | None = None,
) -> None:
    updated_at = now or local_now()
    if product_type == "hotel_room":
        affected = cursor.execute(
            """
            UPDATE hotel_room_daily
            SET available_inventory = available_inventory - 1,
                reserved_inventory = reserved_inventory + 1,
                updated_at = %s
            WHERE room_type_id = %s
              AND business_date >= DATE(%s)
              AND business_date < DATE(%s)
              AND status_code = 'active'
              AND available_inventory > 0
            """,
            (updated_at, product_id, travel_time, travel_end_time),
        )
        stay_nights = (
            (travel_end_time.date() - travel_time.date()).days if travel_end_time else 0
        )
        if affected != stay_nights:
            raise conflict("酒店商品库存不足")
        return
    elif product_type == "scenic_ticket":
        affected = cursor.execute(
            """
            UPDATE scenic_ticket_daily
            SET available_inventory = available_inventory - 1,
                reserved_inventory = reserved_inventory + 1,
                updated_at = %s
            WHERE ticket_type_id = %s
              AND business_date = DATE(%s)
              AND status_code = 'active'
              AND available_inventory > 0
            """,
            (updated_at, product_id, travel_time),
        )
    elif product_type == "flight_cabin":
        affected = cursor.execute(
            """
            UPDATE flight_cabin_inventory
            SET available_inventory = available_inventory - 1,
                reserved_inventory = reserved_inventory + 1,
                updated_at = %s
            WHERE id = %s AND status_code = 'active' AND available_inventory > 0
            """,
            (updated_at, product_id),
        )
    elif product_type == "train_seat":
        affected = cursor.execute(
            """
            UPDATE train_seat_inventory
            SET available_inventory = available_inventory - 1,
                reserved_inventory = reserved_inventory + 1,
                updated_at = %s
            WHERE id = %s AND status_code = 'active' AND available_inventory > 0
            """,
            (updated_at, product_id),
        )
    elif product_type == "bus_seat":
        affected = cursor.execute(
            """
            UPDATE bus_seat_inventory
            SET available_inventory = available_inventory - 1,
                reserved_inventory = reserved_inventory + 1,
                updated_at = %s
            WHERE id = %s AND status_code = 'active' AND available_inventory > 0
            """,
            (updated_at, product_id),
        )
    else:
        affected = cursor.execute(
            """
            UPDATE transfer_capacity_calendar
            SET available_inventory = available_inventory - 1,
                reserved_inventory = reserved_inventory + 1,
                updated_at = %s
            WHERE transfer_service_id = %s
              AND business_date = DATE(%s)
              AND status_code = 'active'
              AND available_inventory > 0
            """,
            (updated_at, product_id, travel_time),
        )
    if affected != 1:
        raise conflict("商品库存不足")


def _release_inventory(
    cursor,
    product_type: str,
    product_id: int,
    travel_time: datetime,
    travel_end_time: datetime | None = None,
    now: datetime | None = None,
) -> None:
    updated_at = now or local_now()
    if product_type == "hotel_room":
        cursor.execute(
            """
            UPDATE hotel_room_daily
            SET available_inventory = available_inventory + 1,
                reserved_inventory = GREATEST(reserved_inventory - 1, 0),
                updated_at = %s
            WHERE room_type_id = %s
              AND business_date >= DATE(%s)
              AND business_date < DATE(%s)
            """,
            (updated_at, product_id, travel_time, travel_end_time),
        )
    elif product_type == "scenic_ticket":
        cursor.execute(
            """
            UPDATE scenic_ticket_daily
            SET available_inventory = available_inventory + 1,
                reserved_inventory = GREATEST(reserved_inventory - 1, 0),
                updated_at = %s
            WHERE ticket_type_id = %s AND business_date = DATE(%s)
            """,
            (updated_at, product_id, travel_time),
        )
    elif product_type == "flight_cabin":
        cursor.execute(
            """
            UPDATE flight_cabin_inventory
            SET available_inventory = available_inventory + 1,
                reserved_inventory = GREATEST(reserved_inventory - 1, 0),
                updated_at = %s
            WHERE id = %s
            """,
            (updated_at, product_id),
        )
    elif product_type == "train_seat":
        cursor.execute(
            """
            UPDATE train_seat_inventory
            SET available_inventory = available_inventory + 1,
                reserved_inventory = GREATEST(reserved_inventory - 1, 0),
                updated_at = %s
            WHERE id = %s
            """,
            (updated_at, product_id),
        )
    elif product_type == "bus_seat":
        cursor.execute(
            """
            UPDATE bus_seat_inventory
            SET available_inventory = available_inventory + 1,
                reserved_inventory = GREATEST(reserved_inventory - 1, 0),
                updated_at = %s
            WHERE id = %s
            """,
            (updated_at, product_id),
        )
    else:
        cursor.execute(
            """
            UPDATE transfer_capacity_calendar
            SET available_inventory = available_inventory + 1,
                reserved_inventory = GREATEST(reserved_inventory - 1, 0),
                updated_at = %s
            WHERE transfer_service_id = %s AND business_date = DATE(%s)
            """,
            (updated_at, product_id, travel_time),
        )


def _capture_inventory(
    cursor,
    product_type: str,
    product_id: int,
    travel_time: datetime,
    travel_end_time: datetime | None = None,
    now: datetime | None = None,
) -> None:
    updated_at = now or local_now()
    if product_type == "hotel_room":
        cursor.execute(
            """
            UPDATE hotel_room_daily
            SET reserved_inventory = GREATEST(reserved_inventory - 1, 0),
                sold_inventory = sold_inventory + 1,
                updated_at = %s
            WHERE room_type_id = %s
              AND business_date >= DATE(%s)
              AND business_date < DATE(%s)
            """,
            (updated_at, product_id, travel_time, travel_end_time),
        )
    elif product_type == "scenic_ticket":
        cursor.execute(
            """
            UPDATE scenic_ticket_daily
            SET reserved_inventory = GREATEST(reserved_inventory - 1, 0),
                sold_inventory = sold_inventory + 1,
                updated_at = %s
            WHERE ticket_type_id = %s AND business_date = DATE(%s)
            """,
            (updated_at, product_id, travel_time),
        )
    elif product_type == "flight_cabin":
        cursor.execute(
            """
            UPDATE flight_cabin_inventory
            SET reserved_inventory = GREATEST(reserved_inventory - 1, 0),
                sold_inventory = sold_inventory + 1,
                updated_at = %s
            WHERE id = %s
            """,
            (updated_at, product_id),
        )
    elif product_type == "train_seat":
        cursor.execute(
            """
            UPDATE train_seat_inventory
            SET reserved_inventory = GREATEST(reserved_inventory - 1, 0),
                sold_inventory = sold_inventory + 1,
                updated_at = %s
            WHERE id = %s
            """,
            (updated_at, product_id),
        )
    elif product_type == "bus_seat":
        cursor.execute(
            """
            UPDATE bus_seat_inventory
            SET reserved_inventory = GREATEST(reserved_inventory - 1, 0),
                sold_inventory = sold_inventory + 1,
                updated_at = %s
            WHERE id = %s
            """,
            (updated_at, product_id),
        )
    else:
        cursor.execute(
            """
            UPDATE transfer_capacity_calendar
            SET reserved_inventory = GREATEST(reserved_inventory - 1, 0),
                sold_inventory = sold_inventory + 1,
                updated_at = %s
            WHERE transfer_service_id = %s AND business_date = DATE(%s)
            """,
            (updated_at, product_id, travel_time),
        )


def _promotion_rows(
    product_type: str, product_id: int, now: datetime
) -> list[dict[str, Any]]:
    return fetch_all(
        """
        SELECT
            p.id AS promotion_id,
            p.promotion_name,
            pb.id AS promotion_binding_id,
            pr.id AS promotion_rule_id,
            pr.trigger_type_code,
            pr.trigger_payload,
            pr.benefit_type_code,
            pr.benefit_payload
        FROM promotion_bindings pb
        JOIN promotions p
          ON p.id = pb.promotion_id
         AND p.status_code = 'active'
         AND %s BETWEEN p.start_time AND p.end_time
        LEFT JOIN promotion_rules pr
          ON pr.promotion_id = p.id
         AND pr.status_code = 'active'
        WHERE pb.product_type_code = %s
          AND pb.target_id = %s
          AND pb.status_code = 'active'
        ORDER BY p.id ASC, pr.sort_order ASC, pr.id ASC
        """,
        (now, product_type, product_id),
    )


def _match_promotion(
    rule: dict[str, Any], sale_amount: Decimal, quantity: int, travel_time: datetime
) -> bool:
    if rule["promotion_rule_id"] is None:
        return True
    payload = _loads(rule["trigger_payload"], {})
    trigger_type = rule["trigger_type_code"]
    if trigger_type == "min_spend":
        return sale_amount >= _decimal(payload.get("min_spend", 0))
    if trigger_type == "product_count":
        return quantity >= int(payload.get("min_count", 1))
    if trigger_type == "time_window":
        time_window = payload.get("time_window")
        if not time_window or "-" not in time_window:
            return False
        start_text, end_text = time_window.split("-", 1)
        current_text = travel_time.strftime("%H:%M")
        return start_text <= current_text <= end_text
    return False


def _order_items(order_id: int) -> list[dict[str, Any]]:
    return fetch_all(
        """
        SELECT
            oi.id,
            oi.product_type_code,
            oi.product_id,
            oi.product_name,
            oi.sale_amount,
            oi.refunded_amount,
            oi.settlement_amount,
            oi.status_code,
            oi.travel_time,
            oi.travel_end_time,
            oi.traveler_id,
            t.traveler_name
        FROM order_items oi
        LEFT JOIN travelers t ON t.id = oi.traveler_id
        WHERE oi.order_id = %s
        ORDER BY oi.id ASC
        """,
        (order_id,),
    )


def _order_items_for_update(cursor, order_id: int) -> list[dict[str, Any]]:
    cursor.execute(
        """
        SELECT
            id,
            product_type_code,
            product_id,
            sale_amount,
            settlement_amount,
            status_code,
            travel_time,
            travel_end_time
        FROM order_items
        WHERE order_id = %s
        ORDER BY id ASC
        FOR UPDATE
        """,
        (order_id,),
    )
    return _cursor_fetchall_dicts(cursor)


def _paid_order_settlement_amount(
    order: dict[str, Any], items: list[dict[str, Any]]
) -> Decimal:
    item_settlement = sum(
        (
            _decimal(
                item["settlement_amount"]
                if item["settlement_amount"] is not None
                else item["sale_amount"]
            )
            for item in items
        ),
        Decimal("0.00"),
    )
    if item_settlement > Decimal("0.00"):
        return item_settlement
    return _decimal(order["payable_amount"])


def _member_level_from_growth(growth_value: int) -> str:
    if growth_value >= 12000:
        return "gold"
    if growth_value >= 5000:
        return "silver"
    return "normal"


def _complete_successful_payment(
    cursor,
    payment_id: int,
    paid_at: datetime,
    now: datetime,
) -> tuple[dict[str, Any], dict[str, Any], bool]:
    cursor.execute(
        """
        SELECT *
        FROM payments
        WHERE id = %s
        FOR UPDATE
        """,
        (payment_id,),
    )
    payment = _cursor_fetchone_dict(cursor)
    if payment is None:
        raise not_found("支付记录不存在")

    cursor.execute(
        """
        SELECT *
        FROM orders
        WHERE id = %s
        FOR UPDATE
        """,
        (payment["order_id"],),
    )
    order = _cursor_fetchone_dict(cursor)
    if order is None:
        raise not_found("订单不存在")

    if payment["status_code"] == "success":
        return payment, order, False
    if payment["status_code"] in {"failed", "closed"}:
        raise conflict("当前支付记录已是终态，不能改为支付成功")

    cursor.execute(
        """
        SELECT id
        FROM payments
        WHERE order_id = %s AND status_code = 'success' AND id <> %s
        LIMIT 1
        FOR UPDATE
        """,
        (payment["order_id"], payment_id),
    )
    if cursor.fetchone() is not None:
        raise conflict("订单已存在成功支付记录")
    if order["status_code"] != "pending_payment":
        raise conflict("当前订单状态不允许支付成功")

    items = _order_items_for_update(cursor, payment["order_id"])
    settlement_amount = _paid_order_settlement_amount(order, items)
    paid_amount = _decimal(payment["amount"])

    for item in items:
        _capture_inventory(
            cursor,
            item["product_type_code"],
            item["product_id"],
            item["travel_time"],
            item["travel_end_time"],
            now,
        )

    cursor.execute(
        """
        UPDATE payments
        SET status_code = 'success',
            paid_at = %s,
            updated_at = %s
        WHERE id = %s
        """,
        (paid_at, now, payment_id),
    )
    cursor.execute(
        """
        UPDATE orders
        SET status_code = 'paid',
            paid_amount = %s,
            settlement_amount = %s,
            paid_at = %s,
            updated_at = %s
        WHERE id = %s
        """,
        (paid_amount, settlement_amount, paid_at, now, payment["order_id"]),
    )
    cursor.execute(
        """
        UPDATE order_items
        SET status_code = 'paid',
            paid_at = %s,
            updated_at = %s
        WHERE order_id = %s
          AND status_code = 'pending_payment'
        """,
        (paid_at, now, payment["order_id"]),
    )

    points_earned = int(paid_amount.to_integral_value(rounding=ROUND_DOWN))
    if points_earned > 0:
        cursor.execute(
            """
            SELECT *
            FROM member_accounts
            WHERE user_id = %s
            FOR UPDATE
            """,
            (payment["user_id"],),
        )
        member_account = _cursor_fetchone_dict(cursor)
        if member_account is None:
            raise conflict("当前用户会员账户不存在")
        new_balance = int(member_account["points_balance"]) + points_earned
        new_total_points = int(member_account["total_points"]) + points_earned
        new_growth_value = int(member_account["growth_value"]) + points_earned
        cursor.execute(
            """
            INSERT INTO member_point_ledger (
                user_id, ledger_type_code, points_delta, balance_after, created_at
            ) VALUES (%s, 'order_earn', %s, %s, %s)
            """,
            (payment["user_id"], points_earned, new_balance, now),
        )
        cursor.execute(
            """
            UPDATE member_accounts
            SET member_level_code = %s,
                points_balance = %s,
                total_points = %s,
                growth_value = %s,
                updated_at = %s
            WHERE user_id = %s
            """,
            (
                _member_level_from_growth(new_growth_value),
                new_balance,
                new_total_points,
                new_growth_value,
                now,
                payment["user_id"],
            ),
        )

    cursor.execute("SELECT * FROM payments WHERE id = %s", (payment_id,))
    updated_payment = _cursor_fetchone_dict(cursor)
    cursor.execute("SELECT * FROM orders WHERE id = %s", (payment["order_id"],))
    updated_order = _cursor_fetchone_dict(cursor)
    if updated_payment is None or updated_order is None:
        raise conflict("支付成功后置处理失败")
    return updated_payment, updated_order, True


def _cancel_pending_order_in_tx(
    cursor, order: dict[str, Any], cancel_reason: str, now: datetime
) -> bool:
    if order["status_code"] != "pending_payment":
        return False
    items = _order_items_for_update(cursor, order["id"])
    for item in items:
        _release_inventory(
            cursor,
            item["product_type_code"],
            item["product_id"],
            item["travel_time"],
            item["travel_end_time"],
            now,
        )
    cursor.execute(
        """
        UPDATE payments
        SET status_code = 'closed',
            updated_at = %s
        WHERE order_id = %s
          AND status_code = 'pending'
        """,
        (now, order["id"]),
    )
    cursor.execute(
        """
        UPDATE order_items
        SET status_code = 'cancelled',
            cancelled_at = %s,
            updated_at = %s
        WHERE order_id = %s
          AND status_code = 'pending_payment'
        """,
        (now, now, order["id"]),
    )
    cursor.execute(
        """
        UPDATE orders
        SET status_code = 'cancelled',
            cancel_reason = %s,
            finalized_at = %s,
            updated_at = %s
        WHERE id = %s
        """,
        (cancel_reason, now, now, order["id"]),
    )
    cursor.execute(
        """
        SELECT user_coupon_id
        FROM order_coupon_usages
        WHERE order_id = %s
        """,
        (order["id"],),
    )
    coupon_usages = _cursor_fetchall_dicts(cursor)
    for coupon_usage in coupon_usages:
        cursor.execute(
            """
            UPDATE user_coupons
            SET status_code = 'available',
                used_at = NULL,
                updated_at = %s
            WHERE id = %s AND user_id = %s
            """,
            (now, coupon_usage["user_coupon_id"], order["user_id"]),
        )
    if coupon_usages:
        cursor.execute(
            "DELETE FROM order_coupon_usages WHERE order_id = %s", (order["id"],)
        )

    cursor.execute(
        """
        SELECT point_ledger_id, points_used
        FROM order_point_usages
        WHERE order_id = %s
        """,
        (order["id"],),
    )
    point_usage = _cursor_fetchone_dict(cursor)
    if point_usage is not None:
        cursor.execute(
            """
            UPDATE member_accounts
            SET points_balance = points_balance + %s,
                updated_at = %s
            WHERE user_id = %s
            """,
            (point_usage["points_used"], now, order["user_id"]),
        )
        cursor.execute(
            "DELETE FROM order_point_usages WHERE order_id = %s", (order["id"],)
        )
        cursor.execute(
            "DELETE FROM member_point_ledger WHERE id = %s AND user_id = %s",
            (point_usage["point_ledger_id"], order["user_id"]),
        )
    return True


def close_expired_pending_orders(limit: int = 100) -> dict[str, int]:
    now = local_now()
    expire_before = now - timedelta(minutes=PAYMENT_EXPIRE_MINUTES)
    closed_count = 0
    with db_cursor() as (_, cursor):
        cursor.execute(
            """
            SELECT o.*
            FROM orders o
            JOIN (
                SELECT order_id, MAX(created_at) AS latest_pending_payment_created_at
                FROM payments
                WHERE status_code = 'pending'
                GROUP BY order_id
            ) p ON p.order_id = o.id
            WHERE o.status_code = 'pending_payment'
              AND p.latest_pending_payment_created_at < %s
            ORDER BY p.latest_pending_payment_created_at ASC, o.id ASC
            LIMIT %s
            FOR UPDATE
            """,
            (expire_before, limit),
        )
        orders = _cursor_fetchall_dicts(cursor)
        for order in orders:
            if _cancel_pending_order_in_tx(cursor, order, "payment_timeout", now):
                closed_count += 1
    return {"closedCount": closed_count}


@router.post("/orders", summary="创建订单")
def create_order(
    body: OrderCreateRequest,
    current_user_id: Annotated[int, Depends(get_current_user_id)],
):
    if body.orderTypeCode not in VALID_PRODUCT_TYPES:
        raise bad_request("orderTypeCode 不合法")
    if not body.items:
        raise bad_request("items 不能为空")
    _ensure_channel(body.sourceChannelCode)
    member_account = fetch_one(
        """
        SELECT user_id, points_balance
        FROM member_accounts
        WHERE user_id = %s
        """,
        (current_user_id,),
    )
    if member_account is None:
        raise conflict("当前用户会员账户不存在")

    now = local_now()
    expanded_units: list[dict[str, Any]] = []
    for item in body.items:
        if item.productTypeCode != body.orderTypeCode:
            raise bad_request("所有明细的 productTypeCode 必须与 orderTypeCode 一致")
        traveler_ids = _validate_travelers(
            item.productTypeCode, item.travelerIds, item.quantity, current_user_id
        )
        travel_time = None
        if item.productTypeCode != "hotel_room":
            if item.travelTime is None:
                raise bad_request("travelTime 不能为空")
            travel_time = parse_datetime(item.travelTime, "travelTime")
        product = _fetch_product_snapshot(
            item.productTypeCode,
            item.productId,
            travel_time=travel_time,
            check_in_date=item.checkInDate,
            check_out_date=item.checkOutDate,
        )
        if product["currency_code"] != body.currencyCode:
            raise conflict("商品币种与订单币种不一致")
        actual_travel_time = product.get("travel_time") or travel_time
        actual_travel_end_time = product.get("travel_end_time")
        for index in range(item.quantity):
            traveler_id = traveler_ids[index] if index < len(traveler_ids) else None
            expanded_units.append(
                {
                    "productTypeCode": item.productTypeCode,
                    "productId": item.productId,
                    "productName": product["product_name"],
                    "saleAmount": _decimal(product["sale_price_amount"]),
                    "settlementAmount": _decimal(product["settlement_price_amount"]),
                    "currencyCode": product["currency_code"],
                    "travelTime": actual_travel_time,
                    "travelEndTime": actual_travel_end_time,
                    "travelerId": traveler_id,
                }
            )

    goods_amount = sum(unit["saleAmount"] for unit in expanded_units)
    promotion_discount = Decimal("0.00")
    promotion_details: list[dict[str, Any]] = []
    for unit in expanded_units:
        candidate_rules = _promotion_rows(
            unit["productTypeCode"], unit["productId"], now
        )
        best_match: dict[str, Any] | None = None
        best_amount = Decimal("0.00")
        for rule in candidate_rules:
            if not _match_promotion(rule, unit["saleAmount"], 1, unit["travelTime"]):
                continue
            amount = _promotion_discount_amount(rule, unit["saleAmount"])
            if amount > best_amount:
                best_amount = amount
                best_match = rule
        if best_match and best_amount > Decimal("0.00"):
            promotion_discount += best_amount
            promotion_details.append(
                {
                    "promotionId": best_match["promotion_id"],
                    "promotionBindingId": best_match["promotion_binding_id"],
                    "promotionRuleId": best_match["promotion_rule_id"],
                    "discountAmount": best_amount,
                }
            )

    remaining_after_promotion = max(Decimal("0.00"), goods_amount - promotion_discount)
    coupon_discount = Decimal("0.00")
    coupon_usages: list[dict[str, Any]] = []
    if body.userCouponIds:
        placeholders = ", ".join(["%s"] * len(body.userCouponIds))
        coupons = fetch_all(
            f"""
            SELECT
                uc.id,
                uc.template_id,
                uc.status_code,
                uc.min_spend_amount,
                uc.discount_amount,
                uc.max_discount_amount,
                uc.valid_from,
                uc.valid_until,
                ct.coupon_type_code,
                ct.applicable_product_type
            FROM user_coupons uc
            JOIN coupon_templates ct ON ct.id = uc.template_id
            WHERE uc.user_id = %s
              AND uc.id IN ({placeholders})
            ORDER BY uc.id ASC
            """,
            tuple([current_user_id] + body.userCouponIds),
        )
        coupon_map = {int(row["id"]): row for row in coupons}
        if len(coupon_map) != len(set(body.userCouponIds)):
            raise bad_request("userCouponIds 中存在无效优惠券")
        for coupon_id in body.userCouponIds:
            coupon = coupon_map[coupon_id]
            if coupon["status_code"] != "available" or not (
                coupon["valid_from"] <= now <= coupon["valid_until"]
            ):
                raise conflict("存在不可用优惠券")
            if coupon["applicable_product_type"] != body.orderTypeCode:
                raise conflict("优惠券不适用于当前订单类型")
            if remaining_after_promotion - coupon_discount < _decimal(
                coupon["min_spend_amount"]
            ):
                raise conflict("优惠券未满足使用门槛")
            discount_amount = _coupon_discount_amount(
                coupon, remaining_after_promotion - coupon_discount
            )
            if discount_amount <= Decimal("0.00"):
                continue
            coupon_discount += discount_amount
            coupon_usages.append(
                {
                    "userCouponId": coupon["id"],
                    "templateId": coupon["template_id"],
                    "discountAmount": discount_amount,
                }
            )

    remaining_after_coupon = max(
        Decimal("0.00"), goods_amount - promotion_discount - coupon_discount
    )
    points_used = 0
    point_discount = Decimal("0.00")
    if body.usePoints:
        points_used, point_discount = _point_discount(
            int(member_account["points_balance"]), remaining_after_coupon
        )
    payable_amount = (
        goods_amount - promotion_discount - coupon_discount - point_discount
    )
    if payable_amount < Decimal("0.00"):
        raise conflict("订单金额计算异常")

    with db_cursor() as (_, cursor):
        order_no = make_no("TR")
        cursor.execute(
            """
            INSERT INTO orders (
                order_no, user_id, order_type_code, status_code, currency_code,
                goods_amount, marketing_discount_amount, coupon_discount_amount,
                point_discount_amount, payable_amount, paid_amount, refunded_amount,
                settlement_amount, source_channel_code, cancel_reason, paid_at,
                finalized_at, created_at, updated_at
            ) VALUES (%s, %s, %s, 'pending_payment', %s, %s, %s, %s, %s, %s, NULL, NULL, NULL, %s, NULL, NULL, NULL, %s, %s)
            """,
            (
                order_no,
                current_user_id,
                body.orderTypeCode,
                body.currencyCode,
                goods_amount,
                promotion_discount,
                coupon_discount,
                point_discount,
                payable_amount,
                body.sourceChannelCode,
                now,
                now,
            ),
        )
        order_id = cursor.lastrowid
        for unit in expanded_units:
            _reserve_inventory(
                cursor,
                unit["productTypeCode"],
                unit["productId"],
                unit["travelTime"],
                unit["travelEndTime"],
                now,
            )
            cursor.execute(
                """
                INSERT INTO order_items (
                    order_id, user_id, traveler_id, product_type_code, product_id, product_name,
                    sale_amount, refunded_amount, settlement_amount, status_code, travel_time, travel_end_time,
                    cancelled_at, paid_at, refunded_at, completed_at, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, NULL, %s, 'pending_payment', %s, %s, NULL, NULL, NULL, NULL, %s, %s)
                """,
                (
                    order_id,
                    current_user_id,
                    unit["travelerId"],
                    unit["productTypeCode"],
                    unit["productId"],
                    unit["productName"],
                    unit["saleAmount"],
                    unit["settlementAmount"],
                    unit["travelTime"],
                    unit["travelEndTime"],
                    now,
                    now,
                ),
            )
        for promotion in promotion_details:
            cursor.execute(
                """
                INSERT INTO order_promotion_details (
                    order_id, order_item_id, order_type_code, promotion_id, promotion_binding_id,
                    promotion_rule_id, discount_amount, created_at, updated_at
                ) VALUES (%s, NULL, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    order_id,
                    body.orderTypeCode,
                    promotion["promotionId"],
                    promotion["promotionBindingId"],
                    promotion["promotionRuleId"],
                    promotion["discountAmount"],
                    now,
                    now,
                ),
            )
        for coupon_usage in coupon_usages:
            cursor.execute(
                """
                INSERT INTO order_coupon_usages (
                    order_id, order_item_id, user_id, template_id, user_coupon_id,
                    order_type_code, discount_amount, created_at, updated_at
                ) VALUES (%s, NULL, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    order_id,
                    current_user_id,
                    coupon_usage["templateId"],
                    coupon_usage["userCouponId"],
                    body.orderTypeCode,
                    coupon_usage["discountAmount"],
                    now,
                    now,
                ),
            )
            cursor.execute(
                """
                UPDATE user_coupons
                SET status_code = 'used', used_at = %s, updated_at = %s
                WHERE id = %s AND user_id = %s
                """,
                (now, now, coupon_usage["userCouponId"], current_user_id),
            )
        if points_used > 0:
            new_balance = int(member_account["points_balance"]) - points_used
            cursor.execute(
                """
                INSERT INTO member_point_ledger (
                    user_id, ledger_type_code, points_delta, balance_after, created_at
                ) VALUES (%s, 'point_redeem', %s, %s, %s)
                """,
                (current_user_id, -points_used, new_balance, now),
            )
            point_ledger_id = cursor.lastrowid
            cursor.execute(
                """
                INSERT INTO order_point_usages (
                    order_id, user_id, point_ledger_id, points_used, discount_amount, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    order_id,
                    current_user_id,
                    point_ledger_id,
                    points_used,
                    point_discount,
                    now,
                    now,
                ),
            )
            cursor.execute(
                """
                UPDATE member_accounts
                SET points_balance = %s, updated_at = %s
                WHERE user_id = %s
                """,
                (new_balance, now, current_user_id),
            )
    order = _ensure_order_owned(order_id, current_user_id)
    return {
        "orderId": order["id"],
        "orderNo": order["order_no"],
        "orderTypeCode": order["order_type_code"],
        "statusCode": order["status_code"],
        "goodsAmount": money(order["goods_amount"]),
        "marketingDiscountAmount": money(order["marketing_discount_amount"]),
        "couponDiscountAmount": money(order["coupon_discount_amount"]),
        "pointDiscountAmount": money(order["point_discount_amount"]),
        "payableAmount": money(order["payable_amount"]),
        "createdAt": format_datetime(order["created_at"]),
    }


@router.get("/orders", summary="分页查询订单")
def list_orders(
    current_user_id: Annotated[int, Depends(get_current_user_id)],
    status_code: Annotated[
        str | None,
        Query(
            alias="statusCode", description=f"订单状态筛选，{ORDER_STATUS_ENUM_DESC}"
        ),
    ] = None,
    order_type_code: Annotated[
        str | None,
        Query(
            alias="orderTypeCode", description=f"订单类型筛选，{PRODUCT_TYPE_ENUM_DESC}"
        ),
    ] = None,
    created_from: Annotated[
        str | None,
        Query(
            alias="createdFrom",
            description="下单时间下限，格式 YYYY-MM-DD HH:mm:ss 或 YYYY-MM-DDTHH:mm:ss，筛选 created_at >= createdFrom。",
        ),
    ] = None,
    created_to: Annotated[
        str | None,
        Query(
            alias="createdTo",
            description="下单时间上限，格式 YYYY-MM-DD HH:mm:ss 或 YYYY-MM-DDTHH:mm:ss，筛选 created_at <= createdTo。",
        ),
    ] = None,
    page_no: Annotated[int, Query(alias="pageNo", description="页码，从 1 开始。")] = 1,
    page_size: Annotated[
        int,
        Query(alias="pageSize", description="每页数量，默认 20，服务端最大限制 100。"),
    ] = 20,
):
    offset, limit = offset_limit(page_no, page_size)
    conditions = ["user_id = %s"]
    params: list[Any] = [current_user_id]
    if status_code:
        conditions.append("status_code = %s")
        params.append(status_code)
    if order_type_code:
        conditions.append("order_type_code = %s")
        params.append(order_type_code)
    if created_from:
        conditions.append("created_at >= %s")
        params.append(parse_datetime(created_from, "createdFrom"))
    if created_to:
        conditions.append("created_at <= %s")
        params.append(parse_datetime(created_to, "createdTo"))
    where_clause = " AND ".join(conditions)
    rows = fetch_all(
        f"""
        SELECT
            id, order_no, order_type_code, status_code,
            goods_amount, payable_amount, created_at
        FROM orders
        WHERE {where_clause}
        ORDER BY created_at DESC, id DESC
        LIMIT %s OFFSET %s
        """,
        tuple(params + [limit, offset]),
    )
    total = count_total(
        f"""
        SELECT COUNT(*) AS total
        FROM orders
        WHERE {where_clause}
        """,
        tuple(params),
    )
    return {
        "list": [
            {
                "orderId": row["id"],
                "orderNo": row["order_no"],
                "orderTypeCode": row["order_type_code"],
                "statusCode": row["status_code"],
                "goodsAmount": money(row["goods_amount"]),
                "payableAmount": money(row["payable_amount"]),
                "createdAt": format_datetime(row["created_at"]),
            }
            for row in rows
        ],
        "pageNo": page_no,
        "pageSize": page_size,
        "total": total,
    }


@router.get("/orders/{orderId}", summary="查询订单详情")
def get_order_detail(
    order_id: Annotated[
        int,
        Path(
            alias="orderId",
            description="订单 ID，对应 orders.id；必须属于当前请求头用户。",
        ),
    ],
    current_user_id: Annotated[int, Depends(get_current_user_id)],
):
    order = _ensure_order_owned(order_id, current_user_id)
    items = _order_items(order_id)
    coupon_usages = fetch_all(
        """
        SELECT user_coupon_id, discount_amount
        FROM order_coupon_usages
        WHERE order_id = %s
        ORDER BY id ASC
        """,
        (order_id,),
    )
    promotion_details = fetch_all(
        """
        SELECT promotion_id, discount_amount
        FROM order_promotion_details
        WHERE order_id = %s
        ORDER BY id ASC
        """,
        (order_id,),
    )
    point_usage = fetch_one(
        """
        SELECT points_used, discount_amount
        FROM order_point_usages
        WHERE order_id = %s
        """,
        (order_id,),
    )
    payments = fetch_all(
        """
        SELECT id, payment_no, payment_method_code, amount, status_code, paid_at, created_at
        FROM payments
        WHERE order_id = %s AND user_id = %s
        ORDER BY created_at DESC, id DESC
        """,
        (order_id, current_user_id),
    )
    return {
        "orderId": order["id"],
        "orderNo": order["order_no"],
        "orderTypeCode": order["order_type_code"],
        "statusCode": order["status_code"],
        "currencyCode": order["currency_code"],
        "goodsAmount": money(order["goods_amount"]),
        "marketingDiscountAmount": money(order["marketing_discount_amount"]),
        "couponDiscountAmount": money(order["coupon_discount_amount"]),
        "pointDiscountAmount": money(order["point_discount_amount"]),
        "payableAmount": money(order["payable_amount"]),
        "paidAmount": money(order["paid_amount"]),
        "refundedAmount": money(order["refunded_amount"]),
        "sourceChannelCode": order["source_channel_code"],
        "createdAt": format_datetime(order["created_at"]),
        "items": [
            {
                "orderItemId": row["id"],
                "productTypeCode": row["product_type_code"],
                "productId": row["product_id"],
                "productName": row["product_name"],
                "saleAmount": money(row["sale_amount"]),
                "refundedAmount": money(row["refunded_amount"]),
                "statusCode": row["status_code"],
                "travelTime": format_datetime(row["travel_time"]),
                "travelEndTime": format_datetime(row["travel_end_time"]),
                "travelerId": row["traveler_id"],
                "travelerName": row["traveler_name"],
            }
            for row in items
        ],
        "couponUsages": [
            {
                "userCouponId": row["user_coupon_id"],
                "discountAmount": money(row["discount_amount"]),
            }
            for row in coupon_usages
        ],
        "promotionDetails": [
            {
                "promotionId": row["promotion_id"],
                "discountAmount": money(row["discount_amount"]),
            }
            for row in promotion_details
        ],
        "pointUsage": {
            "pointsUsed": point_usage["points_used"],
            "discountAmount": money(point_usage["discount_amount"]),
        }
        if point_usage
        else None,
        "payments": [
            {
                "paymentId": row["id"],
                "paymentNo": row["payment_no"],
                "paymentMethodCode": row["payment_method_code"],
                "amount": money(row["amount"]),
                "statusCode": row["status_code"],
                "paidAt": format_datetime(row["paid_at"]),
                "createdAt": format_datetime(row["created_at"]),
            }
            for row in payments
        ],
    }


@router.post("/orders/{orderId}/cancel", summary="取消订单")
def cancel_order(
    body: OrderCancelRequest,
    order_id: Annotated[
        int,
        Path(
            alias="orderId",
            description="订单 ID，对应 orders.id；必须属于当前请求头用户且订单为待支付状态。",
        ),
    ],
    current_user_id: Annotated[int, Depends(get_current_user_id)],
):
    order = _ensure_order_owned(order_id, current_user_id)
    if order["status_code"] != "pending_payment":
        raise conflict("只有待支付订单可以取消")
    items = _order_items(order_id)
    point_usage = fetch_one(
        """
        SELECT id, point_ledger_id, points_used
        FROM order_point_usages
        WHERE order_id = %s
        """,
        (order_id,),
    )
    coupon_usages = fetch_all(
        """
        SELECT id, user_coupon_id
        FROM order_coupon_usages
        WHERE order_id = %s
        """,
        (order_id,),
    )
    now = local_now()
    with db_cursor() as (_, cursor):
        for item in items:
            _release_inventory(
                cursor,
                item["product_type_code"],
                item["product_id"],
                item["travel_time"],
                item["travel_end_time"],
                now,
            )
        cursor.execute(
            """
            UPDATE order_items
            SET status_code = 'cancelled',
                cancelled_at = %s,
                updated_at = %s
            WHERE order_id = %s AND user_id = %s
            """,
            (now, now, order_id, current_user_id),
        )
        cursor.execute(
            """
            UPDATE orders
            SET status_code = 'cancelled',
                cancel_reason = %s,
                finalized_at = %s,
                updated_at = %s
            WHERE id = %s AND user_id = %s
            """,
            (body.cancelReason, now, now, order_id, current_user_id),
        )
        for coupon_usage in coupon_usages:
            cursor.execute(
                """
                UPDATE user_coupons
                SET status_code = 'available', used_at = NULL, updated_at = %s
                WHERE id = %s AND user_id = %s
                """,
                (now, coupon_usage["user_coupon_id"], current_user_id),
            )
        if coupon_usages:
            cursor.execute(
                "DELETE FROM order_coupon_usages WHERE order_id = %s", (order_id,)
            )
        if point_usage:
            cursor.execute(
                """
                UPDATE member_accounts
                SET points_balance = points_balance + %s,
                    updated_at = %s
                WHERE user_id = %s
                """,
                (point_usage["points_used"], now, current_user_id),
            )
            cursor.execute(
                "DELETE FROM order_point_usages WHERE order_id = %s", (order_id,)
            )
            cursor.execute(
                "DELETE FROM member_point_ledger WHERE id = %s AND user_id = %s",
                (point_usage["point_ledger_id"], current_user_id),
            )
    cancelled = _ensure_order_owned(order_id, current_user_id)
    return {
        "orderId": cancelled["id"],
        "statusCode": cancelled["status_code"],
        "cancelReason": cancelled["cancel_reason"],
        "updatedAt": format_datetime(cancelled["updated_at"]),
    }


@router.post("/orders/{orderId}/payments", summary="创建订单支付")
@router.post("/orders/{orderId}/pay", summary="支付订单")
def pay_order(
    body: OrderPayRequest,
    order_id: Annotated[
        int,
        Path(
            alias="orderId",
            description="订单 ID，对应 orders.id；必须属于当前请求头用户且订单为待支付状态。",
        ),
    ],
    current_user_id: Annotated[int, Depends(get_current_user_id)],
):
    if body.paymentMethodCode not in PAYMENT_METHODS:
        raise bad_request("paymentMethodCode 不合法")
    order = _ensure_order_owned(order_id, current_user_id)
    if order["status_code"] != "pending_payment":
        raise conflict("当前订单状态不允许发起支付")
    if _decimal(order["payable_amount"]) <= Decimal("0.00"):
        raise conflict("订单应付金额必须大于 0")
    pending_payment = fetch_one(
        """
        SELECT id, payment_no, amount, status_code, payment_method_code, created_at
        FROM payments
        WHERE order_id = %s AND user_id = %s AND status_code = 'pending'
        ORDER BY id DESC
        LIMIT 1
        """,
        (order_id, current_user_id),
    )
    if pending_payment is None:
        now = local_now()
        with db_cursor() as (_, cursor):
            cursor.execute(
                """
                INSERT INTO payments (
                    payment_no, order_id, user_id, payment_method_code, currency_code,
                    amount, status_code, paid_at, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, 'pending', NULL, %s, %s)
                """,
                (
                    make_no("PAY"),
                    order_id,
                    current_user_id,
                    body.paymentMethodCode,
                    order["currency_code"],
                    order["payable_amount"],
                    now,
                    now,
                ),
            )
            payment_id = cursor.lastrowid
        pending_payment = fetch_one(
            """
            SELECT id, payment_no, amount, status_code, payment_method_code, created_at
            FROM payments
            WHERE id = %s
            """,
            (payment_id,),
        )
    if pending_payment is None:
        raise conflict("支付记录创建失败")
    expire_time = pending_payment["created_at"] + timedelta(minutes=15)
    return {
        "paymentId": pending_payment["id"],
        "paymentNo": pending_payment["payment_no"],
        "orderId": order_id,
        "amount": money(pending_payment["amount"]),
        "statusCode": pending_payment["status_code"],
        "paymentMethodCode": pending_payment["payment_method_code"],
        "paymentPayload": {
            "payToken": f"mock_pay_token_{pending_payment['id']}",
            "expireTime": format_datetime(expire_time),
            "clientType": body.clientType,
        },
    }


@router.post("/payments/callback", summary="处理支付回调")
def handle_payment_callback(
    body: PaymentCallbackRequest,
    payment_signature: Annotated[
        str | None,
        Header(
            alias="X-Demo-Payment-Signature",
            description="演示环境支付回调签名；默认值为 mock-payment-signature，可通过 DEMO_PAYMENT_SIGNATURE 环境变量覆盖。",
        ),
    ] = None,
):
    if payment_signature != DEMO_PAYMENT_SIGNATURE:
        raise unauthorized("支付回调签名不合法")
    if body.statusCode not in PAYMENT_CALLBACK_STATUS_CODES:
        raise bad_request("statusCode 不合法")
    if body.paymentMethodCode not in PAYMENT_METHODS:
        raise bad_request("paymentMethodCode 不合法")
    if body.statusCode == "success" and body.paidAt is None:
        raise bad_request("支付成功回调必须传入 paidAt")

    now = local_now()
    paid_at = parse_datetime(body.paidAt, "paidAt") if body.paidAt is not None else None
    with db_cursor() as (_, cursor):
        cursor.execute(
            """
            SELECT *
            FROM payments
            WHERE payment_no = %s
            FOR UPDATE
            """,
            (body.paymentNo,),
        )
        payment = _cursor_fetchone_dict(cursor)
        if payment is None:
            raise not_found("支付记录不存在")
        if int(payment["order_id"]) != body.orderId:
            raise conflict("回调 orderId 与支付记录不一致")
        if payment["payment_method_code"] != body.paymentMethodCode:
            raise conflict("回调 paymentMethodCode 与支付记录不一致")
        if _decimal(payment["amount"]) != _decimal(body.amount):
            raise conflict("回调 amount 与支付记录不一致")

        if payment["status_code"] in {"success", "failed", "closed"}:
            cursor.execute(
                """
                SELECT *
                FROM orders
                WHERE id = %s
                FOR UPDATE
                """,
                (payment["order_id"],),
            )
            updated_order = _cursor_fetchone_dict(cursor)
            if updated_order is None:
                raise not_found("订单不存在")
            updated_payment = payment
            processed = False
        elif body.statusCode == "success":
            if paid_at is None:
                raise bad_request("支付成功回调必须传入 paidAt")
            updated_payment, updated_order, processed = _complete_successful_payment(
                cursor,
                int(payment["id"]),
                paid_at,
                now,
            )
        else:
            cursor.execute(
                """
                SELECT *
                FROM orders
                WHERE id = %s
                FOR UPDATE
                """,
                (payment["order_id"],),
            )
            updated_order = _cursor_fetchone_dict(cursor)
            if updated_order is None:
                raise not_found("订单不存在")
            processed = False
            if payment["status_code"] == "pending":
                cursor.execute(
                    """
                    UPDATE payments
                    SET status_code = %s,
                        updated_at = %s
                    WHERE id = %s
                    """,
                    (body.statusCode, now, payment["id"]),
                )
                processed = True
            cursor.execute("SELECT * FROM payments WHERE id = %s", (payment["id"],))
            updated_payment = _cursor_fetchone_dict(cursor)
            if updated_payment is None:
                raise conflict("支付记录更新失败")

    return {
        "paymentId": updated_payment["id"],
        "paymentNo": updated_payment["payment_no"],
        "orderId": updated_order["id"],
        "paymentStatusCode": updated_payment["status_code"],
        "orderStatusCode": updated_order["status_code"],
        "processed": processed,
    }


@router.get("/payments/{paymentId}", summary="查询支付记录详情")
def get_payment(
    payment_id: Annotated[
        int,
        Path(
            alias="paymentId",
            description="支付记录 ID，对应 payments.id；必须属于当前请求头用户。",
        ),
    ],
    current_user_id: Annotated[int, Depends(get_current_user_id)],
):
    payment = _ensure_payment_owned(payment_id, current_user_id)
    return _payment_status_payload(payment)


@router.post("/payments/{paymentId}/close", summary="关闭支付记录")
def close_payment(
    body: PaymentCloseRequest,
    payment_id: Annotated[
        int,
        Path(
            alias="paymentId",
            description="支付记录 ID，对应 payments.id；必须属于当前请求头用户，且支付状态为 pending。",
        ),
    ],
    current_user_id: Annotated[int, Depends(get_current_user_id)],
):
    if not body.closeReason.strip():
        raise bad_request("closeReason 不能为空")
    now = local_now()
    with db_cursor() as (_, cursor):
        cursor.execute(
            """
            SELECT *
            FROM payments
            WHERE id = %s AND user_id = %s
            FOR UPDATE
            """,
            (payment_id, current_user_id),
        )
        payment = _cursor_fetchone_dict(cursor)
        if payment is None:
            raise not_found("支付记录不存在")
        if payment["status_code"] == "pending":
            cursor.execute(
                """
                UPDATE payments
                SET status_code = 'closed',
                    updated_at = %s
                WHERE id = %s
                """,
                (now, payment_id),
            )
            cursor.execute("SELECT * FROM payments WHERE id = %s", (payment_id,))
            payment = _cursor_fetchone_dict(cursor)
            if payment is None:
                raise conflict("支付记录更新失败")
    return {
        "paymentId": payment["id"],
        "paymentNo": payment["payment_no"],
        "orderId": payment["order_id"],
        "statusCode": payment["status_code"],
        "updatedAt": format_datetime(payment["updated_at"]),
    }


@router.get("/orders/{orderId}/payments", summary="查询订单支付记录")
def list_order_payments(
    order_id: Annotated[
        int,
        Path(
            alias="orderId",
            description="订单 ID，对应 orders.id；必须属于当前请求头用户。",
        ),
    ],
    current_user_id: Annotated[int, Depends(get_current_user_id)],
):
    _ensure_order_owned(order_id, current_user_id)
    rows = fetch_all(
        """
        SELECT id, payment_no, payment_method_code, amount, status_code, paid_at, created_at
        FROM payments
        WHERE order_id = %s AND user_id = %s
        ORDER BY created_at DESC, id DESC
        """,
        (order_id, current_user_id),
    )
    return {
        "list": [
            {
                "paymentId": row["id"],
                "paymentNo": row["payment_no"],
                "paymentMethodCode": row["payment_method_code"],
                "amount": money(row["amount"]),
                "statusCode": row["status_code"],
                "paidAt": format_datetime(row["paid_at"]),
            }
            for row in rows
        ]
    }
