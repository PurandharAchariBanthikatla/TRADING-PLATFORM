"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV = [
  { href: "/admin/users", label: "Users" },
  { href: "/admin/kyc", label: "KYC" },
  { href: "/admin/assets", label: "Assets" },
  { href: "/admin/markets", label: "Markets" },
  { href: "/admin/orders", label: "Orders" },
  { href: "/admin/risk-controls", label: "Risk Controls" },
  { href: "/admin/audit-logs", label: "Audit Logs" },
];

export function AdminShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="flex min-h-[calc(100vh-57px)]">
      <aside className="hidden w-56 flex-shrink-0 border-r border-hairline bg-panel/40 sm:block">
        <div className="px-4 py-4">
          <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-signal">Admin Portal</p>
          <p className="mt-0.5 font-mono text-[10px] text-ink-muted">Demo data &middot; role-gated</p>
        </div>
        <nav className="flex flex-col gap-0.5 px-2">
          {NAV.map((item) => {
            const active = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`rounded-md px-3 py-2 font-mono text-xs transition ${
                  active ? "bg-panel-raised text-signal" : "text-ink-muted hover:bg-panel-raised hover:text-ink"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
      </aside>

      <nav className="flex gap-1 overflow-x-auto border-b border-hairline px-2 py-2 sm:hidden">
        {NAV.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={`whitespace-nowrap rounded-md px-3 py-1.5 font-mono text-xs transition ${
              pathname === item.href ? "bg-panel-raised text-signal" : "text-ink-muted"
            }`}
          >
            {item.label}
          </Link>
        ))}
      </nav>

      <div className="flex-1 overflow-x-hidden p-4 sm:p-6">{children}</div>
    </div>
  );
}

export function AdminPageHeader({ title, description }: { title: string; description: string }) {
  return (
    <div className="mb-5">
      <h1 className="font-display text-xl text-ink">{title}</h1>
      <p className="mt-1 text-sm text-ink-muted">{description}</p>
    </div>
  );
}

export function KpiCard({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-lg border border-hairline bg-panel p-4">
      <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-ink-muted">{label}</p>
      <p className="mt-1.5 font-display text-2xl text-ink">{value}</p>
      {hint && <p className="mt-1 font-mono text-[10px] text-ink-muted">{hint}</p>}
    </div>
  );
}
