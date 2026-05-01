from pydantic import BaseModel, Field, field_validator
from typing import Optional


class Iso8583Message(BaseModel):
    """Parsed ISO 8583 message with mandatory and common data elements."""

    mti: str = Field(..., pattern="^(0200|0400)$")
    primary_bitmap: str
    secondary_bitmap: Optional[str] = None

    de4: str = Field(..., description="Amount — exactly 12 numeric chars")
    de11: str = Field(..., description="STAN — exactly 6 numeric chars")
    de37: str = Field(..., description="RRN — exactly 12 chars")
    de49: str = Field(..., description="Currency code — 524, 840, or 356")
    de102: str = Field(..., description="Source account LLVAR")
    de103: str = Field(..., description="Destination account LLVAR")

    de7: Optional[str] = Field(None, description="Transmission datetime — exactly 10 chars MMDDHHmmss")

    raw_hex: str = Field(..., description="Original raw bytes as hex — stored before parsing")

    @field_validator("de4")
    @classmethod
    def validate_de4(cls, v: str) -> str:
        if len(v) != 12:
            raise ValueError(f"DE4 must be exactly 12 characters, got {len(v)}")
        if not v.isdigit():
            raise ValueError("DE4 must be numeric")
        return v

    @field_validator("de11")
    @classmethod
    def validate_de11(cls, v: str) -> str:
        if len(v) != 6:
            raise ValueError(f"DE11 must be exactly 6 characters, got {len(v)}")
        if not v.isdigit():
            raise ValueError("DE11 must be numeric")
        return v

    @field_validator("de37")
    @classmethod
    def validate_de37(cls, v: str) -> str:
        if len(v) != 12:
            raise ValueError(f"DE37 must be exactly 12 characters, got {len(v)}")
        return v

    @field_validator("de49")
    @classmethod
    def validate_de49(cls, v: str) -> str:
        if v not in {"524", "840", "356"}:
            raise ValueError(f"DE49 '{v}' not in supported currencies: 524, 840, 356")
        return v

    @field_validator("de7")
    @classmethod
    def validate_de7(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and len(v) != 10:
            raise ValueError(f"DE7 must be exactly 10 characters, got {len(v)}")
        return v
