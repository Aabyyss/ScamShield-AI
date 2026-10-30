# Architecture

ScamShield AI is a **single-process desktop app**. Streamlit serves the UI on loopback, the
detection engine runs in the same Python process, and the only other process involved is a local
Ollama server that supplies the language model. No request ever leaves the machine.

For the design rationale, the full feature catalogue and the measured numbers, see
[docs/PROJECT-REPORT.md](docs/PROJECT-REPORT.md). This file is the structural blueprint.

---

## 1. Layers

```
              ┌─────────────────────────────────────────────┐
 screenshot ─►│ app.py — Streamlit UI (5 tabs, dialogs)     │
              │  input → analyse → render → feedback → export│
 pasted text ►│                                             │
              └───────────────────┬─────────────────────────┘
                                  │ engine.analyze()
              ┌───────────────────▼─────────────────────────┐
              │ scamshield/engine.py — orchestration        │
              │  1. rules.prescan()        12 fraud families│
              │  2. learning.apply_to_hits()  weights/phrases│
              │  3. entities.assess()      links, mail, IDs │
              │  4. Ollama / Gemma 4       explanation       │
              │  5. verification           quotes + severity │
              │  6. scoring                deterministic     │
              └──────┬───────────────┬──────────────────────┘
                     │               │
        learning.py (SQLite)   report.py (Markdown)   cli.py (terminal)
```

The application is split so that the **verdict never depends on the model**. Scoring is
deterministic (rules + entities); the model may only *explain* and add non-critical families that
pass quote verification.

## 2. Folder structure

```
app.py                     Streamlit UI: tabs, dialogs, theme, rendering
launcher.py                one-click launcher: deps, Ollama wake-up, port, browser
ScamShield.bat             double-click entry for Windows
setup_desktop.bat          creates the Desktop shortcut for a collaborator
launch.sh                  macOS/Linux launcher
scamshield/
  __init__.py              public API surface (analyze, Analysis, Flag, pick_model …)
  engine.py                Ollama client, JSON contract, guardrails, merge, scoring, fallback
  rules.py                 Rule dataclass, 12 families, prescan(), rule_score()
  entities.py              link / mailbox / phone / ID extraction and structural judgement
  learning.py              SQLite store, consent, Beta-smoothed weights, phrases, trust
  ocr.py                   RapidOCR (ONNX) screenshot reading, Tesseract fallback
  report.py                Markdown safety report builder
  cli.py                   terminal interface (--sample, --json, --no-ai …)
  ui.py                    CSS theme, HTML components, result card
  samples.py               5-message demo corpus with expected verdicts
skills/job-scam-detector/
  SKILL.md                 the Agent Skill: full playbook + compact `runtime:` brief
tests/                     47 unittest tests (rules, entities, learning, OCR, report)
tools/                     build_pdf.py, shoot_ui.py, make_logo.py, create_shortcut.ps1
assets/                    logo.png, icon.ico, logo-192.png
data/                      local runtime state (DB, launcher.json, logs) — not source
docs/                      PROJECT-REPORT.md and the generated PDF
screenshots/               images used by the README and the report
```

`data/` and `__pycache__/` are runtime artefacts, not shippable code.

## 3. Request lifecycle

1. The UI calls `engine.analyze(message, use_ai=False)` — a rules-only pass that returns in
   milliseconds (measured ~7 ms via the CLI).
2. `learning.record_verdict()` stores the scan immediately, so the "messages checked" counter
   moves before the model answers. The row id is kept.
3. The result renders from `Analysis`: risk band, score ring, quoted flags, entity findings,
   recommended actions, questions to ask.
4. If the AI layer is enabled and Ollama answers, `engine.analyze(..., use_ai=True)` runs:
   `_build_messages()` sends a compact runtime brief plus the deterministic hits as *candidate
   evidence*, and the streamed JSON is validated field by field.
5. The model-backed result replaces the provisional one, `learning.update_verdict()` refines the
   same row (one scan = one row), and the UI reruns with the final verdict.
6. The user may correct the verdict (`record_feedback()` moves bounded rule weights), download the
   Markdown report, or start another message.

If Ollama is missing, slow or returns unusable JSON, `_rules_only()` produces the same shaped
`Analysis` with an explicit `error` note. The product never blocks on the model.

## 4. Module contracts

| Module | Owns | Must not |
|---|---|---|
| `engine.py` | Orchestration, model I/O, verification, scoring, `Analysis`/`Flag` types | Contain detection patterns (those live in `rules.py`) |
| `rules.py` | Regex families, weights, severity, `prescan()`, `rule_score()` floors | Call the network or the model |
| `entities.py` | Structural judgement of links/mailboxes/numbers/IDs | Decide the overall verdict |
| `learning.py` | Local persistence, consent, weight multipliers, taught phrases | Retrain a model or talk to a server |
| `ocr.py` | Image → text, with confidence and warnings | Analyse the text |
| `report.py` | Markdown export from an `Analysis` | Read the DB or the UI |
| `ui.py` | CSS + HTML fragments for the Streamlit layer | Contain business logic |
| `cli.py` | Terminal entry point | Reimplement the engine |

## 5. Trust boundaries

```
user input ──► OCR ──► rules/entities (deterministic, trusted) ──► score
                    └► model output (untrusted) ──► verification ──► explanation only
```

The model's answer is treated as untrusted text: unknown flag codes, unverifiable quotes,
critical families without rule support, and payment claims contradicted by a "no fee" sentence are
all discarded and counted (`discarded claims` in the result footer).

## 6. Scoring

| Rule | Value |
|---|---|
| Sum of fired rule weights | 0–100, capped |
| Any `critical` severity hit | floor of **82** |
| Three or more hits, none critical | floor of **45** |
| Bands | HIGH ≥ 65 · MEDIUM ≥ 30 · LOW < 30 |
| Model contribution | at most +15 points, never lowers a rule verdict |

## 7. Deployment model

- One machine, one user, `127.0.0.1` only. No authentication, no hosting, no multi-tenancy.
- Ollama is optional; without it the app is fully functional with rules + entities.
- The launcher starts Streamlit detached, waits for `/healthz`, then opens the browser and records
  `{port, pid, url}` in `data/launcher.json` so a second launch reuses the running server.
- Rebuilding the PDF: `python tools/build_pdf.py`. Re-capturing screenshots:
  `python tools/shoot_ui.py` (needs a server on 8501 and the Playwright dev dependency).

## 8. Extension points

| Want to | Change |
|---|---|
| Add a fraud family | `rules.py` (`RULES`), then the matching code in the SKILL.md flag list |
| Change the model | sidebar dropdown, `SCAMSHIELD_MODEL`, or `DEFAULT_MODEL` in `engine.py` |
| Change the prompt | `skills/job-scam-detector/SKILL.md` (`runtime:` block is what the model sees) |
| Add a stored fact | `learning.py` schema + a test in `tests/test_learning.py` |
| Add a UI panel | `app.py` (tab) + `ui.py` (component + CSS) |
