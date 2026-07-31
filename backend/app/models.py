import uuid
from typing import Optional

from pydantic import BaseModel, field_validator


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
