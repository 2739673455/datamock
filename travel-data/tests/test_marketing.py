from __future__ import annotations


def test_list_available_coupon_templates(client, marketing_headers):
    response = client.get(
        "/api/v1/coupon-templates/available",
        headers=marketing_headers,
        params={"pageNo": 1, "pageSize": 5},
    )

    assert response.status_code == 200
    data = response.json()
    assert "list" in data
    assert "total" in data


def test_list_user_coupons(client, marketing_headers):
    response = client.get(
        "/api/v1/coupons",
        headers=marketing_headers,
        params={"pageNo": 1, "pageSize": 5},
    )

    assert response.status_code == 200
    data = response.json()
    assert "list" in data
    assert "total" in data


def test_receive_coupon(client, marketing_headers, marketing_user_context):
    response = client.post(
        "/api/v1/coupons/receive",
        headers=marketing_headers,
        json={"templateId": marketing_user_context["templateId"]},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["templateId"] == marketing_user_context["templateId"]
    assert data["statusCode"] == "available"


def test_receive_coupon_template_not_found(client, marketing_headers):
    response = client.post(
        "/api/v1/coupons/receive",
        headers=marketing_headers,
        json={"templateId": 999999999},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "优惠券模板不存在"
