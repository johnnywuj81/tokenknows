# T17 · IMConnector 抽象基类与注册中心

## 1. 目标
建立三家 IM（飞书/钉钉/企微）的统一抽象层。本任务只产 base class + registry + 单测，不实现具体平台。
Proposal: §9.2 IMConnector 抽象接口

## 2. 范围
- **In**: ABC 接口、IMNormalizedMessage 数据类、SignalResult 数据类、Connector 注册中心、health 监控
- **Out**: 具体平台实现（T18-T19）、SignalGate 实现（T20）

## 3. 接口契约

`backend/src/im/connector_base.py`：复制 Proposal §9.2 的 `IMConnector` ABC。关键方法：

| 方法 | 同步/异步 | 备注 |
|---|---|---|
| `get_authorize_url` | async | 返回平台 OAuth URL |
| `exchange_code` | async | code → token dict |
| `refresh_token` | async | 续期 |
| `revoke` | async | 撤回授权 |
| `list_chats` | async | 当前应用可见的 chat 列表 |
| `add_bot_to_chat` | async | 把 bot 加进群 |
| `list_chat_members` | async | 群成员 |
| `fetch_history` | async iter | 历史消息（自动分页） |
| `stream_messages` | async iter | 实时事件流 |
| `health` | async | 返回 `{ ok: bool, last_event_at, error_count_1h }` |

`IMNormalizedMessage` 数据类字段见 Proposal §9.2。

## 4. 组件分解

```
backend/src/im/
├── connector_base.py        ← ABC + 数据类
├── registry.py              ← 平台 → Connector 类的映射；运行时按 platform 字符串取实例
├── factory.py               ← 从 IMConnection 行构造 Connector 实例（解密凭据）
└── health_monitor.py        ← 周期性调用 health()，写 metrics

backend/tests/im/
├── test_registry.py
├── test_factory.py
└── fake_connector.py        ← 测试用 stub
```

## 5. 状态管理
N/A

## 6. 注册机制

```python
# registry.py
_REGISTRY: dict[str, type[IMConnector]] = {}

def register_connector(platform: str):
    def deco(cls): _REGISTRY[platform] = cls; return cls
    return deco

def get_connector_class(platform: str) -> type[IMConnector]:
    if platform not in _REGISTRY:
        raise UnknownPlatform(platform)
    return _REGISTRY[platform]
```

各 Adapter 在自己模块顶部 `@register_connector("feishu")`。

## 7. 必备状态（DoD）
- [ ] 抽象方法用 `@abstractmethod` 强制子类实现
- [ ] `IMNormalizedMessage` 用 `@dataclass(frozen=True)`
- [ ] 注册中心是模块级单例（不要每次新建）
- [ ] FakeConnector 实现所有接口（用于上层模块测试）
- [ ] health_monitor 默认 60s 一次，失败 3 次后写 metrics `im_connector_unhealthy`

## 8. 验收
- [ ] `from im.registry import get_connector_class; get_connector_class('feishu')` 在 T18 完成后能拿到飞书类
- [ ] 注册同一平台两次抛 `DuplicateRegistration`
- [ ] FakeConnector 能完整跑通一遍"假"端到端流程（用于 T20-T22 测试）
- [ ] mypy strict 通过

## 9. 已知陷阱
- ABC 的 `AsyncIterator` 签名要写 `AsyncIterator[IMNormalizedMessage]`，不是 `Iterator`；旧 Python 3.9 之前不支持泛型 ABC 方法
- `raw: dict` 字段进数据库前必须丢掉（敏感、体积大）
- factory 解密凭据时要复用 T16 的 `crypto.py`，不要重写

## 10. Claude Code 指令
先把 dataclass 和 ABC 写完，再写 registry，再写 factory，最后写 FakeConnector。FakeConnector 要做成"可注入历史消息列表 + 可触发事件流"的形式，方便 T20-T22 单测。
