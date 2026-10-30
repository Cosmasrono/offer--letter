import type { Report } from "@offer-checker/prisma-client-v2";
import { prisma } from "./prisma";
import { canViewReport, type CurrentUser } from "./session";
import { memoryKeys, patternGroup, similarity, validFingerprint } from "./scam-memory";
import { reportStatus } from "./scam-status";
import { readOfferConfirmation } from "./offer-confirmation";
import type { AnalysisReport, Entities, Finding, Fingerprint, MemoryMatch, RiskLevel, SourceCheck, VerifyLink } from "./types";
import { activeReports, isReportExpired, type ReportPrivacy } from "./privacy-policy";

const levelFor = (score: number): RiskLevel => score >= 60 ? "HIGH" : score >= 30 ? "MEDIUM" : "LOW";

/** Retrieve eligible cases, including human corrections, without releasing historical letter text. */
export async function applyCommunityReports(report: AnalysisReport): Promise<AnalysisReport> {
  const keys = memoryKeys(report.entities);
  const fingerprint = validFingerprint(report.fingerprint);
  const matchers = [
    ...(keys.length ? [{ memoryIndicatorKeys: { hasSome: keys } }] : []),
    ...(fingerprint ? [{ memoryBands: { hasSome: fingerprint.bands } }] : []),
  ];
  if (!matchers.length) return { ...report, memory_matches: [] };
  const candidates = await prisma.report.findMany({
    where: { AND: [
      activeReports(),
      { OR: [{ memoryConsent: true }, { memoryConsent: null }, { memoryConsent: { isSet: false } }] },
      { OR: [{ scamStatus: "CONFIRMED_SCAM" }, { scamStatus: "REPORTED_SCAM" }, { scamStatus: "SUSPECTED_SCAM", memoryAutoEligible: true }] },
      { OR: matchers },
    ] },
    orderBy: { createdAt: "desc" }, take: 100,
    select: { scamStatus: true, riskLevel: true, userReportedAt: true, memoryIndicatorKeys: true, fingerprint: true },
  });
  const grouped = new Map<MemoryMatch["status"], { details: Set<string>; similarity: number; patterns: Set<string>; strong: boolean }>();
  for (const candidate of candidates) {
    const status = reportStatus(candidate);
    if (status !== "CONFIRMED_SCAM" && status !== "REPORTED_SCAM" && status !== "SUSPECTED_SCAM") continue;
    const storedFingerprint = validFingerprint(candidate.fingerprint);
    const share = similarity(fingerprint, storedFingerprint);
    const details = keys.filter(key => candidate.memoryIndicatorKeys.includes(key));
    if (!details.length && share < .5) continue;
    const group = grouped.get(status) ?? { details: new Set<string>(), similarity: 0, patterns: new Set<string>(), strong: false };
    details.forEach(detail => group.details.add(detail));
    group.similarity = Math.max(group.similarity, share);
    group.strong ||= Boolean(details.length && share >= .8);
    group.patterns.add(patternGroup(storedFingerprint, candidate.memoryIndicatorKeys));
    grouped.set(status, group);
  }
  const matches: MemoryMatch[] = [...grouped].map(([status, group]) => ({
    status, matching_details: [...group.details].slice(0, 10),
    template_similarity: group.similarity >= .5 ? Math.round(group.similarity * 100) / 100 : null,
    case_count: group.patterns.size,
    contact_and_template: group.strong,
  }));
  if (!matches.length) return { ...report, memory_matches: [] };
  const findings: Finding[] = matches.map(match => {
    const confirmed = match.status === "CONFIRMED_SCAM";
    const reported = match.status === "REPORTED_SCAM";
    const details = match.matching_details.map(key => key.replace(/^[A-Z]+:/, ""));
    const parts = [details.length && `Matching contact/payment details: ${details.join(", ")}.`,
      match.template_similarity !== null && `About ${Math.round(match.template_similarity * 100)}% wording similarity.`].filter(Boolean);
    return {
      id: `scam_memory_${match.status.toLowerCase()}`,
      title: confirmed ? "Matches a reviewed, confirmed scam case" : reported ? "Matches a user-reported scam awaiting review" : "Matches a previously flagged high-risk pattern",
      detail: `${parts.join(" ")} ${confirmed ? "An administrator confirmed the earlier case as a scam." : "This match has not been confirmed by a reviewer."} ${match.case_count} distinct stored pattern(s). A copied template alone does not prove fraud.`,
      severity: confirmed ? "high" : "medium", category: "community", points: confirmed ? (details.length ? 35 : 30) : reported ? 15 : 10,
    };
  });
  let score = Math.min(100, report.score + findings.reduce((total, finding) => total + finding.points, 0));
  const strong = matches.some(match => match.status === "CONFIRMED_SCAM" && match.contact_and_template);
  if (strong) score = Math.max(score, 60);
  const summary = strong ? "This document reuses wording and contact or payment details from a reviewed scam. Do not send money or documents before independent verification."
    : "This document matches details or wording from earlier flagged cases. Review the matching evidence and verify the sender independently.";
  return { ...report, score, risk_level: levelFor(score), summary, memory_matches: matches, findings: [...findings, ...report.findings] };
}

