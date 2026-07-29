from __future__ import annotations


def test_get_me(client, auth_headers):
    response = client.get("/api/v1/me", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["userId"] > 0
    assert "statusCode" in data


def test_get_me_requires_user_header(client):
    response = client.get("/api/v1/me")

    assert response.status_code == 401
    assert response.json()["detail"] == "缺少请求头 X-User-Id"


def test_get_travelers(client, auth_headers):
    response = client.get(
        "/api/v1/me/travelers",
        headers=auth_headers,
        params={"pageNo": 1, "pageSize": 5},
    )

    assert response.status_code == 200
    data = response.json()
    assert "list" in data
    assert "total" in data
    assert data["pageNo"] == 1


def test_create_update_delete_traveler(client, auth_headers, now_stamp):
    create_payload = {
        "travelerName": f"测试出行人{now_stamp[-6:]}",
        "identityTypeCode": "passport",
        "identityNo": f"P{now_stamp}XYZ",
        "genderCode": "male",
        "birthDate": "1995-01-02",
        "phone": "13800001111",
    }
    create_response = client.post(
        "/api/v1/me/travelers", headers=auth_headers, json=create_payload
    )

    assert create_response.status_code == 200
    created = create_response.json()
    traveler_id = created["travelerId"]
    assert created["statusCode"] == "active"
    assert created["identityNoMasked"] is not None

    update_payload = {
        **create_payload,
        "travelerName": f"已更新{now_stamp[-4:]}",
        "phone": "13900002222",
        "statusCode": "active",
    }
    update_response = client.put(
        f"/api/v1/me/travelers/{traveler_id}",
        headers=auth_headers,
        json=update_payload,
    )

    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["travelerId"] == traveler_id
    assert updated["travelerName"] == update_payload["travelerName"]
    assert updated["phone"] == update_payload["phone"]

    delete_response = client.delete(
        f"/api/v1/me/travelers/{traveler_id}",
        headers=auth_headers,
    )

    assert delete_response.status_code == 200
    deleted = delete_response.json()
    assert deleted["travelerId"] == traveler_id
    assert deleted["statusCode"] == "inactive"


def test_get_member_account(client, auth_headers):
    response = client.get("/api/v1/me/member-account", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["userId"] > 0
    assert "pointsBalance" in data


def test_get_point_ledger(client, auth_headers):
    response = client.get(
        "/api/v1/me/point-ledger",
        headers=auth_headers,
        params={"pageNo": 1, "pageSize": 5},
    )

    assert response.status_code == 200
    data = response.json()
    assert "list" in data
    assert "total" in data
