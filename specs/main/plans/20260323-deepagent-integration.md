# DeepAgent 接入方案

## 1. 目标

将当前平台中的 `agent 执行内核` 替换为 `DeepAgent` 风格的执行引擎，同时保留平台已经收敛好的底座能力：

- `Agent Spec`
- `Tool Registry`
- `File Service + ACL`
- `Trace`
- `Definition Registry / Draft / Publish`

目标不是替换整个平台，而是替换 `agent runtime / planner / replan loop` 这一层。

## 2. 当前架构中的替换边界

### 2.1 保留的部分

以下能力继续由平台负责，不交给 DeepAgent：

- `Tool Manifest` 与 `Tool Registry`
- `Agent Spec` 与 `Agent Registry`
- 文件服务与 ACL
- trace contract 与 trace store
- definition lifecycle
- draft / register / publish API

对应当前实现：

- `app/tools/registry.py`
- `app/services/tool_definition_registry_service.py`
- `app/services/agent_registry_service.py`
- `app/api/routes/files.py`
- `app/services/file_service.py`
- `app/services/file_acl_service.py`
- `app/services/platform_trace_service.py`
- `app/services/trace_store.py`

### 2.2 替换的部分

最适合替换为 DeepAgent 的部分：

- `OtieRuntime`
- planner / replan loop
- agent invoke 时的执行编排

对应当前实现：

- `app/runtime/loop.py`
- `app/planner/*`
- `app/api/routes/unified.py` 中的 `POST /v1/agents/{agentId}/invoke`

## 3. 目标形态

平台演进后的结构应为：

1. 平台读取 `Agent Spec`
2. 平台解析出 `systemPrompt / availableTools / runtime / memory / policy`
3. 平台将这些内容映射为 `DeepAgentRuntimeConfig`
4. 平台把 `Tool Registry`、文件工具、trace emitter 注入给 DeepAgent
5. DeepAgent 负责：
   - 步骤规划
   - 动态选 tool
   - replan
   - 反思与继续执行
6. 平台负责：
   - 工具权限边界
   - 文件权限边界
   - trace 标准化
   - 结果回包 contract

## 4. 接入原则

### 4.1 平台是控制面

平台负责：

- 定义
- 鉴权
- 审批
- trace
- 资源边界

DeepAgent 不直接管理这些数据源。

### 4.2 DeepAgent 是执行面

DeepAgent 只负责执行：

- plan
- act
- observe
- replan
- respond

### 4.3 所有外部能力都通过平台注入

DeepAgent 不直接访问：

- 文件系统
- 自定义 tool 存储
- trace store

而是通过平台注入的 adapter 使用：

- tool adapter
- file adapter
- trace adapter

## 5. Agent Spec 到 DeepAgent 的映射

建议映射如下：

| Agent Spec 字段 | DeepAgent Runtime 配置 |
| --- | --- |
| `id` | `agentId` |
| `name` | `agentName` |
| `systemPrompt` | `systemPrompt` |
| `availableTools` | `allowedToolIds` |
| `runtime.mode` | `executionMode` |
| `runtime.maxSteps` | `maxSteps` |
| `memory.type` | `memoryMode` |
| `memory.root` | `workspaceRoot` |
| `policy.requiresUserContext` | `requiresUserContext` |
| `policy.allowFileAccess` | `allowFileAccess` |
| `policy.allowNetworkAccess` | `allowNetworkAccess` |

建议新增一个平台内的 adapter 层：

- `DeepAgentRuntimeAdapter`

职责：

- 读取 `Agent Spec`
- 构造 DeepAgent 配置
- 注入工具、文件、trace 适配器
- 返回统一的 `AgentInvokeResponse`

## 6. Tool Registry 接入方式

DeepAgent 不直接维护 tools 列表。

平台应暴露一个统一 adapter：

- `PlatformToolAdapter`

能力：

