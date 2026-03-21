# Feature Specification: FastGPT + Dify Integration Project

**Feature Branch**: `main`  
**Created**: 2026-03-19  
**Status**: Draft  
**Input**: User description: "/fastGpt dify 结合的项目"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Unified Chat Entry (Priority: P1)

As an operations engineer, I can send one chat request to a unified endpoint and let the system decide to execute through FastGPT or Dify based on routing rules.

**Why this priority**: This is the core product value of "combined project" and enables immediate integration validation.

**Independent Test**: Send a request with route conditions and verify it reaches the selected provider and returns normalized output.

**Mode Selection**: Within the unified chat endpoint, the system MUST automatically select one execution mode among `agent` / `react` / `workflow` using LangGraph based on the user input.

**Acceptance Scenarios**:

1. **Given** a route rule mapping tenant A to FastGPT, **When** tenant A sends a chat request, **Then** the request is executed by FastGPT and returns unified response fields.
2. **Given** a route rule mapping tenant B to Dify, **When** tenant B sends a chat request, **Then** the request is executed by Dify and returns unified response fields.

---

### User Story 2 - Workflow Trigger via Dify (Priority: P2)

As a product owner, I can trigger a Dify workflow through the same integration service for tasks that require workflow orchestration.

**Why this priority**: Workflow support extends beyond basic chat and unlocks process automation.

**Independent Test**: Call workflow API with input variables and verify workflow status and output mapping.

**Acceptance Scenarios**:

1. **Given** a configured Dify workflow ID, **When** a workflow request is submitted, **Then** the system returns normalized status and result payload.

---

### User Story 3 - Provider Fallback and Monitoring (Priority: P3)

As an SRE, I can configure fallback strategy and view trace logs to ensure service continuity when one provider fails.

**Why this priority**: Improves reliability and operational confidence for production rollout.

**Independent Test**: Simulate FastGPT failure, verify automatic fallback to Dify, and confirm trace correlation in logs.

**Acceptance Scenarios**:

1. **Given** FastGPT is unavailable and fallback is enabled, **When** a chat request is sent to FastGPT route, **Then** the system falls back to Dify and records fallback reason.

---

### Edge Cases

- What happens when both FastGPT and Dify time out?
- How does system handle incompatible response schemas from provider upgrades?
- What happens when workflow input variables are missing required keys?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST expose a unified API for chat and workflow requests.
- **FR-002**: System MUST support rule-based routing between FastGPT and Dify.
- **FR-003**: System MUST normalize provider outputs into a consistent response schema.
- **FR-004**: System MUST support configurable fallback strategy per route.
- **FR-005**: System MUST emit structured logs with correlation IDs for all provider interactions.
- **FR-006**: System MUST protect provider credentials via environment-based secret configuration.
- **FR-007**: System MUST provide health-check endpoints for integration readiness.
- **FR-010**: System MUST use LangGraph to auto-select `agent` / `react` / `workflow` execution modes inside the unified chat endpoint based on user input.
- **FR-008**: System MUST use Python + FastAPI as the service runtime for this feature.
- **FR-009**: System SHOULD prefer open-source standard project layout and reusable libraries over custom framework code.

### Key Entities *(include if feature involves data)*

- **IntegrationRoute**: Routing rule that maps tenant/request characteristics to a target provider and fallback policy.
- **UnifiedRequest**: Standardized incoming payload for chat or workflow execution.
- **UnifiedResponse**: Normalized response model returned to clients.
- **ExecutionTrace**: Audit record of provider calls, retries, fallback events, and latency.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 95% of standard chat requests return normalized response within 2 seconds under nominal load.
- **SC-002**: Fallback succeeds for at least 99% of single-provider failures in integration tests.
- **SC-003**: 100% of requests include traceable correlation IDs across logs.
- **SC-004**: Route configuration changes become effective without service restart.

## OTIE 对齐改造清单 v1（中文）

目标：把当前 `aiChatFLow` 从“功能原型”升级为“可治理、可审计、可扩展的 OTIE Runtime 形态”。

### 一、改造范围与阶段

- 阶段 1（2-4 天）：
  - 统一协议：`IntentEnvelope`、`ExecutionPlan`、`ExecutionTrace`
  - 计划输出结构化（不再仅 `string[]`）
  - 执行器按 step 执行，输出 step 级事件流
- 阶段 2（3-5 天）：
  - `Constitution Layer`（allow/deny/approval/schema）
  - Tool/Skill manifest 与风险分级
  - 策略决策日志化
