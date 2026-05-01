"""
Generates a binary ISO 8583 0200 message and saves it to tests/samples/.
Uses pyiso8583 so the format exactly matches what the parser expects.

Usage:
    python scripts/generate_sample_message.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import binascii
from iso8583 import encode
from iso8583.specs import default_ascii as spec

# ── Message fields ────────────────────────────────────────────────────────────
MESSAGE = {
    "t":   "0200",          # MTI
    "3":   "000000",        # Processing code
    "4":   "000000150050",  # Amount — NPR 1500.50 → UInt64 150050
    "7":   "0430120000",    # Transmission datetime MMDDHHmmss
    "11":  "000001",        # STAN
    "37":  "000000000001",  # RRN
    "41":  "TERM0001",      # Terminal ID
    "49":  "524",           # Currency — NPR
    "102": "9800000002",    # Source account DE102
    "103": "9800000001",    # Dest account DE103 — must match seed wallet mapping
}

def generate():
    raw, _ = encode(MESSAGE, spec)
    raw_bytes = bytes(raw)

    # 2-byte length header
    header = len(raw_bytes).to_bytes(2, "big")
    full_frame = header + raw_bytes

    # Save to samples directory
    output_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "tests", "samples", "valid_0200_npr.bin"
    )
    with open(output_path, "wb") as f:
        f.write(full_frame)

    print(f"✓ Sample message written to: {output_path}")
    print(f"    Total bytes  : {len(full_frame)}")
    print(f"    Header       : {header.hex().upper()} ({len(raw_bytes)} bytes declared)")
    print(f"    MTI          : 0200")
    print(f"    DE4 amount   : 000000150050 → UInt64 150050")
    print(f"    DE49 currency: 524 (NPR)")
    print(f"    DE103 dest   : 9800000001")
    print(f"    Raw hex      : {full_frame.hex().upper()}")


if __name__ == "__main__":
    generate()