// Mirrors backend/app/models.py

export type RiskLevel = "LOW" | "MEDIUM" | "HIGH";
export type ScamStatus = "UNREVIEWED" | "SUSPECTED_SCAM" | "REPORTED_SCAM" | "CONFIRMED_SCAM" | "CLEARED";
export type MemoryMatch = {
  status: "CONFIRMED_SCAM" | "REPORTED_SCAM" | "SUSPECTED_SCAM";
  matching_details: string[];
  template_similarity: number | null;
  case_count: number;
  contact_and_template?: boolean;
};
// An offer letter, or a job ad / SMS / chat message (checked with gentler rules).
export type Kind = "letter" | "message" | "visa";
export type Severity = "info" | "low" | "medium" | "high" | "critical";

export type Finding = {
  id: string;
  title: string;
  detail: string;
  severity: Severity;
  category: "content" | "contact" | "company" | "document" | "country" | "ai" | "community";
  points: number;
};

export type Entities = {
  emails: string[];
  phones: string[];
  urls: string[];
  domains: string[];
  money: string[];
  fee_mentions: string[];
  payment_accounts: string[];
  company_name: string | null;
  job_title: string | null;
  agency_name: string | null;
  agency_licence: string | null;
  company_registration_number?: string | null;
  agency_emails?: string[];
};

export type SourceCheck = {
  check: "employer" | "agency" | "website" | "discovery" | "email" | "sponsorship" | "sponsor_registry" | "care_provider";
  status: "MATCHED" | "MISMATCH" | "NOT_FOUND" | "UNAVAILABLE" | "UNVERIFIED" | "NOT_APPLICABLE";
  subject: string;
  source_name: string;
  source_url: string;
  checked_at: string;
  detail: string;
  record_name?: string | null;
  record_id?: string | null;
  record_status?: string | null;
  source_updated_at?: string | null;
  checked_pages?: string[];
  comparisons?: { field: string; letter_value: string; source_value: string; status: "MATCHED" | "MISMATCH" | "UNVERIFIED"; detail: string }[];
};

export type Fingerprint = { signature: number[]; bands: string[] };

export type VerifyLink = { label: string; url: string };

export type AnalysisReport = {
  file_name: string;
  kind: Kind;
  risk_level: RiskLevel;
  score: number;
  country: string | null;
  country_name: string | null;
  company_name: string | null;
  job_title: string | null;
  summary: string;
  findings: Finding[];
  advice: string[];
  verify_links: VerifyLink[];
  entities: Entities;
  text_excerpt: string;
  extraction_method: string;
  ai_used: boolean;
  warnings: string[];
  checks_not_run: string[];
  fingerprint: Fingerprint | null;
  source_checks?: SourceCheck[];
  offer_confirmation?: OfferConfirmation | null;
  verification?: VerificationSummary | null;
  visa?: VisaAssessment | null;
  scam_status?: ScamStatus;
  review_note?: string | null;
  reviewed_at?: string | null;
  memory_matches?: MemoryMatch[];
};

export type VisaDetails = {
  holder_name: string | null; passport_number: string | null; visa_number: string | null;
  nationality: string | null; sponsor: string | null; job_title: string | null;
  visa_type: string | null; issue_date: string | null; expiry_date: string | null;
};
export type VisaPreview = {
  country: "QA" | "KW"; detected_country: string | null; details: VisaDetails;
  offer_details: VisaDetails | null; warnings: string[];
};
export type VisaAssessment = {
  details: VisaDetails; extracted_details: VisaDetails; offer_details: VisaDetails | null;
  extracted_offer_details: VisaDetails | null; offer_file_name: string | null; detected_country: string | null;
  corrections: string[]; official_status: "NOT_CHECKED";
  comparisons: { field: string; visa_value: string | null; offer_value: string | null; status: "MATCHED" | "MISMATCH" | "UNVERIFIED"; detail: string }[];
  guidance: { source_name: string; source_url: string; steps: string[] };
};

export type OfferConfirmation = {
  status: "CONFIRMED" | "DENIED" | "REVOKED";
  employer_contact: string;
  source_url: string;
  offer_reference: string;
  job_title: string;
  confirmed_at: string;
  recorded_at: string;
  note: string;
};

export type VerificationSummary = {
  level: "LIMITED" | "PARTIAL" | "COMPLETE";
  resolved: number;
  required: number;
  items: { id: string; label: string; status: "SUPPORTED" | "CONFLICT" | "UNVERIFIED" | "NOT_APPLICABLE"; detail: string }[];
};

export type AnalyzeResponse = {
  // Only a previously paid legacy credit may provide a token at scan time.
  token?: string;
  id: string | null;
  report: AnalysisReport | null;
};
