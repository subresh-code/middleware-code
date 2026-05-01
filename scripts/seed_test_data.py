"""
Seed script — inserts a test ASE and wallet mapping for end-to-end verification.
Run once before running the TCP test client.

Usage:
    python scripts/seed_test_data.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bcrypt
from app.db import SessionLocal
from app.models.payment import AseRegistry, AccountWalletMapping

# ── Test credentials — only for local verification ───────────────────────────
TEST_ASE_NAME      = "TEST_ASE_01"
TEST_API_KEY       = "test-api-key-12345"
TEST_ACCOUNT       = "9800000001"        # DE103 destination account
TEST_WALLET        = "https://rafiki.example.com/accounts/test-wallet-001"

def seed():
    from app.db import get_session_local
    SessionLocal = get_session_local()
    db = SessionLocal()
    try:
        # ── Remove existing test data ─────────────────────────────────────────
        db.query(AseRegistry).filter(
            AseRegistry.ase_name == TEST_ASE_NAME
        ).delete()
        db.query(AccountWalletMapping).filter(
            AccountWalletMapping.ase_name == TEST_ASE_NAME
        ).delete()
        db.commit()

        # ── Insert ASE registry entry ─────────────────────────────────────────
        api_key_hash = bcrypt.hashpw(
            TEST_API_KEY.encode(), bcrypt.gensalt()
        ).decode()

        ase = AseRegistry(
            ase_name=TEST_ASE_NAME,
            api_key_hash=api_key_hash,
            active=True,
            max_connections=50,
            frame_length_type=2,
        )
        db.add(ase)

        # ── Insert wallet mapping ─────────────────────────────────────────────
        mapping = AccountWalletMapping(
            ase_name=TEST_ASE_NAME,
            account_number=TEST_ACCOUNT,
            wallet_address=TEST_WALLET,
            active=True,
        )
        db.add(mapping)
        db.commit()

        print("✓ ASE registered:")
        print(f"    ase_name         : {TEST_ASE_NAME}")
        print(f"    api_key          : {TEST_API_KEY}")
        print(f"    frame_length_type: 2")
        print()
        print("✓ Wallet mapping inserted:")
        print(f"    account_number   : {TEST_ACCOUNT}")
        print(f"    wallet_address   : {TEST_WALLET}")
        print()
        print("Ready — run scripts/tcp_test_client.py")

    except Exception as e:
        db.rollback()
        print(f"✗ Seed failed: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()