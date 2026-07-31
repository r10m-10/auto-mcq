import uuid

from fastapi import APIRouter, HTTPException, Query

from ..db import get_db
from ..models import BalanceResponse, LinkDeviceRequest, LinkDeviceResponse

router = APIRouter()


@router.post("/link-device", response_model=LinkDeviceResponse)
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


@router.get("/balance", response_model=BalanceResponse)
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
