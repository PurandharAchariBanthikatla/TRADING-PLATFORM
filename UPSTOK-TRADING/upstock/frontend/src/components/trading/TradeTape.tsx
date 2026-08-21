"use client";

import { useEffect, useState } from "react";
import { marketEngine } from "@/lib/market-engine";
import type { SymbolMeta, Trade } from "@/types/trading";
import { formatPrice, formatSize, formatTime } from "@/lib/format";

export function TradeTape({ meta }: { meta: SymbolMeta }) {
  const [trades, setTrades] = useState<Trade[] | null>(null);
  const [newestId, setNewestId] = useState<string | null>(null);

  useEffect(() => {
    setTrades(null);
    setTrades(marketEngine.getTrades(meta.symbol));
    const unsub = marketEngine.subscribeTrades(meta.symbol, (trade) => {
      setTrades((prev) => [trade, ...(prev ?? [])].slice(0, 40));
      setNewestId(trade.id);
    });
    return unsub;
  }, [meta.symbol]);

  useEffect(() => {
    if (!newestId) return;
    const t = setTimeout(() => setNewestId(null), 400);
    return () => clearTimeout(t);
  }, [newestId]);

  return (
    <div className="flex h-full flex-col rounded-lg border border-hairline bg-panel">
      <div className="flex items-center justify-between border-b border-hairline px-3 py-2">
        <h3 className="font-display text-sm text-ink">Recent Trades</h3>
      </div>
      <div className="flex justify-between px-3 py-1.5 font-mono text-[10px] uppercase tracking-wide text-ink-muted">
        <span>Price</span>
        <span>Size</span>
        <span>Time</span>
      </div>
      <div className="flex-1 overflow-y-auto">
        {!trades ? (
          <p className="p-3 font-mono text-xs text-ink-muted">Connecting to trade feed\u2026</p>
        ) : (
          trades.map((t) => (
            <div
              key={t.id}
              className={`flex items-center justify-between px-3 py-[3px] font-mono text-[11px] transition-colors duration-300 ${
                t.id === newestId ? (t.side === "buy" ? "bg-buy/10" : "bg-sell/10") : ""
              }`}
            >
              <span className={t.side === "buy" ? "text-buy" : "text-sell"}>{formatPrice(t.price, meta.pricePrecision)}</span>
              <span className="text-ink-muted">{formatSize(t.size, meta.sizePrecision)}</span>
              <span className="text-ink-muted/70">{formatTime(t.ts)}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
