"use client";

import type { DemoOrder } from "@/types/trading";
import { formatPrice, formatSize, formatTime } from "@/lib/format";
import { symbolMeta } from "@/lib/market-engine";

export function OpenOrdersTable({ orders, onCancel }: { orders: DemoOrder[]; onCancel: (id: string) => void }) {
  if (orders.length === 0) {
    return (
      <div className="rounded-lg border border-hairline bg-panel p-6 text-center">
        <p className="font-mono text-xs text-ink-muted">No open orders yet. Place a limit order to see it here.</p>
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-lg border border-hairline bg-panel">
      <table className="w-full text-left">
        <thead>
          <tr className="border-b border-hairline font-mono text-[10px] uppercase tracking-wide text-ink-muted">
            <th className="px-3 py-2 font-normal">Market</th>
            <th className="px-3 py-2 font-normal">Side</th>
            <th className="px-3 py-2 font-normal">Type</th>
            <th className="px-3 py-2 font-normal">Price</th>
            <th className="px-3 py-2 font-normal">Size</th>
            <th className="px-3 py-2 font-normal">Filled</th>
            <th className="px-3 py-2 font-normal">Time</th>
            <th className="px-3 py-2 font-normal"></th>
          </tr>
        </thead>
        <tbody className="divide-y divide-hairline">
          {orders.map((o) => {
            const meta = symbolMeta(o.symbol);
            return (
              <tr key={o.id} className="font-mono text-xs text-ink transition hover:bg-panel-raised">
                <td className="px-3 py-2">{meta.displayName}</td>
                <td className={`px-3 py-2 uppercase ${o.side === "buy" ? "text-buy" : "text-sell"}`}>{o.side}</td>
                <td className="px-3 py-2 capitalize text-ink-muted">{o.type}</td>
                <td className="px-3 py-2">{o.price ? formatPrice(o.price, meta.pricePrecision) : "Market"}</td>
                <td className="px-3 py-2">{formatSize(o.size, meta.sizePrecision)}</td>
                <td className="px-3 py-2 text-ink-muted">{formatSize(o.filledSize, meta.sizePrecision)}</td>
                <td className="px-3 py-2 text-ink-muted">{formatTime(o.createdAt)}</td>
                <td className="px-3 py-2 text-right">
                  <button
                    onClick={() => onCancel(o.id)}
                    className="rounded border border-hairline px-2 py-1 text-[10px] text-ink-muted transition hover:border-sell/60 hover:text-sell"
                  >
                    Cancel
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
