export type Side = "buy" | "sell";
export type OrderType = "market" | "limit";
export type OrderStatus = "open" | "filled" | "cancelled" | "partially_filled";

export interface SymbolMeta {
  symbol: string; // "BTC-USDT"
  base: string; // "BTC"
  quote: string; // "USDT"
  displayName: string; // "BTC/USDT"
  pricePrecision: number;
  sizePrecision: number;
  seedPrice: number;
  minNotional: number;
}

export interface OrderBookLevel {
  price: number;
  size: number;
  total: number;
}

export interface OrderBookSnapshot {
  symbol: string;
  bids: OrderBookLevel[];
  asks: OrderBookLevel[];
  updatedAt: number;
}

export interface Trade {
  id: string;
  symbol: string;
  price: number;
  size: number;
  side: Side;
  ts: number;
}

export interface Candle {
  time: number; // minute bucket, ms epoch
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface Ticker {
  symbol: string;
  price: number;
  prevPrice: number;
  changePct: number;
  high24h: number;
  low24h: number;
  volume24h: number;
}

export interface DemoOrder {
  id: string;
  symbol: string;
  side: Side;
  type: OrderType;
  price: number | null; // null for market orders (executes at book price)
  size: number;
  filledSize: number;
  status: OrderStatus;
  createdAt: number;
}

export interface Position {
  symbol: string;
  base: string;
  qty: number;
  avgEntryPrice: number;
}

export interface Balances {
  [asset: string]: number;
}
