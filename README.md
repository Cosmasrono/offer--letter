# Offer Letter Checker

Checks overseas job offer letters and job ads for fraud signals. Upload a PDF, photo or original recruiter `.eml` email, or paste a job ad or recruiter
message from WhatsApp, Facebook or SMS (or attach a screenshot), and get a risk score (LOW / MEDIUM / HIGH) with the
reasons, country-specific advice and official links to verify the employer.

```
Next.js (frontend/)  --upload-->  FastAPI (backend/)  --> rules + domain age + PDF forensics + Claude AI
      |                                  |
      +--- Prisma ---> MongoDB <---------+  (Next.js saves reports; Python stays stateless)
```

## What it checks

| Check | Where |
|---|---|
| Asking for money (visa/medical/ticket/"refundable" fees), M-Pesa / Western Union / crypto payments | `backend/app/rules/general.py` |
| Free email (Gmail, Yahoo...), email domain not matching the company, WhatsApp-only contact | `backend/app/rules/general.py` |
| Urgency, no interview, generic greeting, too many free perks, missing contract terms | `backend/app/rules/general.py` |
| Destination country detection, its legal fee rules, correct work-permit terms, foreign phone numbers | `backend/app/rules/countries.py` |
| Recruitment agency on NEA's accredited list (not listed, expired, revoked, licence number belonging to another agency) | `backend/app/agencies.py` |
| Website domain age (WHOIS). A failed lookup is reported as "not checked", never as a red flag | `backend/app/checks.py` |
| Public website name, emails, phone numbers and company number compared with the letter; company-name search when configured | `backend/app/websites.py` |
| PDF made with online editors / Canva, edited and re-saved, mixed fonts, stripped metadata | `backend/app/forensics.py` |
| Job ads and chat/SMS messages: same fee, payment, passport, agency and scam-database checks, but no penalty for missing letterhead, greeting, contract terms, company name, official email, WhatsApp contact, a Kenyan number or "urgently hiring"; a fee listed in an ad counts even without "you must pay" | `kind="message"` in `backend/app/rules/general.py`, `backend/app/entities.py` |
| AI second opinion + reading photos/scans | `backend/app/ai.py` (Claude, optional) |
| Original email sender, Reply-To, display-name and supplied signing-domain comparisons; readable PDF attachments | `backend/app/email_document.py` |
| UK CoS use-by dates, with scanned-form OCR that keeps labels beside values | `backend/app/sponsorship.py` |
| Contact and payment details (M-Pesa till/paybill+account, bank account, IBAN, crypto wallet) seen in earlier scam letters | `backend/app/entities.py`, `frontend/lib/reports.ts` (MongoDB) |
| Same wording as earlier scam letters (template fingerprint), even with names and numbers changed | `backend/app/fingerprint.py`, `frontend/lib/reports.ts` |
| Letters users flagged with the "Report as scam" button | `frontend/app/api/report-scam/route.ts` |

Countries included: UAE, Saudi Arabia, Qatar, Canada, UK, USA, Australia, Germany, Poland.
Add more by adding an entry to `COUNTRIES` in `backend/app/rules/countries.py` (and `frontend/lib/countries.ts`).

## Setup

### 1. Backend (Python 3.10+)

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env          # macOS/Linux: cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

