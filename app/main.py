import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.routes import health, inbound, webhook
from app.server.tcp import tcp_server
from app.config import get_settings

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start TCP server on application startup."""
    settings = get_settings()
    # Start TCP server in background
    server_task = asyncio.create_task(
        tcp_server.start()
    )
    print(f"TCP server starting on {settings.tcp_host}:{settings.tcp_port}")
    yield
    # Shutdown
    tcp_server.stop()
    server_task.cancel()
    try:
        await server_task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="Payment Middleware",
    description="Middleware translating ISO 8583 messages to ILP/Rafiki",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health.router)
app.include_router(inbound.router)
app.include_router(webhook.router)
