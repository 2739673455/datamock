from __future__ import annotations

from app.main import app

EXPECTED_ROUTES = {
    ("DELETE", "/api/v1/me/travelers/{travelerId}"),
    ("GET", "/api/v1/buses/search"),
    ("GET", "/api/v1/buses/{departureId}"),
    ("GET", "/api/v1/coupon-templates/available"),
    ("GET", "/api/v1/coupons"),
    ("GET", "/api/v1/flights/search"),
    ("GET", "/api/v1/flights/{departureId}"),
    ("GET", "/api/v1/hotels"),
    ("GET", "/api/v1/hotels/{hotelId}"),
    ("GET", "/api/v1/hotels/{hotelId}/room-types"),
    ("GET", "/api/v1/me"),
    ("GET", "/api/v1/me/member-account"),
    ("GET", "/api/v1/me/point-ledger"),
    ("GET", "/api/v1/me/travelers"),
    ("GET", "/api/v1/orders"),
    ("GET", "/api/v1/orders/{orderId}"),
    ("GET", "/api/v1/orders/{orderId}/payments"),
    ("GET", "/api/v1/orders/{orderId}/refund-records"),
    ("GET", "/api/v1/payments/{paymentId}"),
    ("GET", "/api/v1/refund-requests"),
    ("GET", "/api/v1/refund-requests/{refundRequestId}"),
    ("GET", "/api/v1/scenic-spots"),
    ("GET", "/api/v1/scenic-spots/{scenicSpotId}"),
    ("GET", "/api/v1/scenic-spots/{scenicSpotId}/ticket-types"),
    ("GET", "/api/v1/trains/search"),
    ("GET", "/api/v1/trains/{departureId}"),
    ("GET", "/api/v1/transfers"),
    ("GET", "/api/v1/transfers/{serviceId}"),
    ("GET", "/api/v1/transfers/{serviceId}/pricing"),
    ("GET", "/health"),
    ("POST", "/api/v1/coupons/receive"),
    ("POST", "/api/v1/me/travelers"),
    ("POST", "/api/v1/orders"),
    ("POST", "/api/v1/orders/{orderId}/cancel"),
    ("POST", "/api/v1/orders/{orderId}/items/{itemId}/refund-requests"),
    ("POST", "/api/v1/orders/{orderId}/pay"),
    ("POST", "/api/v1/orders/{orderId}/payments"),
    ("POST", "/api/v1/payments/callback"),
    ("POST", "/api/v1/payments/{paymentId}/close"),
    ("PUT", "/api/v1/me/travelers/{travelerId}"),
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
