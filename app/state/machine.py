from datetime import datetime, timezone

from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.payment import AuditLog, PaymentStatus, PaymentTranslation, TriggeredBy


class InvalidTransitionError(Exception):
    pass


VALID_TRANSITIONS: dict[PaymentStatus, set[PaymentStatus]] = {
    PaymentStatus.RECEIVED:     {PaymentStatus.TRANSLATING, PaymentStatus.FAILED},
    PaymentStatus.TRANSLATING:  {PaymentStatus.TRANSLATED, PaymentStatus.FAILED},
    PaymentStatus.TRANSLATED:   {PaymentStatus.ILP_PREPARED, PaymentStatus.FAILED},
    PaymentStatus.ILP_PREPARED: {PaymentStatus.ILP_FULFILLED, PaymentStatus.ILP_REJECTED, PaymentStatus.FAILED},
    PaymentStatus.ILP_FULFILLED:{PaymentStatus.NOTIFIED, PaymentStatus.FAILED},
    PaymentStatus.ILP_REJECTED: {PaymentStatus.FAILED},
    PaymentStatus.NOTIFIED:     {PaymentStatus.SETTLED, PaymentStatus.FAILED},
    PaymentStatus.SETTLED:      set(),
    PaymentStatus.FAILED:       set(),
}

TERMINAL_STATES = {PaymentStatus.SETTLED, PaymentStatus.FAILED}


def transition_payment(
    db: Session,
    payment_id: int,
    to_status: PaymentStatus,
    triggered_by: TriggeredBy,
    metadata: str = None,
) -> PaymentTranslation:
    """
    Atomically transition a payment to a new status.

    - Acquires a pessimistic row lock (nowait) — concurrent attempt raises immediately
    - Creates exactly one audit_log entry per transition
    - Rolls back both status change and audit entry if commit fails
    - Raises InvalidTransitionError for illegal transitions or lock contention
    """
    # ── Acquire row lock — fail immediately if another transaction holds it ──
    try:
        payment = (
            db.query(PaymentTranslation)
            .filter(PaymentTranslation.id == payment_id)
            .with_for_update(nowait=True)
            .first()
        )
    except OperationalError:
        raise InvalidTransitionError(
            f"Payment {payment_id} is locked by another transaction — "
            f"concurrent transition rejected"
        )

    if not payment:
        raise ValueError(f"Payment {payment_id} not found")

    from_status = payment.status

    # ── Guard: terminal states never transition ────────────────────────
    if from_status in TERMINAL_STATES:
        raise InvalidTransitionError(
            f"Payment {payment_id} is in terminal state {from_status.value} — "
            f"no further transitions allowed"
        )

    # ── Guard: only allowed transitions per spec ──────────────────────────
    if to_status not in VALID_TRANSITIONS.get(from_status, set()):
        raise InvalidTransitionError(
            f"Invalid transition for payment {payment_id}: "
            f"{from_status.value} → {to_status.value}"
        )

    # ── Atomic write: status + audit in one transaction ──────────────────
    try:
        payment.status = to_status
        payment.updated_at = datetime.now(timezone.utc)

        audit = AuditLog(
            payment_id=payment.id,
            from_status=from_status if from_status != PaymentStatus.RECEIVED else None,
            to_status=to_status,
            triggered_by=triggered_by,
            meta_data=metadata,
        )
        db.add(audit)
        db.commit()
        db.refresh(payment)
        return payment

    except SQLAlchemyError:
        db.rollback()
        raise
