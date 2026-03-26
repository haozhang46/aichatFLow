"use client";

import type { Dispatch, SetStateAction } from "react";
import AppButton from "@/components/ui/AppButton";
import PlanBranchEditor from "@/app/components/PlanBranchEditor";
import type { CapabilityAgent, ExecutionChecklistItem, ExecutionMode, PendingPlan, PlanBranchNode, PlanHistoryItem, StepExecutionConfig } from "./modalTypes";
import type { FolderAuthorization, StepRunState } from "@/app/types/shared";

type MissingRequiredToolInput = {
  stepIndex: number;
  toolId: string;
  key: string;
  label: string;
};

type ToolRequiredInputMeta = {
  key: string;
  label: string;
  type?: "text" | "password" | "textarea";
  required?: boolean;
  secret?: boolean;
  placeholder?: string;
};

type Props = {
  pendingPlan: PendingPlan;
  executionMode: ExecutionMode;
  loading: boolean;
  confirmedSkills: string[];
  setConfirmedSkills: Dispatch<SetStateAction<string[]>>;
  missingRequiredToolInputs: MissingRequiredToolInput[];
  canExecutePendingPlan: boolean;
  continueChatWithChecklist: () => void;
  confirmAndExecute: () => Promise<void>;
  cancelPlan: () => void;
  onOpenViewFlow: () => void;
  onOpenEditFlow: () => void;
  onExecutionModeChange: (value: "auto_exec" | "user_exec") => void;
  toggleClawhubSuggestion: (slug: string, selected: boolean) => void;
  activeTraceId: string | null;
  executionStepStates: Record<string, StepRunState>;
  updatePlanLine: (index: number, value: string) => void;
  capabilityAgents: CapabilityAgent[];
  stepExecutionConfigs: Record<number, StepExecutionConfig>;
  updateStepAgent: (stepIndex: number, agent: string) => void;
  whitelistedSkills: string[];
  toggleStepSkill: (stepIndex: number, skillId: string, checked: boolean) => void;
  allowlistedTools: string[];
  toggleStepTool: (stepIndex: number, toolId: string, checked: boolean) => void;
  requiredInputsForTool: (toolId: string) => ToolRequiredInputMeta[];
  stepToolInputs: Record<number, Record<string, Record<string, string>>>;
  updateStepToolInput: (stepIndex: number, toolId: string, key: string, value: string) => void;
  planBranches: Record<number, PlanBranchNode[]>;
  selectedPlanBranch: Record<number, Record<string, string>>;
  setSelectedPlanBranch: Dispatch<SetStateAction<Record<number, Record<string, string>>>>;
  setPlanHistory: Dispatch<SetStateAction<PlanHistoryItem[]>>;
  updatePlanBranch: (stepIndex: number, branchId: string, value: string) => void;
  removePlanBranch: (stepIndex: number, branchId: string) => void;
  planBranchInput: Record<string, string>;
  setPlanBranchInput: Dispatch<SetStateAction<Record<string, string>>>;
  addPlanBranch: (stepIndex: number, parentId: string | null) => void;
  updatePendingTaskChecklist: (checklist: ExecutionChecklistItem[]) => void;
  planSupplement: string;
  updatePlanSupplement: (value: string) => void;
  planFolderPathInput: string;
  setPlanFolderPathInput: (value: string) => void;
  planFolderPermInput: string;
  setPlanFolderPermInput: (value: string) => void;
  pickPlanFolderPath: () => Promise<void>;
  addPlanFolderAuth: () => void;
  planFolderAuths: FolderAuthorization[];
  removePlanFolderAuth: (path: string) => void;
  autoInstallMissing: boolean;
  setAutoInstallMissing: (value: boolean) => void;
  pendingApprovalStepId: string | null;
  approvePendingStep: () => Promise<void>;
  rejectPendingStep: () => void;
};