- 列出 agent 可用 tools
- 根据 `toolId` 调用 `ToolRegistry.execute`
- 在调用前自动注入：
  - `currentUserId`
  - `currentAgentId`
  - `allowedToolIds`
  - `traceId`

这样 DeepAgent 只知道自己有一组工具，不知道平台内部 registry 的实现。

## 7. File Service 接入方式

文件访问继续由平台控制。

建议只把以下平台工具暴露给 DeepAgent：

- `file-list`
- `file-read`
- `file-write`
- `file-delete`
- `file-mkdir`
- `file-patch`

平台继续保证：

- cookie 登录态识别用户
- ACL 校验
- `stories/` 根目录限制
- 审计 trace

DeepAgent 不应直接获得磁盘路径。

## 8. Trace 接入方式

DeepAgent 接入后，trace 仍然必须遵守平台 trace contract。

建议方式：

1. 平台在 invoke 开始时创建 `traceId / runId`
2. DeepAgent 每次：
   - plan
   - tool call
   - replan
   - final respond
   都通过 `PlatformTraceAdapter` 发事件
3. 平台把事件写入：
   - RPC trace backend
   - 或本地 fallback backend

建议至少映射这些事件：

- `run_started`
- `step_started`
- `step_completed`
- `replanned`
- `tool_call_started`
- `tool_call_completed`
- `tool_call_failed`
- `run_completed`

## 9. 建议新增的 Adapter 接口

建议平台新增三类 adapter：

### 9.1 `DeepAgentRuntimeAdapter`

职责：

- `invoke(agent_spec, request, context) -> result`

### 9.2 `PlatformToolAdapter`

职责：

- `list_allowed_tools(agent_spec) -> list[ToolManifest]`
- `execute(tool_id, args, context) -> result`

### 9.3 `PlatformTraceAdapter`

职责：

- `emit_run_started(...)`
- `emit_step_started(...)`
- `emit_tool_call_started(...)`
- `emit_tool_call_completed(...)`
- `emit_run_completed(...)`

## 10. 替换顺序

建议按下面顺序做，不要一次替掉整条链：

### Phase 1

新增 `DeepAgentRuntimeAdapter`，但暂时不切默认流量。

### Phase 2

让 `POST /v1/agents/{agentId}/invoke` 在 custom agent 上优先走 DeepAgent adapter。

### Phase 3

让 `story-agent` 先作为首个完整 DeepAgent 接入对象。

### Phase 4

评估是否将现有 `OtieRuntime` 退化为兼容层，或仅保留 workflow / legacy 路径。

## 11. 风险

### 11.1 Tool 权限绕过

如果 DeepAgent 直接调用底层能力，而不走平台 registry，就会绕过：

- allowlist / denylist
- `availableTools`
- ACL

所以必须通过 adapter。

### 11.2 Trace 断裂

如果 DeepAgent 使用自己的事件结构，不经过平台 trace adapter，会导致：

- trace viewer 无法统一展示
- run 与 tool call 无法关联

### 11.3 文件越权

如果 DeepAgent 直接碰文件系统，会绕过 cookie + ACL 模型。

### 11.4 双 runtime 并存复杂度

短期内 `OtieRuntime` 和 `DeepAgentRuntimeAdapter` 并存，会增加维护复杂度，需要清晰的路由与开关。

## 12. 最小落地建议

最小接入顺序建议：

1. 新增 `DeepAgentRuntimeAdapter`
2. 定义 `Agent Spec -> DeepAgentConfig` 映射
3. 注入 `Tool Registry / File Tools / Trace Adapter`
4. 先让 `story-agent` 走新链路
5. 保留现有 `OtieRuntime` 作为 fallback

## 13. 结论

当前平台最适合直接接入 DeepAgent 的位置，是 `agent 执行引擎`，不是整个系统。

推荐策略：

- 保留平台底座
- 替换执行内核
- 通过 adapter 把 tool、file、trace 注入 DeepAgent
- 先从 `story-agent` 开始试点
