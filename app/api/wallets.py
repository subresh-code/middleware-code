"""
Wallet mapping endpoints.
"""
from fastapi import APIRouter

router = APIRouter()

from app.rafiki_client import COOP_WALLET_MAPPING


@router.get("/wallets", tags=["wallets"])
def list_wallet_mappings():
    """List all cooperative to wallet URL mappings."""
    return COOP_WALLET_MAPPING
