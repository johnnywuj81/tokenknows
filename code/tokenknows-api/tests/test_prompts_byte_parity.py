"""PromptTemplate 字节级回归测试.

A1 阶段关键: 从 generation_service.py 抽出 prompt 到 .md 模板后,
对相同 ctx 渲染的 system / user 必须与原硬编码字符串字节级相等.
否则视为破坏现有 4 类生成行为.
"""

from __future__ import annotations

import pytest

from app.prompts import PromptTemplate
from app.prompts.base import _parse


# ── _parse 单元测试 ────────────────────────────────────────────


def test_parse_frontmatter_plus_two_sections() -> None:
    raw = """---
max_tokens: 100
temperature: 0.5
---
@system
sys content here

@user
user content here
"""
    options, sys_src, user_src = _parse(raw)
    assert options == {"max_tokens": 100, "temperature": 0.5}
    assert sys_src == "sys content here"
    assert user_src == "user content here"


def test_parse_no_frontmatter_user_only() -> None:
    raw = "just user content\n"
    options, sys_src, user_src = _parse(raw)
    assert options == {}
    assert sys_src == ""
    assert user_src == "just user content"


def test_parse_no_user_raises() -> None:
    raw = "---\n---\n@system\nsys only\n"
    with pytest.raises(ValueError, match="must have @user"):
        _parse(raw)


def test_parse_non_dict_frontmatter_raises() -> None:
    """frontmatter 解析后必须是 dict, 列表/标量不合法."""
    raw = "---\n- a\n- b\n---\n@user\nx\n"
    with pytest.raises(ValueError, match="must be a YAML dict"):
        _parse(raw)


def test_parse_truly_invalid_yaml_raises() -> None:
    """无法解析的 YAML 抛 ValueError."""
    raw = "---\n{unclosed: brace\n---\n@user\nx\n"
    with pytest.raises(ValueError, match="Invalid YAML"):
        _parse(raw)


# ── outline/_default 字节级回归 ─────────────────────────────────


def _reproduce_old_outline_prompts(type_label: str, time_window: str, fallback: list[str]) -> tuple[str, str]:
    """字节级复现 generation_service.py:_stage_outline 第 362-371 行原本的字符串."""
    system_prompt = (
        "你是 AI 研发知识资产平台的文档大纲生成器。严格按 JSON schema 输出, 不要任何额外文字。\n"
        'JSON schema: {"chapters": ["章节1", "章节2", ...]}\n'
        "约束: 章节标题简洁(≤8 字符), 数量 5-7 个, 顺序符合该文档类型的标准结构。"
    )
    user_prompt = (
        f"为「{type_label}」文档生成章节大纲。\n"
        f"时间范围: {time_window}\n"
        f"参考标准结构 (你可微调以贴合本次主题): {' / '.join(fallback)}"
    )
    return system_prompt, user_prompt


@pytest.mark.parametrize(
    "type_label,time_window,fallback",
    [
        ("项目周报", "this_week", ["本周进展", "Bug 与解决", "关键决策", "风险与阻塞", "下周计划"]),
        ("技术方案", "last_30_days", ["背景", "目标", "设计思路", "关键决策", "风险与取舍", "实施计划"]),
        ("ADR 架构决策记录", "last_week", ["上下文", "决策内容", "备选方案", "后果", "状态"]),
        ("问题复盘报告", "last_14_days", ["现象", "影响范围", "根因", "解决过程", "改进措施", "时间线"]),
    ],
)
def test_outline_default_byte_parity_4_types(type_label: str, time_window: str, fallback: list[str]) -> None:
    """outline/_default.md 渲染结果必须与现有硬编码字节级一致 (4 类)."""
    tpl = PromptTemplate.load("outline/_default")
    rendered = tpl.render({
        "type_label": type_label,
        "time_window": time_window,
        "fallback_joined": " / ".join(fallback),
    })
    expected_sys, expected_user = _reproduce_old_outline_prompts(type_label, time_window, fallback)
    assert rendered.system == expected_sys, (
        f"system 字节不一致!\n"
        f"--- 模板渲染 ---\n{rendered.system!r}\n"
        f"--- 原硬编码 ---\n{expected_sys!r}"
    )
    assert rendered.user == expected_user, (
        f"user 字节不一致!\n"
        f"--- 模板渲染 ---\n{rendered.user!r}\n"
        f"--- 原硬编码 ---\n{expected_user!r}"
    )


