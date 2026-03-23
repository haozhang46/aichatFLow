# 基础 Contract 总览

## 1. 目的

本文档用于整理当前平台里的基础 contract，明确这些 contract 在系统中的用途、边界和关系。

这里的 contract 不是单纯“接口文档”，而是平台运行所依赖的统一约定。它们会被用于：

- 定义 `tool` / `agent`
- 校验定义是否合法
- 驱动 UI 配置与展示
- 约束 runtime 执行
- 对接 RPC / 外部服务
- 管理 lifecycle 与 trace

## 2. Contract 分类

当前基础 contract 可以分成 6 类：

1. Definition Contract
2. Runtime Contract
3. RPC / API Contract
4. UI Contract
5. Trace Contract
6. Lifecycle Contract

## 3. Definition Contract

Definition Contract 用于描述“某个能力长什么样”。

主要包括：

- `Tool Manifest`
- `Agent Spec`

### 3.1 Tool Manifest

文件：

- [tool-manifest.schema.json](/Users/haochaoliang/Desktop/aiChatFLow/specs/main/contracts/tool-manifest.schema.json)

用途：

- 定义一个 tool 的身份、输入输出、执行类型、权限与 UI 描述
- 用于 register / publish / invoke 前的校验
- 用于前端生成 tool 配置界面

关键字段：

- `id`
- `name`
- `description`
- `version`
- `kind`
- `inputSchema`
- `outputSchema`
- `uiSchema`
- `auth`
- `endpoint`
- `policy`
- `source`
- `status`

### 3.2 Agent Spec

文件：

- [agent-spec.schema.json](/Users/haochaoliang/Desktop/aiChatFLow/specs/main/contracts/agent-spec.schema.json)

用途：

- 定义一个 agent 的系统提示、可用工具、运行模式、memory 策略和权限边界
- 用于 register / publish / invoke 前的校验
- 用于平台加载 agent 定义

关键字段：

- `id`
- `name`
- `description`
- `version`
- `systemPrompt`
- `availableTools`
- `runtime`
- `memory`
- `outputSchema`
- `policy`
- `source`
- `status`

## 4. Runtime Contract

Runtime Contract 用于描述平台在执行过程中如何使用定义。

它不是单独一个文件，而是由 Definition Contract 中的几个字段共同组成：

- `Tool Manifest.kind`
- `Tool Manifest.inputSchema`
- `Tool Manifest.outputSchema`
- `Agent Spec.runtime`
- `Agent Spec.availableTools`
- `Agent Spec.memory`
- `Agent Spec.policy`

这些字段在运行时的作用：

- 决定 tool 如何被执行
- 决定 agent 能调用哪些 tool
- 决定 agent 以什么 mode 运行
- 决定 memory / file / network 的允许范围

换句话说：

- Definition Contract 负责“描述”
- Runtime Contract 负责“执行时解释这些描述”

## 5. RPC / API Contract

RPC / API Contract 用于定义平台与外部调用方、外部服务之间如何通信。

### 5.1 当前已有的 API 合同

文件：

- [llm-platform.openapi.yaml](/Users/haochaoliang/Desktop/aiChatFLow/specs/main/contracts/llm-platform.openapi.yaml)
- [unified-api.openapi.yaml](/Users/haochaoliang/Desktop/aiChatFLow/specs/main/contracts/unified-api.openapi.yaml)
- [capabilities.openapi.yaml](/Users/haochaoliang/Desktop/aiChatFLow/specs/main/contracts/capabilities.openapi.yaml)

用途：

- 定义 REST API 请求与响应结构
- 作为前后端和外部服务对接基础

### 5.2 Trace RPC Contract

当前 trace store 已支持：

- 外部 RPC trace service
- 本地文件 fallback

当前约定的 RPC 端点：

- `POST /v1/traces/append`
- `GET /v1/traces/{traceId}/events`
- `GET /v1/traces?requestId=...`

这部分已经单独整理为正式文档：

- [trace-rpc-contract.md](/Users/haochaoliang/Desktop/aiChatFLow/specs/main/contracts/trace-rpc-contract.md)

