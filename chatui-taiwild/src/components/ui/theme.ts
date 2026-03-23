export const buttonVariantClass = {
  neutral: "border border-zinc-300 bg-white text-zinc-900 hover:bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100 dark:hover:bg-zinc-800",
  primary: "bg-zinc-900 text-white hover:bg-zinc-800 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-200",
  success: "bg-emerald-600 text-white hover:bg-emerald-500",
  warning: "bg-amber-500 text-zinc-950 hover:bg-amber-400",
  info: "bg-blue-600 text-white hover:bg-blue-500",
  danger: "bg-red-600 text-white hover:bg-red-500",
  tab: "border border-zinc-300 bg-transparent text-zinc-700 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-200 dark:hover:bg-zinc-800",
} as const;

export const ragGraphTheme = {
  background: "#09090b",
  glow: "#18181b",
  node: {
    scope: "#f4f4f5",
    document: "#a1a1aa",
    chunk: "#52525b",
  },
  edge: {
    hierarchyScope: "rgba(244,244,245,0.28)",
    hierarchyChunk: "rgba(161,161,170,0.18)",
    tag: "rgba(212,212,216,0.22)",
    source: "rgba(113,113,122,0.22)",
    similar: "rgba(82,82,91,0.28)",
  },
  legend: {
    scope: "bg-zinc-100",
    document: "bg-zinc-400",
    chunk: "bg-zinc-600",
    tag: "bg-zinc-300",
    source: "bg-zinc-500",
    similar: "bg-zinc-700",
  },
} as const;
