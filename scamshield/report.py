"""Shareable verdict report — the thing you send to a friend who is about to pay a "visa fee".

Bitdefender, Norton and the FTC all end with "report it / share it". A text report keeps the
whole thing offline: the user downloads it and forwards it themselves, and nothing is uploaded
on their behalf.
"""

from __future__ import annotations

from datetime import datetime
from urllib.parse import quote

from .engine import Analysis

_DISCLAIMER = (
    "ScamShield gives guidance, not a legal accusation. It never claims a company is criminal — "
    "only that a message behaves like known job fraud. Verify the employer independently and "
    "never send money, documents or OTPs to an unverified contact."
)


def _when() -> str:
    return datetime.now().strftime("%d %b %Y, %H:%M")


def build_report(result: Analysis, message: str = "") -> str:
    lines: list[str] = []
    lines.append("# 🛡️ ScamShield AI — safety report")
    lines.append("")
    lines.append(f"**Verdict:** {result.risk_level} RISK · {result.risk_score}/100  ")
    lines.append(f"**Assessment:** {result.headline}  ")
    lines.append(
        f"**Checked:** {_when()} · on this device · "
        f"{result.model or 'rules only'} · confidence {result.confidence}"
    )
    lines.append("")

    if result.summary:
        lines.append(result.summary)
        lines.append("")

    if result.red_flags:
        lines.append("## 🚩 Red flags")
        for index, flag in enumerate(result.red_flags, 1):
            source = "rule + AI" if flag.corroborated else ("rule" if flag.source == "rules" else "AI, unverified")
            lines.append(f"**{index}. {flag.title}** ({flag.severity} · {source})")
            if flag.evidence:
                lines.append(f"> “{flag.evidence}”")
            if flag.why_it_matters:
                lines.append("")
                lines.append(flag.why_it_matters)
            lines.append("")

    if result.positive_signals:
        lines.append("## ✅ What looks legitimate")
        lines.extend(f"- {item}" for item in result.positive_signals)
        lines.append("")

    if result.recommended_actions:
        lines.append("## What to do now")
        lines.extend(f"{i}. {action}" for i, action in enumerate(result.recommended_actions, 1))
        lines.append("")

    if result.questions_to_ask:
        lines.append("## Questions to ask before replying")
        lines.extend(f"- {question}" for question in result.questions_to_ask)
        lines.append("")

    if result.entities:
        lines.append("## 🔗 Links, addresses and numbers found")
        for entity in result.entities:
            reasons = " ".join(entity.reasons[:2])
            lines.append(f"- `{entity.value}` — {entity.label} · {entity.risk} risk. {reasons}")
        lines.append("")

    if result.similar:
        lines.append("## Messages like this you have checked before")
        for case in result.similar:
            lines.append(
                f"- {case.similarity}% similar, {case.created_at[:10]} — that one was {case.level}"
            )
        lines.append("")

    lines.append("## Report it")
    lines.append(
        "- Pakistan: FIA Cybercrime helpline **1991** · PTA complaint portal pta.gov.pk\n"
        "- WhatsApp: report the sender inside the chat; Telegram: @notoscam\n"
        "- Everywhere: the platform where the message arrived, and your bank if you paid"
    )
    lines.append("")
    lines.append("---")
    lines.append(_DISCLAIMER)
    lines.append("")
    if message.strip():
        lines.append("<details><summary>Message as pasted (kept on your device)</summary>")
        lines.append("")
        lines.append("```")
        lines.append(message.strip()[:4000])
        lines.append("```")
        lines.append("</details>")

    return "\n".join(lines)


def report_filename(result: Analysis) -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    return f"scamshield-{result.risk_level.lower()}-{stamp}.md"


def report_data_uri(result: Analysis, report: str) -> str:
    """Small helper for a 'copy as link' button if a UI wants one later."""
    return "data:text/markdown;charset=utf-8," + quote(report)
