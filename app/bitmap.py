class ISO8583Bitmap:
    """
    Handles ISO 8583 bitmap operations.
    Bitmap indicates which data fields are present in the message.
    """
    
    def __init__(self):
        # 128 bits for primary + secondary bitmap
        self.bitmap = [0] * 128
    
    def set_field(self, field_number):
        """Set a field as present in the bitmap."""
        if 1 <= field_number <= 128:
            self.bitmap[field_number - 1] = 1
    
    def clear_field(self, field_number):
        """Clear a field from the bitmap."""
        if 1 <= field_number <= 128:
            self.bitmap[field_number - 1] = 0
    
    def is_field_present(self, field_number):
        """Check if a field is present in the bitmap."""
        if 1 <= field_number <= 128:
            return self.bitmap[field_number - 1] == 1
        return False
    
    def has_secondary_bitmap(self):
        """Check if secondary bitmap is needed (field 65-128 present)."""
        for i in range(64, 128):
            if self.bitmap[i] == 1:
                return True
        return False
    
    def to_bytes(self):
        """
        Convert bitmap to bytes.
        Returns primary bitmap (8 bytes) or primary + secondary (16 bytes).
        """
        result = bytearray()
        
        # Build primary bitmap (fields 1-64)
        primary = self._bits_to_bytes(self.bitmap[0:64])
        result.extend(primary)
        
        # Add secondary bitmap if needed
        if self.has_secondary_bitmap():
            # Set bit 1 of primary to indicate secondary exists
            result[0] |= 0x80
            secondary = self._bits_to_bytes(self.bitmap[64:128])
            result.extend(secondary)
        
        return bytes(result)
    
    def _bits_to_bytes(self, bits):
        """Convert 64 bits (8 bytes) to bytes."""
        result = bytearray(8)
        for i in range(64):
            if bits[i]:
                byte_index = i // 8
                bit_index = 7 - (i % 8)  # MSB first
                result[byte_index] |= (1 << bit_index)
        return result
    
    @classmethod
    def from_bytes(cls, data):
        """
        Parse bitmap from bytes.
        Expects at least 8 bytes for primary bitmap.
        If bit 1 is set, reads additional 8 bytes for secondary.
        """
        bitmap_obj = cls()
        
        if len(data) < 8:
            raise ValueError("Bitmap data must be at least 8 bytes")
        
        # Parse primary bitmap (fields 1-64)
        bitmap_obj._bytes_to_bits(data[0:8], 0)
        
        # Check if secondary bitmap exists
        if data[0] & 0x80:  # Bit 1 is set
            if len(data) < 16:
                raise ValueError("Secondary bitmap indicated but not enough data")
            bitmap_obj._bytes_to_bits(data[8:16], 64)
        
        return bitmap_obj
    
    def _bytes_to_bits(self, bytes_data, offset):
        """Convert bytes to bits starting at offset."""
        for i in range(64):
            byte_index = i // 8
            bit_index = 7 - (i % 8)  # MSB first
            if bytes_data[byte_index] & (1 << bit_index):
                self.bitmap[offset + i] = 1
    
    def to_hex(self):
        """Return bitmap as hex string for display."""
        return self.to_bytes().hex().upper()
    
    def get_present_fields(self):
        """Return list of field numbers that are present."""
        return [i + 1 for i in range(128) if self.bitmap[i] == 1]
    
    def __str__(self):
        """String representation showing present fields."""
        fields = self.get_present_fields()
        hex_value = self.to_hex()
        return f"Bitmap: {hex_value} (Fields: {fields})"


# Example usage and testing
if __name__ == "__main__":
    # Create a bitmap with some fields
    bitmap = ISO8583Bitmap()
    
    # Set fields commonly used in financial transactions
    bitmap.set_field(2)   # Primary Account Number
    bitmap.set_field(3)   # Processing Code
    bitmap.set_field(4)   # Amount
    bitmap.set_field(11)  # STAN
    bitmap.set_field(32)  # Acquiring Institution
    bitmap.set_field(49)  # Currency Code
    
    print("Fields present:", bitmap.get_present_fields())
    print("Bitmap hex:", bitmap.to_hex())
    print("Has secondary:", bitmap.has_secondary_bitmap())
    
    # Test parsing
    bitmap_bytes = bitmap.to_bytes()
    print("\nBitmap bytes:", bitmap_bytes.hex().upper())
    
    # Parse it back
    parsed = ISO8583Bitmap.from_bytes(bitmap_bytes)
    print("Parsed fields:", parsed.get_present_fields())
