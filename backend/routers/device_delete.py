"""Device deletion endpoint.

Permanently removes a device row and its entire credit ledger. Used when
a user resets their device ID from the extension popup — the abandoned ID
is wiped server-side so it stops accumulating orphaned rows in the DB.

Deletion is permanent and irreversible: the credit balance and ledger are
gone. The extension shows a warning ("RESET LOSES OLD CREDITS") before
calling this.
"""

import uuid

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.db import get_db

router = APIRouter()


class DeleteDeviceResponse(BaseModel):
    device_id: str
    deleted: bool
    credits_removed: int


@router.delete("/device", response_model=DeleteDeviceResponse)
def delete_device(device_id: str = Query(...)):
    try:
        uuid.UUID(device_id)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"'{device_id}' is not a valid UUID")

    with get_db() as conn:
        row = conn.execute(
            "SELECT credits_balance FROM users WHERE device_id = ?",
            (device_id,),
        ).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Device not found")

        conn.execute("DELETE FROM credit_events WHERE device_id = ?", (device_id,))
        conn.execute("DELETE FROM users WHERE device_id = ?", (device_id,))

        return DeleteDeviceResponse(
            device_id=device_id,
            deleted=True,
            credits_removed=row["credits_balance"],
        )
