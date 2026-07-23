import uuid
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, field_validator

app = FastAPI(title="Credit System API")

DB_PATH = "app.db"


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT UNIQUE NOT NULL,
                email TEXT,
                credits_balance INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS credit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL REFERENCES users(device_id),
                delta INTEGER NOT NULL,
                reason TEXT NOT NULL,
                source TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS reward_config (
                action_type TEXT PRIMARY KEY,
                credits INTEGER NOT NULL
            )
        """)
        conn.executemany(
            "INSERT OR IGNORE INTO reward_config (action_type, credits) VALUES (?, ?)",
            [("normal_click", 1), ("premium_click", 4), ("ad_reward", 3)],
        )


init_db()


class LinkDeviceRequest(BaseModel):
    device_id: str

    @field_validator("device_id")
    @classmethod
    def validate_uuid(cls, v: str) -> str:
        try:
            uuid.UUID(v)
        except ValueError:
            raise ValueError(f"'{v}' is not a valid UUID")
        return v


class LinkDeviceResponse(BaseModel):
    device_id: str
    credits_balance: int
    linked: bool


class BalanceResponse(BaseModel):
    device_id: str
    credits_balance: int


class ConsumeClickRequest(BaseModel):
    device_id: str
    click_type: str

    @field_validator("device_id")
    @classmethod
    def validate_uuid(cls, v: str) -> str:
        try:
            uuid.UUID(v)
        except ValueError:
            raise ValueError(f"'{v}' is not a valid UUID")
        return v

    @field_validator("click_type")
    @classmethod
    def validate_click_type(cls, v: str) -> str:
        if v not in ("normal_click", "premium_click"):
            raise ValueError(f"click_type must be 'normal_click' or 'premium_click', got '{v}'")
        return v


class GrantRequest(BaseModel):
    device_id: str
    reason: str
    source: Optional[str] = None

    @field_validator("device_id")
    @classmethod
    def validate_uuid(cls, v: str) -> str:
        try:
            uuid.UUID(v)
        except ValueError:
            raise ValueError(f"'{v}' is not a valid UUID")
        return v

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, v: str) -> str:
        if v != "ad_reward":
            raise ValueError(f"reason must be 'ad_reward', got '{v}'")
        return v


class ConsumeClickResponse(BaseModel):
    device_id: str
    credits_balance: int
    delta: int


class GrantResponse(BaseModel):
    device_id: str
    credits_balance: int
    delta: int


class CreditEventResponse(BaseModel):
    id: int
    device_id: str
    delta: int
    reason: str
    source: Optional[str]
    timestamp: str


@app.post("/link-device", response_model=LinkDeviceResponse)
def link_device(body: LinkDeviceRequest):
    device_id = body.device_id
    with get_db() as conn:
        row = conn.execute(
            "SELECT device_id, credits_balance FROM users WHERE device_id = ?",
            (device_id,),
        ).fetchone()

        if row:
            return LinkDeviceResponse(
                device_id=row["device_id"],
                credits_balance=row["credits_balance"],
                linked=False,
            )

        conn.execute(
            "INSERT INTO users (device_id, credits_balance) VALUES (?, 0)",
            (device_id,),
        )
        return LinkDeviceResponse(
            device_id=device_id,
            credits_balance=0,
            linked=True,
        )


@app.get("/balance", response_model=BalanceResponse)
def get_balance(device_id: str = Query(...)):
    try:
        uuid.UUID(device_id)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"'{device_id}' is not a valid UUID")

    with get_db() as conn:
        row = conn.execute(
            "SELECT device_id, credits_balance FROM users WHERE device_id = ?",
            (device_id,),
        ).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Device not found")

        return BalanceResponse(
            device_id=row["device_id"],
            credits_balance=row["credits_balance"],
        )


@app.post("/consume-click", response_model=ConsumeClickResponse)
def consume_click(body: ConsumeClickRequest):
    device_id = body.device_id
    click_type = body.click_type

    with get_db() as conn:
        user = conn.execute(
            "SELECT device_id FROM users WHERE device_id = ?", (device_id,)
        ).fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="Device not found")

        config = conn.execute(
            "SELECT credits FROM reward_config WHERE action_type = ?", (click_type,)
        ).fetchone()
        cost = config["credits"]

        conn.execute(
            "UPDATE users SET credits_balance = credits_balance - ? WHERE device_id = ? AND credits_balance >= ?",
            (cost, device_id, cost),
        )
        if conn.total_changes == 0:
            current = conn.execute(
                "SELECT credits_balance FROM users WHERE device_id = ?", (device_id,)
            ).fetchone()["credits_balance"]
            raise HTTPException(
                status_code=402,
                detail=f"Insufficient credits: have {current}, need {cost}",
            )

        conn.execute(
            "INSERT INTO credit_events (device_id, delta, reason) VALUES (?, ?, ?)",
            (device_id, -cost, click_type),
        )

        new_balance = conn.execute(
            "SELECT credits_balance FROM users WHERE device_id = ?", (device_id,)
        ).fetchone()["credits_balance"]

    return ConsumeClickResponse(
        device_id=device_id,
        credits_balance=new_balance,
        delta=-cost,
    )


@app.post("/grant", response_model=GrantResponse)
def grant_credits(body: GrantRequest):
    device_id = body.device_id
    reason = body.reason
    source = body.source

    with get_db() as conn:
        user = conn.execute(
            "SELECT device_id FROM users WHERE device_id = ?", (device_id,)
        ).fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="Device not found")

        config = conn.execute(
            "SELECT credits FROM reward_config WHERE action_type = ?", (reason,)
        ).fetchone()
        amount = config["credits"]

        conn.execute(
            "UPDATE users SET credits_balance = credits_balance + ? WHERE device_id = ?",
            (amount, device_id),
        )

        conn.execute(
            "INSERT INTO credit_events (device_id, delta, reason, source) VALUES (?, ?, ?, ?)",
            (device_id, amount, reason, source),
        )

        new_balance = conn.execute(
            "SELECT credits_balance FROM users WHERE device_id = ?", (device_id,)
        ).fetchone()["credits_balance"]

    return GrantResponse(
        device_id=device_id,
        credits_balance=new_balance,
        delta=amount,
    )


@app.get("/history", response_model=list[CreditEventResponse])
def get_history(device_id: str = Query(...)):
    try:
        uuid.UUID(device_id)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"'{device_id}' is not a valid UUID")

    with get_db() as conn:
        user = conn.execute(
            "SELECT device_id FROM users WHERE device_id = ?", (device_id,)
        ).fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="Device not found")

        rows = conn.execute(
            """
            SELECT id, device_id, delta, reason, source, timestamp
            FROM credit_events
            WHERE device_id = ?
            ORDER BY timestamp DESC, id DESC
            LIMIT 50
            """,
            (device_id,),
        ).fetchall()

    return [
        CreditEventResponse(
            id=row["id"],
            device_id=row["device_id"],
            delta=row["delta"],
            reason=row["reason"],
            source=row["source"],
            timestamp=row["timestamp"],
        )
        for row in rows
    ]


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
