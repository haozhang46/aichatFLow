"use client";

import AppButton from "@/components/ui/AppButton";
import AppModal from "@/components/ui/AppModal";
import type { PlanHistoryItem } from "@/app/components/modalTypes";

type Props = {
  selectedPlanRecord: PlanHistoryItem | null;
  setSelectedPlanRecord: (item: PlanHistoryItem | null) => void;
  openTaskFlow: (
    source: { title: string; mode: "auto" | "agent" | "react" | "workflow"; lines: string[]; skills: string[] },
    editable: boolean
  ) => void;
};

export default function PlanDetailModal(props: Props) {
  if (!props.selectedPlanRecord) return null;
  const item = props.selectedPlanRecord;
  return (
    <AppModal panelClassName="w-full max-w-3xl max-h-[80vh] overflow-auto bg-white dark:bg-zinc-900 rounded border border-zinc-300 dark:border-zinc-700 p-4">
      <div className="flex items-center gap-2 mb-3">
        <div className="font-medium flex-1">计划详情</div>
        <AppButton type="button" onClick={() => props.setSelectedPlanRecord(null)}>
          关闭
        </AppButton>
      </div>
      <div className="text-sm font-medium">{item.query}</div>
      <div className="text-xs text-zinc-500 mt-1">mode: {item.mode}</div>
      <div className="mt-3">
        <div className="text-sm font-medium">1. 用户意图描述</div>
        <div className="text-sm text-zinc-600 dark:text-zinc-300 whitespace-pre-wrap mt-1">{item.intentDescription}</div>
      </div>
      <div className="mt-3">
        <div className="text-sm font-medium">2. 计划</div>
        <div className="text-sm text-zinc-600 dark:text-zinc-300 mt-1 space-y-1">
          {item.lines.map((line, idx) => (
            <div key={`${item.id}-detail-plan-${idx}`}>{idx + 1}. {line}</div>
          ))}
        </div>
      </div>
      <div className="mt-3">
        <div className="text-sm font-medium">3. task</div>
        <div className="text-sm text-zinc-600 dark:text-zinc-300 mt-1 space-y-1">
          {item.lines.map((line, idx) => (
            <div key={`${item.id}-detail-task-${idx}`}>
              Step {idx + 1}: {line} ｜ agent: {item.mode} ｜ skill:{" "}
              {item.recommendedSkills.length > 0 ? item.recommendedSkills.join(", ") : "none"}
            </div>
          ))}
        </div>
      </div>
      <div className="mt-4 flex items-center gap-2">
        <AppButton
          type="button"
          size="md"
          variant="info"
          onClick={() =>
            props.openTaskFlow(
              {
                title: `${item.query} (可编辑)`,
                mode: item.mode,
                lines: item.lines,
                skills: item.recommendedSkills,
              },
              true
            )
          }
        >
          Task Flow
        </AppButton>
        <AppButton
          type="button"
          size="md"
          onClick={() =>
            props.openTaskFlow(
              {
                title: `${item.query} (查看)`,
                mode: item.mode,
                lines: item.lines,
                skills: item.recommendedSkills,
              },
              false
            )
          }
        >
          查看 Flow
        </AppButton>
      </div>
    </AppModal>
  );
}
