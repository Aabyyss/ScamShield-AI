# Database

One SQLite file, created on demand, owned entirely by the app.

| | |
|---|---|
| Engine | `sqlite3` from the Python standard library (no ORM, no server) |
| Default path | `data/scamshield.db` (next to the project) |
| Override | `SCAMSHIELD_DB` environment variable |
| Access | `scamshield/learning.py` only — the UI and engine never open the file directly |
| Mode | Write-ahead not enabled; one short-lived connection per operation, committed and closed |
| Retention | Kept until the user clears it from the **Learning** tab |

The schema is applied idempotently (`CREATE TABLE IF NOT EXISTS`) on every connection, so a new
install needs no migration step and an existing file is never recreated.

---

## 1. Consent gate

**Nothing is written until the user allows it.** The choice lives in `settings` as
`learning_consent = "on" | "off"`. `learning_enabled()` is checked inside `record_verdict()`, so no
code path can bypass it:

| `settings.learning_consent` | Meaning | Behaviour |
|---|---|---|
| *(no row)* | Never asked (new install) | Nothing recorded; the UI shows the consent dialog |
| `"on"` | Allowed | Scans, corrections, phrases and trust rules are stored |
| `"off"` | Declined | Nothing recorded; the UI states that learning is off |

## 2. Schema

```sql
CREATE TABLE verdicts (                      -- one row per scanned message
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  TEXT    NOT NULL,            -- ISO-8601 UTC
    simhash     INTEGER NOT NULL,            -- 64-bit fingerprint of the wording (no text!)
    level       TEXT    NOT NULL,            -- HIGH | MEDIUM | LOW
    score       INTEGER NOT NULL,            -- 0-100
    rules       TEXT    NOT NULL DEFAULT '', -- comma-separated rule keys that fired
    engine      TEXT    NOT NULL DEFAULT '', -- rules | ollama
    model       TEXT    NOT NULL DEFAULT ''  -- e.g. gemma4:e2b
);
CREATE INDEX idx_verdicts_hash ON verdicts(simhash);

CREATE TABLE feedback (                      -- one correction per verdict
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    verdict_id      INTEGER NOT NULL UNIQUE, -- FK -> verdicts.id (enforced by code)
    created_at      TEXT    NOT NULL,
    predicted_level TEXT    NOT NULL,
    actual_level    TEXT    NOT NULL,        -- what the user said it really was
    note            TEXT    NOT NULL DEFAULT '',
    rule_keys       TEXT    NOT NULL DEFAULT ''
);

CREATE TABLE rule_stats (                    -- Beta counters per rule
    rule_key   TEXT PRIMARY KEY,
    scams      REAL NOT NULL DEFAULT 0,
    legit      REAL NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);

CREATE TABLE phrases (                       -- wording the user taught
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    phrase     TEXT    NOT NULL UNIQUE,      -- normalised, lowercase, >= 2 words
    kind       TEXT    NOT NULL DEFAULT 'scam',
    created_at TEXT    NOT NULL,
    enabled    INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE trusted_domains (               -- domains the user vouches for
    domain     TEXT PRIMARY KEY,             -- lowercase, no scheme, no www.
    note       TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    enabled    INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE settings (                      -- key/value app state
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

## 3. Relations

```
verdicts 1 ──── 0..1 feedback        (feedback.verdict_id is UNIQUE: re-labelling replaces)
rule_stats                            (no FK: keyed by rule key, not by verdict)
phrases, trusted_domains, settings    (independent reference data)
```

There are no database-level foreign keys on purpose: the store survives rule renames without
cascading deletes, and orphaned stats are harmless.

## 4. What is *not* stored

- **The message text.** Only `simhash`, a 64-bit fingerprint (3-token shingles, BLAKE2b), which
  supports "you checked 3 messages like this" without keeping the content.
- CNIC, passport or account numbers — masked before they reach the screen or a report.
- Anything about the model conversation, prompts or replies.

## 5. Write paths

| Operation | Function | Notes |
|---|---|---|
| Record a scan | `record_verdict(text, result)` | Called the moment the rules verdict renders; returns the row id |
| Refine a scan | `update_verdict(id, result)` | AI phase updates the same row — one scan, one row |
| Store a correction | `record_feedback(...)` | Reverses the previous label first, so re-labelling does not stack |
| Learn a phrase | `add_phrase(...)` | Rejects single words / < 6 characters |
| Trust a domain | `add_trusted_domain(...)` | Validated as `label.tld` |
| Consent | `set_consent(bool)` | Enforced inside `record_verdict()` |
| Reset learning | `reset_learning()` | Clears feedback, rule_stats, phrases, trusted_domains; keeps history |
| Clear history | `clear_history()` | Clears verdicts + feedback |

Every write is wrapped in `_session()` (commit, close in `finally`) and returns a failure value
rather than raising, so a broken store degrades the app instead of crashing it. `store_health()`
reports `{ok, path, error}` so the UI can name the real problem.

## 6. Weight maths (read side)

```
labels     = scams + legit
precision  = (2 + scams) / (4 + labels)              # Beta(2, 2) prior
multiplier = clamp(0.55 + 0.9 * precision, 0.55, 1.45)   # only when labels >= 3
```

Stored values are the raw counters; the multiplier is derived at read time, so changing the prior
or the bounds never requires a data migration.

## 7. Handy queries

```sql
-- what has been scanned
SELECT id, created_at, level, score, engine, model FROM verdicts ORDER BY id DESC LIMIT 10;

-- corrections and their effect
SELECT v.level AS predicted, f.actual_level, v.rules
FROM feedback f JOIN verdicts v ON v.id = f.verdict_id ORDER BY f.id DESC;

-- rules whose weight has moved
SELECT rule_key, scams, legit, (scams + legit) AS labels FROM rule_stats
ORDER BY labels DESC;

-- near-duplicates of a fingerprint (computed in Python; SQL only narrows the window)
SELECT id, level FROM verdicts WHERE simhash = ?;
```

## 8. Reset and privacy operations

| User action | SQL effect |
|---|---|
| Turn learning off | `settings` gains `learning_consent='off'`; existing rows stay until cleared |
| Reset learning | `DELETE FROM feedback / rule_stats / phrases / trusted_domains` |
| Clear history | `DELETE FROM verdicts / feedback` |
| Delete everything | close the app and delete `data/scamshield.db` |

The file is **not encrypted**; it is readable by the OS user account that runs the app. That is
acceptable only because no message text is stored and consent is explicit — see §14.2 of the
project report.
