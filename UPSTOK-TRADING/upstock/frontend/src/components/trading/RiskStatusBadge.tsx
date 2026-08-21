"use client";

import { useState } from "react";
import type { RiskEvaluation, RiskStatus } from "@/lib/risk-engine";

const STATUS_STYLES: Record<RiskStatus, { dot: string; text: string; bg: string; label: string }> = {
  pass: { dot: "bg-buy", text: "text-buy", bg: "bg-buy/10 border-buy/30", label: "Risk OK" },
  warn: { dot: "bg-signal", text: "text-signal", bg: "bg-signal/10 border-signal/30", label: "Risk Warning" },
  fail: { dot: "bg-sell", text: "text-sell", bg: "bg-sell/10 border-sell/30", label: "Risk Blocked" },
};

export function RiskStatusBadge({ evaluation }: { evaluation: RiskEvaluation }) {
  const [open, setOpen] = useState(false);
  const style = STATUS_STYLES[evaluation.overall];

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        onBlur={() => setTimeout(() => setOpen(false), 120)}
        className={`flex w-full items-center justify-between rounded-md border px-3 py-2 font-mono text-xs transition ${style.bg}`}
      >
        <span className="flex items-center gap-2">
          <span className={`h-1.5 w-1.5 rounded-full ${style.dot} ${evaluation.overall !== "pass" ? "animate-pulse" : ""}`} />
          <span className={style.text}>{style.label}</span>
        </span>
        <span className="text-ink-muted">{open ? "Hide checks \u2303" : "View checks \u2304"}</span>
      </button>
      {open && (
        <div className="absolute bottom-full left-0 z-40 mb-2 w-full min-w-[280px] rounded-md border border-hairline bg-panel-raised p-3 shadow-lg">
          <p className="mb-2 font-mono text-[10px] uppercase tracking-[0.2em] text-ink-muted">Pre-trade risk checks</p>
          <ul className="space-y-1.5">
            {evaluation.checks.map((check) => {
              const s = STATUS_STYLES[check.status];
              return (
                <li key={check.id} className="flex items-start gap-2 text-xs">
                  <span className={`mt-1 h-1.5 w-1.5 flex-shrink-0 rounded-full ${s.dot}`} />
                  <span>
                    <span className="text-ink">{check.label}: </span>
                    <span className="text-ink-muted">{check.detail}</span>
                  </span>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}
