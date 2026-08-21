"use client";

import { useMemo, useState } from "react";
import { AdminPageHeader, KpiCard } from "@/components/admin/AdminShell";
import { DataTable, type Column } from "@/components/admin/DataTable";
import { StatusPill } from "@/components/admin/StatusPill";
import { generateUsers } from "@/lib/mock-admin-data";
import type { AdminUser } from "@/types/admin";
import { formatUsd, timeAgo } from "@/lib/format";

export default function AdminUsersPage() {
  const [users] = useState<AdminUser[]>(() => generateUsers());

  const stats = useMemo(
    () => ({
      total: users.length,
      active: users.filter((u) => u.status === "active").length,
      pendingKyc: users.filter((u) => u.kycStatus === "pending_review").length,
      totalPortfolio: users.reduce((sum, u) => sum + u.portfolioUsd, 0),
    }),
    [users]
  );

  const columns: Column<AdminUser>[] = [
    { key: "displayName", header: "User", render: (u) => (
        <span>
          <span className="text-ink">{u.displayName}</span>
          <span className="block text-[10px] text-ink-muted">{u.email}</span>
        </span>
      ), sortValue: (u) => u.displayName },
    { key: "role", header: "Role", render: (u) => <span className="capitalize text-ink-muted">{u.role}</span>, sortValue: (u) => u.role },
    { key: "status", header: "Status", render: (u) => <StatusPill value={u.status} />, sortValue: (u) => u.status },
    { key: "kyc", header: "KYC", render: (u) => <StatusPill value={u.kycStatus} />, sortValue: (u) => u.kycStatus },
    { key: "country", header: "Country", render: (u) => u.country, sortValue: (u) => u.country },
    { key: "portfolio", header: "Portfolio", render: (u) => formatUsd(u.portfolioUsd), sortValue: (u) => u.portfolioUsd },
    { key: "lastLogin", header: "Last login", render: (u) => timeAgo(u.lastLoginAt), sortValue: (u) => u.lastLoginAt },
  ];

  return (
    <div>
      <AdminPageHeader title="Users" description="All registered accounts on the sandbox exchange." />
      <div className="mb-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <KpiCard label="Total users" value={stats.total.toLocaleString()} />
        <KpiCard label="Active" value={stats.active.toLocaleString()} />
        <KpiCard label="Pending KYC" value={stats.pendingKyc.toLocaleString()} />
        <KpiCard label="Combined portfolio" value={formatUsd(stats.totalPortfolio)} />
      </div>
      <DataTable
        columns={columns}
        rows={users}
        rowKey={(u) => u.id}
        searchKeys={(u) => `${u.displayName} ${u.email} ${u.country}`}
        searchPlaceholder="Search users by name, email, country\u2026"
      />
    </div>
  );
}
