"""Render a checked letter's report as a PDF that a job seeker can hand to an agency, employer or the authorities."""

import io
from html import escape

import pymupdf

from .models import AnalysisReport, Finding
from .verification import verification_summary

PAGE = pymupdf.paper_rect("a4")
CONTENT = PAGE + (42, 48, -42, -56)  # leave room for the footer

VERDICTS = {
    "HIGH": ("Fraud signals found", "#b91c1c", "#fef2f2"),
    "MEDIUM": ("Unverified - check carefully before you act", "#b45309", "#fffbeb"),
    "LOW": ("No major red flags found", "#047857", "#ecfdf5"),
}
NOT_CHECKED = ("Not checked - no text could be read", "#52525b", "#f4f4f5")
SEVERITY_LABEL = {"critical": "CRITICAL", "high": "HIGH", "medium": "MEDIUM", "low": "LOW", "info": "INFO"}

CSS = """
* { font-family: sans-serif; font-size: 10pt; color: #27272a; }
h1 { font-size: 17pt; margin: 0 0 2pt 0; color: #18181b; }
h2 { font-size: 12pt; margin: 14pt 0 4pt 0; color: #18181b; }
p { margin: 0 0 4pt 0; }
.muted { color: #71717a; font-size: 8.5pt; }
.verdict { font-size: 13pt; font-weight: bold; }
.score { font-size: 11pt; font-weight: bold; }
.flag { margin: 0 0 6pt 0; }
.sev { font-size: 7.5pt; font-weight: bold; }
.detail { color: #52525b; font-size: 9pt; }
.excerpt { font-family: monospace; font-size: 7.5pt; color: #3f3f46; }
td { padding: 2pt 6pt 2pt 0; vertical-align: top; }
"""


def _e(value: object) -> str:
    return escape(str(value))


def _finding(f: Finding) -> str:
    colour = "#047857" if f.points < 0 else {"critical": "#b91c1c", "high": "#b91c1c", "medium": "#b45309"}.get(f.severity, "#52525b")
    return (
        f'<p class="flag"><span class="sev" style="color:{colour}">{SEVERITY_LABEL[f.severity] if f.points >= 0 else "GOOD"}</span> '
        f"<b>{_e(f.title)}</b><br/><span class=\"detail\">{_e(f.detail)}</span></p>"
    )


def _rows(rows: list[tuple[str, str]]) -> str:
    cells = "".join(f'<tr><td class="muted">{_e(k)}</td><td>{_e(v)}</td></tr>' for k, v in rows if v)
    return f"<table>{cells}</table>" if cells else ""


