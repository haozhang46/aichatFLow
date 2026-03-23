# Execution Plan: Tooling, RAG, And Browser Automation

- request_time_utc: 2026-03-21T11:47:13Z
- owner: Codex
- status: in_progress

## 1. Goal

Complete the next implementation phase for OTIE-based tooling:

1. Add step-level required tool inputs in the confirm area.
2. Add tool metadata/schema support for debugging and UI generation.
3. Keep chat concise while moving execution details into trace and dedicated viewers.
4. Prepare the codebase for browser automation and tool playground work.

## 2. Prioritized Tasks

### P0

1. Confirm area required tool inputs
2. Secure secret input handling in UI/runtime path
3. Merge step tool inputs into OTIE toolArgs during execute

### P1

1. Tool metadata enhancements
2. Tool Playground backend invoke API
3. Tool Playground frontend UI

### P2

1. web-fetch tool
2. browser-fetch tool
3. browser-automation tool

### P3

1. Browser session/profile management
2. Action-level approval model
3. Site-specific wrappers such as bilibili actions

## 3. Current Sprint Scope

This execution round will implement:

1. required tool inputs metadata in tool registry
2. confirm UI for step-level tool inputs
3. execution payload support for tool inputs
4. runtime merge into toolArgs

## 4. Non-Goals For This Round

1. Full Tool Playground
2. Full Playwright automation
3. Scrapy/offline crawler jobs
4. Site-specific automation wrappers

## 5. Risks

1. Secret values must not be persisted in plan history or localStorage.
2. Step-level inputs must map deterministically to OTIE steps.
3. Existing plan execution and trace flows must remain backward compatible.

## 6. Validation

1. Python compile succeeds
2. Frontend TypeScript passes
3. Existing OTIE/unified flows still work
4. Step tool inputs can be supplied in confirm UI and arrive at tool execution
