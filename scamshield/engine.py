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

from .rules import RULES, Hit, prescan, rule_score

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


@lru_cache(maxsize=1)
def runtime_brief() -> str:
    """The compact projection of SKILL.md that small local models actually receive.

    The full playbook is 2.5k tokens; on a CPU-only laptop that is most of the latency, and
    small models lose the plot long before the answer ends.
    """
    skill = load_skill()
    start = skill.find("<!-- runtime:start -->")
    end = skill.find("<!-- runtime:end -->")
    if start != -1 and end > start:
        return skill[start + len("<!-- runtime:start -->") : end].strip()
    return _strip_frontmatter(skill)


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


def warmup(model: str, timeout: float = 180.0) -> bool:
    """Load the model into memory once so the first real analysis is not slowed by a cold start."""
    if not model:
        return False
    try:
        requests.post(
            f"{ollama_host()}/api/generate",
            json={
                "model": model,
                "prompt": "ok",
                "stream": False,
                "keep_alive": "30m",
                "options": {"num_predict": 1, "num_ctx": 512},
            },
            timeout=timeout,
        )
        return True
    except requests.RequestException:
        return False


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
    code: str = ""  # taxonomy code; empty for restored rule flags
    corroborated: bool = False  # a rule matched the same family


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
    discarded_claims: int = 0  # model flags dropped because they could not be verified


# --------------------------------------------------------------------------------------
# Ollama call
# --------------------------------------------------------------------------------------


def _close_fragment(fragment: str) -> str:
    """Close every string/bracket left open by a cut-off generation."""
    stack: list[str] = []
    in_string = False
    escape = False
    for ch in fragment:
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch in "{[":
            stack.append(ch)
        elif ch in "}]" and stack:
            stack.pop()

    repaired = fragment
    if in_string:
        repaired = repaired.rstrip("\\")
        repaired += '"'
    repaired = re.sub(r"[,:]\s*$", "", repaired.rstrip())
    for opener in reversed(stack):
        repaired += "}" if opener == "{" else "]"
    return repaired


def _salvage_json(fragment: str) -> dict:
    """Recover the fields that were complete before the model was cut off."""
    candidate = fragment
    for _ in range(60):
        try:
            return json.loads(_close_fragment(candidate))
        except json.JSONDecodeError:
            cut = max(candidate.rfind(","), candidate.rfind("\n"))
            if cut <= 0:
                break
            candidate = candidate[:cut]
    raise ValueError("unrecoverable")


def _extract_json(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"```\s*$", "", text).strip()
    start = text.find("{")
    if start == -1:
        raise EngineError("The model did not return JSON.")
    candidate = text[start:]
    end = candidate.rfind("}")
    if end != -1:
        candidate = candidate[: end + 1]
    # Small models love trailing commas; repairing is cheaper than a 2-minute retry.
    candidate = re.sub(r",\s*([}\]])", r"\1", candidate)
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as exc:
        try:
            return _salvage_json(text[start:])
        except ValueError:
            raise EngineError(f"The model returned malformed JSON ({exc.msg}).") from exc


