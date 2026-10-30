"""Test set of job ads and recruiter messages (WhatsApp, Facebook, SMS), checked in "message" mode.

Every company, person, number and handle here is FICTIONAL. The agencies are in samples/nea_agencies_sample.csv
or deliberately missing from it. expected:  "REAL" -> should score LOW      "FAKE" -> should score HIGH
"""

from dataclasses import dataclass


@dataclass
class Message:
    name: str
    expected: str  # REAL | FAKE
    note: str
    text: str


MESSAGES: list[Message] = [
    # ------------------------------------------------------------------ REAL-style
    Message(
        name="real_agency_facebook_ad", expected="REAL",
        note="Facebook ad from an NEA-accredited agency that says the employer pays all costs",
        text="""Savannah Bridge Recruitment Agency (NEA licence NEA/PEA/2025/0412) is recruiting 20 HVAC technicians
for Corniche Facilities in Doha, Qatar.
Salary QAR 3,200 per month + food allowance. 2-year contract.
Employer pays visa, air ticket and medical.
Trade test on 12 November at our Moi Avenue office, Nairobi.
Apply: jobs@savannahbridge.co.ke
We never charge candidates any fee.""",
    ),
    Message(
        name="real_employer_sms", expected="REAL",
        note="SMS from an employer's HR confirming an interview, pointing to the official email",
        text="""Hi Grace, this is Northwind Logistics HR. Your second interview for the Warehouse Operations Supervisor
role is confirmed for Thu 3 Sep, 10:00 UK time on Teams. The link was sent to your email from
careers@northwindlogistics.co.uk. Reply YES to confirm.""",
    ),
    Message(
        name="real_agency_whatsapp_urgent", expected="REAL",
        note="Honest 'urgently hiring' WhatsApp ad with exclamation marks from an accredited agency (gentler rules)",
        text="""URGENTLY HIRING!! Kilima Jobs International Ltd
Housekeepers needed for 4-star hotels in Dubai, UAE!
Salary AED 1,800 + accommodation and transport.
No fees charged - all costs paid by the employer.
Interviews at our Nairobi office every Tuesday!
WhatsApp 0722 000 118 for details!""",
    ),
    # ------------------------------------------------------------------ FAKE-style
    Message(
        name="fake_dubai_whatsapp_ad", expected="FAKE",
        note="Forwarded WhatsApp ad: fee listed without 'you must pay', M-Pesa till, passport over WhatsApp",
        text="""🔥 DUBAI JOBS 🔥
Cleaners, drivers, security guards needed URGENTLY
Salary 120,000/= per month
Free visa, free ticket, free accommodation!
Registration fee 3,500 only
Send to M-Pesa Till 884512 and WhatsApp your passport copy to 0711 000 222
Limited slots, first come first served!!!""",
    ),
    Message(
        name="fake_canada_sms", expected="FAKE",
        note="SMS claiming IRCC approval and demanding the LMIA fee by paybill",
        text="""Congratulations! Your application for Canada farm work has been approved by IRCC. Pay the LMIA processing
fee of KES 45,000 within 48 hours to secure your slot. Paybill 522522 Acc 7788990. Call +1 437 555 0190.""",
    ),
    Message(
        name="fake_unaccredited_agency_post", expected="FAKE",
        note="Facebook post from a Nairobi agency that isn't NEA-accredited, charging medical and documentation fees",
        text="""HORIZON GULF MANPOWER CONSULTANTS - Nairobi
Hiring 50 waiters for Dubai hotels. Salary AED 2,800.
Medical fee KES 8,000 and documentation fee KES 12,000 paid at our office on registration.
Call 0711 000 563""",
    ),
]
