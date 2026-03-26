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
  background: "#f8fafc",
  glow: "#dbeafe",
  node: {
    scope: "#ff6b6b",
    document: "#4ecdc4",
    chunk: "#3b82f6",
  },
  edge: {
    hierarchyScope: "rgba(59,130,246,0.22)",
    hierarchyChunk: "rgba(148,163,184,0.48)",
    tag: "rgba(78,205,196,0.4)",
    source: "rgba(59,130,246,0.34)",
    similar: "rgba(168,85,247,0.3)",
  },
  legend: {
    scope: "bg-[#ff6b6b]",
    document: "bg-[#4ecdc4]",
    chunk: "bg-[#3b82f6]",
    tag: "bg-[#4ecdc4]",
    source: "bg-[#3b82f6]",
    similar: "bg-[#a855f7]",
  },
} as const;
