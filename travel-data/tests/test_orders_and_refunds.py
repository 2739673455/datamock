from __future__ import annotations

from app.config import DEMO_PAYMENT_SIGNATURE


def create_scenic_order(client, auth_headers, scenic_context):
    response = client.post(
        "/api/v1/orders",
        headers=auth_headers,
        json={
            "orderTypeCode": "scenic_ticket",
            "sourceChannelCode": "app",
            "currencyCode": "CNY",
            "items": [
                {
                    "productTypeCode": "scenic_ticket",
                    "productId": scenic_context["ticketTypeId"],
                    "productName": "测试景点票",
                    "quantity": 1,
                    "travelTime": scenic_context["travelTime"],
                    "travelerIds": [],
                }
            ],
            "userCouponIds": [],
            "usePoints": False,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def create_pending_payment(client, auth_headers, order_id):
    response = client.post(
        f"/api/v1/orders/{order_id}/payments",
        headers=auth_headers,
        json={"paymentMethodCode": "alipay", "clientType": "app"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def mark_payment_success(client, payment_payload):
    response = client.post(
        "/api/v1/payments/callback",
        headers={"X-Demo-Payment-Signature": DEMO_PAYMENT_SIGNATURE},
        json={
            "paymentNo": payment_payload["paymentNo"],
            "orderId": payment_payload["orderId"],
            "paymentMethodCode": payment_payload["paymentMethodCode"],
            "amount": payment_payload["amount"],
            "statusCode": "success",
            "paidAt": "2025-01-08 10:00:00",
            "channelTradeNo": "MOCK_CHANNEL_0001",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_create_list_and_detail_order(client, auth_headers, scenic_context):
    created = create_scenic_order(client, auth_headers, scenic_context)

    assert created["orderTypeCode"] == "scenic_ticket"
    assert created["statusCode"] == "pending_payment"

    list_response = client.get(
        "/api/v1/orders",
        headers=auth_headers,
        params={"pageNo": 1, "pageSize": 10},
    )
    assert list_response.status_code == 200
    listed = list_response.json()
    assert "total" in listed
    assert any(item["orderId"] == created["orderId"] for item in listed["list"])

    detail_response = client.get(
        f"/api/v1/orders/{created['orderId']}",
        headers=auth_headers,
    )
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["orderId"] == created["orderId"]
    assert len(detail["items"]) == 1


def test_cancel_order(client, auth_headers, scenic_context):
    created = create_scenic_order(client, auth_headers, scenic_context)

    response = client.post(
        f"/api/v1/orders/{created['orderId']}/cancel",
        headers=auth_headers,
        json={"cancelReason": "测试取消"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["orderId"] == created["orderId"]
    assert data["statusCode"] == "cancelled"


def test_create_get_and_close_payment(client, auth_headers, scenic_context):
    created = create_scenic_order(client, auth_headers, scenic_context)
    payment = create_pending_payment(client, auth_headers, created["orderId"])

    assert payment["orderId"] == created["orderId"]
    assert payment["statusCode"] == "pending"

    get_response = client.get(
        f"/api/v1/payments/{payment['paymentId']}",
        headers=auth_headers,
    )
    assert get_response.status_code == 200
    assert get_response.json()["paymentId"] == payment["paymentId"]

    close_response = client.post(
        f"/api/v1/payments/{payment['paymentId']}/close",
        headers=auth_headers,
        json={"closeReason": "测试关闭"},
    )
    assert close_response.status_code == 200
    assert close_response.json()["statusCode"] == "closed"


def test_pay_order_compat_path(client, auth_headers, scenic_context):
    created = create_scenic_order(client, auth_headers, scenic_context)

    response = client.post(
        f"/api/v1/orders/{created['orderId']}/pay",
        headers=auth_headers,
        json={"paymentMethodCode": "wechat", "clientType": "miniapp"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["orderId"] == created["orderId"]
    assert data["statusCode"] == "pending"
    assert data["paymentMethodCode"] == "wechat"


def test_payment_callback_and_list_order_payments(client, auth_headers, scenic_context):
    created = create_scenic_order(client, auth_headers, scenic_context)
    payment = create_pending_payment(client, auth_headers, created["orderId"])

    callback = mark_payment_success(client, payment)

    assert callback["paymentId"] == payment["paymentId"]
    assert callback["paymentStatusCode"] == "success"
    assert callback["orderStatusCode"] in {"paid", "in_progress", "finished"}

    list_response = client.get(
        f"/api/v1/orders/{created['orderId']}/payments",
        headers=auth_headers,
    )
    assert list_response.status_code == 200
    payments = list_response.json()["list"]
    assert any(item["paymentId"] == payment["paymentId"] for item in payments)


def test_payment_callback_requires_signature(client, auth_headers, scenic_context):
    created = create_scenic_order(client, auth_headers, scenic_context)
    payment = create_pending_payment(client, auth_headers, created["orderId"])

    response = client.post(
        "/api/v1/payments/callback",
        headers={"X-Demo-Payment-Signature": "wrong-signature"},
        json={
            "paymentNo": payment["paymentNo"],
            "orderId": payment["orderId"],
            "paymentMethodCode": payment["paymentMethodCode"],
            "amount": payment["amount"],
            "statusCode": "success",
            "paidAt": "2025-01-08 10:00:00",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "支付回调签名不合法"


def test_create_list_and_detail_refund_request(client, auth_headers, scenic_context):
    created = create_scenic_order(client, auth_headers, scenic_context)
    payment = create_pending_payment(client, auth_headers, created["orderId"])
    mark_payment_success(client, payment)

    order_detail = client.get(
        f"/api/v1/orders/{created['orderId']}",
        headers=auth_headers,
    ).json()
    order_item_id = order_detail["items"][0]["orderItemId"]
    requested_amount = order_detail["items"][0]["saleAmount"]

    create_response = client.post(
        f"/api/v1/orders/{created['orderId']}/items/{order_item_id}/refund-requests",
        headers=auth_headers,
        json={"requestedAmount": requested_amount, "reason": "测试退款"},
    )

    assert create_response.status_code == 200
    refund = create_response.json()
    assert refund["orderId"] == created["orderId"]
    assert refund["orderItemId"] == order_item_id
    assert refund["statusCode"] == "pending"

    list_response = client.get(
        "/api/v1/refund-requests",
        headers=auth_headers,
        params={"pageNo": 1, "pageSize": 10},
    )
    assert list_response.status_code == 200
    listed = list_response.json()
    assert any(
        item["refundRequestId"] == refund["refundRequestId"] for item in listed["list"]
    )

    detail_response = client.get(
        f"/api/v1/refund-requests/{refund['refundRequestId']}",
        headers=auth_headers,
    )
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["refundRequestId"] == refund["refundRequestId"]

    refund_records_response = client.get(
        f"/api/v1/orders/{created['orderId']}/refund-records",
        headers=auth_headers,
    )
    assert refund_records_response.status_code == 200
    assert "list" in refund_records_response.json()
