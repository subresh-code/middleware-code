"""
Orchestrator Module

Central controller that coordinates the entire middleware workflow.
Manages the flow from ISO 8583 reception to ILP processing and back.
"""

import uuid
from typing import Dict, Any, Optional
from app.utils.logger import logger
from app.modules.iso8583.parser import ISO8583Parser
from app.modules.iso8583.validator import ISO8583Validator
from app.modules.ilp.mapper import ILPMapper
from app.modules.ilp.packet import ILPPacketBuilder
from app.modules.rafiki.client import RafikiClient


class MiddlewareOrchestrator:
    """
    Orchestrates the complete middleware workflow.
    """

    def __init__(self):
        self.parser = ISO8583Parser()
        self.validator = ISO8583Validator()
        self.mapper = ILPMapper()
        self.packet_builder = ILPPacketBuilder()
        self.rafiki_client = RafikiClient()

    async def process_transaction(self, raw_iso_message: str) -> str:
        """
        Process a complete transaction from ISO 8583 to ILP and back.

        Args:
            raw_iso_message: Raw ISO 8583 message string

        Returns:
            Raw ISO 8583 response message
        """
        transaction_id = str(uuid.uuid4())

        try:
            logger.log_transaction(transaction_id, "transaction_started", {
                "message_length": len(raw_iso_message)
            })

            # Step 1: Parse ISO 8583 message
            parsed_iso = self._parse_iso_message(raw_iso_message, transaction_id)
            if not parsed_iso:
                return self._build_error_response(parsed_iso, "96")  # System malfunction

            # Step 2: Validate ISO 8583 message
            validation_result = self._validate_iso_message(parsed_iso, transaction_id)
            if not validation_result["valid"]:
                error_code = "12"  # Invalid transaction
                logger.log_error("validation_failed", f"Validation errors: {validation_result['errors']}", transaction_id)
                return self._build_error_response(parsed_iso, error_code)

            # Step 3: Map ISO to ILP
            ilp_data = self._map_iso_to_ilp(parsed_iso, transaction_id)

            # Step 4: Build ILP packet
            ilp_packet = self._build_ilp_packet(ilp_data, transaction_id)

            # Step 5: Send to Rafiki
            rafiki_response = self._send_to_rafiki(ilp_packet, transaction_id)

            # Step 6: Map ILP response back to ISO
            iso_response = self._map_ilp_to_iso(rafiki_response, parsed_iso, transaction_id)

            # Step 7: Serialize ISO response
            raw_response = self._serialize_iso_response(iso_response, transaction_id)

            logger.log_transaction(transaction_id, "transaction_completed", {
                "response_mti": iso_response.get('MTI'),
                "response_code": iso_response.get('39')
            })

            return raw_response

        except Exception as e:
            logger.log_error("orchestrator_error", f"Transaction processing failed: {str(e)}", transaction_id)
            # Return generic error response
            return self._build_generic_error_response()

    def _parse_iso_message(self, raw_message: str, transaction_id: str) -> Optional[Dict[str, Any]]:
        """Parse ISO 8583 message."""
        try:
            parsed = self.parser.parse_message(raw_message)
            if parsed:
                logger.log_transaction(transaction_id, "iso_parsed", {"mti": parsed.get('MTI')})
            return parsed
        except Exception as e:
            logger.log_error("parse_error", str(e), transaction_id)
            return None

    def _validate_iso_message(self, parsed_message: Dict[str, Any], transaction_id: str) -> Dict[str, Any]:
        """Validate parsed ISO 8583 message."""
        return self.validator.validate_message(parsed_message, transaction_id)

    def _map_iso_to_ilp(self, iso_message: Dict[str, Any], transaction_id: str) -> Dict[str, Any]:
        """Map ISO 8583 to ILP format."""
        return self.mapper.map_iso_to_ilp(iso_message, transaction_id)

    def _build_ilp_packet(self, ilp_data: Dict[str, Any], transaction_id: str) -> Dict[str, Any]:
        """Build ILP packet."""
        return self.packet_builder.build_prepare_packet(ilp_data, transaction_id)

    def _send_to_rafiki(self, ilp_packet: Dict[str, Any], transaction_id: str) -> Dict[str, Any]:
        """Send ILP packet to Rafiki."""
        return self.rafiki_client.send_ilp_packet(ilp_packet, transaction_id)

    def _map_ilp_to_iso(self, rafiki_response: Dict[str, Any], original_iso: Dict[str, Any], transaction_id: str) -> Dict[str, Any]:
        """Map ILP response back to ISO 8583."""
        parsed_response = self.packet_builder.parse_response_packet(rafiki_response, transaction_id)
        return self.mapper.map_ilp_to_iso(parsed_response, original_iso, transaction_id)

    def _serialize_iso_response(self, iso_response: Dict[str, Any], transaction_id: str) -> str:
        """Serialize ISO 8583 response to raw format."""
        # This would use the parser's serialization method
        # For now, return a placeholder
        logger.log_transaction(transaction_id, "iso_serialized", {"mti": iso_response.get('MTI')})
        return "0210..."  # Placeholder

    def _build_error_response(self, original_iso: Dict[str, Any], error_code: str) -> str:
        """Build error response for ISO 8583."""
        # Create error response based on original message
        error_response = original_iso.copy() if original_iso else {}
        error_response['MTI'] = '0210'  # Response MTI
        error_response['39'] = error_code  # Response code
        return "0210..."  # Placeholder

    def _build_generic_error_response(self) -> str:
        """Build generic error response."""
        return "021006..."  # Generic error