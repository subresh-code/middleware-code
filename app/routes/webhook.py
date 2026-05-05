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
    expected = hmac.new(
        settings.rafiki_webhook_secret.encode("utf-8"),
        request_body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.post("/rafiki")
async def rafiki_webhook(request: Request, db: Session = Depends(get_db)):
    body = await request.body()
    signature = request.headers.get("X-Rafiki-Signature", "")

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
        if event_type == "outgoing_payment.created":
            # Step 9: Rafiki is ready. Signal the handler to proceed with ISO debit/liquidity.
            event = pending_payments.get(external_ref)
            if event:
                event.set()
            return {"status": "ok", "event": event_type, "action": "proceed_to_liquidity"}
        
        elif event_type == "outgoing_payment.completed":
            transition_payment(
                db, payment.id, PaymentStatus.ILP_FULFILLED,
                TriggeredBy.RAFIKI_WEBHOOK, f"Rafiki event: {event_type}"
            )
        elif event_type == "incoming_payment.completed":
            # Optional: Credit receiver via ISO 8583 if not already done
            pass
        elif event_type == "payment.FAILED":
            transition_payment(
                db, payment.id, PaymentStatus.ILP_REJECTED,
                TriggeredBy.RAFIKI_WEBHOOK, f"Rafiki event: {event_type}"
            )
        else:
            # Unknown event — ignore but acknowledge
            return {"status": "ignored", "event": event_type}

        # ── Signal the pending TCP request for final status (completed/failed) ──
        event = pending_payments.get(external_ref)
        if event:
            event.set()

    except InvalidTransitionError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"status": "ok", "event": event_type, "payment_id": payment.id}
