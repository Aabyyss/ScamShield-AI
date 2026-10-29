"""Demo corpus. Realistic messages, written to exercise different rule families.

`expected` is what the demo should show. Keep the legitimate sample in the deck: judges
trust a detector that can also say "this one looks fine".
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Sample:
    key: str
    title: str
    channel: str
    expected: str
    text: str


SAMPLES: tuple[Sample, ...] = (
    Sample(
        key="dubai_hotel",
        title="Dubai hotel job — “visa processing fee”",
        channel="WhatsApp forward",
        expected="HIGH",
        text=(
            "URGENT HIRING !!! DUBAI 5 STAR HOTEL\n"
            "Dear Candidate,\n"
            "We have limited slots for Housekeeping & Waiter staff in a reputed 5 star hotel "
            "in Dubai. Salary AED 4500 + food + accommodation + free visa.\n"
            "No interview required, direct joining after visa stamping.\n"
            "Visa processing fee: Rs 35,000 only (refundable after joining).\n"
            "Send fee on JazzCash 0300-XXXXXXX (Account Title: Imran Khan) and share the "
            "screenshot on this number.\n"
            "Only 3 seats left, confirm within 2 hours or slot will be gone.\n"
            "Contact HR Manager: dubai.hr.services786@gmail.com\n"
            "WhatsApp only. Regards, Imran"
        ),
    ),
    Sample(
        key="saudi_visa",
        title="Saudi Aramco project — passport + bank details",
        channel="Email",
        expected="HIGH",
        text=(
            "Subject: FINAL SELECTION - SAUDI ARABIA PROJECT (ARAMCO)\n\n"
            "Dear Applicant,\n"
            "Congratulations! You have been selected directly without interview for our "
            "Aramco project in Dammam. Salary SAR 6,500 monthly + overtime.\n"
            "Company name will be shared after visa approval.\n"
            "To process your work permit, kindly send:\n"
            "1. Passport copy\n"
            "2. CNIC front and back\n"
            "3. Bank statement of last 3 months\n"
            "4. Medical test fee Rs 8,500 via EasyPaisa to account number 0345-XXXXXXX\n"
            "100% visa guaranteed. Contract will be provided after payment.\n"
            "Last date today. Apply via WhatsApp 0345-XXXXXXX.\n"
            "HR Department, Gulf Manpower Services\n"
            "gulfmanpower.hr@yahoo.com"
        ),
    ),
    Sample(
        key="task_scam",
        title="Work from home — “earn Rs 8,000 daily”",
        channel="Instagram DM",
        expected="HIGH",
        text=(
            "Hello dear, we are hiring part time workers for Amazon product review work.\n"
            "No experience required. Work 2 hours daily from mobile.\n"
            "Earn Rs 8,000 daily by liking videos and completing orders.\n"
            "First 3 tasks are free, after that you deposit Rs 5,000 to unlock premium orders "
            "and withdraw double.\n"
            "Payment via USDT or JazzCash. 100% guaranteed income.\n"
            "Only 5 seats left today. Contact me on Telegram t.me/earnfastpk\n"
            "Registration fee Rs 1,000 only, refundable."
        ),
    ),
    Sample(
        key="legit_offer",
        title="Genuine offer — Systems Limited, Lahore",
        channel="Company email",
        expected="LOW",
        text=(
            "Subject: Offer of Employment - Associate Software Engineer\n\n"
            "Dear Ayesha,\n"
            "Following your interviews with our engineering panel on 12 and 18 March, we are "
            "pleased to offer you the position of Associate Software Engineer at Systems "
            "Limited, Lahore.\n"
            "Annual salary: PKR 1,800,000, plus provident fund, health insurance and 20 days "
            "annual leave. Your start date will be 5 May 2026.\n"
            "Please review the attached offer letter and return the signed copy through the "
            "careers portal (careers.systemsltd.com) by 1 April 2026. No payment or fee of any "
            "kind is required at any stage of our hiring process.\n"
            "For questions, reply to this email or call our HR desk on +92 42 111 797 836.\n"
            "Regards,\n"
            "Sana Tariq\n"
            "Talent Acquisition, Systems Limited"
        ),
    ),
    Sample(
        key="borderline",
        title="Borderline — small local employer, Gmail address",
        channel="WhatsApp",
        expected="MEDIUM",
        text=(
            "Assalam o alaikum, this is Bilal from Al-Noor Traders, Faisalabad.\n"
            "We need an accounts assistant for our shop office. Salary Rs 55,000 per month, "
            "6 days a week, 10am to 7pm.\n"
            "No experience needed, we will train you. Send your CV on this WhatsApp number.\n"
            "Interview will be at our office in Gulberg, you can visit any day this week.\n"
            "Please bring your CNIC copy for the interview record.\n"
            "We do not charge any fee."
        ),
    ),
)

SAMPLE_BY_KEY = {s.key: s for s in SAMPLES}
