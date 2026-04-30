"""
ISO 8583 Message Parser and Builder
Handles parsing and construction of ISO 8583 financial messages.
"""

class ISO8583Message:
    """Represents an ISO 8583 message with MTI and data fields."""
    
    # Field definitions: (field_number, length_type, max_length, data_type)
    # length_type: 'fixed' or 'variable'
    # data_type: 'n' (numeric), 'an' (alphanumeric), 'ans' (alphanumeric special), 'b' (binary)
    FIELD_DEFINITIONS = {
        0: {'name': 'MTI', 'type': 'fixed', 'length': 4, 'format': 'an'},
        2: {'name': 'Primary Account Number', 'type': 'variable', 'length': 19, 'format': 'n'},
        3: {'name': 'Processing Code', 'type': 'fixed', 'length': 6, 'format': 'n'},
        4: {'name': 'Amount, Transaction', 'type': 'fixed', 'length': 12, 'format': 'n'},
        7: {'name': 'Transmission Date/Time', 'type': 'fixed', 'length': 10, 'format': 'n'},
        11: {'name': 'System Trace Audit Number', 'type': 'fixed', 'length': 6, 'format': 'n'},
        12: {'name': 'Local Transaction Time', 'type': 'fixed', 'length': 6, 'format': 'n'},
        13: {'name': 'Local Transaction Date', 'type': 'fixed', 'length': 4, 'format': 'n'},
        32: {'name': 'Acquiring Institution ID', 'type': 'variable', 'length': 11, 'format': 'n'},
        37: {'name': 'Retrieval Reference Number', 'type': 'fixed', 'length': 12, 'format': 'an'},
        41: {'name': 'Card Acceptor Terminal ID', 'type': 'fixed', 'length': 8, 'format': 'ans'},
        42: {'name': 'Card Acceptor ID', 'type': 'fixed', 'length': 15, 'format': 'ans'},
        43: {'name': 'Card Acceptor Name/Location', 'type': 'variable', 'length': 40, 'format': 'ans'},
        49: {'name': 'Currency Code', 'type': 'fixed', 'length': 3, 'format': 'n'},
        90: {'name': 'Original Data Elements', 'type': 'fixed', 'length': 42, 'format': 'an'},
    }
    
    def __init__(self, mti=None):
        self.mti = mti  # Message Type Indicator (4 digits)
        self.fields = {}  # field_number -> value
        self.bitmap = None
    
    def set_field(self, field_number, value):
        """Set a data field value."""
        if field_number < 1 or field_number > 128:
            raise ValueError(f"Invalid field number: {field_number}")
        self.fields[field_number] = str(value)
    
    def get_field(self, field_number):
        """Get a data field value."""
        return self.fields.get(field_number)
    
    def has_field(self, field_number):
        """Check if a field is present."""
        return field_number in self.fields
    
    def build_bitmap(self):
        """Build bitmap from present fields."""
        from app.bitmap import ISO8583Bitmap
        bitmap = ISO8583Bitmap()
        
        for field_num in self.fields.keys():
            if field_num != 0:  # Skip MTI
                bitmap.set_field(field_num)
        
        self.bitmap = bitmap
        return bitmap
    
    def to_iso_format(self):
        """
        Convert message to ISO 8583 format.
        Returns bytes ready for transmission.
        """
        if not self.mti:
            raise ValueError("MTI is required")
        
        # Build bitmap if not already built
        if not self.bitmap:
            self.build_bitmap()
        
        # Start with MTI (4 bytes ASCII)
        result = self.mti.encode('ascii')
        
        # Add bitmap
        result += self.bitmap.to_bytes()
        
        # Add field data
        for field_num in sorted(self.fields.keys()):
            if field_num == 0:  # Skip MTI (already added)
                continue
            
            value = self.fields[field_num]
            field_def = self.FIELD_DEFINITIONS.get(field_num, {})
            
            if field_def.get('type') == 'variable':
                # Variable length: add length indicator (2 digits)
                length = len(value)
                result += f"{length:02d}".encode('ascii')
            
            # Add field value
            result += value.encode('ascii')
        
        return result
    
    @classmethod
    def from_iso_format(cls, data):
        """
        Parse ISO 8583 message from bytes.
        """
        from app.bitmap import ISO8583Bitmap
        
        msg = cls()
        
        # Extract MTI (first 4 bytes)
        if len(data) < 4:
            raise ValueError("Message too short for MTI")
        msg.mti = data[0:4].decode('ascii')
        
        # Extract bitmap (at least 8 bytes after MTI)
        if len(data) < 12:  # 4 (MTI) + 8 (bitmap)
            raise ValueError("Message too short for bitmap")
        
        bitmap_data = data[4:12]
        # Check if secondary bitmap needed
        if bitmap_data[0] & 0x80:
            if len(data) < 20:
                raise ValueError("Message too short for secondary bitmap")
            bitmap_data = data[4:20]
        
        msg.bitmap = ISO8583Bitmap.from_bytes(bitmap_data)
        
        # Parse fields based on bitmap
        offset = 4 + len(bitmap_data)
        present_fields = msg.bitmap.get_present_fields()
        
        for field_num in sorted(present_fields):
            if offset >= len(data):
                break
            
            field_def = cls.FIELD_DEFINITIONS.get(field_num, {})
            
            if field_def.get('type') == 'variable':
                # Read length indicator (2 bytes)
                if offset + 2 > len(data):
                    raise ValueError(f"Unexpected end of data at field {field_num}")
                length = int(data[offset:offset+2].decode('ascii'))
                offset += 2
                
                # Read field value
                if offset + length > len(data):
                    raise ValueError(f"Unexpected end of data at field {field_num}")
                value = data[offset:offset+length].decode('ascii')
                offset += length
            else:
                # Fixed length
                length = field_def.get('length', 0)
                if offset + length > len(data):
                    raise ValueError(f"Unexpected end of data at field {field_num}")
                value = data[offset:offset+length].decode('ascii')
                offset += length
            
            msg.fields[field_num] = value
        
        return msg
    
    def get_response_mti(self):
        """Get the response MTI for this message."""
        if not self.mti:
            return None
        
        # Change response bit (position 3: 0=request, 1=response)
        response_mti = list(self.mti)
        if len(response_mti) == 4:
            response_mti[3] = '0' if self.mti[3] == '1' else '1'
            return ''.join(response_mti)
        return None
    
    def __str__(self):
        """String representation of the message."""
        lines = [f"MTI: {self.mti}"]
        if self.bitmap:
            lines.append(f"Bitmap: {self.bitmap.to_hex()}")
        for field_num in sorted(self.fields.keys()):
            field_name = self.FIELD_DEFINITIONS.get(field_num, {}).get('name', f'Field {field_num}')
            lines.append(f"  Field {field_num} ({field_name}): {self.fields[field_num]}")
        return "\n".join(lines)


