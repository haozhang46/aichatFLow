# Trace RPC Contract

## 1. 目标

本文档定义平台与外部 trace service 对接时使用的 RPC contract。

该 contract 的目标是：

- 让平台可以把 trace 存储切换到外部服务
- 让 trace backend 不绑定本地文件或数据库
- 为后续 GraphQL 控制面、外部 observability 平台、自定义 trace collector 提供稳定接口

当前平台逻辑：

- 如果配置了 `TRACE_RPC_URL`，优先走 RPC trace backend
- 如果未配置，回退到本地文件 backend

相关代码：

- [trace_store.py](/Users/haochaoliang/Desktop/aiChatFLow/app/services/trace_store.py)
- [config.py](/Users/haochaoliang/Desktop/aiChatFLow/app/core/config.py)

## 2. 传输方式

当前约定使用 HTTP JSON RPC 风格接口。

基础配置：

- `TRACE_RPC_URL`
- `TRACE_RPC_TIMEOUT_SECONDS`

请求格式：

- `Content-Type: application/json`

响应格式：

- JSON object

## 3. 接口列表

当前约定的最小接口为：

1. `POST /v1/traces/append`
2. `GET /v1/traces/{traceId}/events`
3. `GET /v1/traces?requestId=...&limit=...`

这 3 个接口是当前平台 trace backend 切 RPC 时的最小必要能力。

## 4. Append Event

### 4.1 Endpoint

`POST /v1/traces/append`

### 4.2 用途

向外部 trace service 追加一条事件。

### 4.3 请求体

```json
{
  "traceId": "run_abcd1234",
  "event": {
    "ts": "2026-03-23T10:00:00+00:00",
    "traceId": "run_abcd1234",
    "type": "tool_call_started",
    "timestamp": "2026-03-23T10:00:00+00:00",
    "runId": "run_abcd1234",
    "spanId": "toolcall_1234",
    "parentSpanId": "s1",
    "status": "success",
    "toolId": "file-read",
    "userId": "user-1",
    "metadata": {
      "source": "otie_runtime"
    }
  }
}
```

### 4.4 字段说明

- `traceId`
  外层 trace 标识，必须与事件中的 `traceId` 一致
- `event`
  一条完整 trace 事件

### 4.5 成功响应

```json
{
  "status": "success"
}
```

### 4.6 失败响应

```json
{
  "status": "failed",
  "error": {
    "code": "trace_append_failed",
    "message": "..."
  }
}
```

如果返回非 2xx，平台视为 trace RPC 写入失败。

## 5. Get Trace Events

### 5.1 Endpoint

`GET /v1/traces/{traceId}/events`

### 5.2 用途

按 `traceId` 获取完整事件流。

### 5.3 成功响应

```json
{
  "traceId": "run_abcd1234",
  "events": [
    {
      "traceId": "run_abcd1234",
      "runId": "run_abcd1234",
      "spanId": "span_1",
      "type": "run_started",
      "timestamp": "2026-03-23T10:00:00+00:00"
    }
  ]
}
```

### 5.4 不存在响应

`404`

```json
{
  "detail": "trace not found"
}
```

平台收到 `404` 时，会把该 trace 视为不存在，而不是异常。

## 6. Find Traces By Request

### 6.1 Endpoint

`GET /v1/traces?requestId=...&limit=...`

### 6.2 用途

按 `requestId` 查询相关 trace 列表。

### 6.3 Query 参数

- `requestId`
  必填
- `limit`
  可选，默认由平台传入，通常为 `20`

### 6.4 成功响应

```json
{
  "traceIds": [
    "run_abcd1234",
    "tool_efgh5678"
  ]
}
```

## 7. 事件结构要求

RPC trace service 应接受与平台 `Trace Contract` 一致的事件结构。

参考文件：

- [trace-event.schema.json](/Users/haochaoliang/Desktop/aiChatFLow/specs/main/contracts/trace-event.schema.json)

当前核心字段：

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

## 8. 当前事件类型

当前平台可能发送的事件包括：

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
- `definition_published`

RPC 服务不应对事件类型做过度假设，应允许平台未来扩展事件枚举。

## 9. 错误处理约定

### 9.1 平台侧

当前平台实现策略：

- `append` 失败时，底层 HTTP client 会抛异常
- `read_trace`：
  - 遇到 `404`，返回空列表
  - 遇到其他非 2xx，抛异常
- `find_by_request_id`：
  - 非 2xx 视为失败

### 9.2 RPC 服务侧

建议错误码至少包括：

- `trace_not_found`
- `trace_append_failed`
- `trace_query_failed`
- `invalid_trace_payload`

## 10. 兼容性要求

RPC trace service 应保证：

1. append 为幂等可接受但不强依赖幂等
2. 事件顺序按写入顺序返回
3. `GET /v1/traces/{traceId}/events` 返回的 `events` 为数组
4. `GET /v1/traces` 返回的 `traceIds` 为数组

## 11. 当前非目标

当前 trace RPC contract 还不包含：

- 聚合统计接口
- 跨 trace 复杂搜索接口
- Trace sampling 配置
- Span attributes 的高级索引能力
- OpenTelemetry 标准协议兼容

这些后续可以扩展，但不属于当前最小 contract。

## 12. 后续建议

下一步建议补两类文档：

1. `trace query contract`
   如果后面需要支持筛选、分页、按 user/tool/agent 查询
2. `trace ingest contract`
   如果后面把 append 扩成批量写入或异步队列
