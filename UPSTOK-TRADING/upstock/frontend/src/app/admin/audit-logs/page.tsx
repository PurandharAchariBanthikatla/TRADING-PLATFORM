"use client";

import { useState } from "react";
import { AdminPageHeader, KpiCard } from "@/components/admin/AdminShell";
import { DataTable, type Column } from "@/components/admin/DataTable";
import { StatusPill } from "@/components/admin/StatusPill";
import { generateAuditLog, generateUsers } from "@/lib/mock-admin-data";
import type { AuditLogEntry } from "@/types/admin";
import { formatDateTime } from "@/lib/format";

export default function AdminAuditLogsPage() {
  const [logs] = useState<AuditLogEntry[]>(() => generateAuditLog(generateUsers()));

  const columns: Column<AuditLogEntry>[] = [
    { key: "ts", header: "Time", render: (l) => <span className="text-ink-muted">{formatDateTime(l.ts)}</span>, sortValue: (l) => l.ts },
    { key: "actor", header: "Actor", render: (l) => l.actor, sortValue: (l) => l.actor },
    { key: "action", header: "Action", render: (l) => <code className="text-ink">{l.action}</code>, sortValue: (l) => l.action },
    { key: "target", header: "Target", render: (l) => l.target, sortValue: (l) => l.target },
    { key: "severity", header: "Severity", render: (l) => <StatusPill value={l.severity} />, sortValue: (l) => l.severity },
    { key: "ip", header: "IP", render: (l) => <span className="text-ink-muted">{l.ip}</span> },
  ];

  return (
    <div>
      <AdminPageHeader title="Audit Logs" description="Immutable event trail across auth, trading, and admin actions." />
      <div className="mb-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <KpiCard label="Events" value={logs.length.toLocaleString()} />
        <KpiCard label="Critical" value={logs.filter((l) => l.severity === "critical").length.toLocaleString()} />
        <KpiCard label="Warnings" value={logs.filter((l) => l.severity === "warning").length.toLocaleString()} />
        <KpiCard label="Info" value={logs.filter((l) => l.severity === "info").length.toLocaleString()} />
      </div>
      <DataTable
        columns={columns}
        rows={logs}
        rowKey={(l) => l.id}
        searchKeys={(l) => `${l.actor} ${l.action} ${l.target}`}
        searchPlaceholder="Search by actor, action, or target\u2026"
        pageSize={15}
      />
    </div>
  );
}
