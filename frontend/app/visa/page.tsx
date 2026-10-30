import type { Metadata } from "next";
import Link from "next/link";
import { VisaUpload } from "@/components/VisaUpload";
import { reportPriceKes } from "@/lib/payments";

export const metadata: Metadata = { title: "Visa and offer comparison · Offer Letter Checker" };

export default function VisaPage() {
  return <div className="mx-auto max-w-3xl space-y-6"><Link href="/" className="text-sm underline">← Offer letter checker</Link><div><p className="eyebrow">Before you pay or travel</p><h1 className="mt-3 text-3xl font-semibold sm:text-4xl">Check your visa. Compare your offer.</h1><p className="muted mt-4 leading-relaxed">Review Qatar or Kuwait visa details for validity concerns and differences from your offer letter. Get clear next steps for checking the official government record.</p></div><VisaUpload priceKes={reportPriceKes()} /></div>;
}
