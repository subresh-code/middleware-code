import asyncio
import logging
from contextlib import asynccontextmanager

import bcrypt

from app.db import SessionLocal
from app.models.payment import AseRegistry, PaymentStatus, PaymentTranslation, TriggeredBy
from app.parser.iso8583 import ParseError, encode_iso8583_response, parse_iso8583
from app.state.machine import InvalidTransitionError, transition_payment
from app.translation.core import WalletResolutionError, translate


logger = logging.getLogger(__name__)


@asynccontextmanager
async def get_db_session():
    from app.db import get_session_local
    SessionLocal = get_session_local()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class TcpServer:
    def __init__(self):
        self._server = None
        # ase_name → current connection count
        self._connection_counts: dict[str, int] = {}
        self._lock = asyncio.Lock()

    def _make_error_response(self, mti: str, de39: str, stan: str, frame_length_type: int) -> bytes:
        """Build a proper ISO 8583 0210/0410 error response."""
        response_mti = "0210" if mti == "0200" else "0410"
        try:
            return encode_iso8583_response(
                mti=response_mti,
                fields={"39": de39, "11": stan},
                header_len=frame_length_type,
            )
        except Exception:
            # Last resort — minimal response
            return b"\x00\x00"

    async def _verify_ase(self, db, api_key: str) -> AseRegistry | None:
        """
        Verify API key against ase_registry.
        Returns AseRegistry record if valid and active, None otherwise.
        bcrypt check runs in thread pool to avoid blocking the event loop.
        """
        registries = db.query(AseRegistry).filter(AseRegistry.active == True).all()
        loop = asyncio.get_event_loop()
        for registry in registries:
            match = await loop.run_in_executor(
                None,
                bcrypt.checkpw,
                api_key.encode(),
                registry.api_key_hash.encode(),
            )
            if match:
                return registry
        return None

    async def handle_connection(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        peername = writer.get_extra_info("peername")
        ase_record: AseRegistry | None = None
        authenticated = False

        try:
            from app.config import get_settings
            settings = get_settings()

            # ── Step 1: read API key line on new connection ────────────
            try:
                api_key_line = await asyncio.wait_for(
                    reader.readline(),
                    timeout=settings.tcp_connection_timeout_seconds,
                )
            except asyncio.TimeoutError:
                logger.warning("Connection from %s timed out during auth", peername)
                return

            api_key = api_key_line.strip().decode("ascii", errors="ignore")

            # ── Step 2: verify API key against ase_registry ──────────────
            async with get_db_session() as db:
                ase_record = await self._verify_ase(db, api_key)

            if not ase_record:
                logger.warning("Rejected unauthenticated connection from %s", peername)
                return

            authenticated = True
            ase_name = ase_record.ase_name
            frame_length_type = ase_record.frame_length_type
            max_connections = ase_record.max_connections or settings.tcp_max_connections_per_ase

            # ── Step 3: enforce connection limit ────────────────────────
            async with self._lock:
                current = self._connection_counts.get(ase_name, 0)
                if current >= max_connections:
                    logger.warning(
                        "Connection limit %d reached for ASE %s — rejecting %s",
                        max_connections, ase_name, peername,
                    )
                    return
                self._connection_counts[ase_name] = current + 1

            logger.info("ASE '%s' connected from %s", ase_name, peername)

            # ── Step 4: message loop ──────────────────────────────────────
            try:
                while True:
                    # Read frame length header
                    try:
                        header_bytes = await asyncio.wait_for(
                            reader.readexactly(frame_length_type),
                            timeout=settings.tcp_connection_timeout_seconds,
                        )
                    except (asyncio.IncompleteReadError, asyncio.TimeoutError):
                        logger.info("ASE '%s' connection timed out", ase_name)
                        break

                    msg_len = int.from_bytes(header_bytes, "big")

                    # Reject oversized messages — DE39=30 (format error)
                    if msg_len > settings.tcp_max_message_bytes:
                        logger.warning(
                            "ASE '%s' sent oversized message: %d bytes",
                            ase_name, msg_len,
                        )
                        error_response = self._make_error_response("0200", "30", "000000", frame_length_type)
                        writer.write(error_response)
                        await writer.drain()
                        continue

                    # Read message body
                    try:
                        data = await asyncio.wait_for(
                            reader.readexactly(msg_len),
                            timeout=settings.tcp_connection_timeout_seconds,
                        )
                    except (asyncio.IncompleteReadError, asyncio.TimeoutError):
                        break

                    if not data:
                        break

                    # Include header in raw_bytes so parser stores the full frame
                    full_frame = header_bytes + data

                    # ── Parse ────────────────────────────────────────────────
                    try:
                        msg = parse_iso8583(full_frame, frame_length_type)
                    except ParseError as e:
                        logger.warning("ASE '%s' parse error: %s", ase_name, e)
                        error_response = self._make_error_response(
                            msg.mti if 'msg' in locals() else '0200',
                            "30", "000000", frame_length_type,
                        )
                        writer.write(error_response)
                        await writer.drain()
                        continue

                    # ── Handle 0800 Network Management (echo/heartbeat) ────
                    if msg.mti == "0800":
                        logger.info("ASE '%s' sent 0800 echo request", ase_name)
                        echo_response = encode_iso8583_response(
                            mti="0810",
                            fields={"39": "00", "11": msg.de11},
                            header_len=frame_length_type,
                        )
                        writer.write(echo_response)
                        await writer.drain()
                        continue

                    # ── Process payment ───────────────────────────────────────
                    async with get_db_session() as db:
                        try:
                            # Create payment record with raw fields only
                            payment = PaymentTranslation(
                                ase_name=ase_name,
                                raw_message=msg.raw_hex,
                                mti=msg.mti,
                                status=PaymentStatus.RECEIVED,
                                currency=msg.de49,
                                stan=msg.de11,
                                rrn=msg.de37,
                            )
                            db.add(payment)
                            db.commit()
                            db.refresh(payment)

                            # Transition to TRANSLATING
                            transition_payment(
                                db, payment.id,
                                PaymentStatus.TRANSLATING,
                                TriggeredBy.ASE_INBOUND,
                                "Received from ASE",
                            )

                            # Run translation
                            result = translate(db, msg, ase_name, settings.payment_ttl_seconds)

                            # Update payment with translation results
                            payment.wallet_address = result.wallet_address
                            payment.amount_ilp_uint64 = result.amount_ilp_uint64
                            payment.amount_value = result.amount_ilp_uint64 / (10 ** result.asset_scale)
                            payment.expires_at = result.expires_at
                            db.commit()

                            # Transition to TRANSLATED
                            transition_payment(
                                db, payment.id,
                                PaymentStatus.TRANSLATED,
                                TriggeredBy.TRANSLATION_JOB,
                                "Translation complete",
                            )

                            # Send approved response — DE39=00
                            response = self._make_error_response(
                                msg.mti, "00", msg.de11, frame_length_type)
                            writer.write(response)
                            await writer.drain()

                        except (WalletResolutionError, InvalidTransitionError, ValueError) as e:
                            logger.error("Payment processing error for ASE '%s': %s", ase_name, e)
                            db.rollback()
                            if 'payment' in locals():
                                try:
                                    transition_payment(
                                        db, payment.id,
                                        PaymentStatus.FAILED,
                                        TriggeredBy.SYSTEM,
                                        str(e),
                                    )
                                except Exception:
                                    pass
                            error_response = self._make_error_response(
                                msg.mti if 'msg' in locals() else '0200',
                                "96", msg.de11 if 'msg' in locals() else "000000", frame_length_type,
                            )
                            writer.write(error_response)
                            await writer.drain()

            finally:
                # ── Decrement connection count ───────────────────────────────
                async with self._lock:
                    self._connection_counts[ase_name] = max(
                        0, self._connection_counts.get(ase_name, 1) - 1)
                logger.info("ASE '%s' disconnected from %s", ase_name, peername)

        except Exception as e:
            logger.exception("Unhandled error in TCP connection from %s: %s", peername, e)
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def start(self):
        from app.config import get_settings
        settings = get_settings()
        self._server = await asyncio.start_server(
            self.handle_connection,
            settings.tcp_host, settings.tcp_port,
        )
        logger.info("TCP server listening on %s:%d", settings.tcp_host, settings.tcp_port)
        async with self._server:
            await self._server.serve_forever()

    def stop(self):
        if self._server:
            self._server.close()


tcp_server = TcpServer()
