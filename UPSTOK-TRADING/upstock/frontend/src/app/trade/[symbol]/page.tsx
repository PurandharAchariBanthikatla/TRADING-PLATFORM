"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { AppHeader } from "@/components/AppHeader";
import { MarketSelector } from "@/components/trading/MarketSelector";
import { OrderBook } from "@/components/trading/OrderBook";
import { TradeTape } from "@/components/trading/TradeTape";
import { TradingChart } from "@/components/trading/TradingChart";
import { OrderTicket } from "@/components/trading/OrderTicket";
import { OpenOrdersTable } from "@/components/trading/OpenOrdersTable";
import { PositionsPanel } from "@/components/trading/PositionsPanel";
import { marketEngine, symbolMeta, SYMBOLS } from "@/lib/market-engine";
import type { Balances, DemoOrder, OrderType, Position, Side, Ticker } from "@/types/trading";
import { formatPct, formatPrice, formatUsd } from "@/lib/format";

const INITIAL_BALANCES: Balances = { USDT: 25_000, BTC: 0.42, ETH: 3.1, SOL: 85, XRP: 3200 };
const INITIAL_POSITIONS: Record<string, Position> = {
  "BTC-USDT": { symbol: "BTC-USDT", base: "BTC", qty: 0.18, avgEntryPrice: 61_950 },
  "ETH-USDT": { symbol: "ETH-USDT", base: "ETH", qty: 1.4, avgEntryPrice: 3_280 },
};

function uid(): string {
  return `demo_${Math.random().toString(36).slice(2, 10)}`;
}

