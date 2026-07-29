from __future__ import annotations

import json
from collections import defaultdict
from typing import Annotated, Any

from fastapi import APIRouter, Path, Query

from ..database import fetch_all, fetch_one
from ..errors import bad_request, not_found
from ..utils import count_total, offset_limit, parse_date

router = APIRouter(prefix="/api/v1", tags=["products"])

HOTEL_TYPE_ENUM_DESC = (
    "取值：luxury=豪华型，business=商务型，resort=度假型，boutique=精品型。"
)
STAR_RATING_ENUM_DESC = "取值：3=三星，4=四星，5=五星。"
SCENIC_TYPE_ENUM_DESC = (
    "取值：theme_park=主题公园，museum=博物馆，mountain=山地景区，heritage=文化遗产，"
    "wetland=湿地公园，beach=海滨景区，snow=冰雪景区，forest=森林公园，waterfall=瀑布溪流，"
    "cultural_square=文化广场，ancient_town=古镇古街，religious=宗教场所，theme_water=水上乐园，"
    "zoo=动物园，botanical_garden=植物园，industrial_tourism=工业旅游，red_tourism=红色旅游，ecological=生态景区。"
)
SCENIC_RATING_ENUM_DESC = "取值：5A=5A级，4A=4A级，3A=3A级。"
AIRLINE_ENUM_DESC = (
    "取值：MU=东方航空，CA=中国国航，CZ=南方航空，HU=海南航空，HO=吉祥航空，3U=四川航空，"
    "FM=上海航空，9C=春秋航空，BK=奥凯航空，KN=中国联航，SC=山东航空，TV=西藏航空，"
    "EU=成都航空，G5=华夏航空，JR=天津航空，NS=河北航空，JD=首都航空，ZH=深圳航空，"
    "PN=西部航空，CO=长龙航空。"
)
FLIGHT_CABIN_CLASS_ENUM_DESC = "取值：economy=经济舱，business=商务舱。"
TRAIN_SEAT_CLASS_ENUM_DESC = (
    "取值：second_class=二等座，first_class=一等座，business=商务座。"
)
TRANSFER_SERVICE_TYPE_ENUM_DESC = "取值：airport_pickup=机场接机，airport_dropoff=机场送机，charter_daily=包车一日游，station_transfer=车站接送。"
TRANSFER_VEHICLE_TYPE_ENUM_DESC = (
    "取值：economy=经济型，comfort=舒适型，business=商务型，van=商务车。"
)


def _loads(value: Any, default: Any):
    if value in (None, ""):
        return default
    if isinstance(value, (dict, list)):
        return value
    return json.loads(value)


def _csv_or_none(values: list[str] | None) -> str | None:
    return ",".join(values) if values else None


@router.get("/hotels", summary="分页查询酒店")
def list_hotels(
    area_id: Annotated[
        int, Query(alias="areaId", description="酒店所在城市地区 ID，对应 areas.id。")
    ],
    check_in_date: Annotated[
        str,
        Query(
            alias="checkInDate",
            description="入住日期，格式 YYYY-MM-DD；必须早于 checkOutDate。",
        ),
    ],
    check_out_date: Annotated[
        str,
        Query(
            alias="checkOutDate",
            description="离店日期，格式 YYYY-MM-DD；酒店库存查询不包含离店当天。",
        ),
    ],
    star_rating_codes: Annotated[
        list[str] | None,
        Query(
            alias="starRatingCodes",
            description=f"星级多选筛选，同名 Query 参数重复传入。{STAR_RATING_ENUM_DESC}",
        ),
    ] = None,
    hotel_type_codes: Annotated[
        list[str] | None,
        Query(
            alias="hotelTypeCodes",
            description=f"酒店类型多选筛选，同名 Query 参数重复传入。{HOTEL_TYPE_ENUM_DESC}",
        ),
    ] = None,
    min_price: Annotated[
        float | None,
        Query(
            alias="minPrice",
            description="最低房价筛选，单位元，筛选 sale_price_amount >= minPrice。",
        ),
    ] = None,
    max_price: Annotated[
        float | None,
        Query(
            alias="maxPrice",
            description="最高房价筛选，单位元，筛选 sale_price_amount <= maxPrice。",
        ),
    ] = None,
    keyword: Annotated[
        str | None, Query(description="酒店名称关键字，按 hotel_name 模糊匹配。")
    ] = None,
    page_no: Annotated[int, Query(alias="pageNo", description="页码，从 1 开始。")] = 1,
    page_size: Annotated[
        int,
        Query(alias="pageSize", description="每页数量，默认 20，服务端最大限制 100。"),
    ] = 20,
):
    check_in = parse_date(check_in_date, "checkInDate")
    check_out = parse_date(check_out_date, "checkOutDate")
    if check_in >= check_out:
        raise bad_request("入住日期必须早于离店日期")
    stay_nights = (check_out - check_in).days
    offset, limit = offset_limit(page_no, page_size)
    hotel_conditions = [
        "h.area_id = %s",
        "h.status_code = 'active'",
    ]
    room_conditions = [
        "d.business_date >= %s",
        "d.business_date < %s",
        "d.status_code = 'active'",
        "d.available_inventory > 0",
    ]
    params: list[Any] = [check_in_date, check_out_date]
    hotel_params: list[Any] = [area_id]
    if star_rating_codes:
        hotel_conditions.append(
            f"h.star_rating_code IN ({','.join(['%s'] * len(star_rating_codes))})"
        )
        hotel_params.extend(star_rating_codes)
    if hotel_type_codes:
        hotel_conditions.append(
            f"h.hotel_type_code IN ({','.join(['%s'] * len(hotel_type_codes))})"
        )
        hotel_params.extend(hotel_type_codes)
    if keyword:
        hotel_conditions.append("h.hotel_name LIKE %s")
        hotel_params.append(f"%{keyword}%")
    if min_price is not None:
        room_conditions.append("d.sale_price_amount >= %s")
        params.append(min_price)
    if max_price is not None:
        room_conditions.append("d.sale_price_amount <= %s")
        params.append(max_price)
    room_where_clause = " AND ".join(room_conditions)
    hotel_where_clause = " AND ".join(hotel_conditions)
    rows = fetch_all(
        f"""
        SELECT
            h.id AS hotel_id,
            h.hotel_code,
            h.hotel_name,
            h.hotel_type_code,
            h.star_rating_code,
            h.area_id,
            h.address,
            h.summary,
            h.facility_payload,
            h.check_in_time,
            h.check_out_time,
            MIN(q.min_sale_price_amount) AS min_sale_price_amount,
            MIN(q.currency_code) AS currency_code,
            SUM(q.available_room_count) AS available_room_count
        FROM hotels h
        JOIN (
            SELECT
                rt.hotel_id,
                rt.id AS room_type_id,
                MIN(d.sale_price_amount) AS min_sale_price_amount,
                MIN(d.currency_code) AS currency_code,
                MIN(d.available_inventory) AS available_room_count
            FROM hotel_room_types rt
            JOIN hotel_room_daily d ON d.room_type_id = rt.id
            WHERE rt.status_code = 'active'
              AND {room_where_clause}
            GROUP BY rt.hotel_id, rt.id
            HAVING COUNT(DISTINCT d.business_date) = %s
        ) q ON q.hotel_id = h.id
        WHERE {hotel_where_clause}
        GROUP BY h.id
        ORDER BY min_sale_price_amount ASC, hotel_id ASC
        LIMIT %s OFFSET %s
        """,
        tuple(params + [stay_nights] + hotel_params + [limit, offset]),
    )
    total = count_total(
        f"""
        SELECT COUNT(*) AS total
        FROM (
            SELECT h.id
            FROM hotels h
            JOIN (
                SELECT
                    rt.hotel_id,
                    rt.id AS room_type_id,
                    MIN(d.sale_price_amount) AS min_sale_price_amount,
                    MIN(d.currency_code) AS currency_code,
                    MIN(d.available_inventory) AS available_room_count
                FROM hotel_room_types rt
                JOIN hotel_room_daily d ON d.room_type_id = rt.id
                WHERE rt.status_code = 'active'
                  AND {room_where_clause}
                GROUP BY rt.hotel_id, rt.id
                HAVING COUNT(DISTINCT d.business_date) = %s
            ) q ON q.hotel_id = h.id
            WHERE {hotel_where_clause}
            GROUP BY h.id
        ) AS counted
        """,
        tuple(params + [stay_nights] + hotel_params),
    )
    return {
        "list": [
            {
                "hotelId": row["hotel_id"],
                "hotelCode": row["hotel_code"],
                "hotelName": row["hotel_name"],
                "hotelTypeCode": row["hotel_type_code"],
                "starRatingCode": row["star_rating_code"],
                "areaId": row["area_id"],
                "address": row["address"],
                "summary": row["summary"],
                "facilityTags": _loads(row["facility_payload"], []),
                "checkInTime": str(row["check_in_time"])
                if row["check_in_time"]
                else None,
                "checkOutTime": str(row["check_out_time"])
                if row["check_out_time"]
                else None,
                "minSalePriceAmount": float(row["min_sale_price_amount"]),
                "currencyCode": row["currency_code"],
                "availableRoomCount": int(row["available_room_count"]),
            }
            for row in rows
        ],
        "pageNo": page_no,
        "pageSize": page_size,
        "total": total,
    }


