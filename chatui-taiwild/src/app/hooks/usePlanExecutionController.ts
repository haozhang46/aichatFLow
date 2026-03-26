"use client";

import type { Dispatch, SetStateAction } from "react";
import type { ExecutionChecklistItem, PendingPlan, PlanHistoryItem, Strategy } from "@/app/components/modalTypes";
import type { DeepSeekConfig, StepRunState } from "@/app/types/shared";
import { EXECUTION_MODES } from "@/lib/app-enums";
import { buildApiUrl } from "@/lib/api-client";
import type { ChatMessage } from "@/app/hooks/useChatController";

type BeginChatAction = (label: string, resumeAction: () => Promise<void>) => AbortController;

type Params = {
  tenantId: string;
  strategy: Strategy;
  deepseekConfig: DeepSeekConfig;
  autoInstallMissing: boolean;
  beginChatAction: BeginChatAction;
  finishChatAction: () => void;
  setLoading: Dispatch<SetStateAction<boolean>>;
  setError: Dispatch<SetStateAction<string | null>>;
  setMessages: Dispatch<SetStateAction<ChatMessage[]>>;
  setStrategy: Dispatch<SetStateAction<Strategy>>;
  pendingPlan: PendingPlan | null;
  setPendingPlan: Dispatch<SetStateAction<PendingPlan | null>>;
  executionModesByRequestId: Record<string, "auto_exec" | "user_exec">;
  confirmedSkills: string[];
  planSupplement: string;
  stepExecutionConfigs: Record<number, { agent: string; skills: string[]; tools: string[] }>;
  stepToolInputs: Record<number, Record<string, Record<string, string>>>;
  stepApprovals: Record<string, boolean>;
  planFolderAuths: Array<{ path: string; permission: string }>;
  executionChecklist: ExecutionChecklistItem[];
  setExecutionChecklist: Dispatch<SetStateAction<ExecutionChecklistItem[]>>;
  setExecutionStepStates: Dispatch<SetStateAction<Record<string, StepRunState>>>;
  pendingApprovalStepId: string | null;
  setPendingApprovalStepId: Dispatch<SetStateAction<string | null>>;
  setActiveTraceId: Dispatch<SetStateAction<string | null>>;
  setStepApprovals: Dispatch<SetStateAction<Record<string, boolean>>>;
  setStepRunState: (stepId: string, state: StepRunState) => void;
  resetPendingPlanState: () => void;
  buildConfirmedPlanLines: (lines: string[]) => string[];
  loadHistoryPlan: (item: PlanHistoryItem) => void;
  setPlanHistory: Dispatch<SetStateAction<PlanHistoryItem[]>>;
};

function buildLlmConfig(deepseekConfig: DeepSeekConfig) {
  if (!deepseekConfig.enabled || !deepseekConfig.apiKey.trim()) return null;
  return {
    provider: "deepseek",
    apiKey: deepseekConfig.apiKey.trim(),
    baseUrl: deepseekConfig.baseUrl.trim(),
    model: deepseekConfig.model.trim(),
  };
}

async function readExecutionStream(params: {
  res: Response;
  onEvent: (payload: Record<string, unknown>) => void;
}) {
  const reader = params.res.body!.getReader();
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
      params.onEvent(JSON.parse(dataLine.slice(6)) as Record<string, unknown>);
    }
  }
}

