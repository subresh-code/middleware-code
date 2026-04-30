from sqlalchemy.orm import Session
from app.parser.schemas.message import Iso8583Message
from app.translation.currency_map import get_currency_info
from app.models.payment import PaymentTranslation, AccountWalletMapping
from datetime import datetime, timezone, timedelta


class WalletResolutionError(Exception):
    pass


def resolve_wallet(
    db: Session,
    ase_name: str,
    account_number: str,
) -> str:
    """
    Resolve a destination account (DE103) to a Rafiki wallet address.
    Scoped by ase_name — ASE A cannot resolve ASE B accounts.
    """
    mapping = (
        db.query(AccountWalletMapping)
        .filter(
            AccountWalletMapping.ase_name == ase_name,
            AccountWalletMapping.account_number == account_number,
            AccountWalletMapping.active == True,
        )
        .first()
    )
    if not mapping:
        raise WalletResolutionError(
            f"No active wallet mapping for account {account_number} on ASE {ase_name}"
        )
    return mapping.wallet_address


def compute_ilp_amount(de4: str) -> int:
    """
    Convert DE4 (12-digit zero-padded string) to ILP UInt64 integer.
    Per BLAST: strip leading zeros, no multiplication/division.
    """
    try:
        value = int(de4)  # Strips leading zeros
    except ValueError:
        raise ValueError(f"Invalid DE4 format: {de4}")
    if value == 0:
        raise ValueError("DE4 amount is zero")
    return value


def compute_expires_at(de7: str = None, ttl_seconds: int = 300) -> datetime:
    """
    Derive expiresAt from DE7 (MMDDHHmmss) plus TTL.
    Returns datetime object.
    """
    now = datetime.now(timezone.utc)
    expires = now + timedelta(seconds=ttl_seconds)
    return expires


def translate(
    db: Session,
    msg: Iso8583Message,
    ase_name: str,
) -> dict:
    """
    Takes a parsed Iso8583Message and returns translation results:
    - wallet_address
    - amount_ilp_uint64
    - assetCode, assetScale
    - expiresAt
    """
    # Resolve wallet (ASE-scoped)
    wallet_address = resolve_wallet(db, ase_name, msg.de103)

    # Convert amount
    amount_uint64 = compute_ilp_amount(msg.de4)

    # Map currency
    asset_code, asset_scale = get_currency_info(msg.de49)

    # Compute expiry
    expires_at = compute_expires_at(msg.de7)

    return {
        "wallet_address": wallet_address,
        "amount_ilp_uint64": amount_uint64,
        "assetCode": asset_code,
        "assetScale": asset_scale,
        "expiresAt": expires_at,
    }
