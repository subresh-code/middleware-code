import asyncio
import hmac
import hashlib
import httpx
from typing import Optional
from app.config import get_settings
_settings = get_settings()


class RafikiClient:
    def __init__(self):
        self.base_url = _settings.rafiki_api_url.rstrip("/")
        self.auth_token = _settings.rafiki_auth_token
        self.webhook_secret = _settings.rafiki_webhook_secret
        self.tenant_id = _settings.rafiki_tenant_id
        self.admin_api_secret = _settings.rafiki_admin_api_secret
        self.headers = {
            "Authorization": f"Bearer {self.auth_token}",
            "Content-Type": "application/json",
        }

    def _generate_signature(self, method: str, path: str, body: bytes) -> str:
        """Generate HMAC SHA-256 signature for Rafiki Admin API."""
        message = f"{method.upper()}{path}{body.decode('utf-8') if body else ''}"
        return hmac.new(
            self.admin_api_secret.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        # Prepare body for signing
        json_body = kwargs.get("json")
        body_bytes = b""
        if json_body:
            import json
            body_bytes = json.dumps(json_body).encode("utf-8")

        # Add mandatory Rafiki Admin headers
        headers = self.headers.copy()
        headers["tenant-id"] = self.tenant_id
        headers["signature"] = self._generate_signature(method, path, body_bytes)

        async with httpx.AsyncClient(headers=headers, timeout=10.0) as client:
            url = f"{self.base_url}{path}"
            resp = await client.request(method, url, **kwargs)
            resp.raise_for_status()
            return resp

    async def _request_with_retry(
        self, method: str, path: str, max_retries: int = 3, **kwargs
    ) -> httpx.Response:
        """Retry with exponential backoff: 1s, 2s, 4s."""
        for attempt in range(max_retries):
            try:
                return await self._request(method, path, **kwargs)
            except (httpx.HTTPStatusError, httpx.RequestError) as e:
                if attempt == max_retries - 1:
                    raise
                backoff = 2 ** attempt
                await asyncio.sleep(backoff)

    async def get_wallet_address(self, wallet_address: str) -> dict:
        """Validate destination wallet exists in Rafiki."""
        resp = await self._request_with_retry("GET", f"/accounts/{wallet_address}")
        return resp.json()

    async def create_incoming_payment(
        self, 
        wallet_address: str, 
        amount_value: int, 
        asset_code: str, 
        asset_scale: int,
        expires_at: str = None,
        external_ref: str = None
    ) -> dict:
        """Create receiver-side payment object. Returns incoming payment with URL."""
        payload = {
            "incomingAmount": {
                "value": str(amount_value),
                "assetCode": asset_code,
                "assetScale": asset_scale,
            }
        }
        if expires_at:
            payload["expiresAt"] = expires_at
        if external_ref:
            payload["externalRef"] = external_ref

        resp = await self._request_with_retry(
            "POST", f"/accounts/{wallet_address}/incoming-payments", json=payload
        )
        return resp.json()

    async def create_outgoing_payment(
        self,
        wallet_address: str,
        incoming_payment_url: str,
        amount_value: int,
        asset_code: str,
        asset_scale: int,
        stan: str,
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
        resp = await self._request_with_retry(
            "POST", f"/accounts/{wallet_address}/outgoing-payments", json=payload
        )
        return resp.json()

    async def create_quote(
        self,
        wallet_address: str,
        incoming_payment_url: str,
        amount_value: int,
        asset_code: str,
        asset_scale: int,
    ) -> dict:
        """Create a quote to determine the cost for the sender."""
        payload = {
            "amount": {
                "value": str(amount_value),
                "assetCode": asset_code,
                "assetScale": asset_scale,
            },
            "incomingPayment": incoming_payment_url,
        }
        resp = await self._request_with_retry(
            "POST", f"/accounts/{wallet_address}/quotes", json=payload
        )
        return resp.json()

    async def deposit_outgoing_payment_liquidity(self, payment_id: str) -> dict:
        """Notify Rafiki to approve the outgoing payment by providing liquidity."""
        payload = {"paymentId": payment_id}
        resp = await self._request_with_retry(
            "POST", "/outgoing-payments/deposit-liquidity", json=payload
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
