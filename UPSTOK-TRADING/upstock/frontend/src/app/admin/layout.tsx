"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { AppHeader } from "@/components/AppHeader";
import { AdminShell } from "@/components/admin/AdminShell";

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const { user, isLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && !user) router.replace("/login");
  }, [isLoading, user, router]);

  if (isLoading || !user) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-void">
        <p className="font-mono text-sm text-ink-muted">Loading session\u2026</p>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-void">
      <AppHeader eyebrow="Admin Portal" />
      {user.role !== "admin" && (
        <div className="border-b border-signal/30 bg-signal/10 px-6 py-2 text-center font-mono text-[11px] text-signal">
          Demo mode: viewing the admin portal with a role-based-access-control concept. In production this is
          restricted to the <code>admin</code> role.
        </div>
      )}
      <AdminShell>{children}</AdminShell>
    </main>
  );
}
