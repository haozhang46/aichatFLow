"use client";

import type { ButtonHTMLAttributes, ReactNode } from "react";

type ButtonVariant = "neutral" | "primary" | "success" | "info" | "danger" | "tab";
type ButtonSize = "xs" | "sm" | "md";

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
  children: ReactNode;
};

function cx(...parts: Array<string | false | null | undefined>) {
  return parts.filter(Boolean).join(" ");
}

const variantClass: Record<ButtonVariant, string> = {
  neutral: "border border-zinc-300 dark:border-zinc-700 bg-transparent text-inherit",
  primary: "bg-zinc-900 text-white dark:bg-white dark:text-black",
  success: "bg-emerald-600 text-white",
  info: "border border-indigo-300 text-indigo-700",
  danger: "border border-zinc-300 dark:border-zinc-700 text-red-600",
  tab: "border border-zinc-300 dark:border-zinc-700 bg-transparent text-inherit",
};

const sizeClass: Record<ButtonSize, string> = {
  xs: "text-xs px-2 py-1 rounded",
  sm: "text-xs px-3 py-1.5 rounded",
  md: "text-sm px-3 py-2 rounded",
};

export default function AppButton({
  variant = "neutral",
  size = "sm",
  className,
  children,
  ...props
}: Props) {
  return (
    <button
      {...props}
      className={cx(
        "cursor-pointer hover:opacity-95 disabled:opacity-50 disabled:cursor-not-allowed transition-colors",
        sizeClass[size],
        variantClass[variant],
        className
      )}
    >
      {children}
    </button>
  );
}