export default function TradingTerminalPage() {
  const { user, isLoading } = useAuth();
  const router = useRouter();
  const params = useParams<{ symbol: string }>();
  const symbol = params.symbol ?? SYMBOLS[0]!.symbol;
  const meta = symbolMeta(symbol);

  const [balances, setBalances] = useState<Balances>(INITIAL_BALANCES);
  const [positions, setPositions] = useState<Record<string, Position>>(INITIAL_POSITIONS);
  const [openOrders, setOpenOrders] = useState<DemoOrder[]>([]);
  const [recentOrderTimestamps, setRecentOrderTimestamps] = useState<number[]>([]);
  const [ticker, setTicker] = useState<Ticker | null>(null);
  const [prefillPrice, setPrefillPrice] = useState<number | null>(null);
  const [panel, setPanel] = useState<"positions" | "orders">("positions");
  const [toast, setToast] = useState<string | null>(null);

  useEffect(() => {
    if (!isLoading && !user) router.replace("/login");
  }, [isLoading, user, router]);

  useEffect(() => {
    setTicker(marketEngine.getTicker(meta.symbol));
    const unsub = marketEngine.subscribeTicker(meta.symbol, setTicker);
    return unsub;
  }, [meta.symbol]);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 2600);
    return () => clearTimeout(t);
  }, [toast]);

  function applyFill(symbolKey: string, side: Side, fillPrice: number, size: number) {
    const m = symbolMeta(symbolKey);
    const notional = fillPrice * size;
    setBalances((prev) => {
      const next = { ...prev };
      if (side === "buy") {
        next[m.quote] = (next[m.quote] ?? 0) - notional;
        next[m.base] = (next[m.base] ?? 0) + size;
      } else {
        next[m.base] = (next[m.base] ?? 0) - size;
        next[m.quote] = (next[m.quote] ?? 0) + notional;
      }
      return next;
    });
    setPositions((prev) => {
      const existing = prev[symbolKey] ?? { symbol: symbolKey, base: m.base, qty: 0, avgEntryPrice: fillPrice };
      const signedDelta = side === "buy" ? size : -size;
      const newQty = existing.qty + signedDelta;
      let newAvg = existing.avgEntryPrice;
      if (side === "buy") {
        newAvg = newQty !== 0 ? (existing.qty * existing.avgEntryPrice + size * fillPrice) / newQty : fillPrice;
      } else if (Math.sign(newQty) !== Math.sign(existing.qty) && existing.qty !== 0) {
        newAvg = fillPrice;
      }
      return { ...prev, [symbolKey]: { symbol: symbolKey, base: m.base, qty: newQty, avgEntryPrice: newAvg } };
    });
    setToast(`${side === "buy" ? "Bought" : "Sold"} ${size} ${m.base} @ ${formatPrice(fillPrice, m.pricePrecision)}`);
  }

  function handleSubmit(order: { side: Side; type: OrderType; price: number | null; size: number }) {
    const now = Date.now();
    setRecentOrderTimestamps((prev) => [now, ...prev].slice(0, 20));

    if (order.type === "market") {
      const { avgPrice } = marketEngine.executeMarketOrder(meta.symbol, order.side, order.size);
      applyFill(meta.symbol, order.side, avgPrice, order.size);
    } else {
      const newOrder: DemoOrder = {
        id: uid(),
        symbol: meta.symbol,
        side: order.side,
        type: order.type,
        price: order.price,
        size: order.size,
        filledSize: 0,
        status: "open",
        createdAt: now,
      };
      setOpenOrders((prev) => [newOrder, ...prev]);
      setToast(`Limit ${order.side} order placed for ${order.size} ${meta.base}`);
    }
    setPrefillPrice(null);
  }

  function cancelOrder(id: string) {
    setOpenOrders((prev) => prev.filter((o) => o.id !== id));
  }

  // Simulate limit-order fills: check every open order against the live
  // price of its own market, independent of which symbol is on screen.
  useEffect(() => {
    const interval = setInterval(() => {
      setOpenOrders((prev) => {
        if (prev.length === 0) return prev;
        const remaining: DemoOrder[] = [];
        for (const o of prev) {
          const t = marketEngine.getTicker(o.symbol);
          const crosses =
            o.price !== null && ((o.side === "buy" && t.price <= o.price) || (o.side === "sell" && t.price >= o.price));
          if (crosses) {
            applyFill(o.symbol, o.side, o.price as number, o.size);
          } else {
            remaining.push(o);
          }
        }
        return remaining.length === prev.length ? prev : remaining;
      });
    }, 1200);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const livePrices = useMemo(() => {
    const map: Record<string, number> = {};
    for (const s of SYMBOLS) map[s.symbol] = marketEngine.getTicker(s.symbol).price;
    if (ticker) map[meta.symbol] = ticker.price;
    return map;
  }, [ticker, meta.symbol]);

  const currentPositionNotional = Math.abs((positions[meta.symbol]?.qty ?? 0) * (ticker?.price ?? meta.seedPrice));

  if (isLoading || !user) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-void">
        <p className="font-mono text-sm text-ink-muted">Loading session\u2026</p>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-void">
      <AppHeader eyebrow="Trading Terminal" />

      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-hairline px-6 py-3">
        <div className="flex items-baseline gap-3">
          <h1 className="font-display text-xl text-ink">{meta.displayName}</h1>
          {ticker && (
            <>
              <span className="font-mono text-lg text-ink">{formatPrice(ticker.price, meta.pricePrecision)}</span>
              <span className={`font-mono text-sm ${ticker.changePct >= 0 ? "text-buy" : "text-sell"}`}>
                {formatPct(ticker.changePct)}
              </span>
            </>
          )}
        </div>
        {ticker && (
          <div className="flex gap-5 font-mono text-xs text-ink-muted">
            <span>
              24h High <span className="text-ink">{formatPrice(ticker.high24h, meta.pricePrecision)}</span>
            </span>
            <span>
              24h Low <span className="text-ink">{formatPrice(ticker.low24h, meta.pricePrecision)}</span>
            </span>
            <span>
              24h Volume <span className="text-ink">{formatUsd(ticker.volume24h)}</span>
            </span>
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 gap-3 p-3 lg:grid-cols-[220px_1fr_300px] xl:grid-cols-[240px_1fr_320px]">
        <div className="order-2 lg:order-1">
          <MarketSelector activeSymbol={meta.symbol} />
        </div>

        <div className="order-1 flex flex-col gap-3 lg:order-2">
          <div className="h-[320px]">
            <TradingChart meta={meta} />
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="h-64">
              <OrderBook meta={meta} onPickPrice={setPrefillPrice} />
            </div>
            <div className="h-64">
              <TradeTape meta={meta} />
            </div>
          </div>
        </div>

        <div className="order-3">
          <OrderTicket
            meta={meta}
            livePrice={ticker?.price ?? meta.seedPrice}
            quoteBalance={balances[meta.quote] ?? 0}
            baseBalance={balances[meta.base] ?? 0}
            openOrderCount={openOrders.length}
            currentPositionNotional={currentPositionNotional}
            recentOrderTimestamps={recentOrderTimestamps}
            prefillPrice={prefillPrice}
            onSubmit={handleSubmit}
          />
        </div>
      </div>

      <div className="px-3 pb-6">
        <div className="mb-2 flex gap-1">
          <button
            onClick={() => setPanel("positions")}
            className={`rounded-md px-3 py-1.5 font-mono text-xs uppercase tracking-wide transition ${
              panel === "positions" ? "bg-panel-raised text-signal" : "text-ink-muted hover:text-ink"
            }`}
          >
            Positions
          </button>
          <button
            onClick={() => setPanel("orders")}
            className={`rounded-md px-3 py-1.5 font-mono text-xs uppercase tracking-wide transition ${
              panel === "orders" ? "bg-panel-raised text-signal" : "text-ink-muted hover:text-ink"
            }`}
          >
            Open Orders {openOrders.length > 0 && `(${openOrders.length})`}
          </button>
        </div>
        {panel === "positions" ? (
          <PositionsPanel positions={Object.values(positions)} livePrices={livePrices} />
        ) : (
          <OpenOrdersTable orders={openOrders} onCancel={cancelOrder} />
        )}
      </div>

      {toast && (
        <div className="toast-in fixed bottom-5 left-1/2 z-50 rounded-md border border-signal/40 bg-panel-raised px-4 py-2.5 font-mono text-xs text-ink shadow-lg">
          {toast}
        </div>
      )}
    </main>
  );
}
