import { TickerTape } from "@/components/TickerTape";

export function AuthCard({
  eyebrow,
  title,
  subtitle,
  children,
}: {
  eyebrow: string;
  title: string;
  subtitle: string;
  children: React.ReactNode;
}) {
  return (
    <main className="terminal-grid flex min-h-screen flex-col bg-void">
      <TickerTape />
      <div className="flex flex-1 items-center justify-center px-6 py-16">
        <div className="w-full max-w-md">
          <div className="mb-8 text-center">
            <p className="mb-2 font-mono text-xs uppercase tracking-[0.25em] text-signal">{eyebrow}</p>
            <h1 className="font-display text-3xl font-medium text-ink">{title}</h1>
            <p className="mt-2 text-sm text-ink-muted">{subtitle}</p>
          </div>

          <div className="rounded-lg border border-hairline bg-panel p-8 shadow-[0_0_0_1px_rgba(0,0,0,0.2)]">
            {children}
          </div>
        </div>
      </div>
    </main>
  );
}

export function FieldLabel({ htmlFor, children }: { htmlFor: string; children: React.ReactNode }) {
  return (
    <label htmlFor={htmlFor} className="mb-1.5 block text-sm text-ink-muted">
      {children}
    </label>
  );
}

export function TextInput(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={`w-full rounded-md border border-hairline bg-panel-raised px-3 py-2 text-ink placeholder:text-ink-muted/60 focus:border-signal focus:outline-none focus:ring-1 focus:ring-signal ${props.className ?? ""}`}
    />
  );
}

export function SubmitButton({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...props}
      className="w-full rounded-md bg-signal px-4 py-2.5 font-medium text-void transition hover:bg-signal/90 disabled:cursor-not-allowed disabled:opacity-50"
    >
      {children}
    </button>
  );
}

export function ErrorBanner({ message }: { message: string }) {
  return (
    <div role="alert" className="mb-4 rounded-md border border-sell/30 bg-sell/10 px-3 py-2 text-sm text-sell">
      {message}
    </div>
  );
}
