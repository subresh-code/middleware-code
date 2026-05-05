from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import asyncio
from app.config import get_settings

router = APIRouter(prefix="/api/test", tags=["ISO 8583 Test Client"])

class IsoMessageRequest(BaseModel):
    mti: str = "0200"
    fields: dict
    header_len: int = 2

@router.post("/send")
async def send_iso_message(payload: IsoMessageRequest):
    """Sends a message to the Middleware TCP server and returns the response."""
    settings = get_settings()
    try:
        # 1. Encode the JSON request into ISO 8583 binary
        from app.parser.iso8583 import encode_iso8583_response
        raw_bytes = encode_iso8583_response(
            mti=payload.mti,
            fields=payload.fields,
            header_len=payload.header_len
        )
        
        # 2. Connect to TCP Server and send
        reader, writer = await asyncio.open_connection(
            settings.tcp_host, settings.tcp_port
        )
        
        try:
            # Send the message
            writer.write(raw_bytes)
            await writer.drain()
            
            # Read response (wait for header + message)
            header_bytes = await reader.readexactly(payload.header_len)
            msg_len = int.from_bytes(header_bytes, "big")
            response_bytes = await reader.readexactly(msg_len)
            
            # 3. Parse response to human-readable
            from app.parser.iso8583 import parse_iso8583
            msg = parse_iso8583(header_bytes + response_bytes, payload.header_len)
            
            return {
                "status": "success",
                "sent_hex": raw_bytes.hex().upper(),
                "received_hex": (header_bytes + response_bytes).hex().upper(),
                "response": {
                    "mti": msg.mti,
                    "de39_response_code": msg.de39,
                    "de11_stan": msg.de11,
                }
            }
        finally:
            writer.close()
            await writer.wait_closed()
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TCP Communication Error: {str(e)}")
