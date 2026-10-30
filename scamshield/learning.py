"""Local, explainable self-learning — no model retraining, no cloud.

ScamShield learns the way a careful analyst would: it remembers which rules were right,
which ones cried wolf, and which phrases a particular user keeps receiving. Everything is
stored in a single SQLite file next to the project, and every adjustment is bounded, so a
handful of mistakes can never turn the detector into a rubber stamp.

What is learned
---------------
1. **Rule precision.** For every rule that fires, we keep `scams` and `legit` counts from the
   user's corrections and model the precision as Beta(2 + scams, 2 + legit). The posterior
   mean scales the rule's weight between 0.55x and 1.45x — and only after 3 labelled examples.
2. **Taught phrases.** A user can add wording they keep seeing ("visa stamping charge"). It is
   matched literally and contributes one modest, clearly-labelled flag.
3. **Trusted domains.** User-approved domains dampen the free-mailbox / link heuristics.
4. **Message memory.** A 64-bit simhash of each scan finds near-duplicates *without storing the
   text* — the privacy story survives, and the UI can say "you checked 3 messages like this".

Safeguards (the pitfalls that ruin naive feedback loops):
- feedback only comes from an explicit user click, never from the model's own guess;
- weights are shrunk toward the original, clipped, and require a minimum sample;
- one correction can never change a verdict on its own;
- everything can be reviewed, disabled and reset from the Learning tab.
"""

from __future__ import annotations

import hashlib
import os
import re
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .entities import domains_in
from .rules import Hit

# Beta prior: mean 0.5, worth four observations. Stops "1 correction = 1 new truth".
PRIOR_SCAM = 2.0
PRIOR_LEGIT = 2.0
MIN_LABELS = 3.0
MIN_MULT, MAX_MULT = 0.55, 1.45
PHRASE_WEIGHT = 22
SIMHASH_BITS = 64
DEFAULT_SIMILARITY_DISTANCE = 8

