"""Online checks: how old is the domain the 'company' uses?"""

import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from datetime import datetime, timezone

from .models import Finding
from .rules import FREE_EMAIL_DOMAINS

WHOIS_TIMEOUT_SECONDS = 8


def _creation_date(domain: str) -> datetime | None:
    import whois

    # Socket errors must raise: ignoring them makes a network failure look like an empty (unknown) domain.
    record = whois.whois(domain, quiet=True, ignore_socket_errors=False, timeout=WHOIS_TIMEOUT_SECONDS)
    created = record.creation_date
    if isinstance(created, list):
        created = min(d for d in created if d)
    if not isinstance(created, datetime):
        return None
    return created if created.tzinfo else created.replace(tzinfo=timezone.utc)


def domain_age_findings(domains: list[str]) -> tuple[list[Finding], list[str]]:
    """Return (findings, checks_not_run). A failed lookup is reported as 'not checked', never as a red flag."""
    from whois.exceptions import WhoisDomainNotFoundError

    candidates = [d for d in domains if d not in FREE_EMAIL_DOMAINS][:2]
    if not candidates:
        return [], ["Website domain age: there is no company website or email domain to look up."]
    if os.getenv("ENABLE_DOMAIN_LOOKUP", "true").lower() != "true":
        return [], ["Website domain age: lookups are switched off on this server."]
    findings: list[Finding] = []
    not_run: list[str] = []

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {d: pool.submit(_creation_date, d) for d in candidates}
        for domain, future in futures.items():
            try:
                created = future.result(timeout=WHOIS_TIMEOUT_SECONDS)
            except FutureTimeout:
                not_run.append(f"Website domain age for {domain}: the registry did not answer in time.")
                continue
            except WhoisDomainNotFoundError as e:
                if "no whois server" in str(e).lower():
                    not_run.append(f"Website domain age for {domain}: this country's registry has no public lookup.")
                    continue
                findings.append(Finding(
                    id=f"domain_unregistered:{domain}", title="Website domain not found",
                    detail=f"No registration record was found for {domain}. It may not exist or may be misspelled.",
                    severity="medium", category="company", points=10,
                ))
                continue
            except Exception:
                # Network errors, unsupported country domains (some .ke, .qa...) and unreadable replies.
                not_run.append(f"Website domain age for {domain}: the registry lookup failed.")
                continue
            if created is None:
                not_run.append(f"Website domain age for {domain}: the registration date is not public.")
                continue
            days = (datetime.now(timezone.utc) - created).days
            if days < 180:
                findings.append(Finding(
                    id=f"domain_new:{domain}", title="Very new website domain",
                    detail=f"{domain} was registered only {days} days ago. Scammers create fresh domains that imitate real companies.",
                    severity="high", category="company", points=20,
                ))
            elif days < 365:
                findings.append(Finding(
                    id=f"domain_young:{domain}", title="Website domain is less than a year old",
                    detail=f"{domain} was registered {days} days ago.",
                    severity="medium", category="company", points=10,
                ))
            elif days > 5 * 365:
                findings.append(Finding(
                    id=f"domain_established:{domain}", title="Long-established domain",
                    detail=f"{domain} has been registered for about {days // 365} years. "
                    "Still check it really belongs to the company - scammers copy real domains too.",
                    severity="info", category="company", points=-8,
                ))
    return findings, not_run
