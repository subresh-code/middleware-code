from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import asyncio
from app.config import get_settings

router = APIRouter(prefix="/api/test", tags=["ISO 8583 Test Client"])

class IsoMessageRequest(BaseModel):
    mti: str = "0200"
    header_len: int = 2
    fields: dict | None = None
    raw_hex: str | None = None

@router.post("/send")
async def send_iso_message(payload: IsoMessageRequest):
    """Sends message to Middleware TCP server and returns DE39 response."""
    settings = get_settings()
    try:
        # 1. Determine input type: Raw Hex or JSON Fields
        if payload.raw_hex:
            # Raw Hex: Convert directly to bytes
            raw_bytes = bytes.fromhex(payload.raw_hex)
        else:
            # JSON Fields: Encode to ISO 8583 binary
            from app.parser.iso8583 import encode_iso8583_response
            raw_bytes = encode_iso8583_response(
                mti=payload.mti,
                fields=payload.fields,
                header_len=payload.header_len
            )
        
        # 2. Connect to TCP Server (use 127.0.0.1 inside container)
        try:
            reader, writer = await asyncio.open_connection(
                "127.0.0.1", settings.tcp_port
            )
        except ConnectionRefusedError:
            raise HTTPException(status_code=503, detail="TCP Server not running on port 9000")

        try:
            # 3. Send Message
            writer.write(raw_bytes)
            await writer.drain()
            
            # 4. Read Response (Wait for header + message)
            header_bytes = await reader.readexactly(payload.header_len)
            msg_len = int.from_bytes(header_bytes, "big")
            response_bytes = await reader.readexactly(msg_len)
            
            # 5. Parse Response to get DE39 (Response Code)
            from app.parser.iso8583 import parse_iso8583
            msg = parse_iso8583(header_bytes + response_bytes, payload.header_len)
            
            return {
                "status": "success",
                "sent_hex": raw_bytes.hex().upper(),
                "received_hex": (header_bytes + response_bytes).hex().upper(),
                "response_code_de39": msg.de39,
                "message": f"Rafiki processed. Response Code: {msg.de39} (00=Success, 14=NotFound, 96=SystemError)"
            }
        finally:
            writer.close()
            await writer.wait_closed()
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TCP Error: {str(e)}")