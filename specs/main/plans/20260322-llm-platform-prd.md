# LLM 控制系统底座 PRD

## 1. 背景

当前系统已经具备以下能力雏形：

- `tool` 注册与调用
- `agent` 运行与编排
- `RAG` 管理与检索
- `trace` 查看与运行记录
- 文件服务与 ACL 的基础实现

但整体仍存在明显耦合：

- `tool` 与 `agent` 定义部分仍在主系统代码中
- 平台层、业务能力层、扩展包层边界不清晰
- `trace`、`file access`、`tool invoke`、`agent runtime` 尚未完全收敛为统一底座能力
- 未来如果要支持“由 LLM 生成 tool 和 agent”，缺少标准化的定义、审核和发布流程

本 PRD 的目标是将当前系统演进为一个通用的 `LLM 控制系统底座`，让 `tool` 和 `agent` 通过标准 API 接入，并逐步从主仓库中拆出，以独立 submodule 方式管理。

## 2. 产品目标

### 2.1 总体目标

构建一个通用平台，使系统具备以下能力：

- 通过标准 API 注册、查询、发布、调用 `tool`
- 通过标准 API 注册、查询、发布、调用 `agent`
- `agent` 基于运行时策略自主选择何时调用 `tool`
- 所有资源访问通过平台统一控制，而不是由业务代码自行实现
- 所有执行过程统一 trace、统一审计、统一权限边界
- 后续支持由 LLM 生成 `tool` 和 `agent` 草案，并通过审核后发布

### 2.2 本期目标

- 明确平台分层与边界
- 固化 `Tool Manifest` 与 `Agent Spec`
- 将 `trace`、`file service`、`ACL` 明确纳入平台底层
- 设计 `agent-pack` 与 `tool-pack` 的 submodule 接入方式
- 明确 LLM 生成 `tool/agent` 的 draft -> review -> publish 流程
- 将 `contract` 的手动配置、查看与 review 工作台纳入产品规划，但不在当前实现范围内落地

## 3. 非目标

本期不包含以下内容：

- 不实现完整多租户企业权限系统
- 不实现完整市场化插件商店
- 不实现复杂计费体系
- 不直接让 LLM 生成的 tool/agent 自动发布上线
- 不将所有现有 builtin tool 一次性迁移完毕
- 不在当前阶段实现 `contract` 的手动配置界面与 definition 查看工作台，仅保留规划与契约设计

## 4. 目标用户

### 4.1 平台开发者

负责维护底座、运行时、权限、trace、registry。

### 4.2 Tool/Agent 开发者

基于标准 schema 与 API 创建新 `tool` 或 `agent`，并独立交付能力包。

### 4.3 最终使用者

通过 UI 或 API 使用 agent 完成任务，不需要理解平台内部实现。

### 4.4 LLM 生成工作流

使用自然语言描述需求，让系统先生成 `tool` 或 `agent` 草案，再审核、注册、发布。

## 5. 核心问题

当前架构需要解决的核心问题：

1. 平台底层与业务能力没有彻底分离。
2. `tool` 和 `agent` 的定义、执行、权限边界不够统一。
3. `trace` 没有被定义为独立平台能力。
4. 文件访问需要统一的鉴权与资源边界。
5. 如果未来引入 LLM 生成定义，缺少安全可控的发布链路。

## 6. 产品方案总览

平台整体拆为五层：

### 6.1 Core Platform

负责所有通用底座能力：

- Auth / Session
- ACL / Policy
- Tool Registry
- Agent Registry
- Runtime
- Trace
- File Service
- Definition Validation

### 6.2 Tool Layer

通过 `Tool Manifest` 描述能力，不直接耦合平台内部实现。

支持的执行形态：

- `builtin`
- `http`
- `file`
- `mcp`
- 未来可扩展 `workflow`

### 6.3 Agent Layer

通过 `Agent Spec` 描述 agent 的系统提示词、可用工具、运行模式、记忆与资源策略。

### 6.4 Extension Packs

将业务能力拆成独立子模块：

- `agent-pack`
- `tool-pack`

平台只负责扫描、校验、注册与调用，不直接持有业务定义。

### 6.5 Generator Layer

由 LLM 根据自然语言生成 `tool` 或 `agent` 草案，但必须经过平台审核与发布流程。

### 6.6 Console Layer

平台应预留一个统一控制台，用于后续承载以下能力：

- `tool` / `agent` definition 的手动配置
- definition 原始 schema、编译结果与状态查看
- draft review 与发布审批
- trace、ACL、RPC 配置的统一查看入口

该层在当前阶段先进入规划，不进入实现。