def _build_messages(message: str, hits: list[Hit]) -> list[dict[str, str]]:
    system = runtime_brief()
    system += (
        "\n\n## Hard constraints for this deployment\n"
        "- You are running fully offline on the user's laptop. Do not mention lookups you cannot "
        "perform.\n"
        "- Output must be a single JSON object matching the shape above. No prose outside it.\n"
        "- Never copy schema wording or example wording into your answer; use only words from "
        "the message.\n"
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


def _brace_delta(piece: str, state: dict[str, bool], depth: int) -> tuple[int, bool]:
    """Track JSON brace depth through a streamed chunk, ignoring braces inside strings."""
    for ch in piece:
        if state["in_string"]:
            if state["escape"]:
                state["escape"] = False
            elif ch == "\\":
                state["escape"] = True
            elif ch == '"':
                state["in_string"] = False
        elif ch == '"':
            state["in_string"] = True
        elif ch == "{":
            depth += 1
            state["started"] = True
        elif ch == "}":
            depth -= 1
    return depth, state["started"]


def call_model(message: str, hits: list[Hit], model: str, timeout: float = 300.0) -> dict:
    """Ask the local model for the JSON verdict, stopping the moment the object closes.

    Small models often keep generating past a valid answer and get cut off by num_predict,
    which produced unparseable JSON. Streaming lets us finish on the closing brace instead.
    """
    payload = {
        "model": model,
        "messages": _build_messages(message, hits),
        "stream": True,
        "format": "json",
        "keep_alive": "30m",
        "options": {
            "temperature": 0.1,
            "top_p": 0.9,
            "repeat_penalty": 1.05,
            "num_ctx": 3072,
            "num_predict": 700,
        },
    }

    chunks: list[str] = []
    state = {"in_string": False, "escape": False, "started": False}
    depth = 0

    try:
        with requests.post(
            f"{ollama_host()}/api/chat", json=payload, timeout=(5, timeout), stream=True
        ) as res:
            res.raise_for_status()
            for line in res.iter_lines(decode_unicode=True):
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                except ValueError:
                    continue
                piece = (chunk.get("message") or {}).get("content", "")
                if piece:
                    chunks.append(piece)
                    depth, started = _brace_delta(piece, state, depth)
                    if started and depth <= 0:
                        break  # complete JSON object — stop generation early
                if chunk.get("done"):
                    break
    except requests.Timeout as exc:
        raise EngineError("Local model timed out. Try a smaller model or a shorter message.") from exc
    except requests.RequestException as exc:
        raise EngineError(f"Cannot reach Ollama at {ollama_host()}: {exc}") from exc

    content = "".join(chunks)
    if not content:
        raise EngineError("Ollama returned an empty response.")
    # A cut-off answer is still useful: the verdict, summary and advice come first.
    return _extract_json(content)


# --------------------------------------------------------------------------------------
# Merging
# --------------------------------------------------------------------------------------

_STOPWORDS = {
    "a", "an", "the", "to", "for", "of", "or", "and", "is", "are", "in", "on", "with", "your",
    "you", "not", "no", "that", "this", "it", "as", "at", "from", "by", "be", "has", "have",
    "job", "message", "real",
}


def _tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z]{3,}", text.lower())
    return {w for w in words if w not in _STOPWORDS}


def _normalise(text: str) -> str:
    text = (
        text.replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u2019", "'")
        .replace("\u2026", " ")
    )
    return re.sub(r"\s+", " ", text).strip().lower()


def _quote_verified(quote: str, text_norm: str, text_tokens: set[str]) -> bool:
    """A model claim survives only if its quote can be found in the message."""
    q = _normalise(quote)
    q = re.sub(r"^\.{2,}\s*|\s*\.{2,}$", "", q).strip(" \"'.,;:!")
    if len(q) < 8:
        return False
    if q in text_norm:
        return True
    q_tokens = {t for t in re.findall(r"[a-z0-9]+", q) if t not in _STOPWORDS}
    if len(q_tokens) < 3:
        return False
    return sum(1 for t in q_tokens if t in text_tokens) / len(q_tokens) >= 0.75


TAXONOMY = {rule.key for rule in RULES}
CRITICAL_CODES = {rule.key for rule in RULES if rule.severity == "critical"}
PAYMENT_CODES = {"upfront_payment", "personal_payment_channel"}
# "No payment or fee of any kind is required" must never be read as a payment demand.
NO_FEE_RE = re.compile(
    r"\b(?:no|not|never|without|don't|do\s+not)\b[^.]{0,40}"
    r"\b(?:payment|fee|fees|charge|charges|money|deposit|cost)\b",
    re.IGNORECASE,
)


def _level_for(score: int) -> str:
    if score >= 65:
        return "HIGH"
    if score >= 30:
        return "MEDIUM"
    return "LOW"


def _verdict_for(level: str) -> str:
    return {"HIGH": "scam", "MEDIUM": "suspicious"}.get(level, "likely_legitimate")


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


