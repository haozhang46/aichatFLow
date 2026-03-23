# DeepAgentRuntimeAdapter 接口设计

## 1. 目标

定义平台侧 `DeepAgentRuntimeAdapter` 的最小接口与数据流，使其能够在不破坏现有平台底座的前提下，替换当前 `OtieRuntime` 的执行内核。

本设计只定义接口与职责，不包含具体实现。

## 2. 设计边界

### 2.1 Adapter 负责

- 将 `Agent Spec` 映射为 `DeepAgentConfig`
- 将平台的 tool、file、trace 能力注入 DeepAgent
- 统一 `invoke` 输入与输出 contract
- 统一错误返回与 trace 事件

### 2.2 Adapter 不负责

- 管理 definition registry
- 管理文件 ACL
- 管理 trace store
- 直接读写平台注册数据

这些能力继续由平台底层负责。

## 3. 当前替换点

当前可替换点：

- [loop.py](/Users/haochaoliang/Desktop/aiChatFLow/app/runtime/loop.py)
- [unified.py](/Users/haochaoliang/Desktop/aiChatFLow/app/api/routes/unified.py)

目标形态：

1. `unified agent invoke`
2. `resolve agent spec`
3. `build adapter request`
4. `DeepAgentRuntimeAdapter.invoke(...)`
5. `return platform-standard AgentInvokeResponse`

## 4. 核心接口

建议定义：

```python
class DeepAgentRuntimeAdapter:
    async def invoke(
        self,
        agent_spec: dict[str, Any],
        request: DeepAgentInvokeRequest,
        context: DeepAgentInvokeContext,
    ) -> DeepAgentInvokeResult:
        ...
```

## 5. 输入模型

### 5.1 `DeepAgentInvokeRequest`

```python
@dataclass
class DeepAgentInvokeRequest:
    input: dict[str, Any]
    context: dict[str, Any]
    runtime_options: dict[str, Any]
    llm_config: dict[str, str] | None
```

说明：

- `input`
  - 用户输入，如 `message`
- `context`
  - 工作区、业务上下文、session 补充上下文
- `runtime_options`
  - 温度、最大轮次、stream、超时等运行选项
- `llm_config`
  - 可选模型配置

### 5.2 `DeepAgentInvokeContext`

```python
@dataclass
class DeepAgentInvokeContext:
    trace_id: str
    run_id: str
    user_id: str
    agent_id: str
    tenant_id: str | None
    allowed_tool_ids: list[str]
```

说明：

- `trace_id / run_id`
  平台创建，adapter 只沿用
- `user_id`
  来自 cookie/session
- `allowed_tool_ids`
  来自 `Agent Spec.availableTools`

## 6. 输出模型

```python
@dataclass
class DeepAgentInvokeResult:
    status: str
    mode: str
    answer: str
    events: list[dict[str, Any]]
    step_outputs: dict[str, Any]
    latency_ms: int
    error: dict[str, Any] | None = None
```

返回给平台后，再被包装成现有统一响应：

```json
{
  "status": "success|failed",
  "agent": {},
  "request": {
    "input": {},
    "context": {},
    "runtimeOptions": {},
    "strategy": "",
    "llmConfig": {}
  },
  "result": {
    "mode": "",
    "answer": ""
  },
  "error": null,
  "latencyMs": 0,
  "traceId": ""
}
```

## 7. Agent Spec 映射规则

平台在调用 adapter 前，先将 `Agent Spec` 转为运行配置。

建议映射：

```python
@dataclass
class DeepAgentConfig:
    agent_id: str
    agent_name: str
    system_prompt: str
    execution_mode: str
    max_steps: int
    memory_mode: str
    workspace_root: str | None
    requires_user_context: bool
    allow_file_access: bool
    allow_network_access: bool
    allowed_tool_ids: list[str]
```

映射来源：

- `id` -> `agent_id`
- `name` -> `agent_name`
- `systemPrompt` -> `system_prompt`
- `runtime.mode` -> `execution_mode`
- `runtime.maxSteps` -> `max_steps`
- `memory.type` -> `memory_mode`
- `memory.root` -> `workspace_root`
- `policy.requiresUserContext` -> `requires_user_context`
- `policy.allowFileAccess` -> `allow_file_access`
- `policy.allowNetworkAccess` -> `allow_network_access`
- `availableTools` -> `allowed_tool_ids`

## 8. 平台注入的 Adapter

`DeepAgentRuntimeAdapter` 不应直接碰平台内部 service，而是通过三个注入 adapter 工作。

### 8.1 `PlatformToolAdapter`

