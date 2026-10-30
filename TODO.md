# TODO

Source of truth for progress. Update this file when work lands — it is what stops the next person
(or agent) from re-doing finished work or re-opening settled decisions.

**Status:** working end to end · 55 tests passing · submitted for the Agent Skills hackathon
(*Best use of Gemma 4*). Last updated: 30 October 2026.

---

## Done

### Detection engine
- [x] 12 rule families with quoted evidence, severity and weights (`rules.py`)
- [x] Deterministic scoring: critical floor 82, ≥3-hit floor 45, bands 65 / 30
- [x] Entity layer: links, mailboxes, phone numbers, CNIC/passport, look-alike domains
- [x] Guardrails: quote verification, taxonomy allowlist, critical-family certification,
      no-fee polarity check, model cannot lower a verdict
- [x] Instant rules-first verdict, AI reasoning layered on top, rules-only fallback

### Local model
- [x] Ollama client with streaming + stop-at-closing-brace (`engine.py`)
- [x] Gemma 4 E2B as the default model; `think: false` for reasoning models
- [x] `SKILL.md` Agent Skill with a compact `runtime:` brief (~320 words)
- [x] Model warm-up, 30-minute keep-alive, model picker in the sidebar

### Self-learning (consented, on-device)
- [x] SQLite store: verdicts, feedback, rule stats, phrases, trusted domains, settings
- [x] Beta(2,2)-smoothed rule weights, bounded ×0.55–×1.45, min 3 labels
- [x] Explicit consent dialog; nothing stored until answered; reversible in the Learning tab
- [x] Scan recorded at the rules phase, refined by `update_verdict()` — one row per scan
- [x] Store health surfaced instead of a silent zero; full reset and history clear

### Interface
- [x] Light + dark themes, logo, hero, three-step onboarding
- [x] Verdict card: score ring, quoted flags with attribution (RULE / RULE + AI), actions, questions
- [x] Five tabs: Check a message · How it works · Learning · Compare · Agent Skill
- [x] Markdown safety report export; feedback form ("this verdict is wrong")
- [x] One-page PDF verdict (`pdf.py`, hand-written writer, no new dependency) plus a
      paste-ready WhatsApp caption

### Screenshot input
- [x] RapidOCR (ONNX) in-process, 1600 px upscale, EXIF rotation, 12 MB cap
- [x] Editable transcription before analysis; confidence + warnings shown

### Packaging and docs
- [x] One-click launcher, desktop shortcut for collaborators, logo/icon generation
- [x] README, project report (`docs/`) and the generated PDF
- [x] Project docs: ARCHITECTURE, DATABASE, API_SPEC, CONVENTIONS, GOTCHAS, TODO, .env.example
- [x] 55 tests: rules, entities, learning, OCR, report, PDF
- [x] Compare tab re-verified against each vendor's own pages (30 Oct 2026): Scamio is capped at
      5 checks/day behind an account, Truecaller needs no account and has on-device Message ID,
      ScamAdviser takes links and numbers rather than text

---

## In progress

- [ ] **Rehearse the demo flow** with Wi-Fi off: scam sample → quoted flags → genuine offer → LOW.

---

## Backlog (ordered by value)

### Detection quality
- [ ] Roman-Urdu patterns (`paisay bhejain`, `visa guarantee`, `ghar baithe kamai`)
- [ ] Urdu script + handwritten OCR — currently printed Latin only
- [ ] Local reputation cache built from messages already judged (labelled as cached, never "live")
- [ ] Expand the brand look-alike list beyond the current 14 companies

### Evaluation (the honest gap)
- [ ] Build a consented, anonymised corpus of **200+** real messages — the current 5-message demo
      corpus is a regression suite, not an evaluation set
- [ ] Two independent annotators + a held-out split; report precision/recall **per band**, plus the
      false-positive rate on legitimate offers
- [ ] Separate channel eval (WhatsApp vs email) and a real-screenshot OCR word-error rate

### Product
- [ ] Batch mode: paste several messages, get a triage list
- [ ] Optional "explain like I'm new to job hunting" wording level
- [ ] Rich-text paste that keeps the sender address / link context

### Engineering
- [ ] `tools/requirements-dev.txt` for Playwright + PyMuPDF used by the PDF/screenshot tools
- [ ] Package the app as a signed Windows build (removes the Python prerequisite and SmartScreen
      warning)
- [ ] UI smoke tests (Playwright is already wired into `tools/shoot_ui.py`)
- [ ] Encrypted local store (SQLCipher) if the threat model ever widens beyond one user

---

## Explicitly not planned

| Idea | Why not |
|---|---|
| Cloud LLM API | Breaks the offline privacy guarantee that is the whole pitch |
| Reading WhatsApp data directly | Would need invasive permissions; the app only sees what the user pastes |
| Automatic blocking / reporting on the user's behalf | False positives would harm real employers; the user decides |
| Server-side accounts and shared learning | Out of scope for a single-user desktop tool; raises consent and privacy questions |
