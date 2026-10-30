# Conventions

Rules observed by the existing code. Match them; do not introduce a second style.

---

## 1. Python

| Area | Rule |
|---|---|
| Version | Python 3.14 (developed and tested on it) |
| Future import | Every module starts with `from __future__ import annotations` |
| Typing | Full annotations on public functions; `X \| None` unions, no `Optional` |
| Data shapes | `@dataclass` for value objects (`Analysis`, `Flag`, `Rule`, `Hit`, `Entity`, `Sample`) |
| Naming | `snake_case` functions/variables, `PascalCase` classes, `UPPER_SNAKE` module constants |
| Private helpers | Leading underscore: `_rules_only`, `_build_messages`, `_extract_json`, `_session` |
| Strings | Double quotes; f-strings for anything with a value in it |
| Line length | ~100 characters, wrapping arguments rather than abbreviating names |
| Docstrings | Module docstring explains *why the module exists*; function docstrings state the contract and the failure mode |
| Comments | Explain a non-obvious decision, not the syntax. Numeric thresholds always carry their reason |
| Imports | Standard library, then third party, then local — separated by blank lines |

```python
"""What this module is for and why it exists."""

from __future__ import annotations

import time
from dataclasses import dataclass

# Threshold kept at 8 because a tighter distance produced false "seen before" matches.
DEFAULT_SIMILARITY_DISTANCE = 8


def every_hit_is_discarded(hits) -> bool:
    """Return True when nothing survives verification. Never raises."""
```

## 2. Rules and detection patterns

- A rule **must quote the message verbatim**. No quote, no flag — there is no exception.
- Rule `key` values are `snake_case` and stable: they are stored in the database and referenced by
  the SKILL.md prompt. Renaming one is a data migration, not a refactor.
- Severity is one of `critical`, `high`, `medium`, `low`; weights are integers; the critical floor
  lives in `rule_score()`, not in individual rules.
- Never flag a payment demand in a message that explicitly says no fee is required (the
  `NO_FEE_RE` polarity check exists for exactly that).
- Rules match on word boundaries, so nothing may collapse spaces before matching (see GOTCHAS).

## 3. Errors and degradation

| Situation | Convention |
|---|---|
| Model unreachable / unusable | Raise `EngineError`, catch it in `analyze()`, return a rules-only `Analysis` |
| OCR unusable | Raise `OCRError` with an install hint |
| Storage failure | Return `None`/`False` **and** expose the reason through `store_health()`; never a silent zero |
| Optional dependency missing | Degrade with a readable message, never a traceback in the UI |
| Test-only seams | Environment variables (`SCAMSHIELD_DB`), not monkeypatching internals |

Never swallow an error without either handling it or surfacing it to the user.

## 4. Tests

- `unittest`, standard library only. No pytest, no fixtures frameworks.
- Files: `tests/test_<area>.py`; classes `XTests`; methods `test_<behaviour>_<expectation>`.
- Every test that touches storage sets `SCAMSHIELD_DB` to a temp file and restores it in
  `tearDown`, so tests never see the developer's real history.
- Learning tests must call `learning.set_consent(True)` first — nothing is written without consent.
- Tests must not hit the network or require Ollama. The AI path is exercised with `use_ai=False`
  plus targeted guardrail tests.
- Run: `python -m unittest discover -s tests -v` (47 tests, must stay green).

## 5. UI

- Copy is sentence case; the product never accuses a company of a crime — it describes behaviour.
- Every claim shown to the user is either a verbatim quote or a stated structural observation.
- Style hooks are `ss-` prefixed classes (`ss-verdict`, `ss-pill`, `ss-mono`); theme colours come
  from CSS variables so the light and dark palettes stay in step.
- Any new panel needs both themes checked and the accessibility label kept (`aria-label` on the
  score ring is an example).
- New user-visible behaviour gets a line in the README, and a section in
  `docs/PROJECT-REPORT.md` when it changes the architecture or the guarantees.

## 6. Files and layout

- Source in `scamshield/`; the Streamlit entry point stays `app.py` at the root.
- Build/dev tooling in `tools/`; generated artefacts in `assets/`, `docs/`, `screenshots/`.
- `data/` is runtime state (DB, launcher pid/port, logs) and is never committed as source.
- The single source of truth for the machine-readable prompt is `skills/job-scam-detector/SKILL.md`;
  the `<!-- runtime:start -->…<!-- runtime:end -->` block is what the model actually receives.

## 7. Commits

- Imperative, specific subject line; body explains the *why* and the evidence.
- One logical change per commit. Do not commit `data/*.db`, screenshots unrelated to the change,
  or the installed model files.

## 8. Dependencies

- Standard library first. Add a package only when it replaces real work, and record the decision in
  §7 of the project report (including what was explicitly rejected, and why).
- Runtime deps live in `requirements.txt`. Tooling-only packages (Playwright, PyMuPDF for the PDF
  builder) are dev dependencies and must not be added to runtime requirements.
