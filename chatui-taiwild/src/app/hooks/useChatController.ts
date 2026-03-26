"use client";

import { useRef, useState } from "react";
import type {
  Strategy,
} from "@/app/components/modalTypes";
import type { DeepSeekConfig, PlannedChatPayload } from "@/app/types/shared";
import type { ExecutionMode, PlanHistoryItem, StepExecutionConfig } from "@/app/components/modalTypes";
import { EXECUTION_MODES, STRATEGIES } from "@/lib/app-enums";
import { apiPost } from "@/lib/api-client";
import { normalizeClawhubSuggestions, normalizeExecutionPlan } from "@/lib/plan-normalizers";

export type ChatRole = "user" | "assistant";

export type ChatMessage = {
  role: ChatRole;
  content: string;
  traceId?: string;
};

type Params = {
  tenantId: string;
  strategy: Strategy;
  deepseekConfig: DeepSeekConfig;
  buildRagInput: () => { enabled: boolean; scope: string; topK: number } | null;
  newRequestId: () => string;
  ensureCapabilitiesReady: () => Promise<void>;
  onPlanReady: (payload: PlannedChatPayload) => Promise<void> | void;
};

export function useChatController({
  tenantId,
  strategy,
  deepseekConfig,
  buildRagInput,
  newRequestId,
  ensureCapabilitiesReady,
  onPlanReady,
}: Params) {
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resumeChatActionLabel, setResumeChatActionLabel] = useState<string | null>(null);
  const [canResumeChatAction, setCanResumeChatAction] = useState(false);
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
    setCanResumeChatAction(Boolean(resumableChatActionRef.current));
    setMessages((prev) => [...prev, { role: "assistant", content: "当前请求已停止。可点击 Resume 重新发起。" }]);
    setLoading(false);
  }

  async function resumeChatAction() {
    if (!resumableChatActionRef.current || loading) return;
    setMessages((prev) => [
      ...prev,
      { role: "assistant", content: `恢复动作：${resumeChatActionLabel ?? "上一次请求"}（将重新开始）` },
    ]);
    await resumableChatActionRef.current();
  }

  async function sendMessageWithContent(content: string, options?: { appendUserMessage?: boolean }) {
    const appendUserMessage = options?.appendUserMessage ?? true;
    if (!content.trim()) return;
    setError(null);
    if (appendUserMessage) {
      setMessages((prev) => [...prev, { role: "user", content }]);
    }
    setLoading(true);
    const controller = beginChatAction("chat", () => sendMessageWithContent(content, { appendUserMessage: false }));

    try {
      const requestId = newRequestId();
      const rag = buildRagInput();
      const data = await apiPost<{
        output?: Record<string, unknown>;
      }>(
        "/v1/unified/plan",
        {
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
        },
      );

      const mode = (data?.output?.mode ?? STRATEGIES.AGENT) as Strategy;
      const lines: string[] = Array.isArray(data?.output?.plan)
        ? (data.output.plan as unknown[]).map((x) => String(x))
        : [];
      const recommendedSkills = Array.isArray(data?.output?.recommendedSkills) ? data.output.recommendedSkills : [];
      const missingSkills = Array.isArray(data?.output?.missingSkills) ? data.output.missingSkills : [];
      const installRequired = Boolean(data?.output?.installRequired);
      const requiredSkills = Array.isArray(data?.output?.requiredSkills) ? data.output.requiredSkills : [];
      const executionMode: ExecutionMode =
        data?.output?.executionMode === EXECUTION_MODES.USER_EXEC
          ? EXECUTION_MODES.USER_EXEC
          : EXECUTION_MODES.AUTO_EXEC;
      const intentDescription =
        typeof data?.output?.intentDescription === "string" && data.output.intentDescription.trim()
          ? data.output.intentDescription.trim()
          : `用户希望解决：${content}`;
      const thinking = typeof data?.output?.thinking === "string" ? data.output.thinking : "";
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
      const initialStepConfigs: Record<number, StepExecutionConfig> = {};
      lines.forEach((_, idx) => {
        initialStepConfigs[idx] = {
          agent: mode,
          skills: requiredSkills.length > 0 ? [...requiredSkills] : [...recommendedSkills],
          tools: [],
        };
      });

      await ensureCapabilitiesReady();

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

      await onPlanReady({
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
        executionMode,
        clawhubSuggestions,
        executionPlan,
        historyItem,
        initialStepConfigs,
      });
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

  async function sendMessage() {
    const content = input.trim();
    if (!content) return;
    setInput("");
    await sendMessageWithContent(content, { appendUserMessage: true });
  }

  return {
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
    sendMessageWithContent,
    sendMessage,
  };
}