def _html(report: AnalysisReport, report_id: str, checked_at: str, report_url: str | None) -> str:
    not_checked = not report.text_excerpt.strip()
    label, colour, background = NOT_CHECKED if not_checked else VERDICTS[report.risk_level]
    if report.kind == "visa" and report.risk_level == "HIGH":
        label = "High risk - visa validity or document differences"
    if not not_checked and report.risk_level == "HIGH" and any(finding.id == "cos_expired" for finding in report.findings):
        label = "High risk - expired sponsorship"
    if not not_checked and report.scam_status == "CONFIRMED_SCAM":
        label, colour, background = "Confirmed scam - reviewed", "#b91c1c", "#fef2f2"
    elif not not_checked and report.scam_status == "CLEARED":
        label, colour, background = "Scam report dismissed - reviewed", "#52525b", "#f4f4f5"
    e = report.entities
    red_flags = [f for f in report.findings if f.points > 0]
    good_signs = [f for f in report.findings if f.points <= 0]
    what = "visa / permit" if report.kind == "visa" else "job ad or message" if report.kind == "message" else "offer letter"

    parts = [
        "<h1>Offer Letter Checker - risk report</h1>",
        f'<p class="muted">Report {_e(report_id)} · checked {_e(checked_at)} · {_e(what)}: {_e(report.file_name)}</p>',
        # A one-cell table: a background on a <div> leaks onto the next page in PyMuPDF's Story layout.
        f'<table style="width:100%; margin:10pt 0 6pt 0;"><tr><td style="background-color:{background}; padding:8pt;">'
        f'<p class="verdict" style="color:{colour}">{_e(label)}</p>'
        + ("" if not_checked else f'<p class="score" style="color:{colour}">Scan risk score: {report.score} / 100</p>')
        + f"<p>{'Original scan assessment: ' if report.scam_status in ('CONFIRMED_SCAM', 'CLEARED') else ''}{_e(report.summary)}</p></td></tr></table>",
        _rows([
            ("Employer", report.company_name or ""),
            ("Job", report.job_title or ""),
            ("Country", report.country_name or ""),
            ("Recruitment agency", " - ".join(filter(None, [e.agency_name, e.agency_licence and f"licence {e.agency_licence}"]))),
            ("Tracked status", report.scam_status.replace("_", " ").title() if report.scam_status else ""),
            ("Reviewer reason", report.review_note or ""),
            ("Reviewed at", report.reviewed_at or ""),
        ]),
        f"<h2>Red flags ({len(red_flags)})</h2>",
        "".join(_finding(f) for f in red_flags) or "<p>No red flags were found in the checks that could run.</p>",
    ]
    if good_signs:
        parts += [f"<h2>{'Document observations' if report.kind == 'visa' else 'Good signs'} ({len(good_signs)})</h2>", "".join(_finding(f) for f in good_signs)]
    if report.visa:
        visa = report.visa
        parts.append("<h2>Government visa status: not checked</h2><p>Official issuance, authenticity and work permission have not been confirmed. Opening the official page does not change this status.</p>")
        parts.append(_rows([("Official source", visa.guidance.source_name), ("Official link", visa.guidance.source_url)]))
        parts.extend(f"<p>{index}. {_e(step)}</p>" for index, step in enumerate(visa.guidance.steps, 1))
        parts.append("<h2>Reviewed visa details</h2><p>Reviewed values can include user corrections; they are not official confirmation.</p>")
        for field, value in visa.details.model_dump().items():
            original = getattr(visa.extracted_details, field)
            parts.append(_rows([(field.replace("_", " ").title(), value or "Not found / not checked")]))
            if original != value:
                parts.append(_rows([("Originally extracted", original or "Not found"), ("Provenance", "Corrected by user")]))
        parts.append("<h2>Offer and visa comparison</h2>")
        parts.append(_rows([("Offer file", visa.offer_file_name or "No offer attached")]))
        for comparison in visa.comparisons:
            parts.append(_rows([(comparison.field, comparison.status.title()), ("Visa", comparison.visa_value or "Not found"),
                                ("Offer", comparison.offer_value or "Not found"), ("Meaning", comparison.detail)]))
        if visa.corrections:
            parts.append(_rows([("User corrections", ", ".join(visa.corrections))]))
            if visa.offer_details and visa.extracted_offer_details:
                for field in ("holder_name", "passport_number", "sponsor", "job_title"):
                    if getattr(visa.offer_details, field) != getattr(visa.extracted_offer_details, field):
                        parts.append(_rows([("Offer " + field, getattr(visa.offer_details, field) or "Not supplied"),
                                            ("Originally extracted", getattr(visa.extracted_offer_details, field) or "Not found")]))
        parts.append("<p>Salary is not compared because a visa may not state it. Missing values remain unverified. A sponsor difference may reflect an intermediary and needs explanation.</p>")
    coverage = verification_summary(report)
    parts.append(f"<h2>Verification completeness</h2><p>{_e(coverage.level.title())} evidence: {coverage.resolved} of {coverage.required} checks have conclusive comparisons.</p>"
                 "<p>This is evidence coverage, not the probability an offer is genuine. Conflicts need resolving.</p>")
    for item in coverage.items:
        parts.append(_rows([(item.label, item.status.replace("_", " ").title()), ("Evidence", item.detail)]))
    confirmation = report.offer_confirmation
    label = "Employer-confirmed offer - recorded by reviewer" if confirmation and confirmation.status == "CONFIRMED" and report.scam_status != "CONFIRMED_SCAM" else "Employer denied this offer - recorded by reviewer" if confirmation and confirmation.status == "DENIED" else "Offer not confirmed by the employer"
    if report.kind != "visa":
        parts.append(f"<h2>Employer confirmation</h2><p>{_e(label)}</p>")
    if confirmation and report.kind != "visa":
        parts.append(_rows([("Employer contact", confirmation.employer_contact), ("Independent source", confirmation.source_url),
                            ("Offer reference", confirmation.offer_reference), ("Role", confirmation.job_title), ("Employer response", confirmation.confirmed_at),
                            ("Recorded at", confirmation.recorded_at), ("Evidence", confirmation.note)]))
    if report.kind != "visa":
        parts.append("<p>AI cannot assign employer confirmation. This status records a reviewer's evidence of direct contact; the original scan risk remains visible.</p>")
    if report.memory_matches:
        parts.append("<h2>Matches to earlier scam cases</h2>")
        for match in report.memory_matches:
            parts.append(_rows([
                ("Earlier case status", match.status.replace("_", " ").title()),
                ("Distinct patterns", str(match.case_count)),
                ("Matching details", ", ".join(match.matching_details)),
                ("Wording similarity", f"{match.template_similarity:.0%}" if match.template_similarity is not None else ""),
            ]))
        parts.append("<p>A matching template alone does not prove fraud. User reports and model flags are unconfirmed until reviewed.</p>")
    if report.source_checks:
        parts.append("<h2>Company, website and agency evidence</h2><p>A website or registry match does not authenticate the sender or the job offer.</p>")
        for check in report.source_checks:
            parts.append(_rows([
                ("Check", check.check.title()), ("Outcome", check.status.replace("_", " ").title()),
                ("Subject", check.subject), ("Source", check.source_name), ("Source link", check.source_url),
                ("Checked at", check.checked_at), ("Snapshot retrieved", check.source_updated_at or ""),
                ("Record", " / ".join(filter(None, [check.record_name, check.record_id, check.record_status]))),
                ("Details", check.detail),
            ]))
            for comparison in check.comparisons:
                parts.append(_rows([
                    (comparison.field, comparison.status.title()), ("Letter", comparison.letter_value),
                    ("Source", comparison.source_value), ("Comparison", comparison.detail),
                ]))
            if check.checked_pages:
                parts.append(_rows([("Page checked", url) for url in check.checked_pages]))
    if report.checks_not_run:
        parts += ["<h2>Checks that could not run</h2>", "".join(f"<p>- {_e(c)}</p>" for c in report.checks_not_run)]
    details = _rows([
        ("Emails", ", ".join(e.emails)),
        ("Phone numbers", ", ".join(e.phones)),
        ("Payment details", ", ".join(e.payment_accounts)),
        ("Websites / domains", ", ".join(e.domains)),
        ("Amounts of money", ", ".join(e.money)),
    ])
    if details:
        parts += ["<h2>Details found</h2>", details]
    parts += [
        "<h2>What to do</h2>", "".join(f"<p>- {_e(a)}</p>" for a in report.advice),
        "<h2>Verify officially</h2>", "".join(f"<p>{_e(l['label'])}: {_e(l['url'])}</p>" for l in report.verify_links),
    ]
    if report.text_excerpt.strip():
        excerpt = _e(report.text_excerpt).replace("\n", "<br/>")
        parts += ["<h2>Text that was checked</h2>", f'<p class="excerpt">{excerpt}</p>']
    parts.append(
        '<p class="muted" style="margin-top:12pt">This is an automated risk assessment, not a legal verdict. A low score does '
        "not guarantee an offer is real - always confirm directly with the employer through contact details you find "
        "yourself." + (f" Online copy of this report: {_e(report_url)}" if report_url else "") + "</p>"
    )
    return "".join(parts)


def render_pdf(report: AnalysisReport, report_id: str, checked_at: str, report_url: str | None = None) -> bytes:
    story = pymupdf.Story(html=_html(report, report_id, checked_at, report_url), user_css=CSS)
    buffer = io.BytesIO()
    writer = pymupdf.DocumentWriter(buffer)
    more = True
    while more:
        device = writer.begin_page(PAGE)
        more, _ = story.place(CONTENT)
        story.draw(device)
        writer.end_page()
    writer.close()

    doc = pymupdf.open("pdf", buffer.getvalue())
    for number, page in enumerate(doc, start=1):
        page.insert_text(
            (42, PAGE.height - 30), f"Offer Letter Checker · report {report_id} · page {number} of {doc.page_count}",
            fontsize=7.5, fontname="helv", color=(0.45, 0.45, 0.48),
        )
    doc.set_metadata({"title": f"Offer Letter Checker report {report_id}", "producer": "Offer Letter Checker", "creator": "Offer Letter Checker"})
    return doc.tobytes(garbage=3, deflate=True)
