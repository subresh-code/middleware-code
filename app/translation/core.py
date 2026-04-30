from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.models.payment import AccountWalletMapping
from app.parser.schemas.message import Iso8583Message
from app.translation.currency_map import get_currency_info

MAX_TTL_SECONDS = 300


class WalletResolutionError(Exception):
    pass


@dataclass(frozen=True)
class TranslationResult:
    wallet_address: str
    amount_ilp_uint64: int
    asset_code: str
    asset_scale: int
    expires_at: str  # ISO 8601 UTC string


def resolve_wallet(db: Session, ase_name: str, account_number: str) -> str:
    """
    Resolve DE103 to a Rafiki wallet address.
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
            f"No active wallet mapping for account '{account_number}' "
            f"under ASE '{ase_name}'"
        )
    return mapping.wallet_address


def compute_ilp_amount(de4: str) -> int:
    """
    Convert DE4 (12-digit zero-padded string) to ILP UInt64.
    Strip leading zeros only — no multiplication, no division.
    """
    if len(de4) != 12 or not de4.isdigit():
        raise ValueError(f"DE4 must be exactly 12 numeric characters, got: '{de4}'")
    value = int(de4)
    if value == 0:
        raise ValueError("DE4 amount resolves to zero")
    return value


def compute_expires_at(de7: Optional[str], ttl_seconds: int = MAX_TTL_SECONDS) -> str:
    """
    Derive expiresAt from DE7 (MMDDHHmmss) plus TTL.
    Returns ISO 8601 UTC string. Always in the future at time of creation.
    """
    if ttl_seconds > MAX_TTL_SECONDS:
        raise ValueError(
            f"TTL {ttl_seconds}s exceeds maximum of {MAX_TTL_SECONDS}s"
        )

    now = datetime.now(timezone.utc)

    if de7 and len(de7) == 10:
        try:
            month  = int(de7[0:2])
            day    = int(de7[2:4])
            hour   = int(de7[4:6])
            minute = int(de7[6:8])
            second = int(de7[8:10])
            base = now.replace(
                month=month, day=day,
                hour=hour, minute=minute,
                second=second, microsecond=0
            )
        except (ValueError, OverflowError):
            base = now
    else:
        base = now

    return (base + timedelta(seconds=ttl_seconds)).isoformat()


def translate(
    db: Session,
    msg: Iso8583Message,
    ase_name: str,
    ttl_seconds: int = MAX_TTL_SECONDS,
) -> TranslationResult:
    """
    Translate a parsed Iso8583Message into an ILP-ready TranslationResult.
    Wallet lookup is scoped to ase_name — no cross-ASE resolution possible.
    """
    wallet_address = resolve_wallet(db, ase_name, msg.de103)
    amount_ilp_uint64 = compute_ilp_amount(msg.de4)
    currency = get_currency_info(msg.de49)
    expires_at = compute_expires_at(msg.de7, ttl_seconds)

    return TranslationResult(
        wallet_address=wallet_address,
        amount_ilp_uint64=amount_ilp_uint64,
        asset_code=currency.asset_code,
        asset_scale=currency.asset_scale,
        expires_at=expires_at,
    )