export async function saveReport(report: AnalysisReport, userId: string | null, baseline: { score: number; riskLevel: RiskLevel } | undefined, privacy: ReportPrivacy): Promise<string> {
  const fingerprint = validFingerprint(report.fingerprint);
  const base = baseline ?? { score: report.score, riskLevel: report.risk_level };
  const sponsorshipOnly = report.findings.some(finding => finding.id === "cos_expired" || finding.id.startsWith("sponsor_registry_"))
    && !report.findings.some(finding => finding.severity === "critical")
    && report.findings.filter(finding => finding.id !== "cos_expired" && !finding.id.startsWith("sponsor_registry_")).reduce((total, finding) => total + finding.points, 0) < 60;
  const autoEligible = report.kind !== "visa" && base.riskLevel === "HIGH" && !sponsorshipOnly;
  const share = privacy.memoryConsent && report.kind !== "visa";
  const saved = await prisma.report.create({ data: {
    ...privacy,
    userId, fileName: report.file_name, kind: report.kind, riskLevel: report.risk_level, score: report.score,
    country: report.country, countryName: report.country_name, companyName: report.company_name, jobTitle: report.job_title,
    summary: report.summary, findings: report.findings, advice: report.advice, verifyLinks: report.verify_links,
    entities: report.entities, textExcerpt: report.text_excerpt, extractionMethod: report.extraction_method,
    aiUsed: report.ai_used, warnings: report.warnings, checksNotRun: report.checks_not_run,
    sourceChecks: report.source_checks ?? [], visa: report.visa ? JSON.parse(JSON.stringify(report.visa)) : undefined, fingerprint: report.kind === "visa" ? undefined : fingerprint ?? undefined,
    scamStatus: report.kind !== "visa" && report.risk_level === "HIGH" && !sponsorshipOnly ? "SUSPECTED_SCAM" : "UNREVIEWED",
    baseScore: base.score, baseRiskLevel: base.riskLevel, memoryAutoEligible: autoEligible,
    memoryIndicatorKeys: share ? memoryKeys(report.entities) : [], memoryBands: share ? fingerprint?.bands ?? [] : [], memoryIndexedAt: new Date(),
    memoryMatches: report.memory_matches ?? [], reviewVersion: 0,
  } });
  return saved.id;
}

/** Reporting changes status once; it cannot undo an administrator's decision. */
export async function reportAsScam(id: string, user: CurrentUser | null): Promise<"reported" | "already" | "reviewed" | "missing"> {
  const report = await prisma.report.findUnique({ where: { id } });
  if (!report || !canViewReport(report, user)) return "missing";
  if (["CONFIRMED_SCAM", "CLEARED"].includes(reportStatus(report))) return "reviewed";
  const fingerprint = validFingerprint(report.fingerprint);
  const { count } = await prisma.report.updateMany({
    where: { id, AND: [
      { OR: [{ userReportedAt: null }, { userReportedAt: { isSet: false } }] },
      { OR: [{ reviewVersion: report.reviewVersion ?? 0 }, { reviewVersion: { isSet: false } }, { reviewVersion: null }] },
    ] },
    data: { userReportedAt: new Date(), scamStatus: "REPORTED_SCAM", reviewVersion: (report.reviewVersion ?? 0) + 1,
      memoryIndicatorKeys: report.kind === "visa" || report.memoryConsent === false ? [] : memoryKeys(report.entities as Partial<Entities>), memoryBands: report.kind === "visa" || report.memoryConsent === false ? [] : fingerprint?.bands ?? [], memoryIndexedAt: new Date() },
  });
  return count ? "reported" : "already";
}

