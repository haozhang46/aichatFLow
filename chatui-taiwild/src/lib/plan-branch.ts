export function branchInputKey(stepIndex: number, parentId: string | null) {
  return `${stepIndex}:${parentId ?? "__root__"}`;
}
