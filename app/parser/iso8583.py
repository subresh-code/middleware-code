from iso8583 import decode, encode
from iso8583.decoder import DecodeError
from iso8583.encoder import EncodeError
from iso8583.specs import default_ascii as spec

from app.parser.schemas.message import Iso8583Message

SUPPORTED_MTI = {"0200", "0400", "0800", "0100", "0220", "0221"}  # 0200 also handles inquiry via DE3
MANDATORY_FIELDS = {"4", "11", "37", "49", "102", "103"}


class ParseError(Exception):
    pass


def parse_iso8583(raw_bytes: bytes, frame_length_type: int = 2) -> Iso8583Message:
    """
    Parse raw binary ISO 8583 message.

    raw_bytes       — exactly what arrived off the TCP socket
    frame_length_type — 2 or 4, from ase_registry, controls header stripping
    """
    # ── Step 1: store raw hex immediately — before anything else ──────────
    raw_hex = raw_bytes.hex().upper()

    try:
        # ── Step 2: strip frame length header ───────────────────────────────
        if frame_length_type not in (2, 4):
            raise ParseError(f"Invalid frame_length_type: {frame_length_type}")

        if len(raw_bytes) < frame_length_type + 20:
            raise ParseError("Message too short to contain header + MTI + bitmap")

        declared_len = int.from_bytes(raw_bytes[:frame_length_type], "big")
        payload = raw_bytes[frame_length_type:]

        if len(payload) != declared_len:
            raise ParseError(
                f"Frame length mismatch: header declares {declared_len} bytes, "
                f"got {len(payload)} bytes"
            )

        # ── Step 3: decode via pyiso8583 ──────────────────────────────────
        try:
            decoded, _ = decode(payload, spec)
        except DecodeError as e:
            raise ParseError(f"ISO 8583 decode error: {e}")

        # ── Step 4: validate MTI ─────────────────────────────────────────────
        mti = decoded.get("t", "")
        if mti not in SUPPORTED_MTI:
            raise ParseError(f"Unsupported MTI: '{mti}'")

        # ── Step 5: validate mandatory fields present ────────────────────────
        for field in MANDATORY_FIELDS:
            if field not in decoded:
                raise ParseError(f"Missing mandatory field DE{field}")

        # ── Step 6: validate DE4 non-zero ─────────────────────────────────
        de4 = decoded["4"]
        if de4 == "000000000000":
            raise ParseError("DE4 amount is zero")

        # ── Step 7: extract bitmaps from payload bytes directly ─────────────
        primary_bitmap = payload[4:20].hex().upper()
        secondary_bitmap = None
        if int(primary_bitmap, 16) & (1 << 127):
            secondary_bitmap = payload[20:36].hex().upper()

        # ── Step 8: construct and return — Pydantic validators run here ──
        return Iso8583Message(
            mti=mti,
            primary_bitmap=primary_bitmap,
            secondary_bitmap=secondary_bitmap,
            de4=de4,
            de11=decoded["11"],
            de37=decoded["37"],
            de49=decoded["49"],
            de102=decoded["102"],
            de103=decoded["103"],
            de7=decoded.get("7"),
            raw_hex=raw_hex,
        )

    except ParseError:
        raise
    except Exception as e:
        raise ParseError(f"Unexpected parser error: {e}")


def encode_iso8583_response(mti: str, fields: dict, header_len: int = 2) -> bytes:
    """
    Build a minimal ISO 8583 response message (0210/0410).

    mti        — response MTI, e.g. "0210" or "0410"
    fields     — dict of DE numbers to values, e.g. {"39": "00", "11": "123456"}
    header_len — 2 or 4, length of the frame header to prepend
    """
    try:
        encoded, _ = encode({**fields, "t": mti}, spec)
        header = len(encoded).to_bytes(header_len, "big")
        return header + encoded
    except EncodeError as e:
        raise ParseError(f"ISO 8583 encode error: {e}")
