"""Deterministic red-flag rules for employment-fraud messages.

These rules are the "evidence collector" that runs before the LLM. They are deliberately
simple, quotable and explainable: every hit carries the exact substring that triggered it,
so the UI can show a judge *why* the machine fired. The LLM then reasons about context;
the rules keep it honest.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Rule:
    key: str
    label: str
    weight: int
    severity: str
    why: str
    patterns: tuple[str, ...]

    def compile(self) -> tuple[re.Pattern[str], ...]:
        return tuple(re.compile(p, re.IGNORECASE | re.UNICODE) for p in self.patterns)


@dataclass
class Hit:
    key: str
    label: str
    weight: int
    severity: str
    why: str
    evidence: list[str] = field(default_factory=list)
    raw_evidence: list[str] = field(default_factory=list)


RULES: tuple[Rule, ...] = (
    Rule(
        key="upfront_payment",
        label="Demands an upfront fee to secure the job",
        weight=45,
        severity="critical",
        why="Legitimate employers never charge a candidate for a visa, a slot, training or "
        "'processing'. Recruiting costs are paid by the company, never by the applicant.",
        patterns=(
            r"\b(?:visa|processing|registration|application|interview|medical|training|"
            r"security|service|agency|booking|stamping|stamp)\s*(?:fee|fees|charges?|cost)\b",
            r"\b(?:pay|deposit|transfer|send)\s+(?:us\s+)?(?:only\s+)?"
            r"(?:rs\.?|pkr|aed|usd|\$|₹|₨|sar)\s*[\d,]+",
            r"\bsecurity\s+deposit\b",
            r"\brefundable\s+(?:fee|deposit|amount)\b",
            r"\badvance\s+payment\b",
            r"\bfee\b[^.\n]{0,30}\b(?:refund|visa|joining|slot)\b",
        ),
    ),
    Rule(
        key="personal_payment_channel",
        label="Payment goes to a private wallet, not a company account",
        weight=45,
        severity="critical",
        why="Fraudsters cannot open a corporate bank account, so they route money through "
        "JazzCash, EasyPaisa, USDT or a personal account title. A real employer invoices you "
        "from a registered company account — or not at all.",
        patterns=(
            r"\b(?:jazz\s*cash|jazzcash|easy\s*paisa|easypaisa|naya\s*pay|sada\s*pay|upaisa)\b",
            r"\b(?:western\s+union|money\s*gram|moneygram|usdt|bitcoin|binance|trc\s*20)\b",
            r"\baccount\s+(?:number|title|name|holder)\b",
            r"\b(?:send|share)\s+(?:me\s+)?(?:the\s+)?(?:payment\s+)?screenshot\b",
        ),
    ),
    Rule(
        key="guaranteed_visa",
        label="Guarantees a visa or a job without a real hiring process",
        weight=40,
        severity="critical",
        why="No employer, agent or government can guarantee a work visa before a signed "
        "contract and an approved permit. '100% visa' and 'no interview, direct joining' are "
        "the signature lines of visa fraud.",
        patterns=(
            r"\b(?:100\s*%|guaranteed|guarantee|sure\s*shot)\s*(?:visa|approval|job|placement)\b",
            r"\bvisa\s*(?:is\s*)?(?:guaranteed|confirmed|approved|100)\b",
            r"\b(?:no|without)\s+(?:interview|test|selection\s+process)\b",
            r"\bdirect\s+joining\b",
            r"\bvisa\s+on\s+arrival\b[^.\n]{0,40}\bjob\b",
        ),
    ),
    Rule(
        key="identity_harvesting",
        label="Wants identity documents or banking secrets before a contract",
        weight=40,
        severity="critical",
        why="Passport and CNIC scans plus bank details are resold or used to open accounts in "
        "your name. Nothing beyond a CV is needed before a signed offer. OTPs and PINs are "
        "never requested by an employer, ever.",
        # Deliberately requires a *request to send* the document. Bringing your CNIC to a
        # physical interview is normal in Pakistan; WhatsApp-ing a scan to a stranger is not.
        patterns=(
            r"\b(?:send|share|email|e-mail|whats?app|upload|attach|provide|forward)\b[^.]{0,60}"
            r"\b(?:passport|cnid|cnic|identity\s+card|national\s+id|bank\s+statement|"
            r"bank\s+details|account\s+details)\b",
            r"\b(?:passport|cnid|cnic|bank\s+statement)\b[^.]{0,30}\b(?:copy|scan|photo)"
            r"\b[^.]{0,40}\b(?:send|share|email|whats?app|upload)\b",
            r"\b(?:otp|one[- ]time\s+password|pin\s+code|cvv)\b",
            r"\bselfie\s+with\s+(?:your\s+)?(?:id|passport|cnic)\b",
        ),
    ),
    Rule(
        key="daily_pay_task_scam",
        label="Offers daily cash for trivial online tasks",
        weight=35,
        severity="critical",
        why="The 'like videos / review hotels / complete orders, get paid daily' script is a "
        "task scam: the first small payouts are bait, then you must deposit your own money to "
        "'unlock' bigger orders and it never comes back.",
        patterns=(
            r"\b(?:earn|make|get)\s+(?:up\s+to\s+)?(?:rs\.?|pkr|₨|\$)?\s*[\d,]+\s*"
            r"(?:daily|per\s+day|/day|a\s+day)\b",
            r"\b(?:like|review|subscribe|rate)\b[^.\n]{0,40}\b(?:paid|payment|earn|income)\b",
            r"\b(?:complete|process)\s+(?:orders?|tasks?)\b[^.\n]{0,40}\b(?:commission|earn)\b",
            r"\b(?:recharge|deposit|top\s*up)\b[^.\n]{0,40}\b(?:withdraw|unlock|order)\b",
        ),
    ),
    Rule(
        key="domain_mismatch",
        label="Uses a lookalike, throwaway or shortened link",
        weight=28,
        severity="high",
        why="Real recruiters link to their corporate careers page. Shorteners, free hosting "
        "and domains like .xyz/.top hide the real destination; 'company-hr.com' style domains "
        "are commonly registered days before a scam run.",
        patterns=(
            r"https?://(?:bit\.ly|tinyurl\.com|rb\.gy|cutt\.ly|is\.gd|shorturl\.at|t\.co)\b",
            r"\b[\w-]+\.(?:xyz|top|tk|ml|ga|cf|gq|online|site|shop|click|link)\b",
            r"https?://(?:t\.me|wa\.me|chat\.whatsapp\.com)\b",
            r"\b[\w-]+-(?:hr|careers?|jobs?|recruit(?:ment)?)\.(?:com|net|org)\b",
        ),
    ),
    Rule(
        key="unrealistic_pay",
        label="Promises pay far above the market for the stated role",
        weight=24,
        severity="high",
        why="A salary that is several times the going rate for the same job, especially with "
        "no experience required, is bait. Scammers price the dream high because the victim "
        "never receives it.",
        patterns=(
            r"\b(?:rs\.?|pkr|₨)\s*(?:[\d,]{7,}|[6-9]\d{5})\b[^.\n]{0,30}"
            r"(?:month|monthly|salary|per\s+month)",
            r"\b(?:lakh|lac|crore)\b[^.\n]{0,20}\b(?:month|monthly|salary)\b",
            r"\b(?:aed|sar|usd|\$)\s*(?:[5-9]\d{3}|\d{5,})\b[^.\n]{0,25}"
            r"\b(?:month|monthly|salary)\b",
            r"\b(?:salary|income)\b[^.\n]{0,25}\b(?:lakh|lac|crore)\b",
        ),
    ),
    Rule(
        key="unofficial_channel",
        label="Recruits from a free mailbox or WhatsApp instead of a company address",
        weight=20,
        severity="medium",
        why="'HR Manager' writing from a Gmail or Yahoo address is the most common tell in "
        "job fraud. A genuine company writes from its own domain and can be called on a "
        "published landline.",
        patterns=(
            r"[\w.+-]+@(?:gmail|googlemail|yahoo|hotmail|outlook|live|aol|proton(?:mail)?|"
            r"yandex|icloud|mail)\.(?:com|co|net|in|pk)\b",
            r"\b(?:contact|message|text|dm|inbox)\s+(?:me|us)\s+(?:on|at|via)\s+"
            r"(?:whats\s*app|whatsapp|telegram|imo)\b",
            r"\b(?:whats\s*app|whatsapp|telegram)\s*(?:only|number|no\.?)\b",
        ),
    ),
    Rule(
        key="process_inversion",
        label="Skips the normal hiring process entirely",
        weight=22,
        severity="high",
        why="A real hiring pipeline is CV screening, interview, offer, contract, then visa. "
        "Offers issued before any interview, or contracts released only after payment, invert "
        "that order on purpose.",
        patterns=(
            r"\bno\s+(?:experience|qualification|cv|resume|degree)\s+(?:required|needed|necessary)\b",
            r"\bselected\s+(?:directly|without\s+(?:an?\s+)?interview)\b",
            r"\bcontract\b[^.\n]{0,25}\b(?:after|upon|before)\s+(?:payment|arrival|fee)\b",
            r"\b(?:apply|send\s+your\s+cv)\b[^.\n]{0,25}\b(?:whatsapp|telegram)\b",
        ),
    ),
    Rule(
        key="urgency",
        label="Manufactures urgency to stop you from checking",
        weight=16,
        severity="medium",
        why="Deadlines are pressure tactics. If a slot expires in two hours, you have no time "
        "to verify the employer — which is exactly the point.",
        patterns=(
            r"\b(?:only|last)\s+\d*\s*(?:seats?|slots?|positions?|vacanc(?:y|ies))\b",
            r"\b(?:today|tonight)\s+only\b",
            r"\bwithin\s+\d+\s*(?:hours?|hrs?|minutes?)\b",
            r"\blimited\s+(?:time|slots?|seats?|vacanc(?:y|ies))\b",
            r"\b(?:immediate(?:ly)?|urgent(?:ly)?)\s*(?:joining|required|hire|start)\b",
        ),
    ),
    Rule(
        key="vague_employer",
        label="Never names the actual employer",
        weight=18,
        severity="medium",
        why="You cannot verify a company that is never named. 'A reputed international "
        "company' and 'our client in Dubai' exist so that no one can be checked.",
        patterns=(
            r"\b(?:a|our)\s+(?:reputed|renowned|leading|well[- ]known|international|multinational)\s+"
            r"(?:company|group|client|firm)\b",
            r"\bour\s+(?:client|partner)\s+(?:company|office|in)\b",
            r"\b(?:company|employer)\s+name\s+(?:will\s+be\s+)?(?:shared|disclosed|revealed)\b",
            r"\[(?:company|employer|name|your\s+name)[^\]]{0,20}\]",
        ),
    ),
    Rule(
        key="mass_mailing",
        label="Reads like a bulk copy-paste blast",
        weight=12,
        severity="low",
        why="No name, no role specificity, generic greetings: the message was sent to "
        "thousands of numbers at once. Real recruiters address you and the role.",
        patterns=(
            r"\bdear\s+(?:candidate|applicant|sir\s*/\s*madam|all|job\s*seeker)\b",
            r"\bto\s+whom\s+it\s+may\s+concern\b",
            r"\bselected\s+candidates?\s+(?:are|will|must)\b",
            r"\bthis\s+is\s+to\s+inform\s+(?:you|all)\b",
        ),
    ),
)

_COMPILED = {rule.key: rule.compile() for rule in RULES}


def _snippet(text: str, start: int, end: int, pad: int = 36) -> str:
    """Return a short, quotable window around a match."""
    left = max(0, start - pad)
    right = min(len(text), end + pad)
    chunk = " ".join(text[left:right].split())
    prefix = "…" if left > 0 else ""
    suffix = "…" if right < len(text) else ""
    return f"{prefix}{chunk}{suffix}"


def prescan(text: str) -> list[Hit]:
    """Run every rule against the message and return the hits, strongest first."""
    hits: list[Hit] = []
    for rule in RULES:
        evidence: list[str] = []
        raw: list[str] = []
        for pattern in _COMPILED[rule.key]:
            for match in pattern.finditer(text):
                piece = _snippet(text, match.start(), match.end())
                if piece not in evidence:
                    evidence.append(piece)
                    raw.append(match.group(0))
                if len(evidence) >= 3:
                    break
            if len(evidence) >= 3:
                break
        if evidence:
            hits.append(
                Hit(
                    key=rule.key,
                    label=rule.label,
                    weight=rule.weight,
                    severity=rule.severity,
                    why=rule.why,
                    evidence=evidence,
                    raw_evidence=raw,
                )
            )
    hits.sort(key=lambda h: h.weight, reverse=True)
    return hits


def rule_score(hits: list[Hit]) -> int:
    """Aggregate rule hits into a 0-100 score with sensible floors."""
    if not hits:
        return 0
    total = sum(h.weight for h in hits)
    if any(h.severity == "critical" for h in hits):
        total = max(total, 82)
    elif len(hits) >= 3:
        total = max(total, 45)
    return min(100, total)
