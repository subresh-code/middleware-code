import time
from enum import Enum, auto
from typing import Callable, Any


class CircuitState(str, Enum):
    CLOSED = "CLOSED"    # Normal operation — requests pass through
    OPEN = "OPEN"        # Failing — requests short-circuit immediately
    HALF_OPEN = "HALF_OPEN"  # Testing — allow one request to probe


class CircuitBreakerError(Exception):
    """Raised when circuit is open and fast-fails."""
    pass


class CircuitBreaker:
    """
    Circuit breaker for external calls (Rafiki API).
    - CLOSED: requests pass; on failure, increment fail count
    - OPEN: after N failures, short-circuit with CircuitBreakerError
    - HALF_OPEN: after timeout, allow one probe request
    - On probe success → CLOSED (reset)
    - On probe failure → OPEN again (reset timeout)
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        expected_exceptions: tuple = (Exception,),
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exceptions = expected_exceptions

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float | None = None
        self._lock = None  # Will use asyncio lock if needed

    @property
    def state(self) -> CircuitState:
        return self._state

    def _should_attempt_reset(self) -> bool:
        if self._state != CircuitState.OPEN:
            return False
        if self._last_failure_time is None:
            return False
        return (time.time() - self._last_failure_time) >= self.recovery_timeout

    def _record_success(self):
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time = None

    def _record_failure(self):
        self._failure_count += 1
        self._last_failure_time = time.time()
        if self._failure_count >= self.failure_threshold:
            self._state = CircuitState.OPEN

    def call(self, func: Callable[..., Any], *args, **kwargs) -> Any:
        """
        Synchronous circuit breaker call.
        Raises CircuitBreakerError if circuit is open.
        """
        if self._state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self._state = CircuitState.HALF_OPEN
            else:
                raise CircuitBreakerError(
                    f"Circuit is OPEN (failures={self._failure_count}, "
                    f"retry after {self.recovery_timeout}s)"
                )

        try:
            result = func(*args, **kwargs)
        except self.expected_exceptions as e:
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                self._last_failure_time = time.time()
            else:
                self._record_failure()
            raise
        else:
            if self._state == CircuitState.HALF_OPEN:
                self._record_success()
            else:
                self._record_success()  # Reset failures on success
            return result


# Global circuit breaker instance for Rafiki calls
rafiki_breaker = CircuitBreaker(
    failure_threshold=5,
    recovery_timeout=30.0,
)
