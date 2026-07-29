from typing import Annotated

from fastapi import Header

from .database import fetch_one
from .errors import not_found, unauthorized

UserIdHeader = Annotated[
    str | None,
    Header(
        alias="X-User-Id",
        description=(
            "演示环境用户标识，直接传 users.id，例如 10001。"
            "需要用户身份的接口必填；服务端校验为数字、用户存在且状态不是 inactive。"
        ),
    ),
]


def get_current_user_id(x_user_id: UserIdHeader = None) -> int:
    if x_user_id is None or not x_user_id.strip():
        raise unauthorized("缺少请求头 X-User-Id")
    if not x_user_id.isdigit():
        raise unauthorized("X-User-Id 必须为合法数字")
    user_id = int(x_user_id)
    user = fetch_one(
        """
        SELECT id, status_code
        FROM users
        WHERE id = %s
        """,
        (user_id,),
    )
    if user is None:
        raise not_found("当前用户不存在")
    if user["status_code"] == "inactive":
        raise unauthorized("当前用户状态不可用")
    return user_id
