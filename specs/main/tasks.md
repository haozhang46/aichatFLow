# OTIE 待办任务（Backlog）

> 与 [`spec.md`](./spec.md) 中「OTIE 对齐改造清单」一致；已落地项可在实现后把 `- [ ]` 改为 `- [x]`。

## P0 — 执行与计划闭环

- [x] **TASK-P0-01**：执行器按 `ExecutionPlan.steps[]` 逐步执行（每步可独立 LLM / tool），而非仅拼接整段 `query` 后单次 `run_orchestrator_stream`。
- [x] **TASK-P0-02**：后端完整消费 `inputs.stepExecutions`（每步 `agent` / `skills`），与 UI 配置一致。
- [x] **TASK-P0-03**：Planner 输出与 `executionPlan` 对齐：`type`（`tool` | `llm` | …）、`action`、`dependsOn`、可选重试/超时元数据。
- [x] **TASK-P0-04**：高风险步骤拒绝后支持 **替代步骤**（用户编辑该步文案或替换为安全等价步骤后再续跑）。

## P1 — Constitution / 策略与校验

- [x] **TASK-P1-01**：独立 `PolicyEngine`（或等价模块）：`allow_tools` / `deny_tools` / `require_approval` / 租户或会话级配置。
- [x] **TASK-P1-02**：对关键输出做 **JSON Schema**（或等价）校验，失败记入 trace 并可配置阻断/降级。
- [x] **TASK-P1-03**：审批记录 **持久化**（与 `trace_id` / `request_id` 关联），可查询、可审计。

## P2 — 可观测、KPI、集成

- [x] **TASK-P2-01**：`ExecutionTrace` **持久化**（JSONL/DB 均可），并提供 `GET /v1/traces/{traceId}`（及按 `requestId` 查询）。
- [x] **TASK-P2-02**：`GET /v1/metrics/kpi`：计划成功率、工具失败率、Schema 合规率（口径与 `spec.md` 第十章一致）。
- [x] **TASK-P2-03**：Tool/Skill **统一 manifest**（`tool_id`、输入输出 schema、权限、`risk_level`、`source`）。
- [x] **TASK-P2-04**：ClawHub：可选打通 `clawhub install` 与本地 workspace 同步（与 manifest 联动）。

## P3 — 前端与工程

- [x] **TASK-P3-01**：待确认面板步骤行与 **Step 执行状态**（同一 `stepId`）对齐展示。
- [ ] **TASK-P3-02**：多步连续审批、拒绝后的「编辑再执行」完整 UX。
- [x] **TASK-P3-03**：计划记录详情/卡片展示 `traceId`、策略结果摘要。
- [x] **TASK-P3-04**：仓库结构：根目录 `aiChatFLow` 与 `chatui-taiwild` 的 **git 策略**统一（单仓或子模块说明）。
- [ ] **TASK-P3-05**：E2E（如 Playwright）：plan → 审批（若触发）→ 执行 → 断言 SSE 事件序列。

## 文档同步

- [x] **TASK-DOC-01**：`tasks.md` / `spec.md` 与 `OTIE_PRD_v1.md` 定期对照，标记「已实现 / 待办」避免漂移。（已在 `spec.md` 增加仓库布局链接；持续对照 PRD 为团队流程。）
