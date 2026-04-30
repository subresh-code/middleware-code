"""
Server Module

Entry point for the middleware system. Handles incoming connections
and routes requests to the orchestrator.
"""

import asyncio
import socket
from typing import Optional
from app.utils.logger import logger
from app.utils.config import config
from app.core.orchestrator import MiddlewareOrchestrator


class MiddlewareServer:
    """
    TCP server for receiving ISO 8583 messages.
    """

    def __init__(self):
        self.host = config.host
        self.port = config.port
        self.orchestrator = MiddlewareOrchestrator()
        self.server: Optional[asyncio.AbstractServer] = None

    async def start(self):
        """Start the TCP server."""
        try:
            self.server = await asyncio.start_server(
                self.handle_connection,
                self.host,
                self.port
            )

            logger.logger.info(f"Middleware server started on {self.host}:{self.port}")

            async with self.server:
                await self.server.serve_forever()

        except Exception as e:
            logger.logger.error(f"Failed to start server: {e}")
            raise

    async def stop(self):
        """Stop the TCP server."""
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            logger.logger.info("Middleware server stopped")

    async def handle_connection(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Handle incoming TCP connection."""
        client_address = writer.get_extra_info('peername')
        logger.logger.info(f"New connection from {client_address}")

        try:
            # Read ISO 8583 message
            data = await reader.read(4096)  # Adjust buffer size as needed
            raw_message = data.decode('ascii', errors='ignore').strip()

            if not raw_message:
                logger.logger.warning(f"Empty message from {client_address}")
                return

            logger.logger.info(f"Received message from {client_address}: {len(raw_message)} bytes")

            # Process through orchestrator
            response = await self.orchestrator.process_transaction(raw_message)

            # Send response back
            writer.write(response.encode('ascii'))
            await writer.drain()

            logger.logger.info(f"Sent response to {client_address}")

        except Exception as e:
            logger.logger.error(f"Error handling connection from {client_address}: {e}")
        finally:
            writer.close()
            await writer.wait_closed()


async def main():
    """Main entry point."""
    server = MiddlewareServer()
    try:
        await server.start()
    except KeyboardInterrupt:
        logger.logger.info("Shutting down server...")
        await server.stop()


if __name__ == "__main__":
    asyncio.run(main())