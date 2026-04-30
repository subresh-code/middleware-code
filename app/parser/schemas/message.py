from pydantic import BaseModel, Field
from typing import Optional


class Iso8583Message(BaseModel):
    """Parsed ISO 8583 message with mandatory and common data elements."""

    # Message Type Indicator (4 bytes)
    mti: str = Field(..., pattern="^(0200|0400)$")

    # Primary bitmap (16 hex chars)
    primary_bitmap: str

    # Secondary bitmap (16 hex chars, may be empty if not present)
    secondary_bitmap: Optional[str] = None

    # Mandatory fields per BLAST.md
    de4: str = Field(..., description="Amount, 12 chars numeric")
    de11: str = Field(..., description="STAN, 6 chars numeric")
    de37: str = Field(..., description="Retrieval reference number")
    de49: str = Field(..., description="Currency code, 3 chars numeric")
    de102: str = Field(..., description="Sender account, LLVAR")
    de103: str = Field(..., description="Destination account, LLVAR")

    # Optional but common
    de7: Optional[str] = Field(None, description="Transmission date/time, 10 chars MMDDHHmmss")

    # Raw hex for audit/recovery
    raw_hex: Optional[str] = None