@router.get("/hotels/{hotelId}", summary="查询酒店详情")
def get_hotel_detail(
    hotel_id: Annotated[
        int,
        Path(
            alias="hotelId", description="酒店 ID，对应 hotels.id；仅返回 active 酒店。"
        ),
    ],
):
    row = fetch_one(
        """
        SELECT
            h.id AS hotel_id, h.hotel_code, h.hotel_name, h.hotel_type_code,
            h.star_rating_code, h.address, h.latitude, h.longitude, h.summary,
            h.facility_payload, h.check_in_time, h.check_out_time, h.contact_phone,
            r.hold_until_time, r.min_stay_nights, r.max_room_count, r.rule_payload
        FROM hotels h
        LEFT JOIN hotel_booking_rules r
          ON r.hotel_id = h.id AND r.status_code = 'active'
        WHERE h.id = %s AND h.status_code = 'active'
        """,
        (hotel_id,),
    )
    if row is None:
        raise not_found("酒店不存在")
    return {
        "hotelId": row["hotel_id"],
        "hotelCode": row["hotel_code"],
        "hotelName": row["hotel_name"],
        "hotelTypeCode": row["hotel_type_code"],
        "starRatingCode": row["star_rating_code"],
        "address": row["address"],
        "latitude": float(row["latitude"]) if row["latitude"] is not None else None,
        "longitude": float(row["longitude"]) if row["longitude"] is not None else None,
        "summary": row["summary"],
        "facilityTags": _loads(row["facility_payload"], []),
        "checkInTime": str(row["check_in_time"]) if row["check_in_time"] else None,
        "checkOutTime": str(row["check_out_time"]) if row["check_out_time"] else None,
        "contactPhone": row["contact_phone"],
        "bookingRule": {
            "holdUntilTime": str(row["hold_until_time"])
            if row["hold_until_time"]
            else None,
            "minStayNights": row["min_stay_nights"],
            "maxRoomCount": row["max_room_count"],
            "rulePayload": _loads(row["rule_payload"], {}),
        }
        if row["hold_until_time"]
        or row["rule_payload"]
        or row["min_stay_nights"] is not None
        else None,
    }


