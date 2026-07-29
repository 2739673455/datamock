from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query
from pydantic import BaseModel, Field

from ..database import db_cursor, fetch_all, fetch_one
from ..dependencies import get_current_user_id
from ..errors import bad_request, conflict, not_found
from ..utils import (
    count_total,
    local_now,
    masked_identity,
    normalize_identity,
    offset_limit,
)

router = APIRouter(prefix="/api/v1", tags=["users"])

IDENTITY_TYPE_ENUM_DESC = "取值：id_card=居民身份证，passport=护照。"
GENDER_ENUM_DESC = "取值：male=男，female=女。"
TRAVELER_STATUS_ENUM_DESC = "取值：active=有效，inactive=无效。"
LEDGER_TYPE_ENUM_DESC = (
    "取值：signup_bonus=注册奖励，order_earn=订单获积分，order_earn_revoke=退款撤销获积分，"
    "point_redeem=积分抵扣，expire=过期，admin_adjust=人工调整。"
)


class TravelerCreateRequest(BaseModel):
    travelerName: str = Field(description="出行人姓名，写入 travelers.traveler_name。")
    identityTypeCode: str = Field(
        description=f"证件类型编码，{IDENTITY_TYPE_ENUM_DESC}"
    )
    identityNo: str = Field(
        description="证件号码，服务端入库前会去空格并统一转大写，响应中只返回脱敏值。"
    )
    genderCode: str = Field(description=f"性别编码，{GENDER_ENUM_DESC}")
    birthDate: str | None = Field(
        default=None, description="出生日期，格式 YYYY-MM-DD；未知时传 null 或不传。"
    )
    phone: str | None = Field(
        default=None,
        description="出行人联系电话，用于订单出行通知；未知时传 null 或不传。",
    )


class TravelerUpdateRequest(TravelerCreateRequest):
    statusCode: str = Field(
        default="active", description=f"出行人状态，{TRAVELER_STATUS_ENUM_DESC}"
    )


def _get_traveler_owned(traveler_id: int, current_user_id: int) -> dict[str, Any]:
    traveler = fetch_one(
        """
        SELECT *
        FROM travelers
        WHERE id = %s AND user_id = %s
        """,
        (traveler_id, current_user_id),
    )
    if traveler is None:
        raise not_found("出行人不存在")
    return traveler


@router.get("/me", summary="查询当前用户信息")
def get_me(current_user_id: Annotated[int, Depends(get_current_user_id)]):
    row = fetch_one(
        """
        SELECT
            u.id AS user_id,
            u.nickname,
            u.phone,
            u.email,
            u.gender_code,
            u.birth_date,
            u.status_code,
            p.real_name,
            p.identity_type_code,
            p.identity_no,
            p.residence_city_name,
            p.occupation
        FROM users u
        LEFT JOIN user_profiles p ON p.user_id = u.id
        WHERE u.id = %s
        """,
        (current_user_id,),
    )
    if row is None:
        raise not_found("当前用户不存在")
    return {
        "userId": row["user_id"],
        "nickname": row["nickname"],
        "phone": row["phone"],
        "email": row["email"],
        "genderCode": row["gender_code"],
        "birthDate": str(row["birth_date"]) if row["birth_date"] else None,
        "statusCode": row["status_code"],
        "realName": row["real_name"],
        "identityTypeCode": row["identity_type_code"],
        "identityNoMasked": masked_identity(row["identity_no"]),
        "residenceCityName": row["residence_city_name"],
        "occupation": row["occupation"],
    }


