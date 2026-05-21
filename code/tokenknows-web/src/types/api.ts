/**
 * API DTOs · 镜像后端 schemas/api/* 与 domain ORM。
 *
 * 来源:
 *   - TDD §5 (数据库 schema)
 *   - TDD §6.1 (API 端点)
 *   - PRD §7 (Event / Asset / Chapter / Evidence 模型)
 *
 * 命名规范:
 *   - 实体名直接复用后端 (User / Project / Event / Asset / Chapter / Evidence)
 *   - 后端时间字段 timestamptz → 前端 string (ISO 8601)
 *   - 后端 JSONB → 前端嵌套 interface 或 Record<string, unknown>
 *   - 联合类型用 string literal union (而非 enum,符合 ~/.claude/rules/typescript/coding-style.md)
 */

// ────────────────────────────────────────────────────────────────────
// 通用
// ────────────────────────────────────────────────────────────────────

export interface ApiResponse<T> {
  data: T
}

export interface PaginatedResponse<T> {
  data: T[]
  meta: {
    total: number
    cursor?: string
    has_more: boolean
  }
}

export type ErrorCode =
  | 'BAD_REQUEST'
  | 'UNAUTHORIZED'
  | 'FORBIDDEN'
  | 'NOT_FOUND'
  | 'CONFLICT'
  | 'VALIDATION_ERROR'
  | 'RATE_LIMITED'
  | 'SERVER_ERROR'
  | 'NETWORK_ERROR'
  | 'EGRESS_DENIED'      // 三层出域门禁拒绝
  | 'LICENSE_EXPIRED'    // 凭证过期,进入只读模式

export interface ApiError {
  code: ErrorCode
  message: string
  detail?: unknown
  status: number
}

// ────────────────────────────────────────────────────────────────────
// 用户 / 鉴权
// ────────────────────────────────────────────────────────────────────

export interface User {
  id: string
  email: string
  display_name: string
  is_instance_admin: boolean
  email_verified_at: string | null
  created_at: string
  updated_at: string
}

export interface LoginRequest {
  email: string
  password: string
}

export interface LoginResponse {
  access_token: string
  refresh_token: string
  user: User
}

export interface RegisterRequest {
  email: string
  password: string
  display_name: string
}

// ────────────────────────────────────────────────────────────────────
// 项目
// ────────────────────────────────────────────────────────────────────

export type ProjectRole = 'owner' | 'editor' | 'reviewer' | 'viewer'

export interface BrandTheme {
  primary?: string
  bg?: string
  logo_url?: string
}

export interface Project {
  id: string
  name: string
  description: string | null
  owner_id: string
  llm_egress_enabled: boolean
  task_egress_config: Record<string, boolean>
  custom_redaction_terms: RedactionTerm[]
  brand_theme: BrandTheme
  created_at: string
  updated_at: string

  // 衍生字段 (响应附带)
  role?: ProjectRole
  health?: 'healthy' | 'degraded' | 'down'
  stats?: ProjectStats
}

export interface ProjectStats {
  events_this_week: number
  assets_pending_review: number
  datasources_total: number
  datasources_healthy: number
}

export interface ProjectMember {
  project_id: string
  user_id: string
  role: ProjectRole
  added_at: string
  user?: Pick<User, 'id' | 'email' | 'display_name'>
}

// ────────────────────────────────────────────────────────────────────
// 数据源
// ────────────────────────────────────────────────────────────────────

export type DatasourceType =
  | 'claude_code'
  | 'cursor'
  | 'vscode'
  | 'github'
  | 'local_file'

export interface Datasource {
  id: string
  project_id: string
  type: DatasourceType
  name: string
  config: Record<string, unknown>    // 不同类型字段不同 (e.g. github.repo_url)
  connection_token?: string          // 仅插件类返回
  health: 'healthy' | 'degraded' | 'down'
  last_synced_at: string | null
  created_at: string
}

// ────────────────────────────────────────────────────────────────────
// 研发事件
// ────────────────────────────────────────────────────────────────────

