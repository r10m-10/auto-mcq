from fastapi import HTTPException

from .db import get_db
from .models import (
    ConsumeClickRequest,
    ConsumeClickResponse,
    GrantRequest,
    GrantResponse,
)


def consume_click(body: ConsumeClickRequest) -> ConsumeClickResponse:
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


def grant_credits(body: GrantRequest) -> GrantResponse:
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
