# aiChatFLow Constitution

## Core Principles

### I. Product-Oriented Integration
All work must directly improve the FastGPT + Dify integration product value. Features that do not map to user scenarios or operational outcomes are out of scope.

### II. API-First and Backward Compatibility
Integration interfaces must be explicit, documented, and versioned. Breaking changes require migration guidance and a clear deprecation path.

### III. Testability First
Every critical flow must be independently testable, including provider routing, fallback behavior, and workflow execution outcomes.

### IV. Security and Observability by Default
Secrets must not be logged. All cross-system requests must be traceable through structured logs and correlation identifiers.

### V. Incremental Delivery
Design and implementation must prefer small, independently releasable slices, starting with minimum viable orchestration capability.

## Additional Constraints

- Preferred stack is TypeScript on Node.js for service-layer integration.
- Data schemas must be explicit for request/response contracts.
- Configuration must support environment-based secret injection.

## Development Workflow

- Planning artifacts (`plan.md`, `research.md`, `data-model.md`, `quickstart.md`, and `contracts`) must be complete before implementation tasks are generated.
- Constitution gates are checked before and after design.
- Clarifications must be resolved in `research.md`; unresolved uncertainty blocks progression.

## Governance

This constitution supersedes local ad-hoc practices for this repository. Amendments require documented rationale and impact assessment on existing plans and contracts.

**Version**: 1.0.0 | **Ratified**: 2026-03-19 | **Last Amended**: 2026-03-19