export type EventSourceType = DatasourceType | 'manual'

export type EventType =
  | 'ai_conversation_turn'
  | 'tool_call'
  | 'code_change'
  | 'pr_event'
  | 'issue_event'
  | 'commit'
  | 'local_document'
  | 'manual_note'

export interface Event {
  id: string
  project_id: string
  source_type: EventSourceType
  source_ref: string
  external_id: string
  version: number
  event_type: EventType
  occurred_at: string
  ingested_at: string
  author: { name: string; email?: string; external_id?: string } | null
  title: string | null
  content: string
  payload: Record<string, unknown>
  redaction_state: 'raw' | 'screened' | 'confirmed' | 'exported'
  trust_score: number | null
  tags: string[]
  content_hash: string
  is_private?: boolean   // PRD §5.4 D2 异常 - 敏感来源遮蔽
}

export interface ValueSegment {
  id: string
  event_id: string
  span_start: number
  span_end: number
  category:
    | 'architecture_decision'
    | 'bug_rca'
    | 'prompt_pattern'
    | 'tech_design'
    | 'performance'
    | 'security'
    | 'ux_feedback'
    | 'other'
  trust_score: number
  category_confidence: number
  manual_trust_override: 1 | -1 | null
}

// ────────────────────────────────────────────────────────────────────
// Asset / Chapter / Evidence / PublishRecord
// ────────────────────────────────────────────────────────────────────

export type AssetType = 'weekly_report' | 'tech_design' | 'adr' | 'incident'

export type AssetStatus =
  | 'generating'   // 后端生成中(MVP UI 状态;mock 5s 后转 draft)
  | 'draft'
  | 'in_review'
  | 'approved'
  | 'published'
  | 'archived'

export interface AssetMetrics {
  coverage: number          // 覆盖度 0-1
  citation_density: number  // 引用密度 0-1
  slop_score: number        // 空话比例 0-1 (越低越好)
  similarity: number        // 与历史相似度 0-1
}

export interface Asset {
  id: string
  project_id: string
  type: AssetType
  title: string
  status: AssetStatus
  current_version: number
  template_id: string | null
  created_by: string
  approval_state: 'pending' | 'approved' | 'rejected'
  redaction_state: 'any_unresolved' | 'all_confirmed'
  metrics: AssetMetrics | null
  created_at: string
  updated_at: string
}

export type RedactedSpanType =
  | 'CUSTOMER'
  | 'API_KEY'
  | 'INTERNAL_SYSTEM'
  | 'EMAIL'
  | 'IP'
  | string   // CUSTOM_<name>

export interface RedactedSpan {
  span_start: number
  span_end: number
  type: RedactedSpanType
  status: 'pending' | 'confirmed' | 'overridden' | 'exempted'
  original_hash: string       // 原文不存,仅 hash
  applied_text: string        // 替换占位符
  reason?: string             // 豁免理由
}

export interface ChapterGeneratedBy {
  model: string
  provider: 'anthropic' | 'openai' | 'ollama' | 'vllm'
  latency_ms: number
  prompt_tokens: number
  completion_tokens: number
}

export interface Chapter {
  id: string
  asset_id: string
  asset_version: number
  order_index: number
  title: string
  content: string                              // markdown
  layout: Record<string, unknown>              // 段落级版式 (callout / 警告 / 引用)
  generated_by: ChapterGeneratedBy | null
  regeneration_history: Array<{
    at: string
    user_id: string
    instruction: string
    model: string
  }>
  approval_state: 'pending' | 'approved' | 'rejected'
  redacted_spans: RedactedSpan[]
}

export interface EvidencePreview {
  event_id: string
  title: string | null
  source_type: string
  source_ref: string
  author_name: string | null
  author_email: string | null
  occurred_at: string
  content_excerpt: string
  external_url: string | null
}

