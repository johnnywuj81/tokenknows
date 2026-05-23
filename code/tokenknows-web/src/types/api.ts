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

// 5 个采集器的实时健康度 (T03 工作台数据源卡)
export type DatasourceHealth = 'active' | 'stale' | 'cold' | 'inactive'

export interface DatasourceHealthItem {
  source_type: DatasourceType   // 5 个已知类型
  event_count: number           // 窗口内 (默认 30d)
  total_events: number          // 历史全量
  last_seen_at: string | null   // MAX(occurred_at)
  last_ingested_at: string | null  // MAX(ingested_at)
  health: DatasourceHealth
}

export interface DatasourceHealthResponse {
  items: DatasourceHealthItem[]
  window_days: number
  total_active: number
  total_events_window: number
  total_events_all: number
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

export type AssetType =
  | 'weekly_report'
  | 'tech_design'
  | 'adr'
  | 'incident'
  | 'book'           // v0.2: 书籍类长文档 (10万字+ 嵌套大纲)
  | 'agent_skill'    // v0.2: 蒸馏出的专家技能 (Anthropic SKILL.md 风格)

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
  /** v0.2 · book 跨章节连贯度 (相邻章 cosine 均值); 其它类型为 null */
  consistency_score?: number | null
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
  /** v0.4 · 自动触发标记 (null = 手动生成; 非空 = 由规则自动生成) */
  trigger_meta?: AssetTriggerMeta | null
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

export interface AppliedSkill {
  /** v0.2: 章节生成时被注入的 skill 记录 */
  skill_id: string
  version: number
  applied_at: string
  cosine_similarity?: number
}

export interface Chapter {
  id: string
  asset_id: string
  asset_version: number
  order_index: number
  parent_id?: string | null    // v0.2: book 嵌套大纲 (NULL=顶层卷)
  depth?: number               // v0.2: 0=卷, 1=章, 2=节 (4 类现有都是 0)
  title: string
  content: string                              // markdown
  layout: Record<string, unknown>              // 段落级版式 (callout / 警告 / 引用)
  generated_by: ChapterGeneratedBy | null
  regeneration_history: Array<{
    at: string
    user_id: string
    instruction: string
    model: string
    previous_content?: string  // P3 · 重生成前的内容快照, 用于 diff 视图
  }>
  applied_skills?: AppliedSkill[]   // v0.2: 该章节生成时注入的 skill 列表
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
  | 'public_link'
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

// ────────────────────────────────────────────────────────────────────
// v0.2 · Skill (蒸馏出的 Agent 专家技能)
// ────────────────────────────────────────────────────────────────────

export type SkillStatus =
  | 'draft'
  | 'active'
  | 'deprecated'
  | 'locked'
  // v0.5.1 · Q5 contributor 个人同意 (T48)
  | 'pending_contributor_consent'
  | 'rejected_by_contributor'
  | 'expired_no_consent'

/** v0.5.1 · 单条 contributor consent 记录 */
export interface ConsentRecord {
  user_id: string
  signed_at: string
  channel: 'im_dm' | 'web'
  note: string | null
}

/** v0.6.0 · Reviewer 审批阶段 (T56) */
export type ReviewState =
  | 'not_submitted'
  | 'pending_review'
  | 'approved'
  | 'rejected'

/** v0.6.0 · 单条审批记录 */
export interface ReviewRecord {
  reviewer_id: string
  action: 'submit' | 'approve' | 'reject'
  timestamp: string
  note: string | null
}

export interface SkillMetrics {
  /** 被注入到 prompt 的累计次数 */
  usage_count: number
  /** 应用后用户 approve 的 chapter 数 */
  acceptance_count: number
  /** 应用后用户 reject 的 chapter 数 / 大 diff 重生成 */
  rejection_count: number
  /** acceptance / (acceptance + rejection), 0-1 */
  avg_acceptance_rate: number
  /** 综合分 (cosine × acceptance × recency × usage_confidence), 0-1 */
  trust_score: number
}

export interface SkillDistillSource {
  chapter_id: string
  asset_id: string
  asset_version: number
  quoted_at: string
}

export interface Skill {
  id: string
  project_id: string
  name: string
  version: number
  /** Anthropic SKILL.md 全文 (YAML frontmatter + 正文) */
  skill_md: string
  embedding: number[] | null
  metrics: SkillMetrics
  distilled_from: SkillDistillSource[]
  distilled_at: string
  last_used_at: string | null
  locked: boolean
  status: SkillStatus
  /** evolve_skill_v2 时记录上一代 skill id */
  parent_skill_id: string | null
  // v0.5.1 · Q5 consent (T48)
  contributors: string[]
  consent_required_from: string[]
  consent_signed_by: ConsentRecord[]
  consent_rejected_by: ConsentRecord | null
  consent_expires_at: string | null
  // v0.6.0 · Reviewer 审批 (T56)
  review_state: ReviewState
  review_history: ReviewRecord[]
  last_reviewer_id: string | null
  last_reviewed_at: string | null
  created_at: string
  updated_at: string
}

// v0.6.0 · Review endpoints (T57)
export interface SkillSubmitForReviewRequest {
  user_id: string
  note?: string
}

export interface SkillReviewApproveRequest {
  reviewer_id: string
  note?: string
}

export interface SkillReviewRejectRequest {
  reviewer_id: string
  reason: string
}

export interface SkillReviewActionResponse {
  skill_id: string
  status: SkillStatus
  review_state: ReviewState
  last_action: 'submit' | 'approve' | 'reject'
  last_reviewer_id: string | null
  last_reviewed_at: string | null
}

// v0.5.1 · Consent endpoints (T50)
export interface ConsentSignRequest {
  user_id: string
  channel?: 'im_dm' | 'web'
  note?: string
}

export interface ConsentSignResponse {
  skill_id: string
  current_status: SkillStatus
  signed_count: number
  required_count: number
  all_signed: boolean
}

export interface ConsentRejectRequest {
  user_id: string
  channel?: 'im_dm' | 'web'
  reason: string
}

export interface ConsentRejectResponse {
  skill_id: string
  current_status: SkillStatus
  rejected_by: string
}

export type NotificationType =
  | 'consent_request'
  | 'consent_signed'
  | 'consent_rejected'
  | 'consent_expired'
  // v0.6.0 review
  | 'skill_review_request'
  | 'skill_review_approved'
  | 'skill_review_rejected'

export interface WebNotification {
  id: string
  user_id: string
  type: NotificationType
  title: string
  body: string
  link_url: string
  read: boolean
  created_at: string
  related_skill_id: string | null
}

export interface WebNotificationListResponse {
  items: WebNotification[]
  unread_count: number
}

export interface SkillDistillRequest {
  source_chapter_ids: string[]
  name_hint?: string
}

export interface SkillUpdateRequest {
  skill_md?: string
  name?: string
  locked?: boolean
  status?: SkillStatus
}

// ────────────────────────────────────────────────────────────────────
// v0.3 · IM 集成 (Lark / 钉钉 / 企微 / 邮件)
// ────────────────────────────────────────────────────────────────────

export type IMPlatform = 'feishu' | 'dingtalk' | 'wework' | 'email'

export type IMConnectionStatus = 'pending' | 'active' | 'revoked'

export type IMSourceMode = 'assistant' | 'archive'

export interface IMConnection {
  id: string
  project_id: string
  platform: IMPlatform
  tenant_name: string | null
  auth_token_enc: string | null
  refresh_token_enc: string | null
  token_expires_at: string | null
  consent_signed_by: string | null
  consent_user_id: string | null
  consent_signed_at: string | null
  revoked_at: string | null
  status: IMConnectionStatus
  last_synced_at: string | null
  created_at: string
  updated_at: string
}

export interface IMChat {
  /** 飞书 chat_id / 钉钉 conversationId / 企微 chatid */
  chat_id?: string
  name?: string
  chat_type?: string  // group | p2p | thread
  description?: string
  [key: string]: unknown
}

export interface IMContributor {
  user_id: string
  name?: string | null
  messages: number
}

export interface IMChatStats {
  chat_id: string
  message_count: number
  signal_count: number
  signal_rate: number
  top_contributors: IMContributor[]
}

export interface CreateIMConnectionRequest {
  platform: IMPlatform
  consent_signed_by?: string
  consent_user_id?: string
}

export interface CreateIMConnectionResponse {
  connection: IMConnection
  authorize_url: string
}

export interface DistillIMRequest {
  chat_id: string
  source_mode?: IMSourceMode
}

export interface DistillIMResponse {
  segments_persisted: number
  segment_ids: string[]
}

// ────────────────────────────────────────────────────────────────────
// v0.4 · Auto-Trigger (T26-T35)
// 对齐 backend app/schemas/auto_trigger.py
// ────────────────────────────────────────────────────────────────────

export type TriggerMode = 'cron' | 'event' | 'threshold' | 'mention'

export type ExecutionStatus =
  | 'scheduled'
  | 'fired'
  | 'canceled'
  | 'skipped'
  | 'failed'
  | 'expired'

export type SkipReason =
  | 'cooldown'
  | 'daily_cap_reached'
  | 'extra_condition_failed'
  | 'rule_disabled'
  | 'lower_priority'
  | 'low_confidence'
  | 'quota_exceeded'
  | 'canceled_by_user'

export interface EventMatch {
  event_type: string
  label_any?: string[]
  file_glob?: string[]
  title_contains?: string[]
}

export interface ThresholdSpec {
  metric: string
  comparator: '>=' | '<=' | '==' | '!=' | '>' | '<'
  value: number
  and_not_exists_asset_of_type?: string | null
}

export interface ExtraCondition {
  metric: string
  comparator: '>=' | '<=' | '==' | '!=' | '>' | '<'
  value: number
}

export interface TriggerSignal {
  type: string
  event_id?: string | null
  summary: string
  payload?: Record<string, unknown>
}

export interface TriggerEvaluation {
  matched: boolean
  confidence: number
  dropped_rules?: string[]
  extra_condition_result?: boolean | null
  notes?: string | null
}

export interface TriggerRule {
  id: string
  project_id: string | null
  name: string
  description: string
  priority: number
  mode: TriggerMode
  asset_type: AssetType
  enabled: boolean
  cooldown_seconds: number
  daily_cap: number
  cron_expr?: string | null
  event_match?: EventMatch | null
  threshold_spec?: ThresholdSpec | null
  extra_condition?: ExtraCondition | null
  created_by: string
  created_at: string
  updated_at: string
}

export interface TriggerExecution {
  id: string
  rule_id: string
  project_id: string
  status: ExecutionStatus
  fire_at: string
  fired_at?: string | null
  signal: TriggerSignal
  evaluation?: TriggerEvaluation | null
  asset_id?: string | null
  skip_reason?: SkipReason | null
  error_message?: string | null
  user_canceled: boolean
  user_flagged_false_positive: boolean
  created_at: string
}

export interface AssetTriggerMeta {
  trigger_mode: TriggerMode
  rule_id: string
  rule_name: string
  signal: TriggerSignal
  confidence: number
  fired_at: string
  trigger_execution_id?: string | null
}

// v0.4.4 T44 · 月配额仪表盘
export interface QuotaResponse {
  project_id: string
  year_month: string
  monthly_token_limit: number
  daily_auto_gen_limit: number
  tokens_used: number
  auto_gen_count: number
  is_throttled: boolean
  usage_ratio: number
  status: 'healthy' | 'warning' | 'throttled'
}
