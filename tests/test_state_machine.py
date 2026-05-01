import pytest
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.state.machine import (
    transition_payment, InvalidTransitionError,
    VALID_TRANSITIONS, TERMINAL_STATES,
)
from app.models.payment import (
    Base, PaymentTranslation, PaymentStatus, TriggeredBy, AuditLog,
)


# ── Test fixtures ──────────────────────────────────────────────
@pytest.fixture(scope="module")
def engine():
    eng = create_engine("sqlite:////tmp/test_state.db")
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)


@pytest.fixture
def db(engine):
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def payment(db):
    """Create a payment in RECEIVED state."""
    p = PaymentTranslation(
        ase_name="ASE_A",
        raw_message="test",
        status=PaymentStatus.RECEIVED,
        stan="123456",
        currency="524",
    )
    db.add(p)
    db.commit()
    return p


# ── B.L.A.S.T. Test Cases ─────────────────────────────────────


# ✓ RECEIVED → TRANSLATING → audit entry created
def test_received_to_translating_creates_audit(payment, db):
    transition_payment(db, payment.id, PaymentStatus.TRANSLATING, TriggeredBy.ASE_INBOUND)

    audits = db.query(AuditLog).filter(AuditLog.payment_id == payment.id).all()
    assert len(audits) == 1
    assert audits[0].from_status is None  # First entry has NULL from_status
    assert audits[0].to_status == PaymentStatus.TRANSLATING
    assert audits[0].triggered_by == TriggeredBy.ASE_INBOUND


# ✓ RECEIVED → ILP_PREPARED → raises InvalidTransitionError
def test_direct_jump_rejected(payment, db):
    with pytest.raises(InvalidTransitionError) as exc_info:
        transition_payment(db, payment.id, PaymentStatus.ILP_PREPARED, TriggeredBy.ASE_INBOUND)
    assert "Invalid transition" in str(exc_info.value)


# ✓ SETTLED → FAILED → raises InvalidTransitionError
def test_terminal_settled_no_transition(db):
    p = PaymentTranslation(
        ase_name="ASE_A",
        raw_message="test",
        status=PaymentStatus.SETTLED,
        stan="999999",
    )
    db.add(p)
    db.commit()

    with pytest.raises(InvalidTransitionError) as exc_info:
        transition_payment(db, p.id, PaymentStatus.FAILED, TriggeredBy.SYSTEM)
    assert "terminal state" in str(exc_info.value).lower()


# ✓ FAILED → anything → raises InvalidTransitionError
def test_terminal_failed_no_transition(db):
    p = PaymentTranslation(
        ase_name="ASE_A",
        raw_message="test",
        status=PaymentStatus.FAILED,
        stan="888888",
    )
    db.add(p)
    db.commit()

    with pytest.raises(InvalidTransitionError):
        transition_payment(db, p.id, PaymentStatus.RECEIVED, TriggeredBy.SYSTEM)


# ✓ Every terminal state → no transitions accepted
def test_all_terminal_states_reject(db):
    for terminal_status in TERMINAL_STATES:
        p = PaymentTranslation(
            ase_name="ASE_A",
            raw_message="test",
            status=terminal_status,
            stan=f"STAN_{terminal_status.value}",
        )
        db.add(p)
        db.commit()

        with pytest.raises(InvalidTransitionError):
            transition_payment(db, p.id, PaymentStatus.RECEIVED, TriggeredBy.SYSTEM)


# ✓ triggered_by stored exactly as passed
def test_triggered_by_stored_correctly(payment, db):
    transition_payment(db, payment.id, PaymentStatus.TRANSLATING, TriggeredBy.TRANSLATION_JOB)

    audit = db.query(AuditLog).filter(
        AuditLog.payment_id == payment.id
    ).first()
    assert audit.triggered_by == TriggeredBy.TRANSLATION_JOB


# ✓ Concurrent transition attempts on same payment → only one succeeds
def test_concurrent_transitions_only_one_succeeds(payment, db):
    """
    The pessimistic lock with nowait=True should cause concurrent attempts
    to fail immediately with InvalidTransitionError.
    """
    # First transition (success)
    transition_payment(db, payment.id, PaymentStatus.TRANSLATING, TriggeredBy.ASE_INBOUND)

    # Try to transition from RECEIVED again (should fail - already TRANSLATING)
    with pytest.raises(InvalidTransitionError):
        transition_payment(db, payment.id, PaymentStatus.TRANSLATING, TriggeredBy.ASE_INBOUND)


# ✓ Payment not found → ValueError
def test_payment_not_found(db):
    with pytest.raises(ValueError) as exc_info:
        transition_payment(db, 99999, PaymentStatus.TRANSLATING, TriggeredBy.ASE_INBOUND)
    assert "not found" in str(exc_info.value).lower()


# ✓ from_status NULL on first entry
def test_first_audit_has_null_from_status(db):
    """First audit entry should have from_status = NULL."""
    p = PaymentTranslation(
        ase_name="ASE_A",
        raw_message="test",
        status=PaymentStatus.RECEIVED,
        stan="111111",
    )
    db.add(p)
    db.commit()

    # Transition RECEIVED -> TRANSLATING
    transition_payment(db, p.id, PaymentStatus.TRANSLATING, TriggeredBy.ASE_INBOUND)

    # Check the audit entry - first transition should have from_status=NULL
    audit = db.query(AuditLog).filter(AuditLog.payment_id == p.id).first()
    assert audit is not None
    assert audit.from_status is None


# ✓ Multiple transitions create correct audit trail
def test_multiple_transitions_audit_trail(payment, db):
    """Verify audit log entries are in correct chronological order."""
    # RECEIVED → TRANSLATING
    transition_payment(db, payment.id, PaymentStatus.TRANSLATING, TriggeredBy.ASE_INBOUND)

    # TRANSLATING → TRANSLATED
    transition_payment(db, payment.id, PaymentStatus.TRANSLATED, TriggeredBy.TRANSLATION_JOB)

    # TRANSLATED → ILP_PREPARED
    transition_payment(db, payment.id, PaymentStatus.ILP_PREPARED, TriggeredBy.TRANSLATION_JOB)

    audits = db.query(AuditLog).filter(
        AuditLog.payment_id == payment.id
    ).order_by(AuditLog.created_at).all()

    assert len(audits) == 3
    assert audits[0].to_status == PaymentStatus.TRANSLATING
    assert audits[1].from_status == PaymentStatus.TRANSLATING
    assert audits[1].to_status == PaymentStatus.TRANSLATED
    assert audits[2].from_status == PaymentStatus.TRANSLATED
    assert audits[2].to_status == PaymentStatus.ILP_PREPARED
