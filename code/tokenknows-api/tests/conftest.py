"""pytest fixtures shared across test modules.

将仓库根注入 sys.path 让 `import app.xxx` 工作 (.venv 不一定 pip install -e).
"""

from __future__ import annotations

import sys
from pathlib import Path

# tokenknows-api/ 根目录
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
