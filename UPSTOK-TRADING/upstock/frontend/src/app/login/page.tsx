"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { AuthCard, ErrorBanner, FieldLabel, SubmitButton, TextInput } from "@/components/AuthCard";
import { useAuth } from "@/lib/auth-context";

export default function LoginPage() {
  const { login, error, clearError } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setIsSubmitting(true);
    try {
      await login(email, password);
      router.push("/dashboard");
    } catch {
      // error state is already surfaced via useAuth().error
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <AuthCard eyebrow="Welcome back" title="Sign in" subtitle="Access your portfolio and open orders.">
      {error && <ErrorBanner message={error} />}
      <form onSubmit={handleSubmit} noValidate>
        <div className="mb-4">
          <FieldLabel htmlFor="email">Email</FieldLabel>
          <TextInput
            id="email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => {
              clearError();
              setEmail(e.target.value);
            }}
          />
        </div>
        <div className="mb-6">
          <FieldLabel htmlFor="password">Password</FieldLabel>
          <TextInput
            id="password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => {
              clearError();
              setPassword(e.target.value);
            }}
          />
        </div>
        <SubmitButton type="submit" disabled={isSubmitting}>
          {isSubmitting ? "Signing in\u2026" : "Sign in"}
        </SubmitButton>
      </form>
      <p className="mt-6 text-center text-sm text-ink-muted">
        New here?{" "}
        <Link href="/register" className="text-signal hover:underline">
          Create an account
        </Link>
      </p>
    </AuthCard>
  );
}
