import type { ReactNode } from "react";

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-4 border-b border-border px-4 py-3">
      <div>
        <h1 className="font-ui text-h1 text-text">{title}</h1>
        {description && <p className="mt-0.5 font-ui text-small text-text-2">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
  );
}
