"use client";

import type { Position } from "@/types/trading";
import { formatPrice, formatSize, formatUsd } from "@/lib/format";
import { symbolMeta } from "@/lib/market-engine";

export function PositionsPanel({
  positions,
  livePrices,
}: {
  positions: Position[];
  livePrices: Record<string, number>;
}) {
  const open = positions.filter((p) => Math.abs(p.qty) > 1e-9);

  if (open.length === 0) {
    return (
      <div className="rounded-lg border border-hairline bg-panel p-6 text-center">
        <p className="font-mono text-xs text-ink-muted">No open positions. Fills from market orders land here.</p>
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-lg border border-hairline bg-panel">
      <table className="w-full text-left">
        <thead>
          <tr className="border-b border-hairline font-mono text-[10px] uppercase tracking-wide text-ink-muted">
            <th className="px-3 py-2 font-normal">Asset</th>
            <th className="px-3 py-2 font-normal">Qty</th>
            <th className="px-3 py-2 font-normal">Avg entry</th>
            <th className="px-3 py-2 font-normal">Mark</th>
            <th className="px-3 py-2 font-normal">Unrealized P&amp;L</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-hairline">
          {open.map((p) => {
            const meta = symbolMeta(p.symbol);
            const mark = livePrices[p.symbol] ?? p.avgEntryPrice;
            const pnl = (mark - p.avgEntryPrice) * p.qty;
            const pnlPct = p.avgEntryPrice ? ((mark - p.avgEntryPrice) / p.avgEntryPrice) * 100 * Math.sign(p.qty) : 0;
            return (
              <tr key={p.symbol} className="font-mono text-xs text-ink transition hover:bg-panel-raised">
                <td className="px-3 py-2">{meta.displayName}</td>
                <td className={`px-3 py-2 ${p.qty >= 0 ? "text-buy" : "text-sell"}`}>{formatSize(p.qty, meta.sizePrecision)}</td>
                <td className="px-3 py-2 text-ink-muted">{formatPrice(p.avgEntryPrice, meta.pricePrecision)}</td>
                <td className="px-3 py-2 text-ink-muted">{formatPrice(mark, meta.pricePrecision)}</td>
                <td className={`px-3 py-2 ${pnl >= 0 ? "text-buy" : "text-sell"}`}>
                  {pnl >= 0 ? "+" : ""}
                  {formatUsd(pnl)} <span className="text-ink-muted/70">({pnlPct >= 0 ? "+" : ""}{pnlPct.toFixed(2)}%)</span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
