const TONE_MAP: Record<string, string> = {
  // positive / active
  active: "bg-buy/10 text-buy border-buy/30",
  approved: "bg-buy/10 text-buy border-buy/30",
  enabled: "bg-buy/10 text-buy border-buy/30",
  trading: "bg-buy/10 text-buy border-buy/30",
  filled: "bg-buy/10 text-buy border-buy/30",
  enforced: "bg-buy/10 text-buy border-buy/30",
  info: "bg-buy/10 text-buy border-buy/30",
  // neutral / pending
  pending: "bg-signal/10 text-signal border-signal/30",
  pending_review: "bg-signal/10 text-signal border-signal/30",
  open: "bg-signal/10 text-signal border-signal/30",
  monitoring: "bg-signal/10 text-signal border-signal/30",
  maintenance: "bg-signal/10 text-signal border-signal/30",
  post_only: "bg-signal/10 text-signal border-signal/30",
  warning: "bg-signal/10 text-signal border-signal/30",
  not_started: "bg-ink-muted/10 text-ink-muted border-hairline",
  disabled: "bg-ink-muted/10 text-ink-muted border-hairline",
  // negative
  suspended: "bg-sell/10 text-sell border-sell/30",
  rejected: "bg-sell/10 text-sell border-sell/30",
  cancelled: "bg-sell/10 text-sell border-sell/30",
  halted: "bg-sell/10 text-sell border-sell/30",
  critical: "bg-sell/10 text-sell border-sell/30",
};

export function StatusPill({ value }: { value: string }) {
  const tone = TONE_MAP[value] ?? "bg-panel-raised text-ink-muted border-hairline";
  return (
    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 font-mono text-[10px] uppercase tracking-wide ${tone}`}>
      {value.replace(/_/g, " ")}
    </span>
  );
}
