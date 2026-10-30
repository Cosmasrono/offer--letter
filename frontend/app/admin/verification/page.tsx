import { Suspense } from "react";
import Link from "next/link";
import { NEASettings } from "@/components/NEASettings";
import { getCurrentUser } from "@/lib/session";

async function Settings() {
  const user = await getCurrentUser();
  if (!user?.isAdmin) return <div className="card p-6"><h2 className="font-semibold">Administrator access required</h2><p className="muted mt-2 text-sm">Sign in with a site administrator account to maintain registry data.</p><Link href="/sign-in?next=/admin/verification" className="btn-primary mt-4">Sign in</Link></div>;
  return <NEASettings />;
}

export default function VerificationSettings() {
  return <div className="mx-auto max-w-2xl space-y-6"><Link href="/history" className="text-sm underline">← Report history</Link><div><p className="eyebrow">Administration</p><h1 className="text-3xl font-semibold">Verification sources</h1></div><Suspense fallback={<p>Loading source settings…</p>}><Settings /></Suspense></div>;
}
