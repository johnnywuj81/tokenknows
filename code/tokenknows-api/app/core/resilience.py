"""Resilience primitives: CircuitBreaker, retry with backoff, BulkheadSemaphore.

⚠ 0 修改复制自 digital_enterprise/app/core/resilience.py
   (Architecture.md §17.1 "直接复制" 行动)

Usage:
    breaker = CircuitBreaker(name="llm-anthropic", failure_threshold=5)
    result = await breaker.call(some_async_fn, *args, **kwargs)

    @retry_with_backoff(max_retries=3, base_delay=1.0)
    async def flaky_call(): ...
"""

from __future__ import annotations

import asyncio
import functools
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


# ── Circuit Breaker ──────────────────────────────────────────────────


class CircuitState(str, Enum):
    CLOSED = "closed"        # Normal — requests pass through
    OPEN = "open"            # Tripped — requests fail fast
    HALF_OPEN = "half_open"  # Probing — one test request allowed


class CircuitOpenError(Exception):
    """Raised when the circuit breaker is open and rejecting calls."""

    def __init__(self, name: str, retry_after: float) -> None:
        self.name = name
        self.retry_after = retry_after
        super().__init__(f"Circuit '{name}' is OPEN, retry after {retry_after:.1f}s")


@dataclass
class CircuitBreaker:
    """Async circuit breaker with configurable thresholds.

    Parameters:
        name: Identifier for logging/metrics (e.g., "llm-anthropic")
        failure_threshold: Consecutive failures before opening
        recovery_timeout: Seconds to wait before entering half-open state
        half_open_max_calls: Test calls allowed in half-open state
        excluded_exceptions: Exceptions that don't count as failures (e.g., 4xx client errors)
    """

    name: str
    failure_threshold: int = 5
    recovery_timeout: float = 30.0
    half_open_max_calls: int = 1
    excluded_exceptions: tuple[type[Exception], ...] = ()

    # Internal state
    _state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    _failure_count: int = field(default=0, init=False)
    _last_failure_time: float = field(default=0.0, init=False)
    _half_open_calls: int = field(default=0, init=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)

    @property
    def state(self) -> CircuitState:
        return self._state

    async def call(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Execute fn through the circuit breaker."""
        async with self._lock:
            self._check_state_transition()

            if self._state == CircuitState.OPEN:
                retry_after = self.recovery_timeout - (time.monotonic() - self._last_failure_time)
                raise CircuitOpenError(self.name, max(0, retry_after))

            if self._state == CircuitState.HALF_OPEN and self._half_open_calls >= self.half_open_max_calls:
                raise CircuitOpenError(self.name, self.recovery_timeout)

        # Execute the call outside the lock
        try:
            result = await fn(*args, **kwargs)
        except Exception as exc:
            if isinstance(exc, self.excluded_exceptions):
                raise
            await self._on_failure(exc)
            raise

        await self._on_success()
        return result

    def _check_state_transition(self) -> None:
        """Transition OPEN → HALF_OPEN after recovery timeout."""
        if self._state == CircuitState.OPEN:
            elapsed = time.monotonic() - self._last_failure_time
            if elapsed >= self.recovery_timeout:
                logger.info("Circuit '%s' entering HALF_OPEN after %.1fs", self.name, elapsed)
                self._state = CircuitState.HALF_OPEN
                self._half_open_calls = 0

    async def _on_success(self) -> None:
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                logger.info("Circuit '%s' recovered → CLOSED", self.name)
                self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._half_open_calls = 0

    async def _on_failure(self, exc: Exception) -> None:
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()

            if self._state == CircuitState.HALF_OPEN:
                logger.warning("Circuit '%s' test call failed → OPEN: %s", self.name, exc)
                self._state = CircuitState.OPEN
            elif self._failure_count >= self.failure_threshold:
                logger.warning(
                    "Circuit '%s' opened after %d failures: %s",
                    self.name, self._failure_count, exc,
                )
                self._state = CircuitState.OPEN

    def reset(self) -> None:
        """Manually reset the circuit to CLOSED state."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._half_open_calls = 0


# ── Circuit Breaker Registry ─────────────────────────────────────────

_breakers: dict[str, CircuitBreaker] = {}


def get_circuit_breaker(
    name: str,
    failure_threshold: int = 5,
    recovery_timeout: float = 30.0,
) -> CircuitBreaker:
    """Get or create a named circuit breaker (singleton per name)."""
    if name not in _breakers:
        _breakers[name] = CircuitBreaker(
            name=name,
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
        )
    return _breakers[name]


# ── Retry with Backoff ───────────────────────────────────────────────


def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    backoff_factor: float = 2.0,
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
) -> Callable:
    """Decorator: retry an async function with exponential backoff.

    Usage:
        @retry_with_backoff(max_retries=3)
        async def call_external_api(): ...
    """

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc: Exception | None = None
            for attempt in range(max_retries + 1):
                try:
                    return await fn(*args, **kwargs)
                except retryable_exceptions as exc:
                    last_exc = exc
                    if attempt == max_retries:
                        break
                    delay = min(base_delay * (backoff_factor ** attempt), max_delay)
                    logger.warning(
                        "Retry %d/%d for %s after %.1fs: %s",
                        attempt + 1, max_retries, fn.__name__, delay, exc,
                    )
                    await asyncio.sleep(delay)
            raise last_exc  # type: ignore[misc]

        return wrapper

    return decorator


# ── Bulkhead Semaphore ───────────────────────────────────────────────


class BulkheadSemaphore:
    """Limits concurrent calls to a resource (bulkhead pattern).

    Usage:
        bulkhead = BulkheadSemaphore(name="embedding", max_concurrent=10)
        async with bulkhead:
            await do_embedding(...)
    """

    def __init__(self, name: str, max_concurrent: int = 10, timeout: float = 30.0) -> None:
        self.name = name
        self.max_concurrent = max_concurrent
        self.timeout = timeout
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._waiting = 0
        self._active = 0

    async def __aenter__(self) -> BulkheadSemaphore:
        self._waiting += 1
        try:
            await asyncio.wait_for(self._semaphore.acquire(), timeout=self.timeout)
        except TimeoutError:
            self._waiting -= 1
            raise TimeoutError(
                f"Bulkhead '{self.name}' full: {self._active}/{self.max_concurrent} active, "
                f"{self._waiting} waiting, timeout {self.timeout}s"
            )
        self._waiting -= 1
        self._active += 1
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        self._active -= 1
        self._semaphore.release()

    @property
    def stats(self) -> dict:
        return {
            "name": self.name,
            "active": self._active,
            "waiting": self._waiting,
            "max_concurrent": self.max_concurrent,
        }
