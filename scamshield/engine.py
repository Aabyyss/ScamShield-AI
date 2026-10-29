"""ScamShield engine: local Ollama reasoning + deterministic rules, merged into one verdict.

Everything here talks to 127.0.0.1 only. There is no cloud call, no API key, and no
telemetry, which is the point of the whole project.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import requests

from .rules import Hit, prescan, rule_score

SKILL_PATH = Path(__file__).resolve().parent.parent / "skills" / "job-scam-detector" / "SKILL.md"

# Models we prefer if the user has not chosen one. Gemma first, per the project brief.
PREFERRED_MODELS = (
    "gemma3:4b",
    "gemma3",
    "gemma3:1b",
    "gemma2:2b",
    "gemma2",
    "gemma:2b",
    "gemma:7b",
    "gemma",
    "llama3.2:latest",
    "llama3.2",
    "llama3.1",
)


class EngineError(RuntimeError):
    """The local AI engine could not answer. The app degrades to rules-only."""


def ollama_host() -> str:
    host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").strip().rstrip("/")
    if not host.startswith(("http://", "https://")):
        host = "http://" + host
    host = host.replace("http://0.0.0.0", "http://127.0.0.1").replace(
        "http://[::]", "http://127.0.0.1"
    )
    return host


@lru_cache(maxsize=1)
def load_skill() -> str:
    return SKILL_PATH.read_text(encoding="utf-8")


def _strip_frontmatter(skill: str) -> str:
    if skill.startswith("---"):
        parts = skill.split("---", 2)
        if len(parts) == 3:
            return parts[2].strip()
    return skill


def list_models(timeout: float = 3.0) -> list[str]:
    try:
        res = requests.get(f"{ollama_host()}/api/tags", timeout=timeout)
        res.raise_for_status()
        data = res.json()
    except (requests.RequestException, ValueError):
        return []
    return [m["name"] for m in data.get("models", []) if m.get("name")]


def pick_model(available: list[str]) -> str:
    """Choose a sensible default model from what is actually installed."""
    override = os.environ.get("SCAMSHIELD_MODEL")
    if override:
        return override
    lowered = {name.lower(): name for name in available}
    for candidate in PREFERRED_MODELS:
        if candidate.lower() in lowered:
            return lowered[candidate.lower()]
        for low, original in lowered.items():
            if low.split(":")[0] == candidate.lower().split(":")[0]:
                return original
    return available[0] if available else "gemma3:4b"


def engine_online(timeout: float = 1.5) -> bool:
    try:
        requests.get(f"{ollama_host()}/api/version", timeout=timeout)
        return True
    except requests.RequestException:
        return False


# --------------------------------------------------------------------------------------
# Result model
# --------------------------------------------------------------------------------------


@dataclass
class Flag:
    title: str
    evidence: str
    why_it_matters: str
    severity: str = "medium"
    source: str = "ai"  # ai | rules | both


@dataclass
class Analysis:
    risk_level: str
    risk_score: int
    verdict: str
    category: str
    headline: str
    summary: str
    red_flags: list[Flag] = field(default_factory=list)
    positive_signals: list[str] = field(default_factory=list)
    recommended_actions: list[str] = field(default_factory=list)
    questions_to_ask: list[str] = field(default_factory=list)
    confidence: str = "medium"
    engine: str = "ollama"
    model: str = ""
    latency_ms: int = 0
    rule_hits: list[Hit] = field(default_factory=list)
    error: str | None = None


# --------------------------------------------------------------------------------------
# Ollama call
# --------------------------------------------------------------------------------------


def _extract_json(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"```\s*$", "", text).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise EngineError("The model did not return JSON.")
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise EngineError(f"The model returned malformed JSON ({exc.msg}).") from exc


def _build_messages(message: str, hits: list[Hit]) -> list[dict[str, str]]:
    system = _strip_frontmatter(load_skill())
    system += (
        "\n\n## Hard constraints for this deployment\n"
        "- You are running fully offline on the user's laptop. Do not mention the internet, "
        "databases or lookups you cannot perform.\n"
        "- Output must be a single JSON object matching the contract. No prose outside it.\n"
    )

    if hits:
        lines = []
        for hit in hits:
            quoted = "; ".join(f'"{e}"' for e in hit.evidence[:2])
            lines.append(f"- [{hit.severity}] {hit.label} — seen: {quoted}")
        evidence = (
            "A deterministic rules engine already flagged the following passages. Treat them as "
            "candidate evidence: confirm the ones that are genuinely incriminating, drop false "
            "positives (for example a security-deposit clause that only applies after joining), "
            "and keep looking for flags the rules missed.\n" + "\n".join(lines)
        )
    else:
        evidence = (
            "The deterministic rules engine found no known scam patterns. That is not proof of "
            "legitimacy — judge the message on its own merits."
        )

    user = (
        f"{evidence}\n\n"
        "## Message under investigation\n"
        '"""\n'
        f"{message.strip()}\n"
        '"""\n\n'
        "Return the JSON verdict now."
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def call_model(message: str, hits: list[Hit], model: str, timeout: float = 300.0) -> dict:
    payload = {
        "model": model,
        "messages": _build_messages(message, hits),
        "stream": False,
        "format": "json",
        "keep_alive": "30m",
        "options": {
            "temperature": 0.1,
            "top_p": 0.9,
            "repeat_penalty": 1.05,
            "num_ctx": 8192,
            "num_predict": 800,
        },
    }
    try:
        res = requests.post(f"{ollama_host()}/api/chat", json=payload, timeout=timeout)
        res.raise_for_status()
        body = res.json()
    except requests.Timeout as exc:
        raise EngineError("Local model timed out. Try a smaller model or a shorter message.") from exc
    except requests.RequestException as exc:
        raise EngineError(f"Cannot reach Ollama at {ollama_host()}: {exc}") from exc
    except ValueError as exc:
        raise EngineError("Ollama returned an unreadable response.") from exc

    content = (body.get("message") or {}).get("content", "")
    if not content:
        raise EngineError("Ollama returned an empty response.")
    return _extract_json(content)


