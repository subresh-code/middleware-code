from sqlalchemy.orm import Session
from app.db import SessionLocal
from app.models.payment import (
    PaymentTranslation, PaymentStatus, SettlementBatch, BatchStatus,
    DeadLetter,
)
from datetime import datetime, timezone, timedelta
from app.config import settings
from app.state.machine import transition_payment, TriggeredBy, InvalidTransitionError
from app.server.tcp import tcp_server


def run_settlement_job():
    """
    Scheduled job: Aggregates FULFILLED payments and creates settlement batches.
    Per BLAST: runs end of day, max 1000 payments per batch.
    """
    db = SessionLocal()
    try:
        # Get all ILP_FULFILLED payments not in a batch
        payments = (
            db.query(PaymentTranslation)
            .filter(
                PaymentTranslation.status == PaymentStatus.ILP_FULFILLED,
                PaymentTranslation.settlement_batch_id == None,
            )
            .limit(1000)
            .all()
        )

        if not payments:
            print("No payments to settle")
            return

        # Group by ASE
        by_ase = {}
        for p in payments:
            by_ase.setdefault(p.ase_name, []).append(p)

        for ase_name, ase_payments in by_ase.items():
            total = sum(p.amount_value or 0 for p in ase_payments)

            batch = SettlementBatch(
                ase_name=ase_name,
                total_amount=total,
                payment_count=len(ase_payments),
                status=BatchStatus.PENDING,
            )
            db.add(batch)
            db.flush()

            for p in ase_payments:
                p.settlement_batch_id = batch.id
                p.status = PaymentStatus.SETTLED

            db.commit()
            print(f"Created settlement batch {batch.id} for {ase_name}: {len(ase_payments)} payments")

            # Push settlement notification to ASE via TCP
            try:
                # Build minimal notification: batch ID and total amount
                notification = f"SETTLEMENT|{batch.id}|{batch.total_amount}|{batch.payment_count}".encode()
                # Send to all active connections for this ASE
                # Note: In production, store pending notifications and push when ASE connects
                print(f"Settlement notification for ASE '{ase_name}': batch {batch.id} ready")
                # TCP push would require storing writer references per ASE
                # For now, log the notification
            except Exception as e:
                print(f"Failed to notify ASE '{ase_name}' of settlement: {e}")

    except Exception as e:
        db.rollback()
        print(f"Settlement job failed: {e}")
    finally:
        db.close()


def cleanup_stale_payments():
    """
    Cleanup job: Find ILP_PREPARED payments past expiry and mark as FAILED.
    """
    db = SessionLocal()
    try:
        from app.state.machine import transition_payment, TriggeredBy

        now = datetime.now(timezone.utc)
        stale = (
            db.query(PaymentTranslation)
            .filter(
                PaymentTranslation.status == PaymentStatus.ILP_PREPARED,
                PaymentTranslation.expires_at < now,
            )
            .all()
        )

        for payment in stale:
            try:
                transition_payment(
                    db, payment.id, PaymentStatus.FAILED,
                    TriggeredBy.SYSTEM, "ILP packet expired"
                )
            except Exception as e:
                print(f"Failed to transition payment {payment.id}: {e}")

        if stale:
            print(f"Cleaned up {len(stale)} stale payments")

    except Exception as e:
        print(f"Cleanup job failed: {e}")
    finally:
        db.close()


def retry_dead_letter_payments():
    """
    Scheduled job: Retry payments that have failed but are eligible for retry.
    Moves payments to dead_letter table if retry_count exceeded.
    """
    db = SessionLocal()
    try:
        from app.server.tcp import tcp_server
        from app.clients.rafiki_client import RafikiClient
        from app.translation.core import translate
        from app.parser.iso8583 import parse_iso8583

        # Find FAILED payments with retry_count < 3 and next_retry_at <= now
        now = datetime.now(timezone.utc)
        retryable = (
            db.query(PaymentTranslation)
            .filter(
                PaymentTranslation.status == PaymentStatus.FAILED,
                PaymentTranslation.retry_count < 3,
                (PaymentTranslation.next_retry_at == None) | (PaymentTranslation.next_retry_at <= now),
            )
            .limit(50)
            .all()
        )

        rafiki = RafikiClient()
        for payment in retryable:
            try:
                # Re-attempt: re-parse raw_message and retry translation
                msg = parse_iso8583(
                    bytes.fromhex(payment.raw_message),
                    frame_length_type=2,  # Default, could be from ASE registry
                )

                result = translate(db, msg, payment.ase_name, settings.payment_ttl_seconds)

                # Retry Rafiki calls
                rafiki.get_wallet_address(result.wallet_address)
                incoming = rafiki.create_incoming_payment(
                    wallet_address=result.wallet_address,
                    amount_ilp_uint64=result.amount_ilp_uint64,
                    asset_code=result.asset_code,
                    asset_scale=result.asset_scale,
                    expires_at=result.expires_at.isoformat(),
                    external_ref=payment.stan,
                )
                incoming_id = (
                    incoming.get("data", {})
                    .get("createReceiver", {})
                    .get("receiver", {})
                    .get("id")
                )
                outgoing = rafiki.create_outgoing_payment(
                    wallet_address=result.source_wallet_address,
                    incoming_payment_url=incoming_id,
                    amount_ilp_uint64=result.amount_ilp_uint64,
                    asset_code=result.asset_code,
                    asset_scale=result.asset_scale,
                    stan=payment.stan,
                )

                payment.rafiki_payment_id = str(outgoing)
                payment.retry_count = 0
                payment.next_retry_at = None
                transition_payment(
                    db, payment.id, PaymentStatus.ILP_PREPARED,
                    TriggeredBy.SYSTEM, "Retry successful"
                )
                print(f"Retried payment {payment.id} (STAN={payment.stan}) — success")

            except Exception as e:
                payment.retry_count += 1
                if payment.retry_count >= 3:
                    # Move to dead-letter
                    dl = DeadLetter(
                        payment_id=payment.id,
                        ase_name=payment.ase_name,
                        stan=payment.stan,
                        rrn=payment.rrn,
                        failure_reason=str(e),
                        error_type="RETRY_EXCEEDED",
                    )
                    db.add(dl)
                    print(f"Payment {payment.id} moved to dead-letter after {payment.retry_count} retries")
                else:
                    # Exponential backoff: 1min, 5min, 15min
                    backoff_minutes = [1, 5, 15][payment.retry_count - 1]
                    payment.next_retry_at = now + timedelta(minutes=backoff_minutes)
                    print(f"Payment {payment.id} retry {payment.retry_count}/3 scheduled for {payment.next_retry_at}")

                db.commit()

    except Exception as e:
        db.rollback()
        print(f"Dead-letter retry job failed: {e}")
    finally:
        db.close()