@router.get("/me/travelers", summary="查询常用出行人")
def get_me_travelers(
    current_user_id: Annotated[int, Depends(get_current_user_id)],
    page_no: Annotated[
        int,
        Query(
            alias="pageNo", description="页码，从 1 开始；小于 1 时服务端按 1 处理。"
        ),
    ] = 1,
    page_size: Annotated[
        int,
        Query(
            alias="pageSize", description="每页数量，默认 20；服务端最大限制为 100。"
        ),
    ] = 20,
):
    offset, limit = offset_limit(page_no, page_size)
    rows = fetch_all(
        """
        SELECT
            id, traveler_name, identity_type_code, identity_no,
            gender_code, birth_date, phone, status_code, created_at, updated_at
        FROM travelers
        WHERE user_id = %s AND status_code = 'active'
        ORDER BY updated_at DESC, id DESC
        LIMIT %s OFFSET %s
        """,
        (current_user_id, limit, offset),
    )
    total = count_total(
        """
        SELECT COUNT(*) AS total
        FROM travelers
        WHERE user_id = %s AND status_code = 'active'
        """,
        (current_user_id,),
    )
    return {
        "list": [
            {
                "travelerId": row["id"],
                "travelerName": row["traveler_name"],
                "identityTypeCode": row["identity_type_code"],
                "identityNoMasked": masked_identity(row["identity_no"]),
                "genderCode": row["gender_code"],
                "birthDate": str(row["birth_date"]) if row["birth_date"] else None,
                "phone": row["phone"],
                "statusCode": row["status_code"],
                "createdAt": row["created_at"].strftime("%Y-%m-%d %H:%M:%S"),
                "updatedAt": row["updated_at"].strftime("%Y-%m-%d %H:%M:%S"),
            }
            for row in rows
        ],
        "pageNo": page_no,
        "pageSize": page_size,
        "total": total,
    }


@router.post("/me/travelers", summary="新增常用出行人")
def create_traveler(
    body: TravelerCreateRequest,
    current_user_id: Annotated[int, Depends(get_current_user_id)],
):
    if body.genderCode not in {"male", "female"}:
        raise bad_request("genderCode 只能为 male 或 female")
    if body.identityTypeCode not in {"id_card", "passport"}:
        raise bad_request("identityTypeCode 不合法")
    identity_no = normalize_identity(body.identityNo)
    exists = fetch_one(
        """
        SELECT id
        FROM travelers
        WHERE user_id = %s AND identity_type_code = %s AND identity_no = %s
        """,
        (current_user_id, body.identityTypeCode, identity_no),
    )
    if exists:
        raise conflict("同一证件信息的出行人已存在")
    now = local_now()
    with db_cursor() as (_, cursor):
        cursor.execute(
            """
            INSERT INTO travelers (
                user_id, traveler_name, identity_no, identity_type_code,
                gender_code, birth_date, phone, status_code, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'active', %s, %s)
            """,
            (
                current_user_id,
                body.travelerName,
                identity_no,
                body.identityTypeCode,
                body.genderCode,
                body.birthDate,
                body.phone,
                now,
                now,
            ),
        )
        traveler_id = cursor.lastrowid
    traveler = _get_traveler_owned(traveler_id, current_user_id)
    return {
        "travelerId": traveler["id"],
        "travelerName": traveler["traveler_name"],
        "identityTypeCode": traveler["identity_type_code"],
        "identityNoMasked": masked_identity(traveler["identity_no"]),
        "genderCode": traveler["gender_code"],
        "birthDate": str(traveler["birth_date"]) if traveler["birth_date"] else None,
        "phone": traveler["phone"],
        "statusCode": traveler["status_code"],
        "createdAt": traveler["created_at"].strftime("%Y-%m-%d %H:%M:%S"),
    }


def _has_in_progress_trip(traveler_id: int, current_user_id: int) -> bool:
    row = fetch_one(
        """
        SELECT oi.id
        FROM order_items oi
        JOIN orders o ON o.id = oi.order_id
        WHERE oi.traveler_id = %s
          AND oi.user_id = %s
          AND o.user_id = %s
          AND oi.status_code IN ('paid', 'ticketed')
        LIMIT 1
        """,
        (traveler_id, current_user_id, current_user_id),
    )
    return row is not None


