"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import type { ScamStatus } from "@/lib/types";

type State = "idle" | "confirm" | "sending" | "done" | "reviewed" | "error";

export function ReportScamButton({ reportId, alreadyReported, scamStatus }: { reportId: string; alreadyReported: boolean; scamStatus?: ScamStatus }) {
  const router = useRouter();
  const [state, setState] = useState<State>(alreadyReported ? "done" : "idle");
  const [error, setError] = useState<string | null>(null);

  async function send() {
    setState("sending");
    try {
      const res = await fetch("/api/report-scam", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: reportId }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "Something went wrong.");
      setState(data.status === "reviewed" ? "reviewed" : "done");
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
      setState("error");
    }
  }

  if (scamStatus === "CONFIRMED_SCAM" || scamStatus === "CLEARED" || state === "reviewed") return <p className="text-sm font-medium">This letter has a review decision. See its tracked status.</p>;
  if (state === "done") {
    return (
      <p className="text-sm font-medium text-slate-700 dark:text-slate-300">
        ✓ Reported scam — awaiting review. Matching details can warn others, with the report marked as unconfirmed.
      </p>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-3 text-sm">
      {state === "confirm" || state === "sending" ? (
        <>
          <span>Are you sure this letter is a scam?</span>
          <button
            type="button"
            onClick={send}
            disabled={state === "sending"}
            className="btn btn-sm bg-red-600 text-white hover:bg-red-700"
          >
            {state === "sending" ? "Reporting…" : "Yes, report it"}
          </button>
          <button type="button" onClick={() => setState("idle")} className="btn-ghost btn-sm">
            Cancel
          </button>
        </>
      ) : (
        <>
          <button
            type="button"
            onClick={() => setState("confirm")}
            className="btn-secondary btn-sm"
          >
            Report as scam
          </button>
          <span className="text-xs text-slate-500">Know it&apos;s fake? Reporting it warns others.</span>
          {state === "error" && <span className="w-full text-red-700 dark:text-red-400">{error}</span>}
        </>
      )}
    </div>
  );
}
