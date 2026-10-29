"""ScamShield AI — offline job-scam detector.

Run with:  streamlit run app.py
"""

from __future__ import annotations

import html

import streamlit as st

import scamshield
from scamshield import engine
from scamshield.samples import SAMPLES, SAMPLE_BY_KEY

st.set_page_config(
    page_title="ScamShield AI — Job Scam Detector",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

RISK_STYLE = {
    "HIGH": ("high", "#ff5a5f", "Do not pay. Do not send documents."),
    "MEDIUM": ("medium", "#f5a524", "Unverified. Check the employer before replying."),
    "LOW": ("low", "#2fbf71", "No scam pattern found. Still verify independently."),
}

st.markdown(
    """
<style>
  .stApp { background: radial-gradient(1100px 500px at 15% -10%, #16213e 0%, #0b1020 55%, #080b16 100%); }
  .block-container { padding-top: 2.2rem; max-width: 1180px; }
  h1, h2, h3, h4, p, li, span, div { color: #e8edf7; }
  section[data-testid="stSidebar"] { background: #0c1122; border-right: 1px solid #1e2740; }

  .hero { display: flex; align-items: center; gap: 18px; margin-bottom: 6px; }
  .hero .shield { font-size: 44px; filter: drop-shadow(0 0 18px rgba(88,163,255,.55)); }
  .hero h1 { font-size: 2.15rem; margin: 0; letter-spacing: -.5px; }
  .hero .tag { color: #9fb0cc; font-size: .95rem; margin-top: 2px; }
  .pills { display: flex; gap: 8px; flex-wrap: wrap; margin: 14px 0 22px; }
  .pill { font-size: .75rem; padding: 5px 11px; border-radius: 999px;
          background: rgba(88,163,255,.10); border: 1px solid rgba(88,163,255,.32); color: #a8c7ff; }
  .pill.ok { background: rgba(47,191,113,.10); border-color: rgba(47,191,113,.35); color: #7ee2a8; }
  .pill.warn { background: rgba(245,165,36,.10); border-color: rgba(245,165,36,.35); color: #ffc46b; }

  .risk-banner { display: flex; justify-content: space-between; align-items: center;
                 border-radius: 16px; padding: 22px 26px; margin: 6px 0 10px;
                 border: 1px solid; }
  .risk-banner.high { background: linear-gradient(100deg, rgba(255,90,95,.20), rgba(255,90,95,.04));
                      border-color: rgba(255,90,95,.55); }
  .risk-banner.medium { background: linear-gradient(100deg, rgba(245,165,36,.18), rgba(245,165,36,.04));
                        border-color: rgba(245,165,36,.5); }
  .risk-banner.low { background: linear-gradient(100deg, rgba(47,191,113,.18), rgba(47,191,113,.04));
                     border-color: rgba(47,191,113,.5); }
  .risk-banner .level { font-size: 1.65rem; font-weight: 800; letter-spacing: .5px; }
  .risk-banner .sub { color: #cdd8ea; font-size: .95rem; margin-top: 4px; }
  .risk-banner .score { font-size: 2.6rem; font-weight: 800; line-height: 1; text-align: right; }
  .risk-banner .score small { font-size: .95rem; font-weight: 500; color: #93a4c1; }

  .meter { height: 9px; border-radius: 99px; background: #1a2338; overflow: hidden; margin: 0 0 18px; }
  .meter > div { height: 100%; border-radius: 99px; }

  .flag { border-left: 3px solid #ff5a5f; background: #101728; border-radius: 0 12px 12px 0;
          padding: 14px 18px; margin-bottom: 10px; }
  .flag.high { border-left-color: #ff8c42; }
  .flag.medium { border-left-color: #f5a524; }
  .flag.low { border-left-color: #6b7a99; }
  .flag .top { display: flex; justify-content: space-between; gap: 12px; align-items: baseline; }
  .flag .title { font-weight: 650; font-size: 1.0rem; }
  .flag .sev { font-size: .68rem; letter-spacing: .8px; color: #ff9ba0; text-transform: uppercase;
               white-space: nowrap; }
  .flag .quote { margin: 8px 0 6px; padding: 8px 12px; background: #0a1020; border-radius: 8px;
                 color: #ffd9a8; font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
                 font-size: .82rem; }
  .flag .why { color: #a9b8d0; font-size: .88rem; line-height: 1.5; }

  .step { background: #101728; border: 1px solid #1e2740; border-radius: 12px; padding: 16px 18px;
          height: 100%; }
  .step .n { color: #6ea8ff; font-weight: 800; font-size: .8rem; letter-spacing: 1px; }
  .step h4 { margin: 6px 0 6px; font-size: 1rem; }
  .step p { color: #a9b8d0; font-size: .87rem; line-height: 1.5; margin: 0; }

  .meta { color: #7f8faa; font-size: .78rem; margin-top: 14px; }
  div[data-testid="stMetricValue"] { color: #e8edf7; }
  .stButton > button { border-radius: 10px; }
</style>
""",
    unsafe_allow_html=True,
)


def esc(value: object) -> str:
    return html.escape(str(value or ""))


def load_sample(text: str) -> None:
    st.session_state["message"] = text


# --------------------------------------------------------------------------------------
# Sidebar — engine status and demo controls
# --------------------------------------------------------------------------------------

models = engine.list_models()
online = engine.engine_online()
default_model = engine.pick_model(models)

with st.sidebar:
    st.markdown("### ⚙️ Local engine")

    if online and models:
        st.markdown(
            f'<span class="pill ok">● Ollama connected</span> '
            f'<span class="pill">127.0.0.1 only</span>',
            unsafe_allow_html=True,
        )
    elif online:
        st.markdown('<span class="pill warn">● Ollama up, no model</span>', unsafe_allow_html=True)
        st.caption("Pull a model: `ollama pull gemma3:4b`")
    else:
        st.markdown('<span class="pill warn">● Ollama offline</span>', unsafe_allow_html=True)
        st.caption("Start it with `ollama serve`. Rules engine still works.")

    model = st.selectbox(
        "Model",
        options=models or [default_model],
        index=(models.index(default_model) if default_model in models else 0),
        help="Any local model works. Gemma is the project default; llama3.2 is a good fallback.",
    )
    use_ai = st.toggle("Use local AI", value=True, help="Off = deterministic rules engine only.")

    st.divider()
    st.markdown("### 🧪 Demo messages")
    st.caption("Click to load, then hit Analyse.")
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
    st.markdown("### 🔒 Privacy")
    st.caption(
        "This app has no cloud dependency. Its only network call is to "
        f"`{engine.ollama_host()}`, which runs on this laptop. Disconnect Wi-Fi and it still works."
    )

# --------------------------------------------------------------------------------------
# Header
# --------------------------------------------------------------------------------------

st.markdown(
    """
<div class="hero">
  <div class="shield">🛡️</div>
  <div>
    <h1>ScamShield AI</h1>
    <div class="tag">Paste a job offer. Know if it is a scam — before you send a single rupee.</div>
  </div>
</div>
<div class="pills">
  <span class="pill ok">100% offline</span>
  <span class="pill">Agent Skill · job-scam-detector v1.0</span>
  <span class="pill">Nothing leaves your laptop</span>
</div>
""",
    unsafe_allow_html=True,
)

tab_scan, tab_how, tab_skill = st.tabs(["🔍 Analyse a message", "🧠 How it works", "📜 Agent Skill"])

with tab_scan:
    message = st.text_area(
        "Suspicious message",
        key="message",
        height=230,
        placeholder=(
            "Paste the WhatsApp message, email or DM here…\n\n"
            "e.g. “Dear Candidate, Dubai hotel job, visa fee Rs 35,000, send on JazzCash…”"
        ),
        label_visibility="collapsed",
    )

    left, right = st.columns([1, 3])
    with left:
        run = st.button("Analyse message", type="primary", use_container_width=True)
    with right:
        st.caption(
            "Your text is processed by the model on this machine. No upload, no logging, no cloud."
        )

    if run:
        with st.spinner("Reading the message locally…"):
            st.session_state["result"] = engine.analyze(
                message, model=model, use_ai=use_ai and online
            )
        st.session_state["analysed_text"] = message

    result = st.session_state.get("result")
    if result is not None:
        st.divider()
        cls, color, guidance = RISK_STYLE.get(result.risk_level, RISK_STYLE["LOW"])
        verdict_label = {
            "scam": "This is almost certainly a scam.",
            "suspicious": "This message is suspicious.",
            "likely_legitimate": "No scam pattern detected.",
            "unclear": "Not enough to judge.",
        }.get(result.verdict, result.verdict.replace("_", " ").capitalize())

        st.markdown(
            f"""
<div class="risk-banner {cls}">
  <div>
    <div class="level" style="color:{color}">{esc(result.risk_level)} RISK</div>
    <div class="sub">{esc(verdict_label)} {esc(guidance)}</div>
  </div>
  <div class="score" style="color:{color}">{result.risk_score}<small>/100</small></div>
</div>
<div class="meter"><div style="width:{result.risk_score}%;background:{color}"></div></div>
""",
            unsafe_allow_html=True,
        )

        st.markdown(f"#### {esc(result.headline)}")
        if result.summary:
            st.markdown(
                f'<p style="color:#c3cfe2;font-size:.98rem;line-height:1.65">{esc(result.summary)}</p>',
                unsafe_allow_html=True,
            )

        if result.error:
            st.warning(f"AI engine message: {result.error}")

        col_flags, col_actions = st.columns([1.35, 1])

        with col_flags:
            st.markdown(f"##### 🚩 Red flags ({len(result.red_flags)})")
            if result.red_flags:
                cards = []
                for flag in result.red_flags:
                    quote = (
                        f'<div class="quote">“{esc(flag.evidence)}”</div>'
                        if flag.evidence
                        else ""
                    )
                    cards.append(
                        f'<div class="flag {esc(flag.severity)}">'
                        f'<div class="top"><span class="title">{esc(flag.title)}</span>'
                        f'<span class="sev">{esc(flag.severity)}</span></div>'
                        f"{quote}"
                        f'<div class="why">{esc(flag.why_it_matters)}</div>'
                        f"</div>"
                    )
                st.markdown("".join(cards), unsafe_allow_html=True)
            else:
                st.success("The message shows none of the known scam patterns.")

            if result.positive_signals:
                st.markdown("##### ✅ What looks legitimate")
                for item in result.positive_signals:
                    st.markdown(f"- {esc(item)}")

        with col_actions:
            st.markdown("##### ✅ What to do now")
            actions = result.recommended_actions or [
                "Do not send money or documents until you verify the employer."
            ]
            st.markdown(
                "".join(
                    f'<div style="display:flex;gap:10px;margin-bottom:11px;color:#dbe4f2;'
                    f'font-size:.9rem;line-height:1.5">'
                    f'<span style="color:#6ea8ff;font-weight:700">{i}.</span>'
                    f"<span>{esc(a)}</span></div>"
                    for i, a in enumerate(actions, 1)
                ),
                unsafe_allow_html=True,
            )

            if result.questions_to_ask:
                st.markdown("##### 🎯 Ask them this")
                st.markdown(
                    "".join(
                        f'<div style="color:#a9b8d0;font-size:.86rem;margin-bottom:8px;'
                        f'line-height:1.5">↳ {esc(q)}</div>'
                        for q in result.questions_to_ask
                    ),
                    unsafe_allow_html=True,
                )

        with st.expander("🔬 Evidence the rules engine matched"):
            if result.rule_hits:
                for hit in result.rule_hits:
                    st.markdown(
                        f"**{esc(hit.label)}** · severity `{esc(hit.severity)}` · weight `{hit.weight}`"
                    )
                    for ev in hit.evidence:
                        st.code(ev, language=None)
            else:
                st.caption("No deterministic pattern matched. The verdict rests on the model's reading.")

        engine_label = (
            f"🧠 {esc(result.model)} via Ollama (localhost)"
            if result.engine == "ollama"
            else "⚙️ rules engine only"
        )
        st.markdown(
            f'<div class="meta">{engine_label} · ⏱ {result.latency_ms / 1000:.1f}s · '
            f"🚩 {len(result.rule_hits)} rule signal(s) · "
            f"confidence: {esc(result.confidence)} · "
            f"category: {esc(result.category.replace('_', ' '))}</div>",
            unsafe_allow_html=True,
        )

with tab_how:
    st.markdown("#### Three layers, one verdict")
    cols = st.columns(3)
    steps = [
        (
            "01 · RULES",
            "Deterministic evidence",
            "Twelve fraud patterns — upfront fees, personal wallets, guaranteed visas, identity "
            "harvesting, lookalike domains — scan the text and quote the exact words that matched. "
            "No model can skip these.",
        ),
        (
            "02 · AGENT SKILL",
            "Local reasoning",
            "Gemma reads the same evidence through SKILL.md: a fraud investigator's playbook with "
            "a strict JSON contract. It weighs context, drops false positives, and writes the "
            "advice a human would give.",
        ),
        (
            "03 · MERGE",
            "One defensible verdict",
            "The final score is the higher of the rules score and the model's score. Any critical "
            "signal the model missed is restored, so a fee demand can never be waved through.",
        ),
    ]
    for col, (n, title, body) in zip(cols, steps):
        with col:
            st.markdown(
                f'<div class="step"><div class="n">{n}</div><h4>{title}</h4><p>{body}</p></div>',
                unsafe_allow_html=True,
            )

    st.markdown("##### The privacy argument")
    st.markdown(
        "Scam messages carry names, phone numbers, CNIC copies and bank details. Sending them to a "
        "cloud chatbot is how victims get re-victimised. ScamShield runs the model **on the device**: "
        f"the only socket it opens is `{engine.ollama_host()}`. Turn off Wi-Fi during the demo and "
        "nothing changes, because nothing was ever sent outside."
    )

with tab_skill:
    st.markdown("#### `skills/job-scam-detector/SKILL.md`")
    st.caption(
        "The brain of the project. Editable, versioned, testable — swap the playbook and the "
        "agent changes behaviour without touching a line of Python."
    )
    st.code(engine.load_skill(), language="markdown", line_numbers=False)
