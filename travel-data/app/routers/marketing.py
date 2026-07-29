from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
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
)

router = APIRouter(prefix="/api/v1", tags=["marketing"])

PRODUCT_TYPE_ENUM_DESC = (
    "取值：hotel_room=酒店房型，scenic_ticket=景点票种，flight_cabin=航班舱位，"
    "train_seat=火车席位，bus_seat=汽车席位，transfer_service=接送服务。"
)
USER_COUPON_STATUS_ENUM_DESC = "取值：available=可用，used=已使用，expired=已过期。"


class ReceiveCouponRequest(BaseModel):
    templateId: int = Field(
        description="优惠券模板 ID，对应 coupon_templates.id；领取时会校验模板状态、有效期和每人领取上限。"
    )


@router.get("/coupon-templates/available", summary="分页查询可领取优惠券模板")
def list_available_coupon_templates(
    current_user_id: Annotated[int, Depends(get_current_user_id)],
    product_type_code: Annotated[
        str | None,
        Query(
            alias="productTypeCode",
            description=f"适用商品类型筛选，{PRODUCT_TYPE_ENUM_DESC}",
        ),
    ] = None,
    supplier_id: Annotated[
        int | None,
        Query(
            alias="supplierId",
            description="适用供应商 ID；模板指定该供应商或模板不限制供应商时返回。",
        ),
    ] = None,
    page_no: Annotated[int, Query(alias="pageNo", description="页码，从 1 开始。")] = 1,
    page_size: Annotated[
        int,
        Query(alias="pageSize", description="每页数量，默认 20，服务端最大限制 100。"),
    ] = 20,
):
    offset, limit = offset_limit(page_no, page_size)
    now = local_now()
    conditions = [
        "ct.status_code = 'active'",
        "%s BETWEEN ct.valid_from AND ct.valid_until",
    ]
    params: list[Any] = [current_user_id, now]
    if product_type_code:
        conditions.append("ct.applicable_product_type = %s")
        params.append(product_type_code)
    if supplier_id is not None:
        conditions.append(
            "(ct.applicable_supplier_id = %s OR ct.applicable_supplier_id IS NULL)"
        )
        params.append(supplier_id)
    where_clause = " AND ".join(conditions)
    rows = fetch_all(
        f"""
        SELECT
            ct.id,
            ct.template_code,
            ct.template_name,
            ct.coupon_type_code,
            ct.applicable_product_type,
            ct.min_spend_amount,
            ct.discount_amount,
            ct.max_discount_amount,
            ct.valid_from,
            ct.valid_until,
            ct.per_user_limit,
            COUNT(uc.id) AS received_count
        FROM coupon_templates ct
        LEFT JOIN user_coupons uc
          ON uc.template_id = ct.id
         AND uc.user_id = %s
        WHERE {where_clause}
        GROUP BY ct.id
        HAVING received_count < ct.per_user_limit
        ORDER BY ct.valid_until ASC, ct.id DESC
        LIMIT %s OFFSET %s
        """,
        tuple(params + [limit, offset]),
    )
    total = count_total(
        f"""
        SELECT COUNT(*) AS total
        FROM (
            SELECT ct.id, ct.per_user_limit, COUNT(uc.id) AS received_count
            FROM coupon_templates ct
            LEFT JOIN user_coupons uc
              ON uc.template_id = ct.id
             AND uc.user_id = %s
            WHERE {where_clause}
            GROUP BY ct.id
            HAVING received_count < per_user_limit
        ) AS counted
        """,
        tuple(params),
    )
    return {
        "list": [
            {
                "templateId": row["id"],
                "templateCode": row["template_code"],
                "templateName": row["template_name"],
                "couponTypeCode": row["coupon_type_code"],
                "applicableProductType": row["applicable_product_type"],
                "minSpendAmount": money(row["min_spend_amount"]),
                "discountAmount": money(row["discount_amount"]),
                "maxDiscountAmount": money(row["max_discount_amount"]),
                "validFrom": format_datetime(row["valid_from"]),
                "validUntil": format_datetime(row["valid_until"]),
                "perUserLimit": row["per_user_limit"],
                "receivedCount": int(row["received_count"]),
            }
            for row in rows
        ],
        "pageNo": page_no,
        "pageSize": page_size,
        "total": total,
    }


