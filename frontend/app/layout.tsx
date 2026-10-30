import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import { Suspense } from "react";
import { Icon } from "@/components/Icon";
import { UserMenu } from "@/components/UserMenu";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Offer Letter Checker — A safer next step",
  description: "Check your overseas offer letter, job ad or recruiter message for scam warning signs before you send money or your passport.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" data-scroll-behavior="smooth" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col font-sans">
        <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-lg focus:bg-white focus:px-3 focus:py-2 focus:shadow">Skip to content</a>
        <header className="site-header">
          <nav className="site-nav" aria-label="Main navigation">
            <Brand />
            <div className="nav-links">
              <Link href="/#check">Check an offer</Link>
              <Link href="/visa">Check a visa</Link>
              <Link href="/#how-it-works" className="desktop-link">How it works</Link>
              <Link href="/#questions" className="desktop-link nav-secondary">FAQs</Link>
              <Link href="/history">My reports</Link>
            </div>
            <div className="nav-account"><Suspense fallback={<div className="h-9 w-20 animate-pulse rounded-lg bg-blue-100 dark:bg-blue-950" />}><UserMenu /></Suspense></div>
          </nav>
        </header>
        <main id="main" className="site-main">{children}</main>
        <footer className="site-footer">
          <div className="footer-content">
            <div><Brand /><p>A little clarity before a big decision.<br />Helping job seekers take a safer next step.</p></div>
            <div><h2 className="footer-title">Your next step</h2><ul><li><Link href="/#check">Check an offer</Link></li><li><Link href="/#how-it-works">How it works</Link></li><li><Link href="/history">Your saved reports</Link></li><li><Link href="/privacy">Privacy and consent</Link></li></ul></div>
            <div><h2 className="footer-title">Stay informed. Stay safe.</h2><ul><li><a href="https://www.nea.go.ke" target="_blank" rel="noopener noreferrer">National Employment Authority ↗</a></li><li>Report suspected fraud to the police.</li><li>Confirm offers with the employer directly.</li></ul></div>
          </div>
          <div className="footer-bottom"><span>Offer Letter Checker · Made for your next chapter.</span><p>An automated risk assessment. Always verify an offer directly with the employer.</p></div>
        </footer>
      </body>
    </html>
  );
}

function Brand() {
  return <Link href="/" className="brand" aria-label="Offer Letter Checker home"><span className="brand-mark"><Icon name="shield" className="h-6 w-6" /></span><span><span className="brand-name">Offer Letter Checker</span><span className="brand-tagline">A safer next step</span></span></Link>;
}
