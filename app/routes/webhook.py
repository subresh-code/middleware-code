import hmac
import hashlib
from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.orm import Session
from app.db import get_db
from app.state.machine import transition_payment, TriggeredBy, InvalidTransitionError
from app.models.payment import PaymentTranslation, PaymentStatus
from app.config import get_settings
_settings = get_settings()
from app.state.pending import pending_payments

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

def verify_signature(request_body: bytes, signature: str) -> bool:
    expected = hmac.new(
        _settings.rafiki_webhook_secret.encode("utf-8"),
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
        # Malformed webhook body — return 200 so Rafiki doesn't retry
        logger.warning("Webhook received invalid JSON — returning 200")
        return {"status": "ok", "detail": "invalid JSON — ignored"}

    event_type = payload.get("type")
    data = payload.get("data", {})
    external_ref = data.get("metadata", {}).get("externalRef")  # This is STAN

    if not external_ref:
        logger.warning("Webhook received with no externalRef — returning 200")
        return {"status": "ok", "detail": "missing externalRef — ignored"}

    # Find payment by STAN (DE11)
    payment = (
        db.query(PaymentTranslation)
        .filter(PaymentTranslation.stan == external_ref)
        .order_by(PaymentTranslation.created_at.desc())
        .first()
    )
    # Payment not found — Rafiki may be sending for a payment we don't know
    # Return 200 so Rafiki does not retry
    if not payment:
        logger.warning(
            "Webhook received for unknown stan=%s — returning 200",
            external_ref,
        )
        return {"status": "ok", "detail": "payment not found — ignored"}

    try:
        if event_type == "payment.COMPLETED":
            transition_payment(
                db, payment.id, PaymentStatus.ILP_FULFILLED,
                TriggeredBy.RAFIKI_WEBHOOK, f"Rafiki event: {event_type}"
            )
            # Signal the TCP handler that the payment completed
            if payment.stan in pending_payments:
                pending_payments[payment.stan].set()
        elif event_type == "payment.FAILED":
            transition_payment(
                db, payment.id, PaymentStatus.ILP_REJECTED,
                TriggeredBy.RAFIKI_WEBHOOK, f"Rafiki event: {event_type}"
            )
            # Signal the TCP handler even on failure so it stops waiting
            if payment.stan in pending_payments:
                pending_payments[payment.stan].set()
        else:
            # Unknown event — ignore but acknowledge
            return {"status": "ignored", "event": event_type}
    except InvalidTransitionError as e:
        # Payment already in terminal state
        # This happens when webhook arrives after tcp.py already timed out
        # Return 200 so Rafiki does not retry
        logger.warning(
            "Webhook transition failed for payment %s (already terminal): %s",
            payment.id, e,
        )
        return {"status": "ok", "detail": "already terminal — ignored"}

    return {"status": "ok", "event": event_type, "payment_id": payment.id}
