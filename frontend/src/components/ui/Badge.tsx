type BadgeTone = "neutral" | "positive" | "attention" | "negative";

const TONE_CLASSES: Record<BadgeTone, string> = {
  neutral: "bg-surface-2 text-text-2",
  positive: "bg-positive-bg text-positive",
  attention: "bg-attention-bg text-attention",
  negative: "bg-negative-bg text-negative",
};

// SPEC §12.8: "never colour alone to convey state — pair with icon or
// label." A Badge is always text, never a bare colored dot, so this rule
// holds by construction rather than by discipline at each call site.
export function Badge({ tone = "neutral", children }: { tone?: BadgeTone; children: string }) {
  return (
    <span
      className={`inline-block rounded-sm px-1.5 py-0.5 font-ui text-micro font-medium uppercase tracking-[0.04em] ${TONE_CLASSES[tone]}`}
    >
      {children}
    </span>
  );
}

// Maps the domain's actual status vocabularies (SPEC §4.1 enums) to a tone
// — kept here rather than duplicated per screen, since item lifecycle and
// location status both need this and share the same semantics (active =
// positive, transitional/needs-attention = attention, terminal/negative =
// negative).
const STATUS_TONES: Record<string, BadgeTone> = {
  ACTIVE: "positive",
  PILOT: "attention",
  RAMP_UP: "attention",
  PRE_OPENING: "attention",
  PLANNED: "neutral",
  TEMPORARILY_NOT_AVAILABLE: "attention",
  TEMP_CLOSED: "attention",
  RENOVATION: "attention",
  DO_NOT_INCLUDE_YET: "neutral",
  RELOCATED: "neutral",
  DELISTED: "negative",
  CLOSED: "negative",
};

export function StatusBadge({ status }: { status: string }) {
  return <Badge tone={STATUS_TONES[status] ?? "neutral"}>{status.replaceAll("_", " ")}</Badge>;
}
