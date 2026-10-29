# 🛡️ ScamShield AI

**Paste a job offer. Know if it's a scam — before you send a single rupee.**

ScamShield is an offline AI agent that reads suspicious job messages (WhatsApp forwards,
recruiter DMs, hiring emails) and returns a risk verdict with the exact red flags quoted from
the message. It runs entirely on your laptop: the model is local, the only socket it opens is
`127.0.0.1:11434`, and it keeps working with Wi-Fi switched off.

> Every day, students in Pakistan lose their savings to fake overseas job offers on WhatsApp.
> Most can't tell an offer is fake until the money is gone — and they won't paste a message
> containing their name, CNIC and bank details into a cloud chatbot. ScamShield reads it
> without it ever leaving the machine.

---

## Why this is different from "asking ChatGPT"

| | Cloud chatbot | ScamShield AI |
|---|---|---|
| Message contents | Uploaded, may be retained | Never leave the device |
| Works with Wi-Fi off | No | Yes |
| Consistent judgement | Depends on the prompt you type | Fixed Agent Skill + versioned scoring |
| Evidence | Prose you have to trust | Quoted snippets + rule weights |
| False-negative guard | None | Critical signals can't be argued away by the model |

---

## Quickstart

```bash
# 1. Local model runtime (once)
#    https://ollama.com/download  →  then:
ollama pull gemma3:1b        # ~815 MB, fast on CPU
# or: ollama pull llama3.2   # better judgement, slower on CPU

# 2. App
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 3. Run
streamlit run app.py
```

The sidebar shows whether Ollama is reachable and which models are installed. If the model
isn't running, the app still gives a verdict from the rules engine and says so plainly.

### Command line (useful while building the skill)

```bash
python -m scamshield.cli --list-samples
python -m scamshield.cli --sample dubai_hotel
python -m scamshield.cli --sample legit_offer --json
python -m scamshield.cli "paste any message here" --no-ai
```

---

## How it works

```
                 ┌──────────────────────────────────────────────┐
   pasted text → │ 1. RULES ENGINE  (scamshield/rules.py)       │
                 │    12 fraud patterns, each hit keeps the      │
                 │    exact quote + severity + weight            │
                 └───────────────────┬──────────────────────────┘
                                     │ evidence pack
                 ┌───────────────────▼──────────────────────────┐
                 │ 2. AGENT SKILL  (skills/…/SKILL.md)          │
                 │    Gemma via local Ollama, JSON-only output   │
                 └───────────────────┬──────────────────────────┘
                                     │ verdict + flags + advice
                 ┌───────────────────▼──────────────────────────┐
                 │ 3. VERIFY & SCORE  (scamshield/engine.py)    │
                 │    every model flag needs a quote in the text │
                 │    rules own the flags + severity + score     │
                 └──────────────────────────────────────────────┘
```