@router.get("/hotels/{hotelId}/room-types", summary="查询酒店房型")
def list_hotel_room_types(
    hotel_id: Annotated[
        int, Path(alias="hotelId", description="酒店 ID，对应 hotels.id。")
    ],
    check_in_date: Annotated[
        str,
        Query(
            alias="checkInDate",
            description="入住日期，格式 YYYY-MM-DD；必须早于 checkOutDate。",
        ),
    ],
    check_out_date: Annotated[
        str,
        Query(
            alias="checkOutDate",
            description="离店日期，格式 YYYY-MM-DD；返回日历不包含离店当天。",
        ),
    ],
):
    if parse_date(check_in_date, "checkInDate") >= parse_date(
        check_out_date, "checkOutDate"
    ):
        raise bad_request("入住日期必须早于离店日期")
    rows = fetch_all(
        """
        SELECT
            rt.id AS room_type_id, rt.room_type_code, rt.room_type_name,
            rt.room_type_category_code, rt.area_size, rt.max_guests, rt.amenity_payload,
            d.business_date, d.available_inventory, d.sale_price_amount, d.currency_code,
            d.status_code
        FROM hotel_room_types rt
        JOIN hotel_room_daily d ON d.room_type_id = rt.id
        WHERE rt.hotel_id = %s
          AND rt.status_code = 'active'
          AND d.business_date >= %s
          AND d.business_date < %s
          AND d.status_code = 'active'
        ORDER BY rt.id ASC, d.business_date ASC
        """,
        (hotel_id, check_in_date, check_out_date),
    )
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["room_type_id"]].append(row)
    result = []
    needed_days = (
        parse_date(check_out_date, "checkOutDate")
        - parse_date(check_in_date, "checkInDate")
    ).days
    for room_type_id, calendars in grouped.items():
        if len(calendars) != needed_days:
            continue
        if any(c["available_inventory"] <= 0 for c in calendars):
            continue
        first = calendars[0]
        result.append(
            {
                "roomTypeId": room_type_id,
                "roomTypeCode": first["room_type_code"],
                "roomTypeName": first["room_type_name"],
                "roomTypeCategoryCode": first["room_type_category_code"],
                "areaSize": first["area_size"],
                "maxGuests": first["max_guests"],
                "amenityPayload": _loads(first["amenity_payload"], []),
                "firstNightSalePriceAmount": float(first["sale_price_amount"]),
                "currencyCode": first["currency_code"],
                "availableRoomCount": min(
                    int(c["available_inventory"]) for c in calendars
                ),
                "calendar": [
                    {
                        "businessDate": str(c["business_date"]),
                        "availableInventory": int(c["available_inventory"]),
                        "salePriceAmount": float(c["sale_price_amount"]),
                        "statusCode": c["status_code"],
                    }
                    for c in calendars
                ],
            }
        )
    return {"list": result}


@router.get("/scenic-spots", summary="分页查询景点")
def list_scenic_spots(
    area_id: Annotated[
        int, Query(alias="areaId", description="景点所在城市地区 ID，对应 areas.id。")
    ],
    travel_date: Annotated[
        str,
        Query(
            alias="travelDate",
            description="游玩日期，格式 YYYY-MM-DD；用于查询当天票种价格和库存。",
        ),
    ],
    scenic_type_codes: Annotated[
        list[str] | None,
        Query(
            alias="scenicTypeCodes",
            description=f"景点类型多选筛选，同名 Query 参数重复传入。{SCENIC_TYPE_ENUM_DESC}",
        ),
    ] = None,
    rating_codes: Annotated[
        list[str] | None,
        Query(
            alias="ratingCodes",
            description=f"景点等级多选筛选，同名 Query 参数重复传入。{SCENIC_RATING_ENUM_DESC}",
        ),
    ] = None,
    keyword: Annotated[
        str | None, Query(description="景点名称关键字，按 scenic_name 模糊匹配。")
    ] = None,
    page_no: Annotated[int, Query(alias="pageNo", description="页码，从 1 开始。")] = 1,
    page_size: Annotated[
        int,
        Query(alias="pageSize", description="每页数量，默认 20，服务端最大限制 100。"),
    ] = 20,
):
    offset, limit = offset_limit(page_no, page_size)
    conditions = [
        "s.area_id = %s",
        "s.status_code = 'active'",
        "d.business_date = %s",
        "d.status_code = 'active'",
        "d.available_inventory > 0",
    ]
    params: list[Any] = [area_id, travel_date]
    if scenic_type_codes:
        conditions.append(
            f"s.scenic_type_code IN ({','.join(['%s'] * len(scenic_type_codes))})"
        )
        params.extend(scenic_type_codes)
    if rating_codes:
        conditions.append(f"s.rating_code IN ({','.join(['%s'] * len(rating_codes))})")
        params.extend(rating_codes)
    if keyword:
        conditions.append("s.scenic_name LIKE %s")
        params.append(f"%{keyword}%")
    where_clause = " AND ".join(conditions)
    rows = fetch_all(
        f"""
        SELECT
            s.id AS scenic_spot_id, s.scenic_code, s.scenic_name, s.scenic_type_code,
            s.rating_code, s.area_id, s.address, s.summary, s.tag_payload,
            s.open_time, s.close_time, MIN(d.sale_price_amount) AS min_sale_price_amount,
            MIN(d.currency_code) AS currency_code, SUM(d.available_inventory) AS available_ticket_count
        FROM scenic_spots s
        JOIN scenic_ticket_types t ON t.scenic_spot_id = s.id AND t.status_code = 'active'
        JOIN scenic_ticket_daily d ON d.ticket_type_id = t.id
        WHERE {where_clause}
        GROUP BY s.id
        ORDER BY min_sale_price_amount ASC, scenic_spot_id ASC
        LIMIT %s OFFSET %s
        """,
        tuple(params + [limit, offset]),
    )
    total = count_total(
        f"""
        SELECT COUNT(*) AS total
        FROM (
            SELECT s.id
            FROM scenic_spots s
            JOIN scenic_ticket_types t ON t.scenic_spot_id = s.id AND t.status_code = 'active'
            JOIN scenic_ticket_daily d ON d.ticket_type_id = t.id
            WHERE {where_clause}
            GROUP BY s.id
        ) AS counted
        """,
        tuple(params),
    )
    return {
        "list": [
            {
                "scenicSpotId": row["scenic_spot_id"],
                "scenicCode": row["scenic_code"],
                "scenicName": row["scenic_name"],
                "scenicTypeCode": row["scenic_type_code"],
                "ratingCode": row["rating_code"],
                "areaId": row["area_id"],
                "address": row["address"],
                "summary": row["summary"],
                "tagPayload": _loads(row["tag_payload"], []),
                "openTime": str(row["open_time"]) if row["open_time"] else None,
                "closeTime": str(row["close_time"]) if row["close_time"] else None,
                "minSalePriceAmount": float(row["min_sale_price_amount"]),
                "currencyCode": row["currency_code"],
                "availableTicketCount": int(row["available_ticket_count"]),
            }
            for row in rows
        ],
        "pageNo": page_no,
        "pageSize": page_size,
        "total": total,
    }


