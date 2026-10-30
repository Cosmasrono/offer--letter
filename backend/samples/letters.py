"""Test set of offer letters with the answer we expect from the checker.

Every company, person, email, phone number and domain here is FICTIONAL. Phone numbers use ranges
reserved for fiction where a country has one (UK 0161 496 0xxx, North America 555-01xx, Australia 0491 570 xxx).
The letters are modelled on the patterns of real genuine offers and real reported scams.

expected:  "REAL" -> should score LOW      "FAKE" -> should score HIGH
"""

from dataclasses import dataclass


@dataclass
class Letter:
    file: str
    expected: str  # REAL | FAKE
    country: str
    note: str
    text: str
    producer: str = "Microsoft Word"
    edited_with: str | None = None  # simulate re-saving the PDF in an online editor


LETTERS: list[Letter] = [
    # ------------------------------------------------------------------ REAL-style
    Letter(
        file="real_uk_logistics.pdf", expected="REAL", country="GB",
        note="UK Skilled Worker offer, employer pays sponsorship costs",
        text="""Northwind Logistics Ltd
Company registration number: 09876543
14 Harbour Road, Manchester M1 2AB, United Kingdom
Tel: +44 161 496 0199 | careers@northwindlogistics.co.uk

12 September 2026

Dear Grace Wanjiku,

Offer of Employment - Warehouse Operations Supervisor

Following your interviews on 28 August and 4 September 2026, we are pleased to offer you the position of
Warehouse Operations Supervisor, reporting to the Head of Operations.

Start date: 1 December 2026, subject to visa approval
Basic salary: GBP 34,500 per year, paid monthly
Working hours: 37.5 hours per week, Monday to Friday
Probation: 6 months
Annual leave: 25 days plus UK bank holidays
Notice period: 1 month after probation

This offer is conditional on a successful Skilled Worker visa application. As a licensed sponsor, Northwind
Logistics Ltd will assign you a Certificate of Sponsorship and will pay the Certificate of Sponsorship fee and
the Immigration Skills Charge. You will not be asked to pay us any fees at any stage.

Please confirm your acceptance by replying to careers@northwindlogistics.co.uk by 30 September 2026.

Yours sincerely,
Sarah Thompson
HR Manager, Northwind Logistics Ltd
""",
    ),
    Letter(
        file="real_uae_facilities.pdf", expected="REAL", country="AE",
        note="UAE offer that says the company pays visa, medical and ticket costs (tests fee false positives)",
        text="""Al Noor Facilities Management LLC
Trade Licence No. 784512, Dubai Department of Economy and Tourism
Office 1204, Business Bay Tower, Dubai, United Arab Emirates
Tel: +971 4 330 0145 | recruitment@alnoorfm.ae

3 October 2026

Dear Mr. Brian Otieno Ouma,

Offer of Employment - HVAC Technician

Further to your technical interview held online on 22 September 2026 and your trade test on 29 September 2026,
we are pleased to offer you employment as HVAC Technician in our Dubai operations team.

Basic salary: AED 2,800 per month
Allowances: AED 900 housing allowance and AED 300 transport allowance per month
Working hours: 48 hours per week, 6 days per week, in line with UAE Labour Law
Contract duration: 2 years, renewable
Probation: 6 months
Annual leave: 30 calendar days per completed year
Start date: Upon issue of your entry permit, expected December 2026

Your employment visa, work permit (MOHRE), Emirates ID, medical fitness test and one-way air ticket
to Dubai will be arranged and paid for by the Company. All recruitment costs are borne by the employer
and no fee will be charged to you at any stage. If anyone asks you for money in our name, please report
it to recruitment@alnoorfm.ae.

The MOHRE offer letter will be sent to you separately for electronic signature.

Yours sincerely,
Fatima Al Mansoori
Human Resources Manager
Al Noor Facilities Management LLC
""",
    ),
    Letter(
        file="real_canada_caregiver.pdf", expected="REAL", country="CA",
        note="Canada LMIA-based offer, employer pays LMIA fee",
        text="""Maple Ridge Care Homes Inc.
2210 Riverside Drive, Winnipeg, Manitoba R3T 2N2, Canada
Phone: +1 204 555 0142 | hr@mapleridgecare.ca

18 August 2026

Dear Ms. Mercy Achieng Odhiambo,

Re: Offer of Employment - Personal Support Worker (NOC 44101)

Thank you for attending interviews with our Director of Care on 30 July and 6 August 2026. We are pleased
to offer you a full-time position as a Personal Support Worker at our Winnipeg residence.

Wage: CAD 21.50 per hour
Working hours: 40 hours per week, rotating day and evening shifts
Start date: 15 January 2027, or the date your work permit is issued
Probation: 3 months
Vacation: 2 weeks per year, increasing after 5 years

This position is supported by a positive Labour Market Impact Assessment (LMIA). The LMIA processing fee
has been paid by Maple Ridge Care Homes Inc. and, as required by Canadian law, it will not be recovered
from you. You will apply for your work permit directly with IRCC and pay only the government fees set by IRCC.
We do not use recruitment agents and we never ask candidates to send money to us.

Please sign and return this letter to hr@mapleridgecare.ca within 14 days.

Sincerely,
Daniel Fraser
Human Resources Director, Maple Ridge Care Homes Inc.
""",
    ),
    Letter(
        file="real_germany_engineer.pdf", expected="REAL", country="DE",
        note="German Blue Card offer",
        text="""Rheinwerk Antriebstechnik GmbH
Handelsregister: HRB 45218, Amtsgericht Köln
Industriestraße 18, 50735 Köln, Germany
Tel: +49 221 9876 4410 | jobs@rheinwerk-antriebe.de

25 September 2026

Dear Mr. Kevin Mwangi Kariuki,

Employment Offer - Embedded Software Engineer

Following our video interviews on 9 and 16 September 2026 and your technical assessment, we are pleased to
offer you the position of Embedded Software Engineer in our Cologne development team, reporting to the
Head of Embedded Systems.

Gross salary: EUR 62,000 per year, paid in 12 monthly instalments
Working hours: 40 hours per week, flexible working time
Start date: 1 March 2027, subject to your residence permit
Probation: 6 months
Annual leave: 30 working days
Notice period: 3 months after probation

This offer allows you to apply for an EU Blue Card at the German embassy in Nairobi. We will provide the
signed employment contract and the job description you need for your visa application. The company covers
your relocation flight and the first month of temporary accommodation.

Please confirm your acceptance by email to jobs@rheinwerk-antriebe.de by 10 October 2026.

Kind regards,
Anna Becker
HR Business Partner, Rheinwerk Antriebstechnik GmbH
""",
    ),
    Letter(
        file="real_saudi_nurse.pdf", expected="REAL", country="SA",
        note="Saudi hospital nursing offer, employer covers iqama and visa costs",
        text="""Al Waha Medical Group Company
Commercial Registration (CR) No. 1010654321
King Fahd Road, Riyadh 12271, Kingdom of Saudi Arabia
Tel: +966 11 480 2200 | nursing.recruitment@alwahamedical.sa

20 September 2026

Dear Ms. Faith Njeri Kamau,

Offer of Employment - Staff Nurse (Medical-Surgical Unit)

We refer to your interview with our Nursing Director on 10 September 2026. We are pleased to offer you the
position of Staff Nurse at Al Waha Medical Group, Riyadh.

Basic salary: SAR 5,200 per month
Housing: furnished shared accommodation provided, or SAR 1,000 housing allowance
Transport: hospital transport to and from work
Working hours: 48 hours per week
Contract period: 2 years, renewable
Annual leave: 30 days paid, with return air ticket
Start date: within 60 days of visa issue

Your work visa, iqama, medical insurance and air ticket are the employer's responsibility under Saudi
Labour Law, and Al Waha Medical Group will not charge you any recruitment or processing fees. The contract
will be registered on the Qiwa platform and you will receive a copy before travel.

Please confirm your acceptance by replying to nursing.recruitment@alwahamedical.sa.

Yours faithfully,
Omar Al Harbi
Recruitment Manager, Al Waha Medical Group Company
""",
    ),
    Letter(
        file="real_australia_chef.pdf", expected="REAL", country="AU",
        note="Australian employer-sponsored chef offer",
        text="""Harbourside Kitchen Pty Ltd
ABN 51 824 753 556
45 Wharf Street, Brisbane QLD 4000, Australia
Phone: +61 491 570 156 | careers@harbourside-kitchen.com.au

2 October 2026

Dear Mr. Samuel Kiprop Rotich,

Letter of Offer - Chef de Partie

Following your interview with our Executive Chef on 24 September 2026 and your trial cooking session via
video, we are pleased to offer you the position of Chef de Partie, reporting to the Head Chef.

Annual salary: AUD 76,500 plus superannuation
Working hours: 38 hours per week plus reasonable additional hours
Start date: upon grant of your Skills in Demand (subclass 482) visa
Probation: 6 months
Annual leave: 4 weeks per year

Harbourside Kitchen Pty Ltd will lodge the nomination and pay the nomination fee and the Skilling Australians
Fund levy, as required by the Department of Home Affairs. Under Australian law it is illegal for an employer to
ask for payment for a sponsored position, and we will never ask you for one.

Please sign and return this letter by 16 October 2026.

Yours sincerely,
Jessica Nguyen
Operations Manager, Harbourside Kitchen Pty Ltd
""",
    ),
    Letter(
        file="real_qatar_via_agency.pdf", expected="REAL", country="QA",
        note="Qatar offer recruited through an NEA-accredited Kenyan agency (in the sample NEA list)",
        text="""Corniche Facilities Services W.L.L.
Commercial Registration No. 145872
Al Sadd Street, Doha, State of Qatar
Tel: +974 4498 2210 | recruitment@cornichefacilities.qa

2 October 2026

Dear Mr. Brian Kiprotich Rotich,

Offer of Employment - HVAC Technician

Following your trade test and interview in Nairobi on 18 September 2026, we are pleased to offer you the
position of HVAC Technician. You were recruited through our licensed Kenyan partner, Savannah Bridge
Recruitment Agency Ltd (NEA licence no. NEA/PEA/2025/0412), Moi Avenue, Nairobi, Tel +254 20 765 4321.

Basic salary: QAR 3,200 per month, plus QAR 600 food allowance
Working hours: 48 hours per week, overtime paid as per Qatar Labour Law
Contract duration: 2 years, renewable
Start date: 15 December 2026
Annual leave: 30 days paid, with a return air ticket every 2 years
Accommodation and transport to site are provided by the company.

All recruitment, visa, medical and air ticket costs are paid by the employer. You will not be asked to pay
any fee to us or to Savannah Bridge, and you should report anyone who asks you for money.

Your Qatar work visa and QID will be processed by the company after you sign this offer. Please sign and
return it through Savannah Bridge by 20 October 2026.

Yours sincerely,
Fatima Al-Kuwari
HR Manager, Corniche Facilities Services W.L.L.
""",
    ),
    # ------------------------------------------------------------------ FAKE-style
    Letter(
        file="fake_dubai_mpesa.pdf", expected="FAKE", country="AE",
        note="Classic scam: visa fee by M-Pesa, Gmail, WhatsApp, urgency",
        text="""GULF STAR OIL & GAS RECRUITMENT
Dubai, United Arab Emirates

Dear Applicant,

CONGRATULATIONS!!! You have been selected from our database for the position of Warehouse Supervisor
at Gulf Star Petroleum LLC in Dubai, UAE. No interview is required.

Salary: AED 18,000 per month. Free accommodation, free food, free flight ticket and free medical cover!

To complete your work permit you must pay a visa processing fee of USD 450 and a refundable medical
deposit of USD 150 within 48 hours. Send the money via M-Pesa Paybill 247247 or Western Union to our
agent, Mr. James Otieno. Failure to pay within 48 hours, your offer will be cancelled.

For any questions contact our HR on WhatsApp +254 700 000 451 or email gulfstarhr.recruit@gmail.com

URGENT!!! LIMITED SLOTS AVAILABLE!!!

HR Department
""",
        producer="Canva",
    ),
    Letter(
        file="fake_canada_farm.pdf", expected="FAKE", country="CA",
        note="Fake Canada job, candidate told to pay the LMIA fee to an 'agent'",
        text="""CANADA GREEN FIELDS AGRICULTURE
Alberta, Canada

Dear Candidate,

We are happy to inform you that your CV was selected for the post of Farm Worker / Fruit Picker in Alberta,
Canada. Our company is offering 200 positions for international workers. Salary is CAD 4,800 per month
with free accommodation, free food and free transport.

Your LMIA has been approved. To proceed with your work permit, you are required to pay the LMIA processing
fee of CAD 1,000 and an embassy clearance fee of CAD 350 to our immigration agent. Payment should be made
by Western Union or bank deposit to the personal account of our agent, Mr. Peter Collins.

Kindly send a copy of your passport, your bank details and the payment receipt to
canadagreenfields.jobs@outlook.com within 72 hours to secure your slot.

You can also reach our Canadian Immigration Officer on WhatsApp: +1 587 555 0177.

Regards,
Recruitment Office
""",
    ),
    Letter(
        file="fake_uk_care.pdf", expected="FAKE", country="GB",
        note="Fake UK care job asking the worker to pay for the Certificate of Sponsorship",
        text="""Brightwell Care Services Ltd
London, United Kingdom

Dear Sir/Madam,

RE: OFFER OF EMPLOYMENT AS HEALTH CARE ASSISTANT

Congratulations, you have been successfully selected for the position of Health Care Assistant with
Brightwell Care Services Ltd. You have been selected through our database and an interview is not necessary.

Salary: GBP 4,500 per month. Free accommodation and free flight ticket.

Your Certificate of Sponsorship (COS) is ready. You are required to pay the COS registration fee of GBP 850 and
an insurance fee of GBP 200 before the COS is released to you. Payment details will be sent to you on
Telegram. Failure to comply within 5 days, the offer will be withdrawn.

Contact: brightwellcare.uk@yahoo.com | WhatsApp +44 7700 900461

Management
""",
        producer="iLovePDF",
        edited_with="iLovePDF",
    ),
    Letter(
        file="fake_poland_agency.pdf", expected="FAKE", country="PL",
        note="Fake Poland warehouse job via an unlicensed 'agency' asking for a deposit",
        text="""EUROLINK PLACEMENT AGENCY
Nairobi Office - Recruiting for Poland

Dear Job Seeker,

You have been shortlisted for WAREHOUSE PACKER jobs in Warsaw, Poland. Salary: 3,500 USD monthly.
Free housing and free meals provided by the employer. Positions are limited!

Before your work permit can be processed, every candidate must pay a registration fee of KES 25,000 and a
work permit fee of KES 60,000. Pay through M-Pesa Till Number 5678123 within 7 days. The registration fee is
refundable if your visa is rejected.

Bring your original passport and the M-Pesa message to our office for documentation.
Telegram: @eurolinkjobs | Call: +254 700 000 982

ACT NOW - LAST CHANCE!!!
""",
        producer="WPS Office",
    ),
    Letter(
        file="fake_qatar_professional.pdf", expected="FAKE", country="QA",
        note="Polished-looking scam on a company-style domain; only the fees give it away",
        text="""Doha Pearl Hospitality Group W.L.L.
West Bay, Doha, State of Qatar
Tel: +974 4012 3300 | hr@dohapearl-careers.com

8 October 2026

Dear Mr. Collins Wekesa,

Offer of Employment - Front Office Supervisor

Further to your application, we are pleased to offer you the position of Front Office Supervisor at our
5-star property in Doha.

Basic salary: QAR 9,500 per month
Accommodation and transport provided
Contract duration: 2 years
Start date: November 2026

To process your Qatar work visa and QID, you are required to pay the medical and document attestation
fees of USD 680 to our accredited travel partner. Payment details will be shared after you confirm
acceptance. The amount will be refunded with your first salary.

Kindly confirm your acceptance within 3 days.

Regards,
Human Resources Department
Doha Pearl Hospitality Group W.L.L.
""",
        producer="Microsoft Word",
        edited_with="Sejda PDF",
    ),
    Letter(
        file="fake_saudi_whatsapp.pdf", expected="FAKE", country="SA",
        note="Subtle scam with no fee in the letter: moves the victim to WhatsApp to 'complete processing'",
        text="""Riyadh Royal Construction Company
Kingdom of Saudi Arabia

Dear Applicant,

We are pleased to inform you that you have been selected from our database for the position of Heavy Truck
Driver in Riyadh, Saudi Arabia. No interview is required as your profile meets our requirements.

Salary: SAR 9,000 per month. Free accommodation, free food, free medical and free air ticket.

To complete your visa processing, kindly contact our recruitment officer, Mr. Abdullah, immediately on
WhatsApp +966 50 000 7731. Positions are limited and will be given on a first come, first served basis.

Send your passport copy and a passport photo on WhatsApp to begin.

HR Department
Riyadh Royal Construction Company
""",
    ),
    Letter(
        file="fake_uae_unlisted_agency.pdf", expected="FAKE", country="AE",
        note="No fee in the letter; the Nairobi 'agency' isn't NEA-accredited and moves you to WhatsApp",
        text="""HORIZON GULF MANPOWER CONSULTANTS
Kenyatta Avenue, Nairobi
NEA Licence No: NEA/PEA/2023/0999

5 October 2026

Dear Ms. Faith Njeri,

Offer of Employment - Hotel Housekeeping Attendant, Dubai

We are pleased to confirm that you have been offered the position of Housekeeping Attendant with a
5-star hotel in Dubai, United Arab Emirates.

Salary: AED 2,800 per month
Working hours: 8 hours per day, 6 days per week
Contract period: 2 years
Accommodation and transport provided.

To start your entry permit, send a clear copy of your passport and a passport photo on WhatsApp to our
processing officer on +254 711 000 563 within 3 days. Our documentation team will then contact you with
the next steps.

For any questions email horizongulf.jobs@gmail.com

Regards,
Placement Desk
Horizon Gulf Manpower Consultants
""",
    ),
]
