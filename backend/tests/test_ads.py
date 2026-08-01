import tempfile
import uuid
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers.ads import router as ads_router
from routers.config import router as config_router

TEST_TOKEN = "test-admin-token-0123456789abcdef"


def _build_app():
    app = FastAPI()
    app.include_router(config_router)
    app.include_router(ads_router)
    return app


def _fresh_db(monkeypatch):
    tmp = Path(tempfile.mkdtemp(prefix="automcq_ads_test_"))
    import app.db as db_module

    monkeypatch.setattr(db_module, "DB_PATH", str(tmp / "app.db"))
    db_module.init_db()


@pytest.fixture()
def client(monkeypatch):
    _fresh_db(monkeypatch)
    with TestClient(_build_app()) as c:
        yield c


def _device_id() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Event intake
# ---------------------------------------------------------------------------


def test_record_event_created(client):
    r = client.post(
        "/ads/event",
        json={"slot": "overlay", "event_type": "impression"},
    )
    assert r.status_code == 201
    assert r.json() == {"ok": True}


def test_record_event_with_device(client):
    device_id = _device_id()
    r = client.post(
        "/ads/event",
        json={"slot": "card", "event_type": "click", "device_id": device_id},
    )
    assert r.status_code == 201


def test_record_event_rejects_unknown_slot(client):
    r = client.post(
        "/ads/event",
        json={"slot": "banner", "event_type": "impression"},
    )
    assert r.status_code == 422


def test_record_event_rejects_unknown_event(client):
    r = client.post(
        "/ads/event",
        json={"slot": "overlay", "event_type": "view"},
    )
    assert r.status_code == 422


def test_events_persist_across_calls(client, monkeypatch):
    for i in range(3):
        assert client.post(
            "/ads/event",
            json={"slot": "overlay", "event_type": "impression"},
        ).status_code == 201
    assert client.post(
        "/ads/event",
        json={"slot": "overlay", "event_type": "close"},
    ).status_code == 201

    import app.db as db_module

    conn = db_module.get_db()
    rows = conn.execute(
        "SELECT slot, event_type FROM ad_events ORDER BY id"
    ).fetchall()
    conn.close()
    assert len(rows) == 4
    assert rows[0]["slot"] == "overlay"
    assert rows[0]["event_type"] == "impression"
    assert rows[-1]["event_type"] == "close"
