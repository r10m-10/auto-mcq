import tempfile
import uuid
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.credits import router as credits_router
from app.routers.device import router as device_router
from routers.admin import router as admin_router
from routers.config import router as config_router
from routers.device_delete import router as delete_router
from routers.offerwall import router as offerwall_router

TEST_TOKEN = "test-admin-token-0123456789abcdef"


def _build_app():
    app = FastAPI()
    app.include_router(device_router)
    app.include_router(credits_router)
    app.include_router(offerwall_router)
    app.include_router(delete_router)
    app.include_router(config_router)
    app.include_router(admin_router)
    return app


def _fresh_db(monkeypatch):
    """Point the app at a fresh, empty SQLite DB for this test.

    The conftest session-level temp DB is shared across all tests, which
    would leak aggregate counts between cases. Give each test its own file.
    """
    tmp = Path(tempfile.mkdtemp(prefix="automcq_admin_test_"))
    import app.db as db_module

    monkeypatch.setattr(db_module, "DB_PATH", str(tmp / "app.db"))
    db_module.init_db()


@pytest.fixture()
def client(monkeypatch):
    _fresh_db(monkeypatch)
    monkeypatch.setenv("ADMIN_TOKEN", TEST_TOKEN)
    with TestClient(_build_app()) as c:
        yield c


@pytest.fixture()
def hidden_client(monkeypatch):
    _fresh_db(monkeypatch)
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    with TestClient(_build_app()) as c:
        yield c


def _auth(token=TEST_TOKEN):
    return {"X-Admin-Token": token}


def _device_id() -> str:
    return str(uuid.uuid4())


def _linked_device(client) -> str:
    device_id = _device_id()
    assert client.post("/link-device", json={"device_id": device_id}).status_code == 200
    return device_id


def _with_credits(client, device_id: str) -> None:
    r = client.post("/offerwall/sandbox-claim", json={"device_id": device_id})
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# Auth: fail closed
# ---------------------------------------------------------------------------


def test_admin_hidden_when_token_unset(hidden_client):
    assert hidden_client.get("/admin").status_code == 404
    assert hidden_client.get("/admin/api/stats").status_code == 404
    assert hidden_client.get("/admin/api/devices").status_code == 404
    assert hidden_client.get("/admin/api/config").status_code == 404


def test_admin_api_requires_token(client):
    assert client.get("/admin/api/stats").status_code == 401
    assert client.get("/admin/api/devices").status_code == 401
    assert client.get("/admin/api/config").status_code == 401


def test_admin_api_rejects_wrong_token(client):
    bad = {"X-Admin-Token": "wrong-token"}
    assert client.get("/admin/api/stats", headers=bad).status_code == 401
    assert client.get("/admin/api/stats", headers={"X-Admin-Token": ""}).status_code == 401


def test_admin_page_served_with_token(client):
    r = client.get("/admin")
    assert r.status_code == 200
    assert "AUTOMCQ" in r.text


# ---------------------------------------------------------------------------
# Public config endpoint
# ---------------------------------------------------------------------------


def test_public_config_shape(client):
    r = client.get("/config")
    assert r.status_code == 200
    body = r.json()
    assert body == {
        "sponsor_overlay_enabled": True,
        "sponsor_card_enabled": True,
        "offerwall_enabled": True,
        "ad_name": "VEDPREP CRASH COURSE",
        "ad_sub": "JEE & NEET 2027 mock tests with instant solutions.",
        "ad_url": "https://automcq.reyaanshsharma.com",
    }


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


def test_stats_empty(client):
    body = client.get("/admin/api/stats", headers=_auth()).json()
    assert body["total_devices"] == 0
    assert body["total_balance"] == 0
    assert body["claim_count"] == 0
    assert body["active_devices_today"] == 0


def test_stats_reflect_activity(client):
    device_id = _linked_device(client)
    _with_credits(client, device_id)

    body = client.get("/admin/api/stats", headers=_auth()).json()
    assert body["total_devices"] == 1
    assert body["total_credits_issued"] == 3
    assert body["total_balance"] == 3
    assert body["claim_count"] == 1
    assert body["active_devices_today"] == 1


# ---------------------------------------------------------------------------
# Devices
# ---------------------------------------------------------------------------


def test_devices_list(client):
    d1 = _linked_device(client)
    d2 = _linked_device(client)
    _with_credits(client, d1)

    rows = client.get("/admin/api/devices", headers=_auth()).json()
    assert len(rows) == 2
    by_id = {r["device_id"]: r for r in rows}
    assert by_id[d1]["credits_balance"] == 3
    assert by_id[d2]["credits_balance"] == 0
    assert by_id[d1]["last_activity"] is not None


