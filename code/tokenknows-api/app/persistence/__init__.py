"""持久化层 · SQLite 单进程 + 文件存储.

设计动机:
    MVP 初期 generation_service 用 dict 做内存索引, 重启丢数据. 客户演示反复
    生成同一文档体感不好. 切到 SQLite 一文件 (data/state.sqlite) 仍保 dict
    做读 cache + sync 写, 仅在 mutation 时 commit, 启动时 _bootstrap() 全量 load.

规避了 SQLAlchemy 重型依赖. 不连 Postgres - 那是生产部署 (Architecture.md §17).
"""

from app.persistence.store import bootstrap, get_db, persist

__all__ = ["bootstrap", "get_db", "persist"]
