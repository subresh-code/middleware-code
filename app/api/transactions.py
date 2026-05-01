"""
Transaction-related endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional

router = APIRouter()

from app.database import get_db, Transaction


@router.get("/transactions", tags=["transactions"])
async def list_transactions(
    skip: int = 0,
    limit: int = 100,
    status: Optional[str] = None,
    db_session: Session = Depends(get_db)
):
    """List all transactions with optional filtering."""
    query = db_session.query(Transaction)
    
    if status:
        query = query.filter(Transaction.status == status)
    
    transactions = query.offset(skip).limit(limit).all()
    
    return [
        {
            "id": t.id,
            "mti": t.mti,
            "stan": t.stan,
            "rrn": t.rrn,
            "amount": t.amount,
            "currency": t.currency,
            "status": t.status,
            "created_at": t.created_at
        }
        for t in transactions
    ]


@router.get("/transactions/{transaction_id}", tags=["transactions"])
async def get_transaction(transaction_id: int, db_session: Session = Depends(get_db)):
    """Get transaction details by ID."""
    transaction = db_session.query(Transaction).filter(Transaction.id == transaction_id).first()
    if not transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")
    
    return {
        "id": transaction.id,
        "mti": transaction.mti,
        "stan": transaction.stan,
        "rrn": transaction.rrn,
        "source_account": transaction.source_account,
        "source_coop_id": transaction.source_coop_id,
        "amount": transaction.amount,
        "currency": transaction.currency,
        "status": transaction.status,
        "response_code": transaction.response_code,
        "rafiki_payment_id": transaction.rafiki_payment_id,
        "created_at": transaction.created_at,
        "updated_at": transaction.updated_at
    }