- 阶段 3（2-3 天）：
  - Trace 持久化与查询接口
  - KPI 统计（计划成功率、工具失败率、schema 合规率）

### 二、目标架构（OTIE 映射）

- Input Gateway -> `IntentEnvelope`
- Planner -> `ExecutionPlan`
- Constitution Layer -> `PolicyDecision[]`
- Executor -> `StepResult[]`
- Aggregator -> `FinalResponse`
- Audit -> `ExecutionTrace`

### 三、后端数据模型改造

- 新增 `IntentEnvelope`：
  - `intent`
  - `user_input`
  - `constraints`（如 `safety_level`, `max_steps`）
  - `context`（`tenant_id`, `request_id`, `strategy`）
- 新增 `ExecutionPlan`：
  - `plan_id`
  - `mode`
  - `steps: Step[]`
  - `metadata`
- 新增 `Step`：
  - `id`, `type`, `action`
  - `input`, `depends_on`
  - `agent?`, `skills?`, `risk_level?`
- 新增 `ExecutionTrace`：
  - `trace_id`, `request_id`, `plan_id`
  - `step_events[]`
  - `policy_decisions[]`
  - `final_status`

兼容策略：
- 过渡期保留 `plan: string[]`
- 新增 `executionPlan`（前端优先消费）

### 四、API 改造清单

- `POST /v1/unified/plan`
  - 返回 `intentEnvelope`
  - 返回 `executionPlan`
  - 保留 `plan` 兼容字段
  - 返回 `policyHints`
- `POST /v1/unified/execute/stream`
  - 接收 `executionPlan` 或 `planId`
  - 按 step 执行（不是仅拼接文本）
  - SSE 事件统一为：
    - `step_start`
    - `policy_check`
    - `approval_required`
    - `tool_start`
    - `tool_result`
    - `step_done`
    - `trace_summary`
    - `done`
- 新增审计查询接口：
  - `GET /v1/traces/{traceId}`
  - `GET /v1/traces?requestId=...`
  - `GET /v1/metrics/kpi?from=...&to=...`

### 五、Constitution Layer（治理层）

- 策略对象：
  - `allow_tools`
  - `deny_tools`
  - `require_approval`
  - `output_schema`
  - `max_tool_calls`
- 执行前强制 `policy_check(step)`：
  - deny -> 拒绝并写 trace
  - require approval -> 进入审批态
  - output schema fail -> 标记违规并记录
- 建议文件：
  - `app/services/policy_engine.py`
  - `app/services/schema_validator.py`

### 六、Tool/Skill 注册与风险分级

- 统一 manifest：
  - `tool_id`
  - `input_schema`
  - `output_schema`
  - `required_permissions`
  - `risk_level`
  - `source`（local/clawhub/custom）
- ClawHub 注册后写入 manifest，默认风险至少 `medium`，需人工确认启用。

### 七、前端改造清单

- 待确认面板改为 `executionPlan.steps[]` 渲染：
  - `type/action`
  - `agent/skills`
  - `risk_level`
  - `policy result`
  - `approval` 状态
- 执行流 UI 消费 step 级 SSE 事件
- 历史记录增加：
  - `executionPlan`
  - `traceId`
  - `policyDecisions`

### 八、审计与观测（最低可用）

- Trace 持久化：
  - step start/end
  - status/error
  - input/output 摘要（或 hash）
- KPI 口径：
  - 计划成功率 = 成功计划 / 总计划
  - 工具失败率 = 失败工具调用 / 总工具调用
  - Schema 合规率 = 合规输出 / 总输出

### 九、当前代码优先改动点

- `app/api/routes/unified.py`：
  - `plan_unified` 返回 `executionPlan`
  - `execute_unified_stream` 真正消费 step 配置
- `app/orchestrator/graph.py`：
  - Planner 输出结构化 steps
- `app/services/capability_service.py`：
  - 增加 manifest 与风险字段
- `chatui-taiwild/src/app/page.tsx`：
  - PendingPlan 升级为 plan schema 驱动渲染

### 十、验收标准（v1 Done）

- 可返回并展示结构化 `ExecutionPlan`
- 执行时按 step 执行并输出 step 级事件
- 至少 3 条 Constitution 规则生效（allow/deny/approval）
- 任一次执行可查询完整 `ExecutionTrace`
- 三个 KPI 可通过接口拉取

### 十一、待办任务

可勾选任务清单见 **[`tasks.md`](./tasks.md)**（P0～P3 与文档同步）。

### 十二、仓库布局（Git / 前后端）

见 **[`../../docs/REPO_LAYOUT.md`](../../docs/REPO_LAYOUT.md)**。