@router.get("/coupons", summary="分页查询用户优惠券")
def list_user_coupons(
    current_user_id: Annotated[int, Depends(get_current_user_id)],
    status_code: Annotated[
        str | None,
        Query(
            alias="statusCode",
            description=f"用户券状态筛选，{USER_COUPON_STATUS_ENUM_DESC}",
        ),
    ] = None,
    product_type_code: Annotated[
        str | None,
        Query(
            alias="productTypeCode",
            description=f"适用商品类型筛选，{PRODUCT_TYPE_ENUM_DESC}",
        ),
    ] = None,
    page_no: Annotated[int, Query(alias="pageNo", description="页码，从 1 开始。")] = 1,
    page_size: Annotated[
        int,
        Query(alias="pageSize", description="每页数量，默认 20，服务端最大限制 100。"),
    ] = 20,
):
    offset, limit = offset_limit(page_no, page_size)
    conditions = ["uc.user_id = %s"]
    params: list[Any] = [current_user_id]
    if status_code:
        conditions.append("uc.status_code = %s")
        params.append(status_code)
    if product_type_code:
        conditions.append("ct.applicable_product_type = %s")
        params.append(product_type_code)
    where_clause = " AND ".join(conditions)
    rows = fetch_all(
        f"""
        SELECT
            uc.id,
            uc.coupon_code,
            uc.template_id,
            ct.template_name,
            ct.coupon_type_code,
            ct.applicable_product_type,
            uc.min_spend_amount,
            uc.discount_amount,
            uc.max_discount_amount,
            uc.valid_from,
            uc.valid_until,
            uc.status_code,
            uc.used_at
        FROM user_coupons uc
        JOIN coupon_templates ct ON ct.id = uc.template_id
        WHERE {where_clause}
        ORDER BY uc.valid_until ASC, uc.id DESC
        LIMIT %s OFFSET %s
        """,
        tuple(params + [limit, offset]),
    )
    total = count_total(
        f"""
        SELECT COUNT(*) AS total
        FROM user_coupons uc
        JOIN coupon_templates ct ON ct.id = uc.template_id
        WHERE {where_clause}
        """,
        tuple(params),
    )
    return {
        "list": [
            {
                "userCouponId": row["id"],
                "couponCode": row["coupon_code"],
                "templateId": row["template_id"],
                "templateName": row["template_name"],
                "couponTypeCode": row["coupon_type_code"],
                "applicableProductType": row["applicable_product_type"],
                "minSpendAmount": money(row["min_spend_amount"]),
                "discountAmount": money(row["discount_amount"]),
                "maxDiscountAmount": money(row["max_discount_amount"]),
                "validFrom": format_datetime(row["valid_from"]),
                "validUntil": format_datetime(row["valid_until"]),
                "statusCode": row["status_code"],
                "usedAt": format_datetime(row["used_at"]),
            }
            for row in rows
        ],
        "pageNo": page_no,
        "pageSize": page_size,
        "total": total,
    }


@router.post("/coupons/receive", summary="领取优惠券")
def receive_coupon(
    body: ReceiveCouponRequest,
    current_user_id: Annotated[int, Depends(get_current_user_id)],
):
    template = fetch_one(
        """
        SELECT *
        FROM coupon_templates
        WHERE id = %s
        """,
        (body.templateId,),
    )
    if template is None:
        raise not_found("优惠券模板不存在")
    now = local_now()
    if template["status_code"] != "active" or not (
        template["valid_from"] <= now <= template["valid_until"]
    ):
        raise conflict("当前优惠券模板不可领取")
    received_row = fetch_one(
        """
        SELECT COUNT(*) AS total
        FROM user_coupons
        WHERE template_id = %s AND user_id = %s
        """,
        (body.templateId, current_user_id),
    )
    if received_row is None:
        raise conflict("优惠券领取数量校验失败")
    if int(received_row["total"]) >= int(template["per_user_limit"]):
        raise conflict("已达到该优惠券领取上限")
    with db_cursor() as (_, cursor):
        cursor.execute(
            """
            INSERT INTO user_coupons (
                template_id, user_id, coupon_code, currency_code, min_spend_amount,
                discount_amount, max_discount_amount, valid_from, valid_until,
                status_code, used_at, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'available', NULL, %s, %s)
            """,
            (
                body.templateId,
                current_user_id,
                make_no("UC"),
                template["currency_code"],
                template["min_spend_amount"],
                template["discount_amount"],
                template["max_discount_amount"],
                template["valid_from"],
                template["valid_until"],
                now,
                now,
            ),
        )
        user_coupon_id = cursor.lastrowid
    coupon = fetch_one(
        """
        SELECT id, coupon_code, template_id, status_code, valid_from, valid_until
        FROM user_coupons
        WHERE id = %s
        """,
        (user_coupon_id,),
    )
    if coupon is None:
        raise bad_request("优惠券领取失败")
    return {
        "userCouponId": coupon["id"],
        "couponCode": coupon["coupon_code"],
        "templateId": coupon["template_id"],
        "statusCode": coupon["status_code"],
        "validFrom": format_datetime(coupon["valid_from"]),
        "validUntil": format_datetime(coupon["valid_until"]),
    }
