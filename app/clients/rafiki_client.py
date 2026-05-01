import time
import hmac
import hashlib
import json
import requests
from typing import Optional, Dict, Any
from app.config import get_settings

_settings = get_settings()

class RafikiClient:
    def __init__(self):
        self.base_url = _settings.rafiki_admin_url.rstrip("/")
        self.admin_secret = _settings.rafiki_admin_secret
        self.operator_tenant_id = "438fa74a-fa7d-4317-9ced-dde32ece1787"  # Operator tenant ID
        self.webhook_secret = _settings.rafiki_webhook_secret
        self.session = requests.Session()
        
    def _simple_canonicalize(self, obj: Dict[str, Any]) -> str:
        """Simple JSON canonicalization - sorts keys"""
        return json.dumps(obj, sort_keys=True, separators=(',', ':'))
    
    def _generate_signature(self, body: Dict[str, Any]) -> str:
        """Generate HMAC signature for Rafiki API request"""
        timestamp = int(time.time() * 1000)
        
        # Format request as GraphQL request
        formatted_request = {
            "query": body.get("query"),
            "variables": body.get("variables"),
            "operationName": body.get("operationName")
        }
        # Remove None values
        formatted_request = {k: v for k, v in formatted_request.items() if v is not None}
        
        payload = f"{timestamp}.{self._simple_canonicalize(formatted_request)}"
        
        digest = hmac.new(
            self.admin_secret.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()
        
        return f"t={timestamp}, v1={digest}"
    
    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        url = f"{self.base_url}{path}"
        
        # Add signature and tenant-id headers if body is present
        if 'json' in kwargs:
            signature = self._generate_signature(kwargs['json'])
            if 'headers' not in kwargs:
                kwargs['headers'] = {}
            kwargs['headers']['signature'] = signature
            kwargs['headers']['tenant-id'] = self.operator_tenant_id
            kwargs['headers']['Content-Type'] = 'application/json'
        
        resp = self.session.request(method, url, **kwargs)
        resp.raise_for_status()
        return resp

    def _request_with_retry(
        self, method: str, path: str, max_retries: int = 3, **kwargs
    ) -> requests.Response:
        """Retry with exponential backoff: 1s, 2s, 4s."""
        for attempt in range(max_retries):
            try:
                return self._request(method, path, **kwargs)
            except requests.RequestException as e:
                if attempt == max_retries - 1:
                    raise
                backoff = 2 ** attempt  # 1, 2, 4
                time.sleep(backoff)

    def get_wallet_address(self, wallet_address_url: str) -> dict:
        """Get wallet address details from Rafiki."""
        query = {
            "query": """
                query GetWalletAddress($url: String!) {
                    walletAddressByUrl(url: $url) {
                        id
                        address
                        asset {
                            code
                            scale
                        }
                    }
                }
            """,
            "variables": {"url": wallet_address_url}
        }
        resp = self._request_with_retry("POST", "/graphql", json=query)
        return resp.json()

    def create_incoming_payment(
        self, wallet_address_url: str, amount_ilp_uint64: int, asset_code: str, asset_scale: int
    ) -> dict:
        """Create receiver (incoming payment) in Rafiki. Returns payment data with ID."""
        mutation = {
            "query": """
                mutation CreateReceiver($input: CreateReceiverInput!) {
                    createReceiver(input: $input) {
                        receiver {
                            id
                            incomingAmount {
                                value
                                assetCode
                                assetScale
                            }
                            walletAddressUrl
                        }
                    }
                }
            """,
            "variables": {
                "input": {
                    "walletAddressUrl": wallet_address_url,
                    "incomingAmount": {
                        "value": str(amount_ilp_uint64),
                        "assetCode": asset_code,
                        "assetScale": asset_scale,
                    }
                }
            }
        }
        resp = self._request_with_retry("POST", "/graphql", json=mutation)
        return resp.json()

    def create_outgoing_payment(
        self,
        wallet_address_id: str,
        incoming_payment_url: str,
        debit_amount_ilp_uint64: int,
        asset_code: str,
        asset_scale: int,
        stan: str,  # DE11 — used as externalRef for webhook idempotency
    ) -> dict:
        """Create outgoing payment from incoming payment. Returns payment data."""
        mutation = {
            "query": """
                mutation CreateOutgoingPaymentFromIncomingPayment(
                    $input: CreateOutgoingPaymentFromIncomingPaymentInput!
                ) {
                    createOutgoingPaymentFromIncomingPayment(input: $input) {
                        payment {
                            id
                            state
                            sentAmount {
                                value
                                assetCode
                                assetScale
                            }
                        }
                    }
                }
            """,
            "variables": {
                "input": {
                    "walletAddressId": wallet_address_id,
                    "incomingPayment": incoming_payment_url,
                    "debitAmount": {
                        "value": str(debit_amount_ilp_uint64),
                        "assetCode": asset_code,
                        "assetScale": asset_scale,
                    },
                    "metadata": {
                        "externalRef": stan,
                    },
                }
            }
        }
        resp = self._request_with_retry("POST", "/graphql", json=mutation)
        return resp.json()

    def verify_webhook_signature(self, body: bytes, signature: str) -> bool:
        """Verify HMAC signature on incoming webhook."""
        expected = hmac.new(
            self.webhook_secret.encode("utf-8"),
            body,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)
