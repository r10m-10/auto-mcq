import uuid
import sqlite3
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, field_validator

app = FastAPI(title="Credit System API")

DB_PATH = "app.db"


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    with get_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT UNIQUE NOT NULL,
                email TEXT,
                credits_balance INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
