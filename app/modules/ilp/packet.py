"""
ILP Packet Builder Module

Creates and validates ILP packets for Interledger Protocol transactions.
"""

from typing import Dict, Any, Optional
import json
from app.utils.logger import logger


class ILPPacketBuilder:
    """
    Builds ILP packets according to the Interledger Protocol specification.
    """

    def __init__(self):
        self.packet_types = {
            'prepare': 'ilp_prepare',
            'fulfill': 'ilp_fulfill',
            'reject': 'ilp_reject'
        }

    def build_prepare_packet(self, ilp_data: Dict[str, Any], transaction_id: str) -> Dict[str, Any]:
        """
        Build an ILP Prepare packet for initiating a transaction.

        Args:
            ilp_data: Mapped ILP data from ISO message
            transaction_id: Unique transaction identifier

        Returns:
            ILP Prepare packet
        """
        try:
            packet = {
                'type': self.packet_types['prepare'],
                'amount': ilp_data['amount'],
                'destination': ilp_data['destination'],
                'execution_condition': ilp_data['execution_condition'],
                'expires_at': ilp_data['expires_at'],
                'data': json.dumps(ilp_data.get('metadata', {})).encode('utf-8').hex()
            }

            logger.log_transaction(transaction_id, "ilp_prepare_built", {
                "amount": packet['amount'],
                "destination": packet['destination']
            })

            return packet

        except Exception as e:
            logger.log_error("packet_build_error", f"Failed to build ILP Prepare packet: {str(e)}", transaction_id)
            raise

    def build_fulfill_packet(self, fulfillment_data: Dict[str, Any], transaction_id: str) -> Dict[str, Any]:
        """
        Build an ILP Fulfill packet for successful transaction completion.

        Args:
            fulfillment_data: Fulfillment data
            transaction_id: Unique transaction identifier

        Returns:
            ILP Fulfill packet
        """
        packet = {
            'type': self.packet_types['fulfill'],
            'fulfillment': fulfillment_data.get('fulfillment', 'fulfillment_placeholder'),
            'data': fulfillment_data.get('data', b'').hex()
        }

        logger.log_transaction(transaction_id, "ilp_fulfill_built", {"fulfillment": packet['fulfillment']})
        return packet

    def build_reject_packet(self, rejection_data: Dict[str, Any], transaction_id: str) -> Dict[str, Any]:
        """
        Build an ILP Reject packet for failed transactions.

        Args:
            rejection_data: Rejection data
            transaction_id: Unique transaction identifier

        Returns:
            ILP Reject packet
        """
        packet = {
            'type': self.packet_types['reject'],
            'code': rejection_data.get('code', 'T01'),
            'message': rejection_data.get('message', 'Transaction rejected'),
            'data': rejection_data.get('data', b'').hex()
        }

        logger.log_transaction(transaction_id, "ilp_reject_built", {
            "code": packet['code'],
            "message": packet['message']
        })
        return packet

    def parse_response_packet(self, response_data: Dict[str, Any], transaction_id: str) -> Dict[str, Any]:
        """
        Parse an incoming ILP response packet.

        Args:
            response_data: Raw response data from Rafiki
            transaction_id: Unique transaction identifier

        Returns:
            Parsed ILP response
        """
        try:
            packet_type = response_data.get('type')

            if packet_type == self.packet_types['fulfill']:
                logger.log_transaction(transaction_id, "ilp_fulfill_received", {
                    "fulfillment": response_data.get('fulfillment')
                })
                return {
                    'type': 'fulfill',
                    'fulfillment': response_data.get('fulfillment'),
                    'data': bytes.fromhex(response_data.get('data', ''))
                }

            elif packet_type == self.packet_types['reject']:
                logger.log_transaction(transaction_id, "ilp_reject_received", {
                    "code": response_data.get('code'),
                    "message": response_data.get('message')
                })
                return {
                    'type': 'reject',
                    'code': response_data.get('code'),
                    'message': response_data.get('message'),
                    'data': bytes.fromhex(response_data.get('data', ''))
                }

            else:
                logger.log_error("unknown_packet_type", f"Unknown ILP packet type: {packet_type}", transaction_id)
                return {'type': 'unknown'}

        except Exception as e:
            logger.log_error("packet_parse_error", f"Failed to parse ILP response: {str(e)}", transaction_id)
            raise

    def validate_packet(self, packet: Dict[str, Any]) -> bool:
        """
        Validate an ILP packet structure.

        Args:
            packet: ILP packet to validate

        Returns:
            True if valid, False otherwise
        """
        packet_type = packet.get('type')

        if packet_type == self.packet_types['prepare']:
            required_fields = ['amount', 'destination', 'execution_condition', 'expires_at']
        elif packet_type == self.packet_types['fulfill']:
            required_fields = ['fulfillment']
        elif packet_type == self.packet_types['reject']:
            required_fields = ['code', 'message']
        else:
            return False

        for field in required_fields:
            if field not in packet:
                return False

        return True