@router.get("/scenic-spots/{scenicSpotId}", summary="查询景点详情")
def get_scenic_detail(
    scenic_spot_id: Annotated[
        int,
        Path(
            alias="scenicSpotId",
            description="景点 ID，对应 scenic_spots.id；仅返回 active 景点。",
        ),
    ],
):
    row = fetch_one(
        """
        SELECT
            s.id AS scenic_spot_id, s.scenic_code, s.scenic_name, s.scenic_type_code,
            s.rating_code, s.address, s.latitude, s.longitude, s.summary, s.tag_payload,
            s.open_time, s.close_time, r.latest_booking_time, r.rule_payload
        FROM scenic_spots s
        LEFT JOIN scenic_booking_rules r
          ON r.scenic_spot_id = s.id AND r.status_code = 'active'
        WHERE s.id = %s AND s.status_code = 'active'
        """,
        (scenic_spot_id,),
    )
    if row is None:
        raise not_found("景点不存在")
    return {
        "scenicSpotId": row["scenic_spot_id"],
        "scenicCode": row["scenic_code"],
        "scenicName": row["scenic_name"],
        "scenicTypeCode": row["scenic_type_code"],
        "ratingCode": row["rating_code"],
        "address": row["address"],
        "latitude": float(row["latitude"]) if row["latitude"] is not None else None,
        "longitude": float(row["longitude"]) if row["longitude"] is not None else None,
        "summary": row["summary"],
        "tagPayload": _loads(row["tag_payload"], []),
        "openTime": str(row["open_time"]) if row["open_time"] else None,
        "closeTime": str(row["close_time"]) if row["close_time"] else None,
        "bookingRule": {
            "latestBookingTime": str(row["latest_booking_time"])
            if row["latest_booking_time"]
            else None,
            "rulePayload": _loads(row["rule_payload"], {}),
        }
        if row["latest_booking_time"] or row["rule_payload"]
        else None,
    }


@router.get("/scenic-spots/{scenicSpotId}/ticket-types", summary="查询景点票种")
def list_ticket_types(
    scenic_spot_id: Annotated[
        int, Path(alias="scenicSpotId", description="景点 ID，对应 scenic_spots.id。")
    ],
    travel_date: Annotated[
        str,
        Query(
            alias="travelDate",
            description="游玩日期，格式 YYYY-MM-DD；用于查询当天票种价格和库存。",
        ),
    ],
):
    rows = fetch_all(
        """
        SELECT
            t.id AS ticket_type_id, t.ticket_type_code, t.ticket_type_name,
            t.ticket_category_code, t.benefit_payload,
            d.business_date, d.available_inventory, d.sale_price_amount, d.currency_code, d.status_code
        FROM scenic_ticket_types t
        JOIN scenic_ticket_daily d ON d.ticket_type_id = t.id
        WHERE t.scenic_spot_id = %s
          AND t.status_code = 'active'
          AND d.business_date = %s
          AND d.status_code = 'active'
          AND d.available_inventory > 0
        ORDER BY t.id ASC
        """,
        (scenic_spot_id, travel_date),
    )
    return {
        "list": [
            {
                "ticketTypeId": row["ticket_type_id"],
                "ticketTypeCode": row["ticket_type_code"],
                "ticketTypeName": row["ticket_type_name"],
                "ticketCategoryCode": row["ticket_category_code"],
                "benefitPayload": _loads(row["benefit_payload"], {}),
                "salePriceAmount": float(row["sale_price_amount"]),
                "currencyCode": row["currency_code"],
                "availableTicketCount": int(row["available_inventory"]),
                "calendar": [
                    {
                        "businessDate": str(row["business_date"]),
                        "availableInventory": int(row["available_inventory"]),
                        "salePriceAmount": float(row["sale_price_amount"]),
                        "statusCode": row["status_code"],
                    }
                ],
            }
            for row in rows
        ]
    }


@router.get("/flights/search", summary="搜索航班")
def search_flights(
    departure_area_id: Annotated[
        int,
        Query(
            alias="departureAreaId",
            description="出发城市地区 ID，对应 flight_routes.departure_area_id。",
        ),
    ],
    arrival_area_id: Annotated[
        int,
        Query(
            alias="arrivalAreaId",
            description="到达城市地区 ID，对应 flight_routes.arrival_area_id。",
        ),
    ],
    departure_date: Annotated[
        str,
        Query(
            alias="departureDate",
            description="出发日期，格式 YYYY-MM-DD，按 flight_departures.departure_time 日期部分筛选。",
        ),
    ],
    cabin_class_codes: Annotated[
        list[str] | None,
        Query(
            alias="cabinClassCodes",
            description=f"舱位等级多选筛选，同名 Query 参数重复传入。{FLIGHT_CABIN_CLASS_ENUM_DESC}",
        ),
    ] = None,
    airline_codes: Annotated[
        list[str] | None,
        Query(
            alias="airlineCodes",
            description=f"航司编码多选筛选，同名 Query 参数重复传入。{AIRLINE_ENUM_DESC}",
        ),
    ] = None,
    departure_time_from: Annotated[
        str | None,
        Query(
            alias="departureTimeFrom",
            description="起飞时间下限，格式 HH:mm:ss，仅比较当天时间部分。",
        ),
    ] = None,
    departure_time_to: Annotated[
        str | None,
        Query(
            alias="departureTimeTo",
            description="起飞时间上限，格式 HH:mm:ss，仅比较当天时间部分。",
        ),
    ] = None,
    page_no: Annotated[int, Query(alias="pageNo", description="页码，从 1 开始。")] = 1,
    page_size: Annotated[
        int,
        Query(alias="pageSize", description="每页数量，默认 20，服务端最大限制 100。"),
    ] = 20,
):
    offset, limit = offset_limit(page_no, page_size)
    conditions = [
        "r.departure_area_id = %s",
        "r.arrival_area_id = %s",
        "r.status_code = 'active'",
        "DATE(d.departure_time) = %s",
        "d.status_code = 'scheduled'",
        "i.status_code = 'active'",
        "i.available_inventory > 0",
    ]
    params: list[Any] = [departure_area_id, arrival_area_id, departure_date]
    if cabin_class_codes:
        conditions.append(
            f"i.cabin_class_code IN ({','.join(['%s'] * len(cabin_class_codes))})"
        )
        params.extend(cabin_class_codes)
    if airline_codes:
        conditions.append(
            f"r.airline_code IN ({','.join(['%s'] * len(airline_codes))})"
        )
        params.extend(airline_codes)
    if departure_time_from:
        conditions.append("TIME(d.departure_time) >= %s")
        params.append(departure_time_from)
    if departure_time_to:
        conditions.append("TIME(d.departure_time) <= %s")
        params.append(departure_time_to)
    where_clause = " AND ".join(conditions)
    rows = fetch_all(
        f"""
        SELECT
            d.id AS departure_id,
            d.departure_instance_code,
            r.flight_no,
            r.airline_code,
            r.departure_area_id,
            r.arrival_area_id,
            dep_hub.hub_name AS departure_hub_name,
            arr_hub.hub_name AS arrival_hub_name,
            d.departure_time,
            d.arrival_time,
            r.duration_minutes,
            MIN(i.sale_price_amount) AS min_sale_price_amount,
            MIN(i.currency_code) AS currency_code,
            GROUP_CONCAT(DISTINCT i.cabin_class_code ORDER BY i.cabin_class_code) AS cabin_classes
        FROM flight_routes r
        JOIN flight_departures d ON d.flight_route_id = r.id
        JOIN flight_cabin_inventory i ON i.flight_departure_id = d.id
        JOIN transport_hubs dep_hub ON dep_hub.id = r.departure_hub_id
        JOIN transport_hubs arr_hub ON arr_hub.id = r.arrival_hub_id
        WHERE {where_clause}
        GROUP BY d.id
        ORDER BY d.departure_time ASC, departure_id ASC
        LIMIT %s OFFSET %s
        """,
        tuple(params + [limit, offset]),
    )
    total = count_total(
        f"""
        SELECT COUNT(*) AS total
        FROM (
            SELECT d.id
            FROM flight_routes r
            JOIN flight_departures d ON d.flight_route_id = r.id
            JOIN flight_cabin_inventory i ON i.flight_departure_id = d.id
            JOIN transport_hubs dep_hub ON dep_hub.id = r.departure_hub_id
            JOIN transport_hubs arr_hub ON arr_hub.id = r.arrival_hub_id
            WHERE {where_clause}
            GROUP BY d.id
        ) AS counted
        """,
        tuple(params),
    )
    return {
        "list": [
            {
                "departureId": row["departure_id"],
                "departureInstanceCode": row["departure_instance_code"],
                "flightNo": row["flight_no"],
                "airlineCode": row["airline_code"],
                "departureAreaId": row["departure_area_id"],
                "arrivalAreaId": row["arrival_area_id"],
                "departureHubName": row["departure_hub_name"],
                "arrivalHubName": row["arrival_hub_name"],
                "departureTime": row["departure_time"].strftime("%Y-%m-%d %H:%M:%S"),
                "arrivalTime": row["arrival_time"].strftime("%Y-%m-%d %H:%M:%S"),
                "durationMinutes": row["duration_minutes"],
                "minSalePriceAmount": float(row["min_sale_price_amount"]),
                "currencyCode": row["currency_code"],
                "availableCabinClasses": row["cabin_classes"].split(",")
                if row["cabin_classes"]
                else [],
            }
            for row in rows
        ],
        "pageNo": page_no,
        "pageSize": page_size,
        "total": total,
    }


