"""PromptTemplate · YAML frontmatter + Jinja2 模板加载器.

文件格式:
    ---
    max_tokens: 400
    temperature: 0.3
    json_mode: true
    ---
    @system
    你是 ...

    @user
    为「{{ type_label }}」文档生成 ...

约束:
- frontmatter (--- 包夹) 是 YAML, 仅放 LLMOptions 兼容字段
- 正文按 @system / @user 双段, 至少有 @user (system 可省)
- 占位符走 Jinja2, 缺失变量 → KeyError (严格模式)
- 模板内不调 LLM (无副作用)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, StrictUndefined, Template

# Jinja2 环境: 严格模式 (缺变量直接报错, 避免悄悄渲染成空)
_JINJA_ENV = Environment(
    undefined=StrictUndefined,
    keep_trailing_newline=False,
    autoescape=False,  # markdown 模板不需要 HTML 转义
)


@dataclass(frozen=True)
class RenderedPrompt:
    """渲染后的 prompt, 直接给 LLMRouter 用."""

    system: str
    user: str
    options: dict[str, Any]  # frontmatter 解析出的 LLMOptions 字段


# 模板文件根目录 (app/prompts/)
_PROMPTS_ROOT = Path(__file__).parent


class PromptTemplate:
    """单个模板的加载 + 渲染."""

    __slots__ = ("_name", "_path", "_options", "_system_tpl", "_user_tpl", "_raw")

    def __init__(
        self,
        name: str,
        path: Path,
        options: dict[str, Any],
        system_tpl: Template | None,
        user_tpl: Template,
        raw: str,
    ) -> None:
        self._name = name
        self._path = path
        self._options = options
        self._system_tpl = system_tpl
        self._user_tpl = user_tpl
        self._raw = raw

    @classmethod
    def load(cls, name: str) -> PromptTemplate:
        """加载 `app/prompts/<name>.md` (name 是相对路径 + 文件名不带 .md).

        例: load("outline/weekly_report") → app/prompts/outline/weekly_report.md
        """
        path = _PROMPTS_ROOT / f"{name}.md"
        if not path.is_file():
            raise FileNotFoundError(f"PromptTemplate not found: {path}")
        raw = path.read_text(encoding="utf-8")
        options, system_src, user_src = _parse(raw)
        system_tpl = _JINJA_ENV.from_string(system_src) if system_src else None
        user_tpl = _JINJA_ENV.from_string(user_src)
        return cls(name, path, options, system_tpl, user_tpl, raw)

    def render(self, ctx: dict[str, Any]) -> RenderedPrompt:
        """用 ctx 渲染 system + user 段, 返回 RenderedPrompt."""
        system = self._system_tpl.render(**ctx) if self._system_tpl else ""
        user = self._user_tpl.render(**ctx)
        return RenderedPrompt(system=system, user=user, options=dict(self._options))

    @property
    def name(self) -> str:
        return self._name

    @property
    def path(self) -> Path:
        return self._path

    @property
    def raw(self) -> str:
        """原始文件内容, 用于 hash / 缓存键 / 调试."""
        return self._raw

    def __repr__(self) -> str:
        return f"PromptTemplate(name={self._name!r}, path={self._path})"


# ── 解析 ──────────────────────────────────────────────────────────


_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n(.*)\Z", re.DOTALL)
_SECTION_RE = re.compile(r"^@(system|user)\s*$", re.MULTILINE)


def _parse(raw: str) -> tuple[dict[str, Any], str, str]:
    """解析 frontmatter + @system / @user 段.

    Returns:
        (options, system_src, user_src) — system_src 可为空字符串
    """
    m = _FRONTMATTER_RE.match(raw)
    if m:
        front_yaml, body = m.group(1), m.group(2)
        try:
            options = yaml.safe_load(front_yaml) or {}
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML frontmatter: {e}") from e
        if not isinstance(options, dict):
            raise ValueError("Frontmatter must be a YAML dict")
    else:
        # 无 frontmatter, 全文都是 body
        options = {}
        body = raw

    # 切 @system / @user
    sections: dict[str, str] = {}
    last_tag = None
    last_pos = 0
    for m in _SECTION_RE.finditer(body):
        if last_tag is not None:
            sections[last_tag] = body[last_pos:m.start()].strip("\n")
        last_tag = m.group(1)
        last_pos = m.end() + 1  # +1 跳过换行
    if last_tag is not None:
        sections[last_tag] = body[last_pos:].strip("\n")
    else:
        # 没有 @system / @user 标签 → 全部当 user
        sections["user"] = body.strip("\n")

    if "user" not in sections:
        raise ValueError(f"PromptTemplate must have @user section")

    return options, sections.get("system", ""), sections["user"]


# ── 缓存加载 ──────────────────────────────────────────────────────


@lru_cache(maxsize=64)
def load(name: str) -> PromptTemplate:
    """带缓存的 load. 推荐入口 (避免重复 IO + 编译 Jinja)."""
    return PromptTemplate.load(name)


def clear_cache() -> None:
    """测试用: 清缓存."""
    load.cache_clear()
