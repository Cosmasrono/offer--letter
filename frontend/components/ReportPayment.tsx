"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { Icon } from "./Icon";

type Props = { reportId: string; priceKes: number; paymentsReady: boolean; attemptedToken?: string };
type PaymentStep = "form" | "sending" | "waiting" | "opening";
const tokenKey = (id: string) => `olc-report-download-${id}`;
const pendingKey = (id: string) => `olc-report-payment-${id}`;

function readStored(key: string) {
  try { return localStorage.getItem(key); } catch { return null; }
}
function writeStored(key: string, value: string | null) {
  try {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch { /* Payment still works when browser storage is unavailable. */ }
}

/** Contains only a report ID and price. Findings never enter this component before payment. */
export function ReportPayment({ reportId, priceKes, paymentsReady, attemptedToken = "" }: Props) {
  const router = useRouter();
  const dialogRef = useRef<HTMLDialogElement>(null);
  const pollTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mounted = useRef(false);
  const submitting = useRef(false);
  const [phone, setPhone] = useState("");
  const [step, setStep] = useState<PaymentStep>("form");
  const [error, setError] = useState<string | null>(null);

  const openPaidReport = useCallback((token: string) => {
    if (!/^[a-f0-9]{48}$/.test(token)) throw new Error("Payment confirmation is incomplete. Please check again shortly.");
    writeStored(tokenKey(reportId), token);
    writeStored(pendingKey(reportId), null);
    setStep("opening");
    router.replace(`/report/${reportId}?token=${encodeURIComponent(token)}`, { scroll: false });
  }, [reportId, router]);

  const pollPayment = useCallback(async function poll(paymentId: string) {
    try {
      const response = await fetch(`/api/payments?id=${paymentId}`, { cache: "no-store" });
      const result = await response.json();
      if (!mounted.current) return;
      if (response.ok && result.status === "SUCCESS") {
        openPaidReport(result.downloadToken);
        return;
      }
      if (!response.ok || result.status === "FAILED") {
        writeStored(pendingKey(reportId), null);
        setStep("form");
        setError(result.message ?? result.error ?? "The payment did not go through. You can try again.");
        return;
      }
    } catch {
      // An intermittent connection never unlocks a report. Re-check the same payment.
    }
    if (mounted.current) pollTimer.current = setTimeout(() => void poll(paymentId), 4000);
  }, [openPaidReport, reportId]);

  useEffect(() => {
    mounted.current = true;
    const dialog = dialogRef.current;
    const saved = readStored(tokenKey(reportId));
    if (saved && saved !== attemptedToken && /^[a-f0-9]{48}$/.test(saved)) {
      // The server checks this remembered token before it will send any findings.
      router.replace(`/report/${reportId}?token=${encodeURIComponent(saved)}`, { scroll: false });
    } else {
      dialog?.showModal();
      dialog?.querySelector<HTMLInputElement>("input")?.focus();
      const pending = readStored(pendingKey(reportId));
      if (pending && /^[a-f0-9]{24}$/i.test(pending)) {
        pollTimer.current = setTimeout(() => {
          setStep("waiting");
          void pollPayment(pending);
        }, 0);
      }
    }
    return () => {
      mounted.current = false;
      if (pollTimer.current) clearTimeout(pollTimer.current);
      dialog?.close();
    };
  }, [attemptedToken, pollPayment, reportId, router]);

  async function pay(event: React.FormEvent) {
    event.preventDefault();
    if (submitting.current) return;
    if (!/^(?:\+?254|0)?[17]\d{8}$/.test(phone.replace(/[\s()-]/g, ""))) {
      setError("Enter a valid M-Pesa number, such as 0712 345 678.");
      return;
    }
    submitting.current = true;
    setError(null);
    setStep("sending");
    try {
      const response = await fetch("/api/payments", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reportId, phone }),
      });
      const result = await response.json();
      if (!mounted.current) return;
      if (!response.ok) throw new Error(result.error ?? "The M-Pesa prompt could not be sent. Please try again.");
      if (result.status === "SUCCESS") return openPaidReport(result.downloadToken);
      if (!/^[a-f0-9]{24}$/i.test(result.paymentId)) throw new Error("The payment could not be started. Please try again.");
      writeStored(pendingKey(reportId), result.paymentId);
      setStep("waiting");
      pollTimer.current = setTimeout(() => void pollPayment(result.paymentId), 2000);
    } catch (failure) {
      if (!mounted.current) return;
      setStep("form");
      setError(failure instanceof Error ? failure.message : "The payment could not be started. Please try again.");
    } finally {
      submitting.current = false;
    }
  }

  const waiting = step === "waiting" || step === "opening";
  return (
    <div className="payment-gate">
      <div className="card mx-auto max-w-xl p-8 text-center sm:p-12">
        <span className="feature-icon mx-auto mb-5"><Icon name="lock" /></span>
        <p className="eyebrow">Scan complete</p>
        <h1 className="mt-3 text-3xl font-medium tracking-tight">Your findings are ready.</h1>
        <p className="muted mt-4 text-sm leading-relaxed">Unlock your risk assessment, findings, next steps and PDF report with one M-Pesa payment of <strong>KES {priceKes}</strong>.</p>
        <button type="button" className="btn-primary mt-6" onClick={() => dialogRef.current?.showModal()}>Unlock my report <Icon name="arrow" className="h-4 w-4" /></button>
        <p className="muted mt-4 text-xs">Your findings stay hidden until payment is confirmed.</p>
      </div>
      <dialog ref={dialogRef} className="payment-dialog" aria-labelledby="payment-title" aria-describedby="payment-description">
        <button type="button" className="payment-close btn-ghost btn-sm" aria-label="Close payment popup" onClick={() => dialogRef.current?.close()}><span aria-hidden>×</span></button>
        <div className="payment-dialog-content">
          <span className="feature-icon mb-5"><Icon name={waiting ? "clock" : "shield"} /></span>
          <p className="eyebrow">Scan complete · report locked</p>
          <h2 id="payment-title">One payment.<br /><em>Your complete report.</em></h2>
          <p id="payment-description" className="muted mt-3 text-sm leading-relaxed">The scan has finished. Pay by M-Pesa to reveal the findings and download your PDF.</p>
          <div className="payment-total"><div><strong>Full report + PDF</strong><span>One payment. No extra download fee.</span></div><strong>KES {priceKes}</strong></div>
          {step === "opening" ? <p role="status" className="payment-waiting"><Icon name="check" />Payment confirmed. Opening your report…</p>
            : step === "waiting" ? <div role="status" className="payment-waiting"><span aria-hidden className="payment-spinner" /><div><strong>Check your phone</strong><p>Enter your M-Pesa PIN on your phone to pay KES {priceKes}. Your findings open after payment is confirmed.</p><p className="mt-3 text-xs">Keep this page open. We&apos;re checking the payment status.</p></div></div>
            : !paymentsReady ? <p role="alert" className="alert-error">M-Pesa payments are currently unavailable. Your report stays saved and locked. Please try again later.</p>
            : <form onSubmit={pay} className="space-y-4">
              <div><label htmlFor="unlock-phone" className="label">M-Pesa phone number</label><input id="unlock-phone" type="tel" inputMode="tel" autoComplete="tel" required maxLength={20} value={phone} onChange={(event) => setPhone(event.target.value)} placeholder="0712 345 678" className="field" disabled={step === "sending"} autoFocus /><p className="muted mt-2 text-xs">We&apos;ll send a payment prompt to this number.</p></div>
              {error && <p role="alert" className="alert-error">{error}</p>}
              <button type="submit" disabled={step === "sending"} className="btn-primary h-12 w-full">{step === "sending" ? "Sending M-Pesa prompt…" : `Pay KES ${priceKes} & unlock report`}<Icon name="arrow" className="h-4 w-4" /></button>
            </form>}
          <p className="upload-privacy mt-5"><Icon name="lock" className="h-3 w-3" />Enter your PIN only in the M-Pesa prompt on your phone.</p>
          <button type="button" className="payment-later" onClick={() => dialogRef.current?.close()}>Not now — keep my report locked</button>
        </div>
      </dialog>
    </div>
  );
}
