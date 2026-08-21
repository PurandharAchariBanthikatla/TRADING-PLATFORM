"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { SYMBOLS } from "@/lib/market-engine";

export default function TradeIndexPage() {
  const router = useRouter();
  useEffect(() => {
    router.replace(`/trade/${SYMBOLS[0]!.symbol}`);
  }, [router]);
  return (
    <main className="flex min-h-screen items-center justify-center bg-void">
      <p className="font-mono text-sm text-ink-muted">Loading terminal\u2026</p>
    </main>
  );
}
