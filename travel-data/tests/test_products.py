from __future__ import annotations


def test_list_hotels(client, hotel_context):
    response = client.get(
        "/api/v1/hotels",
        params={
            "areaId": hotel_context["areaId"],
            "checkInDate": hotel_context["checkInDate"],
            "checkOutDate": hotel_context["checkOutDate"],
            "pageNo": 1,
            "pageSize": 5,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert "list" in data
    assert "total" in data
    assert any(item["hotelId"] == hotel_context["hotelId"] for item in data["list"])


def test_get_hotel_detail(client, hotel_context):
    response = client.get(f"/api/v1/hotels/{hotel_context['hotelId']}")

    assert response.status_code == 200
    data = response.json()
    assert data["hotelId"] == hotel_context["hotelId"]
    assert "bookingRule" in data


def test_list_hotel_room_types(client, hotel_context):
    response = client.get(
        f"/api/v1/hotels/{hotel_context['hotelId']}/room-types",
        params={
            "checkInDate": hotel_context["checkInDate"],
            "checkOutDate": hotel_context["checkOutDate"],
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert "list" in data
    assert any(
        item["roomTypeId"] == hotel_context["roomTypeId"] for item in data["list"]
    )


def test_list_scenic_spots(client, scenic_context):
    response = client.get(
        "/api/v1/scenic-spots",
        params={
            "areaId": scenic_context["areaId"],
            "travelDate": scenic_context["travelDate"],
            "pageNo": 1,
            "pageSize": 5,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert "list" in data
    assert "total" in data
    assert any(
        item["scenicSpotId"] == scenic_context["scenicSpotId"] for item in data["list"]
    )


def test_get_scenic_detail(client, scenic_context):
    response = client.get(f"/api/v1/scenic-spots/{scenic_context['scenicSpotId']}")

    assert response.status_code == 200
    assert response.json()["scenicSpotId"] == scenic_context["scenicSpotId"]


def test_list_ticket_types(client, scenic_context):
    response = client.get(
        f"/api/v1/scenic-spots/{scenic_context['scenicSpotId']}/ticket-types",
        params={"travelDate": scenic_context["travelDate"]},
    )

    assert response.status_code == 200
    data = response.json()
    assert "list" in data
    assert any(
        item["ticketTypeId"] == scenic_context["ticketTypeId"] for item in data["list"]
    )


def test_search_flights(client, flight_context):
    response = client.get(
        "/api/v1/flights/search",
        params={
            "departureAreaId": flight_context["departureAreaId"],
            "arrivalAreaId": flight_context["arrivalAreaId"],
            "departureDate": flight_context["departureDate"],
            "pageNo": 1,
            "pageSize": 5,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] > 0
    assert any(
        item["departureId"] == flight_context["departureId"] for item in data["list"]
    )


def test_get_flight_detail(client, flight_context):
    response = client.get(f"/api/v1/flights/{flight_context['departureId']}")

    assert response.status_code == 200
    data = response.json()
    assert data["departureId"] == flight_context["departureId"]
    assert len(data["cabins"]) > 0


def test_search_trains(client, train_context):
    response = client.get(
        "/api/v1/trains/search",
        params={
            "departureAreaId": train_context["departureAreaId"],
            "arrivalAreaId": train_context["arrivalAreaId"],
            "departureDate": train_context["departureDate"],
            "pageNo": 1,
            "pageSize": 5,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] > 0
    assert any(
        item["departureId"] == train_context["departureId"] for item in data["list"]
    )


def test_get_train_detail(client, train_context):
    response = client.get(f"/api/v1/trains/{train_context['departureId']}")

    assert response.status_code == 200
    data = response.json()
    assert data["departureId"] == train_context["departureId"]
    assert len(data["seats"]) > 0


def test_search_buses(client, bus_context):
    response = client.get(
        "/api/v1/buses/search",
        params={
            "departureAreaId": bus_context["departureAreaId"],
            "arrivalAreaId": bus_context["arrivalAreaId"],
            "departureDate": bus_context["departureDate"],
            "pageNo": 1,
            "pageSize": 5,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] > 0
    assert any(
        item["departureId"] == bus_context["departureId"] for item in data["list"]
    )


def test_get_bus_detail(client, bus_context):
    response = client.get(f"/api/v1/buses/{bus_context['departureId']}")

    assert response.status_code == 200
    data = response.json()
    assert data["departureId"] == bus_context["departureId"]
    assert len(data["seats"]) > 0


def test_list_transfers(client, transfer_context):
    response = client.get(
        "/api/v1/transfers",
        params={
            "areaId": transfer_context["areaId"],
            "businessDate": transfer_context["businessDate"],
            "pageNo": 1,
            "pageSize": 5,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] > 0
    assert any(
        item["serviceId"] == transfer_context["serviceId"] for item in data["list"]
    )


def test_get_transfer_detail(client, transfer_context):
    response = client.get(f"/api/v1/transfers/{transfer_context['serviceId']}")

    assert response.status_code == 200
    assert response.json()["serviceId"] == transfer_context["serviceId"]


def test_get_transfer_pricing(client, transfer_context):
    response = client.get(
        f"/api/v1/transfers/{transfer_context['serviceId']}/pricing",
        params={
            "pickupAreaId": transfer_context["pickupAreaId"],
            "dropoffAreaId": transfer_context["dropoffAreaId"],
            "businessDate": transfer_context["businessDate"],
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["serviceId"] == transfer_context["serviceId"]
    assert data["availableInventory"] >= 0
