"""
ISO 8583 Parser Module

This module handles parsing and validation of ISO 8583 financial messages.
ISO 8583 is a standard for exchanging electronic transaction information.

Key Components:
- MTI: Message Type Indicator (e.g., '0200' for transaction request)
- Bitmap: Indicates which data elements are present
- Data Elements: Up to 128 fields containing transaction data

For beginners: Think of an ISO 8583 message as a structured packet with:
- A header (MTI)
- A map (bitmap) showing what's included
- Fields of data (like amount, account number, etc.)

Note: This is a simplified parser for educational purposes. For production, use a robust library like 'iso8583' or 'py8583'.
"""

from typing import Dict, Any, Optional


class ISO8583Parser:
    """
    Simplified parser for ISO 8583 messages.
    Assumes ASCII encoding and basic bitmap handling.
    """

    def __init__(self):
        # Define common MTI types for validation
        self.valid_mtis = {
            '0200': 'Transaction Request',
            '0210': 'Transaction Response',
            '0400': 'Reversal Request',
            '0410': 'Reversal Response',
            # Add more as needed
        }

        # Simplified field lengths (in characters; real ISO has variable lengths)
        self.field_lengths = {
            '2': 16,  # PAN
            '3': 6,   # Processing Code
            '4': 12,  # Amount
            '7': 10,  # Transmission Date/Time
            '11': 6,  # System Trace Audit Number
            '12': 6,  # Local Transaction Time
            '13': 4,  # Local Transaction Date
            '14': 4,  # Expiration Date
            '18': 4,  # Merchant Type
            '22': 3,  # POS Entry Mode
            '25': 2,  # POS Condition Code
            '32': 11, # Acquiring Institution ID
            '35': 37, # Track 2 Data
            '37': 12, # Retrieval Reference Number
            '41': 8,  # Card Acceptor Terminal ID
            '42': 15, # Card Acceptor ID
            '43': 40, # Card Acceptor Name/Location
            '49': 3,  # Currency Code
            '52': 16, # PIN Data
            '54': 20, # Additional Amounts
            # Add more fields as needed
        }

    def parse_message(self, raw_message: str) -> Optional[Dict[str, Any]]:
        """
        Parse a raw ISO 8583 message.

        Args:
            raw_message: The raw string of the ISO 8583 message

        Returns:
            Parsed message as a dictionary, or None if parsing fails
        """
        try:
            if len(raw_message) < 4:
                return None

            # Extract MTI (first 4 characters)
            mti = raw_message[:4]
            if not self._validate_mti(mti):
                print(f"Invalid MTI: {mti}")
                return None

            parsed = {'MTI': mti}

            # Extract bitmap (16 or 32 characters depending on secondary bitmap)
            bitmap_hex = raw_message[4:20]
            bitmap = self._hex_to_binary(bitmap_hex)
            if bitmap[0] == '1':  # Secondary bitmap present
                bitmap_hex += raw_message[20:36]
                bitmap = self._hex_to_binary(bitmap_hex)
                pos = 36
            else:
                pos = 20
            parsed['bitmap'] = bitmap

            # Parse fields based on bitmap
            for i in range(2, len(bitmap) + 1):  # Fields 2 to 128
                if bitmap[i-1] == '1':
                    field_num = str(i)
                    if field_num in self.field_lengths:
                        length = self.field_lengths[field_num]
                        if pos + length <= len(raw_message):
                            parsed[field_num] = raw_message[pos:pos + length]
                            pos += length
                        else:
                            print(f"Message too short for field {field_num}")
                            return None
                    else:
                        print(f"Unknown field length for {field_num}")
                        return None

            return parsed

        except Exception as e:
            print(f"Error parsing ISO 8583 message: {e}")
            return None

    def _hex_to_binary(self, hex_str: str) -> str:
        """Convert hex string to binary string."""
        return bin(int(hex_str, 16))[2:].zfill(len(hex_str)*4)

    def _validate_mti(self, mti: str) -> bool:
        """
        Validate the Message Type Indicator.

        Args:
            mti: The MTI string

        Returns:
            True if valid, False otherwise
        """
        return mti in self.valid_mtis

    def get_message_type(self, mti: str) -> str:
        """
        Get the human-readable description of an MTI.

        Args:
            mti: The MTI string

        Returns:
            Description of the message type
        """
        return self.valid_mtis.get(mti, 'Unknown')

    def validate_required_fields(self, parsed_message: Dict[str, Any], required_fields: list) -> bool:
        """
        Validate that required fields are present in the message.

        Args:
            parsed_message: The parsed ISO 8583 message
            required_fields: List of required field numbers (as strings)

        Returns:
            True if all required fields are present, False otherwise
        """
        for field in required_fields:
            if field not in parsed_message or not parsed_message[field]:
                print(f"Missing required field: {field}")
                return False
        return True


# Example usage (for testing)
if __name__ == "__main__":
    parser = ISO8583Parser()

    # Sample ISO 8583 message (simplified example; real messages vary)
    # MTI: 0200, Bitmap: A000000000000000 (fields 2 and 4 present), Fields: PAN (16), Amount (12)
    sample_message = "0200A000000000000000000000000000000000001234567890123456000000001000"
    print(f"Message length: {len(sample_message)}")
    print(f"Message: {sample_message}")
    print(f"Field 4 slice: {sample_message[36:48]}")

    parsed = parser.parse_message(sample_message)
    if parsed:
        print("Parsed Message:")
        print(f"MTI: {parsed['MTI']} ({parser.get_message_type(parsed['MTI'])})")
        print(f"Bitmap: {parsed['bitmap']}")
        print("Fields:", parsed)
        # Print some common fields
        if '4' in parsed:
            print(f"Amount: {parsed['4']}")
        if '2' in parsed:
            print(f"PAN: {parsed['2']}")
    else:
        print("Failed to parse message")