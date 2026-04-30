"""
Unit Tests for ILP Mapper
"""

import unittest
from app.modules.ilp.mapper import ILPMapper


class TestILPMapper(unittest.TestCase):

    def setUp(self):
        self.mapper = ILPMapper()

    def test_map_iso_to_ilp(self):
        """Test mapping ISO 8583 to ILP."""
        iso_message = {
            'MTI': '0200',
            '2': '4111111111111111',  # PAN
            '4': '000000001000',     # Amount
            '49': '840'              # Currency (USD)
        }

        ilp_data = self.mapper.map_iso_to_ilp(iso_message, "test-tx")

        self.assertIn('amount', ilp_data)
        self.assertIn('destination', ilp_data)
        self.assertEqual(ilp_data['amount'], '1000')
        self.assertEqual(ilp_data['destination'], 'ilp.4111111111111111')

    def test_map_ilp_to_iso_success(self):
        """Test mapping successful ILP response to ISO."""
        ilp_response = {'type': 'ilp_fulfill'}
        original_iso = {'MTI': '0200', '2': '4111111111111111'}

        iso_response = self.mapper.map_ilp_to_iso(ilp_response, original_iso, "test-tx")

        self.assertEqual(iso_response['MTI'], '0210')
        self.assertEqual(iso_response['39'], '00')  # Approved

    def test_map_ilp_to_iso_reject(self):
        """Test mapping rejected ILP response to ISO."""
        ilp_response = {'type': 'ilp_reject', 'code': 'T01'}
        original_iso = {'MTI': '0200', '2': '4111111111111111'}

        iso_response = self.mapper.map_ilp_to_iso(ilp_response, original_iso, "test-tx")

        self.assertEqual(iso_response['MTI'], '0210')
        self.assertEqual(iso_response['39'], '05')  # Declined


if __name__ == '__main__':
    unittest.main()