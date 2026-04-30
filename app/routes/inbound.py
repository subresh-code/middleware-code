from fastapi import APIRouter

router = APIRouter(tags=["inbound"])

# TCP server is now in app/server/tcp.py
# This module is kept for any HTTP-based inbound endpoints if needed
