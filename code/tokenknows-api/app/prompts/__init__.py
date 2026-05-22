"""TokenKnows · Prompt 模板子系统 (v0.2 升级).

把硬编码在 generation_service.py 里的 prompt 抽到独立 .md 文件,
支持 Jinja2 占位符 + skill 注入 + 字节级回归保证.

设计依据: Architecture.md §5.7

使用示例:
    from app.prompts import PromptTemplate

    tpl = PromptTemplate.load("outline/weekly_report")
    rendered = tpl.render({"type_label": "项目周报", "time_window": "this_week", ...})
    # rendered.system / rendered.user / rendered.options
"""

from app.prompts.base import PromptTemplate, RenderedPrompt

__all__ = ["PromptTemplate", "RenderedPrompt"]
