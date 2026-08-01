import tempfile
import uuid
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.credits import router as credits_router
from app.routers.device import router as device_router
from routers.ads import router as ads_router
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
    app.include_router(ads_router)
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
    assert hidden_client.get("/admin/api/rewards").status_code == 404
    assert hidden_client.get("/admin/api/ads-metrics").status_code == 404


def test_admin_api_requires_token(client):
    assert client.get("/admin/api/stats").status_code == 401
    assert client.get("/admin/api/devices").status_code == 401
    assert client.get("/admin/api/config").status_code == 401
    assert client.get("/admin/api/rewards").status_code == 401
    assert client.get("/admin/api/ads-metrics").status_code == 401


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
        "normal_cost": 1,
        "fast_cost": 4,
        "ad_reward": 3,
        "ad_seconds": 25,
        "overlay_config": {
            "enabled": True,
            "source": "house",
            "ad_name": "VEDPREP CRASH COURSE",
            "ad_sub": "JEE & NEET 2027 mock tests with instant solutions.",
            "ad_url": "https://automcq.reyaanshsharma.com",
            "ad_cta": "LEARN MORE",
            "third_party_html": "",
            "frequency_every": 3,
            "min_view_seconds": 0,
            "auto_close_seconds": 0,
            "ad_type": "text",
            "video_url": "",
            "ad_seconds": 25,
        },
        "card_config": {
            "enabled": True,
            "source": "house",
            "ad_name": "VEDPREP CRASH COURSE",
            "ad_sub": "JEE & NEET 2027 mock tests with instant solutions.",
            "ad_url": "https://automcq.reyaanshsharma.com",
            "ad_cta": "LEARN MORE",
            "third_party_html": "",
            "frequency_every": 3,
            "min_view_seconds": 0,
            "auto_close_seconds": 0,
            "ad_type": "text",
            "video_url": "",
            "ad_seconds": 25,
        },
        "offerwall_config": {
            "enabled": True,
            "source": "house",
            "ad_name": "VEDPREP CRASH COURSE",
            "ad_sub": "JEE & NEET 2027 mock tests with instant solutions.",
            "ad_url": "https://automcq.reyaanshsharma.com",
            "ad_cta": "LEARN MORE",
            "third_party_html": "",
            "frequency_every": 3,
            "min_view_seconds": 0,
            "auto_close_seconds": 0,
            "ad_type": "text",
            "video_url": "",
            "ad_seconds": 25,
        },
    }


def test_public_config_reflects_derived_flat_keys(client):
    client.put(
        "/admin/api/config",
        json={"overlay_config": {"enabled": False, "ad_name": "OTHER AD"}},
        headers=_auth(),
    )
    pub = client.get("/config").json()
    assert pub["sponsor_overlay_enabled"] is False
    assert pub["ad_name"] == "OTHER AD"
    # Other slots untouched.
    assert pub["sponsor_card_enabled"] is True


def test_public_config_corrupt_slot_falls_back(client):
    client.put(
        "/admin/api/config",
        json={"overlay_config": {"enabled": False}},
        headers=_auth(),
    )
    import app.db as db_module

    conn = db_module.get_db()
    conn.execute(
        "UPDATE config SET value = 'not-json' WHERE key = 'overlay_config'"
    )
    conn.commit()
    conn.close()

    pub = client.get("/config").json()
    assert pub["sponsor_overlay_enabled"] is True
    assert pub["ad_name"] == "VEDPREP CRASH COURSE"


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


def test_admin_config_update_slot_persists(client):
    r = client.put(
        "/admin/api/config",
        json={
            "overlay_config": {
                "enabled": False,
                "ad_name": "NEW CAMPAIGN",
                "ad_sub": "Fresh copy.",
                "ad_url": "https://example.com",
            }
        },
        headers=_auth(),
    )
    assert r.status_code == 200
    assert r.json()["sponsor_overlay_enabled"] is False
    assert r.json()["overlay_config"]["ad_name"] == "NEW CAMPAIGN"

    got = client.get("/admin/api/config", headers=_auth()).json()
    assert got["sponsor_overlay_enabled"] is False
    assert got["overlay_config"]["ad_name"] == "NEW CAMPAIGN"
    assert got["overlay_config"]["ad_sub"] == "Fresh copy."
    assert got["overlay_config"]["ad_cta"] == "LEARN MORE"

    pub = client.get("/config").json()
    assert pub["sponsor_overlay_enabled"] is False
    assert pub["ad_name"] == "NEW CAMPAIGN"


def test_admin_config_update_third_party_source(client):
    r = client.put(
        "/admin/api/config",
        json={
            "offerwall_config": {
                "source": "third_party",
                "third_party_html": "<div>AD</div>",
            }
        },
        headers=_auth(),
    )
    assert r.status_code == 200
    cfg = r.json()["offerwall_config"]
    assert cfg["source"] == "third_party"
    assert cfg["third_party_html"] == "<div>AD</div>"
    assert cfg["ad_name"] == "VEDPREP CRASH COURSE"


