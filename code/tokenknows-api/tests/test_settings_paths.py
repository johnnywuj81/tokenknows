"""v1.8 T107 · settings.egress_log_path 路径锚定单测.

验:
  - 默认值是绝对路径, 指向 code/tokenknows-api/data/egress.sqlite
  - cwd 切换不影响最终路径
  - 用户 env 传相对路径会 resolve 到 _API_ROOT (不依赖 cwd)
  - 用户 env 传绝对路径原样保留
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.config.settings import Settings, _API_ROOT


def test_api_root_points_to_api_dir() -> None:
    """_API_ROOT 应该是 code/tokenknows-api/."""
    assert _API_ROOT.name == "tokenknows-api"
    assert (_API_ROOT / "app").is_dir()
    assert (_API_ROOT / "tests").is_dir()


def test_default_egress_path_is_absolute_and_under_api_root() -> None:
    s = Settings()
    p = Path(s.egress_log_path)
    assert p.is_absolute()
    # 默认值应位于 api/data/ 下
    assert p == _API_ROOT / "data" / "egress.sqlite"


def test_relative_env_resolves_to_api_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """用户传 EGRESS_LOG_PATH=./data/x.sqlite, cwd 在哪都解析到 api/data/x.sqlite."""
    monkeypatch.setenv("EGRESS_LOG_PATH", "./data/x.sqlite")
    monkeypatch.chdir(tmp_path)  # cwd 切到完全不相关目录
    s = Settings()
    p = Path(s.egress_log_path)
    assert p.is_absolute()
    assert p == _API_ROOT / "data" / "x.sqlite"


def test_relative_env_with_nested_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """嵌套相对路径也正确锚定."""
    monkeypatch.setenv("EGRESS_LOG_PATH", "var/log/audit.sqlite")
    monkeypatch.chdir(tmp_path)
    s = Settings()
    assert Path(s.egress_log_path) == _API_ROOT / "var" / "log" / "audit.sqlite"


def test_absolute_env_kept_as_is(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """生产环境用绝对路径 (/var/tokenknows/...) 原样保留."""
    abs_path = "/tmp/test_egress_absolute.sqlite"
    monkeypatch.setenv("EGRESS_LOG_PATH", abs_path)
    s = Settings()
    assert s.egress_log_path == abs_path


def test_cwd_change_does_not_affect_default(tmp_path: Path) -> None:
    """重置 cwd 多次, 默认值始终指向同一绝对路径 (回归 v1.7 bug)."""
    original_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        s1 = Settings()
        os.chdir("/tmp")
        s2 = Settings()
        assert s1.egress_log_path == s2.egress_log_path
        assert Path(s1.egress_log_path).is_absolute()
    finally:
        os.chdir(original_cwd)
