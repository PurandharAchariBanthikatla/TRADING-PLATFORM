"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { useAuth } from "@/lib/auth-context";
import { AppHeader } from "@/components/AppHeader";

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-hairline bg-panel p-5">
      <p className="font-mono text-xs uppercase tracking-[0.2em] text-ink-muted">{label}</p>
      <p className="mt-2 font-display text-2xl text-ink">{value}</p>
    </div>
  );
}

function LaunchCard({
  href,
  eyebrow,
  title,
  description,
}: {
  href: string;
  eyebrow: string;
  title: string;
  description: string;
}) {
  return (
    <Link
      href={href}
      className="group rounded-lg border border-hairline bg-panel p-5 transition hover:border-signal/60 hover:bg-panel-raised"
    >
      <p className="font-mono text-xs uppercase tracking-[0.2em] text-signal">{eyebrow}</p>
      <h3 className="mt-2 font-display text-lg text-ink">{title}</h3>
      <p className="mt-1.5 text-sm text-ink-muted">{description}</p>
      <span className="mt-3 inline-block font-mono text-xs text-ink-muted transition group-hover:text-signal">
        Open &rarr;
      </span>
    </Link>
  );
}

export default function DashboardPage() {
  const { user, isLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && !user) {
      router.replace("/login");
    }
  }, [isLoading, user, router]);

  if (isLoading || !user) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-void">
        <p className="font-mono text-sm text-ink-muted">Loading session\u2026</p>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-void">
      <AppHeader />
      <div className="border-b border-hairline px-6 py-4">
        <p className="font-mono text-xs uppercase tracking-[0.2em] text-signal">Sandbox</p>
        <h1 className="font-display text-xl text-ink">Welcome, {user.display_name}</h1>
      </div>

      <div className="grid grid-cols-1 gap-4 p-6 sm:grid-cols-3">
        <StatCard label="Portfolio value" value="$0.00" />
        <StatCard label="Open orders" value="0" />
        <StatCard label="24h P&L" value="+0.00%" />
      </div>

      <div className="grid grid-cols-1 gap-4 px-6 pb-6 sm:grid-cols-2">
        <LaunchCard
          href="/trade"
          eyebrow="Live demo"
          title="Trading Terminal"
          description="Order book, candlestick chart, trade tape, and an order ticket wired to a live pre-trade risk engine."
        />
        <LaunchCard
          href="/admin"
          eyebrow="Live demo"
          title="Admin Portal"
          description="Users, KYC, assets, markets, orders, risk controls, and audit logs with realistic sample data."
        />
      </div>

      <div className="mx-6 mb-6 rounded-lg border border-hairline bg-panel p-6">
        <h2 className="font-display text-lg text-ink">Account</h2>
        <dl className="mt-4 grid grid-cols-1 gap-3 font-mono text-sm sm:grid-cols-2">
          <div>
            <dt className="text-ink-muted">Email</dt>
            <dd className="text-ink">{user.email}</dd>
          </div>
          <div>
            <dt className="text-ink-muted">Role</dt>
            <dd className="text-ink">{user.role}</dd>
          </div>
          <div>
            <dt className="text-ink-muted">Email verified</dt>
            <dd className="text-ink">{user.is_email_verified ? "Yes" : "Not yet"}</dd>
          </div>
          <div>
            <dt className="text-ink-muted">2FA</dt>
            <dd className="text-ink">{user.mfa_enabled ? "Enabled" : "Not enabled"}</dd>
          </div>
        </dl>
      </div>

      <p className="mx-6 mb-10 text-sm text-ink-muted">
        Portfolio value, open orders, and P&amp;L above populate once the wallet and ledger services are wired to
        this dashboard. The trading terminal and admin portal are live demo builds using simulated market data.
      </p>
    </main>
  );
}
