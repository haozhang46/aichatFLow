"use client";

import { useEffect, useMemo, useState } from "react";
import TaskFlowModal from "@/components/TaskFlowModal";
import ChatPanel from "@/components/chat/ChatPanel";
import AppButton from "@/components/ui/AppButton";
import CapabilityModal from "@/app/components/CapabilityModal";
import DeepseekModal from "@/app/components/DeepseekModal";
import PendingPlanPanel from "@/app/components/PendingPlanPanel";
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
  RagConfig,
  ExecutionMode,
  CapabilityAgent,
} from "@/app/components/modalTypes";
import { useCapabilityCenter } from "@/app/hooks/useCapabilityCenter";
import { useChatController } from "@/app/hooks/useChatController";
import { usePendingPlanController } from "@/app/hooks/usePendingPlanController";
import { usePlanExecutionController } from "@/app/hooks/usePlanExecutionController";
import { useRagManager } from "@/app/hooks/useRagManager";
import { useTaskFlowController } from "@/app/hooks/useTaskFlowController";
import { useTraceViewer } from "@/app/hooks/useTraceViewer";
import type { DeepSeekConfig } from "@/app/types/shared";
import { apiPost } from "@/lib/api-client";
import { EXECUTION_MODES, STRATEGIES } from "@/lib/app-enums";
import {
  normalizeClawhubSuggestions,
  normalizeExecutionPlan,
  normalizeStoredExecutionMode,
  normalizeStoredTaskChecklist,
} from "@/lib/plan-normalizers";
import {
  DEEPSEEK_CONFIG_KEY,
  PLAN_EXPANDED_KEY,
  PLAN_HISTORY_KEY,
  normalizeStoredPlanHistoryPlainObjects,
} from "@/lib/plan-storage";

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

function stepRunStateClassName(st: string): string {
  switch (st) {
    case "running":
      return "text-blue-600";
    case "success":
      return "text-emerald-600";
    case "failed":
      return "text-red-600";
    default:
      return "text-zinc-500";
  }
}

