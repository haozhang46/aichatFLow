"use client";

import { useEffect, useMemo, useState } from "react";
import type {
  CapabilitySkill,
  CapabilityTool,
  ExecutionChecklistItem,
  ExecutionMode,
  PlanBranchNode,
  PlanHistoryItem,
  StepExecutionConfig,
  PendingPlan,
} from "@/app/components/modalTypes";
import type { FolderAuthorization, PlannedChatPayload, StepRunState } from "@/app/types/shared";
import { EXECUTION_MODES } from "@/lib/app-enums";
import { branchInputKey } from "@/lib/plan-branch";
import type { ChatMessage } from "@/app/hooks/useChatController";

type Params = {
  loading: boolean;
  capabilitySkills: CapabilitySkill[];
  capabilityTools: CapabilityTool[];
  capabilityWhitelist: string[];
  executionModesByRequestId: Record<string, ExecutionMode>;
  setExecutionModesByRequestId: React.Dispatch<React.SetStateAction<Record<string, ExecutionMode>>>;
  setPlanHistory: React.Dispatch<React.SetStateAction<PlanHistoryItem[]>>;
  setMessages: React.Dispatch<React.SetStateAction<ChatMessage[]>>;
  setInput: React.Dispatch<React.SetStateAction<string>>;
};

function normalizePermission(input: string) {
  const value = input.trim();
  if (!/^[0-7]{3}$/.test(value)) return "777";
  return value;
}

function newBranchId() {
  return `b_${Math.random().toString(16).slice(2)}_${Date.now()}`;
}

