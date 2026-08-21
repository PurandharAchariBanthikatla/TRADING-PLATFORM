"use client";

import Link from "next/link";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { TickerTape } from "@/components/TickerTape";
import { useAuth } from "@/lib/auth-context";

export default function HomePage() {
  const { user, isLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && user) {
      router.replace("/dashboard");
    }
  }, [isLoading, user, router]);

  return (
    <main className="terminal-grid flex min-h-screen flex-col bg-void">
      <TickerTape />
      <div className="flex flex-1 flex-col items-center justify-center px-6 text-center">
        <p className="mb-3 font-mono text-xs uppercase tracking-[0.25em] text-signal">Spot &middot; Sandbox mode</p>
        <h1 className="max-w-2xl font-display text-4xl font-medium text-ink sm:text-5xl">
          A trading terminal built for precision, not noise.
        </h1>
        <p className="mt-4 max-w-md text-ink-muted">
          Paper-trading environment. No real funds are held until the ledger, risk, and
          settlement systems clear full verification.
        </p>
        <div className="mt-8 flex gap-3">
          <Link
            href="/register"
            className="rounded-md bg-signal px-5 py-2.5 font-medium text-void transition hover:bg-signal/90"
          >
            Create account
          </Link>
          <Link
            href="/login"
            className="rounded-md border border-hairline px-5 py-2.5 font-medium text-ink transition hover:border-signal/60"
          >
            Sign in
          </Link>
        </div>
      </div>
    </main>
  );
}
