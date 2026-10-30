import unittest

from app.models import AnalysisReport, Entities, OfferConfirmation, SourceCheck
from app.verification import verification_summary


def report(checks=None, **changes):
    return AnalysisReport(file_name="fixture.txt", kind="letter", risk_level="LOW", score=0, country=None, country_name=None,
                          company_name="Example Ltd", job_title="Tester", summary="Check independently.", findings=[], advice=[],
                          verify_links=[], entities=Entities(), text_excerpt="Fictional fixture", extraction_method="plain-text", ai_used=False,
                          warnings=[], checks_not_run=[], fingerprint=None, source_checks=checks or [], **changes)


def check(category, status):
    return SourceCheck(check=category, status=status, subject="Example", source_name="Fixture", source_url="https://example.com/",
                       checked_at="2026-10-27T10:00:00Z", detail="Fixture source comparison.")


class VerificationCompletenessTests(unittest.TestCase):
    def test_low_risk_and_missing_evidence_are_separate(self):
        current = report()
        result = verification_summary(current)
        self.assertEqual(result.level, "LIMITED")
        self.assertEqual(result.resolved, 0)
        self.assertEqual(result.required, 6)
        self.assertEqual(current.risk_level, "LOW")

    def test_registration_and_website_matches_cannot_confirm_private_offer(self):
        current = report([check("employer", "MATCHED"), check("website", "MATCHED"), check("agency", "NOT_APPLICABLE")])
        result = verification_summary(current)
        self.assertEqual(result.level, "PARTIAL")
        self.assertEqual(result.required, 5)
        self.assertEqual(next(item.status for item in result.items if item.id == "offer"), "UNVERIFIED")

    def test_conflict_counts_as_evidence_but_never_complete_verification(self):
        current = report([check("employer", "MISMATCH"), check("email", "MISMATCH")])
        result = verification_summary(current)
        self.assertEqual(result.level, "PARTIAL")
        self.assertEqual(result.resolved, 2)

    def test_only_documented_confirmation_can_complete_offer_check_and_does_not_reduce_risk(self):
        confirmation = OfferConfirmation(status="CONFIRMED", employer_contact="hr@example.com", source_url="https://example.com/contact",
                                         offer_reference="OFFER-123", job_title="Tester", confirmed_at="2026-10-26T10:00:00Z", recorded_at="2026-10-27T10:00:00Z", note="Employer confirmed the recruiter and offer terms.")
        current = report([check("employer", "MATCHED"), check("discovery", "MATCHED"), check("website", "MATCHED"), check("agency", "NOT_APPLICABLE")], offer_confirmation=confirmation)
        current.score, current.risk_level = 80, "HIGH"
        result = verification_summary(current)
        self.assertEqual(result.level, "COMPLETE")
        self.assertEqual(current.score, 80)
        current.scam_status = "CONFIRMED_SCAM"
        self.assertNotEqual(verification_summary(current).level, "COMPLETE")


if __name__ == "__main__":
    unittest.main()
