import hmac
import hashlib
from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.orm import Session
from app.db import get_db
from app.state.machine import transition_payment, TriggeredBy, InvalidTransitionError
from app.models.payment import PaymentTranslation, PaymentStatus
from app.config import get_settings
_settings = get_settings()
from app.clients.rafiki_client import RafikiClient
from app.state.pending import pending_payments

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

def verify_signature(request_body: bytes, signature: str) -> bool:
    # Parse signature: "t=timestamp, v1=digest"
    try:
        # Split by comma
        parts = signature.split(',')
        
        if len(parts) < 2:
            return False
        
        # Parse timestamp from first part: "t=timestamp"
        timestamp_part = parts[0].strip()
        timestamp = timestamp_part.split('=')[1]
        
        # Parse digest from second part: "v1=digest"
        digest_part = parts[1].strip()
        digest = digest_part.split('=')[1]
        
        # Reconstruct payload: timestamp.canonicalize({id, type, data})
        import json
        payload_data = json.loads(request_body)
        canonical_body = json.dumps({
            "id": payload_data.get("id"),
            "type": payload_data.get("type"),
            "data": payload_data.get("data")
        }, sort_keys=True, separators=(',', ':'))
        
        payload = f"{timestamp}.{canonical_body}"
        
        expected = hmac.new(
            _settings.rafiki_webhook_secret.encode("utf-8"),
            payload.encode(),
            hashlib.sha256,
        ).hexdigest()
        
        return hmac.compare_digest(expected, digest)
    except Exception:
        return False
    except Exception as e:
        print(f"Signature verification error: {e}")
        return False


@router.post("/rafiki")
async def rafiki_webhook(request: Request, db: Session = Depends(get_db)):
    body = await request.body()
    signature = request.headers.get("rafiki-signature", "")
    
    if not verify_signature(body, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    event_type = payload.get("type")
    data = payload.get("data", {})
    external_ref = data.get("metadata", {}).get("externalRef")  # This is STAN

    if not external_ref:
        raise HTTPException(status_code=400, detail="Missing externalRef")

    # Find payment by STAN (DE11)
    payment = (
        db.query(PaymentTranslation)
        .filter(PaymentTranslation.stan == external_ref)
        .order_by(PaymentTranslation.created_at.desc())
        .first()
    )
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    try:
        if event_type == "payment.COMPLETED":
            transition_payment(
                db, payment.id, PaymentStatus.ILP_FULFILLED,
                TriggeredBy.RAFIKI_WEBHOOK, f"Rafiki event: {event_type}"
            )
            # Signal TCP handler
            stan = payment.stan
            if stan in pending_payments:
                pending_payments[stan].set()
        elif event_type == "payment.FAILED":
            transition_payment(
                db, payment.id, PaymentStatus.ILP_REJECTED,
                TriggeredBy.RAFIKI_WEBHOOK, f"Rafiki event: {event_type}"
            )
            # Signal TCP handler
            stan = payment.stan
            if stan in pending_payments:
                pending_payments[stan].set()
        else:
            # Unknown event — ignore but acknowledge
            return {"status": "ignored", "event": event_type}
    except InvalidTransitionError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"status": "ok", "event": event_type, "payment_id": payment.id}
