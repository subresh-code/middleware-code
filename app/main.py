"""
Payment Middleware - Main Application.
Middleware translating ISO 8583 messages to ILP/Rafiki for inter-coop transfers.
"""
from fastapi import FastAPI
from app.api import health, wallets, transactions, iso8583

app = FastAPI(
    title="Payment Middleware",
    description="Middleware translating ISO 8583 messages to ILP/Rafiki for inter-coop transfers",
    version="0.2.0",
)

# Include routers
app.include_router(health.router)
app.include_router(wallets.router)
app.include_router(transactions.router)
app.include_router(iso8583.router)


@app.on_event("startup")
def startup_event():Use Merg
    """Initialize database tables on startup."""
    from app.database import db
    db.create_tables()
