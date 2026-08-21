"use client";

import { useEffect, useMemo, useState } from "react";
import { evaluateOrderRisk } from "@/lib/risk-engine";
import { RiskStatusBadge } from "./RiskStatusBadge";
import type { OrderType, Side, SymbolMeta } from "@/types/trading";
import { formatUsd } from "@/lib/format";

export interface OrderTicketProps {
  meta: SymbolMeta;
  livePrice: number;
  quoteBalance: number;
  baseBalance: number;
  openOrderCount: number;
  currentPositionNotional: number;
  recentOrderTimestamps: number[];
  prefillPrice: number | null;
  onSubmit: (order: { side: Side; type: OrderType; price: number | null; size: number }) => void;
}

const SIZE_PRESETS = [25, 50, 75, 100];

export function OrderTicket({
  meta,
  livePrice,
  quoteBalance,
  baseBalance,
  openOrderCount,
  currentPositionNotional,
  recentOrderTimestamps,
  prefillPrice,
  onSubmit,
}: OrderTicketProps) {
  const [side, setSide] = useState<Side>("buy");
  const [type, setType] = useState<OrderType>("limit");
  const [price, setPrice] = useState<string>(livePrice ? livePrice.toFixed(meta.pricePrecision) : "");
  const [size, setSize] = useState<string>("");
  const [flash, setFlash] = useState(false);

  useEffect(() => {
    setPrice(livePrice ? livePrice.toFixed(meta.pricePrecision) : "");
    setSize("");
  }, [meta.symbol]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (prefillPrice) setPrice(prefillPrice.toFixed(meta.pricePrecision));
  }, [prefillPrice, meta.pricePrecision]);

  useEffect(() => {
    if (type === "market") setPrice(livePrice.toFixed(meta.pricePrecision));
  }, [livePrice, type, meta.pricePrecision]);

  const numericPrice = type === "market" ? livePrice : parseFloat(price) || 0;
  const numericSize = parseFloat(size) || 0;

  const evaluation = useMemo(
    () =>
      evaluateOrderRisk({
        side,
        price: numericPrice,
        size: numericSize,
        quoteBalance,
        baseBalance,
        openOrderCount,
        currentPositionNotional,
        recentOrderTimestamps,
      }),
    [side, numericPrice, numericSize, quoteBalance, baseBalance, openOrderCount, currentPositionNotional, recentOrderTimestamps]
  );

  function applyPreset(pct: number) {
    if (side === "buy") {
      const spendable = (quoteBalance * pct) / 100;
      const est = numericPrice > 0 ? spendable / numericPrice : 0;
      setSize(est.toFixed(meta.sizePrecision));
    } else {
      setSize(((baseBalance * pct) / 100).toFixed(meta.sizePrecision));
    }
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (numericSize <= 0 || evaluation.overall === "fail") return;
    onSubmit({ side, type, price: type === "market" ? null : numericPrice, size: numericSize });
    setSize("");
    setFlash(true);
    setTimeout(() => setFlash(false), 500);
  }

  const balanceLine =
    side === "buy"
      ? `${quoteBalance.toLocaleString(undefined, { maximumFractionDigits: 2 })} ${meta.quote} available`
      : `${baseBalance.toLocaleString(undefined, { maximumFractionDigits: 6 })} ${meta.base} available`;

  return (
    <div
      className={`rounded-lg border bg-panel transition-shadow ${
        flash ? "border-signal shadow-[0_0_0_1px_rgba(232,163,61,0.4)]" : "border-hairline"
      }`}
    >
      <div className="grid grid-cols-2 border-b border-hairline">
        <button
          onClick={() => setSide("buy")}
          className={`py-2.5 font-mono text-xs uppercase tracking-wide transition ${
            side === "buy" ? "bg-buy/10 text-buy" : "text-ink-muted hover:text-ink"
          }`}
        >
          Buy
        </button>
        <button
          onClick={() => setSide("sell")}
          className={`py-2.5 font-mono text-xs uppercase tracking-wide transition ${
            side === "sell" ? "bg-sell/10 text-sell" : "text-ink-muted hover:text-ink"
          }`}
        >
          Sell
        </button>
      </div>

      <form onSubmit={handleSubmit} className="space-y-3 p-3">
        <div className="flex gap-1 rounded-md bg-panel-raised p-1">
          {(["limit", "market"] as OrderType[]).map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setType(t)}
              className={`flex-1 rounded py-1 font-mono text-[11px] capitalize transition ${
                type === t ? "bg-void text-ink" : "text-ink-muted hover:text-ink"
              }`}
            >
              {t}
            </button>
          ))}
        </div>

        <div>
          <label className="mb-1 block font-mono text-[10px] uppercase tracking-wide text-ink-muted">
            Price ({meta.quote})
          </label>
          <input
            type="number"
            step="any"
            disabled={type === "market"}
            value={price}
            onChange={(e) => setPrice(e.target.value)}
            className="w-full rounded-md border border-hairline bg-panel-raised px-3 py-2 font-mono text-sm text-ink outline-none focus:border-signal disabled:opacity-50"
            placeholder="0.00"
          />
        </div>

        <div>
          <label className="mb-1 block font-mono text-[10px] uppercase tracking-wide text-ink-muted">
            Size ({meta.base})
          </label>
          <input
            type="number"
            step="any"
            value={size}
            onChange={(e) => setSize(e.target.value)}
            className="w-full rounded-md border border-hairline bg-panel-raised px-3 py-2 font-mono text-sm text-ink outline-none focus:border-signal"
            placeholder="0.00"
          />
          <div className="mt-1.5 grid grid-cols-4 gap-1.5">
            {SIZE_PRESETS.map((p) => (
              <button
                key={p}
                type="button"
                onClick={() => applyPreset(p)}
                className="rounded border border-hairline py-1 font-mono text-[10px] text-ink-muted transition hover:border-signal/60 hover:text-signal"
              >
                {p}%
              </button>
            ))}
          </div>
        </div>

        <div className="flex items-center justify-between font-mono text-[11px] text-ink-muted">
          <span>Est. notional</span>
          <span className="text-ink">{formatUsd(numericPrice * numericSize || 0)}</span>
        </div>
        <p className="font-mono text-[10px] text-ink-muted">{balanceLine}</p>

        <RiskStatusBadge evaluation={evaluation} />

        <button
          type="submit"
          disabled={numericSize <= 0 || evaluation.overall === "fail"}
          className={`w-full rounded-md py-2.5 font-medium transition disabled:cursor-not-allowed disabled:opacity-40 ${
            side === "buy" ? "bg-buy text-void hover:bg-buy/90" : "bg-sell text-void hover:bg-sell/90"
          }`}
        >
          {side === "buy" ? "Buy" : "Sell"} {meta.base}
        </button>
      </form>
    </div>
  );
}
