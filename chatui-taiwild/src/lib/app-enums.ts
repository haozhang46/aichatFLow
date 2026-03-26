export const STRATEGIES = {
  AUTO: "auto",
  AGENT: "agent",
  REACT: "react",
  WORKFLOW: "workflow",
} as const;

export const STRATEGY_VALUES = [
  STRATEGIES.AUTO,
  STRATEGIES.AGENT,
  STRATEGIES.REACT,
  STRATEGIES.WORKFLOW,
] as const;

export type Strategy = (typeof STRATEGY_VALUES)[number];

export const EXECUTION_MODES = {
  AUTO_EXEC: "auto_exec",
  USER_EXEC: "user_exec",
} as const;

export const EXECUTION_MODE_VALUES = [
  EXECUTION_MODES.AUTO_EXEC,
  EXECUTION_MODES.USER_EXEC,
] as const;

export type ExecutionMode = (typeof EXECUTION_MODE_VALUES)[number];
