import type { PlanHistoryItem } from "@/app/components/modalTypes";

export const PLAN_HISTORY_KEY = "aichatflow.planHistory.v1";
export const PLAN_EXPANDED_KEY = "aichatflow.planExpanded.v1";
export const DEEPSEEK_CONFIG_KEY = "aichatflow.deepseek.config.v1";

const PLAN_HISTORY_PLAIN_OBJECT_KEYS = [
  "planBranches",
  "selectedPlanBranch",
  "stepExecutionConfigs",
] as const satisfies ReadonlyArray<keyof PlanHistoryItem>;

type PlanHistoryPlainObjectPick = Pick<
  PlanHistoryItem,
  (typeof PLAN_HISTORY_PLAIN_OBJECT_KEYS)[number]
>;

function normalizeLegacyPlainObjectField<K extends (typeof PLAN_HISTORY_PLAIN_OBJECT_KEYS)[number]>(
  item: Partial<PlanHistoryItem>,
  key: K,
): NonNullable<PlanHistoryItem[K]> {
  const value = item[key];
  if (value && typeof value === "object" && !Array.isArray(value)) return value as NonNullable<PlanHistoryItem[K]>;
  return {} as NonNullable<PlanHistoryItem[K]>;
}

export function normalizeStoredPlanHistoryPlainObjects(item: Partial<PlanHistoryItem>): PlanHistoryPlainObjectPick {
  return Object.fromEntries(
    PLAN_HISTORY_PLAIN_OBJECT_KEYS.map((key) => [key, normalizeLegacyPlainObjectField(item, key)]),
  ) as PlanHistoryPlainObjectPick;
}
