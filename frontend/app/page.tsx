import Link from "next/link";
import { Icon } from "@/components/Icon";
import { UploadForm } from "@/components/UploadForm";
import { RecentReports } from "@/components/RecentReports";
import { reportPriceKes } from "@/lib/payments";

const CHECKS = [
  { icon: "wallet", number: "01", title: "Follow the money", text: "Visa fees, medical charges, personal accounts. We look for payment requests that should make you pause." },
  { icon: "building", number: "02", title: "Look behind the name", text: "Recruiter details, email addresses and website age. Agency checks use the available NEA agency list." },
  { icon: "file", number: "03", title: "Read between the lines", text: "Missing terms, unusual promises and signs of PDF editing. A professional-looking letter can still raise flags." },
  { icon: "search", number: "04", title: "Connect the dots", text: "Contact details, payment accounts and wording that match earlier high-risk or reported offers." },
] as const;
const COUNTRIES = ["United Kingdom", "UAE", "Canada", "Saudi Arabia", "Qatar", "Australia", "Germany", "Poland", "United States"];

export default function Home() {
  const priceKes = reportPriceKes();
  const faqs = [
    { q: "Does a low-risk result mean the offer is real?", a: "A low-risk result means no major warning signs were found in the checks that could run. It is not a guarantee. Always contact the employer directly using details you find independently." },
    { q: "Can I check a WhatsApp message or job advert?", a: "Yes. Choose ‘Job ad or message’ in the checker, then paste the text or attach a screenshot. We adapt the checks because an advert does not need all the details of a formal offer letter." },
    { q: "When do I pay?", a: priceKes === 0 ? "Free testing is enabled. Upload your document to view the findings and download the PDF without paying." : `Scanning happens first. Once your report is ready, a popup asks for your M-Pesa number. Pay KES ${priceKes} to reveal your findings and download the PDF. Nothing is charged just for scanning.` },
    { q: "What happens if my document cannot be read?", a: priceKes === 0 ? "Upload a clearer photo or the original PDF and try again. Testing is free." : "Upload a clearer photo or the original PDF and try again. Payment is only requested after a readable document has been scanned and the report saved." },
    { q: "Who can see my report?", a: "Reports made while signed in are accessible to you and site administrators. Guest reports use private links, so keep those links and payment tokens safe. New reports expire after 30 days and can be deleted earlier. Reusing flagged contact details and wording to check other submissions is optional; choose before submitting." },
    { q: "What is included in a check?", a: `You get a risk score, the reasons behind it, suggested next steps and official verification links.${priceKes > 0 ? ` KES ${priceKes} covers one completed check and its downloadable PDF, with no additional download fee.` : " Saved reports can also be downloaded as a PDF."} Any checks that could not run are listed clearly.` },
  ];
  return (
    <div className="home-page">
      <section className="hero-section" aria-labelledby="hero-title">
        <div className="hero-copy">
          <p className="hero-kicker"><span /> A little clarity. A safer next step.</p>
          <h1 id="hero-title">Big opportunity.<br />Check the<br /><em>small print.</em></h1>
          <p className="hero-description">A new job abroad could change your life. Check your offer letter or recruiter message for scam warning signs before you send money or your passport.</p>
          <div className="hero-assurances"><span><Icon name="globe" />9 destination countries</span><span><Icon name="shield" />No account needed</span></div>
          <a href="#how-it-works" className="text-link hero-how-link">See how it works <Icon name="arrow" className="h-4 w-4" /></a>
          <SampleReport />
        </div>
        <div id="check" className="checker-column">
          <div className="checker-topline"><span><span className="status-dot" /> YOUR NEXT STEP, WITH CONFIDENCE</span><Icon name="shield" className="h-4 w-4" /></div>
          <UploadForm priceKes={priceKes} />
          <p className="checker-note"><Icon name="lock" className="h-3.5 w-3.5 shrink-0" /> Sign in to keep your reports in your account.</p>
          <RecentReports />
        </div>
      </section>
      <section className="country-strip" aria-label="Supported destination countries">
        <div className="country-label"><Icon name="globe" /><span>Local context.<br /><strong>Global opportunities.</strong></span></div>
        <div className="country-names">{COUNTRIES.map((name) => <span key={name}>{name}</span>)}</div>
      </section>
      <section id="what-we-check" className="section-space" aria-labelledby="checks-title">
        <div className="section-heading"><div><p className="eyebrow">A closer look</p><h2 id="checks-title">More than a quick glance.</h2></div><p>A convincing logo is only the beginning.<br className="hidden sm:block" /> We check the details that tell a bigger story.</p></div>
        <div className="checks-grid">{CHECKS.map((item) => <article className="check-feature" key={item.title}><div className="feature-top"><span className="feature-icon"><Icon name={item.icon} /></span><span>{item.number}</span></div><h3>{item.title}</h3><p>{item.text}</p></article>)}</div>
        <p className="checks-footnote">Every report shows what we found and what we couldn&apos;t check. Available registry checks name their source and outcome; official links help you complete any remaining checks.</p>
      </section>
      <section id="how-it-works" className="how-section section-space" aria-labelledby="how-title">
        <div className="how-intro"><p className="eyebrow">Simple from the start</p><h2 id="how-title">From “what if?”<br />to <em>what&apos;s next.</em></h2><p>No complicated forms. No technical language. Just a clearer picture of the offer in front of you.</p><a href="#check" className="text-link">Let&apos;s check your offer <Icon name="arrow" className="h-4 w-4" /></a></div>
        <ol className="how-steps">{[
          { title: "Share what you received", text: "Upload your offer letter, attach a screenshot, or paste the message. Choose the job country or let us detect it.", icon: "upload" },
          { title: priceKes === 0 ? "We scan and save your report." : "We scan. Your findings stay locked.", text: priceKes === 0 ? "We check the document and compare the available company, website and agency evidence." : "We look for warning signs and save your report. Your score, findings and advice remain hidden while you decide to unlock it.", icon: "search" },
          { title: priceKes === 0 ? "Read your findings. Download the PDF." : "Pay by M-Pesa. Reveal the findings.", text: priceKes === 0 ? "Open your risk assessment, review the evidence and download the report. No payment is needed during testing." : `Enter your phone number in the popup and approve the KES ${priceKes} prompt on your phone. Once payment is confirmed, your findings and PDF are unlocked.`, icon: "file" },
        ].map((step, i) => <li key={step.title}><span className="step-number">0{i + 1}</span><div><h3>{step.title}</h3><p>{step.text}</p></div><Icon name={step.icon as "upload" | "search" | "file"} className="step-icon" /></li>)}</ol>
      </section>
      <section className="section-space faq-section" id="questions" aria-labelledby="faq-title">
        <div className="faq-intro"><p className="eyebrow">Good questions</p><h2 id="faq-title">A little more<br />peace of mind.</h2><p>Here&apos;s what to know before you check.</p><div className="price-note"><span className="feature-icon"><Icon name="file" /></span><div><strong>{priceKes > 0 ? `KES ${priceKes} per check` : "Free to check"}</strong><span>{priceKes > 0 ? "Full report + PDF. One payment." : "Clear findings. Practical next steps."}</span></div></div></div>
        <div className="faq-list">{faqs.map((faq, i) => <details key={faq.q} open={i === 0}><summary>{faq.q}<Icon name="plus" className="h-4 w-4 shrink-0" /></summary><p>{faq.a}</p></details>)}</div>
      </section>
      <section className="help-banner"><span className="help-icon"><Icon name="shield" className="h-7 w-7" /></span><div><p className="eyebrow">It&apos;s okay to pause</p><h2>Already paid or shared your documents?</h2><p>Stop further payments. Keep your receipts and messages, and contact NEA or your nearest police station.</p></div><a href="https://www.nea.go.ke" target="_blank" rel="noopener noreferrer" className="btn-secondary">Contact NEA <span aria-hidden>↗</span></a></section>
      <div className="home-bottom-note"><Icon name="shield" className="h-4 w-4" /><p>Your ambition deserves a fair chance. Take a moment to check.</p><Link href="/sign-up" className="text-link">Create an account <Icon name="arrow" className="h-4 w-4" /></Link></div>
    </div>
  );
}

function SampleReport() {
  return (
    <div className="sample-report" aria-label="Example of a report finding, for illustration only">
      <div className="sample-document"><div className="sample-document-heading"><Icon name="file" className="h-4 w-4" /><span>OFFER OF EMPLOYMENT</span><span className="sample-label">EXAMPLE</span></div><div className="document-lines"><i /><i /><i /></div><div className="sample-highlight"><span>“A refundable processing fee is required…”</span><span className="highlight-marker">1</span></div></div>
      <div className="sample-finding"><span className="sample-warning"><Icon name="warning" className="h-4 w-4" /></span><div><strong>Small detail. Big warning sign.</strong><p>A payment request worth checking.</p></div><span className="sample-risk">FLAGGED</span></div>
    </div>
  );
}
