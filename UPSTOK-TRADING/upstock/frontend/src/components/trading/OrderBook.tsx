"use client";

import { useEffect, useRef, useState } from "react";
import { marketEngine } from "@/lib/market-engine";
import type { OrderBookSnapshot, SymbolMeta } from "@/types/trading";
import { formatPrice, formatSize } from "@/lib/format";

function Row({
  level,
  side,
  maxTotal,
  precision,
  sizePrecision,
  onPick,
}: {
  level: { price: number; size: number; total: number };
  side: "bid" | "ask";
  maxTotal: number;
  precision: number;
  sizePrecision: number;
  onPick?: (price: number) => void;
}) {
  const pct = Math.min(100, (level.total / Math.max(maxTotal, 1e-9)) * 100);
  const color = side === "bid" ? "text-buy" : "text-sell";
  const barColor = side === "bid" ? "bg-buy/10" : "bg-sell/10";
  return (
    <button
      type="button"
      onClick={() => onPick?.(level.price)}
      className="relative flex w-full items-center justify-between px-3 py-[3px] font-mono text-[11px] transition hover:bg-panel-raised"
    >
      <span
        className={`absolute inset-y-0 ${side === "bid" ? "right-0" : "right-0"} ${barColor}`}
        style={{ width: `${pct}%` }}
        aria-hidden="true"
      />
      <span className={`relative z-10 ${color}`}>{formatPrice(level.price, precision)}</span>
      <span className="relative z-10 text-ink-muted">{formatSize(level.size, sizePrecision)}</span>
      <span className="relative z-10 hidden text-ink-muted/70 sm:inline">{formatSize(level.total, sizePrecision)}</span>
    </button>
  );
}

export function OrderBook({ meta, onPickPrice }: { meta: SymbolMeta; onPickPrice?: (price: number) => void }) {
  const [book, setBook] = useState<OrderBookSnapshot | null>(null);
  const [flash, setFlash] = useState(false);
  const prevMid = useRef<number | null>(null);

  useEffect(() => {
    setBook(null);
    const unsub = marketEngine.subscribeBook(meta.symbol, (snapshot) => {
      setBook(snapshot);
      setFlash(true);
    });
    setBook(marketEngine.getBook(meta.symbol));
    return unsub;
  }, [meta.symbol]);

  useEffect(() => {
    if (!flash) return;
    const t = setTimeout(() => setFlash(false), 220);
    return () => clearTimeout(t);
  }, [flash]);

  if (!book) {
    return (
      <div className="flex h-64 items-center justify-center rounded-lg border border-hairline bg-panel">
        <p className="font-mono text-xs text-ink-muted">Connecting to order book\u2026</p>
      </div>
    );
  }

  const bestBid = book.bids[0]?.price ?? 0;
  const bestAsk = book.asks[0]?.price ?? 0;
  const spread = bestAsk - bestBid;
  const spreadPct = bestBid ? (spread / bestBid) * 100 : 0;
  const maxTotal = Math.max(
    book.bids[book.bids.length - 1]?.total ?? 0,
    book.asks[book.asks.length - 1]?.total ?? 0
  );
  const mid = (bestBid + bestAsk) / 2;
  const midUp = prevMid.current !== null ? mid >= prevMid.current : true;
  prevMid.current = mid;

  return (
    <div className="flex h-full flex-col rounded-lg border border-hairline bg-panel">
      <div className="flex items-center justify-between border-b border-hairline px-3 py-2">
        <h3 className="font-display text-sm text-ink">Order Book</h3>
        <span className={`h-1.5 w-1.5 rounded-full ${flash ? "bg-signal" : "bg-buy"} transition-colors`} title="Live" />
      </div>
      <div className="flex justify-between px-3 py-1.5 font-mono text-[10px] uppercase tracking-wide text-ink-muted">
        <span>Price</span>
        <span>Size</span>
        <span className="hidden sm:inline">Total</span>
      </div>
      <div className="flex flex-1 flex-col overflow-hidden">
        <div className="flex flex-1 flex-col-reverse overflow-hidden">
          {book.asks
            .slice(0, 10)
            .reverse()
            .map((lvl) => (
              <Row
                key={`ask-${lvl.price}`}
                level={lvl}
                side="ask"
                maxTotal={maxTotal}
                precision={meta.pricePrecision}
                sizePrecision={meta.sizePrecision}
                onPick={onPickPrice}
              />
            ))}
        </div>
        <div className="flex items-baseline justify-between border-y border-hairline bg-panel-raised px-3 py-2">
          <span className={`font-mono text-base font-medium ${midUp ? "text-buy" : "text-sell"}`}>
            {formatPrice(mid, meta.pricePrecision)}
          </span>
          <span className="font-mono text-[10px] text-ink-muted">spread {spreadPct.toFixed(3)}%</span>
        </div>
        <div className="flex flex-1 flex-col overflow-hidden">
          {book.bids.slice(0, 10).map((lvl) => (
            <Row
              key={`bid-${lvl.price}`}
              level={lvl}
              side="bid"
              maxTotal={maxTotal}
              precision={meta.pricePrecision}
              sizePrecision={meta.sizePrecision}
              onPick={onPickPrice}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
