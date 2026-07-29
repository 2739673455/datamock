from __future__ import annotations

from app.main import app

EXPECTED_ROUTES = {
    ("DELETE", "/api/v1/cart/items/{item_id}"),
    ("DELETE", "/api/v1/series/{series_id}/favorite"),
    ("GET", "/api/v1/cart/items"),
    ("GET", "/api/v1/cohorts/{cohort_id}"),
    ("GET", "/api/v1/cohorts/{cohort_id}/reviews"),
    ("GET", "/api/v1/coupons/available"),
    ("GET", "/api/v1/exams/{exam_id}"),
    ("GET", "/api/v1/homeworks/{homework_id}"),
    ("GET", "/api/v1/me"),
    ("GET", "/api/v1/me/cohorts"),
    ("GET", "/api/v1/me/cohorts/{cohort_id}"),
    ("GET", "/api/v1/me/cohorts/{cohort_id}/progress"),
    ("GET", "/api/v1/me/cohorts/{cohort_id}/sessions"),
    ("GET", "/api/v1/me/consultations"),
    ("GET", "/api/v1/me/coupons"),
    ("GET", "/api/v1/me/exam-submissions"),
    ("GET", "/api/v1/me/exams"),
    ("GET", "/api/v1/me/favorites"),
    ("GET", "/api/v1/me/homework-submissions"),
    ("GET", "/api/v1/me/homeworks"),
    ("GET", "/api/v1/me/learning-summary"),
    ("GET", "/api/v1/me/student-profile"),
    ("GET", "/api/v1/me/video-history"),
    ("GET", "/api/v1/orders"),
    ("GET", "/api/v1/orders/{order_id}"),
    ("GET", "/api/v1/orders/{order_id}/payments"),
    ("GET", "/api/v1/payments/{payment_id}"),
    ("GET", "/api/v1/refund-requests"),
    ("GET", "/api/v1/refund-requests/{refund_request_id}"),
    ("GET", "/api/v1/series"),
    ("GET", "/api/v1/series/{series_id}"),
    ("GET", "/api/v1/series/{series_id}/cohorts"),
    ("GET", "/api/v1/service-tickets"),
    ("GET", "/api/v1/service-tickets/{ticket_id}"),
    ("GET", "/api/v1/service-tickets/{ticket_id}/follow-records"),
    ("GET", "/api/v1/sessions/{session_id}"),
    ("GET", "/api/v1/videos/{video_id}"),
    ("GET", "/api/v1/videos/{video_id}/chapters"),
    ("GET", "/health"),
    ("POST", "/api/v1/cart/items"),
    ("POST", "/api/v1/cohorts/{cohort_id}/consultations"),
    ("POST", "/api/v1/cohorts/{cohort_id}/reviews"),
    ("POST", "/api/v1/coupons/{coupon_id}/receive"),
    ("POST", "/api/v1/order-items/{order_item_id}/refund-requests"),
    ("POST", "/api/v1/orders"),
    ("POST", "/api/v1/orders/quote"),
    ("POST", "/api/v1/orders/{order_id}/cancel"),
    ("POST", "/api/v1/orders/{order_id}/payments"),
    ("POST", "/api/v1/payment-notifications/mock"),
    ("POST", "/api/v1/payments/{payment_id}/close"),
    ("POST", "/api/v1/series/{series_id}/favorite"),
    ("POST", "/api/v1/service-tickets"),
    ("POST", "/api/v1/service-tickets/{ticket_id}/satisfaction-surveys"),
}


def public_routes() -> set[tuple[str, str]]:
    routes = set()
    for route in app.routes:
        methods = getattr(route, "methods", set())
        path = getattr(route, "path", "")
        if path.startswith(("/docs", "/redoc", "/openapi")):
            continue
        for method in methods:
            if method in {"GET", "POST", "PUT", "DELETE", "PATCH"}:
                routes.add((method, path))
    return routes


def test_registered_api_routes_match_expected_contract():
    assert public_routes() == EXPECTED_ROUTES