Optional, in `backend/.env`:
- `ANTHROPIC_API_KEY`: turns on the Claude AI analysis and reading of photos/scanned letters
  (get a key at https://console.anthropic.com). Without it, the rules-only checks still work on PDFs and text.
- Or install [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) to read photos without Claude.

### Company websites and identity comparisons

Reports show **scam risk** separately from **verification completeness**. The completeness checklist covers employer
registration, independent website research, website details, agency permission, sender identity and confirmation of
the actual offer. CoS reports add sponsorship validity. A resolved conflict counts as available evidence but prevents
a complete result. Neither coverage nor the model's self-reported confidence is a probability that an offer is real.

**Employer confirmation** starts as unverified. An administrator viewing an unlocked report can record an employer's
confirmation or denial, with the independently sourced contact page, contact used, offer reference, role, response
time and an evidence note. Confirmation additionally requires attesting that the employer verified the recruiter and
offer terms. The form records a response already obtained; it does not send messages or contact employers. The
decision is saved atomically in the existing review audit history, can be withdrawn, and never changes the original
scan risk. AI and ordinary users cannot assign this status. A subsequent confirmed-scam decision invalidates an earlier
employer confirmation even if the scam decision is later cleared. No Prisma schema change is needed.

Original `.eml` emails are read locally before analysis. The reader compares From, Reply-To, display-name addresses
and claimed DKIM signing domains, reads the main body and up to three PDF attachments, and does not execute HTML or
load remote images. **Uploaded Authentication-Results and DKIM headers are untrusted**: cryptographic validation has
not run, and supplied SPF/DKIM/DMARC pass claims never add trust points or establish sender identity. Recipients and
routing headers are excluded from recruiter entity extraction. PDF editing checks cover the first readable attachment.

Unsupported, corrupt and unreadable uploads return **Not checked** with `DOCUMENT_NOT_CHECKED`; no risk verdict,
saved report or payment request is produced. An unreadable document is not labelled fraudulent. UK CoS documents with
a readable past use-by date get an explicit validity finding. Expiry means the document cannot support a new visa
application today; it does not establish whether a historical CoS was genuine or already used. CoS forms are not
penalized for lacking an HR email or full contract terms. Identity-card fields are not treated as financial-card requests.

Recognized CoS forms also trigger an automatic lookup of the **current Home Office sponsor register**. The adapter
discovers the dated CSV from GOV.UK, checks its format and freshness, and caches it in memory for six hours. A name
match must be exact after legal-suffix/case normalization, and the claimed visa route must be listed. Similar names,
missing names and wrong routes produce findings. A failed, incomplete or stale lookup remains unverified and adds
no fraud points. `ENABLE_UK_SPONSOR_LOOKUP=false` disables this network check. The first lookup may take longer while
the full official register downloads. Individual CoS and sponsor-licence numbers are not exposed by this public list.

A past CoS use-by date **always sets at least HIGH risk for new use**, even if AI or other trust signals lower the
points total. The report and PDF label it **High risk — expired sponsorship**, explain that it must not be used for
a new application, and keep historical authenticity unverified. Missing/incorrect current sponsor entries force at
least MEDIUM risk. The app does not treat these validity/current-register findings alone as evidence for automatically
adding a historical document to scam memory. Separate critical scam findings can still qualify the case.

For care-role CoS documents, England care-provider permission is explicitly marked unverified with an official CQC
lookup link until an independently matched provider record is available. Current company/sponsor registration is
not treated as proof of CQC permission. A mere mention of CoS in an ordinary offer does not classify it as a CoS form.

New scans read public HTTPS home pages plus up to two same-host contact/about/careers pages per site. The report
and PDF show the values in the letter alongside the source values, the pages read, and a checked-at timestamp.
Explicit organization-name or company-number conflicts add findings; identity/registry conflicts keep the score
at least MEDIUM even if AI or other trust signals lower it. Website matches add no trust points. An email or
phone missing from the pages read remains unverified, because public sites need not publish every HR contact.
Private vacancies, salaries and offer terms require direct employer confirmation and are shown as unverified.

Set `ENABLE_WEBSITE_CHECK=false` to disable public-page reads. Requests are bounded in size, page count and time;
they use public HTTPS addresses, validate every redirect and pin the connection to a checked public IP. The reader
does not send letter text, upload-specific URLs or personal document details to these websites. JavaScript-only,
blocked, oversized and unreachable pages remain unavailable, with no fraud points for a failed read.

Set `BRAVE_SEARCH_API_KEY` in `backend/.env` to discover a candidate website by the employer's name independently
of links supplied in the letter. Only the extracted company name and destination are searched. Results whose domain
carries the company's brand are preferred over news and directory pages. A letter domain that also carries the brand
but differs from those domains (`emirates-careers-recruitment.com` vs `emirates.com`) gets one more search for the
domain itself: if a page on the company's own sites mentions it (a real careers site), it is accepted; otherwise it is
flagged as a look-alike domain (+25). Each scan uses one to three searches. Without that key,
company-name discovery is explicitly unverified; stated domains and websites published in matched NEA records can
still be read. A search result is a lead, not proof of official website ownership. A copied real website does not
authenticate the sender. No company domain is guessed from its name.

Run `backend/.venv/Scripts/python.exe backend/tools/check_verification_sources.py` from the project root to check
public HTTPS/NEA connectivity and whether registry/search credentials are configured, without printing secrets.

### NEA accredited-agency list

For named agencies and employer names that may belong to an agency, the agency check first queries the current official NEA public API at
`https://api.neaims.go.ke/api/v1/agencies/public/list`, cached in memory for 30 minutes. The current public portal
is `https://neaims.go.ke/home/agencies-info`; the old ASPX URL may serve the portal app instead of a table.
It compares legal name, licence, status and expiry; it also compares explicitly labelled agency emails with
NEA's published email domains to flag possible impersonation. Licence-only or approximate-name matches remain
unverified. The current API's business-registration field is not treated as an NEA licence number, and its
`LICENSE_PAID` status is not treated as licence approval. Missing approval evidence remains unverified; expired,
deregistered and local-only records produce warnings. A named agency that is absent from the live register or a fresh
snapshot is flagged as not NEA-accredited (+20 when it looks Kenyan, +10 otherwise), and the user is told to search
the register in case the name is spelled differently. The adapter also accepts the legacy HTML table if the API is unavailable.
Set `ENABLE_NEA_LIVE_LOOKUP=false` to use imported data only.

When the live source is unavailable, the check uses a maintained snapshot of the official NEA list in
`backend/data/nea_agencies.csv` (or `NEA_AGENCIES_CSV`). **The project does not ship an invented list.** Open the official list at
https://neaims.go.ke/home/agencies-info and obtain an official CSV or HTML table export. Saving only the current
JavaScript app shell does not produce a register export. Include the actual recruitment licence number, not a
business registration number, when using the legacy import format.

An administrator can import that export at `/admin/verification` (also linked from admin History). The page
requires an admin session; backend maintenance additionally requires the shared `BACKEND_API_KEY` configured in
both frontend and backend `.env`. Enter the actual retrieval date/time of the export, not today's date for an old file.

Or, from `backend/`, import it through the CLI:

```powershell
.\.venv\Scripts\python.exe tools/import_nea.py "C:\path\to\official-nea-export.html" --retrieved-at "2026-10-26T10:00:00+00:00"
```

Imports require agency name, licence/registration number, expiry date and status. Invalid dates, conflicting
duplicate licences and empty/invalid exports are rejected before replacing the current data. Each import saves
provenance, a SHA-256 digest and a retrieval timestamp in the adjacent `.metadata.json` file. Refresh within 30 days.
Missing, stale or changed data is shown as unverified and contributes no licence trust/risk score, so an agency is
only flagged as missing when the list it was checked against is live or fresh.

### Official employer records and report evidence

UK employers can be checked against the Companies House public-data API. Set `COMPANIES_HOUSE_API_KEY` in
`backend/.env` (see https://developer.company-information.service.gov.uk/authentication). The key stays server-side.
A stated company number is checked against the employer name and company status. Without a number, only one
unambiguous exact-name search result is followed to its full profile. Missing credentials, ambiguous searches,
timeouts and unsupported destinations remain unverified. Name/status mismatches add findings; an active record
match does not reduce other scam signals or authenticate the sender or offer.

Reports and PDFs include a **Company, website and agency evidence** section showing the source link, outcome, checked-at time,
snapshot retrieval date and matched record details. Older reports have no invented evidence. Supported source
outcomes are Record matched, Details need checking, Not found in source, Check unavailable, Unverified and Not applicable.
Other destinations still use their official verification links; there is no automatic employer lookup for them yet.

The optional `Report.sourceChecks` JSON field has no new index requirement. Run `pnpm exec prisma generate`
after updating the Prisma schema. On Windows, a running server can lock Prisma's engine DLL; stop that project's
server and rerun generation if the engine needs replacing. Restart frontend/backend after editing `.env`.

### Real-document validation

`backend/tools/evaluate_real.py` evaluates a JSONL manifest of independently labelled letters, with confusion
matrices, missed scams, false alarms, borderline cases and timing. Synthetic documents never count toward the
100-real-document target. Real documents are supplied by the dataset owner; none are fabricated by this project.
See `backend/evaluation/README.md` for the manifest format, private-data location and offline/online commands.
The benchmark covers backend analysis; frontend scam-memory and payment access have separate automated tests.

Test it: open http://localhost:8000/docs and try `POST /analyze` with a file from `backend/samples/generated/`.

### 2. Database (MongoDB Atlas, free tier)

1. Create a free cluster at https://www.mongodb.com/atlas.
2. Database Access → add a user. Network Access → allow your IP.
3. Connect → Drivers → copy the connection string and add a database name, e.g.
   `mongodb+srv://USER:PASSWORD@cluster0.xxxxx.mongodb.net/offer_checker?retryWrites=true&w=majority`

Prisma needs a MongoDB **replica set**. Atlas always has one; a plain local `mongod` will not work.

### 3. Frontend (Next.js + Prisma)

```bash
cd frontend
pnpm install                    # also runs prisma generate
copy .env.example .env          # then paste your DATABASE_URL
pnpm db:push                    # creates the collections and indexes
pnpm dev
```

Open http://localhost:3000 (Next.js picks 3001 if 3000 is busy, or run `pnpm dev -p 3001`).

The frontend uses **pnpm**. `pnpm-workspace.yaml` allows the install scripts that Prisma needs
(`allowBuilds`). Without them, pnpm 11 skips downloading the Prisma engine.

Without `DATABASE_URL` the app still works. Reports are shown but not saved, and History stays empty.

### 4. Accounts (email + password)

Signing in is optional: anyone can check a letter. A signed-in user's checks are saved to their account and are
**private**: only they and admins can open the report, pay for it, download it or report it. Reports checked while
signed out stay reachable by their link, as before. Set `ADMIN_EMAILS` in `frontend/.env` (comma-separated); those
accounts get the admin role on sign-up/sign-in and can manage everyone's reports in History. Findings and PDFs
still require a confirmed payment, including for admins.

How it's built (`frontend/lib/session.ts`, `password.ts`, `auth-actions.ts`, `rate-limit.ts`):
- Passwords are hashed with scrypt (N=2^15, per-password salt). At least 10 characters.
- A session is a random 256-bit token in an `httpOnly`, `SameSite=Lax` cookie (`Secure` in production), valid 30
  days. Only its SHA-256 hash is stored (`Session` collection), so signing out really ends it.
- Sign-in allows 5 failures per email and 20 per network in 15 minutes; sign-up 20 accounts per network per hour.
  The error never says whether an email is registered.
- `?next=` redirects only go to paths on this site.
- With Cache Components, anything that reads the session is inside a `<Suspense>` boundary (header menu, report,
  history), and every route handler and Server Action re-checks the session itself.

Not built yet: password reset by email and email verification (they need an email provider).

### 5. Scan first, then unlock with M-Pesa (PayHero)

Upload or paste a document to scan it without paying first. The scan endpoint saves the report and returns only
its ID: no score, findings, advice or document text is sent to the browser. When scanning finishes, the report page
automatically opens a popup for the customer's M-Pesa phone number. Closing it keeps the report locked.

Confirmed payment unlocks both the findings and the **Download PDF** button. The PDF (`backend/app/pdf_report.py`) lists the verdict, every
finding, the checks that could not run, the details found and the official links, so a job seeker can hand it to an
agency, employer, NEA or the police. It also prints the link to the online report, so a recipient can check the PDF
hasn't been edited.

Report access is paid by M-Pesa STK Push through [PayHero](https://docs.payhero.co.ke). In `frontend/.env`:

| Variable | What it is |
|---|---|
| `REPORT_PRICE_KES` | Price for findings and PDF together. Defaults to KES 50; zero, negative or invalid values also fall back to 50 so an unset price never exposes findings. |
| `PAYHERO_API_USERNAME`, `PAYHERO_API_PASSWORD` | PayHero dashboard → API Keys. Server-side only. |
| `PAYHERO_CHANNEL_ID` | PayHero dashboard → Payment Channels → your till/paybill's ID. |
| `PAYHERO_CALLBACK_URL` | Optional public HTTPS URL of `/api/payments/callback`. Without it, payments are confirmed by polling PayHero's status API while the payer waits (this also works on localhost). |
| `PAYHERO_CALLBACK_SECRET` | Random string; added to the callback URL and checked on every callback. |
| `PAYHERO_MOCK` | `true` for local testing: no M-Pesa prompt, payments succeed after ~6 s (phone `0700000000` fails). Ignored in production builds. |
| `PUBLIC_SITE_URL` | Your site's address, printed in the PDF. |

#### Free local testing

`frontend/.env.development.local` currently sets `FREE_REPORT_TESTING=true`. Run `pnpm dev` to scan letters,
view findings and download PDFs without payment. No payment record or M-Pesa prompt is created. Report ownership
checks still apply. This override works only when `NODE_ENV=development`; production builds and servers require
payment even if the flag is accidentally set. Set it to `false` and restart `pnpm dev` to resume payment testing.

#### Payment testing setup: KES 1

Use **KES 1 while testing**, and verify **both successful and failed payments**. The local override is in
`frontend/.env.development.local` (`REPORT_PRICE_KES=1`), so `pnpm dev` displays and requests KES 1.
Restart the development server after changing environment files. Production pricing remains separately configured.

- **Real payment success:** scan a new document, pay the KES 1 prompt on your own M-Pesa number, and confirm
  that the findings and PDF unlock only after provider confirmation.
- **Real payment failure:** use a different unpaid report, cancel the phone prompt or let it expire, and confirm
  that the error allows another attempt while the findings and PDF remain locked.
- **Simulation without a charge:** temporarily set `PAYHERO_MOCK=true` in `frontend/.env.development.local`
  and restart `pnpm dev`. Use `0712345678` for success or `0700000000` for failure; either result arrives after
  about six seconds. These are simulated outcomes, and no phone prompt is sent. Remove the override when
  returning to real payments. Mock payments are disabled in production.

Use fresh unpaid reports for each outcome. A report already unlocked by a successful payment is not a failure
test. Existing pending prompts keep their original amount; create a new payment to test KES 1.

Run the automated success/failure checks without sending payments:

```bash
cd frontend
node --experimental-strip-types --test tests/payhero.test.mjs tests/report-access.test.mjs
```

How it works: `POST /api/payments` sends the STK prompt and stores a `Payment`; the browser polls
`GET /api/payments?id=`, which asks PayHero for the status. PayHero's callback isn't signed, so a payment is only
marked paid after PayHero's status API confirms it. A paid payment gets a random download token that unlocks
both the report page and `/api/report-pdf` for that report; the browser remembers it so the payer can open it again.
Pending payment IDs are remembered too, so refreshing resumes status checks without sending another prompt. After 3 unfinished
attempts a number must wait 15 minutes (PayHero blocks a number for 24 hours after 10 failed prompts in a row).

Unreadable documents and storage failures never expose a report or request payment. Existing unused credits from
the previous pay-before-scanning flow are still honoured. Owners, admins, history links and direct PDF URLs all
require successful payment before findings or downloads are released.

**Lock the backend.** Set the same `BACKEND_API_KEY` in `backend/.env` and `frontend/.env`. Otherwise anyone who
can reach the Python API could render an official-looking PDF from made-up data.

After pulling these changes run `pnpm db:push` in `frontend` (new `User` fields and `Session`, `AuthAttempt`,
`Payment` and `ScamTemplate` collections).

## Test letters

`backend/samples/` has 14 **fictional** offer letters (7 genuine-style, 7 scam-style), 6 fictional job ads and
messages in `samples/messages.py` (3 genuine-style, 3 scam-style) across the UK, UAE, Canada,
Germany, Saudi Arabia, Australia, Poland and Qatar, plus photo versions of two of them. Each letter states the
answer it should get. They're written in `samples/letters.py`, so add new cases there.

```bash
cd backend
.venv\Scripts\python samples\make_samples.py    # writes PDFs + photos to samples/generated/
.venv\Scripts\python samples\evaluate.py        # checks every letter, -v shows all findings
```

Included tricky cases:
- genuine letters that mention visa, LMIA or medical fees but say **the employer pays** them (no false alarm)
- a polished scam on a company-style domain where only the fee request, the iLovePDF re-save and the urgency give it away
- a scam with **no fee at all** that moves the victim to WhatsApp and asks for their passport
- a genuine offer through an NEA-accredited agency, and a fee-free scam from a Nairobi agency that isn't accredited
  (agencies are checked against `samples/nea_agencies_sample.csv`, a fictional list)

The photo versions are skipped unless `ANTHROPIC_API_KEY` is set or Tesseract is installed.
Run `evaluate.py` after every rule change so a fix for one letter doesn't break another.

These letters were written alongside the rules, so passing them is the minimum. For a real measure, test with
real letters:

- **Scam letters:** government and police scam warnings often publish photos of fake offers (Kenya NEA,
  Canada IRCC fraud pages, UK Action Fraud, Gulf embassies' notices), and job-seekers' groups share them often.
- **Genuine letters:** ask friends or colleagues who have worked abroad for theirs, with names, ID numbers and
  salaries blacked out.
- Add each one to a private folder with the expected answer. Don't commit real people's letters to git.

## Notes

### Qatar and Kuwait visa checks

Open `/visa` (also linked from the checker and navigation). The user consents before selecting a visa and optional
offer letter, reviews labelled extracted fields, corrects OCR mistakes, then confirms the check. The review step
does not save a report; final analysis reads the originals again and stores both extracted and reviewed values.
Each file is limited to 10 MB. PDF, JPG, PNG, WEBP and TXT are supported for visas; offers also accept original EML.
Scans need configured image OCR. Unsupported/unreadable documents produce `DOCUMENT_NOT_CHECKED`, without a
saved assessment or payment request. Preview requests are limited to 10 per hour per hashed client IP.

Checks cover clearly labelled issue/visa-entry expiry dates, impossible numeric calendar dates, date order, future issue dates, explicit issuing-country
conflicts, and visit/tourist/business-route concerns when an employment offer is attached. Ambiguous dates are not
guessed, generic/passport expiry fields are not treated as visa expiry, and no undocumented government visa-number
length is assumed. Labels may be on the same line or the following line. Unrecognised layouts need a clearer,
labelled copy or manual government verification; this is not a security-feature or forgery certification service.

Comparison covers holder name, passport number, employer/sponsor and job title when both documents contain them.
Names can reorder without conflict; abbreviated names remain unverified. Sponsor/title differences prompt an
explanation, not an automatic declaration of fraud. Missing fields and absent salary never add fraud points.
Original extracted dates remain visible after corrections; a clear past source expiry cannot be silently erased.
The offer attachment is for comparison, not a full second employer/NEA investigation: use the offer checker for that.

Every visa report and PDF says **Government status: not checked** and gives source-specific steps for Qatar's
official MOI Visa Inquiry & Printing page or Kuwait MOI residency services. The app never submits identifiers to
those portals, scrapes captchas, imports user-reported portal outcomes as verified, or infers authenticity from a
matching name/number. Official sources reviewed on 2026-10-29:
- https://portal.moi.gov.qa/wps/portal/MOIInternet/services/inquiries/visaservices/enquiryandprinting
- https://www.moi.gov.kw/main/eservices/residence

Visa reports use existing report pricing, payment locks, account/guest ownership, 30-day expiry and deletion. Their
document templates and personal identifiers are excluded from shared scam matching, including after review.
Their validity risk is not automatically classified as a suspected scam. Schema fields are optional for compatibility.
The generated client package is versioned to avoid overwriting a DLL held by the existing Windows dev server.

Run `backend/.venv/Scripts/python.exe -m unittest discover -s backend/tests -p test_visas.py` from the root with
`backend` on `PYTHONPATH`, or run `.venv/Scripts/python.exe -m unittest discover -s tests -p test_visas.py` in
`backend`. Frontend API and storage tests are in `frontend/tests/visa.test.mjs` and the existing report tests.
With Playwright available and local free report testing enabled, run `node scripts/check-visa-ui.mjs` in `frontend`
to check both countries end to end with synthetic text documents. It makes no AI calls or payments and deletes the
temporary reports it creates. Screenshots and sample PDFs go to `frontend/artifacts/visa`.

### Consent and report privacy

New submissions start with an explicit consent screen before file selection or pasted text. The server rejects
missing or outdated consent before forwarding documents for analysis. Each saved report records notice version
`2026-10-29`, a server timestamp, the optional pattern-sharing choice and a 30-day expiry. Pattern sharing defaults
off; declining it does not affect the current check. Reporting or admin review never overrides this choice.

New reports stop being accessible at expiry, including through paid tokens and PDF links. MongoDB removes them
using the `Report_privacy_expiry` TTL index, installed automatically before accepting a new scan. Scans fail closed
if that index cannot be installed. Background deletion can lag expiry. Historical reports without `expiresAt` are
not changed or automatically deleted. Never backfill this field or alter retention for existing data without a
separate, reviewed migration. After `db:push`, restart the app so the TTL-index check runs again.

The report page offers deletion before or after payment. Only an account owner, or the browser holding a guest
report's HTTP-only management cookie, can delete it; public links, paid tokens and an unrelated admin role do not
grant deletion rights. Deletion removes the source report and its matching indexes, not transaction bookkeeping,
external-provider copies, existing downloaded PDFs or findings already saved in other reports. Guest users who
clear cookies need operator assistance. Account/payment retention and backups require a separate operator policy.

Set `PRIVACY_OPERATOR_NAME` and a monitored `PRIVACY_CONTACT_EMAIL` in `frontend/.env` before public launch, and
review `/privacy` against the actual hosting, AI provider/model routes, cross-border safeguards and backup policies.
Protect the Python service with `BACKEND_API_KEY` and private network access so users cannot bypass the frontend.
The privacy notice does not establish legal compliance or replace the operator's data-protection review.

The Prisma client generates as the local `@offer-checker/prisma-client-v2` package inside `frontend/node_modules`,
including on `pnpm install`. Next.js treats it as a server external to avoid bundling its dynamic filesystem reads.
After schema edits, run `pnpm exec prisma generate` before type checks or starting the app. MongoDB optional fields
do not require a destructive data migration; the app provisions its retention index on the first consenting scan.

Run `node --test tests/*.test.mjs` and `pnpm lint` in `frontend`. For browser checks with Playwright available, run
`node scripts/check-privacy-ui.mjs`; add `--database` to exercise deletion with disposable synthetic records and
verify the TTL index against the configured database. This mode does not call AI or initiate payments. It removes
only the synthetic records it creates. Screenshots are written to `frontend/artifacts/privacy`.

- **Prisma 6.x is used on purpose**, because it fully supports MongoDB. Check the Prisma docs before upgrading to 7+.
  MongoDB has no migrations, so after changing `prisma/schema.prisma` run `pnpm db:push`.
- **Scoring:** each finding adds or removes points (`points` field). A score of 60+ is HIGH, 30-59 is MEDIUM and below 30 is LOW.
  Any request for money forces HIGH. Tune thresholds in `backend/app/analyzer.py`.
- **Scam database:** every HIGH-risk letter is remembered: its free-provider emails, phone numbers, payment details and a
  MinHash fingerprint of its wording (`ScamTemplate`). Company domains are not, because scam letters copy real employers'
  domains, and a bare paybill isn't either, because banks share one paybill among all customers. A later letter that reuses
  these gets a finding. A matching template adds points but never forces HIGH on its own, since scammers copy real
  employers' letters.
- **Report as scam:** saved reports have a button that adds the letter's details and wording to the database as
  user reports. Anyone can press it, so user reports are unconfirmed: together they add one +15 finding, which can't
  change a clean letter's verdict alone. Each saved report can be reported once. A review page to confirm or reject
  user reports is the next step (see below).
- **AI model:** `claude-opus-5-5` with structured output and automatic refusal fallback (`backend/app/ai.py`).
- The result is a risk assessment, not proof. Always tell users to confirm with the employer directly.
  The best result is "No major red flags found", never "genuine", and every report lists the checks that could not run
  (`checks_not_run`). A file with no readable text is shown as "Not checked".

## Ideas for next steps

- Password reset and email verification (needs an email provider).
- Admin page to review user scam reports (confirm or reject) and keep the NEA agency list up to date.
- Company register connectors for destinations beyond the UK.
- QR-code verification so real employers can sign their letters.
- Swahili and Arabic translations of the report.
