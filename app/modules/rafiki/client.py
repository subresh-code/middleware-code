"""
Rafiki Client Module

Handles communication with Rafiki ILP implementation via REST API.
Includes authentication, retries, and error handling.
"""

import requests
import time
from typing import Dict, Any, Optional
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from app.utils.logger import logger
from app.utils.config import config


class RafikiClient:
    """
    HTTP client for interacting with Rafiki's ILP API.
    """

    def __init__(self):
        self.base_url = config.rafiki_base_url.rstrip('/')
        self.api_key = config.rafiki_api_key
        self.timeout = config.rafiki_timeout

        # Setup session with retry strategy
        self.session = requests.Session()
        retry_strategy = Retry(
            total=config.max_retries,
            status_forcelist=[429, 500, 502, 503, 504],
            backoff_factor=config.retry_delay,
            allowed_methods=["HEAD", "GET", "PUT", "DELETE", "OPTIONS", "TRACE", "POST"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        # Set default headers
        self.session.headers.update({
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json',
            'User-Agent': 'Middleware-ILP-Client/1.0'
        })

    def send_ilp_packet(self, packet: Dict[str, Any], transaction_id: str) -> Dict[str, Any]:
        """
        Send an ILP packet to Rafiki and return the response.

        Args:
            packet: ILP packet to send
            transaction_id: Unique transaction identifier

        Returns:
            ILP response packet
        """
        endpoint = f"{self.base_url}/ilp"
        start_time = time.time()

        try:
            logger.log_transaction(transaction_id, "rafiki_request_started", {
                "endpoint": endpoint,
                "packet_type": packet.get('type')
            })

            response = self.session.post(
                endpoint,
                json=packet,
                timeout=self.timeout
            )

            duration = time.time() - start_time
            logger.log_api_call(endpoint, "POST", response.status_code, duration)

            response.raise_for_status()

            response_data = response.json()

            logger.log_transaction(transaction_id, "rafiki_response_received", {
                "status_code": response.status_code,
                "response_type": response_data.get('type')
            })

            return response_data

        except requests.exceptions.Timeout:
            logger.log_error("timeout_error", f"Rafiki API timeout after {self.timeout}s", transaction_id)
            raise
        except requests.exceptions.ConnectionError:
            logger.log_error("connection_error", "Failed to connect to Rafiki API", transaction_id)
            raise
        except requests.exceptions.HTTPError as e:
            logger.log_error("http_error", f"Rafiki API error: {e.response.status_code} - {e.response.text}", transaction_id)
            raise
        except Exception as e:
            logger.log_error("api_error", f"Unexpected error calling Rafiki API: {str(e)}", transaction_id)
            raise

    def get_account_balance(self, account_id: str) -> Dict[str, Any]:
        """
        Get account balance from Rafiki.

        Args:
            account_id: ILP account identifier

        Returns:
            Balance information
        """
        endpoint = f"{self.base_url}/accounts/{account_id}/balance"

        try:
            response = self.session.get(endpoint, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.log_error("balance_check_error", f"Failed to get balance: {str(e)}")
            raise

    def get_transaction_status(self, transaction_id: str) -> Dict[str, Any]:
        """
        Get transaction status from Rafiki.

        Args:
            transaction_id: Transaction identifier

        Returns:
            Transaction status
        """
        endpoint = f"{self.base_url}/transactions/{transaction_id}"

        try:
            response = self.session.get(endpoint, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.log_error("status_check_error", f"Failed to get transaction status: {str(e)}", transaction_id)
            raise

    def health_check(self) -> bool:
        """
        Perform health check on Rafiki API.

        Returns:
            True if healthy, False otherwise
        """
        try:
            response = self.session.get(f"{self.base_url}/health", timeout=5)
            return response.status_code == 200
        except Exception:
            return False