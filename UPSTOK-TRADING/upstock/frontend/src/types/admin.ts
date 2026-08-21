export type UserStatus = "active" | "suspended" | "pending" | "disabled";
export type KycStatus = "approved" | "pending_review" | "rejected" | "not_started";
export type AssetStatus = "enabled" | "disabled" | "maintenance";
export type MarketStatus = "trading" | "halted" | "post_only" | "delisted";
export type AdminOrderStatus = "open" | "filled" | "cancelled" | "rejected";
export type RiskControlStatus = "enforced" | "monitoring" | "disabled";
export type AuditSeverity = "info" | "warning" | "critical";

export interface AdminUser {
  id: string;
  displayName: string;
  email: string;
  role: "user" | "admin";
  status: UserStatus;
  kycStatus: KycStatus;
  country: string;
  registeredAt: string;
  lastLoginAt: string;
  portfolioUsd: number;
}

export interface KycRecord {
  id: string;
  userId: string;
  displayName: string;
  status: KycStatus;
  tier: "Tier 0" | "Tier 1" | "Tier 2";
  documentType: string;
  submittedAt: string;
  reviewer: string | null;
  riskScore: number; // 0-100
}

export interface AdminAsset {
  id: string;
  symbol: string;
  name: string;
  network: string;
  status: AssetStatus;
  withdrawalEnabled: boolean;
  depositEnabled: boolean;
  circulatingOnPlatform: number;
  minWithdrawal: number;
}

export interface AdminMarket {
  id: string;
  symbol: string;
  base: string;
  quote: string;
  status: MarketStatus;
  makerFeeBps: number;
  takerFeeBps: number;
  dailyVolumeUsd: number;
  lastPrice: number;
}

export interface AdminOrder {
  id: string;
  userDisplayName: string;
  symbol: string;
  side: "buy" | "sell";
  type: "market" | "limit";
  price: number;
  size: number;
  filled: number;
  status: AdminOrderStatus;
  createdAt: string;
}

export interface RiskControl {
  id: string;
  name: string;
  description: string;
  category: "Balance" | "Position" | "Rate Limit" | "Market";
  status: RiskControlStatus;
  threshold: string;
  triggeredLast24h: number;
}

export interface AuditLogEntry {
  id: string;
  actor: string;
  action: string;
  target: string;
  severity: AuditSeverity;
  ip: string;
  ts: string;
}
