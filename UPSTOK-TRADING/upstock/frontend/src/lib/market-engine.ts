import type { Candle, OrderBookLevel, OrderBookSnapshot, SymbolMeta, Ticker, Trade } from "@/types/trading";

/**
 * Simulated real-time market-data engine.
 *
 * This stands in for the WebSocket market-data gateway described in the
 * roadmap (phase 5). It exposes the same shape a real feed would -- a
 * subscribe/unsubscribe pub-sub API delivering ticker, order-book, trade,
 * and candle events -- so swapping this module for a real `WebSocket`
 * connection later is a drop-in change for any component built against it.
 * Everything below is randomly generated, client-side, no network calls.
 */

export const SYMBOLS: SymbolMeta[] = [
  { symbol: "BTC-USDT", base: "BTC", quote: "USDT", displayName: "BTC/USDT", pricePrecision: 2, sizePrecision: 5, seedPrice: 64_218.5, minNotional: 10 },
  { symbol: "ETH-USDT", base: "ETH", quote: "USDT", displayName: "ETH/USDT", pricePrecision: 2, sizePrecision: 4, seedPrice: 3_412.8, minNotional: 10 },
  { symbol: "SOL-USDT", base: "SOL", quote: "USDT", displayName: "SOL/USDT", pricePrecision: 3, sizePrecision: 3, seedPrice: 148.62, minNotional: 5 },
  { symbol: "XRP-USDT", base: "XRP", quote: "USDT", displayName: "XRP/USDT", pricePrecision: 4, sizePrecision: 1, seedPrice: 0.5231, minNotional: 5 },
];

export function symbolMeta(symbol: string): SymbolMeta {
  return SYMBOLS.find((s) => s.symbol === symbol) ?? SYMBOLS[0]!;
}

type Listener<T> = (payload: T) => void;

function uid(prefix: string): string {
  return `${prefix}_${Math.random().toString(36).slice(2, 10)}`;
}

function round(value: number, precision: number): number {
  const f = 10 ** precision;
  return Math.round(value * f) / f;
}

interface SymbolState {
  meta: SymbolMeta;
  price: number;
  open24h: number;
  high24h: number;
  low24h: number;
  volume24h: number;
  book: OrderBookSnapshot;
  trades: Trade[];
  candles: Candle[]; // 1-minute candles, oldest first
}

const BOOK_DEPTH = 14;
const CANDLE_HISTORY_MINUTES = 180;
const TICK_INTERVAL_MS = 900;

function buildBook(symbol: string, midPrice: number, precision: number): OrderBookSnapshot {
  const tick = midPrice * 0.0004;
  const bids: OrderBookLevel[] = [];
  const asks: OrderBookLevel[] = [];
  let bidTotal = 0;
  let askTotal = 0;

  for (let i = 0; i < BOOK_DEPTH; i++) {
    const bidPrice = round(midPrice - tick * (i + 1) - Math.random() * tick * 0.4, precision);
    const askPrice = round(midPrice + tick * (i + 1) + Math.random() * tick * 0.4, precision);
    const bidSize = round(Math.random() * (BOOK_DEPTH - i) * 0.9 + 0.02, 4);
    const askSize = round(Math.random() * (BOOK_DEPTH - i) * 0.9 + 0.02, 4);
    bidTotal += bidSize;
    askTotal += askSize;
    bids.push({ price: bidPrice, size: bidSize, total: round(bidTotal, 4) });
    asks.push({ price: askPrice, size: askSize, total: round(askTotal, 4) });
  }

  return { symbol, bids, asks, updatedAt: Date.now() };
}

function seedCandles(seedPrice: number): Candle[] {
  const candles: Candle[] = [];
  let price = seedPrice * (1 - (Math.random() * 0.02 - 0.01));
  const nowMinute = Math.floor(Date.now() / 60_000) * 60_000;
  for (let i = CANDLE_HISTORY_MINUTES - 1; i >= 0; i--) {
    const time = nowMinute - i * 60_000;
    const drift = (Math.random() - 0.5) * price * 0.006;
    const open = price;
    const close = Math.max(price * 0.5, price + drift);
    const high = Math.max(open, close) + Math.random() * price * 0.0025;
    const low = Math.min(open, close) - Math.random() * price * 0.0025;
    const volume = Math.random() * 40 + 5;
    candles.push({ time, open, high, low, close, volume });
    price = close;
  }
  return candles;
}

class MarketDataEngine {
  private symbols = new Map<string, SymbolState>();
  private tickerListeners = new Map<string, Set<Listener<Ticker>>>();
  private bookListeners = new Map<string, Set<Listener<OrderBookSnapshot>>>();
  private tradeListeners = new Map<string, Set<Listener<Trade>>>();
  private candleListeners = new Map<string, Set<Listener<Candle[]>>>();
  private timer: ReturnType<typeof setInterval> | null = null;
  private subscriberCount = 0;

  constructor() {
    for (const meta of SYMBOLS) {
      const candles = seedCandles(meta.seedPrice);
      const price = candles[candles.length - 1]!.close;
      this.symbols.set(meta.symbol, {
        meta,
        price,
        open24h: meta.seedPrice * (1 - (Math.random() * 0.03 - 0.015)),
        high24h: price * (1 + Math.random() * 0.02),
        low24h: price * (1 - Math.random() * 0.02),
        volume24h: Math.random() * 50_000_000 + 5_000_000,
        book: buildBook(meta.symbol, price, meta.pricePrecision),
        trades: [],
        candles,
      });
    }
  }

  private ensureRunning() {
    if (this.timer) return;
    this.timer = setInterval(() => this.tick(), TICK_INTERVAL_MS);
  }

