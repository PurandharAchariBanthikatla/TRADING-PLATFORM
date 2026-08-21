"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";

const NAV_LINKS = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/trade", label: "Trading Terminal" },
  { href: "/admin", label: "Admin Portal" },
];

export function AppHeader({ eyebrow = "Sandbox" }: { eyebrow?: string }) {
  const { user, logout } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  return (
    <header className="sticky top-0 z-30 border-b border-hairline bg-void/95 backdrop-blur">
      <div className="flex items-center justify-between px-6 py-3">
        <div className="flex items-center gap-6">
          <Link href="/dashboard" className="flex items-baseline gap-2">
            <span className="font-display text-lg font-semibold text-ink">Upstock</span>
            <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-signal">{eyebrow}</span>
          </Link>
          <nav className="hidden items-center gap-1 sm:flex">
            {NAV_LINKS.map((link) => {
              const active = pathname?.startsWith(link.href) && (link.href !== "/dashboard" || pathname === "/dashboard");
              return (
                <Link
                  key={link.href}
                  href={link.href}
                  className={`rounded-md px-3 py-1.5 font-mono text-xs uppercase tracking-wide transition ${
                    active ? "bg-panel-raised text-signal" : "text-ink-muted hover:text-ink"
                  }`}
                >
                  {link.label}
                </Link>
              );
            })}
          </nav>
        </div>
        <div className="flex items-center gap-3">
          {user && (
            <span className="hidden font-mono text-xs text-ink-muted sm:inline">{user.display_name}</span>
          )}
          <button
            onClick={() => logout().then(() => router.push("/login"))}
            className="rounded-md border border-hairline px-3 py-1.5 text-xs text-ink transition hover:border-sell/60 hover:text-sell"
          >
            Sign out
          </button>
        </div>
      </div>
      <nav className="flex items-center gap-1 overflow-x-auto border-t border-hairline px-3 py-1.5 sm:hidden">
        {NAV_LINKS.map((link) => (
          <Link
            key={link.href}
            href={link.href}
            className="whitespace-nowrap rounded-md px-3 py-1 font-mono text-xs uppercase tracking-wide text-ink-muted hover:text-ink"
          >
            {link.label}
          </Link>
        ))}
      </nav>
    </header>
  );
}
