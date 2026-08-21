const MOCK_TICKER = [
  { pair: "BTC/USDT", price: "64,218.50", change: "+2.14%", up: true },
  { pair: "ETH/USDT", price: "3,412.80", change: "+1.08%", up: true },
  { pair: "SOL/USDT", price: "148.62", change: "-0.76%", up: false },
  { pair: "XRP/USDT", price: "0.5231", change: "+0.42%", up: true },
  { pair: "BNB/USDT", price: "586.10", change: "-1.22%", up: false },
  { pair: "ADA/USDT", price: "0.4118", change: "+0.19%", up: true },
];

function TickerRow({ keyPrefix }: { keyPrefix: string }) {
  return (
    <>
      {MOCK_TICKER.map((row) => (
        <span key={`${keyPrefix}-${row.pair}`} className="mx-6 inline-flex items-baseline gap-2 font-mono text-sm">
          <span className="text-ink-muted">{row.pair}</span>
          <span className="text-ink">{row.price}</span>
          <span className={row.up ? "text-buy" : "text-sell"}>{row.change}</span>
        </span>
      ))}
    </>
  );
}

/**
 * Ambient, non-interactive price ticker. Purely atmospheric -- this is mock
 * data, not a live feed (that arrives later via the market-data WebSocket
 * gateway) -- but it's the one place on the auth screens we let the
 * platform's real subject matter (a live order book) speak for itself.
 */
export function TickerTape() {
  return (
    <div
      className="w-full overflow-hidden border-b border-hairline bg-panel/60 py-2"
      role="presentation"
      aria-hidden="true"
    >
      <div className="ticker-track flex w-max whitespace-nowrap">
        <TickerRow keyPrefix="a" />
        <TickerRow keyPrefix="b" />
      </div>
    </div>
  );
}
