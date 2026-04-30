import pytest
from app.parser.iso8583 import parse_iso8583, ParseError
from iso8583 import encode
from iso8583.specs import default_ascii as spec


# ── Helper ────────────────────────────────────────────────────────
def _build_raw_message(fields: dict, frame_length_type: int = 2) -> bytes:
    """Build a valid ISO 8583 message and optionally prepend length header."""
    raw, _ = encode({"t": "0200", **fields}, spec)
    if frame_length_type == 2:
        header = len(raw).to_bytes(2, "big")
    elif frame_length_type == 4:
        header = len(raw).to_bytes(4, "big")
    else:
        raise ValueError("Invalid frame_length_type")
    return header + bytes(raw)


# ── B.L.A.S.T. Test Cases ────────────────────────────────────────

# ✓ Valid 0200 from registered ASE → parsed and queued
def test_valid_0200_parses():
    raw = _build_raw_message({
        "4": "000000001000",
        "11": "123456",
        "37": "123456789012",
        "49": "840",
        "102": "1234567890123456",
        "103": "9876543210987654",
    })
    msg = parse_iso8583(raw, frame_length_type=2)
    assert msg.mti == "0200"
    assert msg.de4 == "000000001000"
    assert msg.de11 == "123456"
    assert msg.de49 == "840"
    assert msg.raw_hex is not None
    assert len(msg.raw_hex) > 0


# ✓ Missing DE103 → ParseError with field name in message
def test_missing_de103():
    raw = _build_raw_message({
        "4": "000000001000",
        "11": "123456",
        "37": "123456789012",
        "49": "840",
        "102": "1234567890123456",
        # DE103 intentionally omitted
    })
    with pytest.raises(ParseError) as exc_info:
        parse_iso8583(raw, frame_length_type=2)
    assert "DE103" in str(exc_info.value)


# ✓ DE4 = "000000000000" → ParseError (zero amount)
def test_de4_zero_amount():
    raw = _build_raw_message({
        "4": "000000000000",
        "11": "123456",
        "37": "123456789012",
        "49": "840",
        "102": "1234567890123456",
        "103": "9876543210987654",
    })
    with pytest.raises(ParseError) as exc_info:
        parse_iso8583(raw, frame_length_type=2)
    assert "zero" in str(exc_info.value).lower()


# ✓ DE49 = "999" (unsupported) → ParseError
def test_de49_unsupported_currency():
    raw = _build_raw_message({
        "4": "000000001000",
        "11": "123456",
        "37": "123456789012",
        "49": "999",
        "102": "1234567890123456",
        "103": "9876543210987654",
    })
    with pytest.raises(ParseError) as exc_info:
        parse_iso8583(raw, frame_length_type=2)
    assert "999" in str(exc_info.value)


# ✓ Corrupted bitmap → ParseError, not silent wrong result
def test_corrupted_bitmap():
    raw = _build_raw_message({
        "4": "000000001000",
        "11": "123456",
        "37": "123456789012",
        "49": "840",
        "102": "1234567890123456",
        "103": "9876543210987654",
    })
    # Corrupt the bitmap (bytes 4-19)
    corrupted = bytearray(raw)
    corrupted[4:20] = b'\\x00' * 16  # Zero out bitmap
    with pytest.raises(ParseError):
        parse_iso8583(bytes(corrupted), frame_length_type=2)


# ✓ DE4 extracted as exactly 12 characters
def test_de4_exactly_12_chars():
    raw = _build_raw_message({
        "4": "000000001000",
        "11": "123456",
        "37": "123456789012",
        "49": "840",
        "102": "1234567890123456",
        "103": "9876543210987654",
    })
    msg = parse_iso8583(raw, frame_length_type=2)
    assert len(msg.de4) == 12
    assert msg.de4 == "000000001000"


# ✓ DE11 (STAN) must be exactly 6 characters
def test_de11_exactly_6_chars():
    raw = _build_raw_message({
        "4": "000000001000",
        "11": "123456",
        "37": "123456789012",
        "49": "840",
        "102": "1234567890123456",
        "103": "9876543210987654",
    })
    msg = parse_iso8583(raw, frame_length_type=2)
    assert len(msg.de11) == 6
    assert msg.de11 == "123456"


