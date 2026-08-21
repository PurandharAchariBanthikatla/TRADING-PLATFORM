import type {
  AdminAsset,
  AdminMarket,
  AdminOrder,
  AdminUser,
  AuditLogEntry,
  AuditSeverity,
  KycRecord,
  RiskControl,
} from "@/types/admin";

// Small seeded PRNG (mulberry32) so the "realistic sample data" is stable
// across renders/reloads instead of reshuffling every time a page mounts.
function mulberry32(seed: number) {
  let a = seed;
  return function () {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const rng = mulberry32(88172645);
const pick = <T,>(arr: T[]): T => arr[Math.floor(rng() * arr.length)]!;
const int = (min: number, max: number) => Math.floor(rng() * (max - min + 1)) + min;
const float = (min: number, max: number, precision = 2) => {
  const v = rng() * (max - min) + min;
  const f = 10 ** precision;
  return Math.round(v * f) / f;
};
const daysAgo = (d: number) => new Date(Date.now() - d * 86_400_000 - int(0, 86_400_000)).toISOString();

const FIRST_NAMES = ["Ava", "Noah", "Priya", "Kenji", "Lucas", "Mia", "Diego", "Elena", "Omar", "Sofia", "Liam", "Zara", "Arjun", "Ines", "Yusuf", "Chloe", "Mateus", "Hana", "Felix", "Nadia"];
const LAST_NAMES = ["Reyes", "Muller", "Chen", "Okafor", "Andersson", "Rossi", "Kim", "Novak", "Silva", "Haddad", "Larsson", "Petrov", "Nakamura", "Costa", "Singh"];
const COUNTRIES = ["United States", "Germany", "Singapore", "Brazil", "Japan", "United Kingdom", "Nigeria", "India", "Poland", "UAE", "Sweden", "Canada"];

function randomName(): string {
  return `${pick(FIRST_NAMES)} ${pick(LAST_NAMES)}`;
}

export function generateUsers(count = 42): AdminUser[] {
  return Array.from({ length: count }, (_, i) => {
    const name = randomName();
    const status = pick(["active", "active", "active", "active", "pending", "suspended", "disabled"] as const);
    const kyc = status === "disabled" ? "rejected" : pick(["approved", "approved", "pending_review", "not_started"] as const);
    return {
      id: `usr_${(1000 + i).toString(36)}`,
      displayName: name,
      email: `${name.toLowerCase().replace(" ", ".")}@example.com`,
      role: i === 0 ? "admin" : rng() < 0.04 ? "admin" : "user",
      status,
      kycStatus: kyc,
      country: pick(COUNTRIES),
      registeredAt: daysAgo(int(3, 540)),
      lastLoginAt: daysAgo(int(0, 14)),
      portfolioUsd: float(0, 185_000, 2),
    };
  });
}

export function generateKyc(users: AdminUser[]): KycRecord[] {
  return users.slice(0, 30).map((u, i) => ({
    id: `kyc_${(2000 + i).toString(36)}`,
    userId: u.id,
    displayName: u.displayName,
    status: u.kycStatus,
    tier: pick(["Tier 0", "Tier 1", "Tier 2"] as const),
    documentType: pick(["Passport", "National ID", "Driver's License"]),
    submittedAt: daysAgo(int(1, 300)),
    reviewer: u.kycStatus === "not_started" ? null : pick(["A. Fischer", "R. Gomez", "S. Patel", null]),
    riskScore: int(2, 96),
  }));
}

const ASSET_DEFS = [
  { symbol: "BTC", name: "Bitcoin", network: "Bitcoin" },
  { symbol: "ETH", name: "Ethereum", network: "ERC-20" },
  { symbol: "SOL", name: "Solana", network: "Solana" },
  { symbol: "XRP", name: "Ripple", network: "XRPL" },
  { symbol: "USDT", name: "Tether USD", network: "ERC-20" },
  { symbol: "USDC", name: "USD Coin", network: "ERC-20" },
  { symbol: "ADA", name: "Cardano", network: "Cardano" },
  { symbol: "DOGE", name: "Dogecoin", network: "Dogecoin" },
];

export function generateAssets(): AdminAsset[] {
  return ASSET_DEFS.map((a, i) => ({
    id: `ast_${i}`,
    symbol: a.symbol,
    name: a.name,
    network: a.network,
    status: rng() < 0.08 ? "maintenance" : "enabled",
    withdrawalEnabled: rng() > 0.1,
    depositEnabled: true,
    circulatingOnPlatform: float(10_000, 4_800_000, 0),
    minWithdrawal: a.symbol === "USDT" || a.symbol === "USDC" ? 10 : float(0.001, 0.05, 4),
  }));
}

const MARKET_DEFS = [
  { symbol: "BTC-USDT", base: "BTC", quote: "USDT", price: 64_218.5 },
  { symbol: "ETH-USDT", base: "ETH", quote: "USDT", price: 3_412.8 },
  { symbol: "SOL-USDT", base: "SOL", quote: "USDT", price: 148.62 },
  { symbol: "XRP-USDT", base: "XRP", quote: "USDT", price: 0.5231 },
  { symbol: "ADA-USDT", base: "ADA", quote: "USDT", price: 0.4118 },
  { symbol: "DOGE-USDT", base: "DOGE", quote: "USDT", price: 0.1284 },
];

export function generateMarkets(): AdminMarket[] {
  return MARKET_DEFS.map((m, i) => ({
    id: `mkt_${i}`,
    symbol: m.symbol,
    base: m.base,
    quote: m.quote,
    status: rng() < 0.08 ? "post_only" : rng() < 0.03 ? "halted" : "trading",
    makerFeeBps: 8,
    takerFeeBps: 12,
    dailyVolumeUsd: float(400_000, 92_000_000, 0),
    lastPrice: m.price,
  }));
}

export function generateOrders(users: AdminUser[], count = 60): AdminOrder[] {
  const symbols = MARKET_DEFS.map((m) => m.symbol);
  return Array.from({ length: count }, (_, i) => {
    const market = MARKET_DEFS[int(0, MARKET_DEFS.length - 1)]!;
    const size = float(0.001, 4, 4);
    const status = pick(["filled", "filled", "filled", "open", "cancelled", "rejected"] as const);
    return {
      id: `ord_${(5000 + i).toString(36)}`,
      userDisplayName: pick(users).displayName,
      symbol: pick(symbols),
      side: pick(["buy", "sell"] as const),
      type: pick(["market", "limit"] as const),
      price: market.price * float(0.985, 1.015, 4),
      size,
      filled: status === "filled" ? size : status === "open" ? float(0, size, 4) : 0,
      status,
      createdAt: daysAgo(int(0, 30)),
    };
  });
}

export function generateRiskControls(): RiskControl[] {
  return [
    { id: "rc_1", name: "Max order notional", description: "Blocks any single order above the configured USD notional.", category: "Balance", status: "enforced", threshold: "$250,000 / order", triggeredLast24h: int(0, 6) },
    { id: "rc_2", name: "Insufficient balance guard", description: "Rejects orders that would exceed available quote or base balance.", category: "Balance", status: "enforced", threshold: "0% overdraft", triggeredLast24h: int(2, 30) },
    { id: "rc_3", name: "Max position exposure", description: "Caps net notional exposure per user, per market.", category: "Position", status: "enforced", threshold: "$500,000 / market", triggeredLast24h: int(0, 4) },
    { id: "rc_4", name: "Max open orders", description: "Limits concurrent open orders per user to reduce book spam.", category: "Position", status: "enforced", threshold: "8 open orders", triggeredLast24h: int(0, 12) },
    { id: "rc_5", name: "Order placement rate limit", description: "Token-bucket limiter on order submissions per user.", category: "Rate Limit", status: "enforced", threshold: "6 orders / 10s", triggeredLast24h: int(1, 40) },
    { id: "rc_6", name: "Login rate limit", description: "Redis-backed limiter on auth endpoints (inherited from api-gateway).", category: "Rate Limit", status: "enforced", threshold: "10 attempts / 5min", triggeredLast24h: int(0, 9) },
    { id: "rc_7", name: "Market volatility circuit breaker", description: "Flags markets for review after abnormal short-window price moves.", category: "Market", status: "monitoring", threshold: "±8% / 5min", triggeredLast24h: int(0, 2) },
    { id: "rc_8", name: "New-account withdrawal hold", description: "Delays first withdrawal for accounts younger than 24h.", category: "Market", status: "disabled", threshold: "24h hold", triggeredLast24h: 0 },
  ];
}

const AUDIT_ACTIONS: { action: string; severity: AuditSeverity }[] = [
  { action: "user.login.success", severity: "info" },
  { action: "user.login.failed", severity: "warning" },
  { action: "order.rejected.risk_check", severity: "warning" },
  { action: "order.placed", severity: "info" },
  { action: "kyc.approved", severity: "info" },
  { action: "kyc.rejected", severity: "warning" },
  { action: "withdrawal.flagged", severity: "critical" },
  { action: "admin.risk_control.updated", severity: "critical" },
  { action: "admin.user.suspended", severity: "critical" },
  { action: "asset.withdrawal.disabled", severity: "warning" },
  { action: "auth.token.refresh_reuse_detected", severity: "critical" },
  { action: "market.halted", severity: "critical" },
];

export function generateAuditLog(users: AdminUser[], count = 80): AuditLogEntry[] {
  return Array.from({ length: count }, (_, i) => {
    const { action, severity } = pick(AUDIT_ACTIONS);
    const isAdminAction = action.startsWith("admin.") || action.startsWith("market.");
    return {
      id: `log_${(9000 + i).toString(36)}`,
      actor: isAdminAction ? "admin@upstock.exchange" : pick(users).email,
      action,
      target: action.startsWith("order") ? pick(MARKET_DEFS).symbol : action.startsWith("kyc") ? pick(users).displayName : "-",
      severity,
      ip: `${int(20, 220)}.${int(0, 255)}.${int(0, 255)}.${int(1, 254)}`,
      ts: daysAgo(int(0, 21)),
    };
  }).sort((a, b) => new Date(b.ts).getTime() - new Date(a.ts).getTime());
}
