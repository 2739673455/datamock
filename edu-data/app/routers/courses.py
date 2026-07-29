"""Course, cohort, and search APIs."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Query

from ..database import execute, fetch_all, fetch_one
from ..dependencies import get_optional_current_user_id
from ..errors import not_found
from ..response import ok
from ..utils import (
    count_total,
    format_date,
    format_datetime,
    format_time,
    json_list,
    local_now,
    money,
    offset_limit,
)

router = APIRouter(prefix="/api/v1", tags=["courses"])


@router.get("/series", summary="分页查询课程系列")
def list_series(
    keyword: Annotated[str | None, Query(description="课程名称关键字。")] = None,
    category_id: Annotated[
        int | None,
        Query(
            alias="categoryId",
            description="课程分类 ID；分类数量较多，不在接口文档中展开枚举。",
        ),
    ] = None,
    learning_goal_code: Annotated[
        str | None,
        Query(
            alias="learningGoalCode",
            description=(
                "学习目标编码。可选值：score_improvement、school_sync、"
                "exam_preparation、postgraduate_exam、certificate_exam、"
                "skill_improvement、job_hunting、promotion、career_switch、"
                "interest_learning、other。"
            ),
        ),
    ] = None,
    delivery_mode_code: Annotated[
        str | None,
        Query(
            alias="deliveryModeCode",
            description="授课方式编码。可选值：online_recorded、online_live、offline_face_to_face。",
        ),
    ] = None,
    current_user_id: Annotated[
        int | None, Depends(get_optional_current_user_id)
    ] = None,
    page_no: Annotated[int, Query(alias="pageNo", description="页码，从 1 开始。")] = 1,
    page_size: Annotated[
        int, Query(alias="pageSize", description="每页条数，范围 1 到 100。")
    ] = 20,
):
    offset, limit = offset_limit(page_no, page_size)
    conditions = ["s.sale_status = 'on_sale'"]
    params: list[Any] = []
    if keyword:
        conditions.append("s.series_name LIKE %s")
        params.append(f"%{keyword}%")
    if category_id is not None:
        conditions.append(
            """
            EXISTS (
                SELECT 1
                FROM series_category_rel AS rel
                WHERE rel.series_id = s.id AND rel.category_id = %s
            )
            """
        )
        params.append(category_id)
    if learning_goal_code:
        conditions.append("JSON_CONTAINS(s.target_learning_goal_codes, JSON_QUOTE(%s))")
        params.append(learning_goal_code)
    if delivery_mode_code:
        conditions.append("s.delivery_mode = %s")
        params.append(delivery_mode_code)

    total = count_total(
        f"""
        SELECT COUNT(DISTINCT s.id) AS total
        FROM series AS s
        WHERE {" AND ".join(conditions)}
        """,
        tuple(params),
    )
    rows = fetch_all(
        f"""
        SELECT
            s.id,
            s.series_name,
            s.cover_url,
            s.delivery_mode,
            s.sale_status,
            COALESCE(AVG(r.score_overall), 0) AS avg_score,
            COUNT(r.id) AS review_count
        FROM series AS s
        LEFT JOIN series_cohort AS c ON c.series_id = s.id
        LEFT JOIN cohort_review AS r ON r.cohort_id = c.id AND r.yn = 1
        WHERE {" AND ".join(conditions)}
        GROUP BY s.id
        ORDER BY avg_score DESC, review_count DESC, s.id DESC
        LIMIT %s OFFSET %s
        """,
        tuple(params + [limit, offset]),
    )
    if current_user_id is not None and keyword and keyword.strip():
        now = local_now()
        execute(
            """
            INSERT INTO series_search_log (
                user_id, keyword_text, search_source, result_count,
                clicked_series_id, searched_at, created_at
            ) VALUES (%s, %s, 'course_list_page', %s, NULL, %s, %s)
            """,
            (current_user_id, keyword.strip(), total, now, now),
        )
    user_links = (
        fetch_user_series_links([int(row["id"]) for row in rows], current_user_id)
        if current_user_id is not None
        else {}
    )
    return ok(
        {
            "list": [
                _series_list_item(row, user_links.get(int(row["id"]), []))
                for row in rows
            ],
            "pageNo": page_no,
            "pageSize": page_size,
            "total": total,
        }
    )


@router.get("/series/{series_id}", summary="查询课程系列详情")
def get_series_detail(
    series_id: Annotated[int, Path(description="课程系列 ID。")],
    current_user_id: Annotated[
        int | None, Depends(get_optional_current_user_id)
    ] = None,
):
    row = fetch_one(
        """
        SELECT
            s.*,
            COALESCE(AVG(r.score_overall), 0) AS avg_score,
            COUNT(r.id) AS review_count
        FROM series AS s
        LEFT JOIN series_cohort AS c ON c.series_id = s.id
        LEFT JOIN cohort_review AS r ON r.cohort_id = c.id AND r.yn = 1
        WHERE s.id = %s
        GROUP BY s.id
        """,
        (series_id,),
    )
    if row is None or row["sale_status"] != "on_sale":
        raise not_found("SERIES_NOT_FOUND", "课程不存在或未上架")
    user_links = (
        fetch_user_series_links([series_id], current_user_id).get(series_id, [])
        if current_user_id is not None
        else []
    )
    return ok(
        {
            "seriesId": row["id"],
            "seriesName": row["series_name"],
            "description": row["description"],
            "deliveryModeCode": row["delivery_mode"],
            "targetLearnerIdentityCodes": json_list(
                row["target_learner_identity_codes"]
            ),
            "targetLearningGoalCodes": json_list(row["target_learning_goal_codes"]),
            "targetGradeCodes": json_list(row["target_grade_codes"]),
            "saleStatusCode": row["sale_status"],
            "avgScore": float(row["avg_score"] or 0),
            "reviewCount": int(row["review_count"] or 0),
            "myEnrollments": user_links,
        }
    )


@router.get("/series/{series_id}/cohorts", summary="查询课程系列班次")
def list_series_cohorts(
    series_id: Annotated[int, Path(description="课程系列 ID。")],
    current_user_id: Annotated[
        int | None, Depends(get_optional_current_user_id)
    ] = None,
):
    rows = fetch_all(
        """
        SELECT
            c.id,
            c.series_id,
            c.cohort_name,
            c.cohort_code,
            c.sale_price,
            s.series_name,
            s.delivery_mode,
            s.cover_url,
            campus.campus_name,
            u.real_name AS head_teacher_name,
            c.start_date,
            c.end_date,
            c.max_student_count,
            c.current_student_count
        FROM series_cohort AS c
        JOIN series AS s ON s.id = c.series_id
        LEFT JOIN org_campus AS campus ON campus.id = c.campus_id
        LEFT JOIN staff_profile AS staff ON staff.id = c.head_teacher_id
        LEFT JOIN sys_user AS u ON u.id = staff.user_id
        WHERE c.series_id = %s
          AND c.yn = 1
          AND c.current_student_count < c.max_student_count
        ORDER BY c.start_date ASC, c.id ASC
        """,
        (series_id,),
    )
    user_links_by_cohort = (
        fetch_user_cohort_links([int(row["id"]) for row in rows], current_user_id)
        if current_user_id is not None
        else {}
    )
    return ok(
        [
            {
                "cohortId": row["id"],
                "cohortName": row["cohort_name"],
                "cohortCode": row["cohort_code"],
                "seriesId": row["series_id"],
                "seriesName": row["series_name"],
                "deliveryModeCode": row["delivery_mode"],
                "coverUrl": row["cover_url"],
                "salePrice": float(row["sale_price"]),
                "campusName": (
                    row["campus_name"]
                    if row["delivery_mode"] == "offline_face_to_face"
                    else None
                ),
                "headTeacherName": row["head_teacher_name"],
                "startDate": format_date(row["start_date"]),
                "endDate": format_date(row["end_date"]),
                "maxStudentCount": row["max_student_count"],
                "currentStudentCount": row["current_student_count"],
                "myEnrollment": user_links_by_cohort.get(int(row["id"])),
            }
            for row in rows
        ]
    )


@router.get("/cohorts/{cohort_id}", summary="查询班次详情")
def get_cohort_detail(
    cohort_id: Annotated[int, Path(description="班次 ID。")],
    current_user_id: Annotated[
        int | None, Depends(get_optional_current_user_id)
    ] = None,
):
    cohort = fetch_one(
        """
        SELECT
            c.*,
            s.series_name,
            s.delivery_mode,
            s.cover_url,
            u.real_name AS head_teacher_name
        FROM series_cohort AS c
        JOIN series AS s ON s.id = c.series_id
        LEFT JOIN staff_profile AS staff ON staff.id = c.head_teacher_id
        LEFT JOIN sys_user AS u ON u.id = staff.user_id
        WHERE c.id = %s
        """,
        (cohort_id,),
    )
    if cohort is None:
        raise not_found("COHORT_NOT_FOUND", "班次不存在")
    user_link = (
        fetch_user_cohort_links([cohort_id], current_user_id).get(cohort_id)
        if current_user_id is not None
        else None
    )
    modules = fetch_all(
        """
        SELECT id, module_name, stage_no, lesson_count
        FROM series_cohort_course
        WHERE cohort_id = %s
        ORDER BY stage_no ASC, id ASC
        """,
        (cohort_id,),
    )
    sessions = fetch_all(
        """
        SELECT
            session.id,
            session.session_title,
            session.teaching_date,
            session.start_time,
            session.end_time
        FROM series_cohort_session AS session
        JOIN series_cohort_course AS course
          ON course.id = session.series_cohort_course_id
        WHERE course.cohort_id = %s
        ORDER BY session.teaching_date ASC, session.start_time ASC, session.id ASC
        """,
        (cohort_id,),
    )
    return ok(
        {
            "cohortId": cohort["id"],
            "cohortName": cohort["cohort_name"],
            "cohortCode": cohort["cohort_code"],
            "seriesId": cohort["series_id"],
            "seriesName": cohort["series_name"],
            "deliveryModeCode": cohort["delivery_mode"],
            "coverUrl": cohort["cover_url"],
            "salePrice": float(cohort["sale_price"]),
            "startDate": format_date(cohort["start_date"]),
            "endDate": format_date(cohort["end_date"]),
            "headTeacherName": cohort["head_teacher_name"],
            "currentStudentCount": cohort["current_student_count"],
            "myEnrollment": user_link,
            "modules": [
                {
                    "cohortCourseId": row["id"],
                    "moduleName": row["module_name"],
                    "stageNo": row["stage_no"],
                    "lessonCount": row["lesson_count"],
                }
                for row in modules
            ],
            "sessions": [
                {
                    "sessionId": row["id"],
                    "sessionTitle": row["session_title"],
                    "teachingDate": format_date(row["teaching_date"]),
                    "startTime": format_time(row["start_time"]),
                    "endTime": format_time(row["end_time"]),
                }
                for row in sessions
            ],
        }
    )


def fetch_user_series_links(
    series_ids: list[int], current_user_id: int
) -> dict[int, list[dict[str, object]]]:
    if not series_ids:
        return {}
    placeholders = ", ".join(["%s"] * len(series_ids))
    rows = fetch_all(
        f"""
        SELECT
            cohort.series_id,
            cohort.id AS cohort_id,
            cohort.cohort_name,
            cohort.cohort_code,
            rel.order_item_id,
            rel.enroll_status,
            rel.enroll_at,
            item.order_id,
            item.order_item_status,
            item.item_name,
            item.payable_amount,
            o.order_no,
            o.order_status
        FROM student_cohort_rel AS rel
        JOIN order_item AS item ON item.id = rel.order_item_id
        JOIN `order` AS o ON o.id = item.order_id
        JOIN series_cohort AS cohort ON cohort.id = rel.cohort_id
        WHERE rel.user_id = %s
          AND cohort.series_id IN ({placeholders})
        ORDER BY rel.enroll_at DESC, rel.id DESC
        """,
        tuple([current_user_id, *series_ids]),
    )
    result: dict[int, list[dict[str, object]]] = {}
    for row in rows:
        result.setdefault(int(row["series_id"]), []).append(_user_link_payload(row))
    return result


def fetch_user_cohort_links(
    cohort_ids: list[int], current_user_id: int
) -> dict[int, dict[str, object]]:
    if not cohort_ids:
        return {}
    placeholders = ", ".join(["%s"] * len(cohort_ids))
    rows = fetch_all(
        f"""
        SELECT
            cohort.series_id,
            cohort.id AS cohort_id,
            cohort.cohort_name,
            cohort.cohort_code,
            rel.order_item_id,
            rel.enroll_status,
            rel.enroll_at,
            item.order_id,
            item.order_item_status,
            item.item_name,
            item.payable_amount,
            o.order_no,
            o.order_status
        FROM student_cohort_rel AS rel
        JOIN order_item AS item ON item.id = rel.order_item_id
        JOIN `order` AS o ON o.id = item.order_id
        JOIN series_cohort AS cohort ON cohort.id = rel.cohort_id
        WHERE rel.user_id = %s
          AND cohort.id IN ({placeholders})
        ORDER BY rel.enroll_at DESC, rel.id DESC
        """,
        tuple([current_user_id, *cohort_ids]),
    )
    return {int(row["cohort_id"]): _user_link_payload(row) for row in rows}


def _user_link_payload(row: dict[str, Any]) -> dict[str, object]:
    return {
        "cohortId": row["cohort_id"],
        "cohortName": row["cohort_name"],
        "cohortCode": row["cohort_code"],
        "orderId": row["order_id"],
        "orderNo": row["order_no"],
        "orderStatusCode": row["order_status"],
        "orderItemId": row["order_item_id"],
        "orderItemStatusCode": row["order_item_status"],
        "itemName": row["item_name"],
        "payableAmount": money(row["payable_amount"]),
        "enrollStatusCode": row["enroll_status"],
        "enrollAt": format_datetime(row["enroll_at"]),
    }


def _series_list_item(
    row: dict[str, Any], user_links: list[dict[str, object]] | None = None
) -> dict[str, Any]:
    return {
        "seriesId": row["id"],
        "seriesName": row["series_name"],
        "coverUrl": row["cover_url"],
        "deliveryModeCode": row["delivery_mode"],
        "saleStatusCode": row["sale_status"],
        "avgScore": float(row["avg_score"] or 0),
        "reviewCount": int(row["review_count"] or 0),
        "myEnrollments": user_links or [],
    }
