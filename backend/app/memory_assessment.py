"""Use retrieved database evidence in the AI explanation without letting AI erase deterministic evidence."""

from . import ai
from .models import AnalysisReport


def assess_memory(report: AnalysisReport) -> dict:
    if not report.memory_matches:
        return {"summary": report.summary, "ai_used": False, "warning": None}
    verdict, warning = ai.analyze(report.text_excerpt, report.entities, report.findings, report.country_name,
                                 report.kind, memory_matches=report.memory_matches, request_timeout=12, source_checks=report.source_checks)
    if verdict and verdict.risk_level == report.risk_level:
        return {"summary": verdict.summary, "ai_used": True, "warning": warning}
    return {"summary": report.summary, "ai_used": False,
            "warning": warning or ("The AI explanation differed from the database warning; the matched evidence was retained."
                                   if verdict else "The AI could not assess the saved-case context. Database matches were still applied.")}
