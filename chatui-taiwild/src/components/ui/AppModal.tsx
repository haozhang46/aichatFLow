"use client";

import type { ReactNode } from "react";

type Props = {
  children: ReactNode;
  zIndexClass?: "z-modal" | "z-tooltip";
  overlayClassName?: string;
  panelClassName?: string;
};

function cx(...parts: Array<string | undefined>) {
  return parts.filter(Boolean).join(" ");
}

export default function AppModal({
  children,
  zIndexClass = "z-modal",
  overlayClassName,
  panelClassName,
}: Props) {
  return (
    <div
      className={cx(
        "fixed inset-0 bg-black/50 flex items-center justify-center p-4",
        zIndexClass,
        overlayClassName
      )}
    >
      <div className={panelClassName}>{children}</div>
    </div>
  );
}
