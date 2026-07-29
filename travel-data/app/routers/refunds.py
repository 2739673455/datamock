from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query
from pydantic import BaseModel, Field

from ..database import db_cursor, fetch_all, fetch_one
from ..dependencies import get_current_user_id
from ..errors import bad_request, conflict, not_found
from ..utils import (
    count_total,
    format_datetime,
    local_now,
    make_no,
    money,
    offset_limit,
    parse_datetime,
)

router = APIRouter(prefix="/api/v1", tags=["refunds"])

REFUND_REQUEST_STATUS_ENUM_DESC = (
    "取值：pending=待处理，approved=审核通过，rejected=审核驳回，success=退款完成。"
)


class RefundRequestCreate(BaseModel):
    requestedAmount: float = Field(
        description="本次申请退款金额，单位元；必须大于 0 且不能超过订单明细剩余可退金额。"
    )
    reason: str = Field(
        description="退款原因，用于前台提交说明；当前演示接口只做接收，不落单独原因字段。"
    )


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


def _ensure_order_item_owned(
    order_id: int, item_id: int, current_user_id: int
) -> dict[str, Any]:
    row = fetch_one(
        """
        SELECT *
        FROM order_items
        WHERE id = %s AND order_id = %s AND user_id = %s
        """,
        (item_id, order_id, current_user_id),
    )
    if row is None:
        raise not_found("订单明细不存在")
    return row


@router.post("/orders/{orderId}/items/{itemId}/refund-requests", summary="申请订单明细退款")
def create_refund_request(
    body: RefundRequestCreate,
    order_id: Annotated[
        int,
        Path(
            alias="orderId",
            description="订单 ID，对应 orders.id；必须属于当前请求头用户。",
        ),
    ],
    item_id: Annotated[
        int,
        Path(
            alias="itemId",
            description="订单明细 ID，对应 order_items.id；必须属于当前订单和当前用户。",
        ),
    ],
    current_user_id: Annotated[int, Depends(get_current_user_id)],
):
    _ensure_order_owned(order_id, current_user_id)
    item = _ensure_order_item_owned(order_id, item_id, current_user_id)
    if item["status_code"] not in {"paid", "ticketed", "completed"}:
        raise conflict("当前订单明细状态不允许申请退款")
    in_progress = fetch_one(
        """
        SELECT id
        FROM refund_requests
        WHERE order_item_id = %s AND user_id = %s AND status_code IN ('pending', 'approved')
        LIMIT 1
        """,
        (item_id, current_user_id),
    )
    if in_progress is not None:
        raise conflict("该订单明细存在进行中的退款申请")
    successful_refund = fetch_one(
        """
        SELECT COALESCE(SUM(amount), 0) AS total_amount
        FROM refund_records
        WHERE order_item_id = %s AND user_id = %s AND status_code = 'success'
        """,
        (item_id, current_user_id),
    )
    refunded_amount = (
        float(successful_refund["total_amount"]) if successful_refund else 0.0
    )
    remaining_amount = float(item["sale_amount"]) - refunded_amount
    if body.requestedAmount <= 0:
        raise bad_request("requestedAmount 必须大于 0")
    if body.requestedAmount > remaining_amount:
        raise conflict("requestedAmount 超过该明细剩余可退金额")
    now = local_now()
    with db_cursor() as (_, cursor):
        cursor.execute(
            """
            INSERT INTO refund_requests (
                refund_request_no, order_id, order_item_id, user_id, requested_amount,
                approved_amount, status_code, requested_at, processed_at, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, NULL, 'pending', %s, NULL, %s, %s)
            """,
            (
                make_no("RR"),
                order_id,
                item_id,
                current_user_id,
                body.requestedAmount,
                now,
                now,
                now,
            ),
        )
        refund_request_id = cursor.lastrowid
    row = fetch_one(
        """
        SELECT id, refund_request_no, order_id, order_item_id, requested_amount, status_code, requested_at
        FROM refund_requests
        WHERE id = %s
        """,
        (refund_request_id,),
    )
    if row is None:
        raise conflict("退款申请创建失败")
    return {
        "refundRequestId": row["id"],
        "refundRequestNo": row["refund_request_no"],
        "orderId": row["order_id"],
        "orderItemId": row["order_item_id"],
        "requestedAmount": money(row["requested_amount"]),
        "statusCode": row["status_code"],
        "requestedAt": format_datetime(row["requested_at"]),
    }