```python
class PlatformToolAdapter:
    async def execute(
        self,
        tool_id: str,
        args: dict[str, Any],
        *,
        user_id: str,
        agent_id: str,
        allowed_tool_ids: list[str],
        trace_id: str,
        parent_span_id: str | None = None,
    ) -> dict[str, Any]:
        ...
```

要求：

- 统一走 `ToolRegistry.execute`
- 自动注入：
  - `currentUserId`
  - `currentAgentId`
  - `allowedToolIds`
  - `traceId`

### 8.2 `PlatformFileAdapter`

建议只包装已有 `file-*` tools，而不是直接给文件系统：

```python
class PlatformFileAdapter:
    async def read(self, path: str, *, context: DeepAgentInvokeContext) -> dict[str, Any]:
        ...

    async def write(self, path: str, content: str, *, context: DeepAgentInvokeContext) -> dict[str, Any]:
        ...

    async def patch(self, path: str, content: str, mode: str, *, context: DeepAgentInvokeContext) -> dict[str, Any]:
        ...
```

### 8.3 `PlatformTraceAdapter`

```python
class PlatformTraceAdapter:
    def emit_run_started(self, *, trace_id: str, run_id: str, agent_id: str, user_id: str, metadata: dict[str, Any]) -> None:
        ...

    def emit_step_started(self, *, trace_id: str, run_id: str, step_id: str, metadata: dict[str, Any]) -> None:
        ...

    def emit_tool_call_started(self, *, trace_id: str, run_id: str, tool_id: str, metadata: dict[str, Any]) -> None:
        ...

    def emit_tool_call_completed(self, *, trace_id: str, run_id: str, tool_id: str, metadata: dict[str, Any]) -> None:
        ...

    def emit_run_completed(self, *, trace_id: str, run_id: str, status: str, metadata: dict[str, Any]) -> None:
        ...
```

## 9. 建议执行流程

### 9.1 `invoke` 时序

1. 路由层读取 `agent_id`
2. 读取 `Agent Spec`
3. 平台校验：
   - agent 状态
   - available tools
   - 用户上下文
4. 生成：
   - `DeepAgentConfig`
   - `DeepAgentInvokeRequest`
   - `DeepAgentInvokeContext`
5. 调 `DeepAgentRuntimeAdapter.invoke(...)`
6. 将结果封装成平台标准响应

### 9.2 工具调用时序

1. DeepAgent 决定调用 tool
2. 调用 `PlatformToolAdapter.execute(...)`
3. 平台校验：
   - `allowedToolIds`
   - tool policy
   - input schema
4. 平台发 trace
5. 调用 `ToolRegistry.execute`
6. 返回结构化结果

## 10. 错误模型

建议 adapter 返回标准错误对象，不直接抛原始异常到路由层。

```json
{
  "code": "agent_invoke_failed",
  "message": "deepagent execution failed",
  "details": {
    "stepId": "s2",
    "toolId": "file-read"
  }
}
```

建议错误 code：

- `agent_invoke_failed`
- `tool_not_allowed`
- `tool_invoke_failed`
- `file_access_denied`
- `runtime_timeout`
- `runtime_validation_failed`

## 11. Trace 对齐要求

adapter 发出的事件必须对齐平台已有 trace contract：

- `run_started`
- `step_started`
- `step_completed`
- `replanned`
- `tool_call_started`
- `tool_call_completed`
- `tool_call_failed`
- `run_completed`

不应引入一套仅 DeepAgent 自己能理解的事件主结构。

如果需要额外字段，应放到 `metadata`。

## 12. 与现有 `OtieRuntime` 的兼容方式

建议短期内保留双 runtime：

### 模式 A

legacy agent 继续走 `OtieRuntime`

### 模式 B

开启 `deepagent` 的 agent 走 `DeepAgentRuntimeAdapter`

建议通过下面任一方式切换：

- `Agent Spec.runtime.engine = "otie" | "deepagent"`
- 或内部灰度配置表

第一种更清晰。

## 13. 最小实现建议

第一版只需要做到：

1. 新增 `DeepAgentRuntimeAdapter` 抽象
2. 新增 `PlatformToolAdapter`
3. 新增 `PlatformTraceAdapter`
4. 在 `POST /v1/agents/{agentId}/invoke` 中增加 adapter 分支
5. 先让 `story-agent` 走该分支

## 14. 结论

`DeepAgentRuntimeAdapter` 应该是平台中的“执行桥接层”。

它的目标不是替代平台，而是：

- 接收平台标准定义
- 注入平台标准能力
- 把 DeepAgent 的执行过程映射回平台标准响应与 trace

这样平台底座仍然保持稳定，DeepAgent 只替换最该替换的执行内核。
