import asyncio
from typing import Dict

# Shared dict mapping STAN → asyncio.Event for payment confirmation
# Used by tcp.py (to wait) and webhook.py (to signal)
pending_payments: Dict[str, asyncio.Event] = {}
