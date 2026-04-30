from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import Optional
import datetime

from app.iso8583_parser import create_financial_request, create_response, parse_iso_message, message_to_dict
from app.rafiki_client import transfer_between_coops, MockRafikiClient
from app.database import get_db, Transaction, db

app = FastAPI(
    title="Payment Middleware",
    description="Middleware translating ISO 8583 messages to ILP/Rafiki for inter-coop transfers",
    version="0.1.0",
)

# Initialize database tables
@app.on_event("startup")
def startup_event():
    db.create_tables()


@app.get("/health", tags=["health"])
def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/iso8583/process", tags=["ISO 8583"])
async def process_iso8583_message(
    source_account: str,
    amount: float,
    currency: str = "840",
    source_coop_id: str = "",
    dest_coop_wallet: str = "http://localhost:3001/alice",
    use_mock: bool = True
):
    """
    Process an ISO 8583 financial request and execute transfer via Rafiki.
    
    Args:
        source_account: Source account number (ISO Field 2)
        amount: Transfer amount
        currency: Currency code (ISO 4217, default USD=840)
        source_coop_id: Source cooperative ID (ISO Field 32)
        dest_coop_wallet: Destination coop's Rafiki wallet URL
        use_mock: Use mock Rafiki client for testing
    
    Returns:
        ISO 8583 response message
    """
    try:
        # Create ISO 8583 financial request (MTI 0200) using pyiso8583
        iso_request_bytes, iso_request_decoded = create_financial_request(
            source_account=source_account,
            amount=amount,
            currency=currency,
            coop_id=source_coop_id
        )
        
        # Store transaction in database
        db_session = next(get_db())
        transaction = Transaction(
            mti=iso_request_decoded.get('t'),
            stan=iso_request_decoded.get('11'),
            rrn=iso_request_decoded.get('37'),
            source_account=source_account,
            source_coop_id=source_coop_id,
            dest_coop_wallet=dest_coop_wallet,
            amount=amount,
            currency=currency,
            request_message=str(iso_request_decoded)
        )
        db_session.add(transaction)
        db_session.commit()
        
        # Create Rafiki client (mock or real)
        rafiki_client = MockRafikiClient() if use_mock else None
        if not use_mock:
            rafiki_client = None  # Will use default real client
        
        # Execute transfer via Rafiki
        source_wallet = f"http://localhost:3000/{source_coop_id}" if source_coop_id else "http://localhost:3000/alice"
        
        result = transfer_between_coops(
            source_coop_wallet=source_wallet,
            dest_coop_wallet=dest_coop_wallet,
            amount=amount,
            currency=currency,
            rafiki_client=rafiki_client if use_mock else None
        )
        
        # Update transaction with result
        transaction.rafiki_payment_id = result.get("payment_id")
        transaction.rafiki_quote_id = result.get("quote_id")
        transaction.status = "COMPLETED" if result["success"] else "FAILED"
        transaction.response_code = result["response_code"]
        db_session.commit()
        
        # Create ISO 8583 response using pyiso8583
        iso_response_bytes, iso_response_decoded = create_response(
            request_decoded=iso_request_decoded,
            response_code=result["response_code"]
        )
        
        # Convert to friendly format
        response_dict = message_to_dict(iso_response_decoded)
        
        # Add additional response fields
        if result.get("payment_id"):
            iso_response_decoded['38'] = result["payment_id"][:6].zfill(6)  # Authorization code
        
        return {
            "mti": iso_response_decoded.get('t'),
            "fields": response_dict['fields'],
            "bitmap": iso_response_decoded.get('p'),
            "transaction_id": transaction.id,
            "success": result["success"],
            "message": "Transfer completed" if result["success"] else result.get("error")
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/transfer", tags=["Transfer"])
async def initiate_transfer(
    source_account: str,
    amount: float,
    dest_coop_wallet: str,
    currency: str = "840",
    source_coop_id: str = "",
    use_mock: bool = True
):
    """
    Simplified endpoint to initiate transfer between coops.
    This is a higher-level API that handles ISO 8583 internally.
    """
    return await process_iso8583_message(
        source_account=source_account,
        amount=amount,
        currency=currency,
        source_coop_id=source_coop_id,
        dest_coop_wallet=dest_coop_wallet,
        use_mock=use_mock
    )


@app.get("/transactions/{transaction_id}", tags=["Transactions"])
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


@app.get("/transactions", tags=["Transactions"])
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


@app.post("/iso8583/parse", tags=["ISO 8583"])
async def parse_iso8583_hex(hex_data: str):
    """
    Parse raw ISO 8583 message from hex string using pyiso8583.
    Useful for debugging incoming messages.
    """
    try:
        data = bytes.fromhex(hex_data)
        decoded, encoded = parse_iso_message(data)
        result = message_to_dict(decoded)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Parse error: {str(e)}")