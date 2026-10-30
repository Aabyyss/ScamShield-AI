# CLAUDE.md — how to work in this repository

ScamShield AI: an offline job-scam detector for Pakistan's job seekers. Streamlit UI, deterministic
rules, local Gemma 4 via Ollama, SQLite learning store, on-device OCR. Built for the Agent Skills
hackathon (*Best use of Gemma 4*).

**Read in this order before changing anything:** this file → [TODO.md](TODO.md) →
[GOTCHAS.md](GOTCHAS.md) → [ARCHITECTURE.md](ARCHITECTURE.md). Check [DATABASE.md](DATABASE.md)
before touching persistence and [CONVENTIONS.md](CONVENTIONS.md) before writing code.

---

## Non-negotiable invariants

1. **Nothing leaves the laptop.** No cloud model, no telemetry, no font/CDN fetches. The only
   network call is `OLLAMA_HOST` (loopback). Turning off Wi-Fi must keep every feature working.
2. **Rules decide, the model explains.** Scoring is deterministic. The model may add only
   non-critical families that pass quote verification, worth at most +15 points, and can never
   lower a rule verdict. Do not move scoring into the prompt.
3. **Every flag quotes the message verbatim.** No quote → no flag. Do not relax
   `_quote_verified`, `NO_FEE_RE` or the taxonomy allowlist to make output look richer.
4. **Consent before storage.** `learning.record_verdict()` writes only when
   `learning_enabled()` is true. Never write to the DB from a new code path that bypasses it.
5. **No silent zeros.** A failed write must reach the user (see `store_health()`), not render as 0.
6. **Never claim accuracy from the 5-message demo corpus.** It is a regression suite. Precision and
   recall require the corpus described in TODO.md.

## Commands

```bash
python -m unittest discover -s tests -v     # 55 tests, keep them green
python -m scamshield.cli --sample dubai_hotel --no-ai     # fast deterministic check
python -m scamshield.cli --sample legit_offer --model gemma4:e2b   # real AI path (60-130 s)
python launcher.py                          # app on 127.0.0.1:8501, reuses a running server
python launcher.py --restart                # stop the recorded server, start again
python tools/build_pdf.py                   # rebuild docs/ScamShield-AI-Project-Report.pdf
python tools/shoot_ui.py                    # re-capture screenshots (server must be running)
```

Model: `gemma4:e2b` by default (installed with `ollama pull gemma4:e2b`). Selection order lives in
`engine.PREFERRED_MODELS` / `engine.DEFAULT_MODEL`.

## Where things live

| Task | File |
|---|---|
| UI, tabs, dialogs, analyse flow | `app.py`, `scamshield/ui.py` |
| Detection rules and scoring | `scamshield/rules.py` |
| Model call, guardrails, merge | `scamshield/engine.py` |
| Prompt the model actually sees | `skills/job-scam-detector/SKILL.md` (`runtime:` block) |
| Persistence, consent, weights | `scamshield/learning.py` |
| Link/mailbox/number judgement | `scamshield/entities.py` |
| Screenshot → text | `scamshield/ocr.py` |
| Report export | `scamshield/report.py` |
| Launcher / shortcut | `launcher.py`, `setup_desktop.bat`, `tools/create_shortcut.ps1` |
| Tests | `tests/test_{rules,entities,learning,ocr}.py` |

## Working rules specific to this repo

- **Windows-first.** Bash syntax in tooling, but the app targets Windows: UTF-8 everywhere
  (`encoding="utf-8"` on file reads, `sys.stdout.reconfigure` in the CLI), and SQLite connections
  always closed (open handles block file deletion).
- **Streamlit state.** Widgets that mirror persisted values must write through `on_change` and
  re-sync when the stored value changes — see GOTCHAS #11. `runOnSave` is off; refresh, don't
  expect hot reload.
- **Port hygiene.** Reuse the server recorded in `data/launcher.json`; never kill by process-name
  pattern (the agent's own command line can match). `launcher.py --restart` is the supported path.
- **Tests must not need the network or Ollama.** Use `use_ai=False`; set `SCAMSHIELD_DB` to a temp
  file; call `learning.set_consent(True)` in `setUp` when a test writes.
- **Do not commit** `data/*.db`, `__pycache__/`, or any downloaded model files.
- **Dependencies:** standard library first; record a new package's rationale in §7 of the project
  report. Tooling-only packages (Playwright, PyMuPDF) stay out of `requirements.txt`.

## Definition of done

- [ ] `python -m unittest discover -s tests` passes (add a test for new behaviour; never weaken an
      existing assertion to make it pass)
- [ ] The behaviour verified in the running app, not only in a unit test, when it is user-visible
- [ ] `README.md` updated for user-visible changes; `docs/PROJECT-REPORT.md` updated when the
      architecture, guarantees or measured numbers change; PDF rebuilt if the report changed
- [ ] `GOTCHAS.md` gains an entry for any non-obvious bug fixed
- [ ] `TODO.md` reflecting the new state
- [ ] No claim in docs that the code or a measurement does not support

## Tone in user-facing copy

Calm, specific, non-accusatory. Describe behaviour ("the domain does not match the company's
official site"), never declare a company criminal. Name the next safe step. The user is a job
seeker who may have just lost money — no blame, no alarmism.
