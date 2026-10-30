import { Suspense } from "react";
import { AuthForm } from "./AuthForm";
import { Icon } from "./Icon";

export function AuthCard({ mode }: { mode: "sign-in" | "sign-up" }) {
  const signingUp = mode === "sign-up";
  return (
    <div className="auth-layout">
      <aside className="auth-story"><span className="feature-icon"><Icon name="shield" className="h-6 w-6" /></span><h2>Your next chapter.<br /><em>A little more clarity.</em></h2><p>Keep your checks together, revisit the details and take your next step with a clearer picture.</p><ul className="auth-benefits"><li><Icon name="file" />All your reports, in one place</li><li><Icon name="lock" />Access through your account</li><li><Icon name="globe" />Pick up from any device</li></ul></aside>
      <div>
        <div className="auth-form-heading"><p className="eyebrow mb-3">Your space to check</p><h1>{signingUp ? "A safer start." : "Good to see you again."}</h1><p>{signingUp ? "Create an account to save your checks and come back to your reports whenever you need." : "Sign in to pick up where you left off and find your saved reports."}</p></div>
        <div className="card p-6 sm:p-8"><Suspense fallback={<div className="h-72 animate-pulse rounded-xl bg-blue-50 dark:bg-blue-950" />}><AuthForm mode={mode} /></Suspense></div>
        <p className="auth-note">Just checking an offer? You can run a check without an account.</p>
      </div>
    </div>
  );
}
