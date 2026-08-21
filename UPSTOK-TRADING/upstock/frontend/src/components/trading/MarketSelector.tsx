"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { marketEngine, SYMBOLS } from "@/lib/market-engine";
import type { Ticker } from "@/types/trading";
import { formatPrice, formatPct } from "@/lib/format";

export function MarketSelector({ activeSymbol }: { activeSymbol: string }) {
  const [tickers, setTickers] = useState<Record<string, Ticker>>({});

  useEffect(() => {
    const unsubs = SYMBOLS.map((m) =>
      marketEngine.subscribeTicker(m.symbol, (t) => setTickers((prev) => ({ ...prev, [m.symbol]: t })))
    );
    setTickers(Object.fromEntries(SYMBOLS.map((m) => [m.symbol, marketEngine.getTicker(m.symbol)])));
    return () => unsubs.forEach((u) => u());
  }, []);

  return (
    <div className="rounded-lg border border-hairline bg-panel">
      <div className="border-b border-hairline px-3 py-2">
        <h3 className="font-display text-sm text-ink">Markets</h3>
      </div>
      <div className="divide-y divide-hairline">
        {SYMBOLS.map((m) => {
          const t = tickers[m.symbol];
          const active = m.symbol === activeSymbol;
          return (
            <Link
              key={m.symbol}
              href={`/trade/${m.symbol}`}
              className={`flex items-center justify-between px-3 py-2.5 transition hover:bg-panel-raised ${
                active ? "bg-panel-raised" : ""
              }`}
            >
              <span className={`font-mono text-xs ${active ? "text-signal" : "text-ink"}`}>{m.displayName}</span>
              {t ? (
                <span className="text-right">
                  <span className="block font-mono text-xs text-ink">{formatPrice(t.price, m.pricePrecision)}</span>
                  <span className={`block font-mono text-[10px] ${t.changePct >= 0 ? "text-buy" : "text-sell"}`}>
                    {formatPct(t.changePct)}
                  </span>
                </span>
              ) : (
                <span className="font-mono text-[10px] text-ink-muted">\u2026</span>
              )}
            </Link>
          );
        })}
      </div>
    </div>
  );
}
