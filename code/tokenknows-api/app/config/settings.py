"""TokenKnows API · 全局配置 (pydantic-settings 读 .env.local).

设计依据: digital_enterprise/app/config/settings.py 模板 +
SharedFoundations.md §2 (错误归一表) + Architecture.md §17.1 (LLM Gateway 配置)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 在 Settings 实例化前预处理:
# pydantic-settings 默认 process env > env_file. 但 shell 中可能存在空值 (如 Claude Code CLI
# 注入的 ANTHROPIC_API_KEY="") 会覆盖 .env.local 的真实值. 这里主动:
#   1. 先清掉 process env 里的空值
#   2. 用 dotenv override=True 让 .env.local 强制覆盖剩余的 process env
_env_path = Path(__file__).parent.parent.parent / ".env.local"
for _key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "MINIMAX_API_KEY", "OLLAMA_API_KEY"):
    if os.environ.get(_key, "").strip() == "":
        os.environ.pop(_key, None)
if _env_path.exists():
    load_dotenv(_env_path, override=True)


class Settings(BaseSettings):
    """全局配置 - 自动从 .env.local 加载 (cwd / parent dirs)."""

    model_config = SettingsConfigDict(
        env_file=".env.local",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ─── LLM Provider Keys ───────────────────────────────────────
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    minimax_api_key: str | None = Field(default=None, alias="MINIMAX_API_KEY")
    minimax_base_url: str = Field(
        default="https://api.minimaxi.com/v1",
        alias="MINIMAX_BASE_URL",
    )
    # Ollama (本地或 Ollama Cloud, OpenAI-compatible endpoint)
    # ⚠ Ollama Cloud 模型 (后缀 ":cloud") 实际走 Ollama 后端到云厂商;
    #   仍属于云出域, 会被 audit 但走 ollama 单一通道.
    ollama_api_key: str | None = Field(default=None, alias="OLLAMA_API_KEY")
    ollama_base_url: str = Field(
        default="http://localhost:11434/v1",
        alias="OLLAMA_BASE_URL",
    )

    # ─── LLM Gateway 三层出域门禁 ─────────────────────────────────
    instance_egress_enabled: bool = Field(default=False, alias="INSTANCE_EGRESS_ENABLED")
    default_project_egress_enabled: bool = Field(
        default=False, alias="DEFAULT_PROJECT_EGRESS_ENABLED"
    )

    # ─── task → provider/model 默认路由 ──────────────────────────
    task_value_extraction_provider: str = Field(
        default="minimax", alias="TASK_VALUE_EXTRACTION_PROVIDER"
    )
    task_value_extraction_model: str = Field(
        default="abab6.5s-chat", alias="TASK_VALUE_EXTRACTION_MODEL"
    )

    task_weekly_report_provider: str = Field(
        default="anthropic", alias="TASK_WEEKLY_REPORT_PROVIDER"
    )
    task_weekly_report_model: str = Field(
        default="claude-sonnet-4-5-20250929", alias="TASK_WEEKLY_REPORT_MODEL"
    )

    task_tech_design_provider: str = Field(
        default="anthropic", alias="TASK_TECH_DESIGN_PROVIDER"
    )
    task_tech_design_model: str = Field(
        default="claude-sonnet-4-5-20250929", alias="TASK_TECH_DESIGN_MODEL"
    )

    task_adr_provider: str = Field(default="anthropic", alias="TASK_ADR_PROVIDER")
    task_adr_model: str = Field(
        default="claude-sonnet-4-5-20250929", alias="TASK_ADR_MODEL"
    )

    task_incident_provider: str = Field(default="anthropic", alias="TASK_INCIDENT_PROVIDER")
    task_incident_model: str = Field(
        default="claude-sonnet-4-5-20250929", alias="TASK_INCIDENT_MODEL"
    )

    # v0.2 · book 长文档生成 (上下文长 → 用 Sonnet 高级模型)
    task_book_provider: str = Field(default="anthropic", alias="TASK_BOOK_PROVIDER")
    task_book_model: str = Field(
        default="claude-sonnet-4-5-20250929", alias="TASK_BOOK_MODEL"
    )

    # v0.2 · agent_skill 蒸馏 (输出短 + 高结构, 用 Sonnet 保质量)
    task_agent_skill_provider: str = Field(
        default="anthropic", alias="TASK_AGENT_SKILL_PROVIDER"
    )
    task_agent_skill_model: str = Field(
        default="claude-sonnet-4-5-20250929", alias="TASK_AGENT_SKILL_MODEL"
    )

    task_redaction_llm_provider: str = Field(
        default="minimax", alias="TASK_REDACTION_LLM_PROVIDER"
    )
    task_redaction_llm_model: str = Field(
        default="abab6.5s-chat", alias="TASK_REDACTION_LLM_MODEL"
    )

    # ─── v0.3 · IM 集成 (T16) ────────────────────────────────────
    # Fernet 主密钥 (base64-encoded 32 bytes). 用于加密 IM OAuth tokens.
    # MVP 单实例; 生产换 KMS (AWS/GCP/Azure KMS) 透明接管.
    # 生成方法: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    im_encryption_key: str | None = Field(
        default=None, alias="IM_ENCRYPTION_KEY"
    )

    # ─── v0.3.1 · SignalGate R10 (本地分类器) ───────────────
    # Ollama 本地小模型路径. 默认 qwen2.5:3b; 实测 4-8 token/s 单条 ~200ms.
    # 设为空字符串 → 关闭 LLM 兜底, 退回纯启发式 (老 MVP 行为).
    signal_gate_llm_model: str = Field(
        default="qwen2.5:3b", alias="SIGNAL_GATE_LLM_MODEL"
    )
    # SignalGate is_signal 判定阈值 (0-1, score >= 此值视为 signal).
    signal_gate_threshold: float = Field(
        default=0.5, alias="SIGNAL_GATE_THRESHOLD", ge=0.0, le=1.0
    )

    # ─── v0.3 · 飞书集成 (T18+T19) ────────────────────────────
    # 飞书开放平台 app 凭据. 生产前从飞书后台获取并通过 env 配置.
    # https://open.feishu.cn/app/{app_id}/baseinfo
    feishu_app_id: str | None = Field(default=None, alias="FEISHU_APP_ID")
    feishu_app_secret: str | None = Field(default=None, alias="FEISHU_APP_SECRET")
    feishu_encrypt_key: str | None = Field(default=None, alias="FEISHU_ENCRYPT_KEY")
    feishu_verification_token: str | None = Field(
        default=None, alias="FEISHU_VERIFICATION_TOKEN"
    )
    # 飞书 OAuth callback 完整 URL (TokenKnows 自己的 endpoint)
    feishu_oauth_redirect_uri: str = Field(
        default="http://localhost:8001/api/v1/webhooks/feishu/auth-callback",
        alias="FEISHU_OAUTH_REDIRECT_URI",
    )
    # 飞书 API base. 国际版用 https://open.larksuite.com
    feishu_api_base: str = Field(
        default="https://open.feishu.cn",
        alias="FEISHU_API_BASE",
    )

    # ─── v0.5.0 · @ 机器人按需触发 (T46) ─────────────────────────
    # bot 在飞书的 open_id (用于 normalize_im_mention 判断 "@bot");
    # 启动时由 OAuth/启动脚本写入; 未配置时 mention dispatcher 静默跳过 (fail-soft).
    feishu_bot_open_id: str | None = Field(
        default=None, alias="FEISHU_BOT_OPEN_ID",
    )
    dingtalk_bot_userid: str | None = Field(
        default=None, alias="DINGTALK_BOT_USERID",
    )
    wework_bot_userid: str | None = Field(
        default=None, alias="WEWORK_BOT_USERID",
    )

    # T47 · 群内 thread 回执的 link 拼接基准 (Proposal v0.5 OD-5)
    # e.g. 'https://tokenknows.acme.com' → 拼成 /projects/:pid/auto-triggers/executions/:eid
    # 未设时回执只含纯文本不含 link
    public_base_url: str | None = Field(
        default=None, alias="PUBLIC_BASE_URL",
    )

    # ─── 服务运行 ────────────────────────────────────────────────
    api_host: str = Field(default="0.0.0.0", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    environment: Literal["local", "dev", "staging", "production"] = Field(
        default="local", alias="ENVIRONMENT"
    )

    # ─── 出域审计 ────────────────────────────────────────────────
    egress_log_path: str = Field(default="./data/egress.sqlite", alias="EGRESS_LOG_PATH")

    # ─── Validator: 空字符串视为未设置 ──────────────────────────
    # 防止 shell env 注入空 key (如 Claude Code CLI 注入的 ANTHROPIC_API_KEY="")
    # 覆盖 .env.local 里的真实值. pydantic-settings 默认 process env > env_file.
    @field_validator(
        "anthropic_api_key",
        "openai_api_key",
        "minimax_api_key",
        "ollama_api_key",
        mode="before",
    )
    @classmethod
    def _empty_string_to_none(cls, v: object) -> object:
        if isinstance(v, str) and v.strip() == "":
            return None
        return v

    # ─── 派生属性 ────────────────────────────────────────────────
    @property
    def is_local(self) -> bool:
        return self.environment == "local"

    def task_provider(self, task: str) -> str:
        """根据 task 名查询 provider (用于 LLMRouter)."""
        mapping = {
            "value_extraction": self.task_value_extraction_provider,
            "weekly_report": self.task_weekly_report_provider,
            "tech_design": self.task_tech_design_provider,
            "adr": self.task_adr_provider,
            "incident": self.task_incident_provider,
            "book": self.task_book_provider,
            "agent_skill": self.task_agent_skill_provider,
            "redaction_llm": self.task_redaction_llm_provider,
        }
        if task not in mapping:
            raise ValueError(f"Unknown task: {task}")
        return mapping[task]

    def task_model(self, task: str) -> str:
        """根据 task 名查询默认 model."""
        mapping = {
            "value_extraction": self.task_value_extraction_model,
            "weekly_report": self.task_weekly_report_model,
            "tech_design": self.task_tech_design_model,
            "adr": self.task_adr_model,
            "incident": self.task_incident_model,
            "book": self.task_book_model,
            "agent_skill": self.task_agent_skill_model,
            "redaction_llm": self.task_redaction_llm_model,
        }
        if task not in mapping:
            raise ValueError(f"Unknown task: {task}")
        return mapping[task]

    def provider_key(self, provider: str) -> str | None:
        """根据 provider 查询对应的 API key.

        Ollama 不需要真 key (本地 daemon 不鉴权), 但为了通过 call_llm 的
        "key 未配置" 短路, 返回固定占位 "ollama-local".
        """
        return {
            "anthropic": self.anthropic_api_key,
            "openai": self.openai_api_key,
            "minimax": self.minimax_api_key,
            "ollama": self.ollama_api_key or "ollama-local",
        }.get(provider)


_settings: Settings | None = None


def get_settings() -> Settings:
    """单例 lazy load."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
