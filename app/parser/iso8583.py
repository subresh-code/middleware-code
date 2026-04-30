import struct
import binascii
from typing import Optional, Dict
from app.parser.schemas.message import Iso8583Message
from app.config import settings


SUPPORTED_MTI = {"0200", "0400"}
MANDATORY_FIELDS = {"4", "11", "37", "49", "102", "103"}
SUPPORTED_CURRENCIES = {"524", "840", "356"}

# DE field types: (type, length_bytes_or_llvar)
# Numeric fields are BCD; alphanumeric are ASCII
FIELD_SPECS = {
    "4": ("numeric", 12),   # Amount, 12 chars
    "7": ("numeric", 10),   # Transmission date/time
    "11": ("numeric", 6),   # STAN
    "37": ("alphanumeric", 12),  # Retrieval ref
    "49": ("numeric", 3),   # Currency code
    "102": ("llvar", None),  # Sender account
    "103": ("llvar", None),  # Destination account
}


class ParseError(Exception):
    pass


def _read_length_header(data: bytes, header_bytes: int) -> int:
    if header_bytes == 2:
        return struct.unpack("!H", data[:2])[0]
    elif header_bytes == 4:
        return struct.unpack("!I", data[:4])[0]
    raise ParseError(f"Unsupported header length: {header_bytes}")


def _extract_numeric(data: bytes, length: int) -> str:
    """Extract BCD numeric field."""
    expected_bytes = (length + 1) // 2
    if len(data) < expected_bytes:
        raise ParseError("Not enough data for numeric field")
    hex_str = binascii.hexlify(data[:expected_bytes]).decode("ascii").upper()
    # Remove padding nibble if odd length
    return hex_str[:length]


def _extract_alphanumeric(data: bytes, length: int) -> str:
    return data[:length].decode("ascii", errors="replace")


def _extract_llvar(data: bytes) -> tuple[str, bytes]:
    """Extract LLVAR field (1-byte length + data). Returns (value, remaining_data)."""
    if not data:
        raise ParseError("Empty data for LLVAR")
    length = data[0]
    if len(data) < 1 + length:
        raise ParseError("Not enough data for LLVAR")
    value = data[1:1+length].decode("ascii", errors="replace")
    return value, data[1+length:]


def _extract_lllvar(data: bytes) -> tuple[str, bytes]:
    """Extract LLLVAR field (2-byte BCD length + data)."""
    if len(data) < 2:
        raise ParseError("Not enough data for LLLVAR")
    length = int(binascii.hexlify(data[:2]).decode("ascii"))
    if len(data) < 2 + length:
        raise ParseError("Not enough data for LLLVAR")
    value = data[2:2+length].decode("ascii", errors="replace")
    return value, data[2+length:]


def _parse_bitmap(data: bytes) -> tuple[str, str, bytes]:
    """Parse primary and optional secondary bitmap. Returns (primary_hex, secondary_hex_or_empty, remaining_data)."""
    if len(data) < 16:
        raise ParseError("Not enough data for primary bitmap")
    primary_hex = binascii.hexlify(data[:16]).decode("ascii").upper()
    remaining = data[16:]

    # Check if secondary bitmap is present (bit 1 of primary bitmap)
    primary_int = int(primary_hex, 16)
    if primary_int & (1 << 63):  # Bit 1 (MSB) set
        if len(remaining) < 16:
            raise ParseError("Secondary bitmap indicated but not enough data")
        secondary_hex = binascii.hexlify(remaining[:16]).decode("ascii").upper()
        return primary_hex, secondary_hex, remaining[16:]
    return primary_hex, "", remaining


def parse_iso8583(raw_bytes: bytes, ase_name: str = "unknown") -> Iso8583Message:
    """
    Parse raw binary ISO 8583 message.
    Expects optional 2 or 4 byte length header, then MTI + Bitmap + Fields.
    """
    header_len = settings.iso8583_header_length
    max_bytes = settings.tcp_max_message_bytes

    if len(raw_bytes) > max_bytes:
        raise ParseError(f"Message too large: {len(raw_bytes)} bytes")

    # Strip length header if present
    if len(raw_bytes) >= header_len:
        msg_len = _read_length_header(raw_bytes, header_len)
        payload = raw_bytes[header_len:]
        if len(payload) != msg_len:
            raise ParseError(f"Length mismatch: header={msg_len}, actual={len(payload)}")
    else:
        payload = raw_bytes

    if len(payload) < 20:  # MTI(4) + Bitmap(16) minimum
        raise ParseError("Message too short")

    # Extract MTI (4 bytes ASCII)
    mti = payload[:4].decode("ascii", errors="replace")
    if mti not in SUPPORTED_MTI:
        raise ParseError(f"Unsupported MTI: {mti}")
    remaining = payload[4:]

    # Parse bitmap
    primary_bmp, secondary_bmp, remaining = _parse_bitmap(remaining)

    # Parse fields based on bitmap
    fields: Dict[str, str] = {}
    # For simplicity, parse fields in order: check bitmap bits and extract known fields
    # Primary bitmap covers DE1-64, secondary covers DE65-128
    # We only care about specific fields (4,7,11,37,49,102,103)

    # Simplified: iterate through remaining bytes and extract known fields
    # In production, use bitmap to determine which fields are present
    # Here we parse in expected order for 0200/0400 messages

    # DE4 (Amount) - always position 0 in data after bitmap
    if "4" in MANDATORY_FIELDS:
        fields["4"] = _extract_numeric(remaining, 12)
        remaining = remaining[6:]  # 12 BCD = 6 bytes

    # DE7 (optional)
    if len(remaining) >= 5:
        try:
            fields["7"] = _extract_numeric(remaining, 10)
            remaining = remaining[5:]
        except:
            pass

    # DE11 (STAN)
    if "11" in MANDATORY_FIELDS:
        fields["11"] = _extract_numeric(remaining, 6)
        remaining = remaining[3:]

    # DE37 (Retrieval ref)
    if "37" in MANDATORY_FIELDS:
        fields["37"] = _extract_alphanumeric(remaining, 12)
        remaining = remaining[12:]

    # DE49 (Currency)
    if "49" in MANDATORY_FIELDS:
        fields["49"] = _extract_numeric(remaining, 3)
        remaining = remaining[2:]  # 3 BCD = 2 bytes

    # DE102 (LLVAR)
    if len(remaining) > 0:
        try:
            fields["102"], remaining = _extract_llvar(remaining)
        except:
            pass

    # DE103 (LLVAR)
    if len(remaining) > 0:
        try:
            fields["103"], remaining = _extract_llvar(remaining)
        except:
            pass

    # Validate mandatory fields
    for f in MANDATORY_FIELDS:
        if f not in fields:
            raise ParseError(f"Missing mandatory field DE{f}")

    # Validate DE4 (amount non-zero)
    if fields["4"] == "000000000000":
        raise ParseError("DE4 amount is zero")

    # Validate DE49 (currency)
    if fields["49"] not in SUPPORTED_CURRENCIES:
        raise ParseError(f"Unsupported currency code: {fields['49']}")

    return Iso8583Message(
        mti=mti,
        primary_bitmap=primary_bmp,
        secondary_bitmap=secondary_bmp if secondary_bmp else None,
        de4=fields["4"],
        de11=fields["11"],
        de37=fields["37"],
        de49=fields["49"],
        de102=fields.get("102", ""),
        de103=fields.get("103", ""),
        de7=fields.get("7"),
        raw_hex=binascii.hexlify(raw_bytes).decode("ascii").upper(),
    )
