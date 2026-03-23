export type Strategy = "auto" | "agent" | "react" | "workflow";

export type PlanBranchNode = {
  id: string;
  parentId: string | null;
  text: string;
};

export type ClawhubPlanSuggestion = {
  slug: string;
  name: string;
  summary: string;
  score?: number;
  riskLevel: "low" | "medium" | "high";
  recommendation: "adopt" | "review" | "avoid";
  analysis: string;
  userSelected?: boolean;
};

export type ExecutionPlanStep = {
  id: string;
  type: string;
  action: string;
  input?: Record<string, unknown>;
  dependsOn?: string[];
  agent?: string;
  skills?: string[];
  outputSchema?: Record<string, unknown>;
};

export type ExecutionPlan = {
  planId: string;
  mode: Strategy;
  steps: ExecutionPlanStep[];
};

export type PlanHistoryItem = {
  id: string;
  query: string;
  requestId: string;
  mode: Strategy;
  lines: string[];
  intentDescription: string;
  recommendedSkills: string[];
  supplement: string;
  favorite: boolean;
  createdAt: string;
  savedPath?: string;
  taskChecklist?: Array<{ id: string; text: string; done: boolean }>;
  executionMode?: "auto_exec" | "user_exec";
  planBranches?: Record<number, PlanBranchNode[]>;
  selectedPlanBranch?: Record<number, Record<string, string>>;
  stepExecutionConfigs?: Record<number, { agent: string; skills: string[]; tools?: string[] }>;
  clawhubSuggestions?: ClawhubPlanSuggestion[];
  executionPlan?: ExecutionPlan;
  lastTraceId?: string;
};

export type ToolRequiredInput = {
  key: string;
  label: string;
  type?: "text" | "password" | "textarea";
  required?: boolean;
  secret?: boolean;
  placeholder?: string;
};

export type CapabilityAgent = {
  id: string;
  label: string;
  description: string;
  source?: string | { type?: string; path?: string };
};

export type CapabilitySkill = {
  id: string;
  name: string;
  source: string;
  installed: boolean;
  whitelisted?: boolean;
  /** ClawHub vector search */
  summary?: string;
  score?: number;
  manifest?: {
    toolId: string;
    riskLevel?: string;
    source?: string;
    permissions?: string[];
    inputSchema?: Record<string, unknown>;
    outputSchema?: Record<string, unknown>;
  };
};

export type CapabilityTool = {
  id: string;
  name: string;
  description: string;
  category?: string;
  builtin?: boolean;
  allowlisted?: boolean;
  denylisted?: boolean;
  inputSchema?: Record<string, unknown>;
  outputSchema?: Record<string, unknown>;
  exampleArgs?: Record<string, unknown>;
  requiredUserInputs?: ToolRequiredInput[];
  uiPlugin?: string | null;
  uiSchema?: {
    layout?: string;
    fields?: Array<{
      key: string;
      label: string;
      component?: string;
      placeholder?: string;
      rows?: number;
      min?: number;
      max?: number;
      step?: number;
      options?: Array<{
        label: string;
        value: string;
      }>;
    }>;
    actions?: Array<{
      key: string;
      label: string;
      type?: string;
    }>;
  } | null;
};

export type DeepSeekConfig = {
  enabled: boolean;
  apiKey: string;
  baseUrl: string;
  model: string;
};

export type RagConfig = {
  enabled: boolean;
  scope: string;
  topK: number;
};
