import type { Side } from "@/types/trading";

/**
 * Lightweight demo risk engine.
 *
 * Deliberately simple: it runs a fixed set of synchronous checks against
 * in-memory state (mock balances, open orders, a rolling timestamp window
 * for rate limiting) and returns a structured result the UI can render as
 * a risk-status indicator. This mirrors the shape a real pre-trade risk
 * service would return -- a checklist plus an overall verdict -- without
 * any of the persistence, async I/O, or account-linking a production
 * engine would need.
 */

export type RiskStatus = "pass" | "warn" | "fail";

export interface RiskCheck {
  id: string;
  label: string;
  status: RiskStatus;
  detail: string;
}

export interface RiskEvaluation {
  overall: RiskStatus;
  checks: RiskCheck[];
  notional: number;
}

export interface RiskLimits {
  maxOpenOrders: number;
  maxPositionNotional: number;
  minOrderNotional: number;
  maxOrderNotional: number;
  rateLimitWindowMs: number;
  rateLimitMaxOrders: number;
}

export const DEFAULT_RISK_LIMITS: RiskLimits = {
  maxOpenOrders: 8,
  maxPositionNotional: 500_000,
  minOrderNotional: 10,
  maxOrderNotional: 250_000,
  rateLimitWindowMs: 10_000,
  rateLimitMaxOrders: 6,
};

export interface RiskContext {
  side: Side;
  price: number;
  size: number;
  quoteBalance: number;
  baseBalance: number;
  openOrderCount: number;
  currentPositionNotional: number;
  recentOrderTimestamps: number[]; // ms epoch, most recent first
  limits?: RiskLimits;
}

function overallFrom(checks: RiskCheck[]): RiskStatus {
  if (checks.some((c) => c.status === "fail")) return "fail";
  if (checks.some((c) => c.status === "warn")) return "warn";
  return "pass";
}

export function evaluateOrderRisk(ctx: RiskContext): RiskEvaluation {
  const limits = ctx.limits ?? DEFAULT_RISK_LIMITS;
  const notional = ctx.price * ctx.size;
  const checks: RiskCheck[] = [];

  // 1. Balance validation
  if (ctx.side === "buy") {
    const headroom = ctx.quoteBalance - notional;
    checks.push({
      id: "balance",
      label: "Balance validation",
      status: notional <= 0 ? "warn" : headroom < 0 ? "fail" : headroom < ctx.quoteBalance * 0.05 ? "warn" : "pass",
      detail:
        headroom < 0
          ? `Requires ${notional.toFixed(2)} quote, only ${ctx.quoteBalance.toFixed(2)} available.`
          : `${headroom.toFixed(2)} quote balance remains after this order.`,
    });
  } else {
    const headroom = ctx.baseBalance - ctx.size;
    checks.push({
      id: "balance",
      label: "Balance validation",
      status: ctx.size <= 0 ? "warn" : headroom < 0 ? "fail" : headroom < ctx.baseBalance * 0.05 ? "warn" : "pass",
      detail:
        headroom < 0
          ? `Requires ${ctx.size} base units, only ${ctx.baseBalance.toFixed(6)} available.`
          : `${headroom.toFixed(6)} base units remain after this order.`,
    });
  }

  // 2. Order notional limits
  checks.push({
    id: "notional",
    label: "Order size limit",
    status:
      notional < limits.minOrderNotional
        ? "fail"
        : notional > limits.maxOrderNotional
        ? "fail"
        : notional > limits.maxOrderNotional * 0.8
        ? "warn"
        : "pass",
    detail:
      notional < limits.minOrderNotional
        ? `Order notional ${notional.toFixed(2)} is below the ${limits.minOrderNotional} minimum.`
        : notional > limits.maxOrderNotional
        ? `Order notional ${notional.toFixed(2)} exceeds the ${limits.maxOrderNotional.toLocaleString()} cap.`
        : `Order notional ${notional.toFixed(2)} of ${limits.maxOrderNotional.toLocaleString()} cap.`,
  });

  // 3. Position exposure limit
  const projectedPosition =
    ctx.currentPositionNotional + (ctx.side === "buy" ? notional : -notional);
  checks.push({
    id: "position",
    label: "Position limit",
    status:
      Math.abs(projectedPosition) > limits.maxPositionNotional
        ? "fail"
        : Math.abs(projectedPosition) > limits.maxPositionNotional * 0.85
        ? "warn"
        : "pass",
    detail: `Projected exposure ${Math.abs(projectedPosition).toLocaleString(undefined, {
      maximumFractionDigits: 0,
    })} of ${limits.maxPositionNotional.toLocaleString()} cap.`,
  });

  // 4. Open order count
  checks.push({
    id: "open-orders",
    label: "Open order limit",
    status:
      ctx.openOrderCount >= limits.maxOpenOrders
        ? "fail"
        : ctx.openOrderCount >= limits.maxOpenOrders - 1
        ? "warn"
        : "pass",
    detail: `${ctx.openOrderCount} of ${limits.maxOpenOrders} open orders in use.`,
  });

  // 5. Rate limiting (token-bucket style, rolling window)
  const windowStart = Date.now() - limits.rateLimitWindowMs;
  const recentCount = ctx.recentOrderTimestamps.filter((ts) => ts >= windowStart).length;
  checks.push({
    id: "rate-limit",
    label: "Rate limit",
    status:
      recentCount >= limits.rateLimitMaxOrders
        ? "fail"
        : recentCount >= limits.rateLimitMaxOrders - 2
        ? "warn"
        : "pass",
    detail: `${recentCount} of ${limits.rateLimitMaxOrders} orders placed in the last ${Math.round(
      limits.rateLimitWindowMs / 1000
    )}s window.`,
  });

  return { overall: overallFrom(checks), checks, notional };
}