export function usePendingPlanController({
  loading,
  capabilitySkills,
  capabilityTools,
  capabilityWhitelist,
  executionModesByRequestId,
  setExecutionModesByRequestId,
  setPlanHistory,
  setMessages,
  setInput,
}: Params) {
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
  const [confirmedSkills, setConfirmedSkills] = useState<string[]>([]);

  const currentPendingExecutionMode: ExecutionMode = pendingPlan
    ? executionModesByRequestId[pendingPlan.requestId] ?? pendingPlan.executionMode
    : EXECUTION_MODES.AUTO_EXEC;

  useEffect(() => {
    if (!pendingPlan || loading) return;
    const normalizedLines = pendingPlan.lines.map((x) => x.trim()).filter((x) => x.length > 0);
    if (normalizedLines.length === 0) return;
    if (normalizedLines.length !== pendingPlan.lines.length) return;
    if ((pendingPlan.taskChecklist ?? []).length > 0) return;
    const seededChecklist: ExecutionChecklistItem[] = normalizedLines.map((line, idx) => ({
      id: `task_${pendingPlan.requestId}_${idx}`,
      text: line,
      done: false,
    }));
    setPendingPlan((prev) => (prev ? { ...prev, taskChecklist: seededChecklist } : prev));
    setPlanHistory((prev) =>
      prev.map((item) =>
        item.requestId === pendingPlan.requestId ? { ...item, taskChecklist: seededChecklist } : item
      )
    );
  }, [pendingPlan, loading, setPlanHistory]);

  const whitelistedSkills = useMemo(() => {
    if (capabilityWhitelist.length > 0) return capabilityWhitelist;
    return capabilitySkills.filter((s) => Boolean(s.whitelisted)).map((s) => s.id);
  }, [capabilityWhitelist, capabilitySkills]);

  const allowlistedTools = useMemo(() => {
    const tools = capabilityTools.filter((tool) => Boolean(tool.allowlisted) && !tool.denylisted).map((tool) => tool.id);
    if (tools.length > 0) return tools;
    return capabilityTools.filter((tool) => !tool.denylisted).map((tool) => tool.id);
  }, [capabilityTools]);

  function resetPendingPlanState() {
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
    setActiveTraceId(null);
    setConfirmedSkills([]);
    setPlanFolderAuths([]);
    setPlanFolderPathInput("");
    setPlanFolderPermInput("777");
  }

  function handlePlanReady(payload: PlannedChatPayload) {
    const {
      requestId,
      query,
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
      executionMode,
      clawhubSuggestions,
      executionPlan,
      initialStepConfigs,
    } = payload;
    setExecutionModesByRequestId((prev) => ({ ...prev, [requestId]: executionMode }));
    setPendingPlan({
      requestId,
      query,
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
    setStepExecutionConfigs(initialStepConfigs);
    setStepToolInputs({});
    setPlanFolderAuths([]);
    setPlanFolderPathInput("");
    setPlanFolderPermInput("777");
  }

  function loadHistoryPlan(item: PlanHistoryItem) {
    const executionMode =
      item.executionMode === EXECUTION_MODES.USER_EXEC ? EXECUTION_MODES.USER_EXEC : EXECUTION_MODES.AUTO_EXEC;
    setExecutionModesByRequestId((prev) => ({ ...prev, [item.requestId]: executionMode }));
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
      executionMode,
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
      clawhubSuggestions: Array.isArray(item.clawhubSuggestions) ? item.clawhubSuggestions : [],
      executionPlan: item.executionPlan,
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
        : Object.fromEntries(
            item.lines.map((_, idx) => [
              idx,
              { agent: item.mode, skills: [...item.recommendedSkills], tools: [] },
            ])
          );
    setStepExecutionConfigs(initialStepConfigs);
    setStepToolInputs({});
  }

  function updatePendingTaskChecklist(checklist: ExecutionChecklistItem[]) {
    setPendingPlan((prev) => (prev ? { ...prev, taskChecklist: checklist } : prev));
    if (!pendingPlan) return;
    setPlanHistory((prev) =>
      prev.map((item) => (item.requestId === pendingPlan.requestId ? { ...item, taskChecklist: checklist } : item))
    );
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
      prev.map((item) => (item.requestId === pendingPlan.requestId ? { ...item, supplement: value } : item))
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
        hist.map((item) => (item.requestId === rid ? { ...item, clawhubSuggestions: nextSuggestions } : item))
      );
      return { ...prev, clawhubSuggestions: nextSuggestions };
    });
  }

  function updatePlanLine(index: number, value: string) {
    setPendingPlan((prev) => {
      if (!prev) return prev;
      const nextLines = [...prev.lines];
      nextLines[index] = value;
      setPlanHistory((items) =>
        items.map((item) => (item.requestId === prev.requestId ? { ...item, lines: nextLines } : item))
      );
      return { ...prev, lines: nextLines };
    });
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
          items.map((item) => (item.requestId === pendingPlan.requestId ? { ...item, planBranches: next } : item))
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
      if (idx >= 0) list[idx] = { ...list[idx], text: value };
      const next = { ...prev, [stepIndex]: list };
      if (pendingPlan) {
        setPlanHistory((items) =>
          items.map((item) => (item.requestId === pendingPlan.requestId ? { ...item, planBranches: next } : item))
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
      if (filtered.length === 0) delete next[stepIndex];
      else next[stepIndex] = filtered;
      if (pendingPlan) {
        setPlanHistory((items) =>
          items.map((item) => (item.requestId === pendingPlan.requestId ? { ...item, planBranches: next } : item))
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
        if (k.startsWith(`${stepIndex}:${branchId}`)) delete next[k];
      });
      return next;
    });
  }

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
      const nextSkills = enabled ? Array.from(new Set([...current.skills, skillId])) : current.skills.filter((x) => x !== skillId);
      return { ...prev, [stepIndex]: { ...current, skills: nextSkills } };
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
          return { ...item, stepExecutionConfigs: { ...current, [stepIndex]: { ...stepCurrent, skills: nextSkills } } };
        })
      );
    }
  }

  function toggleStepTool(stepIndex: number, toolId: string, enabled: boolean) {
    setStepExecutionConfigs((prev) => {
      const current = prev[stepIndex] ?? { agent: pendingPlan?.mode ?? "agent", skills: [], tools: [] };
      const nextTools = enabled ? Array.from(new Set([...(current.tools ?? []), toolId])) : (current.tools ?? []).filter((x) => x !== toolId);
      return { ...prev, [stepIndex]: { ...current, tools: nextTools } };
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
          return { ...item, stepExecutionConfigs: { ...current, [stepIndex]: { ...stepCurrent, tools: nextTools } } };
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
            issues.push({ stepIndex, toolId, key: input.key, label: input.label || input.key });
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
      if (handle?.name) setPlanFolderPathInput(handle.name);
    } catch {
      // User canceled directory picker.
    }
  }

  function setStepRunState(stepId: string, state: StepRunState) {
    setExecutionStepStates((prev) => ({ ...prev, [stepId]: state }));
  }

  return {
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
  };
}
