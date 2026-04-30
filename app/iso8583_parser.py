"""
ISO 8583 Message Parser and Builder using pyiso8583 package.
Handles parsing and construction of ISO 8583 financial messages.
"""

import iso8583
from iso8583.specs import default_ascii as spec
from datetime import datetime
from typing import Dict, Optional, Tuple


def create_financial_request(
    source_account: str,
    amount: float,
    currency: str = "840",
    coop_id: str = "",
    stan: str = "",
    rrn: str = ""
) -> Tuple[bytes, Dict[str, str]]:
    """
    Create an ISO 8583 financial request message (0200) using pyiso8583.
    
    Returns:
        Tuple of (raw_bytes, decoded_dict)
    """
    now = datetime.now()
    
    # Create decoded message dictionary
    decoded = {
        't': '0200',  # Message Type Indicator
    }
    
    # Field 2: Primary Account Number (PAN)
    decoded['2'] = source_account
    
    # Field 3: Processing Code (000000 = purchase/transfer)
    decoded['3'] = '000000'
    
    # Field 4: Amount (12 digits, right-justified, zero-filled)
    amount_cents = int(amount * 100)
    decoded['4'] = f"{amount_cents:012d}"
    
    # Field 7: Transmission Date/Time (MMDDhhmmss)
    decoded['7'] = now.strftime("%m%d%H%M%S")
    
    # Field 11: STAN (System Trace Audit Number)
    if not stan:
        stan = f"{now.microsecond % 1000000:06d}"
    decoded['11'] = stan
    
    # Field 12: Local Transaction Time
    decoded['12'] = now.strftime("%H%M%S")
    
    # Field 13: Local Transaction Date
    decoded['13'] = now.strftime("%m%d")
    
    # Field 32: Acquiring Institution ID
    if coop_id:
        decoded['32'] = coop_id
    
    # Field 37: Retrieval Reference Number
    if not rrn:
        rrn = f"{now.strftime('%H%M%S')}{stan}"
    decoded['37'] = rrn[:12].ljust(12, '0')
    
    # Field 49: Currency Code
    decoded['49'] = currency
    
    # Encode to bytes
    encoded_raw, encoded = iso8583.encode(decoded, spec)
    
    return encoded_raw, decoded


def create_response(
    request_decoded: Dict[str, str],
    response_code: str = "00"
) -> Tuple[bytes, Dict[str, str]]:
    """
    Create an ISO 8583 response message from a request.
    
    Args:
        request_decoded: Decoded request message dictionary
        response_code: ISO 8583 response code (field 39)
    
    Returns:
        Tuple of (raw_bytes, decoded_dict)
    """
    # Create response with reversed MTI (0200 -> 0210)
    decoded = {}
    
    # Change MTI from request to response (flip bit for response)
    mti = request_decoded.get('t', '0200')
    if len(mti) == 4:
        # Change position 4: 0=request, 1=response
        mti_list = list(mti)
        mti_list[3] = '0' if mti[3] == '1' else '1'
        decoded['t'] = ''.join(mti_list)
    else:
        decoded['t'] = '0210'
    
    # Echo fields from request (commonly echoed in responses)
    echo_fields = ['2', '3', '4', '11', '32', '37', '49']
    for field in echo_fields:
        if field in request_decoded:
            decoded[field] = request_decoded[field]
    
    # Add response code (field 39)
    decoded['39'] = response_code
    
    # Encode to bytes
    encoded_raw, encoded = iso8583.encode(decoded, spec)
    
    return encoded_raw, decoded


def parse_iso_message(raw_bytes: bytes) -> Tuple[Dict[str, str], Dict[str, dict]]:
    """
    Parse raw ISO 8583 message bytes using pyiso8583.
    
    Returns:
        Tuple of (decoded_dict, encoded_dict)
    """
    try:
        decoded, encoded = iso8583.decode(raw_bytes, spec)
        return decoded, encoded
    except iso8583.Iso8583Error as e:
        raise ValueError(f"ISO 8583 parse error: {e}")


def message_to_dict(decoded: Dict[str, str]) -> Dict[str, any]:
    """
    Convert decoded ISO 8583 message to a friendly dictionary.
    Includes MTI, bitmap info, and all fields.
    """
    result = {
        'mti': decoded.get('t'),
        'bitmap_primary': decoded.get('p'),
        'fields': {}
    }
    
    # Add all data fields (2-128)
    for key, value in decoded.items():
        if key not in ['t', 'p'] and key.isdigit():
            result['fields'][int(key)] = value
    
    return result


def get_response_mti(mti: str) -> Optional[str]:
    """Get the response MTI for a given request MTI."""
    if not mti or len(mti) != 4:
        return None
    
    mti_list = list(mti)
    mti_list[3] = '0' if mti[3] == '1' else '1'
    return ''.join(mti_list)


def pretty_print_message(decoded: Dict[str, str]) -> str:
    """Return a pretty-printed string of the ISO 8583 message."""
    import io
    output = io.StringIO()
    iso8583.pp(decoded, spec, stream=output)
    return output.getvalue()
