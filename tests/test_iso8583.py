"""
Unit Tests for ISO 8583 Parser
"""

import unittest
from app.modules.iso8583.parser import ISO8583Parser


class TestISO8583Parser(unittest.TestCase):

    def setUp(self):
        self.parser = ISO8583Parser()

    def test_parse_valid_message(self):
        """Test parsing a valid ISO 8583 message."""
        # Sample message with MTI 0200, fields 2 and 4
        message = "0200A000000000000000000000000000000000001234567890123456000000001000"
        parsed = self.parser.parse_message(message)

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed['MTI'], '0200')
        self.assertIn('2', parsed)  # PAN field
        self.assertIn('4', parsed)  # Amount field

    def test_parse_invalid_mti(self):
        """Test parsing message with invalid MTI."""
        message = "9999A000000000000000000000000000000000001234567890123456000000001000"
        parsed = self.parser.parse_message(message)

        self.assertIsNone(parsed)

    def test_validate_required_fields(self):
        """Test validation of required fields."""
        # Mock parsed message missing required field
        parsed = {'MTI': '0200', '2': '1234567890123456'}  # Missing amount
        result = self.parser.validate_required_fields(parsed, ['2', '4'])

        self.assertFalse(result)


if __name__ == '__main__':
    unittest.main()