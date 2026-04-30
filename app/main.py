from fastapi import FastAPI
from app.routes import health, inbound, webhook

app = FastAPI(
    title="Payment Middleware",
    description="Middleware translating ISO 8583 messages to ILP/Rafiki",
    version="0.1.0",
)

app.include_router(health.router)
app.include_router(inbound.router)
app.include_router(webhook.router)
