import Link from "next/link";
import { signOut } from "@/lib/auth-actions";
import { getCurrentUser } from "@/lib/session";

/** Header account area. Reads the session, so render it inside <Suspense>. */
export async function UserMenu() {
  const user = await getCurrentUser();
  if (!user) {
    return (
      <div className="flex items-center gap-1.5">
        <Link href="/sign-in" className="btn-ghost btn-sm">
          Sign in
        </Link>
        {/* Hidden on phones so the header fits; the sign-in page links to sign-up. */}
        <span className="hidden sm:block">
          <Link href="/sign-up" className="btn-primary btn-sm">
            Create account
          </Link>
        </span>
      </div>
    );
  }
  const label = user.name || user.email;
  return (
    <div className="flex items-center gap-2">
      <span className="flex items-center gap-2 text-sm">
        <span
          aria-hidden
          className="flex h-8 w-8 items-center justify-center rounded-full bg-blue-100 text-xs font-semibold text-blue-800 uppercase dark:bg-blue-950 dark:text-blue-300"
        >
          {label.slice(0, 1)}
        </span>
        <span className="hidden max-w-40 truncate font-medium md:inline" title={user.email}>
          {label}
        </span>
        {user.isAdmin && (
          <span className="hidden rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-semibold text-amber-800 sm:inline dark:bg-amber-950 dark:text-amber-300">
            Admin
          </span>
        )}
      </span>
      <form action={signOut}>
        <button type="submit" className="btn-ghost btn-sm">
          Sign out
        </button>
      </form>
    </div>
  );
}
