"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { marketEngine } from "@/lib/market-engine";
import type { Candle, SymbolMeta } from "@/types/trading";
import { formatPrice, formatTime } from "@/lib/format";

const TIMEFRAMES = [
  { id: "1m", label: "1m", bucketMinutes: 1 },
  { id: "5m", label: "5m", bucketMinutes: 5 },
  { id: "15m", label: "15m", bucketMinutes: 15 },
  { id: "1h", label: "1h", bucketMinutes: 60 },
] as const;

function aggregate(candles: Candle[], bucketMinutes: number): Candle[] {
  if (bucketMinutes <= 1) return candles;
  const bucketMs = bucketMinutes * 60_000;
  const out: Candle[] = [];
  for (const c of candles) {
    const bucketTime = Math.floor(c.time / bucketMs) * bucketMs;
    const last = out[out.length - 1];
    if (last && last.time === bucketTime) {
      last.high = Math.max(last.high, c.high);
      last.low = Math.min(last.low, c.low);
      last.close = c.close;
      last.volume += c.volume;
    } else {
      out.push({ ...c, time: bucketTime });
    }
  }
  return out;
}

const WIDTH = 720;
const HEIGHT = 300;
const PADDING = { top: 12, right: 8, bottom: 20, left: 4 };

export function TradingChart({ meta }: { meta: SymbolMeta }) {
  const [raw, setRaw] = useState<Candle[] | null>(null);
  const [timeframe, setTimeframe] = useState<(typeof TIMEFRAMES)[number]>(TIMEFRAMES[0]);
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    setRaw(null);
    setRaw(marketEngine.getCandles(meta.symbol));
    const unsub = marketEngine.subscribeCandles(meta.symbol, setRaw);
    return unsub;
  }, [meta.symbol]);

  const candles = useMemo(() => {
    if (!raw) return [];
    const bucketed = aggregate(raw, timeframe.bucketMinutes);
    return bucketed.slice(-70);
  }, [raw, timeframe]);

  const { bars, minP, maxP } = useMemo(() => {
    if (candles.length === 0) return { bars: [], minP: 0, maxP: 1 };
    const lo = Math.min(...candles.map((c) => c.low));
    const hi = Math.max(...candles.map((c) => c.high));
    const pad = (hi - lo) * 0.08 || hi * 0.01;
    const minP = lo - pad;
    const maxP = hi + pad;
    const plotW = WIDTH - PADDING.left - PADDING.right;
    const plotH = HEIGHT - PADDING.top - PADDING.bottom;
    const slot = plotW / candles.length;
    const bw = Math.max(2, slot * 0.6);
    const y = (p: number) => PADDING.top + plotH * (1 - (p - minP) / Math.max(maxP - minP, 1e-9));
    const bars = candles.map((c, i) => {
      const x = PADDING.left + i * slot + slot / 2;
      return {
        c,
        x,
        yOpen: y(c.open),
        yClose: y(c.close),
        yHigh: y(c.high),
        yLow: y(c.low),
        bw,
        up: c.close >= c.open,
      };
    });
    return { bars, minP, maxP };
  }, [candles]);

  if (!raw || candles.length === 0) {
    return (
      <div className="flex h-[300px] items-center justify-center rounded-lg border border-hairline bg-panel">
        <p className="font-mono text-xs text-ink-muted">Loading chart data\u2026</p>
      </div>
    );
  }

  const last = candles[candles.length - 1]!;
  const first = candles[0]!;
  const changePct = ((last.close - first.open) / first.open) * 100;
  const hovered = hoverIdx !== null ? bars[hoverIdx] : null;

  function handleMove(e: React.MouseEvent<SVGSVGElement>) {
    if (!svgRef.current || bars.length === 0) return;
    const rect = svgRef.current.getBoundingClientRect();
    const relX = ((e.clientX - rect.left) / rect.width) * WIDTH;
    let closest = 0;
    let bestDist = Infinity;
    bars.forEach((b, i) => {
      const d = Math.abs(b.x - relX);
      if (d < bestDist) {
        bestDist = d;
        closest = i;
      }
    });
    setHoverIdx(closest);
  }

  const gridLines = 4;

  return (
    <div className="flex h-full flex-col rounded-lg border border-hairline bg-panel">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-hairline px-3 py-2">
        <div className="flex items-baseline gap-2">
          <h3 className="font-display text-sm text-ink">{meta.displayName}</h3>
          <span className={`font-mono text-xs ${changePct >= 0 ? "text-buy" : "text-sell"}`}>
            {changePct >= 0 ? "+" : ""}
            {changePct.toFixed(2)}%
          </span>
        </div>
        <div className="flex gap-1">
          {TIMEFRAMES.map((tf) => (
            <button
              key={tf.id}
              onClick={() => setTimeframe(tf)}
              className={`rounded px-2 py-1 font-mono text-[10px] uppercase transition ${
                timeframe.id === tf.id ? "bg-panel-raised text-signal" : "text-ink-muted hover:text-ink"
              }`}
            >
              {tf.label}
            </button>
          ))}
        </div>
      </div>
      <div className="relative flex-1 p-2">
        <svg
          ref={svgRef}
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          className="h-full w-full"
          onMouseMove={handleMove}
          onMouseLeave={() => setHoverIdx(null)}
        >
          {Array.from({ length: gridLines }).map((_, i) => {
            const y = PADDING.top + ((HEIGHT - PADDING.top - PADDING.bottom) / (gridLines - 1)) * i;
            const price = maxP - ((maxP - minP) / (gridLines - 1)) * i;
            return (
              <g key={i}>
                <line x1={PADDING.left} y1={y} x2={WIDTH - PADDING.right} y2={y} stroke="#2A2F38" strokeWidth="1" strokeDasharray="2 4" />
                <text x={WIDTH - PADDING.right} y={y - 3} textAnchor="end" fontSize="9" fill="#8B9099" fontFamily="var(--font-mono)">
                  {formatPrice(price, meta.pricePrecision)}
                </text>
              </g>
            );
          })}
          {bars.map((b, i) => (
            <g key={b.c.time} opacity={hoverIdx === null || hoverIdx === i ? 1 : 0.55} className="transition-opacity duration-150">
              <line x1={b.x} y1={b.yHigh} x2={b.x} y2={b.yLow} stroke={b.up ? "#3DDC84" : "#FF5C5C"} strokeWidth="1" />
              <rect
                x={b.x - b.bw / 2}
                y={Math.min(b.yOpen, b.yClose)}
                width={b.bw}
                height={Math.max(1, Math.abs(b.yClose - b.yOpen))}
                fill={b.up ? "#3DDC84" : "#FF5C5C"}
                rx="0.5"
              />
            </g>
          ))}
          {hovered && (
            <line x1={hovered.x} y1={PADDING.top} x2={hovered.x} y2={HEIGHT - PADDING.bottom} stroke="#8B9099" strokeWidth="1" strokeDasharray="3 3" />
          )}
        </svg>
        {hovered && (
          <div className="pointer-events-none absolute left-2 top-2 rounded-md border border-hairline bg-panel-raised/95 px-2.5 py-1.5 font-mono text-[10px] text-ink shadow-lg">
            <p className="text-ink-muted">{formatTime(hovered.c.time)}</p>
            <p>
              O <span className="text-ink">{formatPrice(hovered.c.open, meta.pricePrecision)}</span> &nbsp; H{" "}
              <span className="text-buy">{formatPrice(hovered.c.high, meta.pricePrecision)}</span>
            </p>
            <p>
              L <span className="text-sell">{formatPrice(hovered.c.low, meta.pricePrecision)}</span> &nbsp; C{" "}
              <span className="text-ink">{formatPrice(hovered.c.close, meta.pricePrecision)}</span>
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