@router.get("/flights/{departureId}", summary="查询航班详情")
def get_flight_detail(
    departure_id: Annotated[
        int,
        Path(
            alias="departureId", description="航班实例 ID，对应 flight_departures.id。"
        ),
    ],
):
    header = fetch_one(
        """
        SELECT
            d.id AS departure_id, d.departure_instance_code, d.departure_time, d.arrival_time,
            d.rule_payload, r.flight_no, r.airline_code, r.duration_minutes,
            dep_hub.hub_name AS departure_hub_name, arr_hub.hub_name AS arrival_hub_name
        FROM flight_departures d
        JOIN flight_routes r ON r.id = d.flight_route_id AND r.status_code = 'active'
        JOIN transport_hubs dep_hub ON dep_hub.id = r.departure_hub_id
        JOIN transport_hubs arr_hub ON arr_hub.id = r.arrival_hub_id
        WHERE d.id = %s AND d.status_code = 'scheduled'
        """,
        (departure_id,),
    )
    if header is None:
        raise not_found("航班不存在")
    cabins = fetch_all(
        """
        SELECT cabin_class_code, sale_price_amount, currency_code, available_inventory, status_code
        FROM flight_cabin_inventory
        WHERE flight_departure_id = %s AND status_code = 'active'
        ORDER BY sale_price_amount ASC, cabin_class_code ASC
        """,
        (departure_id,),
    )
    return {
        "departureId": header["departure_id"],
        "departureInstanceCode": header["departure_instance_code"],
        "flightNo": header["flight_no"],
        "airlineCode": header["airline_code"],
        "departureHubName": header["departure_hub_name"],
        "arrivalHubName": header["arrival_hub_name"],
        "departureTime": header["departure_time"].strftime("%Y-%m-%d %H:%M:%S"),
        "arrivalTime": header["arrival_time"].strftime("%Y-%m-%d %H:%M:%S"),
        "durationMinutes": header["duration_minutes"],
        "rulePayload": _loads(header["rule_payload"], {}),
        "cabins": [
            {
                "cabinClassCode": row["cabin_class_code"],
                "salePriceAmount": float(row["sale_price_amount"]),
                "currencyCode": row["currency_code"],
                "availableInventory": int(row["available_inventory"]),
                "statusCode": row["status_code"],
            }
            for row in cabins
        ],
    }


