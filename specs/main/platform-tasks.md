# LLM Platform 实施任务拆解

> 来源：[`20260322-llm-platform-prd.md`](./plans/20260322-llm-platform-prd.md)
>
> 目标：把当前系统演进为通用的 LLM 控制系统底座，并完成 agent/tool 与平台层的拆分。

## P0 — 契约与边界收敛

- [x] **PLATFORM-P0-01**：定义并冻结 `Tool Manifest` JSON schema。
- [x] **PLATFORM-P0-02**：定义并冻结 `Agent Spec` JSON schema。
- [x] **PLATFORM-P0-03**：定义 `trace event` schema，明确 `traceId / runId / spanId / parentSpanId` 模型。
- [x] **PLATFORM-P0-04**：明确平台层与 `agent-pack` / `tool-pack` 的责任边界文档。
- [x] **PLATFORM-P0-05**：定义 draft -> validate -> register -> publish 生命周期状态。

## P1 — 文件服务与权限

- [x] **PLATFORM-P1-01**：提供受限根目录下的文件服务，当前限制在 `stories/`。
- [x] **PLATFORM-P1-02**：用户身份从 cookie/session 提取，不接受客户端直传 `userId`。
- [x] **PLATFORM-P1-03**：基于 `user + path + action` 的 ACL 校验。
- [x] **PLATFORM-P1-04**：提供 `GET/PUT/DELETE /v1/files` 和 `GET /v1/files/tree`。
- [x] **PLATFORM-P1-05**：提供 `GET/POST/DELETE /v1/files/acl`。
- [x] **PLATFORM-P1-06**：将 `file-list/read/write/delete` 注册成 platform tools。
- [x] **PLATFORM-P1-07**：补充 `mkdir` 与 `patch` 文件能力。
- [x] **PLATFORM-P1-08**：增加文件操作审计事件并接入 trace store。
- [x] **PLATFORM-P1-09**：补充 ACL 拒绝场景的结构化错误码和 trace 记录。

## P2 — Tool 平台化

- [x] **PLATFORM-P2-01**：实现 tool registry 的持久化存储，支持 JSON 文件目录加载。
- [x] **PLATFORM-P2-02**：新增 `POST /v1/tools/register`。
- [x] **PLATFORM-P2-03**：新增 `GET /v1/tools` 与 `GET /v1/tools/{id}`。
- [x] **PLATFORM-P2-04**：新增 `POST /v1/tools/{id}/publish`。
- [x] **PLATFORM-P2-05**：新增 `POST /v1/tools/draft`。
- [x] **PLATFORM-P2-06**：把现有 builtin tools 对齐到统一 `Tool Manifest` 输出。
- [x] **PLATFORM-P2-07**：抽象 executor adapter，至少支持 `builtin/http/file` 三种类型。
- [x] **PLATFORM-P2-08**：引入 tool policy 校验，限制 agent 可调用的 tool 范围。
- [x] **PLATFORM-P2-09**：统一 tool invoke 响应结构与错误结构。

## P3 — Agent 平台化

- [x] **PLATFORM-P3-01**：实现 agent registry 的持久化存储，支持 JSON 文件目录加载。
- [x] **PLATFORM-P3-02**：新增 `POST /v1/agents/register`。
- [x] **PLATFORM-P3-03**：新增 `GET /v1/agents` 与 `GET /v1/agents/{id}`。
- [x] **PLATFORM-P3-04**：新增 `POST /v1/agents/{id}/publish`。
- [x] **PLATFORM-P3-05**：新增 `POST /v1/agents/draft`。
- [x] **PLATFORM-P3-06**：统一 agent invoke contract，包括 input、context、runtime options。
- [x] **PLATFORM-P3-07**：把现有 `story-agent` 对齐到统一 `Agent Spec`。
- [x] **PLATFORM-P3-08**：agent runtime 严格基于 `availableTools` 做白名单控制。
- [x] **PLATFORM-P3-09**：支持 agent memory policy 配置化。

## P4 — Trace 平台化