def _headline(level: str, model_headline: str, message: str) -> str:
    """Keep the model's headline only when it is actually a verdict, not a copied subject line."""
    fallback = {
        "HIGH": "This matches a known job-scam pattern. Do not pay.",
        "MEDIUM": "Treat this offer as unverified until you check the employer.",
        "LOW": "No known scam pattern found — still verify independently.",
    }[level]
    candidate = model_headline.strip()
    if level == "LOW" or not candidate or len(candidate.split()) > 14:
        return fallback
    normalised = _normalise(candidate)
    if normalised.startswith("subject") or "caution" in normalised:
        return fallback
    # A headline that is just the message's opening line is not a verdict.
    candidate_words = set(re.findall(r"[a-z0-9]+", normalised))
    opening_words = set(re.findall(r"[a-z0-9]+", _normalise(message))[:8])
    if candidate_words and len(candidate_words & opening_words) / len(candidate_words) >= 0.8:
        return fallback
    return candidate


def _flags_from_hits(hits: list[Hit]) -> list[Flag]:
    return [
        Flag(
            title=h.label,
            evidence=h.evidence[0] if h.evidence else "",
            why_it_matters=h.why,
            severity=h.severity,
            source="rules",
            code=h.key,
            corroborated=True,
        )
        for h in hits
    ]


def _rules_only(
    message: str,
    hits: list[Hit],
    error: str | None,
    ai_note: str = "the local language model was unavailable",
) -> Analysis:
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
            f"Rules-engine only: {ai_note}, so this verdict comes from {len(hits)} "
            "deterministic signal(s) in the text."
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
        result = _rules_only(message, hits, None, ai_note="the AI layer is switched off")
    else:
        try:
            data = call_model(message, hits, model or pick_model(list_models()))
        except EngineError as exc:
            result = _rules_only(
                message,
                hits,
                str(exc),
                ai_note="the local model's answer could not be used",
            )
        else:
            flags: list[Flag] = []
            discarded = 0
            text_norm = _normalise(message)
            text_tokens = _tokens(message)
            hit_keys = {h.key for h in hits}

            # Rules are the source of truth for every family they matched: their labels and
            # quotes are written by us and cannot drift. The model may only add NEW families.
            flags = _flags_from_hits(hits)
            extras: list[Flag] = []
            seen_codes = set(hit_keys)

            for item in _as_list(data.get("red_flags"), limit=8):
                if not isinstance(item, dict):
                    continue
                code = _text(item.get("code"), 40).lower()
                title = _text(item.get("title"), 90)
                evidence = _text(item.get("evidence"), 240)
                if (
                    not title
                    or code not in TAXONOMY
                    or code in seen_codes
                    or code in CRITICAL_CODES  # critical families must be rule-proven
                    or not _quote_verified(evidence, text_norm, text_tokens)
                    or (code in PAYMENT_CODES and NO_FEE_RE.search(evidence))
                ):
                    discarded += 1
                    continue
                seen_codes.add(code)
                # Only the rules layer can certify a critical or high finding.
                extras.append(
                    Flag(
                        title=title,
                        evidence=evidence,
                        why_it_matters=_text(item.get("why_it_matters"), 400),
                        severity="medium",
                        source="ai",
                        code=code,
                    )
                )

            flags.extend(extras[:2])
            order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
            flags.sort(key=lambda f: order.get(f.severity, 2))

            # Deterministic scoring: rules set the floor, and verified model findings add at
            # most 15 points, so a lone model opinion can never reach MEDIUM on its own.
            score = min(100, base_score + min(15, 5 * len(extras)))
            level = _level_for(score)

            actions = [_text(a, 160) for a in _as_list(data.get("recommended_actions"), 6)]
            actions = [a for a in actions if a]
            if not actions:
                actions = _rules_only(message, hits, None).recommended_actions

            headline = _headline(level, _text(data.get("headline"), 160), message)
            summary = _text(data.get("summary"), 700)
            if level == "LOW" and re.search(
                r"\b(scam|fraud|fake|do not pay|do not respond)\b", summary, re.I
            ):
                summary = (
                    "The model raised concerns, but none matched a known fraud pattern in the "
                    "text. Verify the employer independently before sharing documents or money."
                )

            result = Analysis(
                risk_level=level,
                risk_score=score,
                verdict=_verdict_for(level),
                category=_text(data.get("category"), 40) or "unclear",
                headline=headline,
                summary=summary,
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
                discarded_claims=discarded,
            )

    result.latency_ms = int((time.perf_counter() - started) * 1000)
    result.rule_hits = hits
    return result