@router.get("/trains/search", summary="搜索火车车次")
def search_trains(
    departure_area_id: Annotated[
        int,
        Query(
            alias="departureAreaId",
            description="出发城市地区 ID，对应 train_routes.departure_area_id。",
        ),
    ],
    arrival_area_id: Annotated[
        int,
        Query(
            alias="arrivalAreaId",
            description="到达城市地区 ID，对应 train_routes.arrival_area_id。",
        ),
    ],
    departure_date: Annotated[
        str,
        Query(
            alias="departureDate",
            description="出发日期，格式 YYYY-MM-DD，按 train_departures.departure_time 日期部分筛选。",
        ),
    ],
    seat_class_codes: Annotated[
        list[str] | None,
        Query(
            alias="seatClassCodes",
            description=f"席位等级多选筛选。{TRAIN_SEAT_CLASS_ENUM_DESC}",
        ),
    ] = None,
    train_no: Annotated[
        str | None,
        Query(
            alias="trainNo",
            description="车次号关键字，按 train_routes.train_no 模糊匹配。",
        ),
    ] = None,
    departure_time_from: Annotated[
        str | None,
        Query(
            alias="departureTimeFrom",
            description="发车时间下限，格式 HH:mm:ss，仅比较当天时间部分。",
        ),
    ] = None,
    departure_time_to: Annotated[
        str | None,
        Query(
            alias="departureTimeTo",
            description="发车时间上限，格式 HH:mm:ss，仅比较当天时间部分。",
        ),
    ] = None,
    page_no: Annotated[int, Query(alias="pageNo", description="页码，从 1 开始。")] = 1,
    page_size: Annotated[
        int,
        Query(alias="pageSize", description="每页数量，默认 20，服务端最大限制 100。"),
    ] = 20,
):
    offset, limit = offset_limit(page_no, page_size)
    conditions = [
        "r.departure_area_id = %s",
        "r.arrival_area_id = %s",
        "r.status_code = 'active'",
        "DATE(d.departure_time) = %s",
        "d.status_code = 'scheduled'",
        "i.status_code = 'active'",
        "i.available_inventory > 0",
    ]
    params: list[Any] = [departure_area_id, arrival_area_id, departure_date]
    if seat_class_codes:
        conditions.append(
            f"i.seat_class_code IN ({','.join(['%s'] * len(seat_class_codes))})"
        )
        params.extend(seat_class_codes)
    if train_no:
        conditions.append("r.train_no LIKE %s")
        params.append(f"%{train_no}%")
    if departure_time_from:
        conditions.append("TIME(d.departure_time) >= %s")
        params.append(departure_time_from)
    if departure_time_to:
        conditions.append("TIME(d.departure_time) <= %s")
        params.append(departure_time_to)
    where_clause = " AND ".join(conditions)
    rows = fetch_all(
        f"""
        SELECT
            d.id AS departure_id,
            d.departure_instance_code,
            r.train_no,
            r.departure_area_id,
            r.arrival_area_id,
            dep_hub.hub_name AS departure_hub_name,
            arr_hub.hub_name AS arrival_hub_name,
            d.departure_time,
            d.arrival_time,
            r.duration_minutes,
            MIN(i.sale_price_amount) AS min_sale_price_amount,
            MIN(i.currency_code) AS currency_code,
            GROUP_CONCAT(DISTINCT i.seat_class_code ORDER BY i.seat_class_code) AS seat_classes
        FROM train_routes r
        JOIN train_departures d ON d.train_route_id = r.id
        JOIN train_seat_inventory i ON i.train_departure_id = d.id
        JOIN transport_hubs dep_hub ON dep_hub.id = r.departure_hub_id
        JOIN transport_hubs arr_hub ON arr_hub.id = r.arrival_hub_id
        WHERE {where_clause}
        GROUP BY d.id
        ORDER BY d.departure_time ASC, departure_id ASC
        LIMIT %s OFFSET %s
        """,
        tuple(params + [limit, offset]),
    )
    total = count_total(
        f"""
        SELECT COUNT(*) AS total
        FROM (
            SELECT d.id
            FROM train_routes r
            JOIN train_departures d ON d.train_route_id = r.id
            JOIN train_seat_inventory i ON i.train_departure_id = d.id
            JOIN transport_hubs dep_hub ON dep_hub.id = r.departure_hub_id
            JOIN transport_hubs arr_hub ON arr_hub.id = r.arrival_hub_id
            WHERE {where_clause}
            GROUP BY d.id
        ) AS counted
        """,
        tuple(params),
    )
    return {
        "list": [
            {
                "departureId": row["departure_id"],
                "departureInstanceCode": row["departure_instance_code"],
                "trainNo": row["train_no"],
                "departureAreaId": row["departure_area_id"],
                "arrivalAreaId": row["arrival_area_id"],
                "departureHubName": row["departure_hub_name"],
                "arrivalHubName": row["arrival_hub_name"],
                "departureTime": row["departure_time"].strftime("%Y-%m-%d %H:%M:%S"),
                "arrivalTime": row["arrival_time"].strftime("%Y-%m-%d %H:%M:%S"),
                "durationMinutes": row["duration_minutes"],
                "minSalePriceAmount": float(row["min_sale_price_amount"]),
                "currencyCode": row["currency_code"],
                "availableSeatClasses": row["seat_classes"].split(",")
                if row["seat_classes"]
                else [],
            }
            for row in rows
        ],
        "pageNo": page_no,
        "pageSize": page_size,
        "total": total,
    }


@router.get("/trains/{departureId}", summary="查询火车车次详情")
def get_train_detail(
    departure_id: Annotated[
        int,
        Path(
            alias="departureId",
            description="火车班次实例 ID，对应 train_departures.id。",
        ),
    ],
):
    header = fetch_one(
        """
        SELECT
            d.id AS departure_id, d.departure_instance_code, d.departure_time, d.arrival_time,
            r.train_no, r.duration_minutes,
            dep_hub.hub_name AS departure_hub_name, arr_hub.hub_name AS arrival_hub_name
        FROM train_departures d
        JOIN train_routes r ON r.id = d.train_route_id AND r.status_code = 'active'
        JOIN transport_hubs dep_hub ON dep_hub.id = r.departure_hub_id
        JOIN transport_hubs arr_hub ON arr_hub.id = r.arrival_hub_id
        WHERE d.id = %s AND d.status_code = 'scheduled'
        """,
        (departure_id,),
    )
    if header is None:
        raise not_found("车次不存在")
    seats = fetch_all(
        """
        SELECT seat_class_code, sale_price_amount, currency_code, available_inventory, status_code
        FROM train_seat_inventory
        WHERE train_departure_id = %s AND status_code = 'active'
        ORDER BY sale_price_amount ASC, seat_class_code ASC
        """,
        (departure_id,),
    )
    return {
        "departureId": header["departure_id"],
        "departureInstanceCode": header["departure_instance_code"],
        "trainNo": header["train_no"],
        "departureHubName": header["departure_hub_name"],
        "arrivalHubName": header["arrival_hub_name"],
        "departureTime": header["departure_time"].strftime("%Y-%m-%d %H:%M:%S"),
        "arrivalTime": header["arrival_time"].strftime("%Y-%m-%d %H:%M:%S"),
        "durationMinutes": header["duration_minutes"],
        "seats": [
            {
                "seatClassCode": row["seat_class_code"],
                "salePriceAmount": float(row["sale_price_amount"]),
                "currencyCode": row["currency_code"],
                "availableInventory": int(row["available_inventory"]),
                "statusCode": row["status_code"],
            }
            for row in seats
        ],
    }


