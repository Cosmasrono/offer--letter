"use client";

import Link from "next/link";
import { useState } from "react";
import { CONSENT_VERSION, REPORT_RETENTION_DAYS } from "@/lib/privacy-policy";
import { Icon } from "./Icon";

export function ConsentNotice({ onAccept, mode = "offer" }: { onAccept: (memoryConsent: boolean) => void; mode?: "offer" | "visa" }) {
  const [processing, setProcessing] = useState(false);
  const [authority, setAuthority] = useState(false);
  const [memory, setMemory] = useState(false);
  return (
    <div className="space-y-5 p-5 sm:p-7">
      <div><span className="feature-icon mb-4"><Icon name="shield" /></span><p className="eyebrow">Before you share</p><h3 className="mt-2 text-xl font-semibold">Your document. Your choice.</h3><p className="muted mt-3 text-sm leading-relaxed">Read how your information is used before choosing a file or pasting a message.</p></div>
      <ul className="list-disc space-y-3 pl-5 text-sm leading-relaxed">
        <li>{mode === "visa" ? "We read your visa and optional offer letter for validity concerns and differences between the documents. Official government verification guidance is provided separately." : "We read your document or message for scam warning signs and compare relevant employer and agency details with available public sources."}</li>
        <li>Our configured AI providers may receive document text, images and extracted details, including names and passport details if present. Processing may take place outside Kenya. See the <Link href="/privacy#providers" target="_blank" rel="noopener noreferrer" className="underline">provider information</Link>.</li>
        <li>Your saved report, extracted details and consent record expire after {REPORT_RETENTION_DAYS} days. You can delete the report earlier without paying. Keep this browser’s cookies if submitting without an account.</li>
        <li>This is a risk assessment. A low-risk result does not confirm that an offer or visa is genuine.</li>
      </ul>
      <p className="muted text-xs leading-relaxed">Share only what is needed. Cover unrelated personal details before submitting. Payment and account records are separate from your report; external providers have their own retention terms.</p>
      <label className="flex items-start gap-3 text-sm leading-relaxed"><input type="checkbox" checked={processing} onChange={e => setProcessing(e.target.checked)} className="mt-1 h-4 w-4 shrink-0 accent-green-800" /><span>I agree to document processing, including the external processing described above and in the <Link href="/privacy" target="_blank" rel="noopener noreferrer" className="underline">privacy notice</Link>.</span></label>
      <label className="flex items-start gap-3 text-sm leading-relaxed"><input type="checkbox" checked={authority} onChange={e => setAuthority(e.target.checked)} className="mt-1 h-4 w-4 shrink-0 accent-green-800" /><span>This is my information, or I have the person’s permission to submit it.</span></label>
      {mode === "offer" ? <label className="flex items-start gap-3 text-sm leading-relaxed"><input type="checkbox" checked={memory} onChange={e => setMemory(e.target.checked)} className="mt-1 h-4 w-4 shrink-0 accent-green-800" /><span><strong>Optional:</strong> Allow contact/payment details and wording patterns from this report, if flagged or reported, to help check other submissions during its retention period. My document text will not be shown to other users. Declining does not affect my check.</span></label> : <p className="muted text-xs">Visa reports, government form templates and personal identifiers are excluded from shared scam matching.</p>}
      <button type="button" disabled={!processing || !authority} onClick={() => onAccept(memory)} className="btn-primary w-full">Agree and continue <Icon name="arrow" className="h-4 w-4" /></button>
      <p className="muted text-xs">You can leave without submitting anything. Notice version {CONSENT_VERSION}.</p>
    </div>
  );
}
