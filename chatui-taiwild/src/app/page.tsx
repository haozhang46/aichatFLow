"use client";

import { useEffect, useMemo, useRef, useState, type ReactElement } from "react";
import {
  type Edge,
  type Node,
  addEdge,
  useEdgesState,
  useNodesState,
  type Connection,
} from "@xyflow/react";
import TaskFlowModal from "@/components/TaskFlowModal";
import ChatPanel from "@/components/chat/ChatPanel";
import AppButton from "@/components/ui/AppButton";
import CapabilityModal from "@/app/components/CapabilityModal";
import DeepseekModal from "@/app/components/DeepseekModal";
import PlanRecordModal from "@/app/components/PlanRecordModal";
import PlanDetailModal from "@/app/components/PlanDetailModal";
import RagViewerModal from "@/app/components/RagViewerModal";
import SettingsModal from "@/app/components/SettingsModal";
import AgentPlaygroundModal from "@/app/components/AgentPlaygroundModal";
import ToolPlaygroundModal from "@/app/components/ToolPlaygroundModal";
import TraceModal from "@/app/components/TraceModal";
import type {
  Strategy,
  PlanHistoryItem,
  PlanBranchNode,
  ExecutionPlan,
  ExecutionPlanStep,
  ClawhubPlanSuggestion,
  RagConfig,
} from "@/app/components/modalTypes";

type ChatRole = "user" | "assistant";

type ChatMessage = {
  role: ChatRole;
  content: string;
  traceId?: string;
};

type ExecutionMode = "auto_exec" | "user_exec";

type PendingPlan = {
  requestId: string;
  query: string;
  mode: Strategy;
  reusedFromPlanRecord?: boolean;
  planRecordPath?: string;
  intentDescription: string;
  thinking: string;
  searchEvidence: Array<{ title: string; url: string }>;
  lines: string[];
  recommendedSkills: string[];
  missingSkills: string[];
  installRequired: boolean;
  requiredSkills: string[];
  taskChecklist: ExecutionChecklistItem[];
  executionMode: ExecutionMode;
  clawhubSuggestions?: ClawhubPlanSuggestion[];
  executionPlan?: ExecutionPlan;
};

type CapabilityAgent = {
  id: string;
  label: string;
  description: string;
  source?: string | { type?: string; path?: string };
};

type CapabilitySkill = {
  id: string;
  name: string;
  source: string;
  installed: boolean;
  whitelisted?: boolean;
  manifest?: {
    toolId: string;
    riskLevel?: string;
    source?: string;
    permissions?: string[];
    inputSchema?: Record<string, unknown>;
    outputSchema?: Record<string, unknown>;
  };
};

type CapabilityTool = {
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
  requiredUserInputs?: Array<{
    key: string;
    label: string;
    type?: "text" | "password" | "textarea";
    required?: boolean;
    secret?: boolean;
    placeholder?: string;
  }>;
};

type FlowSource = {
  title: string;
  mode: Strategy;
  lines: string[];
  skills: string[];
};

type FolderAuthorization = {
  path: string;
  permission: string;
};

type StepExecutionConfig = {
  agent: string;
  skills: string[];
  tools: string[];
};

type ExecutionChecklistItem = {
  id: string;
  text: string;
  done: boolean;
};

type StepRunState = "pending" | "running" | "success" | "failed";

type DeepSeekConfig = {
  enabled: boolean;
  apiKey: string;
  baseUrl: string;
  model: string;
};

type RagDocument = {
  documentId: string;
  scope: string;
  title: string;
  source?: string;
  tags?: string[];
  content?: string;
  chunks?: Array<{ chunkId: string; chunkIndex: number; content: string }>;
  updatedAt?: string;
};

type RagGraph = {
  nodes: Array<{ id: string; type: string; label: string; meta: Record<string, unknown> }>;
  edges: Array<{ id: string; source: string; target: string }>;
};

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";
const PLAN_HISTORY_KEY = "aichatflow.planHistory.v1";
const PLAN_EXPANDED_KEY = "aichatflow.planExpanded.v1";
const DEEPSEEK_CONFIG_KEY = "aichatflow.deepseek.config.v1";

function newRequestId() {
  return `req_${Math.random().toString(16).slice(2)}_${Date.now()}`;
}

function dedupeAgentsById(items: CapabilityAgent[]): CapabilityAgent[] {
  const seen = new Set<string>();
  const result: CapabilityAgent[] = [];
  for (const item of items) {
    const id = String(item.id || "").trim();
    if (!id || seen.has(id)) continue;
    seen.add(id);
    result.push(item);
  }
  return result;
}

function normalizeClawhubSuggestions(raw: unknown): ClawhubPlanSuggestion[] {
  if (!Array.isArray(raw)) return [];
  const levels = new Set(["low", "medium", "high"]);
  const recs = new Set(["adopt", "review", "avoid"]);
  const out: ClawhubPlanSuggestion[] = [];
  for (const x of raw) {
    if (!x || typeof x !== "object") continue;
    const o = x as Record<string, unknown>;
    const slug = String(o.slug ?? "").trim();
    if (!slug) continue;
    const rl = String(o.riskLevel ?? "low");
    const rc = String(o.recommendation ?? "review");
    const item: ClawhubPlanSuggestion = {
      slug,
      name: String(o.name ?? slug),
      summary: String(o.summary ?? ""),
      riskLevel: (levels.has(rl) ? rl : "low") as ClawhubPlanSuggestion["riskLevel"],
      recommendation: (recs.has(rc) ? rc : "review") as ClawhubPlanSuggestion["recommendation"],
      analysis: String(o.analysis ?? ""),
      userSelected: Boolean(o.userSelected),
    };
    if (typeof o.score === "number") item.score = o.score;
    out.push(item);
  }
  return out;
}

function normalizeExecutionPlan(raw: unknown, fallbackLines: string[], mode: Strategy): ExecutionPlan {
  const fallback: ExecutionPlan = {
    planId: `plan_local_${Date.now()}`,
    mode,
    steps: fallbackLines
      .filter((x) => x.trim().length > 0)
      .map((line, idx) => ({
        id: `s${idx + 1}`,
        type: "llm",
        action: line,
        input: { text: line },
        dependsOn: idx > 0 ? [`s${idx}`] : [],
        agent: mode,
        skills: [],
      })),
  };
  if (!raw || typeof raw !== "object") return fallback;
  const o = raw as Record<string, unknown>;
  const modeRaw = String(o.mode ?? mode);
  const validMode: Strategy = ["auto", "agent", "react", "workflow"].includes(modeRaw)
    ? (modeRaw as Strategy)
    : mode;
  const rawSteps = Array.isArray(o.steps) ? o.steps : [];
  const steps: ExecutionPlanStep[] = rawSteps.flatMap((x, idx) => {
    if (!x || typeof x !== "object") return [];
    const s = x as Record<string, unknown>;
    const action = String(s.action ?? "").trim();
    if (!action) return [];
    const step: ExecutionPlanStep = {
      id: String(s.id ?? `s${idx + 1}`),
      type: String(s.type ?? "llm"),
      action,
      input: s.input && typeof s.input === "object" ? (s.input as Record<string, unknown>) : undefined,
      dependsOn: Array.isArray(s.dependsOn) ? s.dependsOn.map((d) => String(d)) : undefined,
      agent: s.agent ? String(s.agent) : undefined,
      skills: Array.isArray(s.skills) ? s.skills.map((k) => String(k)) : undefined,
      outputSchema:
        s.outputSchema && typeof s.outputSchema === "object"
          ? (s.outputSchema as Record<string, unknown>)
          : undefined,
    };
    return [step];
  });
  return {
    planId: String(o.planId ?? `plan_local_${Date.now()}`),
    mode: validMode,
    steps: steps.length > 0 ? steps : fallback.steps,
  };
}

