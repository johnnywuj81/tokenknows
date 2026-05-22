"""main.py lifespan · retention loop 后台 task (v0.3.1 P1).

覆盖:
- 测试模式下 (PYTEST_CURRENT_TEST 自动设置) 不启 retention task
- 显式 DISABLE_IM_RETENTION=1 也不启
- 非测试模式启 task + 关停时优雅 cancel
- _is_test_mode 边界
"""

from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, patch

import pytest

from app import main


def test_is_test_mode_under_pytest() -> None:
    """pytest 运行时 PYTEST_CURRENT_TEST 一定存在."""
    assert "PYTEST_CURRENT_TEST" in os.environ
    assert main._is_test_mode() is True


def test_is_test_mode_disable_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """DISABLE_IM_RETENTION=1 也被识别."""
    # 清掉 pytest 标记后, 单独靠 DISABLE 也能返 True
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("DISABLE_IM_RETENTION", "1")
    assert main._is_test_mode() is True


def test_is_test_mode_normal_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """两个标记都缺 → 视为生产模式."""
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delenv("DISABLE_IM_RETENTION", raising=False)
    assert main._is_test_mode() is False


@pytest.mark.asyncio
async def test_lifespan_skips_retention_in_test_mode() -> None:
    """测试模式下 lifespan 不创建 retention_sweep task."""
    # 直接走 lifespan async generator 而非 TestClient
    sweep_calls: list[int] = []

    async def fake_loop(interval: int) -> None:
        sweep_calls.append(interval)
        # 立刻让出, 不实际跑
        await asyncio.sleep(0)

    with patch.object(main.im_retention, "retention_sweep_loop", new=fake_loop):
        async with main.lifespan(main.app):
            # 测试模式 → fake_loop 永远不会被调用
            await asyncio.sleep(0.01)
    assert sweep_calls == []


@pytest.mark.asyncio
async def test_lifespan_starts_and_cancels_retention(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """非测试模式: lifespan 应启 task, 关停时 cancel."""
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delenv("DISABLE_IM_RETENTION", raising=False)

    cancel_seen = asyncio.Event()
    started = asyncio.Event()

    async def fake_loop(interval: int) -> None:
        started.set()
        try:
            await asyncio.sleep(3600)  # 模拟长任务
        except asyncio.CancelledError:
            cancel_seen.set()
            raise

    async def fake_token_loop(interval: int) -> None:
        await asyncio.sleep(3600)  # 不需要单独检测, 但要存在

    with patch.object(main.im_retention, "retention_sweep_loop", new=fake_loop), \
         patch.object(main.im_token_refresher, "token_refresher_loop", new=fake_token_loop):
        async with main.lifespan(main.app):
            await asyncio.wait_for(started.wait(), timeout=1.0)
        await asyncio.wait_for(cancel_seen.wait(), timeout=1.0)


@pytest.mark.asyncio
async def test_lifespan_starts_token_refresher_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """v0.3.1 I: 非测试模式应启 token_refresher_loop."""
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delenv("DISABLE_IM_RETENTION", raising=False)

    token_started = asyncio.Event()
    token_cancel_seen = asyncio.Event()

    async def fake_token_loop(interval: int) -> None:
        token_started.set()
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            token_cancel_seen.set()
            raise

    async def fake_retention(interval: int) -> None:
        await asyncio.sleep(3600)

    with patch.object(main.im_retention, "retention_sweep_loop", new=fake_retention), \
         patch.object(main.im_token_refresher, "token_refresher_loop", new=fake_token_loop):
        async with main.lifespan(main.app):
            await asyncio.wait_for(token_started.wait(), timeout=1.0)
        await asyncio.wait_for(token_cancel_seen.wait(), timeout=1.0)


@pytest.mark.asyncio
async def test_lifespan_bootstrap_ordering(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """bootstrap 顺序: db → generation → skills → im → retention."""
    call_order: list[str] = []

    def make_spy(name: str):
        def spy(*args, **kw):
            call_order.append(name)
        return spy

    monkeypatch.setattr(main, "bootstrap_db", make_spy("db"))
    monkeypatch.setattr(main, "_bootstrap_from_db", make_spy("generation"))
    monkeypatch.setattr(main, "bootstrap_skills", make_spy("skills"))
    monkeypatch.setattr(main, "bootstrap_im", make_spy("im"))

    async with main.lifespan(main.app):
        pass

    assert call_order == ["db", "generation", "skills", "im"]