export interface Evidence {
  id: string
  chapter_id: string
  event_id: string
  event_version: number
  span_start: number
  span_end: number
  citation_text: string
  manually_added: boolean
  stale: boolean
  trust_score?: number | null
  citation_strength?: number | null
  event_preview: EvidencePreview
}

export type PublishDestination =
  | 'internal'
  | 'feishu'
  | 'slack'
  | 'notion'
  | 'export_pdf'
  | 'export_docx'
  | 'export_md'

export type PublishMode = 'full' | 'summary_with_backlink'

export interface PublishRecord {
  id: string
  asset_id: string
  asset_version: number
  destination: PublishDestination
  destination_ref: string | null
  publish_mode: PublishMode
  status: 'pending' | 'success' | 'failed' | 'revoked'
  url: string | null
  published_at: string
  published_by: string
  visibility?: 'team' | 'public' | null    // T11 公开链接时
  error?: string | null                    // status=failed 时
}

// ────────────────────────────────────────────────────────────────────
// 脱敏
// ────────────────────────────────────────────────────────────────────

export interface RedactionTerm {
  id: string
  pattern: string      // 正则
  type: string         // CUSTOMER / CUSTOM_xxx
  replacement: string  // 默认替换
  priority: number     // 自定义 > 内置
}

export interface RedactionScanJob {
  job_id: string
  asset_id?: string    // 后端 T10 返回
  status: 'pending' | 'running' | 'done' | 'failed'
  progress: number     // 0-1
  items: RedactionItem[]
}

export interface RedactionItem {
  id: string
  chapter_id: string
  span_start: number
  span_end: number
  type: RedactedSpanType
  matched_text: string
  rule_source: 'rule' | 'llm' | 'custom'
  suggested_replacement: string
  status: 'pending' | 'confirmed' | 'overridden' | 'exempted'
  context_before?: string
  context_after?: string
  reason?: string | null   // T10 豁免理由
}

// ────────────────────────────────────────────────────────────────────
// LLM 配置
// ────────────────────────────────────────────────────────────────────

export interface LlmModel {
  provider: 'anthropic' | 'openai' | 'ollama' | 'vllm'
  model: string         // e.g. "claude-sonnet-4-6" / "qwen2.5-32b"
  display_name: string
  is_cloud: boolean
  capabilities: Array<'long_context' | 'json_mode' | 'tool_use' | 'streaming'>
  is_available: boolean // 后端根据出域开关 + 健康判断
}

export interface LlmConfig {
  instance_egress_enabled: boolean  // read-only, 只 instance_admin 可改 (T15)
  project_egress_enabled: boolean
  task_egress_config: Record<string, boolean>
  allowed_models: string[]          // model id 列表
  audit_level: 'off' | 'summary' | 'full'
}

export interface EgressLogEntry {
  id: string
  ts: string
  project_id: string
  user_id: string
  task: string
  provider: string
  model: string
  request_size_bytes: number
  response_size_bytes: number
  prompt_tokens: number
  completion_tokens: number
  latency_ms: number
  cost_estimate: number
  hash_of_request: string
  fallback_used: boolean
}

// ────────────────────────────────────────────────────────────────────
// 审计
// ────────────────────────────────────────────────────────────────────

export interface AuditLogEntry {
  id: string
  ts: string
  user_id: string | null
  project_id: string | null
  action: string                    // e.g. "project.update" / "asset.publish"
  resource_type: string | null
  resource_id: string | null
  diff: Record<string, unknown>
  ip: string | null
  user_agent: string | null
}

// ────────────────────────────────────────────────────────────────────
// 工作台 todos / 实例统计 (T03 / T15)
// ────────────────────────────────────────────────────────────────────

export interface TodoItem {
  id: string
  type: 'pending_review' | 'pending_generate' | 'pending_publish' | 'pending_redaction'
  title: string
  asset_id?: string
  due_at: string | null
  created_at: string
}

export interface InstanceStats {
  users_total: number
  projects_total: number
  assets_this_month: number
  llm_tokens_this_month: number
  storage_used_bytes: number
  storage_limit_bytes: number
}
