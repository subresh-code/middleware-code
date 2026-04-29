from fastapi import FastAPI

app = FastAPI(
    title="Payment Middleware",
    description="Middleware translating ISO 20022 messages to ILP/Rafiki",
    version="0.1.0",
)

@app.get("/health", tags=["health"])
def health_check():
    """
    Health check endpoint used by developers,
    Docker, and future orchestration tools.
    """
    return {"status": "ok"}