## 7. 架构分层

## 7.1 建议目录结构

```text
/app                         # core platform
/chatui-taiwild              # web ui
/packages
  /agent-pack                # git submodule
  /tool-pack                 # git submodule
/data
  /traces
  /registry
  /drafts
  /acl
  /stories
```

## 7.2 平台与能力包边界

### 平台层负责

- schema 与 contract
- registry
- runtime
- auth / acl
- trace
- file api
- draft/review/publish 流程

### 子模块负责

- `tool manifest`
- `agent spec`
- 可选 prompt、template、ui schema
- 可选外部 executor 配置

### 不允许的耦合

- `tool-pack` 不应直接依赖平台内部 service
- `agent-pack` 不应直接操作 trace store
- 平台层不应把业务 tool/agent 定义硬编码回主仓库

## 8. Tool 设计

## 8.1 Tool Manifest

建议最小结构：

```json
{
  "id": "story-planner",
  "name": "Story Planner",
  "description": "Generate setting, characters and outline",
  "version": "0.1.0",
  "kind": "http",
  "inputSchema": {},
  "outputSchema": {},
  "uiSchema": {},
  "auth": {
    "mode": "user"
  },
  "endpoint": {
    "url": "http://tool-service/v1/run",
    "timeoutMs": 15000
  },
  "policy": {
    "allowAgents": ["story-agent"]
  }
}
```

## 8.2 Tool 生命周期

1. Draft
2. Validate
3. Register
4. Publish
5. Invoke
6. Deprecate / Disable

## 8.3 Tool 核心 API

- `POST /v1/tools/draft`
- `POST /v1/tools/register`
- `POST /v1/tools/{id}/publish`
- `GET /v1/tools`
- `GET /v1/tools/{id}`
- `POST /v1/tools/{id}/invoke`

## 9. Agent 设计

## 9.1 Agent Spec

建议最小结构：

```json
{
  "id": "story-agent",
  "name": "Story Agent",
  "description": "Long-running story writing agent",
  "version": "0.1.0",
  "systemPrompt": "You are a long-running story agent...",
  "availableTools": ["file-read", "file-write", "retrieval"],
  "runtime": {
    "mode": "react",
    "maxSteps": 12
  },
  "memory": {
    "type": "file",
    "root": "stories/"
  },
  "policy": {
    "requiresUserContext": true
  }
}
```

## 9.2 Agent 核心能力

- 基于 spec 启动
- 按 policy 限制可用工具
- 根据 runtime mode 执行
- 使用平台提供的文件、trace、memory、tool invoke 能力

## 9.3 Agent 核心 API

- `POST /v1/agents/draft`
- `POST /v1/agents/register`
- `POST /v1/agents/{id}/publish`
- `GET /v1/agents`
- `GET /v1/agents/{id}`
- `POST /v1/agents/{id}/invoke`

## 10. 文件服务与鉴权

文件服务属于平台底层，不属于任何业务 agent 或 tool。

## 10.1 设计原则

- 用户身份统一从 `cookie/session` 获取
- 不允许前端直传 `userId`
- 所有文件访问都经过 ACL
- 所有路径限制在白名单根目录内
- 平台只暴露受控文件 API 与 file tools

## 10.2 文件 API

- `GET /v1/files`
- `GET /v1/files/tree`
- `PUT /v1/files`
- `DELETE /v1/files`

## 10.3 ACL API

- `GET /v1/files/acl`
- `POST /v1/files/acl`
- `DELETE /v1/files/acl`

## 10.4 Agent 可用文件能力

- `file-list`
- `file-read`
- `file-write`
- `file-delete`

这些能力由平台以 tool 方式暴露给 agent，agent 只知道能力，不知道底层真实文件系统实现。

## 11. Trace 设计

`trace` 必须属于平台层，不属于 `agent-pack` 或 `tool-pack`。

## 11.1 目标

- 所有 agent run 有统一 trace
- 所有 tool 调用有统一 trace
- 所有文件操作与 ACL 拒绝有统一审计记录
- trace 查询与展示统一由平台 API 提供

## 11.2 Trace 模型

核心字段：

- `traceId`
- `runId`
- `spanId`
- `parentSpanId`
- `type`
- `status`
- `timestamp`
- `agentId`
- `toolId`
- `metadata`

## 11.3 Trace 事件来源

### Runtime 事件

- `run_started`
- `step_started`
- `step_completed`
- `replanned`
- `run_completed`

### Tool 事件

- `tool_call_started`
- `tool_call_completed`
- `tool_call_failed`

### File 事件

