import type { ReactNode } from "react";

// SPEC §12.6 rule 9: "Undo over confirm. Reserve confirmation dialogs for
// destructive and irreversible actions." This component exists for that
// narrow case (a branch status transition, a destructive delete) — it is
// not the general "edit in a modal" pattern; inline editing is (SPEC
// §12.6 rule 3), and screens should reach for that first.
export function Dialog({
  open,
  onClose,
  title,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
}) {
  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      onClick={onClose}
      role="presentation"
    >
      <div
        className="w-full max-w-md rounded-lg bg-surface p-4 shadow-2"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="dialog-title"
      >
        <h2 id="dialog-title" className="mb-3 font-ui text-h2 text-text">
          {title}
        </h2>
        {children}
      </div>
    </div>
  );
}