export default function PendingPlanPanel({
  pendingPlan,
  executionMode,
  loading,
  confirmedSkills,
  setConfirmedSkills,
  missingRequiredToolInputs,
  canExecutePendingPlan,
  continueChatWithChecklist,
  confirmAndExecute,
  cancelPlan,
  onOpenViewFlow,
  onOpenEditFlow,
  onExecutionModeChange,
  toggleClawhubSuggestion,
  activeTraceId,
  executionStepStates,
  updatePlanLine,
  capabilityAgents,
  stepExecutionConfigs,
  updateStepAgent,
  whitelistedSkills,
  toggleStepSkill,
  allowlistedTools,
  toggleStepTool,
  requiredInputsForTool,
  stepToolInputs,
  updateStepToolInput,
  planBranches,
  selectedPlanBranch,
  setSelectedPlanBranch,
  setPlanHistory,
  updatePlanBranch,
  removePlanBranch,
  planBranchInput,
  setPlanBranchInput,
  addPlanBranch,
  updatePendingTaskChecklist,
  planSupplement,
  updatePlanSupplement,
  planFolderPathInput,
  setPlanFolderPathInput,
  planFolderPermInput,
  setPlanFolderPermInput,
  pickPlanFolderPath,
  addPlanFolderAuth,
  planFolderAuths,
  removePlanFolderAuth,
  autoInstallMissing,
  setAutoInstallMissing,
  pendingApprovalStepId,
  approvePendingStep,
  rejectPendingStep,
}: Props) {
  return (
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
            {executionMode === "user_exec" ? (
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
            <AppButton type="button" onClick={onOpenViewFlow} size="md" variant="info">
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
              value={executionMode}
              onChange={(e) => onExecutionModeChange(e.target.value === "user_exec" ? "user_exec" : "auto_exec")}
            >
              <option value="auto_exec">系统自动执行（exec + test）</option>
              <option value="user_exec">用户自行执行（仅输出 checklist）</option>
            </select>
          </div>
          <div className="mt-1 text-xs text-zinc-600 dark:text-zinc-400">用户问题：{pendingPlan.query}</div>
          <div className="mt-2 text-xs text-zinc-700 dark:text-zinc-300 whitespace-pre-wrap">
            意图：{pendingPlan.intentDescription}
          </div>
          {pendingPlan.thinking ? (
            <div className="mt-2 text-xs text-zinc-600 dark:text-zinc-400 whitespace-pre-wrap">思考：{pendingPlan.thinking}</div>
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
          {!loading && pendingPlan.clawhubSuggestions && pendingPlan.clawhubSuggestions.length > 0 ? (
            <div className="mt-3">
              <div className="text-xs text-zinc-500 mb-2">
                ClawHub 相关技能（向量检索 + 启发式/LLM 简要分析；<strong>默认不勾选</strong>，确认执行时仅对你勾选的 slug 注册并纳入技能流）
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
                        {s.summary ? <div className="text-xs text-zinc-600 dark:text-zinc-400 line-clamp-2">{s.summary}</div> : null}
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
            推荐 skills: {pendingPlan.recommendedSkills.length > 0 ? pendingPlan.recommendedSkills.join(", ") : "无"}
          </div>
          <div className="mt-1 text-xs text-zinc-600 dark:text-zinc-400">
            缺失 skills: {pendingPlan.missingSkills.length > 0 ? pendingPlan.missingSkills.join(", ") : "无"}
          </div>
          <div className="mt-2">
            <div className="text-xs text-zinc-500 mb-1">确认要使用的 skills</div>
            <div className="flex flex-wrap gap-2">
              {(pendingPlan.requiredSkills.length > 0 ? pendingPlan.requiredSkills : pendingPlan.recommendedSkills).map((sid) => (
                <label
                  key={sid}
                  className="text-xs flex items-center gap-1 border border-zinc-300 dark:border-zinc-700 rounded px-2 py-1"
                >
                  <input
                    type="checkbox"
                    checked={confirmedSkills.includes(sid)}
                    onChange={(e) =>
                      setConfirmedSkills((prev) =>
                        e.target.checked ? Array.from(new Set([...prev, sid])) : prev.filter((x) => x !== sid)
                      )
                    }
                  />
                  {sid}
                </label>
              ))}
            </div>
          </div>
          {activeTraceId ? <div className="mt-2 text-xs font-mono text-zinc-700 dark:text-zinc-300">traceId: {activeTraceId}</div> : null}
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
                          {allowlistedTools.length === 0 ? <div className="text-xs text-zinc-400">暂无可用 tool</div> : null}
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
                      <PlanBranchEditor
                        stepIndex={idx}
                        parentId={null}
                        level={0}
                        planBranches={planBranches}
                        selectedPlanBranch={selectedPlanBranch}
                        setSelectedPlanBranch={setSelectedPlanBranch}
                        pendingPlanRequestId={pendingPlan.requestId}
                        setPlanHistory={setPlanHistory}
                        updatePlanBranch={updatePlanBranch}
                        removePlanBranch={removePlanBranch}
                        planBranchInput={planBranchInput}
                        setPlanBranchInput={setPlanBranchInput}
                        addPlanBranch={addPlanBranch}
                      />
                    </div>
                  </div>
                );
              })
            ) : (
              <div className="text-sm text-zinc-500">未返回可展示的计划步骤。</div>
            )}
          </div>
          {!loading && pendingPlan.lines.length > 0 && pendingPlan.lines.every((x) => x.trim().length > 0) && pendingPlan.taskChecklist.length > 0 ? (
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
                          pendingPlan.taskChecklist.map((x) => (x.id === item.id ? { ...x, done: e.target.checked } : x))
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
                <AppButton type="button" size="md" variant="info" onClick={() => void approvePendingStep()} disabled={loading}>
                  同意 {pendingApprovalStepId} 并继续执行
                </AppButton>
                <AppButton type="button" size="md" variant="danger" onClick={rejectPendingStep} disabled={loading}>
                  拒绝并终止
                </AppButton>
              </>
            ) : null}
            {executionMode === "user_exec" ? (
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
            <AppButton type="button" onClick={onOpenEditFlow} size="md" variant="info">
              Task Flow
            </AppButton>
          </div>
        </>
      )}
    </div>
  );
}
