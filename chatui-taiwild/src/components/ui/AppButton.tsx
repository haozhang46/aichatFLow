"use client";

import type { ButtonHTMLAttributes, ReactNode } from "react";
import { buttonVariantClass } from "@/components/ui/theme";

type ButtonVariant = "neutral" | "primary" | "success" | "warning" | "info" | "danger" | "tab";
type ButtonSize = "xs" | "sm" | "md";

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  loadingText?: ReactNode;
  children: ReactNode;
};

function cx(...parts: Array<string | false | null | undefined>) {
  return parts.filter(Boolean).join(" ");
}

const sizeClass: Record<ButtonSize, string> = {
  xs: "text-xs px-2 py-1 rounded",
  sm: "text-xs px-3 py-1.5 rounded",
  md: "text-sm px-3 py-2 rounded",
};

export default function AppButton({
  variant = "neutral",
  size = "sm",
  loading = false,
  loadingText,
  className,
  children,
  disabled,
  ...props
}: Props) {
  return (
    <button
      {...props}
      disabled={disabled || loading}
      aria-busy={loading}
      className={cx(
        "cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed transition-colors",
        sizeClass[size],
        buttonVariantClass[variant],
        className
      )}
    >
      <span className="inline-flex items-center gap-1.5">
        {loading ? <span className="inline-block h-3 w-3 animate-spin rounded-full border border-current border-r-transparent" /> : null}
        <span>{loading ? loadingText ?? children : children}</span>
      </span>
    </button>
  );
}
