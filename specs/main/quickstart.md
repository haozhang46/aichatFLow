# Quickstart - Skill + Agent Configuration UI

## 1. Prerequisites

- Python 3.9+
- Node.js 20+
- Optional LLM credentials for non-heuristic routing:
  - `OPENAI_API_KEY`
  - `OPENAI_BASE_URL`
  - `OPENAI_MODEL`

## 2. Start Services

### Backend (FastAPI)

```bash
cd /Users/haochaoliang/Desktop/aiChatFLow
source .venv/bin/activate
uvicorn app.main:app --reload --port 3000
```

### Frontend (Next.js)

```bash
cd /Users/haochaoliang/Desktop/aiChatFLow/chatui-taiwild
npm install
npm run dev
```

## 3. Validate Capability Discovery

```bash
curl -X GET http://127.0.0.1:3000/v1/capabilities
```

Expected:
- Includes built-in agents (`agent`, `react`, `workflow`)
- Includes skill list with `installed/trusted` metadata

## 4. Validate Plan-First Flow

```bash
curl -X POST http://127.0.0.1:3000/v1/unified/plan \
  -H "Content-Type: application/json" \
  -d '{
    "requestId": "req-plan-001",
    "tenantId": "tenant-a",
    "requestType": "chat",
    "messages": [{"role":"user","content":"我想知道今天上海天气"}],
    "inputs": {"strategy":"auto"}
  }'
```

Expected:
- Response includes `output.plan`
- Response includes recommendation metadata (`recommendedAgent`, `recommendedSkills`, `missingSkills`, `installRequired`)

## 5. Confirm + Stream Execute

```bash
curl -N -X POST http://127.0.0.1:3000/v1/unified/execute/stream \
  -H "Content-Type: application/json" \
  -d '{
    "requestId": "req-plan-001",
    "tenantId": "tenant-a",
    "requestType": "chat",
    "messages": [{"role":"user","content":"我想知道今天上海天气"}],
    "inputs": {
      "strategy": "auto",
      "confirmed": true,
      "confirmedPlan": ["识别城市与时间", "获取天气信息", "输出建议"],
      "planSupplement": "优先给出白天逐小时天气"
    }
  }'
```

Expected stream event order:
- `status`
- `mode`
- one or more `thought`
- terminal `done`

## 7. Optional: Schema validation & ClawHub workspace stub

- **JSON Schema（步骤输出）**：在 `executionPlan.steps[].outputSchema` 提供 Draft-7 兼容 schema；执行时在 `inputs.schemaValidationMode` 设为 `warn`（默认）或 `block`（失败则终止）；SSE 会发出 `schema_check`。
- **ClawHub 本地占位同步**：设置环境变量 `CLAWHUB_WORKSPACE_SYNC_ENABLED=true` 且 `CLAWHUB_WORKSPACE_PATH=/your/path`，在 `POST /v1/clawhub/register` 时会在该路径下写入占位目录（可替换为真实 `clawhub install`）。

## 6. UI Acceptance Checklist

- Left sidebar renders plan history as category tree.
- Supports favorite toggle, delete item, delete category.
- Selecting history item loads plan back into editable panel.
- Each plan step is editable; supplement input is supported.
- Execution requires explicit confirmation from plan panel.
