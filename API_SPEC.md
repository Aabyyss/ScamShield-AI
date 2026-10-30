# API specification

## 0. There is no inbound HTTP API

ScamShield is a desktop app. Streamlit serves its own UI over loopback
(`http://127.0.0.1:8501` by default) and exposes no public endpoints, no webhooks and no
integration surface. There are no API keys and no accounts. If you need programmatic access, use
the Python API or the CLI in §1–§2.

| | |
|---|---|
| Bind address | `127.0.0.1` only — never `0.0.0.0` |
| Health probe | `GET /healthz` (Streamlit's own liveness endpoint, used by the launcher) |
| Auth | none — the process boundary is the security boundary |
| Outbound calls | one: to the Ollama server on `OLLAMA_HOST` (`http://127.0.0.1:11434` by default) |

---

## 1. Python API

```python
from scamshield import engine, learning, ocr, report

result = engine.analyze(text, model="gemma4:e2b", use_ai=True, use_learning=True)   # -> Analysis
```

### `engine.analyze(message, model="", use_ai=True, use_learning=True) -> Analysis`

Never raises for model problems: if Ollama is unreachable or its answer is unusable, the return
value is a rules-only `Analysis` whose `error` field explains why.

| Field | Type | Meaning |
|---|---|---|
| `risk_level` | `"HIGH" \| "MEDIUM" \| "LOW"` | Band from the deterministic score |
| `risk_score` | `int` | 0–100 |
| `verdict` | `str` | `scam` · `suspicious` · `likely_legitimate` · `unclear` |
| `category` | `str` | e.g. `advance_fee_visa_fraud` |
| `headline` / `summary` | `str` | Plain-language explanation (model when available) |
| `red_flags` | `list[Flag]` | Each with `title`, `evidence` (quoted), `why_it_matters`, `severity`, `source` |
| `recommended_actions` | `list[str]` | 3–5 next steps |
| `questions_to_ask` | `list[str]` | 1–3 questions for the employer |
| `confidence` | `"high" \| "medium" \| "low"` | Model-declared, never derived from the score |
| `engine` | `"rules" \| "ollama"` | Which path produced the explanation |
| `model` | `str` | Model name when the AI layer answered |
| `rule_hits` | `list[Hit]` | Deterministic evidence behind the score |
| `entities` | `list[Entity]` | Links, mailboxes, numbers, IDs |
| `notes` / `error` | `list[str]` / `str` | Learning and fallback messages |

Other public helpers: `engine.list_models()`, `engine.pick_model(available)`,
`engine.engine_online()`, `engine.warmup(model)`, `engine.load_skill()`, `engine.runtime_brief()`.

### Supporting modules

| Call | Returns |
|---|---|
| `rules.prescan(text)` | `list[Hit]` — every matched family with quoted evidence |
| `rules.rule_score(hits)` | `int` — 0–100 with the critical floor at 82 |
| `entities.assess(text, trusted=None)` | `list[Entity]` — link/mailbox/number judgement (`assess_with_trust(text)` pulls the trusted set from the store) |
| `learning.record_verdict(text, result)` | `int \| None` — row id, or `None` when learning is off |
| `learning.update_verdict(id, result)` | `bool` — refine a scan in place |
| `learning.record_feedback(verdict_id, predicted, actual, rule_keys, note)` | `list[dict]` — rules whose weight moved |
| `learning.similar_cases(text)` | `list[SimilarCase]` — near-duplicates by simhash |
| `learning.store_health()` | `{ok, path, error}` |
| `ocr.extract(image_bytes)` | `OCRResult(text, engine, lines, duration_ms, warnings, mean_confidence)` |
| `report.build_report(result, message)` | `str` — Markdown safety report |
| `pdf.build_verdict_pdf(result, message="")` | `bytes` — a one-page A4 PDF (verdict, quoted flags, actions, reporting contacts). `message` is accepted for signature symmetry and deliberately not drawn |
| `pdf.verdict_pdf_filename(result)` | `str` — `scamshield-<level>-<yyyymmdd-hhmm>.pdf` |
| `pdf.build_whatsapp_text(result)` | `str` — plain-text caption to paste alongside the PDF |
| `pdf.sanitize(text)` | `str` — folds text to Latin-1 for the built-in PDF fonts |

Errors: `engine.EngineError` (model unreachable/unusable) and `ocr.OCRError` (image unreadable).
Both are caught by the UI and shown as a readable message.

## 2. CLI contract

```
python -m scamshield.cli [text] [--sample KEY] [--file PATH] [--model NAME] [--no-ai] [--json] [--list-samples]
```

| Flag | Effect |
|---|---|
| `text` | Message to analyse (positional) |
| `--sample KEY` | One of `dubai_hotel`, `saudi_visa`, `task_scam`, `legit_offer`, `borderline` |
| `--file PATH` | Read the message from a file (UTF-8) |
| `--model NAME` | Force a local model; default is the first installed preference (`gemma4:e2b`) |
| `--no-ai` | Rules engine only — fast, deterministic, no model call |
| `--json` | Emit the raw result instead of the human report |
| `--list-samples` | Print the demo corpus with expected bands |

Exit code is `0` on success. Stdout is reconfigured to UTF-8 on Windows so the report's arrows and
quotes print correctly. Footer line for scripting: `engine=<rules|ollama> model=<name>
latency=<ms> rules=<n>`.

## 3. Ollama contract (outbound)

ScamShield is a client of the local Ollama server. These are the only calls it makes.

### `GET /api/tags`

Lists installed models for the sidebar dropdown. Any failure returns `[]` (the app continues).

### `GET /api/version`

Used by `engine_online()` for the status pill.

### `POST /api/chat` — the verdict call

```json
{
  "model": "gemma4:e2b",
  "messages": [{"role": "system", "content": "<runtime brief>"},
               {"role": "user", "content": "<candidate evidence + message>"}],
  "stream": true,
  "format": "json",
  "keep_alive": "30m",
  "think": false,
  "options": {"temperature": 0.1, "top_p": 0.9, "repeat_penalty": 1.05,
              "num_ctx": 3072, "num_predict": 700}
}
```

- `"think": false` is required for reasoning models (Gemma 4 E2B). Without it the model spends its
  token budget in the `message.thinking` field and `content` arrives empty.
- `"stream": true` lets the client stop generation at the balanced closing brace instead of
  waiting for `num_predict`.
- Timeout: 5 s to connect, 300 s to answer.

### Response contract the model must satisfy

```json
{
  "verdict": "scam", "risk_level": "HIGH", "risk_score": 92,
  "category": "advance_fee_visa_fraud",
  "headline": "Visa-fee scam. Do not pay.",
  "summary": "…under 45 words…",
  "red_flags": [{"code": "upfront_payment", "title": "…", "evidence": "<verbatim quote>",
                 "why_it_matters": "…", "severity": "critical"}],
  "positive_signals": [],
  "recommended_actions": ["…"], "questions_to_ask": ["…"], "confidence": "high"
}
```

Allowed `red_flags[].code` values — anything else is discarded:

```
upfront_payment            personal_payment_channel   guaranteed_visa
identity_harvesting        daily_pay_task_scam        domain_mismatch
unrealistic_pay            unofficial_channel         process_inversion
urgency                    vague_employer             mass_mailing
```

Rejection rules applied to every returned flag: unknown code, code the rules already proved,
critical code without rule support, `evidence` that is not a quote from the message, or a payment
claim contradicted by a "no fee" sentence. Rejected flags are counted and shown to the user as
`N unverified model claim(s) discarded`.

### `POST /api/generate`

A one-token warm-up (`num_predict: 1`, `keep_alive: "30m"`) so the first real analysis is not
paying the model load cost. Failure is ignored.

## 4. Failure modes

| Situation | Contract |
|---|---|
| Ollama not installed / not running | `engine_online()` false → UI states it; verdict is rules-only with an `error` note |
| Model missing | Sidebar hints `ollama pull gemma4:e2b`; rules-only verdict |
| Model times out | `EngineError("Local model timed out…")` → rules-only result |
| Empty / unparseable answer | `EngineError("Ollama returned an empty response.")` → rules-only result |
| Learning store unwritable | `store_health()` reports the path and error; scans still verdict correctly |
| OCR engine missing | `ocr.extract` raises `OCRError` with an install hint |
| Oversized image | Rejected before decoding (> 12 MB) with a readable message |