def test_admin_config_rejects_bad_source(client):
    r = client.put(
        "/admin/api/config",
        json={"card_config": {"source": "banner"}},
        headers=_auth(),
    )
    assert r.status_code == 422


def test_admin_config_rejects_unknown_field(client):
    r = client.put(
        "/admin/api/config",
        json={"overlay_config": {"nope": "x"}},
        headers=_auth(),
    )
    assert r.status_code == 422


def test_admin_config_update_empty_body(client):
    r = client.put("/admin/api/config", json={}, headers=_auth())
    assert r.status_code == 400


def test_admin_config_update_unknown_top_key(client):
    r = client.put(
        "/admin/api/config",
        json={"not_a_key": "x"},
        headers=_auth(),
    )
    assert r.status_code == 422


def test_admin_config_economy_updates_reward_config(client):
    r = client.put(
        "/admin/api/config",
        json={"normal_cost": 2, "ad_reward": 5},
        headers=_auth(),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["normal_cost"] == 2
    assert body["ad_reward"] == 5

    pub = client.get("/config").json()
    assert pub["normal_cost"] == 2
    assert pub["ad_reward"] == 5

    # Economy changes must actually reach the grant-time table.
    device_id = _linked_device(client)
    r = client.post("/offerwall/sandbox-claim", json={"device_id": device_id})
    assert r.status_code == 200
    assert r.json()["delta"] == 5


def test_admin_config_offerwall_ad_length_is_per_slot(client):
    r = client.put(
        "/admin/api/config",
        json={"offerwall_config": {"ad_seconds": 45}},
        headers=_auth(),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["offerwall_config"]["ad_seconds"] == 45
    # The flat legacy key now derives from the offerwall slot.
    assert body["ad_seconds"] == 45

    pub = client.get("/config").json()
    assert pub["offerwall_config"]["ad_seconds"] == 45
    assert pub["ad_seconds"] == 45
    # Other slots keep their defaults — the length is offerwall-only.
    assert pub["overlay_config"]["ad_seconds"] == 25


def test_admin_config_offerwall_video_mode(client):
    r = client.put(
        "/admin/api/config",
        json={
            "offerwall_config": {
                "ad_type": "video",
                "video_url": "https://cdn.example.com/ad.mp4",
            }
        },
        headers=_auth(),
    )
    assert r.status_code == 200
    cfg = r.json()["offerwall_config"]
    assert cfg["ad_type"] == "video"
    assert cfg["video_url"] == "https://cdn.example.com/ad.mp4"


def test_admin_config_rejects_bad_ad_type(client):
    r = client.put(
        "/admin/api/config",
        json={"offerwall_config": {"ad_type": "banner"}},
        headers=_auth(),
    )
    assert r.status_code == 422


def test_admin_config_rejects_bad_top_level_key(client):
    r = client.put(
        "/admin/api/config",
        json={"ad_seconds": 30},
        headers=_auth(),
    )
    assert r.status_code == 422


def test_admin_config_economy_rejects_negative(client):
    r = client.put(
        "/admin/api/config",
        json={"normal_cost": -1},
        headers=_auth(),
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Rewards endpoint
# ---------------------------------------------------------------------------


def test_rewards_get_defaults(client):
    r = client.get("/admin/api/rewards", headers=_auth())
    assert r.status_code == 200
    assert r.json() == {"normal_cost": 1, "fast_cost": 4, "ad_reward": 3}


# ---------------------------------------------------------------------------
# Ad metrics
# ---------------------------------------------------------------------------


def test_ads_metrics_empty(client):
    r = client.get("/admin/api/ads-metrics", headers=_auth())
    assert r.status_code == 200
    body = r.json()
    assert len(body["slots"]) == 3
    assert len(body["series"]) == 30
    assert all(s["impressions"] == 0 for s in body["slots"])


def test_ads_metrics_reflect_events(client):
    client.post("/ads/event", json={"slot": "overlay", "event_type": "impression"})
    client.post("/ads/event", json={"slot": "overlay", "event_type": "click"})
    client.post("/ads/event", json={"slot": "card", "event_type": "close"})

    body = client.get("/admin/api/ads-metrics", headers=_auth()).json()
    by_slot = {s["slot"]: s for s in body["slots"]}
    assert by_slot["overlay"]["impressions"] == 1
    assert by_slot["overlay"]["clicks"] == 1
    assert by_slot["card"]["closes"] == 1
    assert body["series"][-1]["impressions"] == 1


def test_ads_metrics_requires_token(client):
    assert client.get("/admin/api/ads-metrics").status_code == 401
