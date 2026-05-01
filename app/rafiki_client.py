"""
Rafiki Client for Interledger Protocol (ILP) integration.
Implements Open Payments specification for Rafiki.
"""

import requests
import json
from typing import Optional, Dict, Any, Tuple


# ISO 8583 Response Codes mapped from Rafiki errors
ISO8583_RESPONSE_CODES = {
    "00": "Approved",
    "05": "Do not honor",
    "14": "Invalid card number (wallet not found)",
    "51": "Not sufficient funds",
    "91": "Issuer or switch inoperative",
    "96": "System malfunction",
}

# Cooperative Wallet Mapping
COOP_WALLET_MAPPING = {
    "001234": "http://localhost:3000/001234",  # Coop 1
    "005678": "http://localhost:3000/005678",  # Coop 2
}


class RafikiClient:
    """
    Client for interacting with Rafiki payment service via Open Payments API.
    https://openpayments.dev/
    """

    def __init__(
        self,
        base_url: str = "http://localhost:3000",
        auth_token: Optional[str] = None,
        wallet_mapping: Optional[Dict[str, str]] = None,
    ):
        """
        Initialize Rafiki client.

        Args:
            base_url: Rafiki server base URL (e.g., http://localhost:3000)
            auth_token: GNAP access token for authenticated requests
            wallet_mapping: Mapping of coop IDs to wallet URLs
        """
        self.base_url = base_url.rstrip('/')
        self.auth_token = auth_token
        self.session = requests.Session()
        self.wallet_mapping = wallet_mapping or COOP_WALLET_MAPPING

        # Set default headers
        headers = {'Content-Type': 'application/json'}
        if auth_token:
            headers['Authorization'] = f'GNAP {auth_token}'
        self.session.headers.update(headers)

    def get_wallet_address(self, wallet_url: str) -> Optional[Dict[str, Any]]:
        """
        Fetch wallet address details from Rafiki.
        GET {wallet_url}

        Returns wallet address resource with asset info, balance, etc.
        """
        try:
            response = self.session.get(wallet_url)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error fetching wallet address: {e}")
            return None

    def resolve_coop_wallet(self, coop_id: str) -> Optional[str]:
        """
        Resolve cooperative ID to Rafiki wallet URL.

        Args:
            coop_id: Cooperative identifier (e.g., "001234")

        Returns:
            Wallet URL or None if not found
        """
        return self.wallet_mapping.get(coop_id)

    def create_quote(
        self,
        sender_wallet: str,
        receiver_wallet: str,
        amount: int,
        asset_code: str = "USD",
        asset_scale: int = 2,
    ) -> Optional[Dict[str, Any]]:
        """
        Create a quote in Rafiki for a payment.
        POST {sender_wallet}/quotes

        Args:
            sender_wallet: Sender's wallet address URL
            receiver_wallet: Receiver's wallet address URL
            amount: Amount in smallest unit (cents for USD)
            asset_code: Asset code (e.g., "USD")
            asset_scale: Asset scale (2 for USD cents)

        Returns:
            Quote object with id, amounts, expiresAt
        """
        url = f"{sender_wallet}/quotes"

        payload = {
            "method": "ilp",
            "walletAddress": receiver_wallet,
            "receiveAmount": {
                "value": str(amount),
                "assetCode": asset_code,
                "assetScale": asset_scale,
            }
        }

        try:
            response = self.session.post(url, json=payload)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error creating quote: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"Response: {e.response.text}")
            return None

    def create_outgoing_payment(
        self,
        sender_wallet: str,
        quote_id: str,
        grant_access_token: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Create an outgoing payment in Rafiki.
        POST {sender_wallet}/outgoing-payments

        Args:
            sender_wallet: Sender's wallet address URL
            quote_id: The quote ID for this payment
            grant_access_token: GNAP access token (if different from init)

        Returns:
            Outgoing payment object with status, amounts sent
        """
        url = f"{sender_wallet}/outgoing-payments"

        headers = {}
        if grant_access_token:
            headers['Authorization'] = f'GNAP {grant_access_token}'

        payload = {
            "quoteId": quote_id,
        }

        try:
            response = self.session.post(url, json=payload, headers=headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error creating outgoing payment: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"Response: {e.response.text}")
            return None

    def check_payment_status(self, payment_url: str) -> Optional[Dict[str, Any]]:
        """
        Check the status of an outgoing payment.
        GET {payment_url}

        Returns:
            Payment object with current status
        """
        try:
            response = self.session.get(payment_url)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error checking payment status: {e}")
            return None

    def get_access_token_for_grant(self, grant_url: str) -> Optional[str]:
        """
        Exchange grant for access token (GNAP flow).
        POST {grant_url}/token

        This is part of the GNAP authorization flow.
        """
        try:
            response = self.session.post(f"{grant_url}/token")
            response.raise_for_status()
            data = response.json()
            return data.get("access_token")
        except requests.exceptions.RequestException as e:
            print(f"Error getting access token: {e}")
            return None


class MockRafikiClient:
    """
    Mock Rafiki client for testing without actual Rafiki instance.
    Simulates successful payment processing.
    """

    def __init__(self, *args, **kwargs):
        self.payments = {}
        self.quotes = {}

    def get_wallet_address(self, wallet_url: str):
        return {
            "id": wallet_url,
            "assetCode": "USD",
            "assetScale": 2,
            "status": "ACTIVE"
        }

    def resolve_coop_wallet(self, coop_id: str) -> str:
        return f"http://localhost:3000/{coop_id}"

    def create_quote(self, sender_wallet: str, receiver_wallet: str, amount: int, **kwargs):
        quote_id = f"quote_{len(self.quotes) + 1}"
        quote = {
            "id": quote_id,
            "walletAddress": sender_wallet,
            "receiver": receiver_wallet,
            "receiveAmount": {
                "value": str(amount),
                "assetCode": kwargs.get("asset_code", "USD"),
                "assetScale": kwargs.get("asset_scale", 2),
            },
            "status": "READY",
            "expiresAt": "2026-05-01T12:00:00.000Z"
        }
        self.quotes[quote_id] = quote
        return quote

    def create_outgoing_payment(self, sender_wallet: str, quote_id: str, **kwargs):
        payment_id = f"payment_{len(self.payments) + 1}"
        quote = self.quotes.get(quote_id, {})
        payment = {
            "id": payment_id,
            "walletAddress": sender_wallet,
            "quoteId": quote_id,
            "status": "COMPLETED",
            "sentAmount": {
                "value": str(quote.get("receiveAmount", {}).get("value", "0")),
                "assetCode": "USD",
                "assetScale": 2,
            },
            "debitAmount": {
                "value": str(quote.get("receiveAmount", {}).get("value", "0")),
                "assetCode": "USD",
                "assetScale": 2,
            }
        }
        self.payments[payment_id] = payment
        return payment

    def check_payment_status(self, payment_url: str):
        payment_id = payment_url.split("/")[-1]
        if payment_id in self.payments:
            return self.payments[payment_id]
        return {"status": "UNKNOWN"}


def map_rafiki_error_to_iso8583(error: str, status_code: Optional[int] = None) -> str:
    """
    Map Rafiki/Open Payments errors to ISO 8583 response codes (field 39).

    ISO 8583 Response Codes:
        00 - Approved
        05 - Do not honor
        14 - Invalid card number (wallet not found)
        51 - Not sufficient funds
        91 - Issuer or switch inoperative
        96 - System malfunction
    """
    error_lower = error.lower()

    if "insufficient" in error_lower or "funds" in error_lower:
        return "51"  # Not sufficient funds
    elif "not found" in error_lower or "invalid" in error_lower:
        return "14"  # Invalid card number
    elif "unauthorized" in error_lower or status_code == 401:
        return "05"  # Do not honor
    elif "unavailable" in error_lower or status_code == 503:
        return "91"  # Issuer inoperative
    else:
        return "96"  # System malfunction


def transfer_between_coops(
    source_coop_wallet: str,
    dest_coop_wallet: str,
    amount: float,
    currency: str = "USD",
    rafiki_client: Optional[RafikiClient] = None,
    use_mock: bool = True,
) -> Dict[str, Any]:
    """
    Transfer money between two coops using Rafiki/Open Payments.

    Flow:
    1. Resolve wallet addresses
    2. Create quote in Rafiki
    3. Create outgoing payment (uses quote)
    4. Return result with ISO 8583 response code

    Args:
        source_coop_wallet: Source coop's wallet URL or coop ID
        dest_coop_wallet: Destination coop's wallet URL or coop ID
        amount: Amount to transfer (in dollars)
        currency: Currency code (ISO 4217)
        rafiki_client: RafikiClient instance (creates mock if None)
        use_mock: Use mock client for testing

    Returns:
        Dictionary with transfer result and ISO 8583 response code
    """
    if use_mock or rafiki_client is None:
        rafiki_client = MockRafikiClient()

    # Convert amount to smallest unit (cents for USD)
    asset_scale = 2 if currency == "USD" else 0
    amount_smallest = int(amount * (10 ** asset_scale))

    # If source/dest are coop IDs, resolve to wallet URLs
    if not source_coop_wallet.startswith("http"):
        source_wallet = rafiki_client.resolve_coop_wallet(source_coop_wallet)
        if not source_wallet:
            return {
                "success": False,
                "error": f"Source coop wallet not found: {source_coop_wallet}",
                "response_code": "14"  # Invalid card number
            }
    else:
        source_wallet = source_coop_wallet

    if not dest_coop_wallet.startswith("http"):
        dest_wallet = rafiki_client.resolve_coop_wallet(dest_coop_wallet)
        if not dest_wallet:
            return {
                "success": False,
                "error": f"Destination coop wallet not found: {dest_coop_wallet}",
                "response_code": "14"  # Invalid card number
            }
    else:
        dest_wallet = dest_coop_wallet

    # Step 1: Verify wallet addresses exist
    source_wallet_info = rafiki_client.get_wallet_address(source_wallet)
    if not source_wallet_info:
        return {
            "success": False,
            "error": "Source wallet not found",
            "response_code": "14"
        }

    # Step 2: Create quote
    quote = rafiki_client.create_quote(
        sender_wallet=source_wallet,
        receiver_wallet=dest_wallet,
        amount=amount_smallest,
        asset_code=currency,
        asset_scale=asset_scale,
    )

    if not quote:
        return {
            "success": False,
            "error": "Failed to create quote",
            "response_code": "91"  # Issuer inoperative
        }

    # Step 3: Create outgoing payment
    payment = rafiki_client.create_outgoing_payment(
        sender_wallet=source_wallet,
        quote_id=quote["id"],
        grant_access_token=None  # Would come from GNAP flow
    )

    if not payment:
        return {
            "success": False,
            "error": "Failed to create outgoing payment",
            "response_code": "05"  # Do not honor
        }

    # Step 4: Check payment status
    payment_status = payment.get("status", "UNKNOWN")

    if payment_status == "COMPLETED":
        return {
            "success": True,
            "payment_id": payment["id"],
            "quote_id": quote["id"],
            "status": payment_status,
            "amount_sent": amount,
            "response_code": "00"  # Approved
        }
    elif payment_status == "PENDING":
        return {
            "success": True,
            "payment_id": payment["id"],
            "quote_id": quote["id"],
            "status": payment_status,
            "amount_sent": 0,
            "response_code": "00"  # Still approved (in progress)
        }
    else:
        return {
            "success": False,
            "payment_id": payment["id"],
            "error": f"Payment failed with status: {payment_status}",
            "response_code": "05"  # Do not honor
        }
