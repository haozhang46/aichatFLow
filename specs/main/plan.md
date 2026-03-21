# Implementation Plan: Skill + Agent Config UI

**Branch**: `main` | **Date**: 2026-03-20 | **Spec**: `/specs/main/spec.md`  
**Input**: User request: "配置skill 和agent 的界面"

## Summary

Build a configuration UX that helps users choose proper `agent` and `skill` for a request, with a strict "plan first, confirm second, execute third" flow. The UI must show categorized plan history (tree style), support favorite/delete/category delete, and allow editing plan steps plus supplemental instructions before execution. Backend must provide capability discovery and plan metadata indicating recommended agent/skills and install requirements.

## Technical Context

**Language/Version**: Python 3.9 (backend), TypeScript 5.x + React 19 + Next.js 16 (frontend)  
**Primary Dependencies**: FastAPI, Pydantic, LangChain/LangGraph, Next.js, TailwindCSS  
**Storage**: In-memory for MVP (plan history in UI state), optional file-based cache for local skill catalog snapshot  
**Testing**: pytest (backend), eslint + Next build + manual integration checks (frontend)  
**Target Platform**: Local Linux/macOS development server + browser clients  
**Project Type**: Web service + web UI  
**Performance Goals**: plan generation p95 < 2s; stream first event < 1s under local dev conditions  
**Constraints**: Plan/execute must require explicit user confirmation; skill install path must be whitelist-gated; no secret leakage in logs  
**Scale/Scope**: Single-tenant local MVP first, extensible to multi-tenant config with persistent storage

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Product-Oriented Integration**: PASS. Skill/agent configuration directly improves orchestration outcomes.
- **II. API-First and Backward Compatibility**: PASS with additive endpoints/contracts only.
- **III. Testability First**: PASS. Plan generation, capability recommendation, confirmation gating, and stream execution are independently testable.
- **IV. Security and Observability by Default**: PASS with constraints (whitelist installs, trace IDs, no secret logging).
- **V. Incremental Delivery**: PASS. Deliver in slices: discovery -> plan metadata -> UI tree/history -> guarded install flow.

Post-design re-check: PASS (no unresolved clarifications, additive contracts preserved backward compatibility).

## Project Structure

### Documentation (this feature)

```text
specs/main/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── unified-api.openapi.yaml
│   └── capabilities.openapi.yaml
└── tasks.md
```

### Source Code (repository root)

```text
app/
├── api/routes/
│   └── unified.py
├── orchestrator/
│   └── graph.py
├── services/
│   └── capability_service.py            # new
└── schemas/
    └── unified.py

chatui-taiwild/
└── src/app/
    └── page.tsx

tests_py/
├── test_unified.py
└── test_capabilities.py                 # new
```

**Structure Decision**: Keep current FastAPI + Next.js structure; add a capability service in backend and extend existing chat page UI for tree/category/favorite/delete behavior.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Constitution stack preference says TypeScript service-layer | Existing implementation is already FastAPI/Python and active in production-like flow | Full backend rewrite would block incremental delivery and exceed current feature scope |
