"use client";

import { useState } from "react";
import { AdminPageHeader, KpiCard } from "@/components/admin/AdminShell";
import { DataTable, type Column } from "@/components/admin/DataTable";
import { StatusPill } from "@/components/admin/StatusPill";
import { generateMarkets } from "@/lib/mock-admin-data";
import type { AdminMarket } from "@/types/admin";
import { formatCompactUsd, formatPrice } from "@/lib/format";

export default function AdminMarketsPage() {
  const [markets] = useState<AdminMarket[]>(() => generateMarkets());

  const columns: Column<AdminMarket>[] = [
    { key: "symbol", header: "Market", render: (m) => `${m.base}/${m.quote}`, sortValue: (m) => m.symbol },
    { key: "status", header: "Status", render: (m) => <StatusPill value={m.status} />, sortValue: (m) => m.status },
    { key: "price", header: "Last price", render: (m) => formatPrice(m.lastPrice, 4), sortValue: (m) => m.lastPrice },
    { key: "volume", header: "24h volume", render: (m) => formatCompactUsd(m.dailyVolumeUsd), sortValue: (m) => m.dailyVolumeUsd },
    { key: "maker", header: "Maker fee", render: (m) => `${(m.makerFeeBps / 100).toFixed(2)}%`, sortValue: (m) => m.makerFeeBps },
    { key: "taker", header: "Taker fee", render: (m) => `${(m.takerFeeBps / 100).toFixed(2)}%`, sortValue: (m) => m.takerFeeBps },
  ];

  return (
    <div>
      <AdminPageHeader title="Markets" description="Trading-pair configuration, fees, and current status." />
      <div className="mb-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <KpiCard label="Markets" value={markets.length.toLocaleString()} />
        <KpiCard label="Trading" value={markets.filter((m) => m.status === "trading").length.toLocaleString()} />
        <KpiCard label="Halted" value={markets.filter((m) => m.status === "halted").length.toLocaleString()} />
        <KpiCard label="24h volume" value={formatCompactUsd(markets.reduce((s, m) => s + m.dailyVolumeUsd, 0))} />
      </div>
      <DataTable
        columns={columns}
        rows={markets}
        rowKey={(m) => m.id}
        searchKeys={(m) => `${m.base} ${m.quote} ${m.symbol}`}
        searchPlaceholder="Search markets\u2026"
      />
    </div>
  );
}
