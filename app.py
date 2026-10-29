"""ScamShield AI — offline job-scam detector.

Run with:  streamlit run app.py
"""

from __future__ import annotations

import threading

import streamlit as st

from scamshield import engine, learning, ui
from scamshield.entities import domains_in
from scamshield.engine import Analysis
from scamshield.report import build_report, report_filename
from scamshield.rules import RULES
from scamshield.samples import SAMPLES
from scamshield.samples import SAMPLE_BY_KEY

st.set_page_config(
    page_title="ScamShield AI — Job Scam Detector",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

RULE_LABELS = {rule.key: rule.label for rule in RULES}

# --------------------------------------------------------------------------------------
# Theme — light is the default; the choice lives in session state and survives reruns.
# --------------------------------------------------------------------------------------

MODE_LABELS = {"light": "☀️ Light", "dark": "🌙 Dark"}
st.session_state.setdefault("theme_mode", MODE_LABELS["light"])
mode_key = "dark" if "Dark" in st.session_state["theme_mode"] else "light"
st.markdown(ui.css(mode_key), unsafe_allow_html=True)


def load_sample(text: str) -> None:
    st.session_state["message"] = text
    st.session_state.pop("result", None)
    st.session_state.pop("verdict_id", None)


def clear_result() -> None:
    st.session_state.pop("result", None)
    st.session_state.pop("verdict_id", None)


# --------------------------------------------------------------------------------------
# Onboarding dialog
# --------------------------------------------------------------------------------------


@st.dialog("👋 How ScamShield works — 3 steps", width="large")
def show_intro() -> None:
    st.markdown(
        """
**1. Paste the message.** The WhatsApp forward, the recruiter DM, the "visa processing"
email — exactly as you received it, names and all.

**2. Read the verdict.** You get a risk level, every red flag quoted word-for-word, and a
plain-language reason for each one. The rules verdict appears instantly; the local AI adds its
reasoning a moment later.

**3. Do the safe thing.** Follow the "what to do now" list, ask the employer the suggested
questions, and download the report so a friend doesn't fall for the same message.
"""
    )
    st.markdown(
        ui.note(
            "🔒 <strong>Nothing leaves this laptop.</strong> The AI runs at "
            f"<code>{ui.esc(engine.ollama_host())}</code>. Turn off Wi-Fi and every feature still "
            "works — that is the whole point."
        ),
        unsafe_allow_html=True,
    )
    st.write("")
    left, right = st.columns(2)
    with left:
        if st.button("Try a real scam message", type="primary", use_container_width=True):
            load_sample(SAMPLE_BY_KEY["dubai_hotel"].text)
            st.rerun()
    with right:
        if st.button("Paste my own message", use_container_width=True):
            st.rerun()


# --------------------------------------------------------------------------------------
# Sidebar
# --------------------------------------------------------------------------------------

models = engine.list_models()
online = engine.engine_online()
default_model = engine.pick_model(models)

with st.sidebar:
    st.markdown("#### Appearance")
    st.segmented_control(
        "Theme",
        options=list(MODE_LABELS.values()),
        key="theme_mode",
        label_visibility="collapsed",
    )

    st.divider()
    st.markdown("#### ⚙️ Local engine")
    if online and models:
        st.markdown(
            '<span class="ss-pill ok">● Ollama connected</span> '
            '<span class="ss-pill">127.0.0.1 only</span>',
            unsafe_allow_html=True,
        )
    elif online:
        st.markdown('<span class="ss-pill warn">● Ollama up, no model</span>', unsafe_allow_html=True)
        st.caption("Pull a model: `ollama pull gemma3:1b`")
    else:
        st.markdown('<span class="ss-pill warn">● Ollama offline</span>', unsafe_allow_html=True)
        st.caption("Start it with `ollama serve`. The rules engine still works.")

    model = st.selectbox(
        "Model",
        options=models or [default_model],
        index=(models.index(default_model) if default_model in models else 0),
        help="Any local model works. Small models are far faster on CPU.",
    )
    use_ai = st.toggle(
        "Use local AI",
        value=True,
        help="Off = instant deterministic verdict, no model call.",
    )
    if models:
        st.caption(f"Tip: `gemma3:1b` takes ~60–90s on a CPU laptop. The verdict never waits for it.")

    st.divider()
    st.markdown("#### 🧪 Demo messages")
    st.caption("Click to load, then press Analyse.")
    for sample in SAMPLES:
        tag = {"HIGH": "🔴", "MEDIUM": "🟠", "LOW": "🟢"}[sample.expected]
        st.button(
            f"{tag} {sample.title}",
            key=f"sample_{sample.key}",
            on_click=load_sample,
            args=(sample.text,),
            use_container_width=True,
        )

    st.divider()
    if learning.available():
        learned = learning.feedback_summary()
        st.markdown("#### 🧠 Learning")
        st.caption(
            f"{learning.verdict_count()} message(s) checked · {learned['total']} correction(s) · "
            f"{len(learning.phrases())} taught phrase(s)"
        )
        st.caption("Open the **Learning** tab to see exactly what changed and undo it.")

    st.divider()
    st.markdown("#### 🔒 Privacy")
    st.caption(
        "No cloud dependency. The only network call is "
        f"`{engine.ollama_host()}`, on this laptop. Disconnect Wi-Fi and it still works."
    )


@st.cache_resource(show_spinner=False)
def _warm_model(model_name: str) -> bool:
    """Load the model once in the background so the first demo click is not slow."""
    threading.Thread(target=engine.warmup, args=(model_name,), daemon=True).start()
    return True


if online and models:
    _warm_model(model)

# --------------------------------------------------------------------------------------
# Header
# --------------------------------------------------------------------------------------

status_pills = [
    ("100% offline", "ok"),
    (f"{len(models)} local model(s)" if online else "AI offline · rules active", "accent" if online else "warn"),
    ("Agent Skill · job-scam-detector v1.1", ""),
    ("Free · no account", ""),
]
header_left, header_right = st.columns([5, 1.15], vertical_alignment="center")
with header_left:
    st.markdown(ui.hero(status_pills), unsafe_allow_html=True)
with header_right:
    if st.button("❓ How to use", use_container_width=True, key="open_intro"):
        show_intro()

if "seen_intro" not in st.session_state:
    st.session_state["seen_intro"] = True
    show_intro()


# --------------------------------------------------------------------------------------
# Result rendering
# --------------------------------------------------------------------------------------


def render_actions(result: Analysis) -> None:
    st.markdown(ui.section("✅ What to do now"), unsafe_allow_html=True)
    actions = result.recommended_actions or [
        "Do not send money or documents until you verify the employer."
    ]
    st.markdown(
        "".join(
            f'<div style="display:flex;gap:10px;margin-bottom:12px;font-size:.9rem;'
            f'line-height:1.55"><span style="color:var(--ss-accent);font-weight:800">{i}</span>'
            f"<span>{ui.esc(action)}</span></div>"
            for i, action in enumerate(actions, 1)
        ),
        unsafe_allow_html=True,
    )
    if result.questions_to_ask:
        st.markdown(ui.section("🎯 Ask them this"), unsafe_allow_html=True)
        st.markdown(
            "".join(
                f'<div style="color:var(--ss-muted);font-size:.86rem;margin-bottom:9px;'
                f'line-height:1.55">↳ {ui.esc(question)}</div>'
                for question in result.questions_to_ask
            ),
            unsafe_allow_html=True,
        )
    if result.positive_signals:
        st.markdown(ui.section("✅ What looks legitimate"), unsafe_allow_html=True)
        st.markdown(
            "".join(
                f'<div style="color:var(--ss-muted);font-size:.86rem;margin-bottom:8px;'
                f'line-height:1.5">• {ui.esc(item)}</div>'
                for item in result.positive_signals
            ),
            unsafe_allow_html=True,
        )


def render_feedback(result: Analysis, verdict_id: int | None, message: str) -> None:
    if not verdict_id or not learning.available():
        return
    with st.expander("📣 Was this verdict right? Your answer tunes the rules", expanded=False):
        st.caption(
            "This is the only way ScamShield learns. One correction changes very little by "
            "design — three or more and the rule's weight is adjusted within ±45%."
        )
        cols = st.columns(3)
        choices = [
            ("🟢 It's legitimate", "LOW"),
            ("🟠 Just suspicious", "MEDIUM"),
            ("🔴 It's a scam", "HIGH"),
        ]
        for col, (label, level) in zip(cols, choices):
            if col.button(label, key=f"fb_{verdict_id}_{level}", use_container_width=True):
                changed = learning.record_feedback(
                    verdict_id,
                    result.risk_level,
                    level,
                    [hit.key for hit in result.rule_hits],
                )
                if changed:
                    st.session_state["feedback_msg"] = "Learned. " + "; ".join(
                        f"{RULE_LABELS.get(c['key'], c['key'])} ×{c['multiplier']:.2f}"
                        for c in changed[:3]
                    )
                else:
                    st.session_state["feedback_msg"] = (
                        "Saved. Each rule needs three labelled messages before its weight moves — "
                        "keep correcting messages that trigger the same rule."
                    )
                st.rerun()

        if st.session_state.get("feedback_msg"):
            st.success(st.session_state["feedback_msg"])

        domains = domains_in(message)
        if domains:
            st.markdown("**Trust a domain you know**")
            domain = st.selectbox(
                "Domain found in this message",
                options=domains,
                key=f"dom_{verdict_id}",
                label_visibility="collapsed",
            )
            if st.button("Trust this domain", key=f"trust_{verdict_id}"):
                ok, note = learning.add_trusted_domain(domain)
                if ok:
                    st.session_state["feedback_msg"] = note
                    st.rerun()
                else:
                    st.error(note)


def render_result(result: Analysis, message: str, verdict_id: int | None = None) -> None:
    st.markdown(ui.verdict(result), unsafe_allow_html=True)

    if result.risk_score in range(27, 34) or result.risk_score in range(62, 69):
        st.markdown(
            ui.note(
                "<strong>Close call.</strong> The score sits near a band boundary, so treat the "
                "level as a second opinion. Add context (the sender's address, the company website) "
                "and re-check before acting on it."
            ),
            unsafe_allow_html=True,
        )
    if result.error:
        st.caption(f"AI layer note: {result.error}")

    left, right = st.columns([1.45, 1], gap="large")
    with left:
        if result.red_flags:
            heading = "🚩 Red flags" if result.risk_level != "LOW" else "🚩 Concerns raised (unverified)"
            st.markdown(ui.section(heading, f"{len(result.red_flags)} found"), unsafe_allow_html=True)
            st.markdown(ui.flags(result.red_flags), unsafe_allow_html=True)
        else:
            st.markdown(ui.section("🚩 Red flags"), unsafe_allow_html=True)
            st.markdown(
                ui.note("No known scam pattern matched. That is good news, not a guarantee."),
                unsafe_allow_html=True,
            )

        if result.entities:
            st.markdown(
                ui.section("🔗 Links, addresses and numbers", f"{len(result.entities)} found"),
                unsafe_allow_html=True,
            )
            st.markdown(ui.entities(result.entities), unsafe_allow_html=True)

        if result.similar:
            st.markdown(ui.section("🕘 You have seen this before"), unsafe_allow_html=True)
            st.markdown(ui.similar(result.similar), unsafe_allow_html=True)

    with right:
        render_actions(result)

        if result.learn_notes:
            st.markdown(ui.section("🧠 Personalised"), unsafe_allow_html=True)
            st.markdown(
                ui.note("<br>".join(ui.esc(note) for note in result.learn_notes)),
                unsafe_allow_html=True,
            )

        report = build_report(result, message)
        st.download_button(
            "⬇️ Download safety report",
            data=report,
            file_name=report_filename(result),
            mime="text/markdown",
            use_container_width=True,
            key=f"dl_{verdict_id or 'x'}",
        )
        st.caption("A shareable summary with the quotes — so the next person doesn't pay.")

    with st.expander("🔬 Evidence and how this was scored", expanded=False):
        if result.rule_hits:
            for hit in result.rule_hits:
                adjustment = f" · {hit.learned_note}" if hit.learned_note else ""
                st.markdown(
                    f"**{ui.esc(hit.label)}** · severity `{hit.severity}` · weight `{hit.weight}`"
                    f"{ui.esc(adjustment)}"
                )
                for evidence in hit.evidence:
                    st.code(evidence, language=None)
        else:
            st.caption("No deterministic pattern matched. The verdict rests on the model's reading.")
        st.caption(
            "Scoring: rule weights, floored at 82 for any critical family, plus at most 15 points "
            "for verified model findings. A lone AI opinion can never reach HIGH."
        )

    if verdict_id:
        render_feedback(result, verdict_id, message)


def render_empty_state() -> None:
    st.markdown(
        ui.steps(
            [
                (
                    "STEP 1",
                    "Paste the whole message",
                    "Forward, DM or email — include the sender address and any link. "
                    "The more of it we see, the better the evidence.",
                ),
                (
                    "STEP 2",
                    "Read the quoted evidence",
                    "Every flag shows the exact words that triggered it and why they matter, "
                    "so nothing is a black box.",
                ),
                (
                    "STEP 3",
                    "Act, then pass it on",
                    "Follow the safety steps and download the report. If the verdict is wrong, "
                    "tell it — that is how it learns.",
                ),
            ]
        ),
        unsafe_allow_html=True,
    )
    st.write("")
    st.markdown(
        ui.note(
            "No message handy? Load one of the <strong>demo messages</strong> from the sidebar, "
            "or use a quick example below."
        ),
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------------------
# Tabs
# --------------------------------------------------------------------------------------

tab_scan, tab_how, tab_learn, tab_compare, tab_skill = st.tabs(
    ["🔍 Check a message", "🧭 How it works", "🎓 Learning", "📊 Compare", "📜 Agent Skill"]
)

with tab_scan:
    message = st.text_area(
        "Suspicious message",
        key="message",
        height=210,
        placeholder=(
            "Paste the WhatsApp message, email or DM here…\n\n"
            "e.g. “Dear Candidate, Dubai hotel job, visa processing fee Rs 35,000, "
            "send on JazzCash…”"
        ),
        label_visibility="collapsed",
        on_change=clear_result,
    )

    quick_left, quick_right = st.columns([3, 1])
    with quick_left:
        chips = st.columns(len(SAMPLES))
        for col, sample in zip(chips, SAMPLES):
            tag = {"HIGH": "🔴", "MEDIUM": "🟠", "LOW": "🟢"}[sample.expected]
            col.button(
                f"{tag} {sample.title.split('—')[0].strip()[:22]}",
                key=f"chip_{sample.key}",
                on_click=load_sample,
                args=(sample.text,),
                use_container_width=True,
            )
    with quick_right:
        run = st.button("Analyse message", type="primary", use_container_width=True)

    st.caption(
        "Your text is processed by the model on this machine. No upload, no logging, no cloud."
    )

    slot = st.empty()

    if run:
        if not message.strip():
            st.toast("Paste a message first.")
        else:
            # Phase 1 — deterministic verdict, available in milliseconds.
            fast = engine.analyze(message, use_ai=False)
            with slot.container():
                render_result(fast, message)
            st.caption("⚡ Rules verdict above is already final on critical signals — the local AI is adding reasoning…")

            if use_ai and online:
                with st.spinner("The local model is reading the message — nothing leaves this laptop…"):
                    full = engine.analyze(message, model=model, use_ai=True)
            else:
                full = fast

            verdict_id = learning.record_verdict(message, full)
            st.session_state["result"] = full
            st.session_state["verdict_id"] = verdict_id
            st.session_state["analyzed_text"] = message
            st.session_state.pop("feedback_msg", None)
            slot.empty()
            st.rerun()

    current = st.session_state.get("result")
    if current is not None and not run:
        render_result(
            current,
            st.session_state.get("analyzed_text", message),
            st.session_state.get("verdict_id"),
        )
        if st.button("🔄 Check another message", key="reset_scan"):
            clear_result()
            st.session_state["message"] = ""
            st.rerun()
    elif current is None and not run:
        render_empty_state()


with tab_how:
    st.markdown("#### Four layers, one defensible verdict")
    st.markdown(
        ui.steps(
            [
                (
                    "01 · RULES",
                    "Deterministic evidence",
                    "Twelve fraud families — upfront fees, private wallets, guaranteed visas, "
                    "document harvesting, lookalike links — quote the exact words that matched, "
                    "in under a tenth of a second.",
                ),
                (
                    "02 · ENTITIES",
                    "Links and contacts",
                    "Every address, link, number and ID is pulled out and judged on structure: "
                    "free mailboxes, look-alike brand domains, throwaway TLDs, hidden numbers.",
                ),
                (
                    "03 · AGENT SKILL",
                    "Local reasoning",
                    "Gemma reads the evidence through SKILL.md — a fraud investigator's playbook "
                    "with a strict JSON contract — and writes the explanation and advice.",
                ),
                (
                    "04 · VERIFY & LEARN",
                    "Bounded, explainable",
                    "Model claims need a taxonomy code and a verified quote. Your corrections "
                    "adjust rule weights within ±45%, after at least three labels.",
                ),
            ]
        ),
        unsafe_allow_html=True,
    )

    st.markdown("##### Guardrails against a small local model")
    st.markdown(
        """
1. **Taxonomy or nothing.** A model flag must carry one of the twelve built-in codes.
2. **Quote or nothing.** Its quote has to exist in the message — full match or 75% token overlap.
3. **No invented payment.** A payment claim is dropped when its own quote denies payment.
4. **Rules certify severity.** Critical families must be rule-proven, and model findings add at
   most 15 points — so no lone AI opinion can turn a message HIGH.
"""
    )

    st.markdown("##### Why not just ask a cloud chatbot?")
    st.markdown(
        "Scam messages contain names, phone numbers, CNIC copies and bank details. Pasting them "
        "into a cloud chatbot is how victims get re-victimised — and a chatbot gives you prose, "
        "not evidence. ScamShield runs the model on the device, quotes the trigger words, and "
        "keeps working with the Wi-Fi off."
    )


with tab_learn:
    st.markdown("#### What ScamShield has learned on this machine")
    summary = learning.feedback_summary()
    rules_learned = [row for row in learning.learned_rule_rows() if row["active"]]
    st.markdown(
        ui.metrics(
            [
                (str(learning.verdict_count()), "messages checked"),
                (str(summary["total"]), "verdicts corrected"),
                (str(len(rules_learned)), "rules adapted"),
                (str(len(learning.phrases())), "phrases taught"),
            ]
        ),
        unsafe_allow_html=True,
    )

    st.markdown(ui.note(
        "<strong>How it learns without retraining.</strong> Each rule keeps two counters — how "
        "often messages it fired on turned out to be scams, and how often they turned out to be "
        "legitimate. Precision is smoothed with a Beta(2, 2) prior, so one click cannot rewrite "
        "the model. After three labelled messages a rule's weight moves between ×0.55 and ×1.45. "
        "Everything is visible here and reversible."
    ), unsafe_allow_html=True)

    st.markdown("##### Rule precision from your corrections")
    if learning.learned_rule_rows():
        rows = []
        for row in learning.learned_rule_rows():
            rows.append(
                [
                    f'<span class="ss-mono">{ui.esc(row["rule"])}</span>'
                    f'<div class="ss-dim">{ui.esc(RULE_LABELS.get(row["rule"], ""))}</div>',
                    f'{row["scams"]:g} / {row["legit"]:g}',
                    f'{row["precision"]:.2f}',
                    f'<span class="ss-mono">×{row["multiplier"]:.2f}</span>',
                    "active" if row["active"] else "collecting…",
                ]
            )
        st.markdown(
            ui.table(["Rule", "Scam / legit labels", "Precision", "Weight", "Status"], rows),
            unsafe_allow_html=True,
        )
    else:
        st.caption("No corrections yet. Every rule is at its designed weight (×1.00).")

    st.markdown("##### Teach it a phrase")
    with st.form("phrase_form", clear_on_submit=True):
        phrase_col, button_col = st.columns([4, 1])
        phrase = phrase_col.text_input(
            "Wording you keep seeing in scams",
            placeholder="e.g. visa stamping charges, ghar baithe kamai",
            label_visibility="collapsed",
        )
        submitted = button_col.form_submit_button("Teach", use_container_width=True)
    if submitted and phrase.strip():
        ok, note = learning.add_phrase(phrase)
        st.session_state["learn_msg"] = note
        if ok:
            st.rerun()
        else:
            st.warning(note)

    for row in learning.phrases():
        col_text, col_del = st.columns([5, 1])
        col_text.markdown(f'`{ui.esc(row["phrase"])}` — added {ui.esc(row["created_at"][:10])}')
        if col_del.button("Remove", key=f"del_phrase_{row['id']}", use_container_width=True):
            learning.delete_phrase(int(row["id"]))
            st.rerun()

    st.markdown("##### Trusted domains")
    st.caption(
        "Domains you vouch for. Free-mailbox and link signals are dampened when every domain in a "
        "message is trusted. A scammer can still use the domain, so this is a preference, not proof."
    )
    with st.form("domain_form", clear_on_submit=True):
        domain_col, domain_btn = st.columns([4, 1])
        domain = domain_col.text_input(
            "Domain",
            placeholder="systemsltd.com",
            label_visibility="collapsed",
        )
        domain_submitted = domain_btn.form_submit_button("Trust", use_container_width=True)
    if domain_submitted and domain.strip():
        ok, note = learning.add_trusted_domain(domain)
        st.session_state["learn_msg"] = note
        if ok:
            st.rerun()
        else:
            st.warning(note)

    for row in learning.trusted_domains():
        col_text, col_del = st.columns([5, 1])
        col_text.markdown(f'`{ui.esc(row["domain"])}`')
        if col_del.button("Forget", key=f"del_domain_{row['domain']}", use_container_width=True):
            learning.delete_trusted_domain(row["domain"])
            st.rerun()

    st.markdown("##### Recent checks")
    recent = learning.recent_verdicts(8)
    if recent:
        rows = [
            [
                ui.esc(row["created_at"].replace("T", " ")[:16]),
                f'{row["level"]} ({row["score"]})',
                ui.esc("rules" if row["engine"] == "rules" else row["engine"]),
                ui.esc(row["actual_level"] or "—"),
            ]
            for row in recent
        ]
        st.markdown(ui.table(["When (UTC)", "Verdict", "Engine", "You said"], rows), unsafe_allow_html=True)
        st.caption("Message text is never stored — only a 64-bit fingerprint, used to spot repeats.")
    else:
        st.caption("Nothing checked yet.")

    st.markdown("##### Reset")
    st.caption(
        "Resetting learns nothing new: corrections, taught phrases and trusted domains are "
        "deleted and every rule returns to its designed weight. Verdict history is kept unless "
        "you clear it too."
    )
    reset_col, clear_col = st.columns(2)
    if reset_col.button("Reset learned adjustments", use_container_width=True):
        learning.reset_learning()
        st.session_state.pop("feedback_msg", None)
        st.rerun()
    if clear_col.button("Clear verdict history", use_container_width=True):
        learning.clear_history()
        st.rerun()

    if st.session_state.get("learn_msg"):
        st.success(st.session_state["learn_msg"])


with tab_compare:
    st.markdown("#### How ScamShield compares")
    st.caption(
        "Capabilities checked against each tool's own documentation (October 2026). "
        "“—”, “Offline” and “Roadmap” are deliberate product choices, not gaps we overlooked."
    )
    headers = ["Capability", "Scamio", "Norton Genie", "ScamAdviser", "Truecaller", "ScamShield"]
    rows = [
        ["Paste text and get a verdict", "✅", "✅", "Partial", "—", "✅"],
        ["Screenshot / image input", "✅", "✅", "✅", "—", "Roadmap (OCR)"],
        ["Link & domain checks", "✅ live", "✅ live", "✅ 40+ sources", "✅ live", "Offline heuristics"],
        ["Phone number lookup", "—", "—", "—", "✅", "Masked-number detector"],
        ["Works fully offline", "❌", "❌", "❌", "❌", "✅"],
        ["No account or upload", "❌", "Partial", "❌", "❌", "✅"],
        ["Quotes the exact trigger words", "Partial", "Partial", "❌", "❌", "✅"],
        ["Explains the scoring", "Partial", "Partial", "✅", "❌", "✅ full audit"],
        ["Learns from your corrections", "✅ vendor-side", "✅ vendor-side", "❌", "✅ community", "✅ on-device"],
        ["Taught phrases / trusted domains", "❌", "❌", "Partial (owners)", "❌", "✅"],
        ["Exportable report", "❌", "❌", "❌", "❌", "✅ Markdown"],
        ["Free, unlimited checks", "✅", "✅", "Partial", "✅", "✅"],
    ]
    st.markdown(ui.table(headers, rows), unsafe_allow_html=True)

    st.markdown("##### What they do better — and what we did about it")
    st.markdown(
        """
- **Scamio and Norton accept screenshots.** Victims usually have a screenshot, not text. We
  keep OCR on the roadmap: Tesseract is a local binary, so it fits the offline promise, but
  shipping a button that fails on a judge's laptop would be worse than an honest gap.
- **Scamio, ScamAdviser and Truecaller check live reputation.** That needs the network. Instead
  ScamShield analyses the *structure* of every link, mailbox and number offline — free mailbox,
  look-alike brand domain, disposable TLD, punycode, hidden digits — and says plainly that
  reputation was not checked.
- **ScamAdviser lets a site owner appeal a score.** We turned that into user correction:
  every verdict can be challenged, and the affected rule's weight moves, visibly.
- **Norton Genie says when it cannot decide.** We added band-boundary warnings, separate
  "flagged" vs "confirmed" language, and a confidence field that the scoring cannot fake.
- **Google Messages and Truecaller act inside the app.** We cannot: no messaging integration.
  Instead the report is downloadable so the user can warn the next person themselves.
"""
    )

    st.markdown("##### Roadmap, in the order we would build it")
    st.markdown(
        """
1. **Local OCR** for screenshots (Tesseract), so the most common input format works offline.
2. **Roman-Urdu patterns** — the scams students actually receive mix Urdu transliteration with
   English, and the current rules are English-first.
3. **A local reputation cache** — domains and numbers from messages the user has already judged,
   labelled as cached and possibly stale, never presented as live data.
4. **A one-page PDF** built from the Markdown report, for sharing on WhatsApp.
"""
    )
    st.caption(
        "Sources: Bitdefender Scamio product & FAQ pages, Norton Genie FAQ, ScamAdviser algorithm "
        "explainer, Truecaller Scam Checker, Google Messages protection documentation, FTC job-scam "
        "guidance. Full links are in the README."
    )


with tab_skill:
    st.markdown("#### `skills/job-scam-detector/SKILL.md`")
    st.caption(
        "The brain of the project. Editable, versioned, testable — swap the playbook and the "
        "agent changes behaviour without touching a line of Python."
    )
    with st.expander("Read the full Agent Skill", expanded=False):
        st.code(engine.load_skill(), language="markdown", line_numbers=False)
