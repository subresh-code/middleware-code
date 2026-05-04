from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.db import get_db
from app.models.payment import PaymentTranslation, PaymentStatus

router = APIRouter(tags=["inbound"])


@router.get("/transaction")
def query_transaction(
    stan: str = Query(None, description="DE11 STAN (6 digits)"),
    rrn: str = Query(None, description="DE37 RRN (12 chars)"),
    ase_name: str = Query(..., description="ASE name for scoping"),
    db: Session = Depends(get_db),
):
    """
    Query transaction status by STAN (DE11) or RRN (DE37).
    ASE-scoped: cannot query other ASEs' transactions.
    """
    if not stan and not rrn:
        raise HTTPException(status_code=400, detail="Provide stan or rrn")

    q = db.query(PaymentTranslation).filter(
        PaymentTranslation.ase_name == ase_name
    )
    if stan:
        q = q.filter(PaymentTranslation.stan == stan)
    if rrn:
        q = q.filter(PaymentTranslation.rrn == rrn)

    payment = q.order_by(PaymentTranslation.created_at.desc()).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Transaction not found")

    return {
        "stan": payment.stan,
        "rrn": payment.rrn,
        "mti": payment.mti,
        "processing_code": payment.processing_code,
        "status": payment.status.value,
        "response_code": payment.response_code,
        "amount_value": float(payment.amount_value) if payment.amount_value else None,
        "currency": payment.currency,
        "created_at": payment.created_at.isoformat() if payment.created_at else None,
        "updated_at": payment.updated_at.isoformat() if payment.updated_at else None,
        "failure_reason": payment.failure_reason,
    }
