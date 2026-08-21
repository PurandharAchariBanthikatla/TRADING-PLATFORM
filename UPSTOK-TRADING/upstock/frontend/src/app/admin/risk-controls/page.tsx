"use client";

import { useState } from "react";
import { AdminPageHeader, KpiCard } from "@/components/admin/AdminShell";
import { DataTable, type Column } from "@/components/admin/DataTable";
import { StatusPill } from "@/components/admin/StatusPill";
import { generateRiskControls } from "@/lib/mock-admin-data";
import type { RiskControl } from "@/types/admin";

export default function AdminRiskControlsPage() {
  const [controls] = useState<RiskControl[]>(() => generateRiskControls());

  const columns: Column<RiskControl>[] = [
    { key: "name", header: "Control", render: (c) => (
        <span>
          <span className="text-ink">{c.name}</span>
          <span className="block max-w-md text-[10px] text-ink-muted">{c.description}</span>
        </span>
      ), sortValue: (c) => c.name },
    { key: "category", header: "Category", render: (c) => c.category, sortValue: (c) => c.category },
    { key: "threshold", header: "Threshold", render: (c) => <span className="text-ink-muted">{c.threshold}</span> },
    { key: "status", header: "Status", render: (c) => <StatusPill value={c.status} />, sortValue: (c) => c.status },
    {
      key: "triggered",
      header: "Triggered (24h)",
      render: (c) => (
        <span className={c.triggeredLast24h > 15 ? "text-signal" : "text-ink"}>{c.triggeredLast24h}</span>
      ),
      sortValue: (c) => c.triggeredLast24h,
    },
  ];

  return (
    <div>
      <AdminPageHeader title="Risk Controls" description="Live configuration of the risk engine's pre-trade checks." />
      <div className="mb-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <KpiCard label="Controls" value={controls.length.toLocaleString()} />
        <KpiCard label="Enforced" value={controls.filter((c) => c.status === "enforced").length.toLocaleString()} />
        <KpiCard label="Monitoring only" value={controls.filter((c) => c.status === "monitoring").length.toLocaleString()} />
        <KpiCard
          label="Triggers, 24h"
          value={controls.reduce((s, c) => s + c.triggeredLast24h, 0).toLocaleString()}
        />
      </div>
      <DataTable columns={columns} rows={controls} rowKey={(c) => c.id} pageSize={20} />
      <p className="mt-4 font-mono text-[10px] text-ink-muted">
        These mirror the checks in the trading terminal&apos;s live risk engine \u2014 balance validation, position and
        open-order limits, and order-placement rate limiting.
      </p>
    </div>
  );
}
