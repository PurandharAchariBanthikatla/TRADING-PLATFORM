"use client";

import { useMemo, useState } from "react";
import { AdminPageHeader, KpiCard } from "@/components/admin/AdminShell";
import { DataTable, type Column } from "@/components/admin/DataTable";
import { StatusPill } from "@/components/admin/StatusPill";
import { generateKyc, generateUsers } from "@/lib/mock-admin-data";
import type { KycRecord } from "@/types/admin";
import { timeAgo } from "@/lib/format";

export default function AdminKycPage() {
  const [records] = useState<KycRecord[]>(() => generateKyc(generateUsers()));

  const stats = useMemo(
    () => ({
      pending: records.filter((r) => r.status === "pending_review").length,
      approved: records.filter((r) => r.status === "approved").length,
      rejected: records.filter((r) => r.status === "rejected").length,
      avgRisk: Math.round(records.reduce((s, r) => s + r.riskScore, 0) / Math.max(records.length, 1)),
    }),
    [records]
  );

  const columns: Column<KycRecord>[] = [
    { key: "user", header: "Applicant", render: (r) => r.displayName, sortValue: (r) => r.displayName },
    { key: "tier", header: "Tier", render: (r) => r.tier, sortValue: (r) => r.tier },
    { key: "doc", header: "Document", render: (r) => r.documentType, sortValue: (r) => r.documentType },
    { key: "status", header: "Status", render: (r) => <StatusPill value={r.status} />, sortValue: (r) => r.status },
    {
      key: "risk",
      header: "Risk score",
      render: (r) => (
        <span className={r.riskScore >= 70 ? "text-sell" : r.riskScore >= 40 ? "text-signal" : "text-buy"}>{r.riskScore}</span>
      ),
      sortValue: (r) => r.riskScore,
    },
    { key: "reviewer", header: "Reviewer", render: (r) => r.reviewer ?? "\u2014", sortValue: (r) => r.reviewer ?? "" },
    { key: "submitted", header: "Submitted", render: (r) => timeAgo(r.submittedAt), sortValue: (r) => r.submittedAt },
  ];

  return (
    <div>
      <AdminPageHeader title="KYC" description="Identity-verification queue and review outcomes." />
      <div className="mb-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <KpiCard label="Pending review" value={stats.pending.toLocaleString()} />
        <KpiCard label="Approved" value={stats.approved.toLocaleString()} />
        <KpiCard label="Rejected" value={stats.rejected.toLocaleString()} />
        <KpiCard label="Avg. risk score" value={String(stats.avgRisk)} />
      </div>
      <DataTable
        columns={columns}
        rows={records}
        rowKey={(r) => r.id}
        searchKeys={(r) => `${r.displayName} ${r.documentType} ${r.tier}`}
        searchPlaceholder="Search KYC records\u2026"
      />
    </div>
  );
}
