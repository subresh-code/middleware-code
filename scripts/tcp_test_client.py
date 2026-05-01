"""
TCP test client — simulates a real ASE sending an ISO 8583 0200 message.
Connects to the middleware TCP server, authenticates, sends a payment,
reads the 0210 response, and reports what happened.

Usage:
    python scripts/tcp_test_client.py

Expected output:
    ✓ Connected to 127.0.0.1:9000
    ✓ API key sent
    ✓ Message sent (N bytes)
    ✓ Response received: <hex>
    ✓ Response MTI: 0210
    ✓ DE39 response code: 00 (Approved)
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import socket
import struct
from iso8583 import decode
from iso8583.specs import default_ascii as spec

# ── Config — must match seed_test_data.py ─────────────────────────────────────
HOST           = "127.0.0.1"
PORT           = 9000
API_KEY        = "test-api-key-12345"
SAMPLE_PATH    = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "tests", "samples", "valid_0200_npr.bin"
)

DE39_CODES = {
    "00": "Approved",
    "05": "Do not honour",
    "12": "Invalid transaction",
    "30": "Format error",
    "96": "System malfunction",
}


def run():
    # ── Load sample message ───────────────────────────────────────────────────
    if not os.path.exists(SAMPLE_PATH):
        print("✗ Sample message not found.")
        print("  Run: python scripts/generate_sample_message.py")
        sys.exit(1)

    with open(SAMPLE_PATH, "rb") as f:
        message = f.read()

    print(f"  Sample loaded  : {len(message)} bytes")
    print(f"  Hex            : {message.hex().upper()}")
    print()

    # ── Connect ───────────────────────────────────────────────────────────────
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(10)
        try:
            s.connect((HOST, PORT))
        except ConnectionRefusedError:
            print(f"✗ Could not connect to {HOST}:{PORT}")
            print("  Is the TCP server running? Check docker-compose logs")
            sys.exit(1)

        print(f"✓ Connected to {HOST}:{PORT}")

        # ── Send API key ──────────────────────────────────────────────────────
        s.sendall((API_KEY + "\n").encode("ascii"))
        print(f"✓ API key sent: {API_KEY}")

        # ── Send ISO 8583 message ─────────────────────────────────────────────
        s.sendall(message)
        print(f"✓ Message sent: {len(message)} bytes")

        # ── Read response header ──────────────────────────────────────────────
        try:
            resp_header = _recv_exact(s, 2)
        except Exception as e:
            print(f"✗ No response received: {e}")
            sys.exit(1)

        resp_len = struct.unpack("!H", resp_header)[0]
        resp_body = _recv_exact(s, resp_len)
        full_response = resp_header + resp_body

        print(f"✓ Response received: {full_response.hex().upper()}")

        # ── Decode response ───────────────────────────────────────────────────
        try:
            decoded, _ = decode(resp_body, spec)
            mti    = decoded.get("t", "????")
            de39   = decoded.get("39", "??")
            de11   = decoded.get("11", "??????")
            meaning = DE39_CODES.get(de39, "Unknown")

            print()
            print(f"✓ Response MTI : {mti}")
            print(f"✓ STAN (DE11)  : {de11}")
            print(f"✓ DE39 code    : {de39} — {meaning}")
            print()

            if de39 == "00":
                print("✅ PAYMENT ACCEPTED — middleware processed the 0200 correctly")
            else:
                print(f"⚠️  PAYMENT DECLINED — DE39={de39} ({meaning})")

        except Exception as e:
            print(f"✗ Could not decode response: {e}")
            print(f"  Raw response hex: {full_response.hex().upper()}")


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    """Read exactly n bytes from socket."""
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError(f"Connection closed after {len(buf)}/{n} bytes")
        buf += chunk
    return buf


if __name__ == "__main__":
    run()