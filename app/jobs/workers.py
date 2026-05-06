import logging
from sqlalchemy.orm import Session
from app.db import SessionLocal
from app.models.payment import PaymentTranslation, PaymentStatus, SettlementBatch, BatchStatus
from datetime import datetime, timezone
from app.config import get_settings

settings = get_settings()

logger = logging.getLogger(__name__)

def submit_batch_to_connectips(batch: SettlementBatch) -> bool:
    """
    Mock submission to ConnectIPS.
    In production, this would be an API call.
    """
    logger.info("Submitting batch %d for %s to ConnectIPS...", batch.id, batch.ase_name)
    # Simulate success
    return True

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
            logger.info("No payments to settle")
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

            # ── Submit batch before marking payments as settled ──
            if submit_batch_to_connectips(batch):
                batch.status = BatchStatus.SUBMITTED
                for p in ase_payments:
                    p.settlement_batch_id = batch.id
                    p.status = PaymentStatus.SETTLED
                logger.info("Batch %d submitted and payments settled for %s", batch.id, ase_name)
            else:
                batch.status = BatchStatus.FAILED
                logger.error("Failed to submit batch %d for %s", batch.id, ase_name)

            db.commit()

    except Exception as e:
        db.rollback()
        logger.exception("Settlement job failed: %s", e)
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
