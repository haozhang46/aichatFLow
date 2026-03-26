import type {
  ClawhubPlanSuggestion,
  ExecutionMode,
  ExecutionPlan,
  PlanHistoryItem,
  StepExecutionConfig,
  Strategy,
} from "@/app/components/modalTypes";

export type DeepSeekConfig = {
  enabled: boolean;
  apiKey: string;
  baseUrl: string;
  model: string;
};

export type StepRunState = "pending" | "running" | "success" | "failed";

export type FolderAuthorization = {
  path: string;
  permission: string;
};

export type PlannedChatPayload = {
  requestId: string;
  query: string;
  mode: Strategy;
  reusedFromPlanRecord: boolean;
  planRecordPath?: string;
  intentDescription: string;
  thinking: string;
  searchEvidence: Array<{ title: string; url: string }>;
  lines: string[];
  recommendedSkills: string[];
  missingSkills: string[];
  installRequired: boolean;
  requiredSkills: string[];
  executionMode: ExecutionMode;
  clawhubSuggestions: ClawhubPlanSuggestion[];
  executionPlan: ExecutionPlan;
  historyItem: PlanHistoryItem;
  initialStepConfigs: Record<number, StepExecutionConfig>;
};
