from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from app.models.payment import (
    PaymentTranslation, PaymentStatus, TriggeredBy, AuditLog
)
from datetime import datetime, timezone


class InvalidTransitionError(Exception):
    pass


# Valid transitions per BLAST.md
VALID_TRANSITIONS = {
    PaymentStatus.RECEIVED:    {PaymentStatus.TRANSLATING, PaymentStatus.FAILED},
    PaymentStatus.TRANSLATING:  {PaymentStatus.TRANSLATED, PaymentStatus.FAILED},
    PaymentStatus.TRANSLATED:   {PaymentStatus.ILP_PREPARED, PaymentStatus.FAILED},
    PaymentStatus.ILP_PREPARED: {PaymentStatus.ILP_FULFILLED, PaymentStatus.ILP_REJECTED, PaymentStatus.FAILED},
    PaymentStatus.ILP_FULFILLED:{PaymentStatus.NOTIFIED, PaymentStatus.FAILED},
    PaymentStatus.ILP_REJECTED: {PaymentStatus.FAILED},
    PaymentStatus.NOTIFIED:     {PaymentStatus.SETTLED, PaymentStatus.FAILED},
    PaymentStatus.SETTLED:      set(),  # terminal
    PaymentStatus.FAILED:       set(),  # terminal
}

# Terminal states — no transitions allowed
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
    Creates exactly one audit_log entry.
    Raises InvalidTransitionError for illegal transitions.
    """
    payment = db.query(PaymentTranslation).filter(PaymentTranslation.id == payment_id).with_for_update().first()
    if not payment:
        raise ValueError(f"Payment {payment_id} not found")

    from_status = payment.status

    # Check terminal state
    if from_status in TERMINAL_STATES:
        raise InvalidTransitionError(
            f"Cannot transition from terminal state {from_status}"
        )

    # Check valid transition
    if to_status not in VALID_TRANSITIONS.get(from_status, set()):
        raise InvalidTransitionError(
            f"Invalid transition: {from_status} → {to_status}"
        )

    # Perform transition atomically
    try:
        payment.status = to_status
        payment.updated_at = datetime.now(timezone.utc)

        audit = AuditLog(
            payment_id=payment.id,
            from_status=from_status,
            to_status=to_status,
            triggered_by=triggered_by,
            meta_data=metadata,
        )
        db.add(audit)
        db.commit()
        return payment
    except SQLAlchemyError:
        db.rollback()
        raise
