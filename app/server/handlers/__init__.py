"""
Handler for 0100 Pre-Authorization messages.
"""
import logging
from sqlalchemy.orm import Session
from app.models.payment import PaymentTranslation, PaymentStatus
from app.state.machine import transition_payment, TriggeredBy
from app.translation.core import translate, WalletResolutionError
from app.clients.rafiki_client import RafikiClient
from app.server.tcp import TcpServer

logger = logging.getLogger(__name__)


async def handle_0100(
    self: TcpServer,
    db: Session,
    msg,
    ase_name: str,
    settings,
    frame_length_type: int,
    writer,
):
    """Handle 0100 Pre-Authorization request."""
    try:
        # ── STAN Idempotency Check ────────────────────
        existing = (
            db.query(PaymentTranslation)
            .filter(
                PaymentTranslation.ase_name == ase_name,
                PaymentTranslation.stan == msg.de11,
                PaymentTranslation.mti == "0100",
            )
            .order_by(PaymentTranslation.created_at.desc())
            .first()
        )
        if existing:
            logger.warning(
                "ASE '%s' duplicate STAN=%s (pre-auth) — returning prior response",
                ase_name, msg.de11,
            )
            writer.write(self._make_error_response(
                msg.mti, "94", msg.de11, frame_length_type))
            await writer.drain()
            return

        payment = PaymentTranslation(
            ase_name=ase_name,
            raw_message=msg.raw_hex,
            mti=msg.mti,
            status=PaymentStatus.RECEIVED,
            currency=msg.de49,
            stan=msg.de11,
            rrn=msg.de37,
            processing_code=msg.de3,
            terminal_id=msg.de41,
        )
        db.add(payment)
        db.commit()
        db.refresh(payment)

        transition_payment(
            db, payment.id,
            PaymentStatus.TRANSLATING,
            TriggeredBy.ASE_INBOUND,
            "Pre-auth received from ASE",
        )

        result = translate(db, msg, ase_name, settings.payment_ttl_seconds)
        payment.wallet_address = result.wallet_address
        payment.amount_ilp_uint64 = result.amount_ilp_uint64
        payment.amount_value = result.amount_ilp_uint64 / (10 ** result.asset_scale)
        payment.expires_at = result.expires_at
        db.commit()

        transition_payment(
            db, payment.id,
            PaymentStatus.TRANSLATED,
            TriggeredBy.TRANSLATION_JOB,
            "Pre-auth translation complete",
        )

        rafiki = RafikiClient()
        try:
            await rafiki.get_wallet_address(result.wallet_address)
        except Exception as e:
            logger.error("Wallet not found for pre-auth: %s", e)
            transition_payment(
                db, payment.id, PaymentStatus.FAILED,
                TriggeredBy.SYSTEM, f"Wallet not found: {e}"
            )
            writer.write(self._make_error_response("0100", "14", msg.de11, frame_length_type))
            await writer.drain()
            return

        try:
            incoming = await rafiki.create_incoming_payment(
                wallet_address=result.wallet_address,
                amount_ilp_uint64=result.amount_ilp_uint64,
                asset_code=result.asset_code,
                asset_scale=result.asset_scale,
                expires_at=result.expires_at.isoformat(),
                external_ref=msg.de11,
            )
        except Exception as e:
            logger.error("Pre-auth incoming payment failed: %s", e)
            transition_payment(
                db, payment.id, PaymentStatus.FAILED,
                TriggeredBy.SYSTEM, f"Rafiki incoming payment failed: {e}"
            )
            writer.write(self._make_error_response("0100", "96", msg.de11, frame_length_type))
            await writer.drain()
            return

        payment.rafiki_payment_id = str(incoming)
        db.commit()
        transition_payment(
            db, payment.id, PaymentStatus.ILP_PREPARED,
            TriggeredBy.TRANSLATION_JOB,
            "Pre-auth: incoming payment created (funds reserved)",
        )

        # Pre-auth does NOT create outgoing payment
        # Check if Rafiki already completed before we stored the event
        # (race condition: webhook arrived between create_incoming_payment and here)
        db.refresh(payment)
        if payment.status == PaymentStatus.ILP_FULFILLED:
            # Webhook already fired and transitioned — no need to wait
            payment.response_code = "00"
            db.commit()
            writer.write(self._make_error_response("0100", "00", msg.de11, frame_length_type))
        elif payment.status == PaymentStatus.ILP_REJECTED:
            # Webhook already fired and rejected
            transition_payment(
                db, payment.id, PaymentStatus.FAILED,
                TriggeredBy.SYSTEM, "ILP rejected before event wait"
            )
            payment.response_code = "05"
            db.commit()
            writer.write(self._make_error_response("0100", "05", msg.de11, frame_length_type))
        else:
            # Normal path — store event and wait
            from app.state.pending import pending_payments
            event = asyncio.Event()
            pending_payments[msg.de11] = event
            try:
                await asyncio.wait_for(event.wait(), timeout=30.0)
            except asyncio.TimeoutError:
                transition_payment(
                    db, payment.id, PaymentStatus.FAILED,
                    TriggeredBy.SYSTEM, "Pre-auth webhook timeout"
                )
                payment.response_code = "68"
                db.commit()
                writer.write(self._make_error_response("0100", "68", msg.de11, frame_length_type))
                await writer.drain()
                return
            finally:
                pending_payments.pop(msg.de11, None)

            db.refresh(payment)
            if payment.status == PaymentStatus.ILP_FULFILLED:
                payment.response_code = "00"
                db.commit()
                writer.write(self._make_error_response("0100", "00", msg.de11, frame_length_type))
            else:
                payment.response_code = "05"
                db.commit()
                writer.write(self._make_error_response("0100", "05", msg.de11, frame_length_type))

        await writer.drain()

    except WalletResolutionError as e:
        logger.warning("Wallet not found for ASE '%s': %s", ase_name, e)
        db.rollback()
        writer.write(self._make_error_response("0100", "14", msg.de11, frame_length_type))
        await writer.drain()
    except (InvalidTransitionError, ValueError) as e:
        logger.error("Pre-auth error for ASE '%s': %s", ase_name, e)
        db.rollback()
        writer.write(self._make_error_response("0100", "96", msg.de11, frame_length_type))
        await writer.drain()
