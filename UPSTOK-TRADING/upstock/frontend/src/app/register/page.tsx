"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { AuthCard, ErrorBanner, FieldLabel, SubmitButton, TextInput } from "@/components/AuthCard";
import { useAuth } from "@/lib/auth-context";

export default function RegisterPage() {
  const { register, login, error, clearError } = useAuth();
  const router = useRouter();
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setIsSubmitting(true);
    try {
      await register(email, password, displayName);
      await login(email, password);
      router.push("/dashboard");
    } catch {
      // error state is already surfaced via useAuth().error
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <AuthCard
      eyebrow="Sandbox trading"
      title="Create your account"
      subtitle="Paper funds only until full verification clears."
    >
      {error && <ErrorBanner message={error} />}
      <form onSubmit={handleSubmit} noValidate>
        <div className="mb-4">
          <FieldLabel htmlFor="displayName">Display name</FieldLabel>
          <TextInput
            id="displayName"
            type="text"
            autoComplete="name"
            required
            minLength={2}
            value={displayName}
            onChange={(e) => {
              clearError();
              setDisplayName(e.target.value);
            }}
          />
        </div>
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
        <div className="mb-2">
          <FieldLabel htmlFor="password">Password</FieldLabel>
          <TextInput
            id="password"
            type="password"
            autoComplete="new-password"
            required
            minLength={10}
            value={password}
            onChange={(e) => {
              clearError();
              setPassword(e.target.value);
            }}
          />
        </div>
        <p className="mb-6 text-xs text-ink-muted">
          At least 10 characters, with an uppercase letter, a lowercase letter, and a digit.
        </p>
        <SubmitButton type="submit" disabled={isSubmitting}>
          {isSubmitting ? "Creating account\u2026" : "Create account"}
        </SubmitButton>
      </form>
      <p className="mt-6 text-center text-sm text-ink-muted">
        Already have an account?{" "}
        <Link href="/login" className="text-signal hover:underline">
          Sign in
        </Link>
      </p>
    </AuthCard>
  );
}
