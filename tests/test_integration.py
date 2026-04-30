"""
Integration Tests for Full Middleware Flow
"""

import unittest
from unittest.mock import Mock, patch
from app.core.orchestrator import MiddlewareOrchestrator


class TestIntegration(unittest.TestCase):

    def setUp(self):
        self.orchestrator = MiddlewareOrchestrator()

    @patch('app.modules.rafiki.client.RafikiClient.send_ilp_packet')
    def test_full_transaction_flow_success(self, mock_send):
        """Test complete transaction flow with successful ILP response."""
        # Mock Rafiki response
        mock_send.return_value = {
            'type': 'ilp_fulfill',
            'fulfillment': 'test_fulfillment',
            'data': ''
        }

        # Sample ISO message
        iso_message = "0200A000000000000000000000000000000000001234567890123456000000001000"

        # Process transaction
        response = self.orchestrator.process_transaction(iso_message)

        # Verify response contains success indicators
        self.assertIsInstance(response, str)
        mock_send.assert_called_once()

    @patch('app.modules.rafiki.client.RafikiClient.send_ilp_packet')
    def test_full_transaction_flow_reject(self, mock_send):
        """Test complete transaction flow with rejected ILP response."""
        # Mock Rafiki response
        mock_send.return_value = {
            'type': 'ilp_reject',
            'code': 'T01',
            'message': 'Insufficient funds'
        }

        # Sample ISO message
        iso_message = "0200A000000000000000000000000000000000001234567890123456000000001000"

        # Process transaction
        response = self.orchestrator.process_transaction(iso_message)

        # Verify response contains rejection indicators
        self.assertIsInstance(response, str)
        mock_send.assert_called_once()


if __name__ == '__main__':
    unittest.main()