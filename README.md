# aiChatFLow

FastAPI 网关（统一 plan / execute、能力发现等）。**必须用安装了依赖的 Python 环境启动**，否则会报 `ModuleNotFoundError: No module named 'langchain_openai'`。

## 后端（推荐）

在项目根目录：

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 3000
```

若使用 **Conda / 系统 Python**，请先在该环境中安装依赖：

```bash
cd /path/to/aiChatFLow
pip install -r requirements.txt
# 或
pip install -e .
```

然后再运行 `uvicorn`（确保 `which python` / `python -c "import langchain_openai"` 指向同一环境）。

## 前端

```bash
cd chatui-taiwild
npm install
npm run dev
```

更多说明见 `specs/main/quickstart.md`、`docs/REPO_LAYOUT.md`。
