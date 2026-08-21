"use client";

import { useState } from "react";
import { AdminPageHeader, KpiCard } from "@/components/admin/AdminShell";
import { DataTable, type Column } from "@/components/admin/DataTable";
import { StatusPill } from "@/components/admin/StatusPill";
import { generateAssets } from "@/lib/mock-admin-data";
import type { AdminAsset } from "@/types/admin";
import { formatSize } from "@/lib/format";

export default function AdminAssetsPage() {
  const [assets] = useState<AdminAsset[]>(() => generateAssets());

  const columns: Column<AdminAsset>[] = [
    { key: "symbol", header: "Asset", render: (a) => (
        <span>
          <span className="text-ink">{a.symbol}</span>
          <span className="block text-[10px] text-ink-muted">{a.name}</span>
        </span>
      ), sortValue: (a) => a.symbol },
    { key: "network", header: "Network", render: (a) => a.network, sortValue: (a) => a.network },
    { key: "status", header: "Status", render: (a) => <StatusPill value={a.status} />, sortValue: (a) => a.status },
    { key: "deposit", header: "Deposits", render: (a) => <StatusPill value={a.depositEnabled ? "enabled" : "disabled"} /> },
    { key: "withdrawal", header: "Withdrawals", render: (a) => <StatusPill value={a.withdrawalEnabled ? "enabled" : "disabled"} /> },
    { key: "circulating", header: "On-platform balance", render: (a) => formatSize(a.circulatingOnPlatform, 2), sortValue: (a) => a.circulatingOnPlatform },
    { key: "minWithdrawal", header: "Min withdrawal", render: (a) => formatSize(a.minWithdrawal, 6), sortValue: (a) => a.minWithdrawal },
  ];

  return (
    <div>
      <AdminPageHeader title="Assets" description="Supported assets, networks, and deposit/withdrawal availability." />
      <div className="mb-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <KpiCard label="Assets listed" value={assets.length.toLocaleString()} />
        <KpiCard label="Enabled" value={assets.filter((a) => a.status === "enabled").length.toLocaleString()} />
        <KpiCard label="In maintenance" value={assets.filter((a) => a.status === "maintenance").length.toLocaleString()} />
        <KpiCard
          label="Withdrawals paused"
          value={assets.filter((a) => !a.withdrawalEnabled).length.toLocaleString()}
        />
      </div>
      <DataTable
        columns={columns}
        rows={assets}
        rowKey={(a) => a.id}
        searchKeys={(a) => `${a.symbol} ${a.name} ${a.network}`}
        searchPlaceholder="Search assets\u2026"
      />
    </div>
  );
}