def test_device_detail_ledger(client):
    device_id = _linked_device(client)
    _with_credits(client, device_id)

    body = client.get(f"/admin/api/devices/{device_id}", headers=_auth()).json()
    assert body["credits_balance"] == 3
    assert len(body["ledger"]) == 1
    assert body["ledger"][0]["delta"] == 3
    assert body["ledger"][0]["source"] == "sandbox_offerwall"


def test_device_detail_not_found(client):
    assert client.get(f"/admin/api/devices/{_device_id()}", headers=_auth()).status_code == 404


def test_device_detail_invalid_uuid(client):
    assert client.get("/admin/api/devices/not-a-uuid", headers=_auth()).status_code == 400


# ---------------------------------------------------------------------------
# Delete (reuses device_delete logic)
# ---------------------------------------------------------------------------


def test_admin_delete_reuses_delete_logic(client):
    device_id = _linked_device(client)
    _with_credits(client, device_id)

    r = client.delete(f"/admin/api/devices/{device_id}", headers=_auth())
    assert r.status_code == 200
    assert r.json()["deleted"] is True
    assert r.json()["credits_removed"] == 3

    assert client.get("/balance", params={"device_id": device_id}).status_code == 404


def test_admin_delete_unknown_device(client):
    r = client.delete(f"/admin/api/devices/{_device_id()}", headers=_auth())
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Credit adjust
# ---------------------------------------------------------------------------


def test_adjust_grants_positive(client):
    device_id = _linked_device(client)
    r = client.post(
        f"/admin/api/devices/{device_id}/credits",
        json={"delta": 50},
        headers=_auth(),
    )
    assert r.status_code == 200
    assert r.json()["credits_balance"] == 50

    detail = client.get(f"/admin/api/devices/{device_id}", headers=_auth()).json()
    assert detail["ledger"][0]["delta"] == 50
    assert detail["ledger"][0]["source"] == "admin_adjust"


def test_adjust_deducts_positive_balance(client):
    device_id = _linked_device(client)
    _with_credits(client, device_id)

    r = client.post(
        f"/admin/api/devices/{device_id}/credits",
        json={"delta": -1},
        headers=_auth(),
    )
    assert r.status_code == 200
    assert r.json()["credits_balance"] == 2


def test_adjust_cannot_go_negative(client):
    device_id = _linked_device(client)
    r = client.post(
        f"/admin/api/devices/{device_id}/credits",
        json={"delta": -5},
        headers=_auth(),
    )
    assert r.status_code == 400


def test_adjust_zero_rejected(client):
    device_id = _linked_device(client)
    r = client.post(
        f"/admin/api/devices/{device_id}/credits",
        json={"delta": 0},
        headers=_auth(),
    )
    assert r.status_code == 422


def test_adjust_over_cap_rejected(client):
    device_id = _linked_device(client)
    r = client.post(
        f"/admin/api/devices/{device_id}/credits",
        json={"delta": 1001},
        headers=_auth(),
    )
    assert r.status_code == 422


def test_adjust_unknown_device(client):
    r = client.post(
        f"/admin/api/devices/{_device_id()}/credits",
        json={"delta": 5},
        headers=_auth(),
    )
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Activity series
# ---------------------------------------------------------------------------


def test_activity_series_is_thirty_days(client):
    device_id = _linked_device(client)
    _with_credits(client, device_id)

    rows = client.get("/admin/api/activity", headers=_auth()).json()
    assert len(rows) == 30
    assert rows[-1]["claims"] == 1
    assert rows[-1]["active_devices"] == 1
    assert sum(r["claims"] for r in rows) == 1


# ---------------------------------------------------------------------------
# Config read/write (admin)
# ---------------------------------------------------------------------------


def test_admin_config_get(client):
    r = client.get("/admin/api/config", headers=_auth())
    assert r.status_code == 200
    assert r.json()["sponsor_overlay_enabled"] is True


def test_admin_config_update_persists(client):
    r = client.put(
        "/admin/api/config",
        json={"sponsor_overlay_enabled": False, "ad_name": "NEW CAMPAIGN"},
        headers=_auth(),
    )
    assert r.status_code == 200
    assert r.json()["sponsor_overlay_enabled"] is False
    assert r.json()["ad_name"] == "NEW CAMPAIGN"

    got = client.get("/admin/api/config", headers=_auth()).json()
    assert got["sponsor_overlay_enabled"] is False
    assert got["ad_name"] == "NEW CAMPAIGN"

    pub = client.get("/config").json()
    assert pub["sponsor_overlay_enabled"] is False


def test_admin_config_update_empty_body(client):
    r = client.put("/admin/api/config", json={}, headers=_auth())
    assert r.status_code == 400
