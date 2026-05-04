"""
Handler for Balance Inquiry (DE3 starts with "31").
"""
import asyncio
import logging
from sqlalchemy.orm import Session
from app.models.payment import PaymentTranslation, PaymentStatus
from app.state.machine import transition_payment, TriggeredBy
from app.translation.core import resolve_wallet, WalletResolutionError
from app.clients.rafiki_client import RafikiClient
from app.server.tcp import TcpServer

logger = logging.getLogger(__name__)


async def handle_balance_inquiry(
    self: TcpServer,
    db: Session,
    msg,
    ase_name: str,
    frame_length_type: int,
    writer,
):
    """Handle balance inquiry request."""
    try:
        # Resolve wallet from DE103 (destination account)
        wallet_address = resolve_wallet(db, ase_name, msg.de103)
        rafiki = RafikiClient()

        # Query Rafiki for wallet balance via GraphQL
        query = {
            "query": """
                query GetWalletBalance($url: String!) {
                    walletAddressByUrl(url: $url) {
                        id
                        asset {
                            code
                            scale
                        }
                        balance
                    }
                }
            """,
            "variables": {"url": wallet_address}
        }
        # Wrap sync requests call in executor to avoid blocking event loop
        loop = asyncio.get_running_loop()
        resp = await loop.run_in_executor(
            None,
            lambda: rafiki._request_with_retry("POST", "/graphql", json=query)
        )
        data = resp.json()

        wallet_data = data.get("data", {}).get("walletAddressByUrl")
        if not wallet_data:
            writer.write(self._make_error_response(msg.mti, "14", msg.de11, frame_length_type))
            await writer.drain()
            return

        # Build response with balance in DE4
        # Balance is in UInt64 format (smallest unit), use directly for DE4
        balance_raw = int(wallet_data.get("balance", 0))
        de4_balance = f"{balance_raw:012d}"

        response_fields = {
            "39": "00",
            "11": msg.de11,
            "4": de4_balance,
        }
        response_mti = "0210" if msg.mti == "0200" else "0110"
        try:
            balance_response = encode_iso8583_response(
                mti=response_mti,
                fields=response_fields,
                header_len=frame_length_type,
            )
            writer.write(balance_response)
        except Exception:
            writer.write(self._make_error_response(msg.mti, "96", msg.de11, frame_length_type))

    except WalletResolutionError as e:
        logger.warning("Balance inquiry wallet not found: %s", e)
        writer.write(self._make_error_response(msg.mti, "14", msg.de11, frame_length_type))
    except Exception as e:
        logger.error("Balance inquiry error: %s", e)
        writer.write(self._make_error_response(msg.mti, "96", msg.de11, frame_length_type))

    await writer.drain()
