import asyncio
import logging
from contextlib import asynccontextmanager

import bcrypt

from app.db import SessionLocal
from app.models.payment import (
    AseRegistry, PaymentStatus, PaymentTranslation, TriggeredBy,
    RawMessageLog,
)
from app.parser.iso8583 import ParseError, encode_iso8583_response, parse_iso8583
from app.state.machine import InvalidTransitionError, transition_payment
from app.translation.core import WalletResolutionError, translate, resolve_wallet
from app.middleware.rate_limiter import check_rate_limit


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
                        # Log successful parse to raw_message_logs
                        async with get_db_session() as db:
                            log = RawMessageLog(
                                ase_name=ase_name,
                                stan=msg.de11 if hasattr(msg, "de11") else None,
                                rrn=msg.de37 if hasattr(msg, "de37") else None,
                                mti=msg.mti,
                                raw_bytes=full_frame.hex().upper(),
                                parsed_successfully=True,
                            )
                            db.add(log)
                            db.commit()
                    except ParseError as e:
                        logger.warning("ASE '%s' parse error: %s", ase_name, e)
                        # Log failed parse with raw bytes
                        async with get_db_session() as db:
                            log = RawMessageLog(
                                ase_name=ase_name,
                                raw_bytes=full_frame.hex().upper(),
                                parsed_successfully=False,
                                error_message=str(e),
                            )
                            db.add(log)
                            db.commit()
                        error_response = self._make_error_response(
                            '0200',  # msg not defined on parse failure
                            "30", "000000", frame_length_type,
                        )
                        writer.write(error_response)
                        await writer.drain()
                        continue

                    # ── Rate limit check ─────────────────────────────────
                    if not check_rate_limit(ase_name):
                        logger.warning("ASE '%s' rate limit exceeded", ase_name)
                        writer.write(self._make_error_response(msg.mti, "03", msg.de11, frame_length_type))
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

                    # ── Handle 0400 Reversal ───────────────────────────────────
                    if msg.mti == "0400":
                        async with get_db_session() as db:
                            # Look up original 0200 by STAN (DE11) + RRN (DE37)
                            original = (
                                db.query(PaymentTranslation)
                                .filter(
                                    PaymentTranslation.ase_name == ase_name,
                                    PaymentTranslation.stan == msg.de11,
                                    PaymentTranslation.rrn == msg.de37,
                                    PaymentTranslation.mti == "0200",
                                )
                                .order_by(PaymentTranslation.created_at.desc())
                                .first()
                            )
                            if not original:
                                logger.warning(
                                    "ASE '%s' reversal for unknown STAN=%s RRN=%s",
                                    ase_name, msg.de11, msg.de37,
                                )
                                writer.write(self._build_response("0400", "25", msg.de11, frame_length_type))
                                await writer.drain()
                                continue

                            if original.status in (PaymentStatus.SETTLED, PaymentStatus.NOTIFIED):
                                # Already settled — cannot reverse at middleware layer
                                writer.write(self._build_response("0400", "39", msg.de11, frame_length_type))
                                await writer.drain()
                                continue

                            if original.status == PaymentStatus.FAILED:
                                # Already failed, reversal not needed
                                writer.write(self._build_response("0400", "00", msg.de11, frame_length_type))
                                await writer.drain()
                                continue

                            # If Rafiki payment was created, attempt to cancel it
                            if original.rafiki_payment_id:
                                try:
                                    rafiki = RafikiClient()
                                    await rafiki.cancel_outgoing_payment(original.rafiki_payment_id)
                                except Exception as e:
                                    logger.warning(
                                        "Could not cancel Rafiki payment %s: %s",
                                        original.rafiki_payment_id, e,
                                    )

                            # Mark original as reversed (FAILED with reason)
                            try:
                                transition_payment(
                                    db, original.id, PaymentStatus.FAILED,
                                    TriggeredBy.ASE_INBOUND,
                                    "Reversed by 0400 reversal request",
                                )
                                original.response_code = "00"
                                db.commit()
                            except InvalidTransitionError:
                                writer.write(self._build_response("0400", "39", msg.de11, frame_length_type))
                                await writer.drain()
                                continue

                            writer.write(self._build_response("0400", "00", msg.de11, frame_length_type))
                            await writer.drain()
                            continue

                    # ── Handle 0100 Pre-Authorization ────────────────────────
                    if msg.mti == "0100":
                        async with get_db_session() as db:
                            try:
                                payment = PaymentTranslation(
                                    ase_name=ase_name,
                                    raw_message=msg.raw_hex,
                                    mti=msg.mti,
                                    status=PaymentStatus.RECEIVED,
                                    currency=msg.de49,
                                    stan=msg.de11,
                                    rrn=msg.de37,
                                    processing_code=msg.de3,
                                    terminal_id=msg.de41,
                                )
                                db.add(payment)
                                db.commit()
                                db.refresh(payment)

                                transition_payment(
                                    db, payment.id,
                                    PaymentStatus.TRANSLATING,
                                    TriggeredBy.ASE_INBOUND,
                                    "Pre-auth received from ASE",
                                )

                                result = translate(db, msg, ase_name, settings.payment_ttl_seconds)
                                payment.wallet_address = result.wallet_address
                                payment.amount_ilp_uint64 = result.amount_ilp_uint64
                                payment.amount_value = result.amount_ilp_uint64 / (10 ** result.asset_scale)
                                payment.expires_at = result.expires_at
                                db.commit()

                                transition_payment(
                                    db, payment.id,
                                    PaymentStatus.TRANSLATED,
                                    TriggeredBy.TRANSLATION_JOB,
                                    "Pre-auth translation complete",
                                )

                                rafiki = RafikiClient()
                                try:
                                    await rafiki.get_wallet_address(result.wallet_address)
                                except Exception as e:
                                    logger.error("Wallet not found for pre-auth: %s", e)
                                    transition_payment(
                                        db, payment.id, PaymentStatus.FAILED,
                                        TriggeredBy.SYSTEM, f"Wallet not found: {e}"
                                    )
                                    writer.write(self._build_response("0100", "14", msg.de11, frame_length_type))
                                    await writer.drain()
                                    continue

                                try:
                                    incoming = await rafiki.create_incoming_payment(
                                        wallet_address=result.wallet_address,
                                        amount_ilp_uint64=result.amount_ilp_uint64,
                                        asset_code=result.asset_code,
                                        asset_scale=result.asset_scale,
                                        expires_at=result.expires_at.isoformat(),
                                        external_ref=msg.de11,
                                    )
                                except Exception as e:
                                    logger.error("Pre-auth incoming payment failed: %s", e)
                                    transition_payment(
                                        db, payment.id, PaymentStatus.FAILED,
                                        TriggeredBy.SYSTEM, f"Rafiki incoming payment failed: {e}"
                                    )
                                    writer.write(self._build_response("0100", "96", msg.de11, frame_length_type))
                                    await writer.drain()
                                    continue

                                payment.rafiki_payment_id = str(incoming)
                                db.commit()
                                transition_payment(
                                    db, payment.id, PaymentStatus.ILP_PREPARED,
                                    TriggeredBy.TRANSLATION_JOB,
                                    "Pre-auth: incoming payment created (funds reserved)",
                                )

                                # Pre-auth does NOT create outgoing payment
                                # Wait for webhook confirmation
                                event = asyncio.Event()
                                pending_payments[msg.de11] = event
                                try:
                                    await asyncio.wait_for(event.wait(), timeout=30.0)
                                except asyncio.TimeoutError:
                                    transition_payment(
                                        db, payment.id, PaymentStatus.FAILED,
                                        TriggeredBy.SYSTEM, "Pre-auth webhook timeout"
                                    )
                                    payment.response_code = "68"
                                    db.commit()
                                    writer.write(self._build_response("0100", "68", msg.de11, frame_length_type))
                                    await writer.drain()
                                    continue
                                finally:
                                    pending_payments.pop(msg.de11, None)

                                db.refresh(payment)
                                if payment.status == PaymentStatus.ILP_FULFILLED:
                                    payment.response_code = "00"
                                    db.commit()
                                    writer.write(self._build_response("0100", "00", msg.de11, frame_length_type))
                                else:
                                    payment.response_code = "05"
                                    db.commit()
                                    writer.write(self._build_response("0100", "05", msg.de11, frame_length_type))

                                await writer.drain()

                            except (WalletResolutionError, InvalidTransitionError, ValueError) as e:
                                logger.error("Pre-auth error for ASE '%s': %s", ase_name, e)
                                db.rollback()
                                writer.write(self._build_response("0100", "96", msg.de11, frame_length_type))
                                await writer.drain()
                        continue

                    # ── Handle Balance Inquiry (DE3 starts with "31") ────────
                    if msg.de3 and msg.de3.startswith("31"):
                        async with get_db_session() as db:
                            try:
                                # Resolve wallet from DE103 (destination account)
                                wallet_address = resolve_wallet(db, ase_name, msg.de103)
                                rafiki = RafikiClient()

                                # Query Rafiki for wallet balance via GraphQL
                                query = {
                                    "query": """
                                        query GetWalletBalance($url: String!) {
                                            walletAddressByUrl(url: $url) {
                                                id
                                                asset {
                                                    code
                                                    scale
                                                }
                                                balance
                                            }
                                        }
                                    """,
                                    "variables": {"url": wallet_address}
                                }
                                resp = rafiki._request_with_retry("POST", "/graphql", json=query)
                                data = resp.json()

                                wallet_data = data.get("data", {}).get("walletAddressByUrl")
                                if not wallet_data:
                                    writer.write(self._build_response(msg.mti, "14", msg.de11, frame_length_type))
                                    await writer.drain()
                                    continue

                                # Build response with balance in DE4
                                # Balance is in UInt64 format, convert to 12-digit DE4
                                balance_raw = int(wallet_data.get("balance", 0))
                                asset_scale = wallet_data.get("asset", {}).get("scale", 2)
                                # Convert UInt64 to display value, then to 12-digit
                                display_value = balance_raw / (10 ** asset_scale)
                                de4_balance = f"{int(display_value * 100):012d}"

                                response_fields = {
                                    "39": "00",
                                    "11": msg.de11,
                                    "4": de4_balance,
                                }
                                response_mti = "0210" if msg.mti == "0200" else "0110"
                                try:
                                    balance_response = encode_iso8583_response(
                                        mti=response_mti,
                                        fields=response_fields,
                                        header_len=frame_length_type,
                                    )
                                    writer.write(balance_response)
                                except Exception:
                                    writer.write(self._build_response(msg.mti, "96", msg.de11, frame_length_type))

                            except WalletResolutionError as e:
                                logger.warning("Balance inquiry wallet not found: %s", e)
                                writer.write(self._build_response(msg.mti, "14", msg.de11, frame_length_type))
                            except Exception as e:
                                logger.error("Balance inquiry error: %s", e)
                                writer.write(self._build_response(msg.mti, "96", msg.de11, frame_length_type))

                            await writer.drain()
                        continue

                    # ── Process payment (0200) ───────────────────────────────
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
