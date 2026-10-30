"""Evidence coverage is separate from fraud risk; AI opinions never complete identity checks."""

from .models import AnalysisReport, VerificationItem, VerificationSummary


def verification_summary(report: AnalysisReport) -> VerificationSummary:
    if report.kind == "visa" and report.visa:
        comparisons = report.visa.comparisons
        items = [VerificationItem(id="government", label="Government visa status", status="UNVERIFIED", detail="No government lookup was performed. Use the official portal guidance.")]
        for comparison in comparisons:
            items.append(VerificationItem(id="visa_" + comparison.field, label=comparison.field,
                status="SUPPORTED" if comparison.status == "MATCHED" else "CONFLICT" if comparison.status == "MISMATCH" else "UNVERIFIED", detail=comparison.detail))
        resolved = sum(item.status in {"SUPPORTED", "CONFLICT"} for item in items)
        return VerificationSummary(level="PARTIAL" if resolved else "LIMITED", resolved=resolved, required=len(items), items=items)
    items = []
    categories = [("employer", "Employer registration"), ("discovery", "Independent website research"),
                  ("website", "Website details"), ("agency", "Recruitment agency permission")]
    if any(check.check == "sponsorship" for check in report.source_checks):
        categories.append(("sponsorship", "UK sponsorship record"))
    if any(check.check == "sponsor_registry" for check in report.source_checks):
        categories.append(("sponsor_registry", "Current UK sponsor permission"))
    if any(check.check == "care_provider" for check in report.source_checks):
        categories.append(("care_provider", "England care-provider registration"))
    for category, label in categories:
        sources = [check for check in report.source_checks if check.check == category]
        state = "UNVERIFIED"
        detail = "No conclusive evidence was saved for this check."
        if sources:
            if any(source.status == "MISMATCH" for source in sources):
                state, detail = "CONFLICT", "The checked sources contain differences that need resolving."
            elif any(source.status == "MATCHED" for source in sources):
                state, detail = "SUPPORTED", "Details matched in the named source; this does not authenticate the offer."
            elif all(source.status == "NOT_APPLICABLE" for source in sources):
                state, detail = "NOT_APPLICABLE", "No recruitment agency was identified."
            else:
                detail = sources[0].detail
        items.append(VerificationItem(id=category, label=label, status=state, detail=detail))
    confirmation = report.offer_confirmation
    confirmed = bool(confirmation and confirmation.status == "CONFIRMED" and report.scam_status != "CONFIRMED_SCAM")
    email_conflict = any(check.check == "email" and check.status == "MISMATCH" for check in report.source_checks)
    items.append(VerificationItem(id="sender", label="Recruiter / sender identity",
                                  status="SUPPORTED" if confirmed else "CONFLICT" if email_conflict else "UNVERIFIED",
                                  detail="A reviewer recorded employer confirmation of the recruiter and offer." if confirmed
                                  else "Email header consistency alone does not authenticate the sender. Confirm the recruiter through independently sourced employer contacts."))
    denied = bool(confirmation and confirmation.status == "DENIED")
    items.append(VerificationItem(id="offer", label="Actual offer and terms",
                                  status="SUPPORTED" if confirmed else "CONFLICT" if denied else "UNVERIFIED",
                                  detail="Direct employer confirmation was recorded by a reviewer." if confirmed else "A reviewer recorded that the employer denied this offer." if denied
                                  else "The employer has not confirmed the offer reference, recruiter and job terms."))
    required = sum(item.status != "NOT_APPLICABLE" for item in items)
    resolved = sum(item.status in {"SUPPORTED", "CONFLICT"} for item in items)
    # A conflict is evidence, but can never be called complete verification.
    complete = required > 0 and all(item.status in {"SUPPORTED", "NOT_APPLICABLE"} for item in items)
    return VerificationSummary(level="COMPLETE" if complete else "PARTIAL" if resolved else "LIMITED",
                               resolved=resolved, required=required, items=items)
