"""
Rafiki Client for Interledger Protocol (ILP) integration.
Handles communication with Rafiki payment rails.
"""

import requests
import json
from typing import Optional, Dict, Any


class RafikiClient:
    """
    Client for interacting with Rafiki payment service.
    Rafiki implements the Open Payments specification for ILP transfers.
    """
    
    def __init__(self, base_url: str = "http://localhost:3000", auth_token: Optional[str] = None):
        """
        Initialize Rafiki client.
        
        Args:
            base_url: Rafiki server URL (default: http://localhost:3000)
            auth_token: Optional authentication token
        """
        self.base_url = base_url.rstrip('/')
        self.auth_token = auth_token
        self.session = requests.Session()
        
        if auth_token:
            self.session.headers.update({
                'Authorization': f'Bearer {auth_token}',
                'Content-Type': 'application/json'
            })
        else:
            self.session.headers.update({
                'Content-Type': 'application/json'
            })
    
    def get_wallet_address(self, wallet_url: str) -> Optional[Dict[str, Any]]:
        """
        Fetch wallet address details from Rafiki.
        
        Args:
            wallet_url: The wallet address URL (e.g., https://wallet.example.com/alice)
        
        Returns:
            Wallet address details or None if not found
        """
        try:
            response = self.session.get(wallet_url)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error fetching wallet address: {e}")
            return None
    
    def create_outgoing_payment(
        self,
        wallet_address: str,
        quote_id: str,
        grant_access_token: str
    ) -> Optional[Dict[str, Any]]:
        """
        Create an outgoing payment in Rafiki.
        
        Args:
            wallet_address: The sender's wallet address URL
            quote_id: The quote ID for this payment
            grant_access_token: Access token for the payment grant
        
        Returns:
            Payment details or None if failed
        """
        url = f"{wallet_address}/outgoing-payments"
        
        headers = self.session.headers.copy()
        headers['Authorization'] = f'GNAP {grant_access_token}'
        
        payload = {
            "quoteId": quote_id,
            "grant": {
                "access_token": grant_access_token
            }
        }
        
        try:
            response = requests.post(url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error creating outgoing payment: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"Response: {e.response.text}")
            return None
    
    def create_quote(
        self,
        wallet_address: str,
        receiver: str,
        amount: int,
        asset_code: str = "USD",
        asset_scale: int = 2
    ) -> Optional[Dict[str, Any]]:
        """
        Create a quote for a payment.
        
        Args:
            wallet_address: Sender's wallet address URL
            receiver: Receiver's wallet address URL
            amount: Amount in smallest unit (cents for USD)
            asset_code: Asset code (e.g., "USD")
            asset_scale: Asset scale (2 for USD cents)
        
        Returns:
            Quote details or None if failed
        """
        url = f"{wallet_address}/quotes"
        
        payload = {
            "method": "ilp",
            "walletAddress": receiver,
            "receiveAmount": {
                "value": str(amount),
                "assetCode": asset_code,
                "assetScale": asset_scale
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
    
    def check_payment_status(self, payment_url: str) -> Optional[str]:
        """
        Check the status of an outgoing payment.
        
        Args:
            payment_url: The full URL of the payment
        
        Returns:
            Payment status string or None if error
        """
        try:
            response = self.session.get(payment_url)
            response.raise_for_status()
            data = response.json()
            return data.get('status')
        except requests.exceptions.RequestException as e:
            print(f"Error checking payment status: {e}")
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
    
    def create_quote(self, wallet_address: str, receiver: str, amount: int, **kwargs):
        quote_id = f"quote_{len(self.quotes) + 1}"
        quote = {
            "id": quote_id,
            "walletAddress": wallet_address,
            "receiver": receiver,
            "amount": amount,
            "status": "READY"
        }
        self.quotes[quote_id] = quote
        return quote
    
    def create_outgoing_payment(self, wallet_address: str, quote_id: str, grant_access_token: str):
        payment_id = f"payment_{len(self.payments) + 1}"
        payment = {
            "id": payment_id,
            "walletAddress": wallet_address,
            "quoteId": quote_id,
            "status": "COMPLETED",
            "amountSent": self.quotes.get(quote_id, {}).get("amount", 0)
        }
        self.payments[payment_id] = payment
        return payment
    
    def check_payment_status(self, payment_url: str):
        payment_id = payment_url.split("/")[-1]
        if payment_id in self.payments:
            return "COMPLETED"
        return "UNKNOWN"


def transfer_between_coops(
    source_coop_wallet: str,
    dest_coop_wallet: str,
    amount: float,
    currency: str = "USD",
    rafiki_client: Optional[RafikiClient] = None
) -> Dict[str, Any]:
    """
    Transfer money between two coops using Rafiki.
    
    Args:
        source_coop_wallet: Source coop's wallet address URL
        dest_coop_wallet: Destination coop's wallet address URL
        amount: Amount to transfer (in dollars)
        currency: Currency code
        rafiki_client: Rafiki client instance (uses Mock if None)
    
    Returns:
        Dictionary with transfer result
    """
    if rafiki_client is None:
        rafiki_client = MockRafikiClient()
    
    # Convert amount to smallest unit (cents for USD)
    amount_cents = int(amount * 100)
    
    # Create quote
    quote = rafiki_client.create_quote(
        wallet_address=source_coop_wallet,
        receiver=dest_coop_wallet,
        amount=amount_cents,
        asset_code=currency,
        asset_scale=2
    )
    
    if not quote:
        return {
            "success": False,
            "error": "Failed to create quote",
            "response_code": "91"  # Issuer or switch inoperative
        }
    
    # Create outgoing payment
    payment = rafiki_client.create_outgoing_payment(
        wallet_address=source_coop_wallet,
        quote_id=quote["id"],
        grant_access_token="mock_token"
    )
    
    if not payment:
        return {
            "success": False,
            "error": "Failed to create payment",
            "response_code": "51"  # Insufficient funds
        }
    
    return {
        "success": True,
        "payment_id": payment["id"],
        "status": payment["status"],
        "amount_sent": amount,
        "response_code": "00"  # Approved
    }