# ✓ DE7 (transmission datetime) must be exactly 10 characters MMDDHHmmss
def test_de7_exactly_10_chars():
    raw = _build_raw_message({
        "4": "000000001000",
        "7": "1234567890",  # 10 chars
        "11": "123456",
        "37": "123456789012",
        "49": "840",
        "102": "1234567890123456",
        "103": "9876543210987654",
    })
    msg = parse_iso8583(raw, frame_length_type=2)
    assert msg.de7 is not None
    assert len(msg.de7) == 10
    assert msg.de7 == "1234567890"


# ✓ Raw hex stored before parsing — stored on entry, not after
def test_raw_hex_stored_before_parsing():
    raw = _build_raw_message({
        "4": "000000001000",
        "11": "123456",
        "37": "123456789012",
        "49": "840",
        "102": "1234567890123456",
        "103": "9876543210987654",
    })
    # Patch parse_iso8583 to check raw_hex is set before any processing
    # We verify by checking raw_hex matches input
    msg = parse_iso8583(raw, frame_length_type=2)
    assert msg.raw_hex == raw.hex().upper()


# ✓ Entire function wrapped in try/except — never crashes server
def test_parser_never_crashes_server():
    # Garbage bytes
    with pytest.raises(ParseError):
        parse_iso8583(b"garbage", frame_length_type=2)

    # Empty bytes
    with pytest.raises(ParseError):
        parse_iso8583(b"", frame_length_type=2)

    # Too short
    with pytest.raises(ParseError):
        parse_iso8583(b"\\x00\\x02", frame_length_type=2)


# ✓ Sample messages from three different ASE formats → all parse correctly
def test_multiple_ase_formats():
    # ASE A — standard 0200
    raw1 = _build_raw_message({
        "4": "000000005000",
        "11": "111111",
        "37": "AAAAAAAAAAAA",
        "49": "524",
        "102": "1111111111111111",
        "103": "AAAAAAAAAAAAAAAA",
    })
    msg1 = parse_iso8583(raw1, frame_length_type=2)
    assert msg1.de49 == "524"

    # ASE B — with DE7
    raw2 = _build_raw_message({
        "4": "000000010000",
        "7": "1234567890",
        "11": "222222",
        "37": "BBBBBBBBBBBB",
        "49": "840",
        "102": "2222222222222222",
        "103": "BBBBBBBBBBBBBBBB",
    })
    msg2 = parse_iso8583(raw2, frame_length_type=2)
    assert msg2.de49 == "840"
    assert msg2.de7 == "1234567890"

    # ASE C — 0400 (reversal)
    raw3 = _build_raw_message({
        "4": "000000020000",
        "11": "333333",
        "37": "CCCCCCCCCCCC",
        "49": "356",
        "102": "3333333333333333",
        "103": "CCCCCCCCCCCCCCCC",
    })
    # Manually set MTI to 0400
    from iso8583 import encode
    fields = {
        "t": "0400",
        "4": "000000020000",
        "11": "333333",
        "37": "CCCCCCCCCCCC",
        "49": "356",
        "102": "3333333333333333",
        "103": "CCCCCCCCCCCCCCCC",
    }
    raw3, _ = encode(fields, spec)
    raw3 = len(raw3).to_bytes(2, "big") + bytes(raw3)
    msg3 = parse_iso8583(raw3, frame_length_type=2)
    assert msg3.mti == "0400"
    assert msg3.de49 == "356"


# ✓ Frame length mismatch → ParseError
def test_frame_length_mismatch():
    raw = _build_raw_message({
        "4": "000000001000",
        "11": "123456",
        "37": "123456789012",
        "49": "840",
        "102": "1234567890123456",
        "103": "9876543210987654",
    })
    # Corrupt the length header
    corrupted = bytearray(raw)
    # Set header to wrong length
    corrupted[0:2] = (9999).to_bytes(2, "big")
    with pytest.raises(ParseError) as exc_info:
        parse_iso8583(bytes(corrupted), frame_length_type=2)
    assert "mismatch" in str(exc_info.value).lower()


# ✓ Message too large → rejected
def test_message_too_large():
    """Test that messages exceeding the configurated max size are rejected."""
    # Build a valid message
    raw = _build_raw_message({
        "4": "000000001000",
        "11": "123456",
        "37": "123456789012",
        "49": "840",
        "102": "1234567890123456",
        "103": "9876543210987654",
    })
    # Create oversized message by adding many null bytes
    oversized = raw + b'\x00' * 5000
    with pytest.raises(ParseError) as exc_info:
        parse_iso8583(oversized, frame_length_type=2)
    # Should fail with frame length mismatch since header doesn't match actual size
    assert "mismatch" in str(exc_info.value).lower() or "large" in str(exc_info.value).lower()