export default function Home() {
  const [tenantId, setTenantId] = useState("tenant-a");
  const [strategy, setStrategy] = useState<Strategy>(STRATEGIES.AUTO);
  const [executionModesByRequestId, setExecutionModesByRequestId] = useState<Record<string, ExecutionMode>>({});
  const [planHistory, setPlanHistory] = useState<PlanHistoryItem[]>([]);
  const [expandedCategories, setExpandedCategories] = useState<Record<Strategy, boolean>>({
    [STRATEGIES.AUTO]: true,
    [STRATEGIES.AGENT]: true,
    [STRATEGIES.REACT]: true,
    [STRATEGIES.WORKFLOW]: true,
  });
  const [autoInstallMissing, setAutoInstallMissing] = useState(true);
  const [capabilityOpen, setCapabilityOpen] = useState(false);
  const [planRecordOpen, setPlanRecordOpen] = useState(false);
  const [planRecordSearch, setPlanRecordSearch] = useState("");
  const [selectedPlanRecord, setSelectedPlanRecord] = useState<PlanHistoryItem | null>(null);
  const [deepseekOpen, setDeepseekOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [toolPlaygroundOpen, setToolPlaygroundOpen] = useState(false);
  const [toolPlaygroundToolId, setToolPlaygroundToolId] = useState("");
  const [toolPlaygroundArgsText, setToolPlaygroundArgsText] = useState("{}");
  const [toolPlaygroundLoading, setToolPlaygroundLoading] = useState(false);
  const [toolPlaygroundResponse, setToolPlaygroundResponse] = useState<Record<string, unknown> | null>(null);
  const [toolPlaygroundError, setToolPlaygroundError] = useState<string | null>(null);
  const [agentPlaygroundOpen, setAgentPlaygroundOpen] = useState(false);
  const [agentPlaygroundInitialAgentId, setAgentPlaygroundInitialAgentId] = useState("");
  const [ragOpen, setRagOpen] = useState(false);
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
  const {
    loading: ragLoading,
    error: ragError,
    scopes: ragScopes,
    documents: ragDocuments,
    graph: ragGraph,
    selectedScope: ragSelectedScope,
    setSelectedScope: setRagSelectedScope,
    load: loadRagViewer,
    createScope: createRagScope,
    addDocument: addRagDocument,
    updateDocument: updateRagDocument,
    deleteDocument: deleteRagDocument,
    batchIngest: batchIngestRag,
    uploadFiles: uploadRagFiles,
  } = useRagManager({ tenantId });
  const traceViewer = useTraceViewer();
  const flowController = useTaskFlowController();
  const {
    input,
    setInput,
    messages,
    setMessages,
    loading,
    setLoading,
    error,
    setError,
    resumeChatActionLabel,
    canResumeChatAction,
    beginChatAction,
    finishChatAction,
    stopChatAction,
    resumeChatAction,
    sendMessage,
  } = useChatController({
    tenantId,
    strategy,
    deepseekConfig,
    buildRagInput,
    newRequestId,
    ensureCapabilitiesReady: async () => {
      if (capabilityAgents.length === 0 || capabilitySkills.length === 0) {
        try {
          await loadCapabilities("", 1);
        } catch {
          // Keep plan panel usable even if capability fetch fails.
        }
      }
    },
    onPlanReady: async ({
      historyItem,
      reusedFromPlanRecord,
      ...payload
    }) => {
      handlePlanReady({ historyItem, reusedFromPlanRecord, ...payload });
      if (!reusedFromPlanRecord) {
        try {
          const saveData = await apiPost<{ path?: string }>("/v1/plan-records/save", {
            query: historyItem.query,
            intentDescription: historyItem.intentDescription,
            mode: historyItem.mode,
            planLines: historyItem.lines,
            recommendedSkills: historyItem.recommendedSkills,
            supplement: "",
          });
          if (typeof saveData?.path === "string") {
            historyItem.savedPath = saveData.path;
          }
        } catch {
          // Keep UI usable even when local file save fails.
        }
      }
      setPlanHistory((prev) => [historyItem, ...prev]);
    },
  });
  const capabilityCenter = useCapabilityCenter({
    setMessages,
    setInput,
    setError,
  });
  const {
    capabilityTab,
    setCapabilityTab,
    capabilityQuery,
    setCapabilityQuery,
    loadCapabilities,
    capabilityAgents,
    capabilitySkills,
    capabilityTools,
    capabilityLoading,
    capabilityInstallingSkillId,
    capabilityTogglingWhitelistSkillId,
    capabilityTogglingToolPolicyKey,
    installSkill,
    toggleWhitelist,
    toggleToolPolicy,
    capabilityWhitelist,
    capabilityPage,
    capabilitySkillsTotal,
    capabilityPageSize,
    onlineQuery,
    setOnlineQuery,
    onlineSkillsLoading,
    searchOnlineSkills,
    onlineSkills,
    onlineAddingSkillId,
    addOnlineSkill,
    customAgentCreating,
    createCustomAgent,
    customAgents,
    refreshCustomAgents,
    customAgentDeletingId,
    deleteCustomAgent,
    personalSkillRootPath,
    personalSkillPathInput,
    personalSkillPathSaving,
    savePersonalSkillPath,
    personalSkillTreeLoading,
    loadPersonalSkillTree,
    pickPersonalSkillPath,
    personalSkillItems,
  } = capabilityCenter;
  const {
    open: flowOpen,
    close: closeFlow,
    title: flowTitle,
    editable: flowEditable,
    nodes: flowNodes,
    edges: flowEdges,
    onNodesChange: onFlowNodesChange,
    onEdgesChange: onFlowEdgesChange,
    onConnect: onFlowConnect,
    flowSkills,
    flowSkillInput,
    setFlowSkillInput,
    addFlowSkill,
    removeFlowSkill,
    flowFolderAuths,
    flowFolderPathInput,
    setFlowFolderPathInput,
    flowFolderPermInput,
    setFlowFolderPermInput,
    addFlowFolderAuth,
    removeFlowFolderAuth,
    pickFolderPath,
    openTaskFlow,
  } = flowController;
  const pendingPlanController = usePendingPlanController({
    loading,
    capabilitySkills,
    capabilityTools,
    capabilityWhitelist,
    executionModesByRequestId,
    setExecutionModesByRequestId,
    setPlanHistory,
    setMessages,
    setInput,
  });
  const {
    pendingPlan,
    setPendingPlan,
    currentPendingExecutionMode,
    planSupplement,
    stepExecutionConfigs,
    stepToolInputs,
    executionChecklist,
    setExecutionChecklist,
    executionStepStates,
    setExecutionStepStates,
    stepApprovals,
    setStepApprovals,
    pendingApprovalStepId,
    setPendingApprovalStepId,
    activeTraceId,
    setActiveTraceId,
    planFolderAuths,
    planFolderPathInput,
    setPlanFolderPathInput,
    planFolderPermInput,
    setPlanFolderPermInput,
    confirmedSkills,
    setConfirmedSkills,
    whitelistedSkills,
    allowlistedTools,
    missingRequiredToolInputs,
    canExecutePendingPlan,
    planBranches,
    selectedPlanBranch,
    planBranchInput,
    setPlanBranchInput,
    setSelectedPlanBranch,
    handlePlanReady,
    resetPendingPlanState,
    loadHistoryPlan,
    updatePendingTaskChecklist,
    continueChatWithChecklist,
    updatePlanSupplement,
    toggleClawhubSuggestion,
    updatePlanLine,
    buildConfirmedPlanLines,
    addPlanBranch,
    updatePlanBranch,
    removePlanBranch,
    updateStepAgent,
    toggleStepSkill,
    toggleStepTool,
    requiredInputsForTool,
    updateStepToolInput,
    addPlanFolderAuth,
    removePlanFolderAuth,
    pickPlanFolderPath,
    setStepRunState,
  } = pendingPlanController;
  const {
    confirmAndExecute,
    executePlanItem,
    approvePendingStep,
    rejectPendingStep,
  } = usePlanExecutionController({
    tenantId,
    strategy,
    deepseekConfig,
    autoInstallMissing,
    beginChatAction,
    finishChatAction,
    setLoading,
    setError,
    setMessages,
    setStrategy,
    pendingPlan,
    setPendingPlan,
    executionModesByRequestId,
    confirmedSkills,
    planSupplement,
    stepExecutionConfigs,
    stepToolInputs,
    stepApprovals,
    planFolderAuths,
    executionChecklist,
    setExecutionChecklist,
    setExecutionStepStates,
    pendingApprovalStepId,
    setPendingApprovalStepId,
    setActiveTraceId,
    setStepApprovals,
    setStepRunState,
    resetPendingPlanState,
    buildConfirmedPlanLines,
    loadHistoryPlan: handleLoadHistoryPlan,
    setPlanHistory,
  });

  function newChat() {
    stopChatAction();
    setMessages([]);
    resetPendingPlanState();
    setInput("");
    setError(null);
    setExecutionModesByRequestId({});
  }

  function handleLoadHistoryPlan(item: PlanHistoryItem) {
    loadHistoryPlan(item);
    setStrategy(item.mode);
  }

  useEffect(() => {
    try {
      const historyRaw = window.localStorage.getItem(PLAN_HISTORY_KEY);
      const expandedRaw = window.localStorage.getItem(PLAN_EXPANDED_KEY);
      if (historyRaw) {
        const parsed = JSON.parse(historyRaw) as Partial<PlanHistoryItem>[];
        if (Array.isArray(parsed)) {
          const normalized = parsed.map((item) => {
            const mode = (item.mode ?? STRATEGIES.AUTO) as Strategy;
            const lines = Array.isArray(item.lines) ? item.lines : [];
            return {
              id: item.id ?? `${item.requestId ?? "legacy"}_${Date.now()}`,
              requestId: item.requestId ?? "legacy",
              query: item.query ?? "未命名提问",
              intentDescription: item.intentDescription ?? `用户希望解决：${item.query ?? "未命名提问"}`,
              mode,
              lines,
              recommendedSkills: Array.isArray(item.recommendedSkills) ? item.recommendedSkills : [],
              supplement: item.supplement ?? "",
              savedPath: item.savedPath,
              lastTraceId: typeof item.lastTraceId === "string" ? item.lastTraceId : undefined,
              favorite: Boolean(item.favorite),
              createdAt: item.createdAt ?? new Date().toISOString(),
              executionMode: normalizeStoredExecutionMode(item.executionMode),
              ...normalizeStoredPlanHistoryPlainObjects(item),
              taskChecklist: normalizeStoredTaskChecklist(item.taskChecklist),
              clawhubSuggestions: normalizeClawhubSuggestions(item.clawhubSuggestions),
              executionPlan: normalizeExecutionPlan(item.executionPlan, lines, mode),
            };
          });
          setPlanHistory(normalized);
          setExecutionModesByRequestId(
            Object.fromEntries(
              normalized.map((item) => [
                item.requestId,
                item.executionMode === EXECUTION_MODES.USER_EXEC ? EXECUTION_MODES.USER_EXEC : EXECUTION_MODES.AUTO_EXEC,
              ])
            )
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
    setAgentPlaygroundInitialAgentId(fallbackAgentId);
    setAgentPlaygroundOpen(true);
  }

  async function invokeToolPlayground() {
    if (!toolPlaygroundToolId) return;
    setToolPlaygroundLoading(true);
    setToolPlaygroundError(null);
    setToolPlaygroundResponse(null);
    try {
      const args = JSON.parse(toolPlaygroundArgsText || "{}");
      const data = await apiPost<Record<string, unknown>>(
        `/v1/otie/tools/${encodeURIComponent(toolPlaygroundToolId)}/invoke`,
        { args }
      );
      setToolPlaygroundResponse(data);
      const dataObj = data as { status?: unknown; error?: { message?: unknown } };
      if (dataObj?.status === "failed" && dataObj?.error?.message) {
        setToolPlaygroundError(String(dataObj.error.message));
      }
    } catch (e: unknown) {
      setToolPlaygroundError(e instanceof Error ? e.message : String(e));
    } finally {
      setToolPlaygroundLoading(false);
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

  function cancelPlan() {
    resetPendingPlanState();
    setMessages((prev) => [...prev, { role: "assistant", content: "已取消本次计划执行。" }]);
  }

  function toggleFavorite(itemId: string) {
    setPlanHistory((prev) =>
      prev.map((item) => (item.id === itemId ? { ...item, favorite: !item.favorite } : item))
    );
  }

  function deletePlanItem(itemId: string) {
    setPlanHistory((prev) => {
      const target = prev.find((item) => item.id === itemId);
      if (target) {
        setExecutionModesByRequestId((current) => {
          const next = { ...current };
          delete next[target.requestId];
          return next;
        });
      }
      return prev.filter((item) => item.id !== itemId);
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
                  await refreshCustomAgents();
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
                    await refreshCustomAgents();
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
                      className={stepRunStateClassName(st)}
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
            onOpenTrace={traceViewer.openTrace}
          />

          {pendingPlan ? (
            <PendingPlanPanel
              pendingPlan={pendingPlan}
              executionMode={currentPendingExecutionMode}
              loading={loading}
              confirmedSkills={confirmedSkills}
              setConfirmedSkills={setConfirmedSkills}
              missingRequiredToolInputs={missingRequiredToolInputs}
              canExecutePendingPlan={canExecutePendingPlan}
              continueChatWithChecklist={continueChatWithChecklist}
              confirmAndExecute={confirmAndExecute}
              cancelPlan={cancelPlan}
              onOpenViewFlow={() =>
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
              onOpenEditFlow={() =>
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
              onExecutionModeChange={(value) =>
                setExecutionModesByRequestId((prev) =>
                  pendingPlan ? { ...prev, [pendingPlan.requestId]: value } : prev
                )
              }
              toggleClawhubSuggestion={toggleClawhubSuggestion}
              activeTraceId={activeTraceId}
              executionStepStates={executionStepStates}
              updatePlanLine={updatePlanLine}
              capabilityAgents={capabilityAgents}
              stepExecutionConfigs={stepExecutionConfigs}
              updateStepAgent={updateStepAgent}
              whitelistedSkills={whitelistedSkills}
              toggleStepSkill={toggleStepSkill}
              allowlistedTools={allowlistedTools}
              toggleStepTool={toggleStepTool}
              requiredInputsForTool={requiredInputsForTool}
              stepToolInputs={stepToolInputs}
              updateStepToolInput={updateStepToolInput}
              planBranches={planBranches}
              selectedPlanBranch={selectedPlanBranch}
              setSelectedPlanBranch={setSelectedPlanBranch}
              setPlanHistory={setPlanHistory}
              updatePlanBranch={updatePlanBranch}
              removePlanBranch={removePlanBranch}
              planBranchInput={planBranchInput}
              setPlanBranchInput={setPlanBranchInput}
              addPlanBranch={addPlanBranch}
              updatePendingTaskChecklist={updatePendingTaskChecklist}
              planSupplement={planSupplement}
              updatePlanSupplement={updatePlanSupplement}
              planFolderPathInput={planFolderPathInput}
              setPlanFolderPathInput={setPlanFolderPathInput}
              planFolderPermInput={planFolderPermInput}
              setPlanFolderPermInput={setPlanFolderPermInput}
              pickPlanFolderPath={pickPlanFolderPath}
              addPlanFolderAuth={addPlanFolderAuth}
              planFolderAuths={planFolderAuths}
              removePlanFolderAuth={removePlanFolderAuth}
              autoInstallMissing={autoInstallMissing}
              setAutoInstallMissing={setAutoInstallMissing}
              pendingApprovalStepId={pendingApprovalStepId}
              approvePendingStep={approvePendingStep}
              rejectPendingStep={rejectPendingStep}
            />
          ) : null}

        </section>
      </main>
      <TaskFlowModal
        open={flowOpen}
        title={flowTitle}
        editable={flowEditable}
        nodes={flowNodes}
        edges={flowEdges}
        onClose={closeFlow}
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
        createCustomAgent={async (payload) => {
          const created = await createCustomAgent(payload);
          if (created) setCapabilityOpen(false);
        }}
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
        loadHistoryPlan={handleLoadHistoryPlan}
        executePlanItem={executePlanItem}
        openTaskFlow={openTaskFlow}
        openTrace={traceViewer.openTrace}
        toggleFavorite={toggleFavorite}
        deletePlanItem={deletePlanItem}
      />
      <PlanDetailModal
        selectedPlanRecord={selectedPlanRecord}
        setSelectedPlanRecord={setSelectedPlanRecord}
        openTaskFlow={openTaskFlow}
      />
      <TraceModal
        open={traceViewer.open}
        onClose={traceViewer.closeTrace}
        loading={traceViewer.loading}
        traceId={traceViewer.traceId}
        traceIds={traceViewer.traceIds}
        onSelectTrace={traceViewer.loadTrace}
        run={traceViewer.run}
        error={traceViewer.error}
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
        initialAgentId={agentPlaygroundInitialAgentId}
        deepseekConfig={deepseekConfig}
      />
    </div>
  );
}