### 5.3 后续方向

如果未来引入 GraphQL 控制面，则建议：

- GraphQL 负责查询和配置
- RPC/HTTP 负责执行与内部服务调用

## 6. UI Contract

UI Contract 用于驱动前端自动生成配置界面和结果展示。

主要来源：

- `Tool Manifest.uiSchema`
- `Tool Manifest.inputSchema`
- `Tool Manifest.outputSchema`
- `Agent Spec.runtime`
- `Agent Spec.policy`
- lifecycle 状态字段

用途：

- 生成表单
- 生成字段校验
- 控制按钮可用状态
- 控制详情页和结果页展示

### 6.1 UI Contract 的两层结构

建议区分两层：

1. `builder model`
   给界面编辑使用
2. `compiled schema`
   给 runtime / validator 使用

也就是说：

- 用户在界面中编辑 key-value / field tree
- 平台把它编译成真正 schema

而不是让用户直接手写底层 schema 文本。

## 7. Trace Contract

Trace Contract 用于统一平台中的事件记录格式。

文件：

- [trace-event.schema.json](/Users/haochaoliang/Desktop/aiChatFLow/specs/main/contracts/trace-event.schema.json)

用途：

- 统一 tool 调用事件
- 统一 agent run 事件
- 统一 file / ACL 审计事件
- 为 trace query API 和 Trace Viewer 提供稳定结构

关键字段：

- `traceId`
- `runId`
- `spanId`
- `parentSpanId`
- `type`
- `status`
- `timestamp`
- `agentId`
- `toolId`
- `userId`
- `resourcePath`
- `metadata`

### 7.1 当前事件类型

主要包括：

- `run_started`
- `run_completed`
- `step_started`
- `step_completed`
- `replanned`
- `tool_call_started`
- `tool_call_completed`
- `tool_call_failed`
- `file_read`
- `file_write`
- `file_delete`
- `acl_denied`
- `tool_registered`
- `agent_registered`
- `draft_published`
- `definition_published`

## 8. Lifecycle Contract

Lifecycle Contract 用于定义 `tool` 和 `agent` 的状态流转。

文件：

- [definition-lifecycle.schema.json](/Users/haochaoliang/Desktop/aiChatFLow/specs/main/contracts/definition-lifecycle.schema.json)
- [platform-lifecycle.md](/Users/haochaoliang/Desktop/aiChatFLow/specs/main/platform-lifecycle.md)

用途：

- 统一 draft -> validate -> register -> publish 流程
- 统一 review / approval 状态
- 控制哪些定义可执行，哪些只可编辑

主要状态：

- `draft`
- `validated`
- `validation_failed`
- `registered`
- `publish_pending`
- `published`
- `publish_rejected`
- `disabled`
- `deprecated`

## 9. Contract 在系统中的使用点

### 9.1 注册阶段

使用：

- Definition Contract
- Lifecycle Contract

作用：

- 校验定义是否合法
- 写入 registry
- 设置初始状态

### 9.2 发布阶段

使用：

- Lifecycle Contract
- Trace Contract

作用：

- 控制状态迁移
- 记录发布事件

### 9.3 调用阶段

使用：

- Runtime Contract
- RPC / API Contract
- Trace Contract

作用：

- 校验输入
- 执行 tool / agent
- 写 trace

### 9.4 UI 阶段

使用：

- UI Contract
- Definition Contract
- Lifecycle Contract

作用：

- 自动生成配置页
- 显示当前状态
- 控制交互动作

## 10. 未来扩展建议

基础 contract 建议继续沿以下方向演进：

1. 把 trace RPC contract 单独落文档
2. 增加 contract builder 的 `builder model` 文档
3. 增加 `tool draft` / `agent draft` contract
4. 如果引入 GraphQL 控制面，再补一份 GraphQL schema 总览

## 11. 当前建议

后续所有新能力，都尽量先判断属于哪一类 contract：

- 是 definition？
- 是 runtime？
- 是 rpc？
- 是 ui？
- 是 trace？
- 是 lifecycle？

这样可以避免把不同职责的 contract 混在一个文件或一个接口里。
