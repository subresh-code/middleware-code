"""
Handler for 0200 Payment messages.
"""
import asyncio
import logging
from sqlalchemy.orm import Session
from app.models.payment import PaymentTranslation, PaymentStatus
from app.state.machine import transition_payment, TriggeredBy
from app.translation.core import translate
from app.clients.rafiki_client import RafikiClient
from app.state.pending import pending_payments
from app.server.tcp import TcpServer

logger = logging.getLogger(__name__)


async def handle_0200(
    self: TcpServer,
    db: Session,
    msg,
    ase_name: str,
    settings,
    frame_length_type: int,
    writer,
):
    """Handle 0200 Payment request with full Rafiki integration."""
    try:
        # ── STAN Idempotency Check ────────────────────────
        existing = (
            db.query(PaymentTranslation)
            .filter(
                PaymentTranslation.ase_name == ase_name,
                PaymentTranslation.stan == msg.de11,
                PaymentTranslation.mti == "0200",
            )
            .order_by(PaymentTranslation.created_at.desc())
            .first()
        )
        if existing:
            logger.warning(
                "ASE '%s' duplicate STAN=%s — returning prior response",
                ase_name, msg.de11,
            )
            writer.write(self._make_error_response(
                msg.mti, "94", msg.de11, frame_length_type))
            await writer.drain()
            return

        # Create payment record with raw fields only
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

        # Transition to TRANSLATING
        transition_payment(
            db, payment.id,
            PaymentStatus.TRANSLATING,
            TriggeredBy.ASE_INBOUND,
            "Received from ASE",
        )

        # Run translation
        result = translate(db, msg, ase_name, settings.payment_ttl_seconds)

        # Update payment with translation results
        payment.wallet_address = result.wallet_address
        payment.amount_ilp_uint64 = result.amount_ilp_uint64
        payment.amount_value = result.amount_ilp_uint64 / (10 ** result.asset_scale)
        payment.expires_at = result.expires_at
        db.commit()

        # Transition to TRANSLATED
        transition_payment(
            db, payment.id,
            PaymentStatus.TRANSLATED,
            TriggeredBy.TRANSLATION_JOB,
            "Translation complete",
        )

        # ── Rafiki Integration: Create Incoming Payment ──
        rafiki = RafikiClient()
        try:
            await rafiki.get_wallet_address(result.wallet_address)
        except Exception as e:
            logger.error("Wallet not found for 0200: %s", e)
            transition_payment(
                db, payment.id, PaymentStatus.FAILED,
                TriggeredBy.SYSTEM, f"Wallet not found: {e}"
            )
            writer.write(self._make_error_response(msg.mti, "14", msg.de11, frame_length_type))
            await writer.drain()
            return

        try:
            incoming = await rafiki.create_incoming_payment(
                wallet_address=result.wallet_address,
                amount_value=result.amount_ilp_uint64,
                asset_code=result.asset_code,
                asset_scale=result.asset_scale,
                expires_at=result.expires_at.isoformat(),
                external_ref=msg.de11,
            )
        except Exception as e:
            logger.error("0200 incoming payment failed: %s", e)
            transition_payment(
                db, payment.id, PaymentStatus.FAILED,
                TriggeredBy.SYSTEM, f"Rafiki incoming payment failed: {e}"
            )
            writer.write(self._make_error_response(msg.mti, "96", msg.de11, frame_length_type))
            await writer.drain()
            return

        payment.rafiki_payment_id = str(incoming)
        db.commit()
        transition_payment(
            db, payment.id, PaymentStatus.ILP_PREPARED,
            TriggeredBy.TRANSLATION_JOB,
            "Incoming payment created",
        )

        # ── Create Quote ───────────────────────────────────────────
        try:
            await rafiki.create_quote(
                wallet_address=result.wallet_address,
                incoming_payment_url=payment.rafiki_payment_id,
                amount_value=result.amount_ilp_uint64,
                asset_code=result.asset_code,
                asset_scale=result.asset_scale,
            )
        except Exception as e:
            logger.error("0200 quote creation failed: %s", e)
            transition_payment(
                db, payment.id, PaymentStatus.FAILED,
                TriggeredBy.SYSTEM, f"Rafiki quote failed: {e}"
            )
            writer.write(self._make_error_response(msg.mti, "96", msg.de11, frame_length_type))
            await writer.drain()
            return

        # ── Create Outgoing Payment (ILP Transfer) ───────────────
        try:
            outgoing = await rafiki.create_outgoing_payment(
                wallet_address=result.wallet_address,
                incoming_payment_url=payment.rafiki_payment_id,
                amount_value=result.amount_ilp_uint64,
                asset_code=result.asset_code,
                asset_scale=result.asset_scale,
                stan=msg.de11,
            )
        except Exception as e:
            logger.error("0200 outgoing payment failed: %s", e)
            transition_payment(
                db, payment.id, PaymentStatus.FAILED,
                TriggeredBy.SYSTEM, f"Rafiki outgoing payment failed: {e}"
            )
            writer.write(self._make_error_response(msg.mti, "96", msg.de11, frame_length_type))
            await writer.drain()
            return

        # ── Deposit Liquidity (Funding) ──────────────────────────
        try:
            # We use the outgoing payment ID returned by Rafiki
            outgoing_id = outgoing.get("id") or outgoing.get("url")
            await rafiki.deposit_outgoing_payment_liquidity(outgoing_id)
        except Exception as e:
            logger.error("0200 liquidity deposit failed: %s", e)
            transition_payment(
                db, payment.id, PaymentStatus.FAILED,
                TriggeredBy.SYSTEM, f"Rafiki funding failed: {e}"
            )
            writer.write(self._make_error_response(msg.mti, "96", msg.de11, frame_length_type))
            await writer.drain()
            return

        # ── Check if Rafiki already completed before we stored the event ──
        # (race condition: webhook arrived between create_outgoing_payment and here)
        db.refresh(payment)
        if payment.status == PaymentStatus.ILP_FULFILLED:
            # Webhook already fired and transitioned — no need to wait
            payment.response_code = "00"
            db.commit()
            writer.write(self._make_error_response(msg.mti, "00", msg.de11, frame_length_type))
        elif payment.status == PaymentStatus.ILP_REJECTED:
            transition_payment(
                db, payment.id, PaymentStatus.FAILED,
                TriggeredBy.SYSTEM, "ILP rejected before event wait"
            )
            payment.response_code = "05"
            db.commit()
            writer.write(self._make_error_response(msg.mti, "05", msg.de11, frame_length_type))
        else:
            # Normal path — store event and wait
            event = asyncio.Event()
            pending_payments[msg.de11] = event
            try:
                await asyncio.wait_for(event.wait(), timeout=30.0)
            except asyncio.TimeoutError:
                transition_payment(
                    db, payment.id, PaymentStatus.FAILED,
                    TriggeredBy.SYSTEM, "Webhook timeout after 30s"
                )
                payment.response_code = "68"
                db.commit()
                writer.write(self._make_error_response(msg.mti, "68", msg.de11, frame_length_type))
                await writer.drain()
                return
            finally:
                pending_payments.pop(msg.de11, None)

            db.refresh(payment)
            if payment.status == PaymentStatus.ILP_FULFILLED:
                payment.response_code = "00"
                db.commit()
                writer.write(self._make_error_response(msg.mti, "00", msg.de11, frame_length_type))
            else:
                payment.response_code = "05"
                db.commit()
                writer.write(self._make_error_response(msg.mti, "05", msg.de11, frame_length_type))

        await writer.drain()

    except WalletResolutionError as e:
        logger.warning("Wallet not found for ASE '%s': %s", ase_name, e)
        db.rollback()
        if 'payment' in locals() and payment.id:
            try:
                transition_payment(
                    db, payment.id,
                    PaymentStatus.FAILED,
                    TriggeredBy.SYSTEM,
                    str(e),
                )
                            except Exception:
                                logger.exception("Critical failure during payment FAILED transition")
        writer.write(self._make_error_response(msg.mti, "14", msg.de11, frame_length_type))
        await writer.drain()
    except (InvalidTransitionError, ValueError) as e:
        logger.error("Payment processing error for ASE '%s': %s", ase_name, e)
        db.rollback()
        if 'payment' in locals() and payment.id:
            try:
                transition_payment(
                    db, payment.id,
                    PaymentStatus.FAILED,
                    TriggeredBy.SYSTEM,
                    str(e),
                )
                            except Exception:
                                logger.exception("Critical failure during payment FAILED transition")
        writer.write(self._make_error_response(msg.mti, "96", msg.de11, frame_length_type))
        await writer.drain()
