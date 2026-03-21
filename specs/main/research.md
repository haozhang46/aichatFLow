# Phase 0 Research - Skill + Agent Config UI

## Decision 1: Capability discovery model

- Decision: Introduce a backend `CapabilityService` that merges three sources: built-in agents, local installed skills, and optional remote candidate skills.
- Rationale: Keeps UI simple and consistent while avoiding direct filesystem/network logic in frontend.
- Alternatives considered: Frontend-only discovery (hard to secure and validate), static JSON list (quick but stale).

## Decision 2: Plan-first recommendation contract

- Decision: Extend plan response with recommendation metadata:
  - `recommendedAgent`
  - `recommendedSkills[]`
  - `missingSkills[]`
  - `installRequired` (boolean)
- Rationale: Allows users to confirm and edit plan before execution and installation.
- Alternatives considered: Only text plan (not machine-actionable), execute-time recommendation only (violates plan-first UX).

## Decision 3: Skill installation strategy

- Decision: Use whitelist-gated install flow with explicit confirmation, and never auto-install from arbitrary URLs.
- Rationale: Prevents supply-chain risks and unintended side effects while still enabling "auto install after confirmation."
- Alternatives considered: Free-form auto install (unsafe), manual-only install (friction too high for target UX).

## Decision 4: UI information architecture

- Decision: Add left-sidebar plan history tree grouped by category (mode/agent), with favorite, delete item, and delete category actions.
- Rationale: Supports quick recall/reuse and aligns with user requirement for tree-like organization.
- Alternatives considered: Flat history list (poor discoverability), server-side history first (slower MVP).

## Decision 5: Plan editability before execute

- Decision: Make each plan step editable and add a supplemental instruction field in confirmation panel.
- Rationale: Users can refine execution intent without rewriting original prompt.
- Alternatives considered: Non-editable plan (fails requirement), full rich editor (higher complexity for MVP).

## Decision 6: Streaming chain-of-thought representation

- Decision: Stream structured execution events (`status`, `mode`, `thought`, `done`) over SSE and render as incremental chain cards in UI.
- Rationale: Provides transparent execution progress while preserving existing transport.
- Alternatives considered: Polling endpoint (slower UX), WebSocket-only redesign (larger scope).

## Decision 7: Testing and rollout

- Decision: Add backend contract tests for capability and plan metadata plus frontend lint/build and manual acceptance checks for tree actions.
- Rationale: Keeps changes independently testable and aligned with constitution.
- Alternatives considered: Manual-only validation (high regression risk), full E2E before MVP (slower delivery).