def test_outline_default_options() -> None:
    """frontmatter options 必须匹配原 LLMOptions."""
    tpl = PromptTemplate.load("outline/_default")
    rendered = tpl.render({
        "type_label": "x", "time_window": "y", "fallback_joined": "z",
    })
    assert rendered.options == {
        "temperature": 0.3,
        "max_tokens": 400,
        "json_mode": True,
        "timeout_seconds": 60,
    }


# ── content/_default 字节级回归 ────────────────────────────────


def _reproduce_old_content_prompts(type_label: str, time_window: str, title: str) -> tuple[str, str]:
    system_prompt = (
        "你是 AI 研发知识资产平台的章节生成器。根据章节标题生成 200-400 字的"
        "markdown 草稿, 风格客观、要点清晰。允许包含 `[1] [2] [3]` 形式的"
        "证据角标占位 (后续阶段会回填真证据)。直接输出 markdown, 不要前置说明。"
    )
    user_prompt = (
        f"文档类型: {type_label}\n"
        f"时间范围: {time_window}\n"
        f"当前章节标题: {title}\n\n"
        "请生成本章节的 markdown 草稿 (200-400 字, 含 2-3 个 [N] 引用占位)."
    )
    return system_prompt, user_prompt


def test_content_default_byte_parity() -> None:
    tpl = PromptTemplate.load("content/_default")
    rendered = tpl.render({
        "type_label": "项目周报",
        "time_window": "this_week",
        "title": "本周进展",
    })
    expected_sys, expected_user = _reproduce_old_content_prompts("项目周报", "this_week", "本周进展")
    assert rendered.system == expected_sys
    assert rendered.user == expected_user


def test_content_default_options() -> None:
    tpl = PromptTemplate.load("content/_default")
    rendered = tpl.render({"type_label": "x", "time_window": "y", "title": "z"})
    assert rendered.options == {
        "temperature": 0.5,
        "max_tokens": 800,
        "timeout_seconds": 90,
    }


# ── assess/_default 字节级回归 ─────────────────────────────────


def _reproduce_old_assess_prompts(asset_type: str, title: str, digest: str) -> tuple[str, str]:
    system_prompt = (
        "你是一位严格的技术文档审稿人, 评估文档的'空话密度'(slop_score).\n"
        "空话 = 笼统形容 / 套话 / 无依据断言 / 模板化措辞 (e.g. '本周高效推进各项工作').\n"
        "返回严格 JSON, 不要任何其它文字, 不要 markdown 代码块:\n"
        '{"slop_score": 0.0-1.0, "reasoning": "≤30字理由"}\n'
        "评分尺度:\n"
        "  0.00-0.15  几乎全是具体事实/数据/引用 (优)\n"
        "  0.15-0.30  少量套话, 主体扎实 (良)\n"
        "  0.30-0.50  套话与事实并存 (中)\n"
        "  0.50-0.80  套话居多, 缺少具体内容 (差)\n"
        "  0.80-1.00  几乎全是空话 (劣)"
    )
    user_prompt = (
        f"文档类型: {asset_type}\n"
        f"标题: {title}\n\n"
        f"全文摘要 (前 8 章, 各 200 字):\n{digest}\n\n"
        "请输出 JSON."
    )
    return system_prompt, user_prompt


def test_assess_default_byte_parity() -> None:
    tpl = PromptTemplate.load("assess/_default")
    digest_sample = "## 本周进展\n本周完成 PR X Y Z\n\n## Bug 与解决\n修复 ..."
    rendered = tpl.render({
        "asset_type": "weekly_report",
        "title": "周报 · 2026-W21",
        "digest": digest_sample,
    })
    expected_sys, expected_user = _reproduce_old_assess_prompts("weekly_report", "周报 · 2026-W21", digest_sample)
    assert rendered.system == expected_sys
    assert rendered.user == expected_user


def test_strict_undefined_raises_on_missing_var() -> None:
    """缺变量必须 raise (StrictUndefined 保证), 否则会悄悄渲染成空."""
    from jinja2 import UndefinedError
    tpl = PromptTemplate.load("outline/_default")
    with pytest.raises(UndefinedError):
        tpl.render({"type_label": "x"})  # 缺 time_window / fallback_joined


def test_load_caches() -> None:
    """重复 load 不应重新读 IO."""
    from app.prompts.base import load, clear_cache
    clear_cache()
    a = load("outline/_default")
    b = load("outline/_default")
    assert a is b  # 缓存命中
