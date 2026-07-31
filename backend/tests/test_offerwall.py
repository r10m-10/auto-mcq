import uuid

import pytest
from fastapi.testclient import TestClient

from main import app


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def _device_id() -> str:
    return str(uuid.uuid4())


def test_link_then_claim_grants_three_credits(client):
    device_id = _device_id()
    assert client.post("/link-device", json={"device_id": device_id}).status_code == 200

    r = client.post("/offerwall/sandbox-claim", json={"device_id": device_id})
    assert r.status_code == 200
    body = r.json()
    assert body["delta"] == 3
    assert body["credits_balance"] == 3


def test_claim_records_source_in_ledger(client):
    device_id = _device_id()
    client.post("/link-device", json={"device_id": device_id})
    client.post("/offerwall/sandbox-claim", json={"device_id": device_id})

    r = client.get("/history", params={"device_id": device_id})
    assert r.status_code == 200
    rows = r.json()
    assert rows[0]["delta"] == 3
    assert rows[0]["reason"] == "ad_reward"
    assert rows[0]["source"] == "sandbox_offerwall"


def test_claim_is_rate_limited_per_device(client):
    device_id = _device_id()
    client.post("/link-device", json={"device_id": device_id})

    first = client.post("/offerwall/sandbox-claim", json={"device_id": device_id})
    assert first.status_code == 200

    second = client.post("/offerwall/sandbox-claim", json={"device_id": device_id})
    assert second.status_code == 429


def test_claim_unknown_device_returns_404(client):
    r = client.post("/offerwall/sandbox-claim", json={"device_id": _device_id()})
    assert r.status_code == 404


def test_claim_invalid_uuid_returns_422(client):
    r = client.post("/offerwall/sandbox-claim", json={"device_id": "not-a-uuid"})
    assert r.status_code == 422
