"use client";

import type { Dispatch, SetStateAction } from "react";
import AppButton from "@/components/ui/AppButton";
import type { PlanBranchNode, PlanHistoryItem } from "./modalTypes";

type Props = {
  stepIndex: number;
  parentId: string | null;
  level: number;
  planBranches: Record<number, PlanBranchNode[]>;
  selectedPlanBranch: Record<number, Record<string, string>>;
  setSelectedPlanBranch: Dispatch<SetStateAction<Record<number, Record<string, string>>>>;
  pendingPlanRequestId: string | null;
  setPlanHistory: Dispatch<SetStateAction<PlanHistoryItem[]>>;
  updatePlanBranch: (stepIndex: number, branchId: string, value: string) => void;
  removePlanBranch: (stepIndex: number, branchId: string) => void;
  planBranchInput: Record<string, string>;
  setPlanBranchInput: Dispatch<SetStateAction<Record<string, string>>>;
  addPlanBranch: (stepIndex: number, parentId: string | null) => void;
};

function branchInputKey(stepIndex: number, parentId: string | null) {
  return `${stepIndex}:${parentId ?? "__root__"}`;
}

export default function PlanBranchEditor({
  stepIndex,
  parentId,
  level,
  planBranches,
  selectedPlanBranch,
  setSelectedPlanBranch,
  pendingPlanRequestId,
  setPlanHistory,
  updatePlanBranch,
  removePlanBranch,
  planBranchInput,
  setPlanBranchInput,
  addPlanBranch,
}: Props) {
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
                  if (pendingPlanRequestId) {
                    setPlanHistory((items) =>
                      items.map((item) =>
                        item.requestId === pendingPlanRequestId ? { ...item, selectedPlanBranch: next } : item,
                      ),
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
          <PlanBranchEditor
            stepIndex={stepIndex}
            parentId={node.id}
            level={level + 1}
            planBranches={planBranches}
            selectedPlanBranch={selectedPlanBranch}
            setSelectedPlanBranch={setSelectedPlanBranch}
            pendingPlanRequestId={pendingPlanRequestId}
            setPlanHistory={setPlanHistory}
            updatePlanBranch={updatePlanBranch}
            removePlanBranch={removePlanBranch}
            planBranchInput={planBranchInput}
            setPlanBranchInput={setPlanBranchInput}
            addPlanBranch={addPlanBranch}
          />
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