- [x] **PLATFORM-P4-01**：让 `ToolRegistry.execute` 成为唯一 tool trace 埋点入口。
- [x] **PLATFORM-P4-02**：让 `OtieRuntime.run` 成为唯一 agent run trace 埋点入口。
- [x] **PLATFORM-P4-03**：为 file tools 接入统一 trace 事件。
- [x] **PLATFORM-P4-04**：定义可插拔 trace store 模型，支持 RPC 优先、文件 fallback。
- [x] **PLATFORM-P4-05**：新增 `GET /v1/traces/{traceId}`。
- [x] **PLATFORM-P4-06**：新增 `GET /v1/traces/{traceId}/events`。
- [x] **PLATFORM-P4-07**：新增 `GET /v1/runs/{runId}`。
- [ ] **PLATFORM-P4-08**：前端 Trace Viewer 切到统一 trace contract。
- [x] **PLATFORM-P4-09**：增加 `tool_call_failed / acl_denied / draft_published` 等标准事件。

## P5 — 子模块拆分

- [ ] **PLATFORM-P5-01**：创建 `packages/agent-pack` 仓库并接入为 git submodule。
- [ ] **PLATFORM-P5-02**：创建 `packages/tool-pack` 仓库并接入为 git submodule。
- [ ] **PLATFORM-P5-03**：将现有 agent spec 迁移到 `agent-pack`。
- [ ] **PLATFORM-P5-04**：将现有 tool manifest 迁移到 `tool-pack`。
- [ ] **PLATFORM-P5-05**：平台启动时支持扫描子模块目录并自动注册。
- [ ] **PLATFORM-P5-06**：定义 submodule 版本与平台版本兼容策略。
- [ ] **PLATFORM-P5-07**：补充 submodule 接入说明与开发者指南。

## P6 — LLM Draft 生成与审核

- [ ] **PLATFORM-P6-01**：实现 `POST /v1/tools/draft` 的 LLM 草案生成链路。
- [ ] **PLATFORM-P6-02**：实现 `POST /v1/agents/draft` 的 LLM 草案生成链路。
- [x] **PLATFORM-P6-03**：增加 draft schema 校验。
- [ ] **PLATFORM-P6-04**：增加 register 前的 policy 校验。
- [ ] **PLATFORM-P6-05**：增加 publish 审批流程。
- [ ] **PLATFORM-P6-06**：记录 draft/review/publish 的 trace 与审计事件。
- [ ] **PLATFORM-P6-07**：前端提供 draft review 界面。

## P7 — 前端工作台

- [ ] **PLATFORM-P7-01**：新增 tool 工作台，支持 list/register/publish/invoke。
- [ ] **PLATFORM-P7-02**：新增 agent 工作台，支持 list/register/publish/invoke。
- [ ] **PLATFORM-P7-03**：新增 file ACL 管理面板。
- [ ] **PLATFORM-P7-04**：新增 tool/agent draft review 界面。
- [ ] **PLATFORM-P7-05**：统一展示 manifest/spec 校验错误。
- [ ] **PLATFORM-P7-06**：在 trace viewer 中展示 tool、agent、file 三类标准事件。
- [ ] **PLATFORM-P7-07**：新增 contract 手动配置工作台，支持以表单方式编辑 `Tool Manifest`、`Agent Spec`、RPC 配置与基础 key-value policy。
- [ ] **PLATFORM-P7-08**：新增 contract 查看页，支持查看已注册 definition 的原始 schema、编译结果、生命周期状态与关联 trace。
- [ ] **PLATFORM-P7-09**：新增手动配置与查看能力的只读预览模式，用于 review 场景，当前阶段先写入计划，不进入实现。

## 当前已完成项

- [x] 文件服务基础版
- [x] 基于 cookie 的用户识别
- [x] ACL 基础能力
- [x] `file-list/read/write/delete` tool 接入
- [x] OTIE 直调 tool 时透传 `currentUserId`
- [x] runtime 调用 tool 时透传 `currentUserId`
- [x] LLM Platform PRD 文档
- [x] LLM Platform OpenAPI 合同草稿

## 建议实施顺序

1. 先完成 `P0` 和 `P2/P3` 的 schema 与 registry。
2. 再完成 `P4`，把 trace 收敛成统一 contract。
3. 然后推进 `P5`，把定义迁移到 submodule。
4. 最后做 `P6/P7`，把 LLM draft 与工作台补齐。

## 备注

- `contract` 的手动配置与查看/管理能力已纳入 `P7` 规划，但当前阶段只保留在 plan 中，不进入实现。