@router.get("/buses/search", summary="搜索汽车班次")
def search_buses(
    departure_area_id: Annotated[
        int,
        Query(
            alias="departureAreaId",
            description="出发城市地区 ID，对应 bus_routes.departure_area_id。",
        ),
    ],
    arrival_area_id: Annotated[
        int,
        Query(
            alias="arrivalAreaId",
            description="到达城市地区 ID，对应 bus_routes.arrival_area_id。",
        ),
    ],
    departure_date: Annotated[
        str,
        Query(
            alias="departureDate",
            description="发车日期，格式 YYYY-MM-DD，按 bus_departures.departure_time 日期部分筛选。",
        ),
    ],
    route_name: Annotated[
        str | None,
        Query(
            alias="routeName",
            description="汽车班线名称关键字，按 bus_routes.route_name 模糊匹配。",
        ),
    ] = None,
    departure_time_from: Annotated[
        str | None,
        Query(
            alias="departureTimeFrom",
            description="发车时间下限，格式 HH:mm:ss，仅比较当天时间部分。",
        ),
    ] = None,
    departure_time_to: Annotated[
        str | None,
        Query(
            alias="departureTimeTo",
            description="发车时间上限，格式 HH:mm:ss，仅比较当天时间部分。",
        ),
    ] = None,
    page_no: Annotated[int, Query(alias="pageNo", description="页码，从 1 开始。")] = 1,
    page_size: Annotated[
        int,
        Query(alias="pageSize", description="每页数量，默认 20，服务端最大限制 100。"),
    ] = 20,
):
    offset, limit = offset_limit(page_no, page_size)
    conditions = [
        "r.departure_area_id = %s",
        "r.arrival_area_id = %s",
        "r.status_code = 'active'",
        "DATE(d.departure_time) = %s",
        "d.status_code = 'scheduled'",
        "i.status_code = 'active'",
        "i.available_inventory > 0",
    ]
    params: list[Any] = [departure_area_id, arrival_area_id, departure_date]
    if route_name:
        conditions.append("r.route_name LIKE %s")
        params.append(f"%{route_name}%")
    if departure_time_from:
        conditions.append("TIME(d.departure_time) >= %s")
        params.append(departure_time_from)
    if departure_time_to:
        conditions.append("TIME(d.departure_time) <= %s")
        params.append(departure_time_to)
    where_clause = " AND ".join(conditions)
    rows = fetch_all(
        f"""
        SELECT
            d.id AS departure_id,
            d.departure_instance_code,
            r.route_name,
            r.departure_area_id,
            r.arrival_area_id,
            dep_hub.hub_name AS departure_hub_name,
            arr_hub.hub_name AS arrival_hub_name,
            d.departure_time,
            d.arrival_time,
            r.duration_minutes,
            i.sale_price_amount,
            i.currency_code,
            i.available_inventory
        FROM bus_routes r
        JOIN bus_departures d ON d.bus_route_id = r.id
        JOIN bus_seat_inventory i ON i.bus_departure_id = d.id
        JOIN transport_hubs dep_hub ON dep_hub.id = r.departure_hub_id
        JOIN transport_hubs arr_hub ON arr_hub.id = r.arrival_hub_id
        WHERE {where_clause}
        ORDER BY d.departure_time ASC, departure_id ASC
        LIMIT %s OFFSET %s
        """,
        tuple(params + [limit, offset]),
    )
    total = count_total(
        f"""
        SELECT COUNT(*) AS total
        FROM bus_routes r
        JOIN bus_departures d ON d.bus_route_id = r.id
        JOIN bus_seat_inventory i ON i.bus_departure_id = d.id
        JOIN transport_hubs dep_hub ON dep_hub.id = r.departure_hub_id
        JOIN transport_hubs arr_hub ON arr_hub.id = r.arrival_hub_id
        WHERE {where_clause}
        """,
        tuple(params),
    )
    return {
        "list": [
            {
                "departureId": row["departure_id"],
                "departureInstanceCode": row["departure_instance_code"],
                "routeName": row["route_name"],
                "departureAreaId": row["departure_area_id"],
                "arrivalAreaId": row["arrival_area_id"],
                "departureHubName": row["departure_hub_name"],
                "arrivalHubName": row["arrival_hub_name"],
                "departureTime": row["departure_time"].strftime("%Y-%m-%d %H:%M:%S"),
                "arrivalTime": row["arrival_time"].strftime("%Y-%m-%d %H:%M:%S"),
                "durationMinutes": row["duration_minutes"],
                "salePriceAmount": float(row["sale_price_amount"]),
                "currencyCode": row["currency_code"],
                "availableInventory": int(row["available_inventory"]),
            }
            for row in rows
        ],
        "pageNo": page_no,
        "pageSize": page_size,
        "total": total,
    }


@router.get("/buses/{departureId}", summary="查询汽车班次详情")
def get_bus_detail(
    departure_id: Annotated[
        int,
        Path(
            alias="departureId", description="汽车班次实例 ID，对应 bus_departures.id。"
        ),
    ],
):
    header = fetch_one(
        """
        SELECT
            d.id AS departure_id, d.departure_instance_code, d.departure_time, d.arrival_time,
            r.route_name, r.duration_minutes,
            dep_hub.hub_name AS departure_hub_name, arr_hub.hub_name AS arrival_hub_name
        FROM bus_departures d
        JOIN bus_routes r ON r.id = d.bus_route_id AND r.status_code = 'active'
        JOIN transport_hubs dep_hub ON dep_hub.id = r.departure_hub_id
        JOIN transport_hubs arr_hub ON arr_hub.id = r.arrival_hub_id
        WHERE d.id = %s AND d.status_code = 'scheduled'
        """,
        (departure_id,),
    )
    if header is None:
        raise not_found("班次不存在")
    seats = fetch_all(
        """
        SELECT seat_class_code, sale_price_amount, currency_code, available_inventory, status_code
        FROM bus_seat_inventory
        WHERE bus_departure_id = %s AND status_code = 'active'
        """,
        (departure_id,),
    )
    return {
        "departureId": header["departure_id"],
        "departureInstanceCode": header["departure_instance_code"],
        "routeName": header["route_name"],
        "departureHubName": header["departure_hub_name"],
        "arrivalHubName": header["arrival_hub_name"],
        "departureTime": header["departure_time"].strftime("%Y-%m-%d %H:%M:%S"),
        "arrivalTime": header["arrival_time"].strftime("%Y-%m-%d %H:%M:%S"),
        "durationMinutes": header["duration_minutes"],
        "seats": [
            {
                "seatClassCode": row["seat_class_code"],
                "salePriceAmount": float(row["sale_price_amount"]),
                "currencyCode": row["currency_code"],
                "availableInventory": int(row["available_inventory"]),
                "statusCode": row["status_code"],
            }
            for row in seats
        ],
    }