@router.put("/me/travelers/{travelerId}", summary="更新常用出行人")
def update_traveler(
    body: TravelerUpdateRequest,
    traveler_id: Annotated[
        int,
        Path(alias="travelerId", description="常用出行人 ID，必须属于当前请求头用户。"),
    ],
    current_user_id: Annotated[int, Depends(get_current_user_id)],
):
    traveler = _get_traveler_owned(traveler_id, current_user_id)
    if body.genderCode not in {"male", "female"}:
        raise bad_request("genderCode 只能为 male 或 female")
    if body.identityTypeCode not in {"id_card", "passport"}:
        raise bad_request("identityTypeCode 不合法")
    if body.statusCode not in {"active", "inactive"}:
        raise bad_request("statusCode 只能为 active 或 inactive")
    if _has_in_progress_trip(traveler_id, current_user_id):
        restricted_changed = any(
            [
                traveler["traveler_name"] != body.travelerName,
                traveler["identity_type_code"] != body.identityTypeCode,
                normalize_identity(traveler["identity_no"])
                != normalize_identity(body.identityNo),
                traveler["gender_code"] != body.genderCode,
                str(traveler["birth_date"]) != (body.birthDate or None),
                traveler["status_code"] != body.statusCode,
            ]
        )
        if restricted_changed:
            raise conflict(
                "该出行人有进行中的行程，暂只允许修改手机号，不能修改姓名、证件、性别、出生日期或状态"
            )
    identity_no = normalize_identity(body.identityNo)
    exists = fetch_one(
        """
        SELECT id
        FROM travelers
        WHERE user_id = %s AND identity_type_code = %s AND identity_no = %s AND id <> %s
        """,
        (current_user_id, body.identityTypeCode, identity_no, traveler_id),
    )
    if exists:
        raise conflict("同一证件信息的出行人已存在")
    now = local_now()
    with db_cursor() as (_, cursor):
        cursor.execute(
            """
            UPDATE travelers
            SET traveler_name = %s,
                identity_no = %s,
                identity_type_code = %s,
                gender_code = %s,
                birth_date = %s,
                phone = %s,
                status_code = %s,
                updated_at = %s
            WHERE id = %s AND user_id = %s
            """,
            (
                body.travelerName,
                identity_no,
                body.identityTypeCode,
                body.genderCode,
                body.birthDate,
                body.phone,
                body.statusCode,
                now,
                traveler_id,
                current_user_id,
            ),
        )
    traveler = _get_traveler_owned(traveler_id, current_user_id)
    return {
        "travelerId": traveler["id"],
        "travelerName": traveler["traveler_name"],
        "identityTypeCode": traveler["identity_type_code"],
        "identityNoMasked": masked_identity(traveler["identity_no"]),
        "genderCode": traveler["gender_code"],
        "birthDate": str(traveler["birth_date"]) if traveler["birth_date"] else None,
        "phone": traveler["phone"],
        "statusCode": traveler["status_code"],
        "updatedAt": traveler["updated_at"].strftime("%Y-%m-%d %H:%M:%S"),
    }


@router.delete("/me/travelers/{travelerId}", summary="删除常用出行人")
def delete_traveler(
    traveler_id: Annotated[
        int,
        Path(
            alias="travelerId",
            description="常用出行人 ID，必须属于当前请求头用户；删除时执行逻辑停用。",
        ),
    ],
    current_user_id: Annotated[int, Depends(get_current_user_id)],
):
    traveler = _get_traveler_owned(traveler_id, current_user_id)
    if traveler["status_code"] == "inactive":
        return {
            "travelerId": traveler_id,
            "statusCode": "inactive",
            "updatedAt": traveler["updated_at"].strftime("%Y-%m-%d %H:%M:%S"),
        }
    if _has_in_progress_trip(traveler_id, current_user_id):
        raise conflict("该出行人有进行中的行程，暂不可删除")
    now = local_now()
    with db_cursor() as (_, cursor):
        cursor.execute(
            """
            UPDATE travelers
            SET status_code = 'inactive', updated_at = %s
            WHERE id = %s AND user_id = %s
            """,
            (now, traveler_id, current_user_id),
        )
    traveler = _get_traveler_owned(traveler_id, current_user_id)
    return {
        "travelerId": traveler_id,
        "statusCode": traveler["status_code"],
        "updatedAt": traveler["updated_at"].strftime("%Y-%m-%d %H:%M:%S"),
    }


