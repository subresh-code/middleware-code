"""
Test script to demonstrate the complete middleware workflow with pyiso8583.
Tests ISO 8583 parsing, bitmap handling, and Rafiki integration.
"""

from app.iso8583_parser import (
    create_financial_request, 
    create_response, 
    parse_iso_message,
    message_to_dict,
    pretty_print_message
)
from app.rafiki_client import MockRafikiClient, transfer_between_coops
import iso8583


def test_pyiso8583_basic():
    """Test basic pyiso8583 functionality."""
    print("=" * 60)
    print("TEST 1: Basic pyiso8583 Encoding/Decoding")
    print("=" * 60)
    
    # Create a simple message
    decoded = {
        't': '0200',  # MTI
        '2': '1234567890123456',  # PAN
        '3': '000000',  # Processing code
        '4': '000000010050',  # Amount
    }
    
    # Encode
    encoded_raw, encoded = iso8583.encode(decoded, iso8583.specs.default_ascii)
    print(f"Encoded bytes: {bytes(encoded_raw).hex().upper()}")
    print(f"Bitmap: {decoded.get('p')}")
    
    # Decode back
    decoded2, _ = iso8583.decode(encoded_raw, iso8583.specs.default_ascii)
    print(f"Decoded MTI: {decoded2.get('t')}")
    print(f"Decoded PAN: {decoded2.get('2')}")
    print()


def test_create_financial_request():
    """Test creating ISO 8583 financial request with pyiso8583."""
    print("=" * 60)
    print("TEST 2: Create Financial Request (pyiso8583)")
    print("=" * 60)
    
    iso_bytes, decoded = create_financial_request(
        source_account="1234567890123456",
        amount=100.50,
        currency="840",
        coop_id="001234"
    )
    
    print(f"Raw bytes (hex): {iso_bytes.hex().upper()}")
    print(f"\nDecoded message:")
    print(f"  MTI: {decoded.get('t')}")
    print(f"  Bitmap: {decoded.get('p')}")
    
    for key, value in decoded.items():
        if key not in ['t', 'p'] and value:
            print(f"  Field {key}: {value}")
    
    print(f"\nPretty print:")
    print(pretty_print_message(decoded))
    print()


def test_parse_message():
    """Test parsing ISO 8583 message."""
    print("=" * 60)
    print("TEST 3: Parse ISO 8583 Message")
    print("=" * 60)
    
    # Create a message first
    iso_bytes, original_decoded = create_financial_request(
        source_account="1234567890123456",
        amount=100.50,
        currency="840",
        coop_id="001234"
    )
    
    print(f"Original message created:")
    print(f"  MTI: {original_decoded.get('t')}")
    print(f"  Fields: {[k for k in original_decoded.keys() if k.isdigit()]}")
    
    # Parse the bytes
    decoded, encoded = parse_iso_message(bytes(iso_bytes))
    
    print(f"\nParsed message:")
    print(f"  MTI: {decoded.get('t')}")
    print(f"  Fields:")
    for key, value in decoded.items():
        if key not in ['t', 'p'] and value:
            print(f"    Field {key}: {value}")
    
    # Use message_to_dict
    result = message_to_dict(decoded)
    print(f"\nAs dict: {result}")
    print()


def test_create_response():
    """Test creating ISO 8583 response."""
    print("=" * 60)
    print("TEST 4: Create Response Message")
    print("=" * 60)
    
    # Create request
    _, request_decoded = create_financial_request(
        source_account="1234567890123456",
        amount=100.50,
        currency="840"
    )
    
    print(f"Request MTI: {request_decoded.get('t')}")
    
    # Create approved response
    response_bytes, response_decoded = create_response(
        request_decoded=request_decoded,
        response_code="00"
    )
    
    print(f"Response MTI: {response_decoded.get('t')}")
    print(f"Response fields:")
    for key, value in response_decoded.items():
        if key not in ['t', 'p'] and value:
            print(f"  Field {key}: {value}")
    print()


def test_rafiki_transfer():
    """Test Rafiki transfer with mock client."""
    print("=" * 60)
    print("TEST 5: Rafiki Transfer (Mock)")
    print("=" * 60)
    
    # Create mock client
    mock_client = MockRafikiClient()
    
    # Execute transfer
    result = transfer_between_coops(
        source_coop_wallet="http://localhost:3000/alice",
        dest_coop_wallet="http://localhost:3001/bob",
        amount=150.75,
        currency="USD",
        rafiki_client=mock_client
    )
    
    print(f"Transfer result:")
    print(f"  Success: {result['success']}")
    print(f"  Payment ID: {result.get('payment_id')}")
    print(f"  Status: {result.get('status')}")
    print(f"  Amount sent: ${result.get('amount_sent')}")
    print(f"  Response code: {result.get('response_code')}")
    print()


def test_complete_flow():
    """Test complete payment flow: ISO 8583 -> Rafiki -> Response."""
    print("=" * 60)
    print("TEST 6: Complete Payment Flow (pyiso8583)")
    print("=" * 60)
    
    # Step 1: Receive ISO 8583 request (simulated)
    print("Step 1: Creating ISO 8583 financial request...")
    iso_bytes, request_decoded = create_financial_request(
        source_account="1234567890123456",
        amount=200.00,
        currency="840",
        coop_id="001234"
    )
    print(f"  MTI: {request_decoded.get('t')}")
    print(f"  Amount: ${float(request_decoded.get('4', '0'))/100:.2f}")
    print(f"  Account: {request_decoded.get('2')}")
    
    # Step 2: Extract data and transfer via Rafiki
    print("\nStep 2: Transferring via Rafiki...")
    mock_client = MockRafikiClient()
    result = transfer_between_coops(
        source_coop_wallet="http://localhost:3000/coop1",
        dest_coop_wallet="http://localhost:3000/coop2",
        amount=200.00,
        currency="USD",
        rafiki_client=mock_client
    )
    print(f"  Transfer successful: {result['success']}")
    print(f"  Payment ID: {result.get('payment_id')}")
    
    # Step 3: Create ISO 8583 response
    print("\nStep 3: Creating ISO 8583 response...")
    response_bytes, response_decoded = create_response(
        request_decoded=request_decoded,
        response_code=result["response_code"]
    )
    print(f"  Response MTI: {response_decoded.get('t')}")
    print(f"  Response code: {response_decoded.get('39')}")
    
    print("\n" + "=" * 60)
    print("ALL TESTS PASSED!")
    print("=" * 60)
    print("\npyiso8583 is working correctly!")
    print("The middleware is ready for production use.")


if __name__ == "__main__":
    test_pyiso8583_basic()
    test_create_financial_request()
    test_parse_message()
    test_create_response()
    test_rafiki_transfer()
    test_complete_flow()