  private maybeStop() {
    if (this.subscriberCount <= 0 && this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
  }

  private tick() {
    for (const state of this.symbols.values()) {
      this.tickSymbol(state);
    }
  }

  private tickSymbol(state: SymbolState) {
    const { meta } = state;
    const volatility = state.price * 0.0012;
    const drift = (Math.random() - 0.498) * volatility;
    const prevPrice = state.price;
    state.price = Math.max(meta.seedPrice * 0.01, round(state.price + drift, meta.pricePrecision));
    state.high24h = Math.max(state.high24h, state.price);
    state.low24h = Math.min(state.low24h, state.price);
    state.volume24h += Math.random() * 1200;

    // Order book: rebuild around new mid price so depth stays realistic.
    state.book = buildBook(meta.symbol, state.price, meta.pricePrecision);
    this.emitBook(meta.symbol, state.book);

    // Trades: emit ~60% of ticks.
    if (Math.random() < 0.6) {
      const side: Trade["side"] = state.price >= prevPrice ? "buy" : "sell";
      const trade: Trade = {
        id: uid("trd"),
        symbol: meta.symbol,
        price: state.price,
        size: round(Math.random() * 2.4 + 0.001, meta.sizePrecision),
        side,
        ts: Date.now(),
      };
      state.trades = [trade, ...state.trades].slice(0, 60);
      this.emitTrade(meta.symbol, trade);
    }

    // Candles: update current minute bucket, roll a new one when the
    // minute changes.
    const bucket = Math.floor(Date.now() / 60_000) * 60_000;
    const last = state.candles[state.candles.length - 1];
    if (last && last.time === bucket) {
      last.close = state.price;
      last.high = Math.max(last.high, state.price);
      last.low = Math.min(last.low, state.price);
      last.volume += Math.random() * 3;
    } else {
      state.candles.push({
        time: bucket,
        open: prevPrice,
        high: Math.max(prevPrice, state.price),
        low: Math.min(prevPrice, state.price),
        close: state.price,
        volume: Math.random() * 3,
      });
      if (state.candles.length > CANDLE_HISTORY_MINUTES) state.candles.shift();
    }
    this.emitCandles(meta.symbol, state.candles);

    this.emitTicker(meta.symbol, {
      symbol: meta.symbol,
      price: state.price,
      prevPrice,
      changePct: ((state.price - state.open24h) / state.open24h) * 100,
      high24h: state.high24h,
      low24h: state.low24h,
      volume24h: state.volume24h,
    });
  }

  private emitTicker(symbol: string, payload: Ticker) {
    this.tickerListeners.get(symbol)?.forEach((cb) => cb(payload));
  }
  private emitBook(symbol: string, payload: OrderBookSnapshot) {
    this.bookListeners.get(symbol)?.forEach((cb) => cb(payload));
  }
  private emitTrade(symbol: string, payload: Trade) {
    this.tradeListeners.get(symbol)?.forEach((cb) => cb(payload));
  }
  private emitCandles(symbol: string, payload: Candle[]) {
    this.candleListeners.get(symbol)?.forEach((cb) => cb([...payload]));
  }

  getTicker(symbol: string): Ticker {
    const s = this.symbols.get(symbol)!;
    return {
      symbol,
      price: s.price,
      prevPrice: s.price,
      changePct: ((s.price - s.open24h) / s.open24h) * 100,
      high24h: s.high24h,
      low24h: s.low24h,
      volume24h: s.volume24h,
    };
  }

  getAllTickers(): Ticker[] {
    return SYMBOLS.map((m) => this.getTicker(m.symbol));
  }

  getBook(symbol: string): OrderBookSnapshot {
    return this.symbols.get(symbol)!.book;
  }

  getTrades(symbol: string): Trade[] {
    return this.symbols.get(symbol)!.trades;
  }

  getCandles(symbol: string): Candle[] {
    return [...this.symbols.get(symbol)!.candles];
  }

  private subscribe<T>(map: Map<string, Set<Listener<T>>>, symbol: string, cb: Listener<T>): () => void {
    this.subscriberCount += 1;
    this.ensureRunning();
    if (!map.has(symbol)) map.set(symbol, new Set());
    map.get(symbol)!.add(cb);
    return () => {
      map.get(symbol)?.delete(cb);
      this.subscriberCount -= 1;
      this.maybeStop();
    };
  }

  subscribeTicker(symbol: string, cb: Listener<Ticker>) {
    return this.subscribe(this.tickerListeners, symbol, cb);
  }
  subscribeBook(symbol: string, cb: Listener<OrderBookSnapshot>) {
    return this.subscribe(this.bookListeners, symbol, cb);
  }
  subscribeTrades(symbol: string, cb: Listener<Trade>) {
    return this.subscribe(this.tradeListeners, symbol, cb);
  }
  subscribeCandles(symbol: string, cb: Listener<Candle[]>) {
    return this.subscribe(this.candleListeners, symbol, cb);
  }

  /** Execute a demo market order immediately against the current book/price. */
  executeMarketOrder(symbol: string, side: "buy" | "sell", size: number): { avgPrice: number } {
    const state = this.symbols.get(symbol)!;
    const levels = side === "buy" ? state.book.asks : state.book.bids;
    let remaining = size;
    let notional = 0;
    for (const level of levels) {
      const fillSize = Math.min(remaining, level.size);
      notional += fillSize * level.price;
      remaining -= fillSize;
      if (remaining <= 0) break;
    }
    const avgPrice = notional / Math.max(size - Math.max(remaining, 0), 1e-9) || state.price;
    return { avgPrice: round(avgPrice, state.meta.pricePrecision) };
  }
}

// Singleton -- safe on the server because it never starts its interval
// until something subscribes, and Next.js client components own the
// subscribe/unsubscribe lifecycle via useEffect.
export const marketEngine = new MarketDataEngine();
