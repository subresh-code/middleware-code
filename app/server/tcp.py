import asyncio
from fastapi import FastAPI
from app.config import settings
from app.parser.iso8583 import parse_iso8583, ParseError
from app.translation.core import translate, WalletResolutionError
from app.state.machine import transition_payment, TriggeredBy, InvalidTransitionError
from app.models.payment import PaymentTranslation, PaymentStatus
from app.db import SessionLocal


class TcpServer:
    def __init__(self):
        self._server = None
        self._ase_connections: dict[str, int] = {}

    async def handle_connection(self, reader, writer):
        """Handle a single persistent TCP connection from an ASE."""
        peername = writer.get_extra_info("peername")
        ase_name = None

        try:
            while True:
                # Read length header
                header_len = settings.iso8583_header_length
                try:
                    header_bytes = await asyncio.wait_for(
                        reader.readexactly(header_len),
                        timeout=settings.tcp_connection_timeout_seconds
                    )
                except (asyncio.IncompleteReadError, asyncio.TimeoutError):
                    break

                msg_len = int.from_bytes(header_bytes, "big")
                if msg_len > settings.tcp_max_message_bytes:
                    # Send error response (DE39=30)
                    writer.write(b"\x00\x14")  # Placeholder
                    await writer.drain()
                    continue

                data = await asyncio.wait_for(
                    reader.readexactly(msg_len),
                    timeout=settings.tcp_connection_timeout_seconds
                )
                if not data:
                    break

                # Parse ISO 8583
                try:
                    msg = parse_iso8583(data, ase_name or "unknown")
                except ParseError as e:
                    writer.write(f"ParseError: {e}".encode())
                    await writer.drain()
                    continue

                # Create payment record
                db = SessionLocal()
                try:
                    payment = PaymentTranslation(
                        ase_name=ase_name or "unknown",
                        raw_message=msg.raw_hex,
                        mti=msg.mti,
                        status=PaymentStatus.RECEIVED,
                        amount_value=int(msg.de4) / 100.0 if msg.de4 else None,
                        amount_ilp_uint64=int(msg.de4) if msg.de4 else None,
                        currency=msg.de49,
                        stan=msg.de11,
                        rrn=msg.de37,
                        sender_account=msg.de102,
                        dest_account=msg.de103,
                    )
                    db.add(payment)
                    db.commit()

                    # Transition to TRANSLATING
                    transition_payment(
                        db, payment.id, PaymentStatus.TRANSLATING,
                        TriggeredBy.ASE_INBOUND, "Received from ASE"
                    )

                    # Translate
                    translation = translate(db, msg, ase_name or "unknown")
                    payment.wallet_address = translation["wallet_address"]
                    payment.amount_ilp_uint64 = translation["amount_ilp_uint64"]
                    payment.expires_at = translation["expiresAt"]
                    db.commit()

                    transition_payment(
                        db, payment.id, PaymentStatus.TRANSLATED,
                        TriggeredBy.TRANSLATION_JOB, "Translation complete"
                    )

                    # Send success response
                    writer.write(b"OK")
                    await writer.drain()

                finally:
                    db.close()

        except Exception as e:
            try:
                writer.write(f"Error: {e}".encode())
                await writer.drain()
            except:
                pass
        finally:
            writer.close()
            await writer.wait_closed()

    async def start(self):
        self._server = await asyncio.start_server(
            self.handle_connection, settings.tcp_host, settings.tcp_port
        )
        print(f"TCP server listening on {settings.tcp_host}:{settings.tcp_port}")
        async with self._server:
            await self._server.serve_forever()

    def stop(self):
        if self._server:
            self._server.close()


tcp_server = TcpServer()
