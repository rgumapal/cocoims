import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from "react";

interface FieldProps {
  label: string;
  htmlFor: string;
  error?: string;
  children: ReactNode;
}

export function Field({ label, htmlFor, error, children }: FieldProps) {
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={htmlFor} className="font-ui text-small font-medium text-text-2">
        {label}
      </label>
      {children}
      {error && <span className="font-ui text-small text-negative">{error}</span>}
    </div>
  );
}

const inputClasses =
  "rounded-md border border-border-strong bg-surface px-2.5 py-1.5 font-ui text-body text-text outline-none focus:border-accent disabled:bg-surface-2 disabled:text-text-3";

export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={inputClasses} {...props} />;
}

export function Select(props: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className={inputClasses} {...props} />;
}
