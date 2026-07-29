from __future__ import annotations


def test_get_me(client, samples, user_headers):
    user = samples.user_with_student
    response = client.get("/api/v1/me", headers=user_headers(user["user_id"]))
    assert response.status_code == 200
    assert response.json()["data"]["userId"] == user["user_id"]


def test_get_me_requires_user_header(client):
    response = client.get("/api/v1/me")
    assert response.status_code == 401
    assert response.json()["code"] == "MISSING_USER_ID"


def test_get_student_profile(client, samples, user_headers):
    user = samples.user_with_student
    response = client.get(
        "/api/v1/me/student-profile",
        headers=user_headers(user["user_id"]),
    )
    assert response.status_code == 200
    assert response.json()["data"]["studentId"] == user["student_id"]


def test_get_learning_summary(client, samples, user_headers):
    user = samples.user_with_student
    response = client.get(
        "/api/v1/me/learning-summary",
        headers=user_headers(user["user_id"]),
    )
    assert response.status_code == 200
    assert "recentLearningRecords" in response.json()["data"]


def test_get_series_list(client):
    response = client.get("/api/v1/series", params={"pageNo": 1, "pageSize": 5})
    assert response.status_code == 200
    assert response.json()["data"]["total"] > 0


def test_get_series_list_with_keyword(client, samples, user_headers):
    series = samples.on_sale_series
    user = samples.user_with_student
    response = client.get(
        "/api/v1/series",
        params={"keyword": str(series["series_name"])[:6], "pageNo": 1, "pageSize": 5},
        headers=user_headers(user["user_id"]),
    )
    assert response.status_code == 200
    assert isinstance(response.json()["data"]["list"], list)


def test_get_series_detail(client, samples):
    row = samples.on_sale_series_with_cohort
    response = client.get(f"/api/v1/series/{row['series_id']}")
    assert response.status_code == 200
    assert response.json()["data"]["seriesId"] == row["series_id"]


def test_get_series_detail_with_user_links(client, samples, user_headers, db):
    rel = samples.active_rel
    row = db["fetch_one"](
        "SELECT series_id FROM series_cohort WHERE id = %s",
        (rel["cohort_id"],),
    )
    assert row is not None
    response = client.get(
        f"/api/v1/series/{row['series_id']}",
        headers=user_headers(rel["user_id"]),
    )
    assert response.status_code == 200
    assert response.json()["data"]["myEnrollments"][0]["orderId"]


def test_get_series_cohorts(client, samples):
    row = samples.on_sale_series_with_cohort
    response = client.get(f"/api/v1/series/{row['series_id']}/cohorts")
    assert response.status_code == 200
    assert isinstance(response.json()["data"], list)


def test_get_cohort_detail(client, samples):
    row = samples.on_sale_series_with_cohort
    response = client.get(f"/api/v1/cohorts/{row['cohort_id']}")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["cohortId"] == row["cohort_id"]
    assert data["seriesId"] == row["series_id"]


def test_get_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "ok"
