# GOTCHAS — hard-learned lessons

Every entry below is a bug that actually happened in this repo, with the cause and the fix that
stuck. Read this before "improving" the engine, the prompt, the OCR pipeline or the UI — several of
these look like obvious simplifications until you know why they exist.

---

## Model / prompt

**1. Gemma 4 returns an empty response (and looks like a timeout).**
Gemma 4 is a reasoning model: it streams its chain of thought into `message.thinking` and only
then emits `message.content`. With a CPU-sized token budget the reasoning consumed everything, so
the client saw no answer and raised *"Ollama returned an empty response"* after 180 s.
→ Always send `"think": false` on `/api/chat`, and salvage JSON from `thinking` if `content` is
still empty. Do not remove this to "let the model reason" — it doubles latency and breaks parsing.

**2. The model invents a fee in a letter that says "no fee".**
The 1B model we started on flagged a genuine Systems Limited offer as a payment scam.
→ `NO_FEE_RE` polarity check plus quote verification. Any change to verification must keep
`test_invented_payment_flag_is_discarded` green.

**3. Model output drifts from the schema (wrong codes, duplicated titles).**
→ Rules own the flags for every family they matched; the model may only add *new* families, and
critical families must be rule-proven. Do not "trust the model more" on a bigger model — the
guardrail also protects against prompt injection inside the message.

**4. Generation ran past a valid JSON object and got cut off mid-field.**
→ Stream and stop at the balanced closing brace (`_brace_delta`), then salvage complete fields.
Braces inside strings must be ignored, which is what the string/escape state tracks.

**5. A 2,524-token playbook made every call take four minutes.**
→ The model receives only the `runtime:` block (~320 words). The full SKILL.md stays for humans.
Editing outside that block does not change behaviour — and people assume it does.

## Rules

**6. "Bring your CNIC to the interview" was flagged as identity harvesting.**
Normal in Pakistan; the rule treated any CNIC mention as document harvesting.
→ The rule now requires a *send/share/upload* verb near the document. Mere mention is not a hit.
Guarded by `test_bringing_cnic_to_interview_is_not_harvesting`.

**7. OCR worked but the rules stopped firing.**
RapidOCR on a ~900 px image returned `SendfeeonJazzCash` — spaces collapsed, so word-boundary
regexes silently missed. → Upscale to a minimum width of 1600 px before recognition
(`ocr.MIN_WIDTH`). Measured: 900 px collapses, 1600 px keeps spacing.

## Storage

**8. Tests failed deleting temp databases on Windows.**
Open SQLite handles block file removal. → `_session()` context manager commits and closes in
`finally`. Never hold a module-level connection.

**9. Correcting the same verdict twice inflated the rule statistics.**
`ON CONFLICT` updated the feedback row but added the counters again.
→ `record_feedback()` first reverses the previous label's contribution, then applies the new one.

**10. "Messages checked" stayed at 0 during a 90-second AI run.**
The scan was recorded only after the model answered, so the UI looked frozen.
→ Record the rules verdict immediately, then `update_verdict()` the same row. One scan = one row.
Do not move recording back to the end of the pipeline.

**11. Choosing "Enable learning" silently ended up off.**
The Learning tab's toggle kept its own session value and re-persisted `False` on the next rerun,
overwriting the stored consent.
→ Widgets that mirror persisted state must write only in an `on_change` callback, and re-sync when
the stored value changes (`consent_snapshot`).

## UI / Streamlit

**12. Streamlit's dark palette painted a white wedge behind the model dropdown.**
The base theme coloured the `role="group"` container, not the select itself.
→ Container-level override in `ui.py`. Inline code chips in captions had the same problem.

**13. Risk badges rendered dark instead of red.**
A global `.stMarkdown span` colour rule outranked the component classes.
→ Keep global selectors structural; colour belongs to the `ss-` components.

**14. `AttributeError` in `dataclasses` while editing files.**
Streamlit's hot reload re-imported modules mid-save.
→ `runOnSave = false` in `.streamlit/config.toml`; refresh instead of expecting live reload.

**15. "Port 8501 is not available" on a fresh start.**
A stale Streamlit process still held the port. → The launcher records `{port, pid, url}` in
`data/launcher.json`, reuses a healthy server, and `--restart` stops the recorded one first.
Killing by name pattern is unsafe here: the agent's own command line can match it.

**16. Screenshots came out dimmed or mid-animation.**
Streamlit dims the page during a rerun, and theme changes reload the page (losing the result).
→ `tools/shoot_ui.py` waits for `stStatusWidget` to disappear, re-runs the analysis after a theme
switch, and uses a taller viewport for the verdict shots.

## Platform

**17. CLI crashed printing results on Windows.**
The console is cp1252 and the report contains `→` and curly quotes.
→ `sys.stdout.reconfigure(encoding="utf-8")` at CLI start. The same class of problem appears when
reading files: always pass `encoding="utf-8"` explicitly.

**18. The desktop shortcut broke after moving Python or `.venv`.**
The `.lnk` stores the interpreter path resolved at setup time.
→ Re-run `setup_desktop.bat`. Documented, not "fixed": resolving it at click time would need a
wrapper script.

## Process

**19. A "dataset" of five hand-written messages cannot support accuracy claims.**
It is a regression corpus for the rules, nothing more.
→ Never quote precision/recall from it. §11.4 of the project report states this openly; keep it
that way until real, labelled messages exist.

**20. Competitor claims must carry a date and a source.**
The Compare tab cites each vendor's documentation (checked 30 October 2026). If you add a row you
cannot source, write "Not documented" rather than guessing — judges do ask.
→ The first audit of this table found four wrong claims: Scamio was marked "free, unlimited" when
its terms cap it at **5 checks/day** and require an account; Truecaller was marked "account
required" and "no offline" when its Scam Checker needs no account and its Message ID runs
on-device; ScamAdviser was marked "no phone lookup" when reverse lookup is a shipped feature. Always
read the vendor's **terms and FAQ**, not just the marketing page, and never attribute a capability
from a vendor's *other* product (Scamio was being credited with Bitdefender's Link Checker).
