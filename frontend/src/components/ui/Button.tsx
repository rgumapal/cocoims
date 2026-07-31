import type { ButtonHTMLAttributes } from "react";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "danger";
}

// SPEC §12.1: gold is a primary action button, "one per screen, at most."
// This component doesn't enforce that count (no way to at the component
// level), but making "primary" the one variant that reaches for --accent
// means a screen has to opt in per-button rather than getting gold by
// default, which is what keeps the count low in practice.
export function Button({ variant = "secondary", className = "", ...props }: ButtonProps) {
  const base =
    "rounded-md px-3 py-1.5 font-ui text-body font-medium transition-colors duration-theme disabled:cursor-not-allowed disabled:opacity-50";
  const variants = {
    primary: "bg-accent text-accent-fg hover:bg-accent-hover",
    secondary: "border border-border-strong bg-surface text-text hover:bg-surface-hover",
    danger: "bg-negative text-text-invert hover:opacity-90",
  };
  return <button className={`${base} ${variants[variant]} ${className}`} {...props} />;
}