_SCHEMA = """
CREATE TABLE IF NOT EXISTS verdicts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    simhash INTEGER NOT NULL,
    level TEXT NOT NULL,
    score INTEGER NOT NULL,
    rules TEXT NOT NULL DEFAULT '',
    engine TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    verdict_id INTEGER NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    predicted_level TEXT NOT NULL,
    actual_level TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    rule_keys TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_verdicts_hash ON verdicts(simhash);
CREATE TABLE IF NOT EXISTS rule_stats (
    rule_key TEXT PRIMARY KEY,
    scams REAL NOT NULL DEFAULT 0,
    legit REAL NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS phrases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    phrase TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL DEFAULT 'scam',
    created_at TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS trusted_domains (
    domain TEXT PRIMARY KEY,
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

CONSENT_KEY = "learning_consent"

_LEVELS = ("HIGH", "MEDIUM", "LOW")


def db_path() -> Path:
    """Resolve the database path on every call so tests can point it at a temp file."""
    override = os.environ.get("SCAMSHIELD_DB")
    if override:
        return Path(override)
    return Path(__file__).resolve().parent.parent / "data" / "scamshield.db"


def _connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


@contextmanager
def _session():
    """One short-lived connection per operation, committed and always closed.

    Streamlit reruns scripts from many threads; closing matters on Windows, where an open
    handle blocks file deletion.
    """
    conn = _connect()
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def available() -> bool:
    """True when the local store can be opened. The UI degrades quietly if it cannot."""
    try:
        _connect().close()
        return True
    except (sqlite3.Error, OSError):
        return False


def store_health() -> dict:
    """Whether the store is usable, and why not — so the UI never shows a silent zero."""
    try:
        _connect().close()
    except (sqlite3.Error, OSError) as exc:
        return {"ok": False, "path": str(db_path()), "error": str(exc)}
    return {"ok": True, "path": str(db_path()), "error": ""}


# --------------------------------------------------------------------------------------
# Consent — nothing is recorded until the user says yes
# --------------------------------------------------------------------------------------


def _get_setting(key: str, default: str | None = None) -> str | None:
    try:
        with _session() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    except (sqlite3.Error, OSError):
        return default
    return row["value"] if row else default


def _set_setting(key: str, value: str) -> bool:
    try:
        with _session() as conn:
            conn.execute(
                "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value, "
                "updated_at = excluded.updated_at",
                (key, value, _now()),
            )
    except (sqlite3.Error, OSError):
        return False
    return True


def consent_choice() -> bool | None:
    """None until the user has been asked, then the stored choice."""
    value = _get_setting(CONSENT_KEY)
    if value is None:
        return None
    return value == "on"


def set_consent(enabled: bool) -> bool:
    return _set_setting(CONSENT_KEY, "on" if enabled else "off")


def learning_enabled() -> bool:
    """Learning runs only after an explicit yes. Unasked means off for new installs."""
    return consent_choice() is True


# --------------------------------------------------------------------------------------
# Message fingerprinting — near-duplicate memory without keeping the text
# --------------------------------------------------------------------------------------


def simhash(text: str) -> int:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    if not tokens:
        return 0
    shingles = (
        [" ".join(tokens[i : i + 3]) for i in range(len(tokens) - 2)]
        if len(tokens) >= 3
        else tokens
    )
    bits = [0] * SIMHASH_BITS
    for shingle in shingles:
        digest = hashlib.blake2b(shingle.encode("utf-8"), digest_size=8).digest()
        value = int.from_bytes(digest, "big")
        for bit in range(SIMHASH_BITS):
            bits[bit] += 1 if (value >> bit) & 1 else -1
    out = 0
    for bit, score in enumerate(bits):
        if score >= 0:
            out |= 1 << bit
    return out - (1 << 64) if out >= (1 << 63) else out


def _distance(a: int, b: int) -> int:
    mask = (1 << 64) - 1
    return bin((a & mask) ^ (b & mask)).count("1")


@dataclass
class SimilarCase:
    verdict_id: int
    level: str
    score: int
    created_at: str
    similarity: int
    distance: int


def similar_cases(text: str, max_distance: int = DEFAULT_SIMILARITY_DISTANCE, limit: int = 3) -> list[SimilarCase]:
    """Find earlier scans whose wording is close to this one. Read-only, fails silently."""
    if not text.strip():
        return []
    fingerprint = simhash(text)
    try:
        with _session() as conn:
            rows = conn.execute(
                "SELECT id, level, score, created_at, simhash FROM verdicts "
                "ORDER BY id DESC LIMIT 500"
            ).fetchall()
    except (sqlite3.Error, OSError):
        return []
    matches: list[SimilarCase] = []
    for row in rows:
        dist = _distance(fingerprint, row["simhash"])
        if dist <= max_distance:
            matches.append(
                SimilarCase(
                    verdict_id=row["id"],
                    level=row["level"],
                    score=row["score"],
                    created_at=row["created_at"],
                    similarity=round((1 - dist / 64) * 100),
                    distance=dist,
                )
            )
    matches.sort(key=lambda m: m.distance)
    return matches[:limit]


# --------------------------------------------------------------------------------------
# Verdict history
# --------------------------------------------------------------------------------------


def record_verdict(text: str, result) -> int | None:
    """Store a scan so a later correction can be tied to the exact evidence that fired.

    Returns the new row id, or None when learning is switched off or the write failed.
    """
    if not learning_enabled():
        return None
    try:
        keys = ",".join(h.key for h in result.rule_hits)
        with _session() as conn:
            cursor = conn.execute(
                "INSERT INTO verdicts (created_at, simhash, level, score, rules, engine, model) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    _now(),
                    simhash(text),
                    result.risk_level,
                    result.risk_score,
                    keys,
                    result.engine,
                    result.model or "",
                ),
            )
            return int(cursor.lastrowid)
    except (sqlite3.Error, OSError):
        return None


def update_verdict(verdict_id: int, result) -> bool:
    """Replace a scan's level/score with the model-backed result, keeping one row per scan.

    The rules verdict is stored the instant it renders so the counters move immediately; the
    AI phase then refines the same row instead of adding a second one.
    """
    try:
        with _session() as conn:
            conn.execute(
                "UPDATE verdicts SET level = ?, score = ?, rules = ?, engine = ?, model = ? "
                "WHERE id = ?",
                (
                    result.risk_level,
                    result.risk_score,
                    ",".join(h.key for h in result.rule_hits),
                    result.engine,
                    result.model or "",
                    verdict_id,
                ),
            )
    except (sqlite3.Error, OSError):
        return False
    return True


def verdict_count() -> int:
    try:
        with _session() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM verdicts").fetchone()[0])
    except (sqlite3.Error, OSError):
        return 0


def recent_verdicts(limit: int = 8) -> list[dict]:
    try:
        with _session() as conn:
            rows = conn.execute(
                "SELECT v.id, v.created_at, v.level, v.score, v.engine, v.rules, "
                "f.actual_level, f.predicted_level "
                "FROM verdicts v LEFT JOIN feedback f ON f.verdict_id = v.id "
                "ORDER BY v.id DESC LIMIT ?",
                (limit,),
            ).fetchall()
    except (sqlite3.Error, OSError):
        return []
    return [
        {
            "id": row["id"],
            "created_at": row["created_at"],
            "level": row["level"],
            "score": row["score"],
            "engine": row["engine"],
            "actual_level": row["actual_level"],
            "predicted_level": row["predicted_level"],
        }
        for row in rows
    ]


# --------------------------------------------------------------------------------------
# Feedback -> bounded rule weights
# --------------------------------------------------------------------------------------


def _label_weights(level: str) -> tuple[float, float]:
    """How much a corrected label counts as scam evidence vs legitimate evidence."""
    return {"HIGH": (1.0, 0.0), "MEDIUM": (0.5, 0.5), "LOW": (0.0, 1.0)}.get(level, (0.0, 0.0))


def record_feedback(
    verdict_id: int,
    predicted_level: str,
    actual_level: str,
    rule_keys: list[str],
    note: str = "",
) -> list[dict]:
    """Store one correction and update the Beta counts for the rules that fired.

    Returns the rules whose weight changed, so the UI can show exactly what was learned.
    """
    actual_level = actual_level.upper()
    if actual_level not in _LEVELS:
        actual_level = predicted_level
    scam_w, legit_w = _label_weights(actual_level)
    before = rule_multipliers()

    def bump(conn: sqlite3.Connection, keys: list[str], scam: float, legit: float) -> None:
        for key in set(keys):
            if not key or key == "learned_phrase":
                continue  # taught phrases carry no baseline weight of their own
            conn.execute(
                "INSERT INTO rule_stats (rule_key, scams, legit, updated_at) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(rule_key) DO UPDATE SET "
                "scams = MAX(0, scams + excluded.scams), "
                "legit = MAX(0, legit + excluded.legit), "
                "updated_at = excluded.updated_at",
                (key, scam, legit, _now()),
            )

    try:
        with _session() as conn:
            # Re-labelling the same verdict replaces the old evidence instead of stacking it.
            previous = conn.execute(
                "SELECT actual_level, rule_keys FROM feedback WHERE verdict_id = ?",
                (verdict_id,),
            ).fetchone()
            if previous:
                old_scam, old_legit = _label_weights(previous["actual_level"])
                old_keys = [k for k in str(previous["rule_keys"]).split(",") if k]
                bump(conn, old_keys, -old_scam, -old_legit)

            conn.execute(
                "INSERT INTO feedback "
                "(verdict_id, created_at, predicted_level, actual_level, note, rule_keys) "
                "VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(verdict_id) DO UPDATE SET "
                "predicted_level = excluded.predicted_level, "
                "actual_level = excluded.actual_level, note = excluded.note, "
                "rule_keys = excluded.rule_keys, created_at = excluded.created_at",
                (
                    verdict_id,
                    _now(),
                    predicted_level,
                    actual_level,
                    note[:400],
                    ",".join(rule_keys),
                ),
            )
            bump(conn, list(rule_keys), scam_w, legit_w)
    except (sqlite3.Error, OSError):
        return []

    after = rule_multipliers()
    changed = []
    for key, value in after.items():
        if abs(value - before.get(key, 1.0)) > 0.001:
            stat = rule_stat(key)
            changed.append({"key": key, "multiplier": value, **stat})
    return changed


def rule_stat(key: str) -> dict:
    try:
        with _session() as conn:
            row = conn.execute(
                "SELECT scams, legit FROM rule_stats WHERE rule_key = ?", (key,)
            ).fetchone()
    except (sqlite3.Error, OSError):
        row = None
    scams = float(row["scams"]) if row else 0.0
    legit = float(row["legit"]) if row else 0.0
    labels = scams + legit
    precision = (PRIOR_SCAM + scams) / (PRIOR_SCAM + PRIOR_LEGIT + labels)
    return {
        "scams": round(scams, 1),
        "legit": round(legit, 1),
        "labels": round(labels, 1),
        "precision": round(precision, 2),
        "multiplier": _multiplier_for(precision, labels),
    }


def _multiplier_for(precision: float, labels: float) -> float:
    if labels < MIN_LABELS:
        return 1.0
    # 0.5 posterior -> 1.0x, 1.0 -> 1.45x, 0.0 -> 0.55x
    raw = 0.55 + 0.9 * precision
    return round(min(MAX_MULT, max(MIN_MULT, raw)), 2)


def rule_multipliers() -> dict[str, float]:
    """Posterior weight multiplier for every rule the user has given feedback on."""
    try:
        with _session() as conn:
            rows = conn.execute("SELECT rule_key, scams, legit FROM rule_stats").fetchall()
    except (sqlite3.Error, OSError):
        return {}
    out: dict[str, float] = {}
    for row in rows:
        labels = float(row["scams"]) + float(row["legit"])
        precision = (PRIOR_SCAM + float(row["scams"])) / (
            PRIOR_SCAM + PRIOR_LEGIT + labels
        )
        out[row["rule_key"]] = _multiplier_for(precision, labels)
    return out


def learned_rule_rows() -> list[dict]:
    """Everything the Learning tab needs to show its work."""
    try:
        with _session() as conn:
            rows = conn.execute(
                "SELECT rule_key, scams, legit FROM rule_stats ORDER BY (scams + legit) DESC"
            ).fetchall()
    except (sqlite3.Error, OSError):
        return []
    out = []
    for row in rows:
        scams, legit = float(row["scams"]), float(row["legit"])
        labels = scams + legit
        precision = (PRIOR_SCAM + scams) / (PRIOR_SCAM + PRIOR_LEGIT + labels)
        out.append(
            {
                "rule": row["rule_key"],
                "scams": round(scams, 1),
                "legit": round(legit, 1),
                "labels": round(labels, 1),
                "precision": round(precision, 2),
                "multiplier": _multiplier_for(precision, labels),
                "active": labels >= MIN_LABELS,
            }
        )
    return out


def feedback_summary() -> dict:
    try:
        with _session() as conn:
            total = int(conn.execute("SELECT COUNT(*) FROM feedback").fetchone()[0])
            correct = int(
                conn.execute(
                    "SELECT COUNT(*) FROM feedback WHERE predicted_level = actual_level"
                ).fetchone()[0]
            )
    except (sqlite3.Error, OSError):
        return {"total": 0, "correct": 0, "corrections": 0, "accuracy": None}
    return {
        "total": total,
        "correct": correct,
        "corrections": total - correct,
        "accuracy": round(correct / total, 2) if total else None,
    }


# --------------------------------------------------------------------------------------
# Taught phrases
# --------------------------------------------------------------------------------------


def normalise_phrase(phrase: str) -> str:
    return re.sub(r"\s+", " ", phrase.strip().lower())


def add_phrase(phrase: str, kind: str = "scam") -> tuple[bool, str]:
    """Teach a phrase. Multiword only: single words overfit immediately."""
    clean = normalise_phrase(phrase)
    if len(clean) < 6 or len(clean.split()) < 2:
        return False, "Use at least two words (six characters) so the match stays specific."
    try:
        with _session() as conn:
            conn.execute(
                "INSERT INTO phrases (phrase, kind, created_at, enabled) VALUES (?, ?, ?, 1) "
                "ON CONFLICT(phrase) DO UPDATE SET enabled = 1",
                (clean, kind, _now()),
            )
    except (sqlite3.Error, OSError) as exc:
        return False, f"Could not save the phrase: {exc}"
    return True, f"Learned “{clean}”. It is checked on every future message."


def phrases(only_enabled: bool = True) -> list[dict]:
    query = "SELECT id, phrase, kind, enabled, created_at FROM phrases"
    if only_enabled:
        query += " WHERE enabled = 1"
    query += " ORDER BY id DESC"
    try:
        with _session() as conn:
            rows = conn.execute(query).fetchall()
    except (sqlite3.Error, OSError):
        return []
    return [dict(row) for row in rows]


def delete_phrase(phrase_id: int) -> None:
    try:
        with _session() as conn:
            conn.execute("DELETE FROM phrases WHERE id = ?", (phrase_id,))
    except (sqlite3.Error, OSError):
        pass


# --------------------------------------------------------------------------------------
# Trusted domains
# --------------------------------------------------------------------------------------


def add_trusted_domain(domain: str) -> tuple[bool, str]:
    clean = domain.strip().lower().removeprefix("www.").strip("/ ")
    if not re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}", clean):
        return False, "That does not look like a domain (example: systemsltd.com)."
    try:
        with _session() as conn:
            conn.execute(
                "INSERT INTO trusted_domains (domain, created_at, enabled) VALUES (?, ?, 1) "
                "ON CONFLICT(domain) DO UPDATE SET enabled = 1",
                (clean, _now()),
            )
    except (sqlite3.Error, OSError) as exc:
        return False, f"Could not save the domain: {exc}"
    return True, f"{clean} is now trusted. Free-mailbox and link heuristics are dampened for it."


def trusted_domains() -> list[dict]:
    try:
        with _session() as conn:
            rows = conn.execute(
                "SELECT domain, created_at FROM trusted_domains WHERE enabled = 1 ORDER BY domain"
            ).fetchall()
    except (sqlite3.Error, OSError):
        return []
    return [dict(row) for row in rows]


def delete_trusted_domain(domain: str) -> None:
    try:
        with _session() as conn:
            conn.execute("DELETE FROM trusted_domains WHERE domain = ?", (domain,))
    except (sqlite3.Error, OSError):
        pass


def _trusted_set() -> set[str]:
    return {row["domain"] for row in trusted_domains()}


# --------------------------------------------------------------------------------------
# Applying what was learned
# --------------------------------------------------------------------------------------


def apply_to_hits(hits: list[Hit], message: str) -> tuple[list[Hit], list[str]]:
    """Adjust rule weights from feedback, add taught phrases, dampen trusted domains."""
    notes: list[str] = []
    multipliers = rule_multipliers()
    trusted = _trusted_set()
    domains = domains_in(message)

    for hit in hits:
        mult = multipliers.get(hit.key, 1.0)
        if mult != 1.0:
            original = hit.weight
            hit.weight = max(1, round(original * mult))
            hit.multiplier = mult
            hit.learned_note = f"weight {original}→{hit.weight} (×{mult:g}) from your feedback"

    # Every detected domain is one the user explicitly vouched for.
    if domains and trusted and all(d in trusted for d in domains):
        keys = {"unofficial_channel", "domain_mismatch"}
        if any(h.key in keys for h in hits):
            for hit in hits:
                if hit.key in keys:
                    hit.weight = max(1, round(hit.weight * 0.25))
                    hit.severity = "low"
                    hit.learned_note = "dampened: you marked this domain as trusted"
            notes.append("Trusted domain applied — free-mailbox and link signals were dampened.")

    taught = phrases()
    norm = re.sub(r"\s+", " ", message.lower())
    matched = [p["phrase"] for p in taught if p["phrase"] and p["phrase"] in norm]
    if matched:
        snippet = ""
        for phrase in matched:
            index = norm.find(phrase)
            if index != -1:
                snippet = message[max(0, index - 30) : index + len(phrase) + 30].strip()
                break
        hits.append(
            Hit(
                key="learned_phrase",
                label="Contains wording you flagged as suspicious",
                weight=PHRASE_WEIGHT,
                severity="medium",
                why=(
                    "You taught ScamShield that this wording appears in scams you receive. "
                    "It is your own signal, kept separate from the built-in rules."
                ),
                evidence=[f"…{snippet}…" if snippet else matched[0]],
                raw_evidence=matched,
                learned_note="taught by you",
            )
        )
        notes.append(f"{len(matched)} taught phrase(s) matched.")

    hits.sort(key=lambda h: h.weight, reverse=True)
    return hits, notes


# --------------------------------------------------------------------------------------
# Reset
# --------------------------------------------------------------------------------------


def reset_learning() -> None:
    """Forget corrections, taught phrases and trusted domains. Verdict history stays."""
    try:
        with _session() as conn:
            conn.execute("DELETE FROM feedback")
            conn.execute("DELETE FROM rule_stats")
            conn.execute("DELETE FROM phrases")
            conn.execute("DELETE FROM trusted_domains")
    except (sqlite3.Error, OSError):
        pass


def clear_history() -> None:
    try:
        with _session() as conn:
            conn.execute("DELETE FROM verdicts")
            conn.execute("DELETE FROM feedback")
    except (sqlite3.Error, OSError):
        pass
