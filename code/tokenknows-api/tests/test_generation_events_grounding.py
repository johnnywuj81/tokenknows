"""T126 · events grounding 纯函数测试.

只测纯函数 (helpers + _stage_collect events 出现在 metadata), 不打 LLM /
不依赖 fixture 数据库, 跑得快且确定性强.
"""

from __future__ import annotations

from app.services.generation_service import (
    _MAX_EVENTS_FOR_PROMPT,
    _MAX_EVENT_CONTENT_CHARS,
    _format_events_block,
    _time_window_from_iso,
)


def test_format_events_block_empty_returns_empty_string() -> None:
    """events=[] → '' (让 prompt 模板 if 分支可以跳过)."""
    assert _format_events_block([]) == ""


def test_format_events_block_single_event() -> None:
    evs = [
        {
            "author": {"name": "alice"},
            "title": "OAuth 失败",
            "content": "OAuth 403, claude.ai 域被卡",
        }
    ]
    out = _format_events_block(evs)
    assert "[1] alice · OAuth 失败" in out
    assert "OAuth 403" in out


def test_format_events_block_missing_author_fallback() -> None:
    """author 缺失 → '?' 占位, 不抛."""
    out = _format_events_block([{"title": "t", "content": "c"}])
    assert "[1] ? · t" in out


def test_format_events_block_truncates_long_content() -> None:
    """超长 content 被截断到 _MAX_EVENT_CONTENT_CHARS + '…'."""
    long_text = "a" * (_MAX_EVENT_CONTENT_CHARS + 200)
    out = _format_events_block([{"title": "x", "content": long_text}])
    # 末尾应是 '…'
    assert out.endswith("…")
    # 原始全长不应完整出现
    assert long_text not in out


def test_format_events_block_caps_at_max_for_prompt() -> None:
    """事件数超 _MAX_EVENTS_FOR_PROMPT 时只保留前 N (按入参顺序, 即调用前已排序)."""
    many = [
        {"title": f"t{i}", "content": f"c{i}", "author": {"name": "x"}}
        for i in range(_MAX_EVENTS_FOR_PROMPT + 5)
    ]
    out = _format_events_block(many)
    # 包含 t0 ... t_{MAX-1}, 不包含 t_{MAX}
    assert f"t{_MAX_EVENTS_FOR_PROMPT - 1}" in out
    assert f"t{_MAX_EVENTS_FOR_PROMPT}" not in out


def test_format_events_block_no_title_uses_placeholder() -> None:
    out = _format_events_block([{"content": "x", "author": {"name": "a"}}])
    assert "(无标题)" in out


def test_time_window_from_iso_known_values_decrease_in_days() -> None:
    """已知 window 名应返回 ISO 时间戳, 且窗口越长 from 越早."""
    a = _time_window_from_iso("this_week")
    b = _time_window_from_iso("last_30_days")
    # 字符串 ISO 直接比大小 (UTC ISO 字典序 = 时间序)
    assert b < a  # 30 天前比 7 天前更早 → 字符串更小


def test_time_window_from_iso_unknown_defaults_to_30_days() -> None:
    """容错: 未识别 window 名按 30 天处理 (与 last_30_days 同)."""
    unknown = _time_window_from_iso("forever-ago")
    expected = _time_window_from_iso("last_30_days")
    # 同秒内调用可能差 1 微秒 → 比较前 19 字符 (年月日时分秒) 即可
    assert unknown[:19] == expected[:19]


def test_time_window_from_iso_none_defaults_to_30_days() -> None:
    """req.time_window 可能是 None → 走 30 天默认."""
    out = _time_window_from_iso(None)
    expected = _time_window_from_iso("last_30_days")
    assert out[:19] == expected[:19]
