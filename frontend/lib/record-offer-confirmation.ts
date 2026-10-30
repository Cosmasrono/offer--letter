import { prisma } from "./prisma";
import { isReportExpired } from "./privacy-policy";
import type { CurrentUser } from "./session";
import type { OfferConfirmation } from "./types";

export class ConfirmationInputError extends Error {}
export class ConfirmationConflict extends Error {}

export async function recordOfferConfirmation(id: string, body: Record<string, unknown>, reviewer: CurrentUser) {
  if (!reviewer.isAdmin) throw new ConfirmationInputError("Administrator access required.");
  const status = body.status;
  if (!["CONFIRMED", "DENIED", "REVOKED"].includes(String(status))) throw new ConfirmationInputError("Choose a confirmation outcome.");
  const field = (name: string, max: number) => {
    const value = typeof body[name] === "string" ? body[name].trim() : "";
    if (value.length > max) throw new ConfirmationInputError("A confirmation field is too long.");
    return value;
  };
  const note = field("note", 2000);
  if (note.length < 30) throw new ConfirmationInputError("Describe the employer response and its evidence in at least 30 characters.");
  const employer_contact = field("employer_contact", 250);
  const offer_reference = field("offer_reference", 150);
  const job_title = field("job_title", 150);
  let source_url = field("source_url", 1000);
  let confirmed_at = field("confirmed_at", 60);
  if (status !== "REVOKED") {
    if (!employer_contact || !offer_reference || !job_title || body.independentContact !== true) {
      throw new ConfirmationInputError("Record the independently sourced employer contact, offer reference and role.");
    }
    try {
      const source = new URL(source_url);
      if (source.protocol !== "https:" || source.username || source.password || !source.hostname.includes(".")) throw new Error();
      source_url = source.href;
    } catch { throw new ConfirmationInputError("Supply the HTTPS page used to independently find the employer contact."); }
    const date = new Date(confirmed_at);
    if (!Number.isFinite(date.getTime()) || date.getTime() > Date.now()) throw new ConfirmationInputError("Enter when the employer responded; it cannot be in the future.");
    confirmed_at = date.toISOString();
    if (status === "CONFIRMED" && (body.recruiterConfirmed !== true || body.termsConfirmed !== true)) {
      throw new ConfirmationInputError("Employer confirmation must cover the recruiter and the offer's reference, role and terms.");
    }
  }
  const report = await prisma.report.findUnique({ where: { id } });
  if (!report || isReportExpired(report)) return null;
  if (report.kind === "visa") throw new ConfirmationInputError("Record employer confirmation on the offer-letter report, not a visa document.");
  if (status === "CONFIRMED" && (!report.companyName || report.scamStatus === "CONFIRMED_SCAM")) {
    throw new ConfirmationConflict("Identify the employer and resolve any confirmed scam decision before recording a confirmed offer.");
  }
  const history = Array.isArray(report.reviewHistory) ? report.reviewHistory : [];
  if (history.length >= 100) throw new ConfirmationConflict("This report has reached its review-history limit.");
  const now = new Date().toISOString();
  const confirmation: OfferConfirmation = { status: status as OfferConfirmation["status"], employer_contact, source_url, offer_reference, job_title,
    confirmed_at, recorded_at: now, note };
  const { count } = await prisma.report.updateMany({
    where: { id, OR: [{ reviewVersion: report.reviewVersion ?? 0 }, { reviewVersion: { isSet: false } }, { reviewVersion: null }] },
    data: { reviewVersion: (report.reviewVersion ?? 0) + 1,
      reviewHistory: [...history, { action: "RECORD_OFFER_CONFIRMATION", at: now, reviewerId: reviewer.id,
        independentContact: body.independentContact === true, recruiterConfirmed: body.recruiterConfirmed === true,
        termsConfirmed: body.termsConfirmed === true, confirmation }] },
  });
  if (!count) throw new ConfirmationConflict("Another reviewer changed this report. Refresh before saving again.");
  return confirmation;
}
