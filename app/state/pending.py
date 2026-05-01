import asyncio

pending_payments: dict[str, asyncio.Event] = {}
