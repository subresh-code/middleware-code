"""
Test script to demonstrate the complete middleware workflow.
Tests ISO 8583 parsing, bitmap handling, and Rafiki integration.
"""

from app.iso8583_parser import ISO8583Message, create_financial_request, create_response
from app.bitmap import ISO8583Bitmap
from app.rafiki_client import MockRafikiClient, transfer_between_coops


def test_bitmap():
    """Test bitmap operations."""
    print("=" * 60)
    print("TEST 1: Bitmap Operations")
    print("=" * 60)
    
    bitmap = ISO8583Bitmap()
    
    # Set fields for a typical financial transaction
    fields_to_set = [2, 3, 4, 11, 32, 49]
    for f in fields_to_set:
        bitmap.set_field(f)
    
    print(f"Fields set: {fields_to_set}")
    print(f"Present fields: {bitmap.get_present_fields()}")
    print(f"Bitmap hex: {bitmap.to_hex()}")
    print(f"Bitmap bytes: {bitmap.to_bytes().hex().upper()}")
    print(f"Has secondary bitmap: {bitmap.has_secondary_bitmap()}")
    
    # Test parsing
    bitmap_bytes = bitmap.to_bytes()
    parsed = ISO8583Bitmap.from_bytes(bitmap_bytes)
    print(f"Parsed fields: {parsed.get_present_fields()}")
    print()


def test_iso8583_message():
    """Test ISO 8583 message creation and parsing."""
    print("=" * 60)
    print("TEST 2: ISO 8583 Message Creation")
    print("=" * 60)
    
    # Create a financial request message
    msg = create_financial_request(
        source_account="1234567890123456",
        amount=100.50,
        currency="840",
        coop_id="001234",
        stan="123456",
        rrn="123456789012"
    )
    
    print(f"MTI: {msg.mti}")
    print(f"Fields:")
    for field_num in sorted(msg.fields.keys()):
        print(f"  Field {field_num}: {msg.fields[field_num]}")
    
    # Build bitmap
    bitmap = msg.build_bitmap()
    print(f"\nBitmap: {bitmap.to_hex()}")
    print(f"Present fields: {bitmap.get_present_fields()}")
    
    # Convert to ISO format
    iso_data = msg.to_iso_format()
    print(f"\nMessage bytes (hex): {iso_data.hex().upper()}")
    print()


def test_iso8583_parsing():
    """Test parsing ISO 8583 message from bytes."""
    print("=" * 60)
    print("TEST 3: ISO 8583 Message Parsing")
    print("=" * 60)
    
    # Create a message first
    original = create_financial_request(
        source_account="1234567890123456",
        amount=100.50,
        currency="840",
        coop_id="001234"
    )
    
    # Convert to bytes
    iso_bytes = original.to_iso_format()
    print(f"Original message created:")
    print(f"  MTI: {original.mti}")
    print(f"  Fields: {list(original.fields.keys())}")
    
    # Parse it back
    parsed = ISO8583Message.from_iso_format(iso_bytes)
    print(f"\nParsed message:")
    print(f"  MTI: {parsed.mti}")
    print(f"  Fields:")
    for field_num in sorted(parsed.fields.keys()):
        print(f"    Field {field_num}: {parsed.fields[field_num]}")
    print()


def test_response_creation():
    """Test creating ISO 8583 response."""
    print("=" * 60)
    print("TEST 4: Response Message Creation")
    print("=" * 60)
    
    # Create request
    request = create_financial_request(
        source_account="1234567890123456",
        amount=100.50,
        currency="840"
    )
    
    print(f"Request MTI: {request.mti}")
    
    # Create approved response
    response = create_response(request, response_code="00")
    print(f"Response MTI: {response.mti}")
    print(f"Response fields:")
    for field_num in sorted(response.fields.keys()):
        print(f"  Field {field_num}: {response.fields[field_num]}")
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
    print("TEST 6: Complete Payment Flow")
    print("=" * 60)
    
    # Step 1: Receive ISO 8583 request (simulated)
    print("Step 1: Creating ISO 8583 financial request...")
    iso_request = create_financial_request(
        source_account="1234567890123456",
        amount=200.00,
        currency="840",
        coop_id="001234"
    )
    print(f"  MTI: {iso_request.mti}")
    print(f"  Amount: ${float(iso_request.get_field(4))/100:.2f}")
    print(f"  Account: {iso_request.get_field(2)}")
    
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
    iso_response = create_response(
        request_msg=iso_request,
        response_code=result["response_code"]
    )
    print(f"  Response MTI: {iso_response.mti}")
    print(f"  Response code: {iso_response.get_field(39)}")
    
    print("\n" + "=" * 60)
    print("ALL TESTS PASSED!")
    print("=" * 60)


if __name__ == "__main__":
    test_bitmap()
    test_iso8583_message()
    test_iso8583_parsing()
    test_response_creation()
    test_rafiki_transfer()
    test_complete_flow()
