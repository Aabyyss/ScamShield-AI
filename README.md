<img src="assets/logo.png" width="96" alt="ScamShield AI logo" align="left" />

# ScamShield AI

**Paste a job offer — or a screenshot of one. Know if it's a scam before you send a single rupee.**

<br clear="left" />

> **Full write-up:** [docs/PROJECT-REPORT.md](docs/PROJECT-REPORT.md) — architecture, every
> library, the real bugs and how they were fixed, measurements and honest limitations.

ScamShield is an offline AI agent that reads suspicious job messages (WhatsApp forwards,
recruiter DMs, hiring emails) and returns a risk verdict with the exact red flags quoted from
the message, plus every link, mailbox and number judged on its own. It runs entirely on your
laptop: the model is local, the only socket it opens is `127.0.0.1:11434`, and it keeps working
with Wi-Fi switched off.

> Every day, students in Pakistan lose their savings to fake overseas job offers on WhatsApp.
> Most can't tell an offer is fake until the money is gone — and they won't paste a message
> containing their name, CNIC and bank details into a cloud chatbot. ScamShield reads it
> without it ever leaving the machine.

---

## What you get

| | |
|---|---|
| **Quoted evidence** | Every red flag shows the exact words that triggered it and why it matters. No black box. |
| **Instant first verdict** | The rules engine answers in under 0.1 s; the local model upgrades the explanation in place. |
| **Screenshot input** | Only have a picture of the message? Local RapidOCR reads it on the device — no Tesseract install, no upload. |
| **Link, mailbox and number checks** | Free mailboxes, look-alike brand domains, throwaway TLDs, shorteners, punycode, hidden digits — all offline. |
| **A shareable report** | One click downloads a Markdown safety report with the quotes, so the next person doesn't pay. |
| **It learns from you** | Correct a verdict and the rules that fired are re-weighted — bounded, visible, reversible. |
| **Light and dark by design** | A hand-tuned bright theme for the projector and a dark one for the room; switch live in the sidebar. |
| **Guided on first open** | A three-step welcome, quick example chips, and plain-language next actions instead of jargon. |
| **100% offline** | No account, no API key, no telemetry. Turn off Wi-Fi mid-demo and nothing changes. |

---

## Why this is different from "asking ChatGPT"

| | Cloud chatbot | ScamShield AI |
|---|---|---|
| Message contents | Uploaded, may be retained | Never leave the device |
| Works with Wi-Fi off | No | Yes |
| Consistent judgement | Depends on the prompt you type | Fixed Agent Skill + versioned scoring |
| Evidence | Prose you have to trust | Quoted snippets + rule weights |
| Links and contacts | "Looks suspicious" | Each entity judged, with reasons |
| Learns from your correction | Not for you | On-device, bounded, undoable |
| False-negative guard | None | Critical signals can't be argued away by the model |

### How it compares to consumer scam checkers

Checked against each product's own documentation (October 2026):

| Capability | Scamio | Norton Genie | ScamAdviser | Truecaller | ScamShield |
|---|---|---|---|---|---|
| Paste text → verdict | ✅ | ✅ | Partial | — | ✅ |
| Screenshot input | ✅ | ✅ | ✅ | — | ✅ local OCR |
| Link / domain checks | ✅ live | ✅ live | ✅ 40+ sources | ✅ live | Offline heuristics |
| Phone number lookup | — | — | — | ✅ | Masked-number detector |
| Works fully offline | ❌ | ❌ | ❌ | ❌ | ✅ |
| No account or upload | ❌ | Partial | ❌ | ❌ | ✅ |
| Quotes the trigger words | Partial | Partial | ❌ | ❌ | ✅ |
| Learns from your corrections | ✅ vendor-side | ✅ vendor-side | ❌ | ✅ community | ✅ on-device |
| Taught phrases / trusted domains | ❌ | ❌ | Partial (owners) | ❌ | ✅ |
| Exportable report | ❌ | ❌ | ❌ | ❌ | ✅ Markdown |

What those tools do better, and what we chose:

- **Screenshots.** Scamio and Norton accept them; victims usually have one. ScamShield now
  matches that with RapidOCR: the ONNX models ship inside the Python package, so
  `pip install` is the only setup and the image never leaves the process. Printed text reads
  well; handwriting and Urdu script still don't, and the app says so after each scan.