export default function Home() {
  const [tenantId, setTenantId] = useState("tenant-a");
  const [strategy, setStrategy] = useState<Strategy>("auto");
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [canResumeChatAction, setCanResumeChatAction] = useState(false);
  const [resumeChatActionLabel, setResumeChatActionLabel] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pendingPlan, setPendingPlan] = useState<PendingPlan | null>(null);
  const [planSupplement, setPlanSupplement] = useState("");
  const [planBranches, setPlanBranches] = useState<Record<number, PlanBranchNode[]>>({});
  const [selectedPlanBranch, setSelectedPlanBranch] = useState<Record<number, Record<string, string>>>({});
  const [planBranchInput, setPlanBranchInput] = useState<Record<string, string>>({});
  const [stepExecutionConfigs, setStepExecutionConfigs] = useState<Record<number, StepExecutionConfig>>({});
  const [stepToolInputs, setStepToolInputs] = useState<Record<number, Record<string, Record<string, string>>>>({});
  const [executionChecklist, setExecutionChecklist] = useState<ExecutionChecklistItem[]>([]);
  const [executionStepStates, setExecutionStepStates] = useState<Record<string, StepRunState>>({});
  const [stepApprovals, setStepApprovals] = useState<Record<string, boolean>>({});
  const [pendingApprovalStepId, setPendingApprovalStepId] = useState<string | null>(null);
  const [activeTraceId, setActiveTraceId] = useState<string | null>(null);
  const [planFolderAuths, setPlanFolderAuths] = useState<FolderAuthorization[]>([]);
  const [planFolderPathInput, setPlanFolderPathInput] = useState("");
  const [planFolderPermInput, setPlanFolderPermInput] = useState("777");
  const [planHistory, setPlanHistory] = useState<PlanHistoryItem[]>([]);
  const [expandedCategories, setExpandedCategories] = useState<Record<Strategy, boolean>>({
    auto: true,
    agent: true,
    react: true,
    workflow: true,
  });
  const [autoInstallMissing, setAutoInstallMissing] = useState(true);
  const [confirmedSkills, setConfirmedSkills] = useState<string[]>([]);
  const [capabilityOpen, setCapabilityOpen] = useState(false);
  const [capabilityTab, setCapabilityTab] = useState<"existing" | "add">("existing");
  const [capabilityQuery, setCapabilityQuery] = useState("");
  const [capabilityAgents, setCapabilityAgents] = useState<CapabilityAgent[]>([]);
  const [capabilitySkills, setCapabilitySkills] = useState<CapabilitySkill[]>([]);
  const [capabilityTools, setCapabilityTools] = useState<CapabilityTool[]>([]);
  const [capabilityLoading, setCapabilityLoading] = useState(false);
  const [capabilityInstallingSkillId, setCapabilityInstallingSkillId] = useState<string | null>(null);
  const [capabilityTogglingWhitelistSkillId, setCapabilityTogglingWhitelistSkillId] = useState<string | null>(null);
  const [capabilityTogglingToolPolicyKey, setCapabilityTogglingToolPolicyKey] = useState<string | null>(null);
  const [capabilityWhitelist, setCapabilityWhitelist] = useState<string[]>([]);
  const [personalSkillRootPath, setPersonalSkillRootPath] = useState("");
  const [personalSkillPathInput, setPersonalSkillPathInput] = useState("");
  const [personalSkillItems, setPersonalSkillItems] = useState<Array<{ type: "dir" | "md"; path: string }>>([]);
  const [personalSkillTreeLoading, setPersonalSkillTreeLoading] = useState(false);
  const [personalSkillPathSaving, setPersonalSkillPathSaving] = useState(false);
  const [capabilityPage, setCapabilityPage] = useState(1);
  const [capabilityPageSize] = useState(8);
  const [capabilitySkillsTotal, setCapabilitySkillsTotal] = useState(0);
  const [onlineQuery, setOnlineQuery] = useState("");
  const [onlineSkills, setOnlineSkills] = useState<CapabilitySkill[]>([]);
  const [onlineSkillsLoading, setOnlineSkillsLoading] = useState(false);
  const [onlineAddingSkillId, setOnlineAddingSkillId] = useState<string | null>(null);
  const [customAgents, setCustomAgents] = useState<CapabilityAgent[]>([]);
  const [customAgentCreating, setCustomAgentCreating] = useState(false);
  const [customAgentDeletingId, setCustomAgentDeletingId] = useState<string | null>(null);
  const [flowOpen, setFlowOpen] = useState(false);
  const [flowEditable, setFlowEditable] = useState(true);
  const [flowTitle, setFlowTitle] = useState("");
  const [flowNodes, setFlowNodes, onFlowNodesChange] = useNodesState<Node>([]);
  const [flowEdges, setFlowEdges, onFlowEdgesChange] = useEdgesState<Edge>([]);
  const [flowSkills, setFlowSkills] = useState<string[]>([]);
  const [flowSkillInput, setFlowSkillInput] = useState("");
  const [flowFolderAuths, setFlowFolderAuths] = useState<FolderAuthorization[]>([]);
  const [flowFolderPathInput, setFlowFolderPathInput] = useState("");
  const [flowFolderPermInput, setFlowFolderPermInput] = useState("777");
  const [planRecordOpen, setPlanRecordOpen] = useState(false);
  const [planRecordSearch, setPlanRecordSearch] = useState("");
  const [selectedPlanRecord, setSelectedPlanRecord] = useState<PlanHistoryItem | null>(null);
  const [traceOpen, setTraceOpen] = useState(false);
  const [traceLoading, setTraceLoading] = useState(false);
  const [traceError, setTraceError] = useState<string | null>(null);
  const [traceViewerId, setTraceViewerId] = useState<string | null>(null);
  const [traceViewerIds, setTraceViewerIds] = useState<string[]>([]);
  const [traceViewerRun, setTraceViewerRun] = useState<Record<string, unknown> | null>(null);
  const [deepseekOpen, setDeepseekOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [toolPlaygroundOpen, setToolPlaygroundOpen] = useState(false);
  const [toolPlaygroundToolId, setToolPlaygroundToolId] = useState("");
  const [toolPlaygroundArgsText, setToolPlaygroundArgsText] = useState("{}");
  const [toolPlaygroundLoading, setToolPlaygroundLoading] = useState(false);
  const [toolPlaygroundResponse, setToolPlaygroundResponse] = useState<Record<string, unknown> | null>(null);
  const [toolPlaygroundError, setToolPlaygroundError] = useState<string | null>(null);
  const [agentPlaygroundOpen, setAgentPlaygroundOpen] = useState(false);
  const [agentPlaygroundAgentId, setAgentPlaygroundAgentId] = useState("");
  const [agentPlaygroundPrompt, setAgentPlaygroundPrompt] = useState("");
  const [agentPlaygroundLoading, setAgentPlaygroundLoading] = useState(false);
  const [agentPlaygroundResponse, setAgentPlaygroundResponse] = useState<Record<string, unknown> | null>(null);
  const [agentPlaygroundError, setAgentPlaygroundError] = useState<string | null>(null);
  const [ragOpen, setRagOpen] = useState(false);
  const [ragLoading, setRagLoading] = useState(false);
  const [ragError, setRagError] = useState<string | null>(null);
  const [ragScopes, setRagScopes] = useState<string[]>([]);
  const [ragDocuments, setRagDocuments] = useState<RagDocument[]>([]);
  const [ragGraph, setRagGraph] = useState<RagGraph | null>(null);
  const [ragSelectedScope, setRagSelectedScope] = useState("");
  const [ragConfig, setRagConfig] = useState<RagConfig>({
    enabled: false,
    scope: "",
    topK: 5,
  });
  const [deepseekConfig, setDeepseekConfig] = useState<DeepSeekConfig>({
    enabled: false,
    apiKey: "",
    baseUrl: "https://api.deepseek.com/v1",
    model: "deepseek-chat",
  });
  const chatAbortControllerRef = useRef<AbortController | null>(null);
  const resumableChatActionRef = useRef<null | (() => Promise<void>)>(null);

  function beginChatAction(label: string, resumeAction: () => Promise<void>) {
    chatAbortControllerRef.current?.abort();
    chatAbortControllerRef.current = new AbortController();
    resumableChatActionRef.current = resumeAction;
    setCanResumeChatAction(false);
    setResumeChatActionLabel(label);
    return chatAbortControllerRef.current;
  }

  function finishChatAction() {
    chatAbortControllerRef.current = null;
  }

  function stopChatAction() {
    if (!chatAbortControllerRef.current) return;
    chatAbortControllerRef.current.abort();
    chatAbortControllerRef.current = null;
    setCanResumeChatAction(true);
    setMessages((prev) => [...prev, { role: "assistant", content: "当前请求已停止。可点击 Resume 重新发起。" }]);
  }

  async function resumeChatAction() {
    if (!resumableChatActionRef.current || loading) return;
    setMessages((prev) => [
      ...prev,
      { role: "assistant", content: `恢复动作：${resumeChatActionLabel ?? "上一次请求"}（将重新开始）` },
    ]);
    await resumableChatActionRef.current();
  }

  function newChat() {
    chatAbortControllerRef.current?.abort();
    chatAbortControllerRef.current = null;
    resumableChatActionRef.current = null;
    setCanResumeChatAction(false);
    setResumeChatActionLabel(null);
    setMessages([]);
    setPendingPlan(null);
    setPlanSupplement("");
    setPlanBranches({});
    setSelectedPlanBranch({});
    setPlanBranchInput({});
    setStepExecutionConfigs({});
    setStepToolInputs({});
    setExecutionChecklist([]);
    setExecutionStepStates({});
    setStepApprovals({});
    setPendingApprovalStepId(null);
    setInput("");
    setError(null);
    setConfirmedSkills([]);
    setPlanFolderAuths([]);
    setPlanFolderPathInput("");
    setPlanFolderPermInput("777");
  }

  useEffect(() => {
    try {
      const historyRaw = window.localStorage.getItem(PLAN_HISTORY_KEY);
      const expandedRaw = window.localStorage.getItem(PLAN_EXPANDED_KEY);
      if (historyRaw) {
        const parsed = JSON.parse(historyRaw) as Partial<PlanHistoryItem>[];
        if (Array.isArray(parsed)) {
          setPlanHistory(
            parsed.map((item) => ({
              id: item.id ?? `${item.requestId ?? "legacy"}_${Date.now()}`,
              requestId: item.requestId ?? "legacy",
              query: item.query ?? "未命名提问",
              intentDescription: item.intentDescription ?? `用户希望解决：${item.query ?? "未命名提问"}`,
              mode: (item.mode ?? "auto") as Strategy,
              lines: Array.isArray(item.lines) ? item.lines : [],
              recommendedSkills: Array.isArray(item.recommendedSkills) ? item.recommendedSkills : [],
              supplement: item.supplement ?? "",
              savedPath: item.savedPath,
              lastTraceId: typeof item.lastTraceId === "string" ? item.lastTraceId : undefined,
              favorite: Boolean(item.favorite),
              createdAt: item.createdAt ?? new Date().toISOString(),
              executionMode:
                item.executionMode === "user_exec" || item.executionMode === "auto_exec"
                  ? item.executionMode
                  : "auto_exec",
              planBranches:
                item.planBranches && typeof item.planBranches === "object"
                  ? item.planBranches
                  : {},
              selectedPlanBranch:
                item.selectedPlanBranch && typeof item.selectedPlanBranch === "object"
                  ? item.selectedPlanBranch
                  : {},
              stepExecutionConfigs:
                item.stepExecutionConfigs && typeof item.stepExecutionConfigs === "object"
                  ? item.stepExecutionConfigs
                  : {},
              taskChecklist: Array.isArray(item.taskChecklist)
                ? item.taskChecklist
                  .map((x) => {
                    const itemX = x as { id?: string; text?: string; done?: boolean };
                    return {
                      id: String(itemX?.id ?? `legacy_${Math.random().toString(16).slice(2)}`),
                      text: String(itemX?.text ?? ""),
                      done: Boolean(itemX?.done),
                    };
                  })
                  .filter((x) => x.text.trim().length > 0)
                : [],
              clawhubSuggestions: normalizeClawhubSuggestions(item.clawhubSuggestions),
              executionPlan: normalizeExecutionPlan(item.executionPlan, item.lines ?? [], (item.mode ?? "auto") as Strategy),
            }))
          );
        }
      }
      if (expandedRaw) {
        const parsed = JSON.parse(expandedRaw) as Record<Strategy, boolean>;
        if (parsed && typeof parsed === "object") {
          setExpandedCategories((prev) => ({ ...prev, ...parsed }));
        }
      }
    } catch {
      // Ignore malformed local storage values.
    }
  }, []);

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(DEEPSEEK_CONFIG_KEY);
      if (!raw) return;
      const parsed = JSON.parse(raw) as Partial<DeepSeekConfig>;
      setDeepseekConfig((prev) => ({
        ...prev,
        enabled: Boolean(parsed.enabled),
        apiKey: parsed.apiKey ?? prev.apiKey,
        baseUrl: parsed.baseUrl ?? prev.baseUrl,
        model: parsed.model ?? prev.model,
      }));
    } catch {
      // Ignore malformed deepseek config.
    }
  }, []);

  useEffect(() => {
    window.localStorage.setItem(PLAN_HISTORY_KEY, JSON.stringify(planHistory));
  }, [planHistory]);

  useEffect(() => {
    window.localStorage.setItem(PLAN_EXPANDED_KEY, JSON.stringify(expandedCategories));
  }, [expandedCategories]);

  useEffect(() => {
    window.localStorage.setItem(DEEPSEEK_CONFIG_KEY, JSON.stringify(deepseekConfig));
  }, [deepseekConfig]);

  useEffect(() => {
    if (!toolPlaygroundOpen) return;
    const tool = capabilityTools.find((item) => item.id === toolPlaygroundToolId);
    if (!tool) return;
    setToolPlaygroundArgsText(JSON.stringify(tool.exampleArgs ?? {}, null, 2));
    setToolPlaygroundResponse(null);
    setToolPlaygroundError(null);
  }, [capabilityTools, toolPlaygroundOpen, toolPlaygroundToolId]);

  useEffect(() => {
    if (!agentPlaygroundOpen) return;
    if (!agentPlaygroundPrompt.trim()) {
      setAgentPlaygroundPrompt("Write a concise answer that demonstrates this agent's behavior.");
    }
    setAgentPlaygroundResponse(null);
    setAgentPlaygroundError(null);
  }, [agentPlaygroundOpen, agentPlaygroundAgentId]);

  useEffect(() => {
    if (!pendingPlan || loading) return;
    const normalizedLines = pendingPlan.lines.map((x) => x.trim()).filter((x) => x.length > 0);
    if (normalizedLines.length === 0) return;
    const ready = normalizedLines.length === pendingPlan.lines.length;
    if (!ready) return;
    if ((pendingPlan.taskChecklist ?? []).length > 0) return;
    const seededChecklist: ExecutionChecklistItem[] = normalizedLines.map((line, idx) => ({
      id: `task_${pendingPlan.requestId}_${idx}`,
      text: line,
      done: false,
    }));
    setPendingPlan((prev) => {
      if (!prev) return prev;
      return { ...prev, taskChecklist: seededChecklist };
    });
    setPlanHistory((prev) =>
      prev.map((item) =>
        item.requestId === pendingPlan.requestId ? { ...item, taskChecklist: seededChecklist } : item
      )
    );
  }, [pendingPlan, loading]);

  async function loadCapabilities(keyword = "", page = 1) {
    setCapabilityLoading(true);
    try {
      const qPart = keyword ? `q=${encodeURIComponent(keyword)}&` : "";
      const qs = `?${qPart}page=${page}&pageSize=${capabilityPageSize}`;
      const res = await fetch(`${apiBaseUrl}/v1/capabilities${qs}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail ?? "load capabilities failed");
      setCapabilityAgents(Array.isArray(data?.agents) ? data.agents : []);
      setCapabilitySkills(Array.isArray(data?.skills) ? data.skills : []);
      setCapabilityTools(Array.isArray(data?.tools) ? data.tools : []);
      setCapabilityWhitelist(Array.isArray(data?.whitelist) ? data.whitelist.map((x: unknown) => String(x)) : []);
      setCapabilitySkillsTotal(Number(data?.skillsTotal ?? 0));
      setCapabilityPage(Number(data?.page ?? page));
    } finally {
      setCapabilityLoading(false);
    }
  }

  function openToolPlayground(initialToolId?: string) {
    setToolPlaygroundError(null);
    setToolPlaygroundResponse(null);
    const fallbackToolId = initialToolId || capabilityTools[0]?.id || "";
    setToolPlaygroundToolId(fallbackToolId);
    const tool = capabilityTools.find((item) => item.id === fallbackToolId);
    setToolPlaygroundArgsText(JSON.stringify(tool?.exampleArgs ?? {}, null, 2));
    setToolPlaygroundOpen(true);
  }

  function openAgentPlayground(initialAgentId?: string) {
    const availableAgents = dedupeAgentsById([...capabilityAgents, ...customAgents]);
    const fallbackAgentId = initialAgentId || availableAgents[0]?.id || "agent";
    setAgentPlaygroundAgentId(fallbackAgentId);
    setAgentPlaygroundError(null);
    setAgentPlaygroundResponse(null);
    setAgentPlaygroundOpen(true);
  }

  async function invokeToolPlayground() {
    if (!toolPlaygroundToolId) return;
    setToolPlaygroundLoading(true);
    setToolPlaygroundError(null);
    setToolPlaygroundResponse(null);
    try {
      const args = JSON.parse(toolPlaygroundArgsText || "{}");
      const res = await fetch(`${apiBaseUrl}/v1/otie/tools/${encodeURIComponent(toolPlaygroundToolId)}/invoke`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ args }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data?.detail ?? "tool invoke failed");
      setToolPlaygroundResponse(data);
      if (data?.status === "failed" && data?.error?.message) {
        setToolPlaygroundError(String(data.error.message));
      }
    } catch (e: unknown) {
      setToolPlaygroundError(e instanceof Error ? e.message : String(e));
    } finally {
      setToolPlaygroundLoading(false);
    }
  }

  async function invokeAgentPlayground() {
    if (!agentPlaygroundAgentId) return;
    setAgentPlaygroundLoading(true);
    setAgentPlaygroundError(null);
    setAgentPlaygroundResponse(null);
    try {
      const res = await fetch(`${apiBaseUrl}/v1/agents/${encodeURIComponent(agentPlaygroundAgentId)}/invoke`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt: agentPlaygroundPrompt,
          llmConfig:
            deepseekConfig.enabled && deepseekConfig.apiKey.trim()
              ? {
                provider: "deepseek",
                apiKey: deepseekConfig.apiKey.trim(),
                baseUrl: deepseekConfig.baseUrl.trim(),
                model: deepseekConfig.model.trim(),
              }
              : null,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(typeof data?.detail === "string" ? data.detail : "Agent invoke failed");
      }
      setAgentPlaygroundResponse(data);
    } catch (e: unknown) {
      setAgentPlaygroundError(e instanceof Error ? e.message : String(e));
    } finally {
      setAgentPlaygroundLoading(false);
    }
  }

  function buildRagInput() {
    const scope = ragConfig.scope.trim();
    if (!ragConfig.enabled && !scope) return null;
    return {
      enabled: ragConfig.enabled || scope.length > 0,
      scope,
      topK: ragConfig.topK,
    };
  }

  async function loadRagViewer(scope = ragSelectedScope) {
    setRagLoading(true);
    setRagError(null);
    try {
      const scopeQuery = scope.trim();
      const [scopesRes, docsRes, graphRes] = await Promise.all([
        fetch(`${apiBaseUrl}/v1/rag/scopes?tenantId=${encodeURIComponent(tenantId)}`),
        fetch(
          `${apiBaseUrl}/v1/rag/documents?tenantId=${encodeURIComponent(tenantId)}${scopeQuery ? `&scope=${encodeURIComponent(scopeQuery)}` : ""
          }`
        ),
        fetch(
          `${apiBaseUrl}/v1/rag/graph?tenantId=${encodeURIComponent(tenantId)}${scopeQuery ? `&scope=${encodeURIComponent(scopeQuery)}` : ""
          }`
        ),
      ]);
      const scopesData = await scopesRes.json().catch(() => ({}));
      const docsData = await docsRes.json().catch(() => ({}));
      const graphData = await graphRes.json().catch(() => ({}));
      if (!scopesRes.ok) throw new Error(scopesData?.detail ?? "load rag scopes failed");
      if (!docsRes.ok) throw new Error(docsData?.detail ?? "load rag documents failed");
      if (!graphRes.ok) throw new Error(graphData?.detail ?? "load rag graph failed");
      setRagScopes(Array.isArray(scopesData?.items) ? scopesData.items.map((x: unknown) => String(x)) : []);
      setRagDocuments(Array.isArray(docsData?.items) ? (docsData.items as RagDocument[]) : []);
      setRagGraph((graphData?.graph as RagGraph) ?? { nodes: [], edges: [] });
    } catch (e: unknown) {
      setRagError(e instanceof Error ? e.message : String(e));
    } finally {
      setRagLoading(false);
    }
  }

  async function createRagScope(scope: string) {
    const nextScope = scope.trim();
    if (!nextScope) return;
    setRagError(null);
    const previousScopes = ragScopes;
    const scopeAlreadyExists = previousScopes.includes(nextScope);
    if (!scopeAlreadyExists) {
      setRagScopes((prev) => [...prev, nextScope].sort((a, b) => a.localeCompare(b)));
    }
    setRagSelectedScope(nextScope);
    setRagDocuments([]);
    setRagGraph({ nodes: [], edges: [] });
    const res = await fetch(`${apiBaseUrl}/v1/rag/scopes`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        tenantId,
        scope: nextScope,
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const message = data?.detail ?? "create rag scope failed";
      if (!scopeAlreadyExists) {
        setRagScopes(previousScopes);
      }
      setRagSelectedScope("");
      setRagError(message);
      throw new Error(message);
    }
    await loadRagViewer(nextScope);
  }

  async function addRagDocument(payload: {
    scope: string;
    title: string;
    content: string;
    source: string;
    tags: string[];
  }) {
    setRagError(null);
    const res = await fetch(`${apiBaseUrl}/v1/rag/documents`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        tenantId,
        scope: payload.scope,
        title: payload.title,
        content: payload.content,
        source: payload.source,
        tags: payload.tags,
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const message = data?.detail ?? "add rag document failed";
      setRagError(message);
      throw new Error(message);
    }
    const nextScope = payload.scope.trim();
    setRagSelectedScope(nextScope);
    await loadRagViewer(nextScope);
  }

  async function updateRagDocument(payload: {
    documentId: string;
    scope: string;
    title: string;
    content: string;
    source: string;
    tags: string[];
  }) {
    setRagError(null);
    const res = await fetch(`${apiBaseUrl}/v1/rag/documents`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        tenantId,
        documentId: payload.documentId,
        scope: payload.scope,
        title: payload.title,
        content: payload.content,
        source: payload.source,
        tags: payload.tags,
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const message = data?.detail ?? "update rag document failed";
      setRagError(message);
      throw new Error(message);
    }
    setRagSelectedScope(payload.scope.trim());
    await loadRagViewer(payload.scope.trim());
  }

  async function deleteRagDocument(documentId: string) {
    setRagError(null);
    const res = await fetch(
      `${apiBaseUrl}/v1/rag/documents/${encodeURIComponent(documentId)}?tenantId=${encodeURIComponent(tenantId)}`,
      { method: "DELETE" }
    );
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const message = data?.detail ?? "delete rag document failed";
      setRagError(message);
      throw new Error(message);
    }
    await loadRagViewer();
  }

  async function batchIngestRag(payload: {
    scope: string;
    items: Array<{
      scope?: string;
      title?: string;
      content?: string;
      url?: string;
      filePath?: string;
      source?: string;
      tags?: string[];
    }>;
  }) {
    setRagError(null);
    const res = await fetch(`${apiBaseUrl}/v1/rag/documents/batch`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        tenantId,
        scope: payload.scope,
        items: payload.items,
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const message = data?.detail ?? "batch ingest failed";
      setRagError(message);
      throw new Error(message);
    }
    setRagSelectedScope(payload.scope.trim());
    await loadRagViewer(payload.scope.trim());
  }

  async function uploadRagFiles(payload: { scope: string; files: File[]; tags: string[] }) {
    setRagError(null);
    const form = new FormData();
    form.set("tenantId", tenantId);
    form.set("scope", payload.scope);
    form.set("tags", payload.tags.join(","));
    for (const file of payload.files) {
      form.append("files", file, file.name);
    }
    const res = await fetch(`${apiBaseUrl}/v1/rag/documents/upload`, {
      method: "POST",
      body: form,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const message = data?.detail ?? "upload rag files failed";
      setRagError(message);
      throw new Error(message);
    }
    setRagSelectedScope(payload.scope.trim());
    await loadRagViewer(payload.scope.trim());
  }

  async function loadCustomAgents() {
    const res = await fetch(`${apiBaseUrl}/v1/agents`);
    const data = await res.json();
    if (!res.ok) throw new Error(data?.detail ?? "load custom agents failed");
    setCustomAgents(Array.isArray(data?.items) ? data.items : []);
  }

  async function loadPersonalSkillTree() {
    setPersonalSkillTreeLoading(true);
    try {
      const res = await fetch(`${apiBaseUrl}/v1/personal-skills/tree`);
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data?.detail ?? "load personal skill tree failed");
      }
      const rootPath = typeof data?.rootPath === "string" ? data.rootPath : "";
      const items = Array.isArray(data?.items)
        ? data.items
          .map((x: unknown) => {
            const item = x as { type?: string; path?: string };
            return {
              type: item?.type === "dir" ? "dir" : ("md" as "dir" | "md"),
              path: String(item?.path ?? ""),
            };
          })
          .filter((x: { path: string }) => x.path.length > 0)
        : [];
      setPersonalSkillRootPath(rootPath);
      setPersonalSkillPathInput(rootPath || personalSkillPathInput);
      setPersonalSkillItems(items);
    } finally {
      setPersonalSkillTreeLoading(false);
    }
  }

  async function savePersonalSkillPath(pathInput: string) {
    const path = pathInput.trim();
    if (!path) return;
    setPersonalSkillPathSaving(true);
    try {
      const res = await fetch(`${apiBaseUrl}/v1/personal-skills/path`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(data?.detail ?? "save personal skill path failed");
        return;
      }
      setPersonalSkillPathInput(path);
      setPersonalSkillRootPath(typeof data?.rootPath === "string" ? data.rootPath : path);
      setPersonalSkillItems(Array.isArray(data?.items) ? data.items : []);
      setMessages((prev) => [...prev, { role: "assistant", content: "个人技能树路径已更新。" }]);
    } finally {
      setPersonalSkillPathSaving(false);
    }
  }

  async function pickPersonalSkillPath() {
    const picker = (window as Window & { showDirectoryPicker?: () => Promise<{ name?: string }> }).showDirectoryPicker;
    if (!picker) return "";
    try {
      const handle = await picker();
      if (handle?.name) {
        setPersonalSkillPathInput(handle.name);
        return handle.name;
      }
    } catch {
      // User canceled directory picker.
    }
    return "";
  }

  async function installSkill(skillId: string) {
    setCapabilityInstallingSkillId(skillId);
    try {
      const res = await fetch(`${apiBaseUrl}/v1/capabilities/install`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ skillId }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(data?.detail ?? "install failed");
        return;
      }
      setMessages((prev) => [...prev, { role: "assistant", content: data?.message ?? "安装成功" }]);
      await loadCapabilities(capabilityQuery, capabilityPage);
    } finally {
      setCapabilityInstallingSkillId(null);
    }
  }

  async function toggleWhitelist(skillId: string, enabled: boolean) {
    setCapabilityTogglingWhitelistSkillId(skillId);
    try {
      const res = await fetch(`${apiBaseUrl}/v1/capabilities/whitelist`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ skillId, enabled }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(data?.detail ?? "set whitelist failed");
        return;
      }
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: `Whitelist updated: ${data?.skillId} -> ${data?.enabled}` },
      ]);
      await loadCapabilities(capabilityQuery, capabilityPage);
    } finally {
      setCapabilityTogglingWhitelistSkillId(null);
    }
  }

  async function toggleToolPolicy(
    toolId: string,
    field: "allowlisted" | "denylisted",
    enabled: boolean
  ) {
    const actionKey = `${toolId}:${field}`;
    setCapabilityTogglingToolPolicyKey(actionKey);
    try {
      const res = await fetch(`${apiBaseUrl}/v1/capabilities/tools/policy`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ toolId, [field]: enabled }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(data?.detail ?? "set tool policy failed");
        return;
      }
      await loadCapabilities(capabilityQuery, capabilityPage);
    } finally {
      setCapabilityTogglingToolPolicyKey(null);
    }
  }

  async function searchOnlineSkills() {
    setOnlineSkillsLoading(true);
    try {
      const res = await fetch(`${apiBaseUrl}/v1/clawhub/search?q=${encodeURIComponent(onlineQuery)}&limit=25`);
      const data = await res.json();
      if (!res.ok) {
        setError(data?.detail ?? "ClawHub search failed");
        return;
      }
      setOnlineSkills(Array.isArray(data?.items) ? data.items : []);
    } finally {
      setOnlineSkillsLoading(false);
    }
  }

  async function addOnlineSkill(skillId: string) {
    setOnlineAddingSkillId(skillId);
    try {
      const res = await fetch(`${apiBaseUrl}/v1/clawhub/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ slug: skillId }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(data?.detail ?? "add online skill failed");
        return;
      }
      setMessages((prev) => [...prev, { role: "assistant", content: data?.message ?? "已加入列表" }]);
      await loadCapabilities(capabilityQuery, 1);
    } finally {
      setOnlineAddingSkillId(null);
    }
  }

  async function createCustomAgent(payload: { agentId: string; label: string; description: string }) {
    setCustomAgentCreating(true);
    try {
      const res = await fetch(`${apiBaseUrl}/v1/agents`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          agentId: payload.agentId,
          label: payload.label,
          description: payload.description,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(data?.detail ?? "create agent failed");
        return;
      }
      const created = data?.agent as { id?: string; label?: string; description?: string } | undefined;
      const createdId = created?.id ?? payload.agentId;
      const createdLabel = created?.label ?? payload.label ?? createdId;
      const createdDesc = created?.description ?? payload.description ?? "";
      await loadCustomAgents();
      await loadCapabilities(capabilityQuery, capabilityPage);
      setCapabilityOpen(false);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content:
            `已创建自建 Agent: ${createdLabel} (${createdId})\n` +
            (createdDesc ? `描述: ${createdDesc}\n` : "") +
            "初始 Plan:\n" +
            "1. 识别并澄清用户目标\n" +
            "2. 生成可执行步骤与所需 skill\n" +
            "3. 等待用户确认后执行\n\n" +
            "请继续输入你的意图（例如：帮我规划今天上海出行）。",
        },
      ]);
      setInput("");
    } finally {
      setCustomAgentCreating(false);
    }
  }

  async function deleteCustomAgent(agentId: string) {
    setCustomAgentDeletingId(agentId);
    try {
      const res = await fetch(`${apiBaseUrl}/v1/agents/${encodeURIComponent(agentId)}`, { method: "DELETE" });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(data?.detail ?? "delete agent failed");
        return;
      }
      if (data?.status === "success") {
        await loadCustomAgents();
        await loadCapabilities(capabilityQuery, capabilityPage);
      }
    } finally {
      setCustomAgentDeletingId(null);
    }
  }

  async function sendMessageWithContent(content: string, options?: { appendUserMessage?: boolean }) {
    const appendUserMessage = options?.appendUserMessage ?? true;
    if (!content.trim()) return;
    setError(null);
    if (appendUserMessage) {
      const userMsg: ChatMessage = { role: "user", content };
      setMessages((prev) => [...prev, userMsg]);
    }
    setLoading(true);
    const controller = beginChatAction("chat", () => sendMessageWithContent(content, { appendUserMessage: false }));

    try {
      const requestId = newRequestId();
      const rag = buildRagInput();
      const res = await fetch(`${apiBaseUrl}/v1/unified/plan`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: controller.signal,
        body: JSON.stringify({
          requestId,
          tenantId,
          requestType: "chat",
          messages: [{ role: "user", content }],
          inputs: {
            strategy,
            ...(rag ? { rag } : {}),
            llmConfig:
              deepseekConfig.enabled && deepseekConfig.apiKey.trim()
                ? {
                  provider: "deepseek",
                  apiKey: deepseekConfig.apiKey.trim(),
                  baseUrl: deepseekConfig.baseUrl.trim(),
                  model: deepseekConfig.model.trim(),
                }
                : null,
          },
        }),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data?.detail ?? "Request failed");
      }

      const mode = (data?.output?.mode ?? "agent") as Strategy;
      const lines: string[] = Array.isArray(data?.output?.plan)
        ? (data.output.plan as unknown[]).map((x) => String(x))
        : [];
      const recommendedSkills = Array.isArray(data?.output?.recommendedSkills)
        ? data.output.recommendedSkills
        : [];
      const missingSkills = Array.isArray(data?.output?.missingSkills) ? data.output.missingSkills : [];
      const installRequired = Boolean(data?.output?.installRequired);
      const requiredSkills = Array.isArray(data?.output?.requiredSkills) ? data.output.requiredSkills : [];
      const executionMode: ExecutionMode =
        data?.output?.executionMode === "user_exec" ? "user_exec" : "auto_exec";
      const intentDescription =
        typeof data?.output?.intentDescription === "string" && data.output.intentDescription.trim()
          ? data.output.intentDescription.trim()
          : `用户希望解决：${content}`;
      const thinking =
        typeof data?.output?.thinking === "string" ? data.output.thinking : "";
      const searchEvidence = Array.isArray(data?.output?.searchEvidence)
        ? data.output.searchEvidence
          .map((x: unknown) => {
            const item = x as { title?: string; url?: string };
            return {
              title: String(item?.title ?? "").trim(),
              url: String(item?.url ?? "").trim(),
            };
          })
          .filter((x: { title: string; url: string }) => x.title && x.url.startsWith("https://"))
        : [];
      const clawhubSuggestions = normalizeClawhubSuggestions(data?.output?.clawhubPlanSuggestions);
      const executionPlan = normalizeExecutionPlan(data?.output?.executionPlan, lines, mode);
      const reusedFromPlanRecord = Boolean(data?.output?.reusedFromPlanRecord);
      const planRecordPath =
        typeof data?.output?.planRecordPath === "string" && data.output.planRecordPath.trim()
          ? data.output.planRecordPath.trim()
          : undefined;
      setPendingPlan({
        requestId,
        query: content,
        mode,
        reusedFromPlanRecord,
        planRecordPath,
        intentDescription,
        thinking,
        searchEvidence,
        lines,
        recommendedSkills,
        missingSkills,
        installRequired,
        requiredSkills,
        taskChecklist: lines.map((line, idx) => ({
          id: `task_${requestId}_${idx}`,
          text: line,
          done: false,
        })),
        executionMode,
        clawhubSuggestions,
        executionPlan,
      });
      setConfirmedSkills(requiredSkills.length > 0 ? requiredSkills : recommendedSkills);
      setPlanSupplement("");
      setPlanBranches({});
      setSelectedPlanBranch({});
      setPlanBranchInput({});
      const initialStepConfigs: Record<number, StepExecutionConfig> = {};
      lines.forEach((_, idx) => {
        initialStepConfigs[idx] = {
          agent: mode,
          skills: requiredSkills.length > 0 ? [...requiredSkills] : [...recommendedSkills],
          tools: [],
        };
      });
      setStepExecutionConfigs(initialStepConfigs);
      setStepToolInputs({});
      setPlanFolderAuths([]);
      setPlanFolderPathInput("");
      setPlanFolderPermInput("777");
      if (capabilityAgents.length === 0 || capabilitySkills.length === 0) {
        try {
          await loadCapabilities("", 1);
        } catch {
          // Keep plan panel usable even if capability fetch fails.
        }
      }
      const now = new Date().toISOString();
      const historyItem: PlanHistoryItem = {
        id: `${requestId}_${now}`,
        requestId,
        query: content,
        intentDescription,
        mode,
        lines,
        recommendedSkills,
        supplement: "",
        favorite: false,
        createdAt: now,
        executionMode,
        planBranches: {},
        selectedPlanBranch: {},
        stepExecutionConfigs: initialStepConfigs,
        taskChecklist: lines.map((line, idx) => ({
          id: `task_${requestId}_${idx}`,
          text: line,
          done: false,
        })),
        clawhubSuggestions,
        executionPlan,
        savedPath: planRecordPath,
      };
      if (!reusedFromPlanRecord) {
        try {
          const saveRes = await fetch(`${apiBaseUrl}/v1/plan-records/save`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              query: historyItem.query,
              intentDescription: historyItem.intentDescription,
              mode: historyItem.mode,
              planLines: historyItem.lines,
              recommendedSkills: historyItem.recommendedSkills,
              supplement: "",
            }),
          });
          const saveData = await saveRes.json().catch(() => ({}));
          if (saveRes.ok && typeof saveData?.path === "string") {
            historyItem.savedPath = saveData.path;
          }
        } catch {
          // Keep UI usable even when local file save fails.
        }
      }
      setPlanHistory((prev) => [historyItem, ...prev]);
      // Plan is rendered in a dedicated UI panel below.
    } catch (e: unknown) {
      if (e instanceof DOMException && e.name === "AbortError") {
        return;
      }
      const message = e instanceof Error ? e.message : String(e);
      setError(message);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: `Error: ${message}` },
      ]);
    } finally {
      finishChatAction();
      setLoading(false);
    }
  }

  async function sendMessage() {
    const content = input.trim();
    if (!content) return;
    setInput("");
    await sendMessageWithContent(content, { appendUserMessage: true });
  }

  async function confirmAndExecute() {
    if (!pendingPlan) return;
    if (pendingPlan.executionMode === "user_exec") {
      setExecutionChecklist(pendingPlan.taskChecklist);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content:
            "该计划为“用户执行”模式：已生成可勾选 checklist。请按清单执行并在 chat 里反馈进展，我会基于 checklist 继续协助。",
        },
      ]);
      setPlanHistory((prev) =>
        prev.map((item) =>
          item.requestId === pendingPlan.requestId
            ? { ...item, taskChecklist: pendingPlan.taskChecklist, executionMode: pendingPlan.executionMode }
            : item
        )
      );
      setPendingPlan(null);
      return;
    }
    const confirmedPlanLines = buildConfirmedPlanLines(pendingPlan.lines);
    const stepConfigList = pendingPlan.lines.map((_, idx) => ({
      stepIndex: idx,
      step: pendingPlan.lines[idx],
      agent: stepExecutionConfigs[idx]?.agent || pendingPlan.mode,
      skills: stepExecutionConfigs[idx]?.skills || [],
      tools: stepExecutionConfigs[idx]?.tools || [],
      toolInputs: stepToolInputs[idx] || {},
    }));
    const selectedClawhubSlugs = (pendingPlan.clawhubSuggestions ?? [])
      .filter((x) => x.userSelected)
      .map((x) => x.slug);
    const mergedConfirmedSkills = Array.from(
      new Set([
        ...stepConfigList.flatMap((x) => x.skills).filter((x) => x.trim().length > 0),
        ...confirmedSkills,
        ...selectedClawhubSlugs,
      ])
    );
    setLoading(true);
    setError(null);
    const seedStepStates: Record<string, StepRunState> = {};
    const epSteps = pendingPlan.executionPlan?.steps ?? [];
    if (epSteps.length > 0) {
      epSteps.forEach((s) => {
        seedStepStates[s.id] = "pending";
      });
    } else {
      pendingPlan.lines.forEach((_, i) => {
        seedStepStates[`s${i + 1}`] = "pending";
      });
    }
    setExecutionStepStates(seedStepStates);
    setActiveTraceId(null);
    setExecutionChecklist(
      confirmedPlanLines.map((line, idx) => ({
        id: `exec_${Date.now()}_${idx}`,
        text: line,
        done: false,
      }))
    );
    let blockedExecution = false;
    let capturedTraceId: string | null = null;
    const historyRequestId = pendingPlan.requestId;
    const resumePendingPlan = pendingPlan;
    const controller = beginChatAction("execution", async () => {
      setPendingPlan(resumePendingPlan);
      await confirmAndExecute();
    });
    try {
      const res = await fetch(`${apiBaseUrl}/v1/unified/execute/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: controller.signal,
        body: JSON.stringify({
          requestId: pendingPlan.requestId,
          tenantId,
          requestType: "chat",
          messages: [{ role: "user", content: pendingPlan.query }],
          inputs: {
            strategy,
            confirmed: true,
            confirmedPlan: confirmedPlanLines,
            executionPlan: pendingPlan.executionPlan,
            planSupplement,
            missingSkills: pendingPlan.missingSkills,
            autoInstallMissing,
            confirmedSkills: mergedConfirmedSkills.length > 0 ? mergedConfirmedSkills : confirmedSkills,
            stepExecutions: stepConfigList,
            taskChecklist: pendingPlan.taskChecklist,
            executionMode: pendingPlan.executionMode,
            stepApprovals,
            folderAuthorizations: planFolderAuths,
            clawhubSelectedSlugs: selectedClawhubSlugs,
            llmConfig:
              deepseekConfig.enabled && deepseekConfig.apiKey.trim()
                ? {
                  provider: "deepseek",
                  apiKey: deepseekConfig.apiKey.trim(),
                  baseUrl: deepseekConfig.baseUrl.trim(),
                  model: deepseekConfig.model.trim(),
                }
                : null,
          },
        }),
      });
      if (!res.ok || !res.body) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data?.detail ?? "Stream request failed");
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const events = buffer.split("\n\n");
        buffer = events.pop() ?? "";
        for (const raw of events) {
          const lines = raw.split("\n");
          const dataLine = lines.find((line) => line.startsWith("data: "));
          if (!dataLine) continue;
          const payload = JSON.parse(dataLine.slice(6)) as {
            type: string;
            message?: string;
            mode?: string;
            content?: string;
            answer?: string;
            blocked?: boolean;
            pendingApprovalStepId?: string;
            skill?: string;
            status?: string;
            stepId?: string;
            stepIndex?: number;
            step?: string;
            summary?: string;
            riskLevel?: string;
            allow?: boolean;
            reason?: string;
            decision?: string;
            trace?: { total?: number; success?: number; failed?: number };
            data?: Array<{ id?: string; name?: string; installed?: boolean }>;
            traceId?: string;
            ok?: boolean;
            error?: string;
          };
          if (payload.type === "trace" && payload.traceId) {
            capturedTraceId = payload.traceId;
            setActiveTraceId(payload.traceId);
          } else if (payload.type === "step_start") {
            if (payload.stepId) setStepRunState(payload.stepId, "running");
          } else if (payload.type === "step_done") {
            if (payload.stepId) setStepRunState(payload.stepId, payload.status === "failed" ? "failed" : "success");
          } else if (payload.type === "approval_required") {
            if (payload.stepId) setStepRunState(payload.stepId, "running");
            if (payload.stepId) setPendingApprovalStepId(payload.stepId);
            setMessages((prev) => [
              ...prev,
              {
                role: "assistant",
                content: `执行已暂停：需要审批步骤 ${payload.stepId ?? ""}。详情请查看 Trace。`,
                traceId: capturedTraceId ?? undefined,
              },
            ]);
          } else if (payload.type === "done") {
            if (payload.blocked) {
              blockedExecution = true;
              setPendingApprovalStepId(payload.pendingApprovalStepId ?? null);
              setMessages((prev) => [
                ...prev,
                {
                  role: "assistant",
                  content: `执行已暂停：等待审批步骤 ${payload.pendingApprovalStepId ?? ""}。详情请查看 Trace。`,
                  traceId: capturedTraceId ?? undefined,
                },
              ]);
            } else {
              setPendingApprovalStepId(null);
              setExecutionChecklist((prev) => prev.map((item) => ({ ...item, done: true })));
              setMessages((prev) => [
                ...prev,
                {
                  role: "assistant",
                  content: `${payload.answer ?? ""}`,
                  traceId: capturedTraceId ?? undefined,
                },
              ]);
              if (capturedTraceId) {
                setPlanHistory((prev) =>
                  prev.map((it) =>
                    it.requestId === historyRequestId ? { ...it, lastTraceId: capturedTraceId! } : it
                  )
                );
              }
            }
          }
        }
      }
      if (!blockedExecution) {
        setPendingPlan(null);
        setPlanSupplement("");
        setPlanBranches({});
        setSelectedPlanBranch({});
        setPlanBranchInput({});
        setStepExecutionConfigs({});
        setStepToolInputs({});
        setExecutionStepStates({});
        setStepApprovals({});
        setActiveTraceId(null);
      }
    } catch (e: unknown) {
      if (e instanceof DOMException && e.name === "AbortError") {
        return;
      }
      const message = e instanceof Error ? e.message : String(e);
      setError(message);
      setMessages((prev) => [...prev, { role: "assistant", content: `Error: ${message}` }]);
    } finally {
      finishChatAction();
      setLoading(false);
    }
  }

  async function executePlanItem(item: PlanHistoryItem) {
    if (item.executionMode === "user_exec") {
      loadHistoryPlan(item);
      setExecutionChecklist(item.taskChecklist ?? []);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content:
            "该计划是“用户执行”模式，不会直接调用 LLM 执行。请先勾选/更新 task checklist，然后点击“按选中 checklist 继续对话”。",
        },
      ]);
      return;
    }
    setLoading(true);
    setError(null);
    const seedStepStates: Record<string, StepRunState> = {};
    (item.executionPlan?.steps ?? []).forEach((s) => {
      seedStepStates[s.id] = "pending";
    });
    setExecutionStepStates(seedStepStates);
    setStrategy(item.mode);
    setExecutionChecklist(
      item.lines.map((line, idx) => ({
        id: `history_${Date.now()}_${idx}`,
        text: line,
        done: false,
      }))
    );
    setMessages((prev) => [...prev, { role: "user", content: item.query }]);
    let capturedTraceId: string | null = item.lastTraceId ?? null;
    let blockedExecution = false;
    const historyRequestId = item.requestId;
    const controller = beginChatAction("history", () => executePlanItem(item));
    try {
      const res = await fetch(`${apiBaseUrl}/v1/unified/execute/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: controller.signal,
        body: JSON.stringify({
          requestId: item.requestId || newRequestId(),
          tenantId,
          requestType: "chat",
          messages: [{ role: "user", content: item.query }],
          inputs: {
            strategy: item.mode,
            confirmed: true,
            confirmedPlan: item.lines,
            executionPlan: item.executionPlan,
            planSupplement: item.supplement ?? "",
            missingSkills: [],
            autoInstallMissing: false,
            confirmedSkills: Array.from(
              new Set([
                ...item.recommendedSkills,
                ...(item.clawhubSuggestions ?? []).filter((x) => x.userSelected).map((x) => x.slug),
              ])
            ),
            clawhubSelectedSlugs: (item.clawhubSuggestions ?? [])
              .filter((x) => x.userSelected)
              .map((x) => x.slug),
            taskChecklist: item.taskChecklist ?? [],
            executionMode: item.executionMode ?? "auto_exec",
            llmConfig:
              deepseekConfig.enabled && deepseekConfig.apiKey.trim()
                ? {
                  provider: "deepseek",
                  apiKey: deepseekConfig.apiKey.trim(),
                  baseUrl: deepseekConfig.baseUrl.trim(),
                  model: deepseekConfig.model.trim(),
                }
                : null,
          },
        }),
      });
      if (!res.ok || !res.body) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data?.detail ?? "Stream request failed");
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const events = buffer.split("\n\n");
        buffer = events.pop() ?? "";
        for (const raw of events) {
          const lines = raw.split("\n");
          const dataLine = lines.find((line) => line.startsWith("data: "));
          if (!dataLine) continue;
          const payload = JSON.parse(dataLine.slice(6)) as {
            type: string;
            answer?: string;
            blocked?: boolean;
            pendingApprovalStepId?: string;
            status?: string;
            stepId?: string;
            reason?: string;
            decision?: string;
            traceId?: string;
          };
          if (payload.type === "trace" && payload.traceId) {
            capturedTraceId = payload.traceId;
            setActiveTraceId(payload.traceId);
          } else if (payload.type === "step_start") {
            if (payload.stepId) setStepRunState(payload.stepId, "running");
          } else if (payload.type === "step_done") {
            if (payload.stepId) setStepRunState(payload.stepId, payload.status === "failed" ? "failed" : "success");
          } else if (payload.type === "approval_required") {
            if (payload.stepId) setStepRunState(payload.stepId, "running");
            if (payload.stepId) setPendingApprovalStepId(payload.stepId);
            setMessages((prev) => [
              ...prev,
              {
                role: "assistant",
                content: `执行已暂停：需要审批步骤 ${payload.stepId ?? ""}。详情请查看 Trace。`,
                traceId: capturedTraceId ?? undefined,
              },
            ]);
          } else if (payload.type === "done") {
            if (payload.blocked) {
              blockedExecution = true;
              setPendingApprovalStepId(payload.pendingApprovalStepId ?? null);
              setMessages((prev) => [
                ...prev,
                {
                  role: "assistant",
                  content: `执行已暂停：等待审批步骤 ${payload.pendingApprovalStepId ?? ""}。详情请查看 Trace。`,
                  traceId: capturedTraceId ?? undefined,
                },
              ]);
            } else {
              setPendingApprovalStepId(null);
              setExecutionChecklist((prev) => prev.map((check) => ({ ...check, done: true })));
              setMessages((prev) => [
                ...prev,
                {
                  role: "assistant",
                  content: `${payload.answer ?? ""}`,
                  traceId: capturedTraceId ?? undefined,
                },
              ]);
              if (capturedTraceId) {
                setPlanHistory((prev) =>
                  prev.map((it) =>
                    it.requestId === historyRequestId ? { ...it, lastTraceId: capturedTraceId! } : it
                  )
                );
              }
            }
          }
        }
      }
    } catch (e: unknown) {
      if (e instanceof DOMException && e.name === "AbortError") {
        return;
      }
      const message = e instanceof Error ? e.message : String(e);
      setError(message);
      setMessages((prev) => [...prev, { role: "assistant", content: `Error: ${message}` }]);
    } finally {
      finishChatAction();
      setLoading(false);
      if (!blockedExecution) {
        setExecutionStepStates({});
      }
    }
  }

  function cancelPlan() {
    setPendingPlan(null);
    setPlanSupplement("");
    setPlanBranches({});
    setSelectedPlanBranch({});
    setPlanBranchInput({});
    setStepExecutionConfigs({});
    setStepToolInputs({});
    setPlanFolderAuths([]);
    setPlanFolderPathInput("");
    setPlanFolderPermInput("777");
    setExecutionChecklist([]);
    setMessages((prev) => [...prev, { role: "assistant", content: "已取消本次计划执行。" }]);
  }

  function updatePlanLine(index: number, value: string) {
    setPendingPlan((prev) => {
      if (!prev) return prev;
      const nextLines = [...prev.lines];
      nextLines[index] = value;
      setPlanHistory((items) =>
        items.map((item) =>
          item.requestId === prev.requestId ? { ...item, lines: nextLines } : item
        )
      );
      return { ...prev, lines: nextLines };
    });
  }

  function toggleFavorite(itemId: string) {
    setPlanHistory((prev) =>
      prev.map((item) => (item.id === itemId ? { ...item, favorite: !item.favorite } : item))
    );
  }

  function deletePlanItem(itemId: string) {
    setPlanHistory((prev) => prev.filter((item) => item.id !== itemId));
  }

  function loadHistoryPlan(item: PlanHistoryItem) {
    setPendingPlan({
      requestId: item.requestId,
      query: item.query,
      mode: item.mode,
      intentDescription: item.intentDescription,
      thinking: "",
      searchEvidence: [],
      lines: [...item.lines],
      recommendedSkills: [...item.recommendedSkills],
      missingSkills: [],
      installRequired: false,
      requiredSkills: [...item.recommendedSkills],
      executionMode: item.executionMode === "user_exec" ? "user_exec" : "auto_exec",
      taskChecklist: Array.isArray(item.taskChecklist)
        ? item.taskChecklist.map((x, idx) => ({
          id: x.id || `history_${item.requestId}_${idx}`,
          text: x.text,
          done: Boolean(x.done),
        }))
        : item.lines.map((line, idx) => ({
          id: `history_${item.requestId}_${idx}`,
          text: line,
          done: false,
        })),
      clawhubSuggestions: normalizeClawhubSuggestions(item.clawhubSuggestions),
      executionPlan: normalizeExecutionPlan(item.executionPlan, item.lines, item.mode),
    });
    setConfirmedSkills([...item.recommendedSkills]);
    setPlanSupplement(item.supplement ?? "");
    setPlanBranches(item.planBranches ?? {});
    setSelectedPlanBranch(item.selectedPlanBranch ?? {});
    setPlanBranchInput({});
    const initialStepConfigs: Record<number, StepExecutionConfig> =
      item.stepExecutionConfigs && Object.keys(item.stepExecutionConfigs).length > 0
        ? Object.fromEntries(
          Object.entries(item.stepExecutionConfigs).map(([key, value]) => [
            Number(key),
            {
              agent: value.agent,
              skills: Array.isArray(value.skills) ? value.skills : [],
              tools: Array.isArray(value.tools) ? value.tools : [],
            },
          ])
        )
        : (() => {
          const fallback: Record<number, StepExecutionConfig> = {};
          item.lines.forEach((_, idx) => {
            fallback[idx] = {
              agent: item.mode,
              skills: [...item.recommendedSkills],
              tools: [],
            };
          });
          return fallback;
        })();
    setStepExecutionConfigs(initialStepConfigs);
    setStepToolInputs({});
    setStrategy(item.mode);
  }

  async function loadTrace(traceId: string) {
    setTraceLoading(true);
    setTraceError(null);
    setTraceViewerId(traceId);
    setTraceViewerRun(null);
    try {
      const otieRes = await fetch(`${apiBaseUrl}/v1/otie/runs/${encodeURIComponent(traceId)}`);
      const otieData = await otieRes.json().catch(() => ({}));
      if (otieRes.ok && otieData?.run) {
        setTraceViewerRun(otieData.run);
        return;
      }

      const traceRes = await fetch(`${apiBaseUrl}/v1/traces/${encodeURIComponent(traceId)}`);
      const traceData = await traceRes.json().catch(() => ({}));
      if (!traceRes.ok) {
        throw new Error(otieData?.detail ?? traceData?.detail ?? "load trace failed");
      }
      setTraceViewerRun({
        traceId,
        runId: traceId,
        status: "legacy-trace",
        finalAnswer: "",
        stepOutputs: {},
        events: Array.isArray(traceData?.events) ? traceData.events : [],
      });
    } catch (err) {
      setTraceError(err instanceof Error ? err.message : "load trace failed");
    } finally {
      setTraceLoading(false);
    }
  }

  async function openTrace(traceId: string, requestId?: string) {
    setTraceOpen(true);
    if (requestId) {
      try {
        const res = await fetch(`${apiBaseUrl}/v1/traces?requestId=${encodeURIComponent(requestId)}`);
        const data = await res.json().catch(() => ({}));
        if (res.ok && Array.isArray(data?.traceIds)) {
          const ids = data.traceIds.map((x: unknown) => String(x)).filter((x: string) => x.trim().length > 0);
          setTraceViewerIds(ids.length > 0 ? ids : [traceId]);
        } else {
          setTraceViewerIds([traceId]);
        }
      } catch {
        setTraceViewerIds([traceId]);
      }
    } else {
      setTraceViewerIds([traceId]);
    }
    await loadTrace(traceId);
  }

  function updatePendingTaskChecklist(checklist: ExecutionChecklistItem[]) {
    setPendingPlan((prev) => {
      if (!prev) return prev;
      return { ...prev, taskChecklist: checklist };
    });
    if (pendingPlan) {
      setPlanHistory((prev) =>
        prev.map((item) =>
          item.requestId === pendingPlan.requestId ? { ...item, taskChecklist: checklist } : item
        )
      );
    }
  }

  function setStepRunState(stepId: string, state: StepRunState) {
    setExecutionStepStates((prev) => ({ ...prev, [stepId]: state }));
  }

  function continueChatWithChecklist() {
    if (!pendingPlan) return;
    const checked = pendingPlan.taskChecklist.filter((x) => x.done);
    const unchecked = pendingPlan.taskChecklist.filter((x) => !x.done);
    const checkedText = checked.length > 0 ? checked.map((x) => `- ${x.text}`).join("\n") : "- 无";
    const uncheckedText = unchecked.length > 0 ? unchecked.map((x) => `- ${x.text}`).join("\n") : "- 无";
    const prompt =
      `基于这个计划继续协助我。\n` +
      `已完成 checklist:\n${checkedText}\n\n` +
      `未完成 checklist:\n${uncheckedText}\n\n` +
      `请给我下一步最优先动作，并说明原因。`;
    setInput(prompt);
    setMessages((prev) => [
      ...prev,
      { role: "assistant", content: "已将选中的 checklist 生成到输入框，点击 Send 继续对话。" },
    ]);
  }

  function updatePlanSupplement(value: string) {
    setPlanSupplement(value);
    if (!pendingPlan) return;
    setPlanHistory((prev) =>
      prev.map((item) =>
        item.requestId === pendingPlan.requestId ? { ...item, supplement: value } : item
      )
    );
  }

  function toggleClawhubSuggestion(slug: string, selected: boolean) {
    setPendingPlan((prev) => {
      if (!prev) return prev;
      const nextSuggestions = (prev.clawhubSuggestions ?? []).map((s) =>
        s.slug === slug ? { ...s, userSelected: selected } : s
      );
      const rid = prev.requestId;
      setPlanHistory((hist) =>
        hist.map((item) =>
          item.requestId === rid ? { ...item, clawhubSuggestions: nextSuggestions } : item
        )
      );
      return { ...prev, clawhubSuggestions: nextSuggestions };
    });
  }

  const filteredPlanRecords = useMemo(() => {
    const q = planRecordSearch.trim().toLowerCase();
    if (!q) return planHistory;
    return planHistory.filter(
      (item) =>
        item.query.toLowerCase().includes(q) ||
        item.intentDescription.toLowerCase().includes(q) ||
        item.mode.toLowerCase().includes(q) ||
        item.recommendedSkills.join(" ").toLowerCase().includes(q)
    );
  }, [planHistory, planRecordSearch]);

  function applyFlowSkills(skills: string[]) {
    const normalized = skills.filter((s) => s.trim().length > 0);
    setFlowSkills(normalized);
    setFlowNodes((prev) =>
      prev.map((node) => {
        if (node.id === "skills-node") {
          return {
            ...node,
            data: {
              ...(node.data || {}),
              skills: normalized,
              editable: flowEditable,
              onAddSkill: (skill: string) => addFlowSkillByNode(skill),
              onRemoveSkill: (skill: string) => removeFlowSkill(skill),
            },
          };
        }
        const label = String(node.data?.label ?? "");
        const updatedLabel = label.replace(
          /skill:\s*.*/i,
          `skill: ${normalized.length > 0 ? normalized.join(", ") : "none"}`
        );
        return { ...node, data: { ...node.data, label: updatedLabel } };
      })
    );
  }

  function buildFlowGraph(source: FlowSource) {
    const nodes: Node[] = source.lines.map((line, idx) => ({
      id: `n-${idx + 1}`,
      position: { x: 80 + idx * 280, y: 120 },
      data: {
        label: `Step ${idx + 1}\n${line}\nagent: ${source.mode}\nskill: ${source.skills.length > 0 ? source.skills.join(", ") : "none"
          }`,
      },
      draggable: true,
      style: {
        color: "#18181b",
        background: "#f4f4f5",
        border: "1px solid #a1a1aa",
        borderRadius: "8px",
        fontSize: "12px",
        whiteSpace: "pre-wrap",
        width: 240,
      },
    }));
    const skillNode: Node = {
      id: "skills-node",
      type: "skillNode",
      position: { x: 80 + Math.max(0, source.lines.length - 1) * 280, y: 320 },
      data: {
        skills: source.skills,
        editable: flowEditable,
        onAddSkill: (skill: string) => addFlowSkillByNode(skill),
        onRemoveSkill: (skill: string) => removeFlowSkill(skill),
      },
      draggable: true,
    };
    const authNode: Node = {
      id: "auth-node",
      position: { x: 80, y: 420 },
      data: {
        label: "Folder Auth\nnone",
      },
      draggable: true,
      style: {
        color: "#18181b",
        background: "#fafafa",
        border: "1px solid #a1a1aa",
        borderRadius: "8px",
        fontSize: "12px",
        whiteSpace: "pre-wrap",
        width: 280,
      },
    };
    const edges: Edge[] = source.lines.slice(1).map((_, idx) => ({
      id: `e-${idx + 1}-${idx + 2}`,
      source: `n-${idx + 1}`,
      target: `n-${idx + 2}`,
      animated: true,
    }));
    if (nodes.length > 0) {
      edges.push({
        id: "e-last-skill",
        source: `n-${nodes.length}`,
        target: "skills-node",
        animated: true,
      });
    }
    edges.push({
      id: "e-skill-auth",
      source: "skills-node",
      target: "auth-node",
      animated: true,
    });
    return { nodes: [...nodes, skillNode, authNode], edges };
  }

  function openTaskFlow(source: FlowSource, editable: boolean) {
    const graph = buildFlowGraph(source);
    setFlowNodes(graph.nodes);
    setFlowEdges(graph.edges);
    setFlowEditable(editable);
    setFlowTitle(source.title);
    setFlowSkills(source.skills);
    setFlowSkillInput("");
    setFlowFolderAuths([]);
    setFlowFolderPathInput("");
    setFlowFolderPermInput("777");
    setFlowOpen(true);
  }

  function onFlowConnect(params: Edge | Connection) {
    if (!flowEditable) return;
    setFlowEdges((eds) => addEdge(params, eds));
  }

  function addFlowSkillByNode(skill: string) {
    const next = skill.trim();
    if (!next) return;
    if (flowSkills.includes(next)) return;
    applyFlowSkills([...flowSkills, next]);
  }

  function addFlowSkill() {
    const next = flowSkillInput.trim();
    if (!next) return;
    addFlowSkillByNode(next);
    setFlowSkillInput("");
  }

  function removeFlowSkill(skill: string) {
    applyFlowSkills(flowSkills.filter((s) => s !== skill));
  }

  function applyFlowFolderAuths(next: FolderAuthorization[]) {
    setFlowFolderAuths(next);
    const label =
      next.length > 0
        ? `Folder Auth\n${next.map((x) => `${x.path} (${x.permission})`).join("\n")}`
        : "Folder Auth\nnone";
    setFlowNodes((prev) =>
      prev.map((node) => {
        if (node.id !== "auth-node") return node;
        return { ...node, data: { ...node.data, label } };
      })
    );
  }

  function normalizePermission(input: string) {
    const value = input.trim();
    if (!/^[0-7]{3}$/.test(value)) return "777";
    return value;
  }

  function newBranchId() {
    return `b_${Math.random().toString(16).slice(2)}_${Date.now()}`;
  }

  function branchInputKey(stepIndex: number, parentId: string | null) {
    return `${stepIndex}:${parentId ?? "__root__"}`;
  }

  function buildConfirmedPlanLines(lines: string[]) {
    const result: string[] = [];
    lines.forEach((line, idx) => {
      result.push(line);
      const nodes: PlanBranchNode[] = planBranches[idx] ?? [];
      const selectedMap: Record<string, string> = selectedPlanBranch[idx] ?? {};
      let parentId: string | null = null;
      while (true) {
        const key: string = parentId ?? "__root__";
        const nextId: string | undefined = selectedMap[key];
        if (!nextId) break;
        const node: PlanBranchNode | undefined = nodes.find((n) => n.id === nextId);
        if (!node) break;
        const text = node.text.trim();
        if (text) result.push(`分支: ${text}`);
        parentId = node.id;
      }
    });
    return result;
  }

  function addPlanBranch(stepIndex: number, parentId: string | null) {
    const key = branchInputKey(stepIndex, parentId);
    const raw = (planBranchInput[key] ?? "").trim();
    if (!raw) return;
    const nextNode: PlanBranchNode = { id: newBranchId(), parentId, text: raw };
    setPlanBranches((prev) => {
      const list = prev[stepIndex] ?? [];
      const next = { ...prev, [stepIndex]: [...list, nextNode] };
      if (pendingPlan) {
        setPlanHistory((items) =>
          items.map((item) =>
            item.requestId === pendingPlan.requestId ? { ...item, planBranches: next } : item
          )
        );
      }
      return next;
    });
    const parentKey = parentId ?? "__root__";
    setSelectedPlanBranch((prev) => {
      const next = {
        ...prev,
        [stepIndex]: { ...(prev[stepIndex] ?? {}), [parentKey]: nextNode.id },
      };
      if (pendingPlan) {
        setPlanHistory((items) =>
          items.map((item) =>
            item.requestId === pendingPlan.requestId ? { ...item, selectedPlanBranch: next } : item
          )
        );
      }
      return next;
    });
    setPlanBranchInput((prev) => ({ ...prev, [key]: "" }));
  }

  function updatePlanBranch(stepIndex: number, branchId: string, value: string) {
    setPlanBranches((prev) => {
      const list = [...(prev[stepIndex] ?? [])];
      const idx = list.findIndex((x) => x.id === branchId);
      if (idx >= 0) {
        list[idx] = { ...list[idx], text: value };
      }
      const next = { ...prev, [stepIndex]: list };
      if (pendingPlan) {
        setPlanHistory((items) =>
          items.map((item) =>
            item.requestId === pendingPlan.requestId ? { ...item, planBranches: next } : item
          )
        );
      }
      return next;
    });
  }

  function removePlanBranch(stepIndex: number, branchId: string) {
    setPlanBranches((prev) => {
      const list = [...(prev[stepIndex] ?? [])];
      const removeSet = new Set<string>([branchId]);
      let changed = true;
      while (changed) {
        changed = false;
        for (const node of list) {
          if (node.parentId && removeSet.has(node.parentId) && !removeSet.has(node.id)) {
            removeSet.add(node.id);
            changed = true;
          }
        }
      }
      const filtered = list.filter((x) => !removeSet.has(x.id));
      const next = { ...prev };
      if (filtered.length === 0) {
        delete next[stepIndex];
      } else {
        next[stepIndex] = filtered;
      }
      if (pendingPlan) {
        setPlanHistory((items) =>
          items.map((item) =>
            item.requestId === pendingPlan.requestId ? { ...item, planBranches: next } : item
          )
        );
      }
      return next;
    });
    setSelectedPlanBranch((prev) => {
      const map = { ...(prev[stepIndex] ?? {}) };
      Object.keys(map).forEach((k) => {
        if (map[k] === branchId) delete map[k];
      });
      const next = { ...prev, [stepIndex]: map };
      if (pendingPlan) {
        setPlanHistory((items) =>
          items.map((item) =>
            item.requestId === pendingPlan.requestId ? { ...item, selectedPlanBranch: next } : item
          )
        );
      }
      return next;
    });
    setPlanBranchInput((prev) => {
      const next = { ...prev };
      Object.keys(next).forEach((k) => {
        if (k.startsWith(`${stepIndex}:${branchId}`)) {
          delete next[k];
        }
      });
      return next;
    });
  }

  function renderBranchEditor(stepIndex: number, parentId: string | null, level: number): ReactElement {
    const nodes = (planBranches[stepIndex] ?? []).filter((x) => x.parentId === parentId);
    const parentKey = parentId ?? "__root__";
    return (
      <div className={level > 0 ? "ml-6 mt-1 space-y-1" : "space-y-1"}>
        {nodes.map((node) => (
          <div key={node.id} className="space-y-1">
            <div className="flex items-center gap-2">
              <input
                type="radio"
                name={`plan-branch-${stepIndex}-${parentKey}`}
                checked={(selectedPlanBranch[stepIndex] ?? {})[parentKey] === node.id}
                onChange={() =>
                  setSelectedPlanBranch((prev) => {
                    const next = {
                      ...prev,
                      [stepIndex]: { ...(prev[stepIndex] ?? {}), [parentKey]: node.id },
                    };
                    if (pendingPlan) {
                      setPlanHistory((items) =>
                        items.map((item) =>
                          item.requestId === pendingPlan.requestId
                            ? { ...item, selectedPlanBranch: next }
                            : item
                        )
                      );
                    }
                    return next;
                  })
                }
              />
              <input
                className="flex-1 border border-zinc-300 dark:border-zinc-700 rounded px-2 py-1 text-xs bg-white dark:bg-zinc-900"
                value={node.text}
                onChange={(e) => updatePlanBranch(stepIndex, node.id, e.target.value)}
              />
              <AppButton type="button" size="xs" variant="danger" onClick={() => removePlanBranch(stepIndex, node.id)}>
                删除
              </AppButton>
            </div>
            {renderBranchEditor(stepIndex, node.id, level + 1)}
          </div>
        ))}
        <div className="flex items-center gap-2">
          <input
            className="flex-1 border border-zinc-300 dark:border-zinc-700 rounded px-2 py-1 text-xs bg-white dark:bg-zinc-900"
            placeholder={level === 0 ? "新增分支，例如：如果基础薄弱先补 JS" : "新增子分支"}
            value={planBranchInput[branchInputKey(stepIndex, parentId)] ?? ""}
            onChange={(e) =>
              setPlanBranchInput((prev) => ({
                ...prev,
                [branchInputKey(stepIndex, parentId)]: e.target.value,
              }))
            }
          />
          <AppButton type="button" size="xs" variant="info" onClick={() => addPlanBranch(stepIndex, parentId)}>
            添加分支
          </AppButton>
        </div>
      </div>
    );
  }

  const whitelistedSkills = useMemo(() => {
    if (capabilityWhitelist.length > 0) return capabilityWhitelist;
    return capabilitySkills.filter((s) => Boolean(s.whitelisted)).map((s) => s.id);
  }, [capabilityWhitelist, capabilitySkills]);

  const allowlistedTools = useMemo(() => {
    const tools = capabilityTools
      .filter((tool) => Boolean(tool.allowlisted) && !tool.denylisted)
      .map((tool) => tool.id);
    if (tools.length > 0) return tools;
    return capabilityTools.filter((tool) => !tool.denylisted).map((tool) => tool.id);
  }, [capabilityTools]);

  function updateStepAgent(stepIndex: number, agentId: string) {
    setStepExecutionConfigs((prev) => {
      const next = {
        ...prev,
        [stepIndex]: {
          agent: agentId,
          skills: prev[stepIndex]?.skills ?? [],
          tools: prev[stepIndex]?.tools ?? [],
        },
      };
      if (pendingPlan) {
        setPlanHistory((items) =>
          items.map((item) =>
            item.requestId === pendingPlan.requestId ? { ...item, stepExecutionConfigs: next } : item
          )
        );
      }
      return next;
    });
  }

  function toggleStepSkill(stepIndex: number, skillId: string, enabled: boolean) {
    setStepExecutionConfigs((prev) => {
      const current = prev[stepIndex] ?? { agent: pendingPlan?.mode ?? "agent", skills: [], tools: [] };
      const nextSkills = enabled
        ? Array.from(new Set([...current.skills, skillId]))
        : current.skills.filter((x) => x !== skillId);
      return {
        ...prev,
        [stepIndex]: { ...current, skills: nextSkills },
      };
    });
    if (pendingPlan) {
      setPlanHistory((items) =>
        items.map((item) => {
          if (item.requestId !== pendingPlan.requestId) return item;
          const current = item.stepExecutionConfigs ?? {};
          const stepCurrent = current[stepIndex] ?? { agent: pendingPlan.mode, skills: [], tools: [] };
          const nextSkills = enabled
            ? Array.from(new Set([...(stepCurrent.skills ?? []), skillId]))
            : (stepCurrent.skills ?? []).filter((x) => x !== skillId);
          return {
            ...item,
            stepExecutionConfigs: {
              ...current,
              [stepIndex]: { ...stepCurrent, skills: nextSkills },
            },
          };
        })
      );
    }
  }

  function toggleStepTool(stepIndex: number, toolId: string, enabled: boolean) {
    setStepExecutionConfigs((prev) => {
      const current = prev[stepIndex] ?? { agent: pendingPlan?.mode ?? "agent", skills: [], tools: [] };
      const nextTools = enabled
        ? Array.from(new Set([...(current.tools ?? []), toolId]))
        : (current.tools ?? []).filter((x) => x !== toolId);
      return {
        ...prev,
        [stepIndex]: { ...current, tools: nextTools },
      };
    });
    if (pendingPlan) {
      setPlanHistory((items) =>
        items.map((item) => {
          if (item.requestId !== pendingPlan.requestId) return item;
          const current = item.stepExecutionConfigs ?? {};
          const stepCurrent = current[stepIndex] ?? { agent: pendingPlan.mode, skills: [], tools: [] };
          const nextTools = enabled
            ? Array.from(new Set([...(stepCurrent.tools ?? []), toolId]))
            : (stepCurrent.tools ?? []).filter((x) => x !== toolId);
          return {
            ...item,
            stepExecutionConfigs: {
              ...current,
              [stepIndex]: { ...stepCurrent, tools: nextTools },
            },
          };
        })
      );
    }
    if (!enabled) {
      setStepToolInputs((prev) => {
        const current = prev[stepIndex] ?? {};
        if (!(toolId in current)) return prev;
        const nextCurrent = { ...current };
        delete nextCurrent[toolId];
        return { ...prev, [stepIndex]: nextCurrent };
      });
    }
  }

  function getToolMeta(toolId: string) {
    return capabilityTools.find((tool) => tool.id === toolId);
  }

  function updateStepToolInput(stepIndex: number, toolId: string, key: string, value: string) {
    setStepToolInputs((prev) => ({
      ...prev,
      [stepIndex]: {
        ...(prev[stepIndex] ?? {}),
        [toolId]: {
          ...((prev[stepIndex] ?? {})[toolId] ?? {}),
          [key]: value,
        },
      },
    }));
  }

  const missingRequiredToolInputs = useMemo(() => {
    const issues: Array<{ stepIndex: number; toolId: string; key: string; label: string }> = [];
    Object.entries(stepExecutionConfigs).forEach(([rawIndex, config]) => {
      const stepIndex = Number(rawIndex);
      const tools = config?.tools ?? [];
      tools.forEach((toolId) => {
        const meta = getToolMeta(toolId);
        const requiredInputs = meta?.requiredUserInputs ?? [];
        requiredInputs.forEach((input) => {
          if (!input.required) return;
          const value = stepToolInputs[stepIndex]?.[toolId]?.[input.key] ?? "";
          if (!String(value).trim()) {
            issues.push({
              stepIndex,
              toolId,
              key: input.key,
              label: input.label || input.key,
            });
          }
        });
      });
    });
    return issues;
  }, [capabilityTools, stepExecutionConfigs, stepToolInputs]);

  const canExecutePendingPlan = !loading && missingRequiredToolInputs.length === 0;

  function requiredInputsForTool(toolId: string) {
    return getToolMeta(toolId)?.requiredUserInputs ?? [];
  }

  function addPlanFolderAuth() {
    const path = planFolderPathInput.trim();
    if (!path) return;
    const permission = normalizePermission(planFolderPermInput);
    const exists = planFolderAuths.some((x) => x.path === path);
    const next = exists
      ? planFolderAuths.map((x) => (x.path === path ? { ...x, permission } : x))
      : [...planFolderAuths, { path, permission }];
    setPlanFolderAuths(next);
    setPlanFolderPermInput(permission);
    setPlanFolderPathInput("");
  }

  function removePlanFolderAuth(path: string) {
    setPlanFolderAuths((prev) => prev.filter((x) => x.path !== path));
  }

  async function pickPlanFolderPath() {
    const picker = (window as Window & { showDirectoryPicker?: () => Promise<{ name?: string }> }).showDirectoryPicker;
    if (!picker) return;
    try {
      const handle = await picker();
      if (handle?.name) {
        setPlanFolderPathInput(handle.name);
      }
    } catch {
      // User canceled directory picker.
    }
  }

  function addFlowFolderAuth() {
    const path = flowFolderPathInput.trim();
    if (!path) return;
    const permission = normalizePermission(flowFolderPermInput);
    const exists = flowFolderAuths.some((x) => x.path === path);
    const next = exists
      ? flowFolderAuths.map((x) => (x.path === path ? { ...x, permission } : x))
      : [...flowFolderAuths, { path, permission }];
    applyFlowFolderAuths(next);
    setFlowFolderPermInput(permission);
    setFlowFolderPathInput("");
  }

  function removeFlowFolderAuth(path: string) {
    applyFlowFolderAuths(flowFolderAuths.filter((x) => x.path !== path));
  }

  async function pickFolderPath() {
    if (!flowEditable) return;
    const picker = (window as Window & { showDirectoryPicker?: () => Promise<{ name?: string }> }).showDirectoryPicker;
    if (!picker) return;
    try {
      const handle = await picker();
      if (handle?.name) {
        setFlowFolderPathInput(handle.name);
      }
    } catch {
      // User canceled directory picker.
    }
  }

  return (
    <div className="min-h-screen bg-zinc-50 dark:bg-black">
      <header className="p-5 border-b border-zinc-200 dark:border-zinc-800">
        <div className="max-w-3xl mx-auto flex justify-between items-center gap-3">
          <div className="font-semibold">Chat UI</div>
          {/* <div className="text-sm text-zinc-500">FastAPI + LangGraph</div> */}
          <div className="flex items-center gap-2">
            <AppButton
              type="button"
              className="ml-auto"
              onClick={async () => {
                try {
                  await loadCapabilities("", 1);
                  await loadCustomAgents();
                  await loadPersonalSkillTree();
                  setCapabilityOpen(true);
                } catch (e: unknown) {
                  setError(e instanceof Error ? e.message : String(e));
                }
              }}
            >
              Agent/Skill
            </AppButton>
            <AppButton type="button" onClick={newChat}>
              New Chat
            </AppButton>
            <AppButton
              type="button"
              onClick={async () => {
                if (capabilityAgents.length === 0) {
                  try {
                    await loadCapabilities("", 1);
                  } catch (e: unknown) {
                    setError(e instanceof Error ? e.message : String(e));
                    return;
                  }
                }
                if (customAgents.length === 0) {
                  try {
                    await loadCustomAgents();
                  } catch (e: unknown) {
                    setError(e instanceof Error ? e.message : String(e));
                    return;
                  }
                }
                openAgentPlayground();
              }}
            >
              Agents
            </AppButton>
            <AppButton
              type="button"
              onClick={async () => {
                if (capabilityTools.length === 0) {
                  try {
                    await loadCapabilities("", 1);
                  } catch (e: unknown) {
                    setError(e instanceof Error ? e.message : String(e));
                    return;
                  }
                }
                openToolPlayground();
              }}
            >
              Tools
            </AppButton>
            <AppButton
              type="button"
              onClick={async () => {
                setRagOpen(true);
                await loadRagViewer();
              }}
            >
              RAG
            </AppButton>
            <AppButton type="button" onClick={() => setSettingsOpen(true)}>
              Settings
            </AppButton>
            <AppButton type="button" onClick={() => setDeepseekOpen(true)}>
              DeepSeek
            </AppButton>
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto p-5 grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-4">
        <aside className="border border-zinc-200 dark:border-zinc-800 rounded bg-white dark:bg-zinc-900 p-3 h-fit">
          <div className="text-sm font-semibold">计划记录</div>
          <div className="text-xs text-zinc-500 mt-1">卡片展示，支持搜索</div>
          <AppButton type="button" size="md" className="mt-3 w-full" onClick={() => setPlanRecordOpen(true)}>
            查看计划记录
          </AppButton>
          <div className="mt-2 text-xs text-zinc-500">共 {planHistory.length} 条</div>
          {(executionChecklist.length > 0 || (pendingPlan?.taskChecklist?.length ?? 0) > 0) ? (
            <div className="mt-4 border-t border-zinc-200 dark:border-zinc-700 pt-3">
              <div className="text-sm font-semibold">执行 Checklist</div>
              <div className="mt-2 space-y-1">
                {(executionChecklist.length > 0 ? executionChecklist : pendingPlan?.taskChecklist ?? []).map((item) => (
                  <label
                    key={item.id}
                    className="text-xs flex items-start gap-2 border border-zinc-200 dark:border-zinc-700 rounded px-2 py-1"
                  >
                    <input
                      type="checkbox"
                      checked={item.done}
                      onChange={(e) =>
                        executionChecklist.length > 0
                          ? setExecutionChecklist((prev) =>
                            prev.map((x) => (x.id === item.id ? { ...x, done: e.target.checked } : x))
                          )
                          : updatePendingTaskChecklist(
                            (pendingPlan?.taskChecklist ?? []).map((x) =>
                              x.id === item.id ? { ...x, done: e.target.checked } : x
                            )
                          )
                      }
                    />
                    <span className={item.done ? "line-through text-zinc-400" : ""}>{item.text}</span>
                  </label>
                ))}
              </div>
            </div>
          ) : null}
          {Object.keys(executionStepStates).length > 0 ? (
            <div className="mt-4 border-t border-zinc-200 dark:border-zinc-700 pt-3">
              <div className="text-sm font-semibold">Step 执行状态</div>
              <div className="mt-2 space-y-1">
                {Object.entries(executionStepStates).map(([sid, st]) => (
                  <div
                    key={sid}
                    className="text-xs border border-zinc-200 dark:border-zinc-700 rounded px-2 py-1 flex items-center justify-between"
                  >
                    <span className="font-mono text-zinc-500">{sid}</span>
                    <span
                      className={
                        st === "running"
                          ? "text-blue-600"
                          : st === "success"
                            ? "text-emerald-600"
                            : st === "failed"
                              ? "text-red-600"
                              : "text-zinc-500"
                      }
                    >
                      {st}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </aside>

        <section className="flex flex-col gap-4">
          <ChatPanel
            messages={messages}
            loading={loading}
            error={error}
            input={input}
            onInputChange={setInput}
            onSend={sendMessage}
            canStop={loading}
            onStop={stopChatAction}
            canResume={canResumeChatAction}
            onResume={resumeChatAction}
            resumeLabel={resumeChatActionLabel}
            onOpenTrace={openTrace}
          />

          {pendingPlan ? (
            <div className="rounded border border-zinc-300 bg-zinc-50 p-3 dark:border-zinc-700 dark:bg-zinc-900">
              {pendingPlan.reusedFromPlanRecord ? (
                <>
                  <div className="text-sm font-medium text-zinc-800 dark:text-zinc-100">命中历史计划记录</div>
                  <div className="mt-3 border border-zinc-200 dark:border-zinc-700 rounded p-3 bg-white/70 dark:bg-zinc-800">
                    <div className="text-sm font-medium text-zinc-900 dark:text-zinc-100">{pendingPlan.query}</div>
                    <div className="mt-1 text-xs text-zinc-500">mode: {pendingPlan.mode}</div>
                    <div className="mt-2 text-xs text-zinc-700 dark:text-zinc-300 whitespace-pre-wrap">
                      意图：{pendingPlan.intentDescription}
                    </div>
                    <div className="mt-2 space-y-1 text-xs text-zinc-700 dark:text-zinc-300">
                      {pendingPlan.lines.map((line, idx) => (
                        <div key={`reused-plan-${idx}`}>{idx + 1}. {line}</div>
                      ))}
                    </div>
                    <div className="mt-2 text-[11px] text-zinc-500">
                      skill: {pendingPlan.recommendedSkills.length > 0 ? pendingPlan.recommendedSkills.join(", ") : "none"}
                    </div>
                    {pendingPlan.planRecordPath ? (
                      <div className="mt-1 text-[10px] font-mono text-zinc-500 break-all">{pendingPlan.planRecordPath}</div>
                    ) : null}
                  </div>
                  <div className="mt-3 flex items-center gap-2">
                    {missingRequiredToolInputs.length > 0 ? (
                      <div className="text-xs text-zinc-600 dark:text-zinc-300">
                        缺少工具输入：{missingRequiredToolInputs.map((item) => `Step ${item.stepIndex + 1} ${item.toolId}.${item.label}`).join("，")}
                      </div>
                    ) : null}
                  </div>
                  <div className="mt-3 flex items-center gap-2">
                    {pendingPlan.executionMode === "user_exec" ? (
                      <AppButton type="button" size="md" variant="info" onClick={continueChatWithChecklist}>
                        按选中 checklist 继续对话
                      </AppButton>
                    ) : (
                      <AppButton type="button" size="md" variant="success" onClick={() => void confirmAndExecute()} disabled={!canExecutePendingPlan}>
                        执行
                      </AppButton>
                    )}
                    <AppButton type="button" size="md" onClick={cancelPlan} disabled={loading}>
                      取消
                    </AppButton>
                    <AppButton
                      type="button"
                      onClick={() =>
                        openTaskFlow(
                          {
                            title: `${pendingPlan.query} (查看)`,
                            mode: pendingPlan.mode,
                            lines: buildConfirmedPlanLines(pendingPlan.lines),
                            skills: pendingPlan.recommendedSkills,
                          },
                          false
                        )
                      }
                      size="md"
                      variant="info"
                    >
                      查看 Flow
                    </AppButton>
                  </div>
                </>
              ) : (
                <>
                  <div className="text-sm font-medium text-zinc-800 dark:text-zinc-100">
                    执行计划待确认（mode: {pendingPlan.mode}）
                  </div>
                  <div className="mt-2 flex items-center gap-2">
                    <div className="text-xs text-zinc-500">执行模式</div>
                    <select
                      className="border border-zinc-300 dark:border-zinc-700 rounded px-2 py-1 text-xs bg-white dark:bg-zinc-900"
                      value={pendingPlan.executionMode}
                      onChange={(e) =>
                        setPendingPlan((prev) =>
                          prev
                            ? {
                              ...prev,
                              executionMode: e.target.value === "user_exec" ? "user_exec" : "auto_exec",
                            }
                            : prev
                        )
                      }
                    >
                      <option value="auto_exec">系统自动执行（exec + test）</option>
                      <option value="user_exec">用户自行执行（仅输出 checklist）</option>
                    </select>
                  </div>
                  <div className="mt-1 text-xs text-zinc-600 dark:text-zinc-400">
                    用户问题：{pendingPlan.query}
                  </div>
                  <div className="mt-2 text-xs text-zinc-700 dark:text-zinc-300 whitespace-pre-wrap">
                    意图：{pendingPlan.intentDescription}
                  </div>
                  {pendingPlan.thinking ? (
                    <div className="mt-2 text-xs text-zinc-600 dark:text-zinc-400 whitespace-pre-wrap">
                      思考：{pendingPlan.thinking}
                    </div>
                  ) : null}
                  {pendingPlan.searchEvidence.length > 0 ? (
                    <div className="mt-2">
                      <div className="text-xs text-zinc-500 mb-1">检索依据</div>
                      <div className="space-y-1">
                        {pendingPlan.searchEvidence.map((item, idx) => (
                          <a
                            key={`${item.url}-${idx}`}
                            href={item.url}
                            target="_blank"
                            rel="noreferrer"
                            className="block text-xs text-zinc-700 hover:underline dark:text-zinc-300"
                          >
                            {idx + 1}. {item.title}
                          </a>
                        ))}
                      </div>
                    </div>
                  ) : null}
                  {!loading &&
                    pendingPlan.clawhubSuggestions &&
                    pendingPlan.clawhubSuggestions.length > 0 ? (
                    <div className="mt-3">
                      <div className="text-xs text-zinc-500 mb-2">
                        ClawHub 相关技能（向量检索 + 启发式/LLM 简要分析；<strong>默认不勾选</strong>
                        ，确认执行时仅对你勾选的 slug 注册并纳入技能流）
                      </div>
                      <div className="space-y-2 max-h-64 overflow-y-auto pr-1">
                        {pendingPlan.clawhubSuggestions.map((s) => (
                          <div
                            key={s.slug}
                            className="border border-zinc-200 dark:border-zinc-700 rounded p-2 bg-white/60 dark:bg-zinc-800/80"
                          >
                            <label className="flex items-start gap-2 cursor-pointer">
                              <input
                                type="checkbox"
                                className="mt-1 shrink-0"
                                checked={Boolean(s.userSelected)}
                                onChange={(e) => toggleClawhubSuggestion(s.slug, e.target.checked)}
                              />
                              <div className="flex-1 min-w-0 space-y-1">
                                <div className="flex flex-wrap items-center gap-2">
                                  <span className="text-sm font-medium text-zinc-800 dark:text-zinc-100">{s.name}</span>
                                  <span
                                    className={`text-[10px] px-1.5 py-0.5 rounded ${s.riskLevel === "high"
                                      ? "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-200"
                                      : s.riskLevel === "medium"
                                        ? "bg-zinc-200 text-zinc-900 dark:bg-zinc-700 dark:text-zinc-100"
                                        : "bg-zinc-100 text-zinc-800 dark:bg-zinc-800 dark:text-zinc-100"
                                      }`}
                                  >
                                    risk {s.riskLevel}
                                  </span>
                                  <span
                                    className={`text-[10px] px-1.5 py-0.5 rounded ${s.recommendation === "avoid"
                                      ? "bg-red-50 text-red-700 dark:bg-red-950/50"
                                      : s.recommendation === "review"
                                        ? "bg-zinc-100 text-zinc-800 dark:bg-zinc-800 dark:text-zinc-100"
                                        : "bg-zinc-50 text-zinc-700 dark:bg-zinc-900 dark:text-zinc-200"
                                      }`}
                                  >
                                    {s.recommendation}
                                  </span>
                                </div>
                                <div className="text-[10px] font-mono text-zinc-500 break-all">{s.slug}</div>
                                {s.summary ? (
                                  <div className="text-xs text-zinc-600 dark:text-zinc-400 line-clamp-2">{s.summary}</div>
                                ) : null}
                                <div className="text-xs text-zinc-700 dark:text-zinc-300 whitespace-pre-wrap">{s.analysis}</div>
                                {typeof s.score === "number" ? (
                                  <div className="text-[10px] text-zinc-400">match score {s.score.toFixed(3)}</div>
                                ) : null}
                              </div>
                            </label>
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : null}
                  <div className="mt-2 text-xs text-zinc-600 dark:text-zinc-400">
                    推荐 skills:{" "}
                    {pendingPlan.recommendedSkills.length > 0
                      ? pendingPlan.recommendedSkills.join(", ")
                      : "无"}
                  </div>
                  <div className="mt-1 text-xs text-zinc-600 dark:text-zinc-400">
                    缺失 skills: {pendingPlan.missingSkills.length > 0 ? pendingPlan.missingSkills.join(", ") : "无"}
                  </div>
                  <div className="mt-2">
                    <div className="text-xs text-zinc-500 mb-1">确认要使用的 skills</div>
                    <div className="flex flex-wrap gap-2">
                      {(pendingPlan.requiredSkills.length > 0
                        ? pendingPlan.requiredSkills
                        : pendingPlan.recommendedSkills
                      ).map((sid) => (
                        <label
                          key={sid}
                          className="text-xs flex items-center gap-1 border border-zinc-300 dark:border-zinc-700 rounded px-2 py-1"
                        >
                          <input
                            type="checkbox"
                            checked={confirmedSkills.includes(sid)}
                            onChange={(e) =>
                              setConfirmedSkills((prev) =>
                                e.target.checked
                                  ? Array.from(new Set([...prev, sid]))
                                  : prev.filter((x) => x !== sid)
                              )
                            }
                          />
                          {sid}
                        </label>
                      ))}
                    </div>
                  </div>
                  {activeTraceId ? (
                    <div className="mt-2 text-xs font-mono text-zinc-700 dark:text-zinc-300">
                      traceId: {activeTraceId}
                    </div>
                  ) : null}
                  <div className="mt-3 space-y-2">
                    {pendingPlan.lines.length > 0 ? (
                      pendingPlan.lines.map((line, idx) => {
                        const stepIdForRow = pendingPlan.executionPlan?.steps?.[idx]?.id ?? `s${idx + 1}`;
                        const rowState = executionStepStates[stepIdForRow];
                        return (
                          <div
                            key={`${idx}`}
                            className="text-sm text-zinc-700 dark:text-zinc-200 border border-zinc-200 dark:border-zinc-700 rounded px-3 py-2 bg-white/70 dark:bg-zinc-800"
                          >
                            <div className="flex items-start gap-2">
                              <span className="mt-2 text-xs text-zinc-500">{idx + 1}.</span>
                              {rowState ? (
                                <span
                                  className={`mt-1.5 text-[10px] px-1.5 py-0.5 rounded shrink-0 ${rowState === "running"
                                    ? "bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-200"
                                    : rowState === "success"
                                      ? "bg-emerald-100 text-emerald-900 dark:bg-emerald-900/40 dark:text-emerald-100"
                                      : rowState === "failed"
                                        ? "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-200"
                                        : "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300"
                                    }`}
                                >
                                  {stepIdForRow}:{rowState}
                                </span>
                              ) : null}
                              <input
                                className="flex-1 border border-zinc-300 dark:border-zinc-700 rounded px-2 py-1 bg-white dark:bg-zinc-900"
                                value={line}
                                onChange={(e) => updatePlanLine(idx, e.target.value)}
                              />
                            </div>
                            <div className="mt-2 ml-6">
                              <div className="mb-2 grid grid-cols-1 md:grid-cols-[200px_1fr] gap-2">
                                <label className="text-xs text-zinc-500">
                                  agent
                                  <select
                                    className="mt-1 w-full border border-zinc-300 dark:border-zinc-700 rounded px-2 py-1 text-xs bg-white dark:bg-zinc-900"
                                    value={stepExecutionConfigs[idx]?.agent ?? pendingPlan.mode}
                                    onChange={(e) => updateStepAgent(idx, e.target.value)}
                                  >
                                    {capabilityAgents.length > 0 ? (
                                      capabilityAgents.map((a) => (
                                        <option key={a.id} value={a.id}>
                                          {a.label}
                                        </option>
                                      ))
                                    ) : (
                                      <option value={pendingPlan.mode}>{pendingPlan.mode}</option>
                                    )}
                                  </select>
                                </label>
                                <div>
                                  <div className="text-xs text-zinc-500 mb-1">skills（whitelist）</div>
                                  <div className="flex flex-wrap gap-2">
                                    {(whitelistedSkills.length > 0 ? whitelistedSkills : pendingPlan.requiredSkills).map((sid) => (
                                      <label
                                        key={`${idx}-${sid}`}
                                        className="text-xs flex items-center gap-1 border border-zinc-300 dark:border-zinc-700 rounded px-2 py-1"
                                      >
                                        <input
                                          type="checkbox"
                                          checked={Boolean(stepExecutionConfigs[idx]?.skills?.includes(sid))}
                                          onChange={(e) => toggleStepSkill(idx, sid, e.target.checked)}
                                        />
                                        {sid}
                                      </label>
                                    ))}
                                    {whitelistedSkills.length === 0 && pendingPlan.requiredSkills.length === 0 ? (
                                      <div className="text-xs text-zinc-400">暂无 whitelist skill</div>
                                    ) : null}
                                  </div>
                                </div>
                              </div>
                              <div className="mb-2">
                                <div className="text-xs text-zinc-500 mb-1">tools</div>
                                <div className="flex flex-wrap gap-2">
                                  {allowlistedTools.map((tid) => (
                                    <label
                                      key={`${idx}-tool-${tid}`}
                                      className="text-xs flex items-center gap-1 border border-zinc-300 dark:border-zinc-700 rounded px-2 py-1"
                                    >
                                      <input
                                        type="checkbox"
                                        checked={Boolean(stepExecutionConfigs[idx]?.tools?.includes(tid))}
                                        onChange={(e) => toggleStepTool(idx, tid, e.target.checked)}
                                      />
                                      {tid}
                                    </label>
                                  ))}
                                  {allowlistedTools.length === 0 ? (
                                    <div className="text-xs text-zinc-400">暂无可用 tool</div>
                                  ) : null}
                                </div>
                                {(stepExecutionConfigs[idx]?.tools ?? []).length > 0 ? (
                                  <div className="mt-2 space-y-2">
                                    {(stepExecutionConfigs[idx]?.tools ?? []).map((toolId) => {
                                      const requiredInputs = requiredInputsForTool(toolId);
                                      if (!requiredInputs.length) return null;
                                      return (
                                        <div
                                          key={`${idx}-tool-inputs-${toolId}`}
                                          className="rounded border border-zinc-200 dark:border-zinc-700 px-2 py-2 bg-zinc-50/60 dark:bg-zinc-900/40"
                                        >
                                          <div className="text-[11px] font-medium text-zinc-600 dark:text-zinc-300 mb-2">
                                            {toolId} required inputs
                                          </div>
                                          <div className="space-y-2">
                                            {requiredInputs.map((inputMeta) => {
                                              const value = stepToolInputs[idx]?.[toolId]?.[inputMeta.key] ?? "";
                                              const inputType = inputMeta.secret || inputMeta.type === "password" ? "password" : "text";
                                              return (
                                                <label key={`${toolId}-${inputMeta.key}`} className="block">
                                                  <div className="text-[11px] text-zinc-500 mb-1">
                                                    {inputMeta.label || inputMeta.key}
                                                    {inputMeta.required ? " *" : ""}
                                                  </div>
                                                  {inputMeta.type === "textarea" ? (
                                                    <textarea
                                                      className="w-full min-h-20 border border-zinc-300 dark:border-zinc-700 rounded px-2 py-1 text-xs bg-white dark:bg-zinc-900"
                                                      value={value}
                                                      placeholder={inputMeta.placeholder ?? ""}
                                                      onChange={(e) => updateStepToolInput(idx, toolId, inputMeta.key, e.target.value)}
                                                    />
                                                  ) : (
                                                    <input
                                                      type={inputType}
                                                      className="w-full border border-zinc-300 dark:border-zinc-700 rounded px-2 py-1 text-xs bg-white dark:bg-zinc-900"
                                                      value={value}
                                                      placeholder={inputMeta.placeholder ?? ""}
                                                      onChange={(e) => updateStepToolInput(idx, toolId, inputMeta.key, e.target.value)}
                                                    />
                                                  )}
                                                </label>
                                              );
                                            })}
                                          </div>
                                        </div>
                                      );
                                    })}
                                  </div>
                                ) : null}
                              </div>
                              <div className="text-xs text-zinc-500 mb-1">后续分支</div>
                              {renderBranchEditor(idx, null, 0)}
                            </div>
                          </div>
                        );
                      })
                    ) : (
                      <div className="text-sm text-zinc-500">未返回可展示的计划步骤。</div>
                    )}
                  </div>
                  {!loading &&
                    pendingPlan.lines.length > 0 &&
                    pendingPlan.lines.every((x) => x.trim().length > 0) &&
                    pendingPlan.taskChecklist.length > 0 ? (
                    <div className="mt-3">
                      <div className="text-xs text-zinc-500 mb-1">计划任务 Checklist（可勾选保存）</div>
                      <div className="space-y-1">
                        {pendingPlan.taskChecklist.map((item) => (
                          <label
                            key={item.id}
                            className="text-xs flex items-start gap-2 border border-zinc-300 dark:border-zinc-700 rounded px-2 py-1"
                          >
                            <input
                              type="checkbox"
                              checked={item.done}
                              onChange={(e) =>
                                updatePendingTaskChecklist(
                                  pendingPlan.taskChecklist.map((x) =>
                                    x.id === item.id ? { ...x, done: e.target.checked } : x
                                  )
                                )
                              }
                            />
                            <span className={item.done ? "line-through text-zinc-400" : ""}>{item.text}</span>
                          </label>
                        ))}
                      </div>
                    </div>
                  ) : null}
                  <label className="mt-3 block">
                    <div className="text-xs text-zinc-500 mb-1">补充说明（可选）</div>
                    <textarea
                      className="w-full min-h-20 border border-zinc-300 dark:border-zinc-700 rounded px-3 py-2 bg-white dark:bg-zinc-900 text-sm"
                      placeholder="例如：优先给出上海浦东今天白天逐小时天气，并附出行建议。"
                      value={planSupplement}
                      onChange={(e) => updatePlanSupplement(e.target.value)}
                    />
                  </label>
                  <div className="mt-3">
                    <div className="text-xs text-zinc-500 mb-1">本地文件夹授权（路径 + Linux 权限）</div>
                    <div className="flex items-center gap-2 flex-wrap">
                      <input
                        className="border border-zinc-300 dark:border-zinc-700 rounded px-2 py-1 text-xs w-[320px] bg-white dark:bg-zinc-900"
                        placeholder="/home/user/project"
                        value={planFolderPathInput}
                        onChange={(e) => setPlanFolderPathInput(e.target.value)}
                      />
                      <input
                        className="border border-zinc-300 dark:border-zinc-700 rounded px-2 py-1 text-xs w-20 text-center bg-white dark:bg-zinc-900"
                        placeholder="777"
                        value={planFolderPermInput}
                        onChange={(e) => setPlanFolderPermInput(e.target.value)}
                      />
                      <AppButton type="button" size="xs" onClick={() => void pickPlanFolderPath()}>
                        选择文件夹
                      </AppButton>
                      <AppButton type="button" size="xs" variant="info" onClick={addPlanFolderAuth}>
                        添加授权
                      </AppButton>
                    </div>
                    <div className="mt-2 flex items-center gap-2 flex-wrap">
                      {planFolderAuths.length === 0 ? (
                        <div className="text-xs text-zinc-400">none</div>
                      ) : (
                        planFolderAuths.map((item) => (
                          <div
                            key={`${item.path}-${item.permission}`}
                            className="text-xs border border-zinc-300 dark:border-zinc-700 rounded px-2 py-1 flex items-center gap-1"
                          >
                            <span>{item.path}</span>
                            <span className="text-zinc-500">({item.permission})</span>
                            <AppButton type="button" size="xs" variant="danger" onClick={() => removePlanFolderAuth(item.path)}>
                              x
                            </AppButton>
                          </div>
                        ))
                      )}
                    </div>
                  </div>
                  {pendingPlan.installRequired ? (
                    <label className="mt-2 flex items-center gap-2 text-xs text-zinc-600 dark:text-zinc-300">
                      <input
                        type="checkbox"
                        checked={autoInstallMissing}
                        onChange={(e) => setAutoInstallMissing(e.target.checked)}
                      />
                      确认后自动安装缺失 skills（仅白名单）
                    </label>
                  ) : null}
                  {missingRequiredToolInputs.length > 0 ? (
                    <div className="mt-2 text-xs text-amber-700 dark:text-amber-300">
                      缺少工具输入：{missingRequiredToolInputs.map((item) => `Step ${item.stepIndex + 1} ${item.toolId}.${item.label}`).join("，")}
                    </div>
                  ) : null}
                  <div className="mt-3 flex items-center gap-2">
                    {pendingApprovalStepId ? (
                      <>
                        <AppButton
                          type="button"
                          size="md"
                          variant="info"
                          onClick={() => {
                            setStepApprovals((prev) => ({ ...prev, [pendingApprovalStepId]: true }));
                            void confirmAndExecute();
                          }}
                          disabled={loading}
                        >
                          同意 {pendingApprovalStepId} 并继续执行
                        </AppButton>
                        <AppButton
                          type="button"
                          size="md"
                          variant="danger"
                          onClick={() => {
                            setPendingApprovalStepId(null);
                            setMessages((prev) => [...prev, { role: "assistant", content: `已拒绝步骤 ${pendingApprovalStepId}，执行终止。` }]);
                          }}
                          disabled={loading}
                        >
                          拒绝并终止
                        </AppButton>
                      </>
                    ) : null}
                    {pendingPlan.executionMode === "user_exec" ? (
                      <AppButton type="button" size="md" variant="info" onClick={continueChatWithChecklist}>
                        按选中 checklist 继续对话
                      </AppButton>
                    ) : (
                      <AppButton type="button" size="md" variant="success" onClick={() => void confirmAndExecute()} disabled={!canExecutePendingPlan}>
                        确认执行
                      </AppButton>
                    )}
                    <AppButton type="button" size="md" onClick={cancelPlan} disabled={loading}>
                      取消
                    </AppButton>
                    <AppButton
                      type="button"
                      onClick={() =>
                        openTaskFlow(
                          {
                            title: `${pendingPlan.query} (可编辑)`,
                            mode: pendingPlan.mode,
                            lines: buildConfirmedPlanLines(pendingPlan.lines),
                            skills: pendingPlan.recommendedSkills,
                          },
                          true
                        )
                      }
                      size="md"
                      variant="info"
                    >
                      Task Flow
                    </AppButton>
                  </div>
                </>
              )}
            </div>
          ) : null}

        </section>
      </main>
      <TaskFlowModal
        open={flowOpen}
        title={flowTitle}
        editable={flowEditable}
        nodes={flowNodes}
        edges={flowEdges}
        onClose={() => setFlowOpen(false)}
        onNodesChange={onFlowNodesChange}
        onEdgesChange={onFlowEdgesChange}
        onConnect={onFlowConnect}
        flowSkills={flowSkills}
        flowSkillInput={flowSkillInput}
        setFlowSkillInput={setFlowSkillInput}
        addFlowSkill={addFlowSkill}
        removeFlowSkill={removeFlowSkill}
        flowFolderAuths={flowFolderAuths}
        flowFolderPathInput={flowFolderPathInput}
        setFlowFolderPathInput={setFlowFolderPathInput}
        flowFolderPermInput={flowFolderPermInput}
        setFlowFolderPermInput={setFlowFolderPermInput}
        addFlowFolderAuth={addFlowFolderAuth}
        removeFlowFolderAuth={removeFlowFolderAuth}
        pickFolderPath={pickFolderPath}
      />
      <style jsx global>{`
        .task-flow-modal .react-flow__controls-button {
          background: #f3e2b3;
          color: #7a5a1f;
          border-bottom: 1px solid #d6b36a;
        }
        .task-flow-modal .react-flow__controls-button:hover {
          background: #ead39a;
        }
      `}</style>
      <CapabilityModal
        open={capabilityOpen}
        onClose={() => setCapabilityOpen(false)}
        capabilityTab={capabilityTab}
        setCapabilityTab={setCapabilityTab}
        capabilityQuery={capabilityQuery}
        setCapabilityQuery={setCapabilityQuery}
        loadCapabilities={loadCapabilities}
        capabilityAgents={capabilityAgents}
        capabilitySkills={capabilitySkills}
        capabilityTools={capabilityTools}
        capabilityLoading={capabilityLoading}
        capabilityInstallingSkillId={capabilityInstallingSkillId}
        capabilityTogglingWhitelistSkillId={capabilityTogglingWhitelistSkillId}
        capabilityTogglingToolPolicyKey={capabilityTogglingToolPolicyKey}
        installSkill={installSkill}
        toggleWhitelist={toggleWhitelist}
        toggleToolPolicy={toggleToolPolicy}
        openAgentPlayground={(agentId) => openAgentPlayground(agentId)}
        openToolPlayground={(toolId) => openToolPlayground(toolId)}
        capabilityPage={capabilityPage}
        capabilitySkillsTotal={capabilitySkillsTotal}
        capabilityPageSize={capabilityPageSize}
        onlineQuery={onlineQuery}
        setOnlineQuery={setOnlineQuery}
        onlineSkillsLoading={onlineSkillsLoading}
        searchOnlineSkills={searchOnlineSkills}
        onlineSkills={onlineSkills}
        onlineAddingSkillId={onlineAddingSkillId}
        addOnlineSkill={addOnlineSkill}
        customAgentCreating={customAgentCreating}
        createCustomAgent={createCustomAgent}
        customAgents={customAgents}
        customAgentDeletingId={customAgentDeletingId}
        deleteCustomAgent={deleteCustomAgent}
        personalSkillRootPath={personalSkillRootPath}
        personalSkillPathInput={personalSkillPathInput}
        personalSkillPathSaving={personalSkillPathSaving}
        savePersonalSkillPath={savePersonalSkillPath}
        personalSkillTreeLoading={personalSkillTreeLoading}
        loadPersonalSkillTree={loadPersonalSkillTree}
        pickPersonalSkillPath={pickPersonalSkillPath}
        personalSkillItems={personalSkillItems}
      />
      <DeepseekModal
        open={deepseekOpen}
        onClose={() => setDeepseekOpen(false)}
        deepseekConfig={deepseekConfig}
        setDeepseekConfig={setDeepseekConfig}
      />
      <SettingsModal
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        tenantId={tenantId}
        strategy={strategy}
        setTenantId={setTenantId}
        setStrategy={setStrategy}
        ragConfig={ragConfig}
        setRagConfig={setRagConfig}
        apiBaseUrl={apiBaseUrl}
      />
      <RagViewerModal
        open={ragOpen}
        onClose={() => setRagOpen(false)}
        tenantId={tenantId}
        loading={ragLoading}
        error={ragError}
        selectedScope={ragSelectedScope}
        setSelectedScope={(value) => {
          setRagSelectedScope(value);
          void loadRagViewer(value);
        }}
        scopes={ragScopes}
        documents={ragDocuments}
        graph={ragGraph}
        onRefresh={async () => {
          await loadRagViewer();
        }}
        onCreateScope={createRagScope}
        onAddDocument={addRagDocument}
        onUpdateDocument={updateRagDocument}
        onDeleteDocument={deleteRagDocument}
        onBatchIngest={batchIngestRag}
        onUploadFiles={uploadRagFiles}
      />
      <PlanRecordModal
        open={planRecordOpen}
        onClose={() => setPlanRecordOpen(false)}
        planRecordSearch={planRecordSearch}
        setPlanRecordSearch={setPlanRecordSearch}
        filteredPlanRecords={filteredPlanRecords}
        setSelectedPlanRecord={setSelectedPlanRecord}
        loadHistoryPlan={loadHistoryPlan}
        executePlanItem={executePlanItem}
        openTaskFlow={openTaskFlow}
        openTrace={openTrace}
        toggleFavorite={toggleFavorite}
        deletePlanItem={deletePlanItem}
      />
      <PlanDetailModal
        selectedPlanRecord={selectedPlanRecord}
        setSelectedPlanRecord={setSelectedPlanRecord}
        openTaskFlow={openTaskFlow}
      />
      <TraceModal
        open={traceOpen}
        onClose={() => setTraceOpen(false)}
        loading={traceLoading}
        traceId={traceViewerId}
        traceIds={traceViewerIds}
        onSelectTrace={loadTrace}
        run={traceViewerRun}
        error={traceError}
      />
      <ToolPlaygroundModal
        open={toolPlaygroundOpen}
        onClose={() => setToolPlaygroundOpen(false)}
        tenantId={tenantId}
        ragScopes={ragScopes}
        onOpenRagViewer={() => {
          void loadRagViewer(ragSelectedScope);
          setRagOpen(true);
        }}
        tools={capabilityTools}
        selectedToolId={toolPlaygroundToolId}
        onSelectTool={setToolPlaygroundToolId}
        argsText={toolPlaygroundArgsText}
        setArgsText={setToolPlaygroundArgsText}
        loading={toolPlaygroundLoading}
        response={toolPlaygroundResponse}
        error={toolPlaygroundError}
        onInvoke={invokeToolPlayground}
      />
      <AgentPlaygroundModal
        open={agentPlaygroundOpen}
        onClose={() => setAgentPlaygroundOpen(false)}
        agents={dedupeAgentsById([...capabilityAgents, ...customAgents])}
        selectedAgentId={agentPlaygroundAgentId}
        onSelectAgent={setAgentPlaygroundAgentId}
        prompt={agentPlaygroundPrompt}
        setPrompt={setAgentPlaygroundPrompt}
        loading={agentPlaygroundLoading}
        response={agentPlaygroundResponse}
        error={agentPlaygroundError}
        onInvoke={invokeAgentPlayground}
      />
    </div>
  );
}
