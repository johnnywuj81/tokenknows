"""v1.8 T112 · _parse_llm_json 容错 markdown 包裹 JSON 单测.

验:
  - 纯 JSON (无包裹) 直接解析
  - markdown ```json...``` 包裹
  - markdown ```...``` 包裹 (无 json 标签)
  - 前后说明文字 + JSON 块混合
  - 列表 [...] 也支持
  - 真的烂数据 (空 / 非 JSON) 仍抛 JSONDecodeError
"""

from __future__ import annotations

import json
import pytest

from app.services.generation_service import _parse_llm_json


def test_plain_json_object():
    assert _parse_llm_json('{"a": 1}') == {"a": 1}


def test_plain_json_array():
    assert _parse_llm_json('[1, 2, 3]') == [1, 2, 3]


def test_markdown_json_fence():
    raw = '```json\n{"nodes": [{"id": "n1"}]}\n```'
    assert _parse_llm_json(raw) == {"nodes": [{"id": "n1"}]}


def test_markdown_plain_fence():
    raw = '```\n{"x": 42}\n```'
    assert _parse_llm_json(raw) == {"x": 42}


def test_uppercase_json_tag():
    raw = '```JSON\n{"x": 1}\n```'
    assert _parse_llm_json(raw) == {"x": 1}


def test_preamble_text_with_json_block():
    """Claude 经常加 'Here is the JSON: { ... }' 前缀."""
    raw = '这是结果:\n{"nodes": [{"id": "n_alice"}]}\n谢谢!'
    assert _parse_llm_json(raw) == {"nodes": [{"id": "n_alice"}]}


def test_postamble_text():
    raw = '{"x": 1}\n以上是结果.'
    # 第一次 json.loads 失败, 提取首个 {...} 块
    result = _parse_llm_json(raw)
    assert result == {"x": 1}


def test_extra_whitespace():
    raw = '   \n\n  {"x": 1}  \n\n  '
    assert _parse_llm_json(raw) == {"x": 1}


def test_nested_object_in_fence():
    raw = '```json\n{"edges": [{"source": "a", "target": "b"}]}\n```'
    assert _parse_llm_json(raw) == {"edges": [{"source": "a", "target": "b"}]}


def test_empty_string_raises():
    with pytest.raises(json.JSONDecodeError):
        _parse_llm_json("")


def test_garbage_raises():
    with pytest.raises(json.JSONDecodeError):
        _parse_llm_json("this is not JSON at all")


def test_partial_json_salvaged_by_repair():
    """F 改造后行为变更:
    截断 JSON (LLM 中途断流) 走 json-repair 层尽力恢复, 比 crash 给上游更多信息.
    上游 caller 应再用 pydantic / 业务校验拦不完整的结构.

    旧行为: raises JSONDecodeError
    新行为: returns {'a': ''} 之类 (json-repair 补齐缺的 value)
    """
    result = _parse_llm_json('{"a": ')
    assert isinstance(result, dict)
    assert "a" in result
