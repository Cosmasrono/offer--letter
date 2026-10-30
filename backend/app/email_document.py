"""Read original emails without opening links, executing HTML or trusting supplied authentication headers."""

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
from email.utils import getaddresses
from html.parser import HTMLParser

from .entities import EMAIL_RE, domain_of
from .models import Finding, SourceCheck, SourceComparison


class EmailHTML(HTMLParser):
    def __init__(self, content):
        super().__init__(convert_charrefs=True)
        self.words, self.hidden = [], 0
        self.feed(content)

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "template"}:
            self.hidden += 1
        if tag in {"p", "div", "br", "li", "tr"}:
            self.words.append("\n")
        if not self.hidden and tag == "a":
            href = dict(attrs).get("href", "")
            if href.startswith(("https://", "http://", "mailto:")):
                self.words.append(" " + href + " ")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "template"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden:
            self.words.append(data)


@dataclass
class ParsedEmail:
    text: str
    sender_addresses: list[str]
    evidence: SourceCheck
    findings: list[Finding]
    pdf_attachments: list[tuple[str, bytes]]
    warnings: list[str]


def _related(left, right):
    return left == right or left.endswith("." + right) or right.endswith("." + left)


def read_email(data: bytes) -> ParsedEmail:
    try:
        message = BytesParser(policy=policy.default).parsebytes(data)
        if not message.get_all("From"):
            raise ValueError("Choose an original .eml email containing a From header.")
        senders = getaddresses([str(value) for value in message.get_all("From", [])])
        replies = getaddresses([str(value) for value in message.get_all("Reply-To", [])])
        sender_emails = [address.lower() for _, address in senders if EMAIL_RE.fullmatch(address)]
        reply_emails = [address.lower() for _, address in replies if EMAIL_RE.fullmatch(address)]
        findings, comparisons, warnings = [], [], []
        ambiguous = len(message.get_all("From", [])) != 1 or len(sender_emails) != 1
        if ambiguous:
            findings.append(Finding(id="email_ambiguous_sender", title="Original email has an ambiguous sender",
                                    detail="The email has missing, multiple or malformed sender addresses. Independently confirm who sent it.",
                                    severity="medium", category="contact", points=15))
        sender_domains = {domain_of(address) for address in sender_emails}
        reply_domains = {domain_of(address) for address in reply_emails}
        reply_conflict = bool(not ambiguous and reply_domains and not any(_related(left, right) for left in sender_domains for right in reply_domains))
        comparisons.append(SourceComparison(field="Sender and reply address", letter_value=", ".join(sender_emails) or "Ambiguous sender",
                                             source_value=", ".join(reply_emails) or "No separate Reply-To address",
                                             status="MISMATCH" if reply_conflict or ambiguous else "UNVERIFIED",
                                             detail="Replies go to a different domain. This may be an agency or service provider; confirm it with the employer." if reply_conflict
                                             else "These addresses came from the uploaded file and have not been independently authenticated."))
        if reply_conflict:
            findings.append(Finding(id="email_reply_domain_mismatch", title="Recruiter email sends replies to a different domain",
                                    detail=f"From: {', '.join(sender_emails)}. Reply-To: {', '.join(reply_emails)}. Confirm this alternate contact before sending information.",
                                    severity="medium", category="contact", points=15))
        displayed_emails = [address.lower() for name, _ in senders for address in EMAIL_RE.findall(name)]
        if displayed_emails and not set(displayed_emails) <= set(sender_emails):
            findings.append(Finding(id="email_disguised_sender", title="Displayed sender email differs from the actual address",
                                    detail=f"The sender label contains {', '.join(displayed_emails)}, while the actual From address is {', '.join(sender_emails)}.",
                                    severity="high", category="contact", points=25))
        signing_domains = sorted(set(domain.lower() for header in message.get_all("DKIM-Signature", [])
                                     for domain in re.findall(r"(?:^|;)\s*d=([a-zA-Z0-9.-]+)", str(header))))[:10]
        comparisons.append(SourceComparison(field="Email signing domain", letter_value=", ".join(sorted(sender_domains)) or "Unknown",
                                             source_value=", ".join(signing_domains) or "No DKIM signature supplied", status="UNVERIFIED",
                                             detail="Signing domains are read from supplied headers. Cryptographic signature verification has not run; a matching domain or signature alone does not confirm the offer."))
        authentication = [str(value)[:1500] for value in message.get_all("Authentication-Results", [])][:3]
        comparisons.append(SourceComparison(field="Claimed email authentication", letter_value="Uploaded email",
                                             source_value="; ".join(authentication) or "No Authentication-Results header supplied", status="UNVERIFIED",
                                             detail="Uploaded headers can be forged or edited. Supplied SPF/DKIM/DMARC pass claims are not treated as verified results or trust points."))
        body = message.get_body(preferencelist=("plain", "html"))
        text = ""
        if body is not None:
            text = body.get_content()
            if body.get_content_type() == "text/html":
                text = "".join(EmailHTML(text).words)
        attachments, size = [], 0
        for index, part in enumerate(message.walk()):
            if index >= 50:
                warnings.append("Only the first 50 email MIME parts were inspected.")
                break
            filename = part.get_filename() or ""
            if filename.lower().endswith(".pdf") and not part.is_multipart():
                if len(attachments) >= 3:
                    warnings.append("Only the first three PDF attachments were read.")
                    continue
                content = part.get_payload(decode=True) or b""
                size += len(content)
                if size > 10 * 1024 * 1024:
                    raise ValueError("Decoded email attachments exceed 10 MB.")
                attachments.append((filename, content))
        evidence = SourceCheck(check="email", status="MISMATCH" if findings else "UNVERIFIED", subject=", ".join(sender_emails) or "Email sender",
                               source_name="Uploaded original email (.eml)", source_url="", checked_at=datetime.now(timezone.utc).isoformat(),
                               comparisons=comparisons, detail="Compared sender, reply address and supplied signing headers. The uploaded email is evidence to inspect, not an independently trusted source of authentication.")
        return ParsedEmail(text=text[:100_000], sender_addresses=sender_emails + reply_emails, evidence=evidence,
                           findings=findings, pdf_attachments=attachments, warnings=warnings)
    except (RecursionError, LookupError, TypeError) as error:
        raise ValueError("The original email could not be read. Export it again as .eml.") from error
