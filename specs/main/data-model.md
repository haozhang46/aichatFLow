# Data Model - Skill + Agent Configuration UI

## Entity: AgentCapability

- Purpose: Describe executable built-in agent modes shown in configuration UI.
- Fields:
  - `id` (string, stable key: `agent` | `react` | `workflow`)
  - `label` (string)
  - `description` (string)
  - `category` (string, e.g. `built-in`)
  - `available` (boolean)
- Validation Rules:
  - `id` must map to backend-supported execution mode.
  - `available=false` agents are non-selectable in plan stage.

## Entity: SkillCapability

- Purpose: Represent an installable or installed skill candidate.
- Fields:
  - `id` (string)
  - `name` (string)
  - `source` (enum: `local` | `curated` | `github`)
  - `installed` (boolean)
  - `trusted` (boolean, whitelist-based)
  - `version` (string, optional)
  - `tags` (string[])
  - `installCommand` (string, optional)
- Validation Rules:
  - `installCommand` is required when `installed=false` and `trusted=true`.
  - `trusted=false` skills cannot be auto-installed.

## Entity: PlanRecommendation

- Purpose: Machine-readable plan output before user confirmation.
- Fields:
  - `requestId` (string)
  - `query` (string)
  - `recommendedAgent` (string)
  - `recommendedSkills` (string[])
  - `missingSkills` (string[])
  - `installRequired` (boolean)
  - `planSteps` (string[])
  - `createdAt` (datetime)
- Relationships:
  - References `AgentCapability` and `SkillCapability`.
- Validation Rules:
  - `installRequired=true` only when `missingSkills` is non-empty.
  - `recommendedAgent` must be an available capability.

## Entity: PlanHistoryItem (UI-side)

- Purpose: Tree/list persistence item for reusable plans in left sidebar.
- Fields:
  - `id` (string)
  - `requestId` (string)
  - `query` (string)
  - `mode` (string)
  - `category` (string, defaults to mode)
  - `lines` (string[])
  - `supplement` (string)
  - `favorite` (boolean)
  - `createdAt` (datetime)
- Validation Rules:
  - Empty `lines` allowed, but item still must be displayable.
  - Category delete cascades to all items in category.

## Entity: ExecutionStreamEvent

- Purpose: Incremental UI updates during confirmed execution.
- Fields:
  - `type` (enum: `status` | `mode` | `thought` | `done` | `error`)
  - `message` (string, optional)
  - `content` (string, optional)
  - `answer` (string, optional)
  - `latencyMs` (number, optional)
- Validation Rules:
  - Stream must end with `done` or `error`.
  - `done` event must include final `answer`.

## State Transitions

- Plan flow:
  - `draft_input` -> `plan_generated` -> (`plan_edited`)* -> (`confirmed` | `cancelled`)
- Execute flow:
  - `confirmed` -> `execute_started` -> `streaming_events` -> (`done` | `error`)
