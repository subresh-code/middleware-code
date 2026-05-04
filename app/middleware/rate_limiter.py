"""
Rate limiter for ASE connections.
Per-ASE token bucket: limits messages/second.
"""
import time
from collections import defaultdict


class TokenBucket:
    """Token bucket rate limiter."""
    def __init__(self, capacity: int, refill_rate: float):
        """
        capacity: max tokens (max burst size)
        refill_rate: tokens per second
        """
        self.capacity = capacity
        self.tokens = float(capacity)
        self.refill_rate = refill_rate
        self.last_refill = time.monotonic()

    def _refill(self):
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(
            self.capacity,
            self.tokens + elapsed * self.refill_rate,
        )
        self.last_refill = now

    def consume(self, tokens: int = 1) -> bool:
        """Try to consume tokens. Returns True if allowed, False if rate-limited."""
        self._refill()
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False


# Global rate limiter registry: ase_name -> TokenBucket
_rate_buckets: dict[str, TokenBucket] = {}
_default_capacity = 100  # messages per minute = 100/60 ≈ 1.67 msg/sec
_default_refill_rate = 100 / 60.0  # 100 messages per 60 seconds


def check_rate_limit(ase_name: str, capacity: int = None, refill_rate: float = None) -> bool:
    """
    Check if ASE is within rate limit.
    Returns True if allowed, False if rate-limited.
    """
    if ase_name not in _rate_buckets:
        cap = capacity if capacity else _default_capacity
        rate = refill_rate if refill_rate else _default_refill_rate
        _rate_buckets[ase_name] = TokenBucket(cap, rate)

    bucket = _rate_buckets[ase_name]
    return bucket.consume(1)


def get_bucket_status(ase_name: str) -> dict:
    """Get current token count for an ASE (for monitoring)."""
    if ase_name not in _rate_buckets:
        return {"exists": False}
    bucket = _rate_buckets[ase_name]
    bucket._refill()
    return {
        "exists": True,
        "tokens": round(bucket.tokens, 2),
        "capacity": bucket.capacity,
        "refill_rate": bucket.refill_rate,
    }
