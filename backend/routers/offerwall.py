"""Sandboxed rewarded-ad (offerwall) endpoint.

Grants credits through the existing ledger logic in `main.py` — the
grant/consume code is imported and called, never reimplemented. The
sandbox trusts the client-side ad timer plus a crude per-device cooldown;
the real offerwall SDK replaces the verification step once accounts are
approved.

# TODO(real-offerwall): replace the timer/cooldown trust model with a
# server-side verification of the completed ad impression (offerwall SDK).
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

from app.credits import grant_credits, GrantRequest, GrantResponse
from app.db import get_db

router = APIRouter()

SANDBOX_MIN_INTERVAL_SECONDS = 20


class SandboxClaimRequest(BaseModel):
    device_id: str

    @field_validator("device_id")
    @classmethod
    def validate_uuid(cls, v: str) -> str:
        try:
            uuid.UUID(v)
        except ValueError:
            raise ValueError(f"'{v}' is not a valid UUID")
        return v


def _last_sandbox_grant(device_id: str) -> datetime | None:
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT timestamp FROM credit_events
            WHERE device_id = ? AND source = ?
            ORDER BY id DESC LIMIT 1
            """,
            (device_id, "sandbox_offerwall"),
        ).fetchone()
    if not row:
        return None
    return datetime.fromisoformat(row["timestamp"])


@router.post("/offerwall/sandbox-claim", response_model=GrantResponse)
def sandbox_claim(body: SandboxClaimRequest):
    last = _last_sandbox_grant(body.device_id)
    if last is not None:
        elapsed = (datetime.now(timezone.utc).replace(tzinfo=None) - last).total_seconds()
        if elapsed < SANDBOX_MIN_INTERVAL_SECONDS:
            raise HTTPException(
                status_code=429,
                detail=(
                    f"Ad cooldown in progress — try again in "
                    f"{max(1, int(SANDBOX_MIN_INTERVAL_SECONDS - elapsed))}s"
                ),
            )
    return grant_credits(
        GrantRequest(device_id=body.device_id, reason="ad_reward", source="sandbox_offerwall")
    )
