from httpx import AsyncClient

from app.core.middleware import REQUEST_ID_HEADER


async def test_generates_request_id_when_absent(client: AsyncClient) -> None:
    response = await client.get("/health/live")
    request_id = response.headers[REQUEST_ID_HEADER]
    assert len(request_id) >= 8


async def test_honours_a_well_formed_inbound_request_id(client: AsyncClient) -> None:
    response = await client.get("/health/live", headers={REQUEST_ID_HEADER: "caller-supplied-123"})
    assert response.headers[REQUEST_ID_HEADER] == "caller-supplied-123"


async def test_replaces_a_malformed_inbound_request_id(client: AsyncClient) -> None:
    malicious = "short\r\nX-Injected: true"
    response = await client.get("/health/live", headers={REQUEST_ID_HEADER: malicious})
    returned = response.headers[REQUEST_ID_HEADER]
    assert returned != malicious
    assert "\r" not in returned
    assert "X-Injected" not in response.headers


async def test_two_requests_get_different_ids(client: AsyncClient) -> None:
    first = await client.get("/health/live")
    second = await client.get("/health/live")
    assert first.headers[REQUEST_ID_HEADER] != second.headers[REQUEST_ID_HEADER]


async def test_error_response_carries_the_same_request_id(client: AsyncClient) -> None:
    response = await client.get("/does-not-exist", headers={REQUEST_ID_HEADER: "fixed-id-00001"})
    assert response.headers[REQUEST_ID_HEADER] == "fixed-id-00001"
    assert response.json()["error"]["request_id"] == "fixed-id-00001"
