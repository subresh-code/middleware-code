"""
ISO 8583 Validator Module

Validates parsed ISO 8583 messages against business rules and requirements.
Ensures message integrity and compliance with financial standards.
"""

from typing import Dict, Any, List, Optional
from app.utils.logger import logger


class ISO8583Validator:
    """
    Validator for ISO 8583 messages with configurable rules.
    """

    def __init__(self):
        # Required fields for different MTI types
        self.required_fields = {
            '0200': ['2', '3', '4', '7', '11', '12', '13', '18', '22', '25', '32', '37', '41', '42', '43', '49'],  # Transaction request
            '0210': ['3', '4', '7', '11', '12', '13', '18', '32', '37', '38', '39', '41', '42', '43', '49'],  # Transaction response
            '0400': ['2', '3', '4', '7', '11', '12', '13', '18', '32', '37', '41', '42', '43', '49'],  # Reversal request
            '0410': ['3', '4', '7', '11', '12', '13', '18', '32', '37', '38', '39', '41', '42', '43', '49'],  # Reversal response
        }

        # Field validation rules
        self.field_validators = {
            '2': self._validate_pan,  # Primary Account Number
            '3': self._validate_processing_code,
            '4': self._validate_amount,
            '7': self._validate_transmission_date_time,
            '11': self._validate_system_trace_number,
            '12': self._validate_local_transaction_time,
            '13': self._validate_local_transaction_date,
            '18': self._validate_merchant_type,
            '22': self._validate_pos_entry_mode,
            '25': self._validate_pos_condition_code,
            '32': self._validate_acquiring_institution,
            '37': self._validate_retrieval_reference_number,
            '38': self._validate_authorization_code,
            '39': self._validate_response_code,
            '41': self._validate_terminal_id,
            '42': self._validate_merchant_id,
            '43': self._validate_merchant_location,
            '49': self._validate_currency_code,
        }

    def validate_message(self, parsed_message: Dict[str, Any], transaction_id: str) -> Dict[str, Any]:
        """
        Validate a parsed ISO 8583 message.

        Args:
            parsed_message: Parsed ISO 8583 message
            transaction_id: Unique transaction identifier for logging

        Returns:
            Validation result with success status and error details
        """
        errors = []

        # Check MTI
        mti = parsed_message.get('MTI')
        if not mti:
            errors.append("Missing MTI")
            return {"valid": False, "errors": errors}

        # Check required fields
        required = self.required_fields.get(mti, [])
        for field in required:
            if field not in parsed_message or not parsed_message[field]:
                errors.append(f"Missing required field: {field}")

        # Validate individual fields
        for field, value in parsed_message.items():
            if field in self.field_validators and value:
                validator = self.field_validators[field]
                try:
                    if not validator(value):
                        errors.append(f"Invalid field {field}: {value}")
                except Exception as e:
                    errors.append(f"Validation error for field {field}: {str(e)}")

        # Log validation result
        if errors:
            logger.log_error("validation_error", f"ISO8583 validation failed: {errors}", transaction_id)
            return {"valid": False, "errors": errors}
        else:
            logger.log_transaction(transaction_id, "iso8583_validated", {"mti": mti})
            return {"valid": True, "errors": []}

    def _validate_pan(self, value: str) -> bool:
        """Validate Primary Account Number (PAN)."""
        # PAN should be 13-19 digits
        return len(value) >= 13 and len(value) <= 19 and value.isdigit()

    def _validate_processing_code(self, value: str) -> bool:
        """Validate Processing Code."""
        return len(value) == 6 and value.isdigit()

    def _validate_amount(self, value: str) -> bool:
        """Validate Transaction Amount."""
        # Amount should be numeric, typically 12 digits with implied decimals
        return len(value) == 12 and value.isdigit() and int(value) > 0

    def _validate_transmission_date_time(self, value: str) -> bool:
        """Validate Transmission Date/Time (MMDDHHMMSS)."""
        return len(value) == 10 and value.isdigit()

    def _validate_system_trace_number(self, value: str) -> bool:
        """Validate System Trace Audit Number."""
        return len(value) == 6 and value.isdigit()

    def _validate_local_transaction_time(self, value: str) -> bool:
        """Validate Local Transaction Time (HHMMSS)."""
        return len(value) == 6 and value.isdigit()

    def _validate_local_transaction_date(self, value: str) -> bool:
        """Validate Local Transaction Date (MMDD)."""
        return len(value) == 4 and value.isdigit()

    def _validate_merchant_type(self, value: str) -> bool:
        """Validate Merchant Type (MCC)."""
        return len(value) == 4 and value.isdigit()

    def _validate_pos_entry_mode(self, value: str) -> bool:
        """Validate POS Entry Mode."""
        return len(value) == 3 and value.isdigit()

    def _validate_pos_condition_code(self, value: str) -> bool:
        """Validate POS Condition Code."""
        return len(value) == 2 and value.isdigit()

    def _validate_acquiring_institution(self, value: str) -> bool:
        """Validate Acquiring Institution ID."""
        return len(value) >= 3 and len(value) <= 11 and value.isdigit()

    def _validate_retrieval_reference_number(self, value: str) -> bool:
        """Validate Retrieval Reference Number."""
        return len(value) == 12

    def _validate_authorization_code(self, value: str) -> bool:
        """Validate Authorization Identification Response."""
        return len(value) == 6

    def _validate_response_code(self, value: str) -> bool:
        """Validate Response Code."""
        # Common response codes: 00=Approved, 05=Declined, etc.
        valid_codes = ['00', '01', '03', '04', '05', '12', '14', '25', '30', '41', '43', '51', '54', '57', '58']
        return value in valid_codes

    def _validate_terminal_id(self, value: str) -> bool:
        """Validate Card Acceptor Terminal ID."""
        return len(value) == 8

    def _validate_merchant_id(self, value: str) -> bool:
        """Validate Card Acceptor ID."""
        return len(value) == 15

    def _validate_merchant_location(self, value: str) -> bool:
        """Validate Card Acceptor Name/Location."""
        return len(value) <= 40

    def _validate_currency_code(self, value: str) -> bool:
        """Validate Currency Code."""
        # ISO 4217 currency codes
        return len(value) == 3 and value.isdigit()