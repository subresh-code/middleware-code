import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.routes import health, inbound, webhook
from app.config import settings

@asynccontextmanager
async def lifespan(app: FastAPI):
    # TCP server will be wired here once app/server/tcp.py is implemented
    yield


app = FastAPI(
    title="Payment Middleware",
    description="Middleware translating ISO 8583 messages to ILP/Rafiki",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health.router)
app.include_router(inbound.router)
app.include_router(webhook.router)