def create_financial_request(source_account, amount, currency="840", coop_id="", stan="", rrn=""):
    """Create an ISO 8583 financial request message (0200)."""
    import datetime
    
    msg = ISO8583Message(mti="0200")
    
    # Field 2: Primary Account Number (source)
    msg.set_field(2, source_account)
    
    # Field 3: Processing Code (000000 = purchase/transfer)
    msg.set_field(3, "000000")
    
    # Field 4: Amount (12 digits, right-justified, zero-filled)
    amount_formatted = f"{int(amount * 100):012d}"  # Convert to cents
    msg.set_field(4, amount_formatted)
    
    # Field 7: Transmission Date/Time (MMDDhhmmss)
    now = datetime.datetime.now()
    msg.set_field(7, now.strftime("%m%d%H%M%S"))
    
    # Field 11: STAN (System Trace Audit Number)
    if not stan:
        stan = f"{now.microsecond % 1000000:06d}"
    msg.set_field(11, stan)
    
    # Field 12: Local Transaction Time
    msg.set_field(12, now.strftime("%H%M%S"))
    
    # Field 13: Local Transaction Date
    msg.set_field(13, now.strftime("%m%d"))
    
    # Field 32: Acquiring Institution ID (coop ID)
    if coop_id:
        msg.set_field(32, coop_id)
    
    # Field 37: Retrieval Reference Number
    if not rrn:
        rrn = f"{now.strftime('%H%M%S')}{stan}"
    msg.set_field(37, rrn[:12].ljust(12, '0'))
    
    # Field 49: Currency Code
    msg.set_field(49, currency)
    
    return msg


def create_response(request_msg, response_code="00", additional_fields=None):
    """Create an ISO 8583 response message."""
    msg = ISO8583Message(mti=request_msg.get_response_mti())
    
    # Copy fields from request that should be echoed
    echo_fields = [2, 3, 4, 11, 32, 37, 49]
    for field_num in echo_fields:
        if request_msg.has_field(field_num):
            msg.set_field(field_num, request_msg.get_field(field_num))
    
    # Add response code in field 39
    msg.set_field(39, response_code)
    
    # Add additional fields if provided
    if additional_fields:
        for field_num, value in additional_fields.items():
            msg.set_field(field_num, value)
    
    return msg
