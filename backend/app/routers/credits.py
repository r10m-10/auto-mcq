import uuid

from fastapi import APIRouter, HTTPException, Query

from ..credits import consume_click as consume_credits
from ..credits import grant_credits as grant_credits_impl
from ..db import get_db
from ..models import (
    ConsumeClickRequest,
    ConsumeClickResponse,
    CreditEventResponse,
    GrantRequest,
    GrantResponse,
)

router = APIRouter()


@router.post("/consume-click", response_model=ConsumeClickResponse)
def consume_click(body: ConsumeClickRequest):
    return consume_credits(body)


@router.post("/grant", response_model=GrantResponse)
def grant_credits(body: GrantRequest):
    return grant_credits_impl(body)


@router.get("/history", response_model=list[CreditEventResponse])
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
