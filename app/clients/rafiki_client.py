import time
import hmac
import hashlib
import json
import requests
from typing import Optional, Dict, Any
from app.config import get_settings
from app.clients.circuit_breaker import rafiki_breaker

_settings = get_settings()


class RafikiClient:
    def __init__(self):
        self.base_url = settings.rafiki_api_url.rstrip("/")
        self.auth_token = settings.rafiki_auth_token
        self.webhook_secret = settings.rafiki_webhook_secret
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.auth_token}",
            "Content-Type": "application/json",
        })

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        url = f"{self.base_url}{path}"
        resp = self.session.request(method, url, **kwargs)
        resp.raise_for_status()
        return resp

    def _request_with_retry(
        self, method: str, path: str, max_retries: int = 3, **kwargs
    ) -> requests.Response:
        """Retry with exponential backoff: 1s, 2s, 4s. Protected by circuit breaker."""
        def _do_request():
            for attempt in range(max_retries):
                try:
                    return self._request(method, path, **kwargs)
                except requests.RequestException as e:
                    if attempt == max_retries - 1:
                        raise
                    backoff = 2 ** attempt  # 1, 2, 4
                    time.sleep(backoff)
            raise requests.RequestException("Max retries exceeded")

        return rafiki_breaker.call(_do_request)

    def get_wallet_address(self, wallet_address: str) -> dict:
        """Validate destination wallet exists in Rafiki."""
        resp = self._request_with_retry("GET", f"/accounts/{wallet_address}")
        return resp.json()

    def create_incoming_payment(
        self, wallet_address: str, amount_value: int, asset_code: str, asset_scale: int
    ) -> dict:
        """Create receiver-side payment object. Returns incoming payment with URL."""
        payload = {
            "incomingAmount": {
                "value": str(amount_value),
                "assetCode": asset_code,
                "assetScale": asset_scale,
            }
        }
        resp = self._request_with_retry(
            "POST", f"/accounts/{wallet_address}/incoming-payments", json=payload
        )
        return resp.json()

    def create_outgoing_payment(
        self,
        wallet_address: str,
        incoming_payment_url: str,
        amount_value: int,
        asset_code: str,
        asset_scale: int,
        stan: str,  # DE11 — used as externalRef for webhook idempotency
    ) -> dict:
        """Trigger ILP packet. Returns outgoing payment."""
        payload = {
            "method": "ilp",
            "amount": {
                "value": str(amount_value),
                "assetCode": asset_code,
                "assetScale": asset_scale,
            },
            "incomingPayment": incoming_payment_url,
            "metadata": {
                "externalRef": stan,
            },
        }
        resp = self._request_with_retry(
            "POST", f"/accounts/{wallet_address}/outgoing-payments", json=payload
        )
        return resp.json()

    def verify_webhook_signature(self, body: bytes, signature: str) -> bool:
        """Verify HMAC signature on incoming webhook."""
        expected = hmac.new(
            self.webhook_secret.encode("utf-8"),
            body,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    def cancel_outgoing_payment(self, payment_id: str) -> dict:
        """Attempt to cancel an outgoing payment in Rafiki (if supported)."""
        mutation = {
            "query": """
                mutation CancelOutgoingPayment($id: String!) {
                    cancelOutgoingPayment(id: $id) {
                        payment {
                            id
                            state
                        }
                    }
                }
            """,
            "variables": {"id": payment_id}
        }
        try:
            resp = self._request_with_retry("POST", "/graphql", json=mutation)
            return resp.json()
        except Exception as e:
            logger = __import__("logging").getLogger(__name__)
            logger.warning("Could not cancel Rafiki payment %s: %s", payment_id, e)
            return {}
