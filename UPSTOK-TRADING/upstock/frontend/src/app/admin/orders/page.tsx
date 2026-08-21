"use client";

import { useState } from "react";
import { AdminPageHeader, KpiCard } from "@/components/admin/AdminShell";
import { DataTable, type Column } from "@/components/admin/DataTable";
import { StatusPill } from "@/components/admin/StatusPill";
import { generateOrders, generateUsers } from "@/lib/mock-admin-data";
import type { AdminOrder } from "@/types/admin";
import { formatPrice, formatSize, timeAgo } from "@/lib/format";

export default function AdminOrdersPage() {
  const [orders] = useState<AdminOrder[]>(() => generateOrders(generateUsers()));

  const columns: Column<AdminOrder>[] = [
    { key: "id", header: "Order ID", render: (o) => <span className="text-ink-muted">{o.id}</span>, sortValue: (o) => o.id },
    { key: "user", header: "User", render: (o) => o.userDisplayName, sortValue: (o) => o.userDisplayName },
    { key: "symbol", header: "Market", render: (o) => o.symbol, sortValue: (o) => o.symbol },
    { key: "side", header: "Side", render: (o) => <span className={o.side === "buy" ? "text-buy" : "text-sell"}>{o.side}</span>, sortValue: (o) => o.side },
    { key: "type", header: "Type", render: (o) => <span className="capitalize text-ink-muted">{o.type}</span>, sortValue: (o) => o.type },
    { key: "price", header: "Price", render: (o) => formatPrice(o.price, 4), sortValue: (o) => o.price },
    { key: "size", header: "Size / Filled", render: (o) => `${formatSize(o.size, 4)} / ${formatSize(o.filled, 4)}`, sortValue: (o) => o.size },
    { key: "status", header: "Status", render: (o) => <StatusPill value={o.status} />, sortValue: (o) => o.status },
    { key: "created", header: "Created", render: (o) => timeAgo(o.createdAt), sortValue: (o) => o.createdAt },
  ];

  return (
    <div>
      <AdminPageHeader title="Orders" description="Platform-wide order flow across all markets and users." />
      <div className="mb-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <KpiCard label="Total orders" value={orders.length.toLocaleString()} />
        <KpiCard label="Filled" value={orders.filter((o) => o.status === "filled").length.toLocaleString()} />
        <KpiCard label="Open" value={orders.filter((o) => o.status === "open").length.toLocaleString()} />
        <KpiCard label="Rejected" value={orders.filter((o) => o.status === "rejected").length.toLocaleString()} />
      </div>
      <DataTable
        columns={columns}
        rows={orders}
        rowKey={(o) => o.id}
        searchKeys={(o) => `${o.id} ${o.userDisplayName} ${o.symbol}`}
        searchPlaceholder="Search by order ID, user, or market\u2026"
      />
    </div>
  );
}
