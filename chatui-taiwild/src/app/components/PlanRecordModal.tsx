"use client";

import AppButton from "@/components/ui/AppButton";
import AppModal from "@/components/ui/AppModal";
import type { PlanHistoryItem, Strategy } from "@/app/components/modalTypes";

type Props = {
  open: boolean;
  onClose: () => void;
  planRecordSearch: string;
  setPlanRecordSearch: (value: string) => void;
  filteredPlanRecords: PlanHistoryItem[];
  setSelectedPlanRecord: (item: PlanHistoryItem | null) => void;
  loadHistoryPlan: (item: PlanHistoryItem) => void;
  executePlanItem: (item: PlanHistoryItem) => Promise<void>;
  openTaskFlow: (
    source: { title: string; mode: Strategy; lines: string[]; skills: string[] },
    editable: boolean
  ) => void;
  toggleFavorite: (itemId: string) => void;
  deletePlanItem: (itemId: string) => void;
};

export default function PlanRecordModal(props: Props) {
  if (!props.open) return null;
  return (
    <AppModal panelClassName="w-full max-w-6xl h-[82vh] bg-white dark:bg-zinc-900 rounded border border-zinc-300 dark:border-zinc-700 flex flex-col">
      <div className="px-4 py-3 border-b border-zinc-200 dark:border-zinc-700 flex items-center gap-2">
        <div className="font-medium flex-1">计划记录</div>
        <input
          className="border border-zinc-300 dark:border-zinc-700 rounded px-2 py-1 text-sm w-64"
          placeholder="card search..."
          value={props.planRecordSearch}
          onChange={(e) => props.setPlanRecordSearch(e.target.value)}
        />
        <AppButton type="button" onClick={props.onClose}>
          关闭
        </AppButton>
      </div>
      <div className="p-4 overflow-auto grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {props.filteredPlanRecords.map((item) => (
          <div key={item.id} className="border border-zinc-200 dark:border-zinc-700 rounded p-3">
            <AppButton
              type="button"
              variant="tab"
              size="xs"
              className="text-sm font-medium truncate text-left w-full border-none dark:border-none px-0 py-0"
              onClick={() => props.setSelectedPlanRecord(item)}
            >
              {item.query}
            </AppButton>
            <div className="text-xs text-zinc-500 mt-1">{item.mode}</div>
            <div className="mt-2 text-xs text-zinc-500 whitespace-pre-wrap">{item.intentDescription}</div>
            <div className="mt-2 text-xs">
              {item.lines.slice(0, 3).map((line, idx) => (
                <div key={`${item.id}-line-${idx}`}>{idx + 1}. {line}</div>
              ))}
            </div>
            <div className="mt-2 text-[11px] text-zinc-500">
              skill: {item.recommendedSkills.length > 0 ? item.recommendedSkills.join(", ") : "none"}
            </div>
            {item.lastTraceId ? (
              <div className="mt-1 text-[10px] font-mono text-indigo-600 dark:text-indigo-400 break-all">
                trace: {item.lastTraceId}
              </div>
            ) : null}
            <div className="mt-3 flex items-center gap-2 flex-wrap">
              <AppButton
                type="button"
                onClick={() => {
                  props.loadHistoryPlan(item);
                  props.onClose();
                }}
                size="xs"
              >
                加载计划
              </AppButton>
              <AppButton type="button" onClick={() => void props.executePlanItem(item)} size="xs" variant="success">
                使用计划
              </AppButton>
              <AppButton
                type="button"
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
                size="xs"
                variant="info"
              >
                Task Flow
              </AppButton>
              <AppButton type="button" onClick={() => props.toggleFavorite(item.id)} size="xs">
                {item.favorite ? "★" : "☆"}
              </AppButton>
              <AppButton type="button" onClick={() => props.deletePlanItem(item.id)} size="xs" variant="danger">
                删除
              </AppButton>
            </div>
          </div>
        ))}
        {props.filteredPlanRecords.length === 0 ? <div className="text-sm text-zinc-500">没有匹配的计划记录。</div> : null}
      </div>
    </AppModal>
  );
}