- **Live reputation.** ScamAdviser, Truecaller and Scamio query maintained databases. That needs
  the network, so ScamShield judges link *structure* offline and says plainly that reputation was
  not checked.
- **Uncertainty.** Norton Genie says when it cannot decide. ScamShield warns when a score sits
  on a band boundary and never presents "no pattern found" as proof of legitimacy.
- **In-app protection.** Google Messages and Truecaller act inside the messaging app. We can't;
  the downloadable report is how a user warns the next person instead.

Sources: [Bitdefender Scamio](https://www.bitdefender.com/en-us/consumer/scamio),
[Norton Genie FAQ](https://support.norton.com/sp/de/de/home/current/solutions/v20230717145233467),
[ScamAdviser algorithm](https://www.scamadviser.com/articles/scamadviser-algorithm-explainer),
[Truecaller Scam Checker](https://www.truecaller.com/scam-checker),
[Google Messages protection](https://support.google.com/messages/answer/9327903?hl=en),
[FTC job scams](https://consumer.ftc.gov/articles/job-scams).

---

## Quickstart

### One click (Windows, recommended)

```text
1. Double-click  setup_desktop.bat        (once — puts a shortcut on your Desktop)
2. Double-click  “ScamShield AI”          (from now on)
```

The shortcut starts the local server, wakes Ollama, opens the browser and then steps aside; the
app keeps running if you close the console. First launch installs the Python packages for you.
No shortcut wanted? Double-click `ScamShield.bat`, or on macOS/Linux run `./launch.sh`.

Launcher options: `python launcher.py --port 8600`, `--no-browser`, `--restart`, `--stop`.

### Manual start

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

Screenshot reading needs no extra system software: `rapidocr-onnxruntime` (in
`requirements.txt`) bundles its own models and runs on CPU. `screenshots/whatsapp-demo.png`
is a ready-made scam screenshot you can upload to try it.

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
                 │    12 fraud families, each hit keeps the      │
                 │    exact quote + severity + weight            │
                 └───────────────────┬──────────────────────────┘
                                     │ evidence pack
                 ┌───────────────────▼──────────────────────────┐
                 │ 2. ENTITIES  (scamshield/entities.py)        │
                 │    every link, mailbox, number, ID judged     │
                 │    on structure — no network involved         │
                 └───────────────────┬──────────────────────────┘
                                     │
                 ┌───────────────────▼──────────────────────────┐
                 │ 3. AGENT SKILL  (skills/…/SKILL.md)          │
                 │    Gemma via local Ollama, JSON-only output   │
                 └───────────────────┬──────────────────────────┘
                                     │ verdict + flags + advice
                 ┌───────────────────▼──────────────────────────┐
                 │ 4. VERIFY, LEARN & SCORE (engine + learning) │
                 │    quotes verified, rules certify severity,   │
                 │    feedback adjusts weights within ±45%       │
                 └──────────────────────────────────────────────┘
```

**Why both layers.** Rules alone are brittle ("CNIC" isn't always fraud). A model alone can be
talked out of a verdict by a polite scammer — or, at 1B parameters, invent one. Together: the
rules assign the score and the model explains it.

### Guardrails against a small model

A tiny local model is not a frontier model, so the architecture assumes it will sometimes be
wrong. Four checks run before any model output reaches the screen:

1. **Taxonomy or nothing.** Each flag must carry a `code` from the twelve-family taxonomy.
2. **Quote or nothing.** The `evidence` must be found in the message (exact match, or ≥75% token
   overlap after normalisation). A hallucinated quote kills the flag.
3. **No invented payment.** A payment claim is discarded when its own quote denies payment
   ("no payment or fee of any kind is required") — the failure mode we hit while building this.
4. **Rules certify severity.** A `critical`/`high` claim is downgraded to `medium` unless the rules
   engine independently matched the same family, and model findings add at most 15 points.

Every discarded claim is counted in the result footer.

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
floors the score at 82. The score is deterministic: rule weights, plus at most 15 points for
verified model findings.

---

## Self-learning, without retraining a model

The **Learning** tab is the whole mechanism, visible and reversible:

1. **Rule precision.** Every rule keeps two counters — how often messages it fired on were
   confirmed scams, and how often they were called legitimate. Precision is the posterior mean of
   `Beta(2 + scams, 2 + legit)`, so a prior worth four observations absorbs early noise.
   After **three labelled messages** a rule's weight moves between **×0.55 and ×1.45**.
2. **Taught phrases.** Wording you keep seeing (`visa stamping charges`, `ghar baithe kamai`) is
   matched literally and contributes one modest, clearly-labelled flag. Multiword only, so a
   single word can't hijack the detector.
3. **Trusted domains.** Domains you vouch for dampen free-mailbox and link signals. It is a
   preference, not proof — the UI says so.
4. **Message memory.** A 64-bit simhash of each scan finds near-duplicates so the app can say
   *"you checked 3 messages like this; two were scams"* — **without storing the message text**.

Safeguards: feedback comes only from an explicit click, never from the model's own guess; one
correction changes nothing; re-labelling a verdict replaces its old evidence instead of stacking
it; a critical signal keeps its floor, so feedback cannot whitewash an upfront-fee demand; and
*Reset learned adjustments* returns every rule to its designed weight.

That last property is worth saying on stage: **this system learns to be more accurate, not more
lenient.**

---

## Demo script (3 minutes, on stage)

1. **Frame it.** "Job scams target students who can't afford to lose Rs 35,000. Victims won't
   paste these messages into ChatGPT, because the message contains their CNIC. So we made the
   AI come to them."
2. **The instant layer.** Paste the Dubai hotel message (quick chip or sidebar). Hit **Analyse**.
   The rules verdict, quoted red flags and the Gmail/wallet entities appear in under a second.
3. **The reasoning layer.** While the local model finishes, point at the sidebar: `Ollama
   connected · 127.0.0.1 only`. The summary, advice and "ask them this" questions fill in.
4. **The proof.** Turn off Wi-Fi *live*. Run the Saudi Aramco message again. Same verdict, zero
   network.
5. **The honest test.** Run the legitimate Systems Limited offer: **LOW**, with positive signals
   and its real domain marked clean. "A detector that flags everything protects no one."
6. **The learning loop.** Say the borderline message is legitimate. Show **Learning** → the rule's
   precision, its new weight, and the reset button. "It adjusts — and you can prove it did."
7. **Close.** "Every rule and prompt is in the repo. A telecom, a university or NADRA could ship
   this to millions of users without a single rupee of inference cost."

### Demo corpus

| Sample | Expected | What it exercises |
|---|---|---|
| `dubai_hotel` | **HIGH** | visa fee, JazzCash, guaranteed visa, urgency, Gmail HR |
| `saudi_visa` | **HIGH** | passport/CNIC/bank harvesting, "company name later" |
| `task_scam` | **HIGH** | daily-pay task scam, Telegram funnel, refundable fee |
| `legit_offer` | **LOW** | real offer letter: interview panel, official domain, "no fee at any stage" |
| `borderline` | **MEDIUM** | small local employer, Gmail, "no experience needed" |

---

## Interface

- **Light theme by default**, designed for a projector: white cards, soft shadows, blue accent,
  readable quoted evidence. **Dark theme** is a full second palette, not an inversion.
- **Welcome dialog** on first open explains the three-step flow and offers a scam example.
  It is also reachable from **❓ How to use** at any time.
- **Two input modes:** paste text, or upload a screenshot (PNG/JPG/WebP) and edit the text OCR
  produces before it is analysed.
- **Quick example chips** above the button, plus the fuller demo list in the sidebar.
- **Tabs:** Check a message · How it works · Learning · Compare · Agent Skill.
- Verdicts expose *why*: quoted evidence, entity reasons, rule weights, discarded AI claims.

---

## Performance on a CPU-only laptop

Measured on this machine (no GPU, Ollama 0.40, Python 3.14, 8 threads):

| Path | Time | Notes |
|---|---|---|
| Rules + entities only | **< 0.1 s** | Rendered immediately in the UI |
| Screenshot OCR (RapidOCR) | **~4–7 s** | 1600 px upscale, 70-word card measured at 91% confidence |
| `gemma3:1b` full verdict | **~65–95 s** | Recommended demo model; ~320-word runtime brief |
| `llama3.2` (3B) full verdict | ~4 min | Best judgement, too slow for stage |

Three optimisations make the small model usable:

- **Instant first paint.** The deterministic verdict renders while the model works.
- **A compact runtime brief.** SKILL.md is a 2,500-token playbook for humans; the engine sends a
  320-word projection marked `<!-- runtime:start/end -->` in the same file.
- **Stop at the closing brace.** Ollama streams; the client stops the moment the JSON balances,
  and salvages complete fields if the model rambles past the token cap.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Sidebar says *Ollama offline* | Run `ollama serve`, then refresh the browser. |
| Analysis returns instantly with a warning | The model failed or timed out; the verdict is rules-only and still correct. Try `gemma3:1b`. |
| Very slow first analysis | The model is loading (~16 s). The app warms it at startup. |
| Learning tab is empty after a correction | A rule needs three labelled messages before its weight moves; that is by design. |
| `AttributeError` in `dataclasses` after editing files | Streamlit hot-reloaded mid-import. Refresh; `runOnSave` is off for this reason. |

## Project layout

```
app.py                              Streamlit UI (5 tabs, onboarding, theme switch)
launcher.py                         one-click launcher (deps, Ollama, port, browser)
ScamShield.bat                      Windows double-click entry point
setup_desktop.bat                   creates the Desktop shortcut for any collaborator
launch.sh                           macOS / Linux entry point
assets/                             logo, page icon and multi-size .ico
tools/make_logo.py                  regenerates the logo and icon from code
tools/create_shortcut.ps1           Windows shortcut creation with the custom icon
docs/PROJECT-REPORT.md              full technical report
scamshield/
  rules.py                          12 deterministic fraud families + scoring
  entities.py                       offline link / mailbox / phone / ID analysis
  ocr.py                            local screenshot reading (RapidOCR, Tesseract fallback)
  engine.py                         Ollama client, JSON contract, merge logic, fallback
  learning.py                       SQLite feedback store, Beta weights, phrases, memory
  report.py                         shareable Markdown safety report
  ui.py                             light + dark palettes, cards, ring, tables
  samples.py                        demo corpus with expected verdicts
  cli.py                            terminal interface for testing the pipeline
skills/job-scam-detector/SKILL.md   the Agent Skill: playbook, taxonomy, JSON contract
tests/                              44 regression tests (rules, entities, learning, report, OCR)
screenshots/whatsapp-demo.png       ready-made scam screenshot for trying OCR
.streamlit/config.toml              light base theme, telemetry off
data/scamshield.db                  local learning store (git-ignored)
```

Environment variables:

| Variable | Default | Purpose |
|---|---|---|
| `OLLAMA_HOST` | `http://127.0.0.1:11434` | Local engine address |
| `SCAMSHIELD_MODEL` | auto-detect | Force a specific model |
| `SCAMSHIELD_DB` | `data/scamshield.db` | Where the learning store lives |

Run the tests with `python -m unittest discover -s tests -v`.

---

## Limitations (say these out loud — judges trust it more)

- **It reads text, not people.** A patient scammer who avoids every pattern can pass. The
  verdict is a second opinion, not a guarantee.
- **Small local models are weaker than frontier models.** `gemma3:1b` invents claims under
  pressure — during development it flagged a genuine offer letter as a payment scam. That is
  exactly why the verification layer exists.
- **OCR is good, not perfect.** Printed Latin text reads well, but handwriting, Urdu script,
  heavy compression and cropped screenshots produce errors. That is why the extracted text lands
  in an editable box before it is analysed.
- **No live reputation data.** Link and number judgement is structural and offline, so it cannot
  know a domain was reported yesterday.
- **Urdu/Roman-Urdu is only partly covered.** The rule patterns are English-first.
- **Not a legal or financial authority.** It never claims a company is fake — only that a
  message behaves like fraud.

## Roadmap

1. **Urdu and handwritten OCR** — RapidOCR covers printed Latin text; the scams students
   actually receive often arrive as Urdu script or a photo of handwriting.
2. **Roman-Urdu patterns** (`paisay bhejain`, `visa guarantee`, `ghar baithe kamai`).
3. **A local reputation cache** built from messages the user has already judged, labelled as
   cached and possibly stale.
4. **One-page PDF** generated from the Markdown report for WhatsApp sharing.

## Ethics

ScamShield gives guidance, not accusations. It never names a company as criminal, never asks
for personal data, and never phones home. Victims are told what to do next, not blamed.

---

Built for the Agent Skills hackathon. Local model: Google Gemma via Ollama.

A collaborator only needs to clone the repository, install the requirements once (the launcher
does it on first run) and run `setup_desktop.bat` to get the same one-click shortcut.
