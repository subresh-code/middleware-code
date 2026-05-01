"""
ISO 8583 and transfer endpoints.
"""
from fastapi import APIRouter, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
import datetime

router = APIRouter()

from app.iso8583_parser import create_financial_request, create_response, parse_iso_message, message_to_dict
from app.rafiki_client import transfer_between_coops, MockRafikiClient, RafikiClient, COOP_WALLET_MAPPING
from app.database import get_db, Transaction, db


@router.post("/iso8583/process", tags=["iso8583"])
async def process_iso8583_message(
    source_account: str,
    amount: float,
    currency: str = "840",
    source_coop_id: str = "",
    dest_coop_wallet: str = "",
    dest_coop_id: str = "",
    use_mock: bool = True,
    rafiki_url: str = "http://localhost:3000"
):
    """
    Process an ISO 8583 financial request and execute transfer via Rafiki.
    
    Args:
        source_account: Source account number (ISO Field 2)
        amount: Transfer amount
        currency: Currency code (ISO 4217, default USD=840)
        source_coop_id: Source cooperative ID (ISO Field 32)
        dest_coop_wallet: Destination coop's Rafiki wallet URL (overrides dest_coop_id)
        dest_coop_id: Destination cooperative ID (resolved via mapping)
        use_mock: Use mock Rafiki client for testing
        rafiki_url: Rafiki server URL for real transfers
    
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
            dest_coop_wallet=dest_coop_wallet or dest_coop_id,
            amount=amount,
            currency=currency,
            request_message=str(iso_request_decoded)
        )
        db_session.add(transaction)
        db_session.commit()
        
        # Resolve destination wallet
        if not dest_coop_wallet and dest_coop_id:
            dest_coop_wallet = COOP_WALLET_MAPPING.get(dest_coop_id, "")
        
        if not dest_coop_wallet:
            dest_coop_wallet = f"http://localhost:3001/alice"
        
        # Resolve source wallet
        source_wallet = COOP_WALLET_MAPPING.get(source_coop_id, "")
        if not source_wallet:
            source_wallet = f"http://localhost:3000/{source_coop_id}" if source_coop_id else "http://localhost:3000/alice"
        
        # Create Rafiki client (mock or real)
        if use_mock:
            rafiki_client = MockRafikiClient()
        else:
            rafiki_client = RafikiClient(base_url=rafiki_url)
        
        # Execute transfer via Rafiki
        result = transfer_between_coops(
            source_coop_wallet=source_wallet,
            dest_coop_wallet=dest_coop_wallet,
            amount=amount,
            currency=currency,
            rafiki_client=rafiki_client,
            use_mock=use_mock
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
        
        return {
            "mti": iso_response_decoded.get('t'),
            "fields": response_dict['fields'],
            "bitmap": iso_response_decoded.get('p'),
            "transaction_id": transaction.id,
            "success": result["success"],
            "message": "Transfer completed" if result["success"] else result.get("error"),
            "rafiki_payment_id": result.get("payment_id"),
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/transfer", tags=["transfer"])
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


@router.post("/iso8583/parse", tags=["iso8583"])
async def parse_iso8583_hex(hex_data: str = None, body: dict = None):
    """
    Parse raw ISO 8583 message from hex string using pyiso8583.
    Useful for debugging incoming messages.
    Provide hex_data as query parameter or in request body as JSON: {"hex_data": "..."}
    """
    try:
        # Get hex_data from body or query parameter
        if body and 'hex_data' in body:
            hex_string = body['hex_data']
        elif hex_data:
            hex_string = hex_data
        else:
            raise ValueError("hex_data is required")
        
        data = bytes.fromhex(hex_string)
        decoded, encoded = parse_iso_message(data)
        result = message_to_dict(decoded)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Parse error: {str(e)}")