- `file_read`
- `file_write`
- `file_delete`
- `acl_denied`

### Registry 事件

- `tool_registered`
- `agent_registered`
- `draft_published`

## 11.4 Trace API

- `GET /v1/traces/{traceId}`
- `GET /v1/runs/{runId}`
- `GET /v1/traces/{traceId}/events`

## 12. 子模块方案

## 12.1 为什么用 submodule

当前阶段使用 `git submodule` 的优势：

- 边界清晰
- 迁移成本低
- 可以独立管理 `tool` 和 `agent` 定义
- 平台与能力包版本关系可控

## 12.2 子模块拆分建议

### `packages/agent-pack`

包含：

- `agents/*.json`
- `prompts/*.md`
- `templates/*`

### `packages/tool-pack`

包含：

- `manifests/*.json`
- `ui/*.json`
- `examples/*`
- 可选 `executors/*`

## 12.3 平台接入方式

平台启动时：

1. 扫描子模块目录
2. 读取 spec / manifest
3. 做 schema 校验
4. 注册到 registry
5. 对外暴露统一 API

## 13. LLM 生成流程

## 13.1 原则

LLM 只能生成草案，不能直接发布。

## 13.2 流程

1. 用户用自然语言描述需求
2. 系统调用 LLM 生成 draft
3. 平台做 schema 校验
4. 用户或管理员 review
5. 注册
6. 发布

## 13.3 Draft API

- `POST /v1/tools/draft`
- `POST /v1/agents/draft`

## 13.4 Review / Publish API

- `POST /v1/tools/register`
- `POST /v1/tools/{id}/publish`
- `POST /v1/agents/register`
- `POST /v1/agents/{id}/publish`

## 14. 核心用户故事

### 14.1 平台开发者

作为平台开发者，我希望 tool 和 agent 通过标准 schema 接入，这样 runtime、trace、auth、acl 可以统一控制。

### 14.2 Tool 开发者

作为 tool 开发者，我希望只编写 manifest 和 executor 配置，而不需要修改平台核心代码。

### 14.3 Agent 开发者

作为 agent 开发者，我希望通过 spec 声明系统提示词、可用工具和 memory 策略，而不需要侵入底层运行时代码。

### 14.4 最终用户

作为最终用户，我希望通过 UI 使用 agent，并且 agent 访问文件或调用工具时始终受权限控制。

### 14.5 LLM 配置生成者

作为产品设计者，我希望用自然语言生成新的 tool/agent 草案，再审核后上线，以降低扩展成本。

## 15. 非功能要求

- 所有身份从 cookie/session 获取
- 所有文件访问必须经过 ACL
- 所有 tool 调用必须经过 registry
- 所有 agent 执行必须经过 runtime
- 所有 run 与 tool call 必须可 trace
- manifest/spec 必须版本化
- 支持从 JSON 文件存储平滑迁移到数据库

## 16. 里程碑

### M1 平台契约收敛

- 固化 `Tool Manifest`
- 固化 `Agent Spec`
- 固化 trace contract

### M2 文件服务与权限

- 文件 API
- ACL API
- file tools 接入 runtime

### M3 Tool 平台化

- tool registry API
- draft/register/publish/invoke
- builtin/http/file executor 抽象

### M4 Agent 平台化

- agent registry API
- spec loader
- invoke/publish 流程

### M5 子模块拆分

- `agent-pack` submodule
- `tool-pack` submodule
- loader 接入

### M6 LLM 生成

- tool draft 生成
- agent draft 生成
- review / publish 流程

## 17. 风险与约束

### 17.1 规范不稳定

如果 schema 在拆分后频繁变化，会导致 submodule 与平台兼容性频繁破坏。

### 17.2 权限边界失控

如果 agent/tool 绕过统一 runtime 或 file service，平台会失去权限控制能力。

### 17.3 Trace 不统一

如果 tool/agent 直接自建 trace 存储，会导致链路不可追踪。

### 17.4 LLM 生成风险

如果 draft 没有 review/publish 闭环，LLM 生成的定义可能带来越权、错误 schema 或不稳定行为。

## 18. MVP 建议

第一阶段建议先做到：

1. 文件服务 + ACL
2. Tool Manifest + Tool Registry
3. Agent Spec + Agent Registry
4. Trace Contract + Trace Query API
5. `agent-pack` / `tool-pack` 子模块加载

做到这一步，系统已经具备“可运行的通用 LLM 控制底座”形态。

## 19. 后续拆解建议

本 PRD 后续可拆成三份实施文档：

- 架构设计文档
- API 合同文档
- 分阶段任务拆解文档
