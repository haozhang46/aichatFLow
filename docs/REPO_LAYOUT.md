# 仓库结构说明（TASK-P3-04）

本仓库采用 **单仓库多目录** 布局（非 git submodule）：

| 路径 | 说明 |
|------|------|
| `app/` | FastAPI 后端（Python 3.9+） |
| `chatui-taiwild/` | Next.js 前端（独立 `package.json`） |
| `tests_py/` | 后端 pytest |
| `specs/main/` | 规格与任务清单（`spec.md`、`tasks.md`、`plan.md`） |

## 开发

- 后端：`uvicorn app.main:app --reload --port 3000`（项目根目录，需 venv）
- 前端：`cd chatui-taiwild && npm run dev`

## Git 策略

- **推荐**：单仓根目录初始化 `git`，将 `chatui-taiwild/` 作为普通子目录提交。
- **若需拆分**：可将前端单独成仓，通过 CI 发布镜像或 npm 包；当前未配置 submodule。