# --------------------------------------------------------------------------------------
# Merging
# --------------------------------------------------------------------------------------

_SEVERITIES = {"critical", "high", "medium", "low"}
_STOPWORDS = {
    "a", "an", "the", "to", "for", "of", "or", "and", "is", "are", "in", "on", "with", "your",
    "you", "not", "no", "that", "this", "it", "as", "at", "from", "by", "be", "has", "have",
    "job", "message", "real",
}


def _tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z]{3,}", text.lower())
    return {w for w in words if w not in _STOPWORDS}


def _level_for(score: int) -> str:
    if score >= 65:
        return "HIGH"
    if score >= 30:
        return "MEDIUM"
    return "LOW"


def _verdict_for(level: str) -> str:
    return {"HIGH": "scam", "MEDIUM": "suspicious"}.get(level, "likely_legitimate")


def _clamp_score(value: object, fallback: int) -> int:
    try:
        return max(0, min(100, int(round(float(value)))))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return fallback


def _as_list(value: object, limit: int = 8) -> list:
    if isinstance(value, list):
        return value[:limit]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _text(value: object, limit: int = 400) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())[:limit]


def _flag_covered(hit: Hit, flags: list[Flag]) -> bool:
    raw = [r.lower() for r in hit.raw_evidence if len(r) >= 5]
    for flag in flags:
        blob = f"{flag.title} {flag.evidence}".lower()
        if any(r in blob for r in raw):
            return True
    label_tokens = _tokens(hit.label)
    for flag in flags:
        if len(label_tokens & _tokens(f"{flag.title} {flag.why_it_matters}")) >= 2:
            return True
    return False


def _flags_from_hits(hits: list[Hit]) -> list[Flag]:
    return [
        Flag(
            title=h.label,
            evidence=h.evidence[0] if h.evidence else "",
            why_it_matters=h.why,
            severity=h.severity,
            source="rules",
        )
        for h in hits
    ]


