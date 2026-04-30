"""
ILP Mapper Module

Maps ISO 8583 fields to ILP packet structure.
Handles data transformation and format conversion.
"""

from typing import Dict, Any, Optional
from decimal import Decimal
from app.utils.logger import logger
from app.utils.config import config


class ILPMapper:
    """
    Maps ISO 8583 transaction data to ILP format.
    """

    def __init__(self):
        # ISO 8583 to ILP field mappings
        self.field_mappings = {
            'amount': '4',  # Transaction amount
            'destination': '2',  # Primary Account Number (PAN) -> ILP address
            'merchant_id': '42',  # Card Acceptor ID
            'terminal_id': '41',  # Card Acceptor Terminal ID
            'currency': '49',  # Currency Code
            'transaction_time': '12',  # Local Transaction Time
            'transaction_date': '13',  # Local Transaction Date
            'processing_code': '3',  # Processing Code
            'merchant_category': '18',  # Merchant Type
        }

        # Currency code mappings (ISO 4217 to ILP)
        self.currency_mappings = {
            '840': 'USD',
            '978': 'EUR',
            '826': 'GBP',
            '392': 'JPY',
            # Add more as needed
        }

    def map_iso_to_ilp(self, iso_message: Dict[str, Any], transaction_id: str) -> Dict[str, Any]:
        """
        Transform ISO 8583 message to ILP packet data.

        Args:
            iso_message: Parsed ISO 8583 message
            transaction_id: Unique transaction identifier

        Returns:
            ILP packet data dictionary
        """
        try:
            ilp_data = {}

            # Map amount
            amount = self._map_amount(iso_message)
            if amount:
                ilp_data['amount'] = amount

            # Map destination (PAN to ILP address)
            destination = self._map_destination(iso_message)
            if destination:
                ilp_data['destination'] = destination

            # Map currency
            currency = self._map_currency(iso_message)
            if currency:
                ilp_data['currency'] = currency

            # Map additional metadata
            ilp_data['metadata'] = self._map_metadata(iso_message)

            # Generate execution condition (simplified)
            ilp_data['execution_condition'] = self._generate_execution_condition(iso_message)

            # Set expiration (24 hours from now)
            import time
            ilp_data['expires_at'] = int(time.time() * 1000) + (24 * 60 * 60 * 1000)

            logger.log_transaction(transaction_id, "iso_to_ilp_mapped", {
                "ilp_amount": ilp_data.get('amount'),
                "ilp_destination": ilp_data.get('destination')
            })

            return ilp_data

        except Exception as e:
            logger.log_error("mapping_error", f"Failed to map ISO to ILP: {str(e)}", transaction_id)
            raise

    def map_ilp_to_iso(self, ilp_response: Dict[str, Any], original_iso: Dict[str, Any], transaction_id: str) -> Dict[str, Any]:
        """
        Transform ILP response back to ISO 8583 format.

        Args:
            ilp_response: ILP response data
            original_iso: Original ISO 8583 message for context
            transaction_id: Unique transaction identifier

        Returns:
            ISO 8583 response message
        """
        try:
            iso_response = original_iso.copy()

            # Update MTI for response
            mti = original_iso.get('MTI', '0200')
            if mti == '0200':
                iso_response['MTI'] = '0210'
            elif mti == '0400':
                iso_response['MTI'] = '0410'

            # Map response code
            response_code = self._map_response_code(ilp_response)
            iso_response['39'] = response_code

            # Add authorization code if approved
            if response_code == '00':
                iso_response['38'] = self._generate_auth_code()

            # Update transmission date/time
            import datetime
            now = datetime.datetime.utcnow()
            iso_response['7'] = now.strftime('%m%d%H%M%S')

            logger.log_transaction(transaction_id, "ilp_to_iso_mapped", {
                "response_code": response_code,
                "mti": iso_response.get('MTI')
            })

            return iso_response

        except Exception as e:
            logger.log_error("mapping_error", f"Failed to map ILP to ISO: {str(e)}", transaction_id)
            raise

    def _map_amount(self, iso_message: Dict[str, Any]) -> Optional[str]:
        """Map transaction amount to ILP format."""
        amount_str = iso_message.get(self.field_mappings['amount'])
        if not amount_str:
            return None

        # Convert to integer (remove implied decimals)
        try:
            amount = int(amount_str)
            return str(amount)
        except ValueError:
            return None

    def _map_destination(self, iso_message: Dict[str, Any]) -> Optional[str]:
        """Map PAN to ILP destination address."""
        pan = iso_message.get(self.field_mappings['destination'])
        if not pan:
            return None

        # Convert PAN to ILP address format
        # In practice, this would involve looking up the ILP address for the account
        # For demo, create a simple ILP address
        return f"{config.ilp_address_prefix}{pan}"

    def _map_currency(self, iso_message: Dict[str, Any]) -> Optional[str]:
        """Map currency code to ILP format."""
        currency_code = iso_message.get(self.field_mappings['currency'])
        if not currency_code:
            return config.default_currency

        return self.currency_mappings.get(currency_code, config.default_currency)

    def _map_metadata(self, iso_message: Dict[str, Any]) -> Dict[str, Any]:
        """Map additional metadata for ILP packet."""
        metadata = {}

        # Merchant information
        merchant_id = iso_message.get(self.field_mappings['merchant_id'])
        if merchant_id:
            metadata['merchant_id'] = merchant_id

        terminal_id = iso_message.get(self.field_mappings['terminal_id'])
        if terminal_id:
            metadata['terminal_id'] = terminal_id

        # Transaction details
        processing_code = iso_message.get(self.field_mappings['processing_code'])
        if processing_code:
            metadata['processing_code'] = processing_code

        return metadata

    def _generate_execution_condition(self, iso_message: Dict[str, Any]) -> str:
        """Generate execution condition for ILP packet."""
        # In a real implementation, this would be a cryptographic hash
        # For demo, return a placeholder
        return "execution_condition_placeholder"

    def _map_response_code(self, ilp_response: Dict[str, Any]) -> str:
        """Map ILP response to ISO 8583 response code."""
        # Check ILP response type
        response_type = ilp_response.get('type')

        if response_type == 'ilp_fulfill':
            return '00'  # Approved
        elif response_type == 'ilp_reject':
            # Map rejection reasons to ISO codes
            rejection_reason = ilp_response.get('code', 'T01')
            rejection_mapping = {
                'T01': '05',  # Insufficient funds -> Declined
                'T02': '12',  # Invalid destination -> Invalid transaction
                'T03': '14',  # Expired -> Original amount incorrect
            }
            return rejection_mapping.get(rejection_reason, '05')
        else:
            return '06'  # Error

    def _generate_auth_code(self) -> str:
        """Generate authorization code for approved transactions."""
        import random
        import string
        return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))