export function usePlanExecutionController({
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
  loadHistoryPlan,
  setPlanHistory,
}: Params) {
  async function confirmAndExecute() {
    if (!pendingPlan) return;
    const executionMode = executionModesByRequestId[pendingPlan.requestId] ?? pendingPlan.executionMode;
    if (executionMode === EXECUTION_MODES.USER_EXEC) {
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
          item.requestId === pendingPlan.requestId ? { ...item, taskChecklist: pendingPlan.taskChecklist, executionMode } : item
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
    const selectedClawhubSlugs = (pendingPlan.clawhubSuggestions ?? []).filter((x) => x.userSelected).map((x) => x.slug);
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
    if (epSteps.length > 0) epSteps.forEach((s) => (seedStepStates[s.id] = "pending"));
    else pendingPlan.lines.forEach((_, i) => (seedStepStates[`s${i + 1}`] = "pending"));
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
      const res = await fetch(buildApiUrl("/v1/unified/execute/stream"), {
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
            executionMode,
            stepApprovals,
            folderAuthorizations: planFolderAuths,
            clawhubSelectedSlugs: selectedClawhubSlugs,
            llmConfig: buildLlmConfig(deepseekConfig),
          },
        }),
      });
      if (!res.ok || !res.body) {
        const data = await res.json().catch(() => ({}));
        throw new Error((data as { detail?: string })?.detail ?? "Stream request failed");
      }

      await readExecutionStream({
        res,
        onEvent: (payload) => {
          if (payload.type === "trace" && typeof payload.traceId === "string") {
            capturedTraceId = payload.traceId;
            setActiveTraceId(payload.traceId);
          } else if (payload.type === "step_start" && typeof payload.stepId === "string") {
            setStepRunState(payload.stepId, "running");
          } else if (payload.type === "step_done" && typeof payload.stepId === "string") {
            setStepRunState(payload.stepId, payload.status === "failed" ? "failed" : "success");
          } else if (payload.type === "approval_required" && typeof payload.stepId === "string") {
            setStepRunState(payload.stepId, "running");
            setPendingApprovalStepId(payload.stepId);
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
              setPendingApprovalStepId(typeof payload.pendingApprovalStepId === "string" ? payload.pendingApprovalStepId : null);
              setMessages((prev) => [
                ...prev,
                {
                  role: "assistant",
                  content: `执行已暂停：等待审批步骤 ${String(payload.pendingApprovalStepId ?? "")}。详情请查看 Trace。`,
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
                  content: `${String(payload.answer ?? "")}`,
                  traceId: capturedTraceId ?? undefined,
                },
              ]);
              if (capturedTraceId) {
                setPlanHistory((prev) =>
                  prev.map((it) => (it.requestId === historyRequestId ? { ...it, lastTraceId: capturedTraceId! } : it))
                );
              }
            }
          }
        },
      });

      if (!blockedExecution) {
        resetPendingPlanState();
      }
    } catch (e: unknown) {
      if (e instanceof DOMException && e.name === "AbortError") return;
      const message = e instanceof Error ? e.message : String(e);
      setError(message);
      setMessages((prev) => [...prev, { role: "assistant", content: `Error: ${message}` }]);
    } finally {
      finishChatAction();
      setLoading(false);
    }
  }

  async function executePlanItem(item: PlanHistoryItem) {
    if (item.executionMode === EXECUTION_MODES.USER_EXEC) {
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
      const res = await fetch(buildApiUrl("/v1/unified/execute/stream"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        signal: controller.signal,
        body: JSON.stringify({
          requestId: item.requestId,
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
            clawhubSelectedSlugs: (item.clawhubSuggestions ?? []).filter((x) => x.userSelected).map((x) => x.slug),
            taskChecklist: item.taskChecklist ?? [],
            executionMode: item.executionMode ?? EXECUTION_MODES.AUTO_EXEC,
            llmConfig: buildLlmConfig(deepseekConfig),
          },
        }),
      });
      if (!res.ok || !res.body) {
        const data = await res.json().catch(() => ({}));
        throw new Error((data as { detail?: string })?.detail ?? "Stream request failed");
      }

      await readExecutionStream({
        res,
        onEvent: (payload) => {
          if (payload.type === "trace" && typeof payload.traceId === "string") {
            capturedTraceId = payload.traceId;
            setActiveTraceId(payload.traceId);
          } else if (payload.type === "step_start" && typeof payload.stepId === "string") {
            setStepRunState(payload.stepId, "running");
          } else if (payload.type === "step_done" && typeof payload.stepId === "string") {
            setStepRunState(payload.stepId, payload.status === "failed" ? "failed" : "success");
          } else if (payload.type === "approval_required" && typeof payload.stepId === "string") {
            setStepRunState(payload.stepId, "running");
            setPendingApprovalStepId(payload.stepId);
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
              setPendingApprovalStepId(typeof payload.pendingApprovalStepId === "string" ? payload.pendingApprovalStepId : null);
              setMessages((prev) => [
                ...prev,
                {
                  role: "assistant",
                  content: `执行已暂停：等待审批步骤 ${String(payload.pendingApprovalStepId ?? "")}。详情请查看 Trace。`,
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
                  content: `${String(payload.answer ?? "")}`,
                  traceId: capturedTraceId ?? undefined,
                },
              ]);
              if (capturedTraceId) {
                setPlanHistory((prev) =>
                  prev.map((it) => (it.requestId === historyRequestId ? { ...it, lastTraceId: capturedTraceId! } : it))
                );
              }
            }
          }
        },
      });
    } catch (e: unknown) {
      if (e instanceof DOMException && e.name === "AbortError") return;
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

  function approvePendingStep() {
    if (!pendingApprovalStepId) return Promise.resolve();
    setStepApprovals((prev) => ({ ...prev, [pendingApprovalStepId]: true }));
    return confirmAndExecute();
  }

  function rejectPendingStep() {
    setPendingApprovalStepId(null);
    setMessages((prev) => [
      ...prev,
      { role: "assistant", content: `已拒绝步骤 ${pendingApprovalStepId}，执行终止。` },
    ]);
  }

  return {
    confirmAndExecute,
    executePlanItem,
    approvePendingStep,
    rejectPendingStep,
  };
}
