"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useActionState, useState } from "react";
import { signIn, signUp, type AuthFormState } from "@/lib/auth-actions";

export function AuthForm({ mode }: { mode: "sign-in" | "sign-up" }) {
  const signingUp = mode === "sign-up";
  const [state, action, pending] = useActionState<AuthFormState, FormData>(signingUp ? signUp : signIn, undefined);
  const [showPassword, setShowPassword] = useState(false);
  const next = useSearchParams().get("next") ?? "/";
  const otherHref = `${signingUp ? "/sign-in" : "/sign-up"}${next !== "/" ? `?next=${encodeURIComponent(next)}` : ""}`;

  return (
    <form action={action} className="space-y-5" noValidate>
      <input type="hidden" name="next" value={next} />
      {signingUp && (
        <div>
          <label htmlFor="name" className="label">
            Name <span className="font-normal text-slate-500">(optional)</span>
          </label>
          <input id="name" name="name" autoComplete="name" maxLength={80} defaultValue={state?.name} className="field" />
        </div>
      )}
      <div>
        <label htmlFor="email" className="label">
          Email
        </label>
        <input
          id="email"
          name="email"
          type="email"
          autoComplete="email"
          required
          defaultValue={state?.email}
          className="field"
          placeholder="you@example.com"
        />
      </div>
      <div>
        <div className="flex items-baseline justify-between">
          <label htmlFor="password" className="label">
            Password
          </label>
          <button
            type="button"
            onClick={() => setShowPassword((s) => !s)}
            className="text-xs font-medium text-blue-700 hover:underline dark:text-blue-400"
          >
            {showPassword ? "Hide" : "Show"}
          </button>
        </div>
        <input
          id="password"
          name="password"
          type={showPassword ? "text" : "password"}
          autoComplete={signingUp ? "new-password" : "current-password"}
          required
          minLength={signingUp ? 10 : undefined}
          maxLength={128}
          className="field"
          aria-describedby={signingUp ? "password-hint" : undefined}
        />
        {signingUp && (
          <p id="password-hint" className="mt-1.5 text-xs text-slate-500">
            At least 10 characters. A short sentence you&apos;ll remember works well.
          </p>
        )}
      </div>

      {state?.error && (
        <p role="alert" className="alert-error">
          {state.error}
        </p>
      )}

      <button type="submit" disabled={pending} className="btn-primary w-full">
        {pending ? (signingUp ? "Creating your account…" : "Signing in…") : signingUp ? "Create account" : "Sign in"}
      </button>

      <p className="muted text-center text-sm">
        {signingUp ? "Already have an account? " : "New here? "}
        <Link href={otherHref} className="font-semibold text-blue-700 hover:underline dark:text-blue-400">
          {signingUp ? "Sign in" : "Create an account"}
        </Link>
      </p>
    </form>
  );
}