**Why both layers.** Rules alone are brittle ("CNIC" isn't always fraud). A model alone can be
talked out of a verdict by a polite scammer — or, at 1B parameters, invent one. Together: the
rules assign the score and the model explains it.

### Guardrails against a small model

A tiny local model is not a frontier model, so the architecture assumes it will sometimes be
wrong. Four checks run before any model output reaches the screen:

1. **Taxonomy or nothing.** Each flag must carry a `code` from the twelve-family taxonomy. Free-form
   accusations are discarded.
2. **Quote or nothing.** The `evidence` must be found in the message (exact match, or ≥75% token
   overlap after normalisation). A hallucinated quote kills the flag.
3. **No invented payment.** A payment claim is discarded when its own quote denies payment
   ("no payment or fee of any kind is required") — the failure mode we hit while building this.
4. **Rules certify severity.** A `critical`/`high` claim is downgraded to `medium` unless the rules
   engine independently matched the same family, and model findings add at most 15 points to the
   deterministic score. A lone model opinion can never reach HIGH.

Every discarded claim is counted and shown in the result footer — useful on stage, and honest.

### The Agent Skill

[`skills/job-scam-detector/SKILL.md`](skills/job-scam-detector/SKILL.md) is the brain: a
fraud-investigator playbook with a red-flag taxonomy, a scoring rubric, an output contract
(JSON schema), and hard rules like *"every flag must quote the message"*. It is loaded at
runtime and injected as the system prompt — edit the file, restart, and the agent's behaviour
changes without touching Python.

### Risk scoring

| Band | Score | Meaning |
|---|---|---|
| 🔴 HIGH | 65–100 | Matches a known scam pattern. Do not pay, do not send documents. |
| 🟠 MEDIUM | 30–64 | Unverified. Check the employer before replying. |
| 🟢 LOW | 0–29 | No scam pattern found. Still verify independently. |

A single **critical** family (upfront fee, private wallet, guaranteed visa, document request)
floors the score at 82 — by design, one decisive signal beats five weak ones. The score itself is
deterministic: rule weights, plus at most 5 points per verified model finding (capped at 15).

---

## Demo script (3 minutes, on stage)

1. **Frame it.** "Job scams target students who can't afford to lose Rs 35,000. Victims won't
   paste these messages into ChatGPT, because the message contains their CNIC. So we made the
   AI come to them."
2. **The instant layer.** Paste the Dubai hotel message (sidebar → *Dubai hotel job*). Hit
   **Analyse**. The rules verdict and quoted red flags appear in under a second.
3. **The reasoning layer.** While the local model finishes, point at the sidebar: `Ollama
   connected · 127.0.0.1 only`. The summary, advice and "ask them this" questions fill in.
4. **The proof.** Turn off Wi-Fi (or unplug the LAN cable) *live*. Run the Saudi Aramco message
   again. Same verdict, zero network. "Nothing was ever sent anywhere — that's why this is safe
   to use on a message with your passport number in it."
5. **The honest test.** Run the legitimate Systems Limited offer: it comes back **LOW** with
   positive signals. "A detector that flags everything protects no one."
6. **Close.** "Every rule and every prompt is in the repo. A telecom, a university or NADRA
   could ship this to millions of users without a single rupee of inference cost."

### Demo corpus

| Sample | Expected | What it exercises |
|---|---|---|
| `dubai_hotel` | **HIGH** | visa fee, JazzCash, guaranteed visa, urgency, Gmail HR |
| `saudi_visa` | **HIGH** | passport/CNIC/bank statement harvest, "company name later" |
| `task_scam` | **HIGH** | daily-pay task scam, Telegram funnel, refundable registration fee |
| `legit_offer` | **LOW** | real offer letter: interview panel, official domain, "no fee at any stage" |
| `borderline` | **MEDIUM** | small local employer, Gmail, "no experience needed" — suspicious, not fraud |

`python -m scamshield.cli --list-samples` prints them; every sample's expected band is asserted
in [`tests/test_rules.py`](tests/test_rules.py) — run `python -m unittest discover -s tests -v`.

---

## Performance on a CPU-only laptop

Measured on this machine (no GPU, Ollama 0.40, Python 3.14, 8 threads):

| Path | Time | Notes |
|---|---|---|
| Rules engine only | **< 0.1 s** | Rendered immediately in the UI |
| `gemma3:1b` full verdict | **~65–95 s** | Recommended demo model; ~320-word runtime brief |
| `llama3.2` (3B) full verdict | ~4 min | Best judgement, too slow for stage |

Three optimisations make the small model usable, and each is a lesson worth telling judges:

- **Instant first paint.** The UI renders the deterministic verdict while the model works, then
  upgrades the explanation in place. The audience never waits for a spinner.
- **A compact runtime brief.** SKILL.md is a 2,500-token playbook for humans; the engine sends a
  320-word projection marked `<!-- runtime:start/end -->` inside the same file. One source of
  truth, a fraction of the prompt processing.
- **Stop at the closing brace.** Ollama streams; the client stops generation the moment the JSON
  object balances, and salvages complete fields if a small model rambles past the token cap.

The model stays loaded for 30 minutes (`keep_alive`) so a demo never pays the ~16 s cold start
twice. For a hard guarantee on stage, set `SCAMSHIELD_MODEL` and run one warm-up analysis first.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Sidebar says *Ollama offline* | Run `ollama serve`, then refresh the browser. |
| Analysis returns instantly with a warning | The model failed or timed out; the verdict is rules-only and still correct. Try `gemma3:1b`. |
| `AttributeError` in `dataclasses` after editing files | Streamlit hot-reloaded mid-import. Refresh the browser; `runOnSave` is off by default for this reason. |
| Very slow first analysis | The model is loading (~16 s). The UI warms it at startup; keep the app open before you present. |

## Project layout

```
app.py                              Streamlit UI (3 tabs: Analyse, How it works, Agent Skill)
scamshield/
  rules.py                          12 deterministic fraud patterns + scoring
  engine.py                         Ollama client, JSON contract, merge logic, fallback
  samples.py                        demo corpus with expected verdicts
  cli.py                            terminal interface for testing the pipeline
skills/job-scam-detector/SKILL.md   the Agent Skill: playbook, taxonomy, JSON contract
tests/test_rules.py                 regression tests for the rules engine
.streamlit/config.toml              dark theme, telemetry off
```

Environment variables:

| Variable | Default | Purpose |
|---|---|---|
| `OLLAMA_HOST` | `http://127.0.0.1:11434` | Local engine address |
| `SCAMSHIELD_MODEL` | auto-detect | Force a specific model |

---

## Limitations (say these out loud — judges trust it more)

- **It reads text, not people.** A patient scammer who avoids every pattern can pass. The
  verdict is a second opinion, not a guarantee.
- **Small local models are weaker than frontier models.** `gemma3:1b` invents claims under
  pressure — during development it flagged a genuine offer letter as a payment scam. That is
  exactly why the verification layer exists; expect noisy flags from the model and treat its
  prose as an explanation, not evidence.
- **Not a legal or financial authority.** It never claims a company is fake — only that a
  message behaves like fraud.
- **Urdu/Roman-Urdu is only partly covered.** The rule patterns are English-first; a
  Roman-Urdu phrase list is the obvious next step for Pakistan.
- **No URL reputation lookups**, because that would require the network. Domain heuristics are
  offline and therefore blunt.

## If you extend it

- Add Roman-Urdu patterns (`visa fees`, `paisay bhejain`, `guaranteed visa`) to `rules.py`.
- Add a "paste a screenshot" path with local OCR (Tesseract) — still offline.
- Log anonymised verdict counts to a local SQLite file for a "scams reported this week" panel.
- Package the skill as a standalone agent skill other tools can load.

## Ethics

ScamShield gives guidance, not accusations. It never names a company as criminal, never asks
for personal data, and never phones home. Victims are told what to do next, not blamed.

---

Built for the Agent Skills hackathon. Local model: Google Gemma via Ollama.
