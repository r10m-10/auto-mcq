import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.credits import router as credits_router
from app.routers.device import router as device_router
from routers.device_delete import router as delete_router
from routers.offerwall import router as offerwall_router


@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(device_router)
    app.include_router(credits_router)
    app.include_router(offerwall_router)
    app.include_router(delete_router)
    with TestClient(app) as c:
        yield c


def _device_id() -> str:
    return str(uuid.uuid4())


def _linked_device(client) -> str:
    device_id = _device_id()
    assert client.post("/link-device", json={"device_id": device_id}).status_code == 200
    return device_id


def test_delete_removes_device_and_ledger(client):
    device_id = _linked_device(client)
    client.post("/offerwall/sandbox-claim", json={"device_id": device_id})

    r = client.delete("/device", params={"device_id": device_id})
    assert r.status_code == 200
    body = r.json()
    assert body["deleted"] is True
    assert body["credits_removed"] == 3

    assert client.get("/balance", params={"device_id": device_id}).status_code == 404
    assert client.get("/history", params={"device_id": device_id}).status_code == 404


def test_delete_unknown_device_returns_404(client):
    r = client.delete("/device", params={"device_id": _device_id()})
    assert r.status_code == 404


def test_delete_invalid_uuid_returns_400(client):
    r = client.delete("/device", params={"device_id": "not-a-uuid"})
    assert r.status_code == 400


def test_delete_removes_balance_from_link_check(client):
    device_id = _linked_device(client)
    client.post("/offerwall/sandbox-claim", json={"device_id": device_id})
    assert client.delete("/device", params={"device_id": device_id}).status_code == 200

    r = client.post("/link-device", json={"device_id": device_id})
    assert r.status_code == 200
    assert r.json()["credits_balance"] == 0
    assert r.json()["linked"] is True
