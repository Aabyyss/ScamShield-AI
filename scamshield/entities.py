"""Offline entity analysis: who is the message asking you to contact, and does it add up?

Scamio, Truecaller and ScamAdviser all add a reputation layer for links, addresses and phone
numbers. A reputation lookup needs the network, so this module does the honest offline version:
extract every link, mailbox, number and ID in the message, then judge each one on structural
signals that do not require a database — free mailboxes, look-alike brand domains, throwaway
TLDs, shorteners, punycode, partially hidden phone numbers.

Nothing here makes a network request. "No offline red flag" is never presented as "safe".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

FREE_MAIL = {
    "gmail.com",
    "googlemail.com",
    "yahoo.com",
    "yahoo.co.uk",
    "yahoo.com.pk",
    "hotmail.com",
    "outlook.com",
    "live.com",
    "aol.com",
    "protonmail.com",
    "proton.me",
    "yandex.com",
    "icloud.com",
    "mail.com",
    "gmx.com",
    "zoho.com",
}

SHORTENERS = {
    "bit.ly",
    "tinyurl.com",
    "rb.gy",
    "cutt.ly",
    "is.gd",
    "shorturl.at",
    "t.co",
    "goo.gl",
    "ow.ly",
    "buff.ly",
    "tiny.cc",
    "rebrand.ly",
}

RISKY_TLDS = {
    "xyz",
    "top",
    "tk",
    "ml",
    "ga",
    "cf",
    "gq",
    "click",
    "link",
    "shop",
    "site",
    "online",
    "buzz",
    "icu",
    "rest",
    "work",
    "monster",
    "loan",
    "zip",
    "mov",
}

# A short, honest list: brand token -> the only domain that brand actually uses.
OFFICIAL_DOMAINS = {
    "systemsltd": ("systemsltd.com", "Systems Limited"),
    "aramco": ("aramco.com", "Saudi Aramco"),
    "nestle": ("nestle.com", "Nestlé"),
    "unilever": ("unilever.com", "Unilever"),
    "pepsico": ("pepsico.com", "PepsiCo"),
    "hbl": ("hbl.com", "HBL"),
    "ubl": ("ubl.com", "UBL"),
    "faysalbank": ("faysalbank.com", "Faysal Bank"),
    "jazz": ("jazz.com.pk", "Jazz"),
    "telenor": ("telenor.com.pk", "Telenor"),
    "ptcl": ("ptcl.com.pk", "PTCL"),
    "nadra": ("nadra.gov.pk", "NADRA"),
    "bykea": ("bykea.com", "Bykea"),
    "careem": ("careem.com", "Careem"),
}

ROLE_INBOXES = ("hr", "jobs", "job", "career", "careers", "recruit", "recruitment", "hiring", "apply")

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
URL_RE = re.compile(r"https?://[^\s<>\"')\]]+")
DOMAIN_RE = re.compile(
    r"(?<![\w@.\-])((?:[a-z0-9](?:[a-z0-9\-]*[a-z0-9])?\.)+"
    r"(?:com|net|org|pk|ae|sa|io|co|info|biz|app|dev|me|ly|in|uk|us|de|"
    r"xyz|top|tk|ml|ga|cf|gq|click|link|shop|site|online|buzz|icu|rest|work|monster))"
    r"(?:/[^\s<>\"']*)?",
    re.IGNORECASE,
)
PHONE_RE = re.compile(
    r"(?<![\w.])(?:\+92[\s\-]?|0)\d{2,3}[\s\-]?\d{3}[\s\-]?\d{4}(?![\w])"
)
MASKED_PHONE_RE = re.compile(
    r"(?<![\w.])(?:\+92[\s\-]?|0)\d{2,3}[\s\-]?[Xx*]{6,8}(?![\w])"
)
CNIC_RE = re.compile(r"(?<!\d)\d{5}-?\d{7}-?\d(?!\d)")

_RISK_ORDER = {"high": 0, "medium": 1, "low": 2, "info": 3}

_KIND_LABEL = {
    "email": "Email address",
    "url": "Link",
    "domain": "Domain",
    "phone": "Phone number",
    "personal": "Personal data",
}


@dataclass
class Entity:
    kind: str
    value: str
    risk: str
    reasons: list[str] = field(default_factory=list)
    domain: str = ""

    @property
    def label(self) -> str:
        return _KIND_LABEL.get(self.kind, self.kind.title())


def _domain_of_url(url: str) -> str:
    try:
        host = urlsplit(url).hostname or ""
    except ValueError:
        return ""
    return host.lower().removeprefix("www.")


def _brand_claim(domain: str) -> tuple[str, str] | None:
    """Return (official domain, brand) when a domain imitates a known brand."""
    compact = domain.replace("-", "").replace(".", "")
    for token, (official, brand) in OFFICIAL_DOMAINS.items():
        if token in compact and domain != official and not domain.endswith("." + official):
            return official, brand
    return None


def assess_domain(domain: str, trusted: set[str] | None = None) -> tuple[str, list[str]]:
    trusted = trusted or set()
    reasons: list[str] = []
    domain = domain.lower().removeprefix("www.")

    if domain in trusted:
        return "low", ["You marked this domain as trusted."]
    if domain.startswith("xn--") or ".xn--" in domain:
        return "high", ["Punycode domain — it can display as a different name than it really is."]
    if domain in SHORTENERS:
        return "high", ["Link shortener: the real destination is hidden until you click."]

    tld = domain.rsplit(".", 1)[-1]
    claim = _brand_claim(domain)
    if claim:
        official, brand = claim
        return "high", [
            f"Uses the name of {brand} but is not {official}.",
            "Look-alike domains are registered days before a scam run.",
        ]
    if tld in RISKY_TLDS:
        return "medium", [
            f".{tld} is cheap and disposable; fraud runs use it heavily.",
            "A real employer links to its own corporate domain.",
        ]
    if any(part in domain for part in ("-hr.", "-jobs.", "-career", "-recruit", "visa", "manpower")):
        reasons.append("Wording like 'visa', 'manpower' or '-hr' inside the domain is a common front.")
    if domain.count("-") >= 2:
        reasons.append("Multiple hyphens — typical of throwaway recruiter domains.")
    if reasons:
        return "medium", reasons
    return "low", ["No structural red flag. Reputation cannot be checked offline — open the company site yourself."]


def _assess_email(email: str, trusted: set[str] | None = None) -> Entity:
    local, _, domain = email.lower().partition("@")
    risk, reasons = assess_domain(domain, trusted)
    if domain in FREE_MAIL and domain not in (trusted or set()):
        risk = "high"
        reasons = [
            "Free mailbox: anyone can create it in a minute, and no company can be verified behind it.",
            "Real HR writes from the company's own domain.",
        ]
        if any(token in local for token in ROLE_INBOXES):
            reasons.append(f"The name “{local}” pretends to be an official HR desk.")
    return Entity(kind="email", value=email, risk=risk, reasons=reasons, domain=domain)


def _snippet(text: str, start: int, end: int, pad: int = 22) -> str:
    return " ".join(text[max(0, start - pad) : min(len(text), end + pad)].split())


def mask_number(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    if len(digits) < 7:
        return value
    return f"{value[: len(value) - 6]}{'•' * 4}{value[-2:]}"


def assess(text: str, trusted: set[str] | None = None) -> list[Entity]:
    """Extract every contact point and ID in the message, strongest risk first."""
    trusted = trusted or set()
    entities: list[Entity] = []
    seen: set[tuple[str, str]] = set()
    consumed: list[tuple[int, int]] = []

    def add(entity: Entity) -> None:
        key = (entity.kind, entity.value.lower())
        if key not in seen:
            seen.add(key)
            entities.append(entity)

    for match in EMAIL_RE.finditer(text):
        consumed.append(match.span())
        add(_assess_email(match.group(0), trusted))

    for match in URL_RE.finditer(text):
        consumed.append(match.span())
        raw = match.group(0).rstrip(".,;:!?")
        domain = _domain_of_url(raw)
        if not domain:
            continue
        risk, reasons = assess_domain(domain, trusted)
        if domain in FREE_MAIL:
            risk, reasons = "medium", ["Links to a free file-hosting or mailbox domain, not a company site."]
        add(Entity(kind="url", value=raw, risk=risk, reasons=reasons, domain=domain))

    for match in DOMAIN_RE.finditer(text):
        if any(start <= match.start() < end for start, end in consumed):
            continue
        raw = match.group(1).rstrip(".,;:!?")
        domain = raw.lower().removeprefix("www.").split("/")[0]
        risk, reasons = assess_domain(domain, trusted)
        add(Entity(kind="domain", value=domain, risk=risk, reasons=reasons, domain=domain))

    for match in MASKED_PHONE_RE.finditer(text):
        consumed.append(match.span())
        add(
            Entity(
                kind="phone",
                value=match.group(0),
                risk="medium",
                reasons=[
                    "The number is partly hidden — you cannot check who owns it.",
                    "Only the scammer benefits from an unverifiable contact.",
                ],
            )
        )

    for match in PHONE_RE.finditer(text):
        if any(start <= match.start() < end for start, end in consumed):
            continue
        add(
            Entity(
                kind="phone",
                value=match.group(0),
                risk="info",
                reasons=[
                    "Phone numbers cannot be looked up offline. Call the number published on the "
                    "company's own website instead."
                ],
            )
        )

    for match in CNIC_RE.finditer(text):
        add(
            Entity(
                kind="personal",
                value=mask_number(match.group(0)),
                risk="info",
                reasons=[
                    "This message contains an ID number. Never send ID, passport or bank details "
                    "to an employer you have not verified independently."
                ],
            )
        )

    entities.sort(key=lambda e: (_RISK_ORDER.get(e.risk, 9), e.kind, e.value))
    return entities


def domains_in(text: str) -> list[str]:
    """Every domain mentioned, from emails, links or bare text."""
    domains: list[str] = []
    for match in EMAIL_RE.finditer(text):
        domain = match.group(0).partition("@")[2].lower()
        if domain not in domains:
            domains.append(domain)
    for match in URL_RE.finditer(text):
        domain = _domain_of_url(match.group(0).rstrip(".,;:!?"))
        if domain and domain not in domains:
            domains.append(domain)
    for match in DOMAIN_RE.finditer(text):
        domain = match.group(1).lower().removeprefix("www.").split("/")[0]
        if domain not in domains:
            domains.append(domain)
    return domains


def assess_with_trust(text: str) -> list[Entity]:
    """Convenience wrapper that reads the locally trusted domains."""
    from . import learning

    return assess(text, {row["domain"] for row in learning.trusted_domains()})