def _rules_only(message: str, hits: list[Hit], error: str) -> Analysis:
    score = rule_score(hits)
    level = _level_for(score)
    if not message.strip():
        score, level = 0, "LOW"
    actions = ["Do not send money, documents or OTPs based on this message."]
    keys = {h.key for h in hits}
    if keys & {"upfront_payment", "personal_payment_channel"}:
        actions.insert(0, "Stop all payments and do not share payment screenshots.")
    if "identity_harvesting" in keys:
        actions.insert(0, "Do not share passport, CNIC or bank details.")
    actions.append("Verify the employer on its official website, never a link from the message.")
    actions.append("Call the company's published number and ask HR to confirm the vacancy.")
    actions.append("Report the message to PTA / FIA Cybercrime (helpline 1991) or the platform.")
    headline = (
        "No known scam pattern found — still verify independently."
        if score < 30
        else "Multiple scam patterns detected. Do not engage."
        if score < 65
        else "This matches a known job-scam pattern. Do not pay."
    )
    return Analysis(
        risk_level=level,
        risk_score=score,
        verdict=_verdict_for(level),
        category="unclear",
        headline=headline,
        summary=(
            "Rules-engine only: the local language model was unavailable, so this verdict comes "
            f"from {len(hits)} deterministic signal(s) in the text."
        ),
        red_flags=_flags_from_hits(hits),
        recommended_actions=actions[:5],
        confidence="medium" if hits else "low",
        engine="rules",
        model="",
        rule_hits=hits,
        error=error,
    )


def analyze(message: str, model: str = "", use_ai: bool = True) -> Analysis:
    """Analyse a message. Falls back to the rules engine if the LLM is unavailable."""
    started = time.perf_counter()
    hits = prescan(message)
    base_score = rule_score(hits)

    if not message.strip():
        return Analysis(
            risk_level="LOW",
            risk_score=0,
            verdict="unclear",
            category="unclear",
            headline="Paste the full message to analyse it.",
            summary="There is nothing to analyse yet.",
            recommended_actions=["Paste the WhatsApp message or email you received."],
            confidence="low",
            engine="rules",
            rule_hits=hits,
        )

    if not use_ai:
        result = _rules_only(message, hits, "AI disabled — rules engine only.")
    else:
        try:
            data = call_model(message, hits, model or pick_model(list_models()))
        except EngineError as exc:
            result = _rules_only(message, hits, str(exc))
        else:
            ai_score = _clamp_score(data.get("risk_score"), base_score)
            score = max(ai_score, base_score)
            if ai_score >= 60 and base_score >= 60:
                score = min(100, score + 5)
            level = _level_for(score)

            flags: list[Flag] = []
            for item in _as_list(data.get("red_flags"), limit=8):
                if not isinstance(item, dict):
                    continue
                title = _text(item.get("title"), 90)
                if not title:
                    continue
                severity = str(item.get("severity", "medium")).lower()
                flags.append(
                    Flag(
                        title=title,
                        evidence=_text(item.get("evidence"), 200),
                        why_it_matters=_text(item.get("why_it_matters"), 400),
                        severity=severity if severity in _SEVERITIES else "medium",
                    )
                )

            # The rules engine never lets a critical demand disappear from the report.
            for hit in hits:
                if hit.severity in {"critical", "high"} and not _flag_covered(hit, flags):
                    flags.append(
                        Flag(
                            title=hit.label,
                            evidence=hit.evidence[0] if hit.evidence else "",
                            why_it_matters=hit.why,
                            severity=hit.severity,
                            source="rules",
                        )
                    )

            order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
            flags.sort(key=lambda f: order.get(f.severity, 2))

            actions = [_text(a, 160) for a in _as_list(data.get("recommended_actions"), 6)]
            actions = [a for a in actions if a]
            if not actions:
                actions = _rules_only(message, hits, "")["recommended_actions"]

            result = Analysis(
                risk_level=level,
                risk_score=score,
                verdict=str(data.get("verdict") or _verdict_for(level)).lower(),
                category=_text(data.get("category"), 40) or "unclear",
                headline=_text(data.get("headline"), 160)
                or "Treat this message with caution until you verify the employer.",
                summary=_text(data.get("summary"), 700),
                red_flags=flags[:8],
                positive_signals=[
                    _text(p, 160) for p in _as_list(data.get("positive_signals"), 4) if _text(p)
                ],
                recommended_actions=actions[:5],
                questions_to_ask=[
                    _text(q, 160) for q in _as_list(data.get("questions_to_ask"), 4) if _text(q)
                ],
                confidence=str(data.get("confidence", "medium")).lower(),
                engine="ollama",
                model=model or "",
                rule_hits=hits,
            )

    result.latency_ms = int((time.perf_counter() - started) * 1000)
    result.rule_hits = hits
    return result


def mask_sensitive(text: str) -> str:
    """Mask CNIC and passport numbers when echoing a message back to the screen."""
    text = re.sub(r"\b\d{5}-\d{7}-\d\b", "*****-*******-*", text)
    text = re.sub(r"\b[A-Z]{2}\d{7}\b", "**#######", text)
    return text