@router.get("/me/member-account", summary="查询会员账户")
def get_member_account(current_user_id: Annotated[int, Depends(get_current_user_id)]):
    row = fetch_one(
        """
        SELECT user_id, member_level_code, points_balance, total_points, growth_value,
               created_at, updated_at
        FROM member_accounts
        WHERE user_id = %s
        """,
        (current_user_id,),
    )
    if row is None:
        raise not_found("当前用户会员账户不存在")
    return {
        "userId": row["user_id"],
        "memberLevelCode": row["member_level_code"],
        "pointsBalance": row["points_balance"],
        "totalPoints": row["total_points"],
        "growthValue": row["growth_value"],
        "createdAt": row["created_at"].strftime("%Y-%m-%d %H:%M:%S"),
        "updatedAt": row["updated_at"].strftime("%Y-%m-%d %H:%M:%S"),
    }


@router.get("/me/point-ledger", summary="分页查询积分流水")
def get_point_ledger(
    current_user_id: Annotated[int, Depends(get_current_user_id)],
    page_no: Annotated[
        int,
        Query(
            alias="pageNo", description="页码，从 1 开始；小于 1 时服务端按 1 处理。"
        ),
    ] = 1,
    page_size: Annotated[
        int,
        Query(
            alias="pageSize", description="每页数量，默认 20；服务端最大限制为 100。"
        ),
    ] = 20,
    ledger_type_code: Annotated[
        str | None,
        Query(
            alias="ledgerTypeCode",
            description=f"积分流水类型编码，{LEDGER_TYPE_ENUM_DESC}",
        ),
    ] = None,
    created_from: Annotated[
        str | None,
        Query(
            alias="createdFrom",
            description="流水创建时间下限，格式 YYYY-MM-DD HH:mm:ss 或 YYYY-MM-DDTHH:mm:ss，筛选 created_at >= createdFrom。",
        ),
    ] = None,
    created_to: Annotated[
        str | None,
        Query(
            alias="createdTo",
            description="流水创建时间上限，格式 YYYY-MM-DD HH:mm:ss 或 YYYY-MM-DDTHH:mm:ss，筛选 created_at <= createdTo。",
        ),
    ] = None,
):
    offset, limit = offset_limit(page_no, page_size)
    conditions = ["user_id = %s"]
    params: list[Any] = [current_user_id]
    if ledger_type_code:
        conditions.append("ledger_type_code = %s")
        params.append(ledger_type_code)
    if created_from:
        conditions.append("created_at >= %s")
        params.append(created_from)
    if created_to:
        conditions.append("created_at <= %s")
        params.append(created_to)
    where_clause = " AND ".join(conditions)
    rows = fetch_all(
        f"""
        SELECT
            id, ledger_type_code, points_delta, balance_after, created_at
        FROM member_point_ledger
        WHERE {where_clause}
        ORDER BY created_at DESC, id DESC
        LIMIT %s OFFSET %s
        """,
        tuple(params + [limit, offset]),
    )
    total = count_total(
        f"""
        SELECT COUNT(*) AS total
        FROM member_point_ledger
        WHERE {where_clause}
        """,
        tuple(params),
    )
    return {
        "list": [
            {
                "ledgerId": row["id"],
                "ledgerTypeCode": row["ledger_type_code"],
                "pointsDelta": row["points_delta"],
                "balanceAfter": row["balance_after"],
                "createdAt": row["created_at"].strftime("%Y-%m-%d %H:%M:%S"),
            }
            for row in rows
        ],
        "pageNo": page_no,
        "pageSize": page_size,
        "total": total,
    }