export class ReviewConflict extends Error {}

/** Atomic decision and audit entry. Clearing a case excludes it from subsequent memory searches. */
export async function reviewScam(id: string, action: "CONFIRM_SCAM" | "CLEAR" | "REOPEN", note: string, sourceUrl: string | null, reviewer: CurrentUser) {
  if (!reviewer.isAdmin) throw new Error("Administrator access required.");
  const report = await prisma.report.findUnique({ where: { id } });
  if (!report || isReportExpired(report)) return null;
  const previous = reportStatus(report);
  const next = action === "CONFIRM_SCAM" ? "CONFIRMED_SCAM" : action === "CLEAR" ? "CLEARED" : report.userReportedAt ? "REPORTED_SCAM" : "SUSPECTED_SCAM";
  const history = Array.isArray(report.reviewHistory) ? report.reviewHistory : [];
  if (history.length >= 100) throw new ReviewConflict("This case has reached its review-history limit.");
  const now = new Date();
  const fingerprint = validFingerprint(report.fingerprint);
  const { count } = await prisma.report.updateMany({
    where: { id, OR: [{ reviewVersion: report.reviewVersion ?? 0 }, { reviewVersion: { isSet: false } }, { reviewVersion: null }] },
    data: { scamStatus: next, reviewVersion: (report.reviewVersion ?? 0) + 1, reviewNote: note,
      reviewedAt: now, reviewedById: reviewer.id,
      reviewHistory: [...history, { action, from: previous, to: next, at: now.toISOString(), reviewerId: reviewer.id, note, sourceUrl }],
      memoryIndicatorKeys: report.kind === "visa" || report.memoryConsent === false ? [] : memoryKeys(report.entities as Partial<Entities>), memoryBands: report.kind === "visa" || report.memoryConsent === false ? [] : fingerprint?.bands ?? [], memoryIndexedAt: now },
  });
  if (!count) throw new ReviewConflict("Another update changed this case. Refresh before reviewing again.");
  return { scamStatus: next, reviewedAt: now.toISOString() };
}

export function toAnalysisReport(r: Report): AnalysisReport {
  return {
    file_name: r.fileName, kind: r.kind === "visa" ? "visa" : r.kind === "message" ? "message" : "letter", risk_level: r.riskLevel as RiskLevel,
    score: r.score, country: r.country, country_name: r.countryName, company_name: r.companyName, job_title: r.jobTitle,
    summary: r.summary, findings: r.findings as unknown as Finding[], advice: r.advice, verify_links: r.verifyLinks as unknown as VerifyLink[],
    entities: { ...({ agency_name: null, agency_licence: null, payment_accounts: [] } satisfies Partial<Entities>), ...(r.entities as unknown as Entities) },
    text_excerpt: r.textExcerpt, extraction_method: r.extractionMethod, ai_used: r.aiUsed, warnings: r.warnings,
    checks_not_run: r.checksNotRun ?? [], source_checks: (r.sourceChecks as unknown as SourceCheck[] | null) ?? [],
    fingerprint: r.fingerprint as unknown as Fingerprint | null,
    scam_status: reportStatus(r), review_note: r.reviewNote, reviewed_at: r.reviewedAt?.toISOString() ?? null,
    memory_matches: (r.memoryMatches as unknown as MemoryMatch[] | null) ?? [],
    offer_confirmation: readOfferConfirmation(r.reviewHistory, reportStatus(r)),
    visa: (r.visa as unknown as AnalysisReport["visa"]) ?? null,
  };
}

export const isObjectId = (id: string) => /^[a-f0-9]{24}$/i.test(id);
