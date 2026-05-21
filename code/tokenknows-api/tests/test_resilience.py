"""CircuitBreaker + retry_with_backoff + BulkheadSemaphore 单测.

用 asyncio + monkeypatch sleep 控制时间, 不依赖真等.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from app.core.resilience import (
    BulkheadSemaphore,
    CircuitBreaker,
    CircuitOpenError,
    CircuitState,
    get_circuit_breaker,
    retry_with_backoff,
)


# ─── CircuitBreaker · 基本状态机 ────────────────────────────────────


@pytest.mark.asyncio
async def test_breaker_starts_closed() -> None:
    cb = CircuitBreaker(name="t")
    assert cb.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_breaker_success_keeps_closed() -> None:
    cb = CircuitBreaker(name="t", failure_threshold=3)
    fake = AsyncMock(return_value="ok")
    for _ in range(5):
        result = await cb.call(fake)
        assert result == "ok"
    assert cb.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_breaker_opens_after_threshold_failures() -> None:
    cb = CircuitBreaker(name="t", failure_threshold=3)
    fail = AsyncMock(side_effect=RuntimeError("boom"))
    # 3 次失败后开断
    for _ in range(3):
        with pytest.raises(RuntimeError):
            await cb.call(fail)
    assert cb.state == CircuitState.OPEN


@pytest.mark.asyncio
async def test_breaker_open_rejects_calls_with_circuit_open_error() -> None:
    cb = CircuitBreaker(name="t", failure_threshold=2, recovery_timeout=60)
    fail = AsyncMock(side_effect=RuntimeError("x"))
    for _ in range(2):
        with pytest.raises(RuntimeError):
            await cb.call(fail)
    # 第 3 次应该被 fast-fail
    fake_after = AsyncMock(return_value="never")
    with pytest.raises(CircuitOpenError) as exc:
        await cb.call(fake_after)
    assert exc.value.name == "t"
    assert exc.value.retry_after > 0
    # 被拒绝的调用不应实际执行
    fake_after.assert_not_called()


@pytest.mark.asyncio
async def test_breaker_transitions_to_half_open_after_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """recovery_timeout 后第一次调用 → HALF_OPEN."""
    cb = CircuitBreaker(name="t", failure_threshold=1, recovery_timeout=0.01)
    fail = AsyncMock(side_effect=RuntimeError("x"))
    with pytest.raises(RuntimeError):
        await cb.call(fail)
    assert cb.state == CircuitState.OPEN
    # 等够 recovery_timeout
    await asyncio.sleep(0.02)
    # 这次成功应该 close
    ok = AsyncMock(return_value="ok")
    result = await cb.call(ok)
    assert result == "ok"
    assert cb.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_breaker_half_open_failure_reopens() -> None:
    cb = CircuitBreaker(name="t", failure_threshold=1, recovery_timeout=0.01)
    fail = AsyncMock(side_effect=RuntimeError("x"))
    with pytest.raises(RuntimeError):
        await cb.call(fail)
    await asyncio.sleep(0.02)
    # HALF_OPEN 探测调用失败 → 重新 OPEN
    with pytest.raises(RuntimeError):
        await cb.call(fail)
    assert cb.state == CircuitState.OPEN


@pytest.mark.asyncio
async def test_breaker_excluded_exceptions_dont_open() -> None:
    """4xx 等业务错不计失败."""

    class ClientError(Exception):
        pass

    cb = CircuitBreaker(
        name="t", failure_threshold=2, excluded_exceptions=(ClientError,)
    )
    fail = AsyncMock(side_effect=ClientError("400"))
    for _ in range(5):
        with pytest.raises(ClientError):
            await cb.call(fail)
    assert cb.state == CircuitState.CLOSED


def test_breaker_manual_reset() -> None:
    cb = CircuitBreaker(name="t")
    cb._state = CircuitState.OPEN
    cb._failure_count = 99
    cb.reset()
    assert cb.state == CircuitState.CLOSED
    assert cb._failure_count == 0


# ─── breaker registry ─────────────────────────────────────────────


def test_get_circuit_breaker_singleton_per_name() -> None:
    a = get_circuit_breaker("test-singleton")
    b = get_circuit_breaker("test-singleton")
    assert a is b


def test_get_circuit_breaker_distinct_names() -> None:
    a = get_circuit_breaker("name-a")
    b = get_circuit_breaker("name-b")
    assert a is not b


# ─── retry_with_backoff ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_retry_success_first_try(monkeypatch: pytest.MonkeyPatch) -> None:
    """第一次就成功不需 retry."""
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())   # 防真等
    calls = 0

    @retry_with_backoff(max_retries=3, base_delay=0.001)
    async def fn() -> str:
        nonlocal calls
        calls += 1
        return "ok"

    result = await fn()
    assert result == "ok"
    assert calls == 1


@pytest.mark.asyncio
async def test_retry_eventually_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())
    calls = 0

    @retry_with_backoff(max_retries=3, base_delay=0.001)
    async def fn() -> str:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise RuntimeError("transient")
        return "ok"

    result = await fn()
    assert result == "ok"
    assert calls == 3


@pytest.mark.asyncio
async def test_retry_exhausts_and_reraises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())

    @retry_with_backoff(max_retries=2, base_delay=0.001)
    async def fn() -> str:
        raise RuntimeError("always fails")

    with pytest.raises(RuntimeError, match="always fails"):
        await fn()


@pytest.mark.asyncio
async def test_retry_only_specified_exceptions(monkeypatch: pytest.MonkeyPatch) -> None:
    """非 retryable 异常不 retry, 直接抛."""
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())
    calls = 0

    @retry_with_backoff(
        max_retries=3, base_delay=0.001,
        retryable_exceptions=(ValueError,),
    )
    async def fn() -> str:
        nonlocal calls
        calls += 1
        raise KeyError("not retryable")   # KeyError ∉ retryable

    with pytest.raises(KeyError):
        await fn()
    assert calls == 1   # 只调用了 1 次, 没 retry


# ─── BulkheadSemaphore ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_bulkhead_allows_within_limit() -> None:
    bh = BulkheadSemaphore("test-bh", max_concurrent=3)
    async with bh:
        assert bh._active == 1
    assert bh._active == 0


@pytest.mark.asyncio
async def test_bulkhead_concurrent_count_tracked() -> None:
    bh = BulkheadSemaphore("test-bh-2", max_concurrent=2)
    async with bh:
        async with bh:
            assert bh._active == 2
        assert bh._active == 1
    assert bh._active == 0


@pytest.mark.asyncio
async def test_bulkhead_timeout_raises() -> None:
    """已满且 timeout 短 → 抛 TimeoutError."""
    bh = BulkheadSemaphore("test-bh-full", max_concurrent=1, timeout=0.05)

    async def hog() -> None:
        async with bh:
            await asyncio.sleep(0.5)

    task = asyncio.create_task(hog())
    await asyncio.sleep(0.01)   # 让 task 进入 with
    with pytest.raises(TimeoutError, match="full"):
        async with bh:
            pass
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