@router.get("/refund-requests", summary="分页查询退款申请")
def list_refund_requests(
    current_user_id: Annotated[int, Depends(get_current_user_id)],
    status_code: Annotated[
        str | None,
        Query(
            alias="statusCode",
            description=f"退款申请状态筛选，{REFUND_REQUEST_STATUS_ENUM_DESC}",
        ),
    ] = None,
    requested_from: Annotated[
        str | None,
        Query(
            alias="requestedFrom",
            description="退款申请时间下限，格式 YYYY-MM-DD HH:mm:ss 或 YYYY-MM-DDTHH:mm:ss，筛选 requested_at >= requestedFrom。",
        ),
    ] = None,
    requested_to: Annotated[
        str | None,
        Query(
            alias="requestedTo",
            description="退款申请时间上限，格式 YYYY-MM-DD HH:mm:ss 或 YYYY-MM-DDTHH:mm:ss，筛选 requested_at <= requestedTo。",
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
    if requested_from:
        conditions.append("requested_at >= %s")
        params.append(parse_datetime(requested_from, "requestedFrom"))
    if requested_to:
        conditions.append("requested_at <= %s")
        params.append(parse_datetime(requested_to, "requestedTo"))
    where_clause = " AND ".join(conditions)
    rows = fetch_all(
        f"""
        SELECT
            id, refund_request_no, order_id, order_item_id, requested_amount,
            approved_amount, status_code, requested_at, processed_at
        FROM refund_requests
        WHERE {where_clause}
        ORDER BY requested_at DESC, id DESC
        LIMIT %s OFFSET %s
        """,
        tuple(params + [limit, offset]),
    )
    total = count_total(
        f"""
        SELECT COUNT(*) AS total
        FROM refund_requests
        WHERE {where_clause}
        """,
        tuple(params),
    )
    return {
        "list": [
            {
                "refundRequestId": row["id"],
                "refundRequestNo": row["refund_request_no"],
                "orderId": row["order_id"],
                "orderItemId": row["order_item_id"],
                "requestedAmount": money(row["requested_amount"]),
                "approvedAmount": money(row["approved_amount"]),
                "statusCode": row["status_code"],
                "requestedAt": format_datetime(row["requested_at"]),
                "processedAt": format_datetime(row["processed_at"]),
            }
            for row in rows
        ],
        "pageNo": page_no,
        "pageSize": page_size,
        "total": total,
    }


@router.get("/refund-requests/{refundRequestId}", summary="查询退款申请详情")
def get_refund_request_detail(
    refund_request_id: Annotated[
        int,
        Path(
            alias="refundRequestId",
            description="退款申请 ID，对应 refund_requests.id；必须属于当前请求头用户。",
        ),
    ],
    current_user_id: Annotated[int, Depends(get_current_user_id)],
):
    row = fetch_one(
        """
        SELECT
            rr.id, rr.refund_request_no, rr.order_id, rr.order_item_id, rr.requested_amount,
            rr.approved_amount, rr.status_code, rr.requested_at, rr.processed_at,
            r.id AS refund_id, r.refund_no, r.amount, r.status_code AS refund_status_code, r.processed_at AS refund_processed_at
        FROM refund_requests rr
        LEFT JOIN refund_records r ON r.refund_request_id = rr.id
        WHERE rr.id = %s AND rr.user_id = %s
        """,
        (refund_request_id, current_user_id),
    )
    if row is None:
        raise not_found("退款申请不存在")
    return {
        "refundRequestId": row["id"],
        "refundRequestNo": row["refund_request_no"],
        "orderId": row["order_id"],
        "orderItemId": row["order_item_id"],
        "requestedAmount": money(row["requested_amount"]),
        "approvedAmount": money(row["approved_amount"]),
        "statusCode": row["status_code"],
        "requestedAt": format_datetime(row["requested_at"]),
        "processedAt": format_datetime(row["processed_at"]),
        "refundRecord": {
            "refundId": row["refund_id"],
            "refundNo": row["refund_no"],
            "amount": money(row["amount"]),
            "statusCode": row["refund_status_code"],
            "processedAt": format_datetime(row["refund_processed_at"]),
        }
        if row["refund_id"] is not None
        else None,
    }


@router.get("/orders/{orderId}/refund-records", summary="查询订单退款记录")
def list_order_refund_records(
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
        SELECT
            id, refund_no, refund_request_id, order_item_id, amount, status_code, processed_at, created_at
        FROM refund_records
        WHERE order_id = %s AND user_id = %s
        ORDER BY created_at DESC, id DESC
        """,
        (order_id, current_user_id),
    )
    return {
        "list": [
            {
                "refundId": row["id"],
                "refundNo": row["refund_no"],
                "refundRequestId": row["refund_request_id"],
                "orderItemId": row["order_item_id"],
                "amount": money(row["amount"]),
                "statusCode": row["status_code"],
                "processedAt": format_datetime(row["processed_at"]),
            }
            for row in rows
        ]
    }