@router.get("/transfers", summary="分页查询接送服务")
def list_transfers(
    area_id: Annotated[
        int,
        Query(
            alias="areaId",
            description="服务城市地区 ID，对应 transfer_services.area_id。",
        ),
    ],
    business_date: Annotated[
        str,
        Query(
            alias="businessDate",
            description="服务日期，格式 YYYY-MM-DD，用于查询当天运力。",
        ),
    ],
    service_type_codes: Annotated[
        list[str] | None,
        Query(
            alias="serviceTypeCodes",
            description=f"服务类型多选筛选，同名 Query 参数重复传入。{TRANSFER_SERVICE_TYPE_ENUM_DESC}",
        ),
    ] = None,
    vehicle_type_codes: Annotated[
        list[str] | None,
        Query(
            alias="vehicleTypeCodes",
            description=f"车型多选筛选，同名 Query 参数重复传入。{TRANSFER_VEHICLE_TYPE_ENUM_DESC}",
        ),
    ] = None,
    page_no: Annotated[int, Query(alias="pageNo", description="页码，从 1 开始。")] = 1,
    page_size: Annotated[
        int,
        Query(alias="pageSize", description="每页数量，默认 20，服务端最大限制 100。"),
    ] = 20,
):
    offset, limit = offset_limit(page_no, page_size)
    conditions = [
        "s.area_id = %s",
        "s.status_code = 'active'",
        "c.business_date = %s",
        "c.status_code = 'active'",
        "c.available_inventory > 0",
    ]
    params: list[Any] = [area_id, business_date]
    if service_type_codes:
        conditions.append(
            f"s.service_type_code IN ({','.join(['%s'] * len(service_type_codes))})"
        )
        params.extend(service_type_codes)
    if vehicle_type_codes:
        conditions.append(
            f"s.vehicle_type_code IN ({','.join(['%s'] * len(vehicle_type_codes))})"
        )
        params.extend(vehicle_type_codes)
    where_clause = " AND ".join(conditions)
    rows = fetch_all(
        f"""
        SELECT
            s.id AS service_id, s.service_code, s.service_name, s.service_type_code,
            s.area_id, s.vehicle_type_code, s.passenger_capacity, c.available_inventory
        FROM transfer_services s
        JOIN transfer_capacity_calendar c ON c.transfer_service_id = s.id
        WHERE {where_clause}
        ORDER BY s.vehicle_type_code ASC, service_id ASC
        LIMIT %s OFFSET %s
        """,
        tuple(params + [limit, offset]),
    )
    total = count_total(
        f"""
        SELECT COUNT(*) AS total
        FROM transfer_services s
        JOIN transfer_capacity_calendar c ON c.transfer_service_id = s.id
        WHERE {where_clause}
        """,
        tuple(params),
    )
    return {
        "list": [
            {
                "serviceId": row["service_id"],
                "serviceCode": row["service_code"],
                "serviceName": row["service_name"],
                "serviceTypeCode": row["service_type_code"],
                "areaId": row["area_id"],
                "vehicleTypeCode": row["vehicle_type_code"],
                "passengerCapacity": row["passenger_capacity"],
                "availableInventory": int(row["available_inventory"]),
            }
            for row in rows
        ],
        "pageNo": page_no,
        "pageSize": page_size,
        "total": total,
    }


@router.get("/transfers/{serviceId}", summary="查询接送服务详情")
def get_transfer_detail(
    service_id: Annotated[
        int,
        Path(alias="serviceId", description="接送服务 ID，对应 transfer_services.id。"),
    ],
):
    row = fetch_one(
        """
        SELECT id AS service_id, service_code, service_name, service_type_code,
               area_id, vehicle_type_code, passenger_capacity
        FROM transfer_services
        WHERE id = %s AND status_code = 'active'
        """,
        (service_id,),
    )
    if row is None:
        raise not_found("接送服务不存在")
    return {
        "serviceId": row["service_id"],
        "serviceCode": row["service_code"],
        "serviceName": row["service_name"],
        "serviceTypeCode": row["service_type_code"],
        "areaId": row["area_id"],
        "vehicleTypeCode": row["vehicle_type_code"],
        "passengerCapacity": row["passenger_capacity"],
    }


@router.get("/transfers/{serviceId}/pricing", summary="查询接送服务价格")
def get_transfer_pricing(
    service_id: Annotated[
        int,
        Path(alias="serviceId", description="接送服务 ID，对应 transfer_services.id。"),
    ],
    pickup_area_id: Annotated[
        int,
        Query(
            alias="pickupAreaId",
            description="上车地区 ID，对应 transfer_service_area_rules.pickup_area_id。",
        ),
    ],
    dropoff_area_id: Annotated[
        int,
        Query(
            alias="dropoffAreaId",
            description="下车地区 ID，对应 transfer_service_area_rules.dropoff_area_id。",
        ),
    ],
    business_date: Annotated[
        str,
        Query(
            alias="businessDate",
            description="服务日期，格式 YYYY-MM-DD，用于查询当天运力和价格。",
        ),
    ],
):
    row = fetch_one(
        """
        SELECT
            s.id AS service_id,
            s.vehicle_type_code,
            s.passenger_capacity,
            r.pickup_area_id,
            r.dropoff_area_id,
            r.price_amount AS sale_price_amount,
            c.available_inventory,
            r.rule_payload,
            r.status_code
        FROM transfer_services s
        JOIN transfer_service_area_rules r
          ON r.transfer_service_id = s.id
        JOIN transfer_capacity_calendar c
          ON c.transfer_service_id = s.id
        WHERE s.id = %s
          AND s.status_code = 'active'
          AND r.pickup_area_id = %s
          AND r.dropoff_area_id = %s
          AND r.status_code = 'active'
          AND c.business_date = %s
          AND c.status_code = 'active'
        """,
        (service_id, pickup_area_id, dropoff_area_id, business_date),
    )
    if row is None:
        raise not_found("接送服务价格或库存不存在")
    return {
        "serviceId": row["service_id"],
        "pickupAreaId": row["pickup_area_id"],
        "dropoffAreaId": row["dropoff_area_id"],
        "businessDate": business_date,
        "vehicleTypeCode": row["vehicle_type_code"],
        "passengerCapacity": row["passenger_capacity"],
        "salePriceAmount": float(row["sale_price_amount"]),
        "currencyCode": "CNY",
        "availableInventory": int(row["available_inventory"]),
        "rulePayload": _loads(row["rule_payload"], []),
        "statusCode": row["status_code"],
    }
