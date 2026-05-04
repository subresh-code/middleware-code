"""
Handler for 0400 Reversal messages.
"""
import logging
from sqlalchemy.orm import Session
from app.models.payment import PaymentTranslation, PaymentStatus
from app.state.machine import transition_payment, TriggeredBy
from app.clients.rafiki_client import RafikiClient
from app.server.tcp import TcpServer

logger = logging.getLogger(__name__)


async def handle_0400(
    self: TcpServer,
    db: Session,
    msg,
    ase_name: str,
    frame_length_type: int,
    writer,
):
    """Handle 0400 Reversal request."""
    # Look up original 0200 by STAN (DE11) + RRN (DE37)
    original = (
        db.query(PaymentTranslation)
        .filter(
            PaymentTranslation.ase_name == ase_name,
            PaymentTranslation.stan == msg.de11,
            PaymentTranslation.rrn == msg.de37,
            PaymentTranslation.mti == "0200",
        )
        .order_by(PaymentTranslation.created_at.desc())
        .first()
    )
    if not original:
        logger.warning(
            "ASE '%s' reversal for unknown STAN=%s RRN=%s",
            ase_name, msg.de11, msg.de37,
        )
        writer.write(self._make_error_response("0400", "25", msg.de11, frame_length_type))
        await writer.drain()
        return

    if original.status in (PaymentStatus.SETTLED, PaymentStatus.NOTIFIED):
        # Already settled — cannot reverse at middleware layer
        writer.write(self._make_error_response("0400", "39", msg.de11, frame_length_type))
        await writer.drain()
        return

    if original.status == PaymentStatus.FAILED:
        # Already failed, reversal not needed
        writer.write(self._make_error_response("0400", "00", msg.de11, frame_length_type))
        await writer.drain()
        return

    # If Rafiki payment was created, attempt to cancel it
    if original.rafiki_payment_id:
        try:
            rafiki = RafikiClient()
            await rafiki.cancel_outgoing_payment(original.rafiki_payment_id)
        except Exception as e:
            logger.warning(
                "Could not cancel Rafiki payment %s: %s",
                original.rafiki_payment_id, e,
            )

    # Mark original as reversed (FAILED with reason)
    try:
        transition_payment(
            db, original.id, PaymentStatus.FAILED,
            TriggeredBy.ASE_INBOUND,
            "Reversed by 0400 reversal request",
        )
        original.response_code = "00"
        db.commit()
    except InvalidTransitionError:
        writer.write(self._make_error_response("0400", "39", msg.de11, frame_length_type))
        await writer.drain()
        return

    writer.write(self._make_error_response("0400", "00", msg.de11, frame_length_type))
    await writer.drain()
