import React from "react";
import { cn } from "@/lib/utils";

interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: "default" | "purple" | "pink" | "blue" | "emerald" | "amber" | "outline" | "danger";
  size?: "sm" | "md";
}

export const Badge: React.FC<BadgeProps> = ({
  children,
  variant = "default",
  size = "sm",
  className,
  ...props
}) => {
  const variantStyles = {
    default: "bg-surface-tertiary text-slate-300 border-surface-border",
    purple: "bg-purple-950/50 text-purple-300 border-purple-800/40 shadow-glow-purple",
    pink: "bg-pink-950/50 text-pink-300 border-pink-800/40 shadow-glow-pink",
    blue: "bg-blue-950/50 text-blue-300 border-blue-800/40 shadow-glow-blue",
    emerald: "bg-emerald-950/50 text-emerald-300 border-emerald-800/40",
    amber: "bg-amber-950/50 text-amber-300 border-amber-800/40",
    outline: "bg-transparent text-slate-400 border-slate-700/60",
    danger: "bg-rose-950/50 text-rose-300 border-rose-800/40",
  };

  const sizeStyles = {
    sm: "text-[11px] px-2 py-0.5 font-medium tracking-wide",
    md: "text-xs px-2.5 py-1 font-medium",
  };

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border transition-colors select-none",
        variantStyles[variant],
        sizeStyles[size],
        className
      )}
      {...props}
    >
      {children}
    </span>
  );
};
