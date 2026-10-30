"""Country profiles: how to recognise the destination country and what a genuine offer looks like there.

To add a country, add an entry to COUNTRIES. `keywords` help auto-detect the country from the letter,
`permit_terms` are words a genuine offer for that country usually mentions, and `verify_links` are
official places a job seeker can check the employer or agency.
"""

from dataclasses import dataclass, field


@dataclass
class Country:
    code: str
    name: str
    keywords: list[str]
    phone_codes: list[str]
    currencies: list[str]
    permit_terms: list[str]
    fee_rule: str
    verify_links: list[dict[str, str]] = field(default_factory=list)


COUNTRIES: dict[str, Country] = {
    c.code: c
    for c in [
        Country(
            code="AE",
            name="United Arab Emirates",
            keywords=["dubai", "abu dhabi", "sharjah", "ajman", "uae", "united arab emirates", "emirates", "ras al khaimah"],
            phone_codes=["+971", "00971"],
            currencies=["AED", "dirham"],
            permit_terms=["mohre", "work permit", "labour contract", "employment contract", "emirates id", "entry permit", "residence visa"],
            fee_rule="UAE law prohibits charging workers recruitment or visa fees - the employer pays them.",
            verify_links=[
                {"label": "Ministry of Human Resources & Emiratisation (MOHRE)", "url": "https://www.mohre.gov.ae"},
            ],
        ),
        Country(
            code="SA",
            name="Saudi Arabia",
            keywords=["saudi", "riyadh", "jeddah", "dammam", "mecca", "makkah", "medina", "ksa", "neom"],
            phone_codes=["+966", "00966"],
            currencies=["SAR", "riyal"],
            permit_terms=["iqama", "qiwa", "musaned", "work visa", "employment contract"],
            fee_rule="Saudi labour law makes the employer responsible for recruitment, visa and iqama fees.",
            verify_links=[
                {"label": "Qiwa (Ministry of Human Resources platform)", "url": "https://qiwa.sa"},
                {"label": "Musaned (domestic worker recruitment)", "url": "https://musaned.com.sa"},
            ],
        ),
        Country(
            code="QA",
            name="Qatar",
            keywords=["qatar", "doha", "lusail", "al wakrah"],
            phone_codes=["+974", "00974"],
            currencies=["QAR", "riyal"],
            permit_terms=["qid", "work visa", "employment contract", "ministry of labour", "residence permit"],
            fee_rule="Qatari law prohibits recruiters from charging workers recruitment fees.",
            verify_links=[{"label": "Qatar Ministry of Labour", "url": "https://www.mol.gov.qa"}],
        ),
        Country(
            code="CA",
            name="Canada",
            keywords=["canada", "toronto", "vancouver", "calgary", "montreal", "ottawa", "alberta", "ontario", "british columbia", "manitoba", "saskatchewan"],
            phone_codes=["+1"],
            currencies=["CAD", "C$"],
            permit_terms=["lmia", "work permit", "ircc", "job bank", "temporary foreign worker", "noc"],
            fee_rule="Canadian employers may not charge workers recruitment fees or recover the LMIA fee from them.",
            verify_links=[
                {"label": "IRCC - fraud and scams", "url": "https://www.canada.ca/en/immigration-refugees-citizenship/services/protect-fraud.html"},
                {"label": "Job Bank (official job listings)", "url": "https://www.jobbank.gc.ca"},
            ],
        ),
        Country(
            code="GB",
            name="United Kingdom",
            keywords=["united kingdom", "uk", "london", "england", "scotland", "wales", "manchester", "birmingham", "nhs"],
            phone_codes=["+44", "0044"],
            currencies=["GBP", "£", "pound"],
            permit_terms=["certificate of sponsorship", "cos", "skilled worker", "health and care worker", "home office", "sponsor licence"],
            fee_rule="UK sponsors must not make workers pay the Certificate of Sponsorship fee or the Immigration Skills Charge.",
            verify_links=[
                {"label": "Register of licensed sponsors (GOV.UK)", "url": "https://www.gov.uk/government/publications/register-of-licensed-sponsors-workers"},
                {"label": "Companies House company search", "url": "https://find-and-update.company-information.service.gov.uk"},
            ],
        ),
        Country(
            code="US",
            name="United States",
            keywords=["united states", "usa", "u.s.", "new york", "california", "texas", "florida", "h-1b", "h-2b", "h-2a"],
            phone_codes=["+1"],
            currencies=["USD", "US$"],
            permit_terms=["h-1b", "h-2a", "h-2b", "uscis", "petition", "green card", "i-129", "labor certification"],
            fee_rule="US rules bar employers and recruiters from charging H-2A/H-2B workers recruitment fees.",
            verify_links=[
                {"label": "US State Department - work visas", "url": "https://travel.state.gov/content/travel/en/us-visas/employment.html"},
                {"label": "SEC EDGAR company search", "url": "https://www.sec.gov/edgar/search/"},
            ],
        ),
        Country(
            code="AU",
            name="Australia",
            keywords=["australia", "sydney", "melbourne", "brisbane", "perth", "adelaide"],
            phone_codes=["+61", "0061"],
            currencies=["AUD", "A$"],
            permit_terms=["subclass 482", "skills in demand", "sponsorship", "home affairs", "abn", "nomination"],
            fee_rule="It is illegal in Australia to ask for or receive payment in return for visa sponsorship.",
            verify_links=[
                {"label": "ABN Lookup (business register)", "url": "https://abr.business.gov.au"},
                {"label": "Department of Home Affairs", "url": "https://immi.homeaffairs.gov.au"},
            ],
        ),
        Country(
            code="DE",
            name="Germany",
            keywords=["germany", "deutschland", "berlin", "munich", "münchen", "hamburg", "frankfurt", "cologne", "gmbh"],
            phone_codes=["+49", "0049"],
            currencies=["EUR", "€", "euro"],
            permit_terms=["blue card", "residence permit", "aufenthaltstitel", "bundesagentur", "skilled immigration", "visa"],
            fee_rule="Genuine German employers do not ask applicants to pay for a job or a work visa.",
            verify_links=[
                {"label": "Make it in Germany (official portal)", "url": "https://www.make-it-in-germany.com"},
                {"label": "German company register (Handelsregister)", "url": "https://www.handelsregister.de"},
            ],
        ),
        Country(
            code="PL",
            name="Poland",
            keywords=["poland", "polska", "warsaw", "warszawa", "krakow", "kraków", "wroclaw", "gdansk", "poznan", "sp. z o.o"],
            phone_codes=["+48", "0048"],
            currencies=["PLN", "zł", "zloty"],
            permit_terms=["work permit", "zezwolenie na pracę", "voivode", "karta pobytu", "krs"],
            fee_rule="Polish employment agencies may not charge job seekers fees for finding them work.",
            verify_links=[
                {"label": "KRS company search", "url": "https://wyszukiwarka-krs.ms.gov.pl"},
                {"label": "Register of employment agencies (KRAZ)", "url": "https://stor.praca.gov.pl"},
            ],
        ),
    ]
}

# Shown on every report: where to check that a recruitment agency is licensed in the job seeker's home country.
HOME_COUNTRY_LINKS = [
    {"label": "Kenya: NEA recruitment-agency register", "url": "https://neaims.go.ke/home/agencies-info"},
]


def detect_country(text: str, phones: list[str]) -> str | None:
    lower = f" {text.lower()} "
    scores: dict[str, int] = {}
    for code, c in COUNTRIES.items():
        score = sum(2 for k in c.keywords if f" {k} " in lower or f" {k}," in lower or f" {k}." in lower)
        score += sum(1 for cur in c.currencies if cur.lower() in lower)
        score += sum(1 for t in c.permit_terms if t in lower)
        if c.phone_codes != ["+1"]:
            score += sum(2 for p in phones for pc in c.phone_codes if p.replace(" ", "").startswith(pc))
        if score:
            scores[code] = score
    if not scores:
        return None
    best = max(scores, key=lambda k: scores[k])
    return best if scores[best] >= 2 else None
