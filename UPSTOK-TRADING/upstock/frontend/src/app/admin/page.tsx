"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function AdminIndexPage() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/admin/users");
  }, [router]);
  return <p className="font-mono text-xs text-ink-muted">Loading admin portal\u2026</p>;
}
