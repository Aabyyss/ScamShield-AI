"""Presentation layer: two hand-tuned palettes and the HTML/CSS they render.

Streamlit's built-in theme is fixed at startup, so ScamShield carries its own palette in a
CSS-variable block and overrides the widgets it uses. That gives a genuinely bright, high
contrast light mode (the default) and an equally deliberate dark mode, switchable live.
No web fonts, no CDN, no images: the page must render with Wi-Fi off.
"""

from __future__ import annotations

import html
from typing import Iterable, Sequence

from .entities import Entity
from .learning import SimilarCase

LIGHT = {
    "bg": "#f3f6fc",
    "glow1": "rgba(37,99,235,.13)",
    "glow2": "rgba(13,148,136,.10)",
    "surface": "#ffffff",
    "surface2": "#eef3fb",
    "text": "#16223a",
    "heading": "#0a1628",
    "muted": "#5b6d8b",
    "line": "#dfe7f4",
    "accent": "#2563eb",
    "accent2": "#1d4ed8",
    "accent_text": "#ffffff",
    "accent_soft": "rgba(37,99,235,.08)",
    "accent_line": "rgba(37,99,235,.22)",
    "shadow": "0 14px 38px rgba(15,35,70,.09)",
    "shadow_sm": "0 2px 10px rgba(15,35,70,.06)",
    "high": "#cf2a20",
    "high_soft": "rgba(207,42,32,.07)",
    "high_line": "rgba(207,42,32,.24)",
    "medium": "#a85a06",
    "medium_soft": "rgba(168,90,6,.08)",
    "medium_line": "rgba(168,90,6,.24)",
    "low": "#08744a",
    "low_soft": "rgba(8,116,74,.08)",
    "low_line": "rgba(8,116,74,.24)",
    "quote_bg": "#f7faff",
    "quote_text": "#7a4b09",
    "track": "#e7eefa",
    "chip": "#f1f5fc",
}

DARK = {
    "bg": "#070c17",
    "glow1": "rgba(88,163,255,.16)",
    "glow2": "rgba(45,212,191,.10)",
    "surface": "#0f1729",
    "surface2": "#121c31",
    "text": "#e8eefb",
    "heading": "#ffffff",
    "muted": "#96a6c2",
    "line": "#1e2a44",
    "accent": "#6ea8ff",
    "accent2": "#9cc4ff",
    "accent_text": "#06101f",
    "accent_soft": "rgba(110,168,255,.10)",
    "accent_line": "rgba(110,168,255,.30)",
    "shadow": "0 16px 40px rgba(0,0,0,.4)",
    "shadow_sm": "0 2px 12px rgba(0,0,0,.28)",
    "high": "#ff7a7a",
    "high_soft": "rgba(255,90,95,.12)",
    "high_line": "rgba(255,90,95,.42)",
    "medium": "#f7b955",
    "medium_soft": "rgba(245,165,36,.12)",
    "medium_line": "rgba(245,165,36,.38)",
    "low": "#4ade9f",
    "low_soft": "rgba(52,211,153,.12)",
    "low_line": "rgba(52,211,153,.34)",
    "quote_bg": "#0a1220",
    "quote_text": "#ffd9a8",
    "track": "#1b2740",
    "chip": "#131f36",
}

PALETTES = {"light": LIGHT, "dark": DARK}
_SEVERITY_CLASS = {"critical": "high", "high": "high", "medium": "medium", "low": "low"}


def esc(value: object) -> str:
    return html.escape(str(value or ""))


def css(mode: str = "light") -> str:
    p = PALETTES.get(mode, LIGHT)
    variables = "\n".join(f"    --ss-{key}: {value};" for key, value in p.items())
    return f"""
<style>
  :root {{
{variables}
    --ss-radius: 18px;
    --ss-font: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    --ss-mono: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  }}

  html, body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] {{
    background: var(--ss-bg) !important;
    color: var(--ss-text);
    font-family: var(--ss-font);
  }}
  .stApp {{
    background-image:
      radial-gradient(900px 420px at 8% -8%, var(--ss-glow1) 0%, transparent 60%),
      radial-gradient(700px 380px at 96% 4%, var(--ss-glow2) 0%, transparent 62%) !important;
    background-repeat: no-repeat;
  }}
  header[data-testid="stHeader"] {{ background: transparent !important; }}
  [data-testid="stToolbar"] {{ right: 1rem; }}
  .block-container {{ padding-top: 1.9rem; padding-bottom: 3rem; max-width: 1200px; }}

  /* ---------- typography ---------- */
  /* Only structural text: component colours must win over this rule. */
  .stMarkdown, .stMarkdown p, .stMarkdown li,
  label, .stCaption, [data-testid="stCaptionContainer"], [data-testid="stWidgetLabel"] p {{
    color: var(--ss-text);
  }}
  .stMarkdown h1, .stMarkdown h2, .stMarkdown h3, .stMarkdown h4, .stMarkdown h5 {{
    color: var(--ss-heading); letter-spacing: -.2px;
  }}
  .stCaption, [data-testid="stCaptionContainer"] p {{ color: var(--ss-muted) !important; }}
  a, .stMarkdown a {{ color: var(--ss-accent) !important; }}

  /* ---------- sidebar ---------- */
  section[data-testid="stSidebar"] {{
    background: var(--ss-surface2) !important;
    border-right: 1px solid var(--ss-line);
  }}
  section[data-testid="stSidebar"] *,
  section[data-testid="stSidebar"] .stMarkdown p {{ color: var(--ss-text); }}
  section[data-testid="stSidebar"] h3 {{ color: var(--ss-heading); font-size: 1rem; }}
  [data-testid="stSidebarCollapsedControl"] button {{ color: var(--ss-text); }}

  /* ---------- widgets ---------- */
  textarea, input[type="text"], input[type="password"], [data-baseweb="input"],
  [data-baseweb="base-input"], [data-baseweb="select"] > div {{
    background: var(--ss-surface) !important;
    color: var(--ss-text) !important;
    border-color: var(--ss-line) !important;
    border-radius: 12px !important;
  }}
  textarea::placeholder, input::placeholder {{ color: var(--ss-muted) !important; opacity: .75; }}
  textarea:focus, [data-baseweb="input"]:focus-within, [data-baseweb="select"] > div:focus-within {{
    border-color: var(--ss-accent) !important;
    box-shadow: 0 0 0 3px var(--ss-accent_soft) !important;
  }}
  [data-baseweb="popover"], [data-baseweb="menu"], [data-baseweb="select"] ul {{
    background: var(--ss-surface) !important; color: var(--ss-text) !important;
    border: 1px solid var(--ss-line) !important;
  }}
  /* The selectbox paints its container with the base theme, leaving a light strip behind
     the arrow in dark mode. */
  [data-testid="stSelectbox"] > div,
  [data-testid="stSelectbox"] [role="group"] {{
    background: var(--ss-surface) !important;
    border-radius: 12px !important;
  }}
  [data-testid="stSelectbox"] svg {{
    fill: var(--ss-muted) !important;
    color: var(--ss-muted) !important;
  }}
  [data-baseweb="menu"] li {{ color: var(--ss-text) !important; }}
  [data-baseweb="menu"] li:hover {{ background: var(--ss-accent_soft) !important; }}

  .stButton > button, .stDownloadButton > button,
  button[data-testid="stBaseButton-secondary"] {{
    background: var(--ss-surface) !important;
    color: var(--ss-text) !important;
    border: 1px solid var(--ss-line) !important;
    border-radius: 12px !important;
    font-weight: 600;
    box-shadow: var(--ss-shadow_sm);
    transition: transform .12s ease, border-color .12s ease, box-shadow .12s ease;
  }}
  .stButton > button:hover, .stDownloadButton > button:hover {{
    border-color: var(--ss-accent) !important;
    color: var(--ss-accent) !important;
    transform: translateY(-1px);
  }}
  .stButton > button[kind="primary"], button[data-testid="stBaseButton-primary"] {{
    background: linear-gradient(120deg, var(--ss-accent), var(--ss-accent2)) !important;
    color: var(--ss-accent_text) !important;
    border: none !important;
    box-shadow: 0 10px 24px var(--ss-accent_line);
  }}
  .stButton > button[kind="primary"]:hover {{
    color: var(--ss-accent_text) !important; filter: brightness(1.05);
  }}

  [data-testid="stSegmentedControl"] button, [data-testid="stPills"] button {{
    background: var(--ss-surface) !important;
    color: var(--ss-muted) !important;
    border-color: var(--ss-line) !important;
  }}
  [data-testid="stSegmentedControl"] button[aria-checked="true"],
  [data-testid="stPills"] button[aria-checked="true"] {{
    background: var(--ss-accent_soft) !important;
    color: var(--ss-accent) !important;
    border-color: var(--ss-accent_line) !important;
  }}

  .stTabs [data-baseweb="tab-list"] {{
    gap: 6px; background: var(--ss-surface2); padding: 6px; border-radius: 14px;
    border: 1px solid var(--ss-line);
  }}
  .stTabs [data-baseweb="tab"] {{
    height: 40px; border-radius: 10px; color: var(--ss-muted) !important;
    background: transparent !important; font-weight: 600; padding: 0 16px;
  }}
  .stTabs [aria-selected="true"] {{
    background: var(--ss-surface) !important; color: var(--ss-accent) !important;
    box-shadow: var(--ss-shadow_sm);
  }}
  .stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] {{ background: transparent !important; }}

  [data-testid="stExpander"] details {{
    background: var(--ss-surface); border: 1px solid var(--ss-line);
    border-radius: 14px; box-shadow: var(--ss-shadow_sm);
  }}
  [data-testid="stExpander"] summary {{
    color: var(--ss-text) !important; font-weight: 600; border-radius: 14px;
  }}
  [data-testid="stExpander"] summary:hover {{ color: var(--ss-accent) !important; }}

  [data-testid="stAlert"] {{
    background: var(--ss-surface) !important; color: var(--ss-text) !important;
    border: 1px solid var(--ss-line) !important; border-radius: 14px;
  }}
  [data-testid="stAlert"] * {{ color: var(--ss-text) !important; }}

  [data-testid="stCode"], [data-testid="stCode"] pre, .stMarkdown pre {{
    background: var(--ss-quote_bg) !important; border: 1px solid var(--ss-line) !important;
    border-radius: 12px !important;
  }}
  [data-testid="stCode"] code, .stMarkdown pre code, .stMarkdown code {{
    color: var(--ss-text) !important; font-family: var(--ss-mono) !important;
  }}
  /* Inline code in captions inherits the base theme's light chip, which glares in dark mode. */
  .stMarkdown :not(pre) > code {{
    background: var(--ss-chip) !important;
    border: 1px solid var(--ss-line) !important;
    border-radius: 6px !important;
    padding: 1px 5px !important;
  }}
  hr, [data-testid="stDivider"] {{ border-color: var(--ss-line) !important; }}
  [data-testid="stSpinner"] * {{ color: var(--ss-muted) !important; }}
  [data-testid="stToast"] {{
    background: var(--ss-surface) !important; color: var(--ss-text) !important;
    border: 1px solid var(--ss-line) !important;
  }}

  div[role="dialog"], [data-testid="stDialog"] > div {{
    background: var(--ss-surface) !important;
    color: var(--ss-text);
    border: 1px solid var(--ss-line);
    border-radius: 20px;
    box-shadow: var(--ss-shadow);
  }}
  div[role="dialog"] * {{ color: var(--ss-text); }}
  div[role="dialog"] h2 {{ color: var(--ss-heading) !important; }}

  /* ---------- hero ---------- */
  .ss-hero {{ display: flex; gap: 20px; align-items: center; padding: 6px 0 4px; }}
  .ss-shield {{
    width: 66px; height: 66px; flex: 0 0 66px; display: grid; place-items: center;
    font-size: 30px; border-radius: 20px; overflow: hidden;
    background: linear-gradient(140deg, var(--ss-accent), var(--ss-accent2));
    box-shadow: 0 12px 28px var(--ss-accent_line);
  }}
  .ss-shield img {{ width: 100%; height: 100%; display: block; object-fit: cover; }}
  .ss-eyebrow {{
    font-size: .68rem; letter-spacing: 2px; font-weight: 800;
    color: var(--ss-accent); text-transform: uppercase; margin-bottom: 4px;
  }}
  .ss-hero h1 {{
    margin: 0; font-size: 2.05rem; line-height: 1.15; letter-spacing: -1px;
    color: var(--ss-heading); font-weight: 800;
  }}
  .ss-hero h1 .ss-grad {{
    background: linear-gradient(100deg, var(--ss-accent), var(--ss-accent2));
    -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent;
  }}
  .ss-hero p {{ margin: 8px 0 0; color: var(--ss-muted); font-size: .96rem; max-width: 62ch; }}

  .ss-pills {{ display: flex; gap: 8px; flex-wrap: wrap; margin: 16px 0 20px; }}
  .ss-pill {{
    font-size: .74rem; font-weight: 650; padding: 6px 12px; border-radius: 999px;
    background: var(--ss-surface); border: 1px solid var(--ss-line);
    color: var(--ss-muted); box-shadow: var(--ss-shadow_sm); white-space: nowrap;
  }}
  .ss-pill.ok {{ color: var(--ss-low); border-color: var(--ss-low_line); background: var(--ss-low_soft); }}
  .ss-pill.warn {{ color: var(--ss-medium); border-color: var(--ss-medium_line); background: var(--ss-medium_soft); }}
  .ss-pill.accent {{ color: var(--ss-accent); border-color: var(--ss-accent_line); background: var(--ss-accent_soft); }}

  /* ---------- cards ---------- */
  .ss-card {{
    background: var(--ss-surface); border: 1px solid var(--ss-line);
    border-radius: var(--ss-radius); padding: 18px 20px; box-shadow: var(--ss-shadow_sm);
  }}
  .ss-section {{
    display: flex; align-items: baseline; justify-content: space-between; gap: 12px;
    margin: 22px 0 10px;
  }}
  .ss-section h3 {{
    margin: 0; font-size: 1.02rem; color: var(--ss-heading); letter-spacing: -.2px;
  }}
  .ss-section .ss-count {{ color: var(--ss-muted); font-size: .8rem; }}

  .ss-verdict {{
    display: flex; gap: 24px; align-items: center; justify-content: space-between;
    border-radius: 20px; padding: 22px 26px; border: 1px solid var(--ss-line);
    box-shadow: var(--ss-shadow); margin: 6px 0 4px; position: relative; overflow: hidden;
  }}
  .ss-verdict::before {{
    content: ""; position: absolute; inset: 0 auto 0 0; width: 6px; background: var(--ss-level);
  }}
  .ss-verdict.high {{ background: linear-gradient(105deg, var(--ss-high_soft), var(--ss-surface) 62%); --ss-level: var(--ss-high); }}
  .ss-verdict.medium {{ background: linear-gradient(105deg, var(--ss-medium_soft), var(--ss-surface) 62%); --ss-level: var(--ss-medium); }}
  .ss-verdict.low {{ background: linear-gradient(105deg, var(--ss-low_soft), var(--ss-surface) 62%); --ss-level: var(--ss-low); }}
  .ss-badge {{
    display: inline-flex; align-items: center; gap: 7px; font-size: .76rem; font-weight: 800;
    letter-spacing: 1.1px; text-transform: uppercase; padding: 6px 12px; border-radius: 999px;
    background: var(--ss-surface); border: 1px solid var(--ss-level); color: var(--ss-level);
  }}
  .ss-verdict h2 {{
    margin: 12px 0 6px; font-size: 1.42rem; line-height: 1.3; color: var(--ss-heading);
    letter-spacing: -.4px;
  }}
  .ss-verdict .ss-summary {{
    margin: 0; color: var(--ss-muted); font-size: .92rem; line-height: 1.6; max-width: 68ch;
  }}
  .ss-verdict-meta {{
    margin-top: 14px; display: flex; gap: 8px; flex-wrap: wrap; color: var(--ss-muted);
    font-size: .76rem;
  }}
  .ss-verdict-meta span {{
    background: var(--ss-chip); border: 1px solid var(--ss-line); padding: 4px 9px;
    border-radius: 999px;
  }}
  .ss-ring {{ flex: 0 0 128px; display: grid; place-items: center; }}

  .ss-flag {{
    background: var(--ss-surface); border: 1px solid var(--ss-line);
    border-left: 4px solid var(--ss-level); border-radius: 6px 14px 14px 6px;
    padding: 14px 18px; margin-bottom: 10px; box-shadow: var(--ss-shadow_sm);
    --ss-level: var(--ss-high);
  }}
  .ss-flag.critical, .ss-flag.high {{ --ss-level: var(--ss-high); }}
  .ss-flag.medium {{ --ss-level: var(--ss-medium); }}
  .ss-flag.low {{ --ss-level: var(--ss-low); }}
  .ss-flag .ss-flag-top {{
    display: flex; gap: 12px; justify-content: space-between; align-items: baseline;
  }}
  .ss-flag .ss-flag-title {{ font-weight: 700; font-size: .98rem; color: var(--ss-heading); }}
  .ss-flag .ss-sev {{
    font-size: .66rem; font-weight: 800; letter-spacing: 1px; text-transform: uppercase;
    color: var(--ss-level); background: var(--ss-chip); border: 1px solid var(--ss-line);
    padding: 3px 8px; border-radius: 999px; white-space: nowrap;
  }}
  .ss-flag .ss-quote {{
    margin: 10px 0 8px; padding: 9px 13px; border-radius: 10px;
    background: var(--ss-quote_bg); border: 1px dashed var(--ss-line);
    color: var(--ss-quote_text); font-family: var(--ss-mono); font-size: .81rem;
    line-height: 1.55; word-break: break-word;
  }}
  .ss-flag .ss-why {{ color: var(--ss-muted); font-size: .87rem; line-height: 1.55; }}
  .ss-flag .ss-learn {{
    margin-top: 8px; font-size: .74rem; color: var(--ss-accent);
    background: var(--ss-accent_soft); display: inline-block; padding: 3px 8px;
    border-radius: 6px;
  }}

  .ss-entity {{
    display: flex; gap: 14px; align-items: flex-start; padding: 12px 14px;
    border: 1px solid var(--ss-line); border-radius: 12px; margin-bottom: 8px;
    background: var(--ss-surface);
  }}
  .ss-entity .ss-entity-body {{ flex: 1; min-width: 0; }}
  .ss-entity .ss-entity-value {{
    font-family: var(--ss-mono); font-size: .82rem; color: var(--ss-heading);
    word-break: break-all; font-weight: 600;
  }}
  .ss-entity .ss-entity-kind {{ color: var(--ss-muted); font-size: .72rem; margin-top: 2px; }}
  .ss-entity .ss-entity-why {{ color: var(--ss-muted); font-size: .8rem; margin-top: 5px; line-height: 1.5; }}
  .ss-entity .ss-entity-risk {{
    font-size: .66rem; font-weight: 800; letter-spacing: .8px; text-transform: uppercase;
    padding: 4px 8px; border-radius: 999px; white-space: nowrap;
    border: 1px solid var(--ss-line); color: var(--ss-muted); background: var(--ss-chip);
  }}
  .ss-entity.risk-high .ss-entity-risk {{ color: var(--ss-high); border-color: var(--ss-high_line); background: var(--ss-high_soft); }}
  .ss-entity.risk-medium .ss-entity-risk {{ color: var(--ss-medium); border-color: var(--ss-medium_line); background: var(--ss-medium_soft); }}
  .ss-entity.risk-low .ss-entity-risk {{ color: var(--ss-low); border-color: var(--ss-low_line); background: var(--ss-low_soft); }}

  .ss-steps {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }}
  @media (max-width: 900px) {{ .ss-steps {{ grid-template-columns: 1fr; }} }}
  .ss-step {{
    background: var(--ss-surface); border: 1px solid var(--ss-line); border-radius: 14px;
    padding: 16px 18px; box-shadow: var(--ss-shadow_sm);
  }}
  .ss-step .ss-num {{
    font-size: .7rem; font-weight: 800; letter-spacing: 1.4px; color: var(--ss-accent);
  }}
  .ss-step h4 {{ margin: 6px 0 4px; font-size: .98rem; color: var(--ss-heading); }}
  .ss-step p {{ margin: 0; color: var(--ss-muted); font-size: .85rem; line-height: 1.55; }}

  .ss-metrics {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; }}
  @media (max-width: 900px) {{ .ss-metrics {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }} }}
  .ss-metric {{
    background: var(--ss-surface); border: 1px solid var(--ss-line); border-radius: 14px;
    padding: 14px 16px; box-shadow: var(--ss-shadow_sm);
  }}
  .ss-metric .ss-value {{
    font-size: 1.5rem; font-weight: 800; color: var(--ss-heading); line-height: 1.1;
  }}
  .ss-metric .ss-label {{ color: var(--ss-muted); font-size: .78rem; margin-top: 4px; }}

  .ss-note {{
    border: 1px dashed var(--ss-line); border-radius: 12px; padding: 12px 14px;
    color: var(--ss-muted); font-size: .84rem; background: var(--ss-chip); line-height: 1.55;
  }}
  .ss-note strong {{ color: var(--ss-text); }}

  .ss-table {{ width: 100%; border-collapse: collapse; font-size: .83rem; }}
  .ss-table th {{
    text-align: left; color: var(--ss-muted); font-weight: 700; font-size: .72rem;
    letter-spacing: .6px; text-transform: uppercase; padding: 8px 10px;
    border-bottom: 1px solid var(--ss-line);
  }}
  .ss-table td {{
    padding: 9px 10px; border-bottom: 1px solid var(--ss-line); color: var(--ss-text);
  }}
  .ss-table tr:last-child td {{ border-bottom: none; }}
  .ss-table .ss-mono {{ font-family: var(--ss-mono); font-size: .78rem; }}
  .ss-table .ss-dim {{ color: var(--ss-muted); }}

  .ss-flow {{ color: var(--ss-muted); font-size: .82rem; line-height: 1.7; }}
  .ss-kbd {{
    font-family: var(--ss-mono); font-size: .76rem; background: var(--ss-chip);
    border: 1px solid var(--ss-line); border-bottom-width: 2px; border-radius: 6px;
    padding: 1px 6px; color: var(--ss-text);
  }}
</style>
"""


def hero(status_pills: Sequence[tuple[str, str]] = (), logo_b64: str = "") -> str:
    pills = "".join(
        f'<span class="ss-pill {esc(cls)}">{esc(text)}</span>' for text, cls in status_pills
    )
    shield = (
        f'<div class="ss-shield"><img src="data:image/png;base64,{logo_b64}" '
        'alt="ScamShield AI logo"></div>'
        if logo_b64
        else '<div class="ss-shield">🛡️</div>'
    )
    return f"""
<div class="ss-hero">
  {shield}
  <div>
    <div class="ss-eyebrow">Offline job-fraud detector</div>
    <h1>Know a job scam <span class="ss-grad">before you pay.</span></h1>
    <p>Paste the WhatsApp message or email you received. ScamShield quotes the exact red flags,
       explains them in plain language, and tells you what to do next — all on this laptop.</p>
  </div>
</div>
<div class="ss-pills">{pills}</div>
"""


def _ring(score: int, color: str) -> str:
    radius = 52
    circumference = 2 * 3.14159 * radius
    offset = circumference * (1 - max(0, min(100, score)) / 100)
    return f"""
<svg viewBox="0 0 120 120" width="122" height="122" role="img" aria-label="Risk score {score} out of 100">
  <circle cx="60" cy="60" r="{radius}" fill="none" stroke="var(--ss-track)" stroke-width="10"/>
  <circle cx="60" cy="60" r="{radius}" fill="none" stroke="{color}" stroke-width="10"
          stroke-linecap="round" stroke-dasharray="{circumference:.1f}"
          stroke-dashoffset="{offset:.1f}" transform="rotate(-90 60 60)"/>
  <text x="60" y="58" text-anchor="middle" font-size="30" font-weight="800"
        font-family="{font}" fill="{color}">{score}</text>
  <text x="60" y="78" text-anchor="middle" font-size="10" fill="var(--ss-muted)">out of 100</text>
</svg>
"""


font = "ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif"


def verdict(result) -> str:
    cls = {"HIGH": "high", "MEDIUM": "medium"}.get(result.risk_level, "low")
    level_label = {"HIGH": "High risk", "MEDIUM": "Medium risk"}.get(
        result.risk_level, "Low risk"
    )
    icon = {"high": "🔴", "medium": "🟠", "low": "🟢"}[cls]
    color = {"high": "var(--ss-high)", "medium": "var(--ss-medium)", "low": "var(--ss-low)"}[cls]
    meta = [
        f"confidence {esc(result.confidence)}",
        f"{len(result.red_flags)} flag(s)",
        "local AI · " + esc(result.model) if result.engine == "ollama" and result.model else "rules engine",
        f"{result.latency_ms / 1000:.1f}s",
        "no network used",
    ]
    if result.discarded_claims:
        meta.append(f"{result.discarded_claims} unverified model claim(s) discarded")
    meta_html = "".join(f"<span>{m}</span>" for m in meta)
    return f"""
<div class="ss-verdict {cls}">
  <div>
    <span class="ss-badge">{icon} {level_label}</span>
    <h2>{esc(result.headline)}</h2>
    <p class="ss-summary">{esc(result.summary)}</p>
    <div class="ss-verdict-meta">{meta_html}</div>
  </div>
  <div class="ss-ring">{_ring(int(result.risk_score), color)}</div>
</div>
"""


def section(title: str, count: str = "") -> str:
    count_html = f'<span class="ss-count">{esc(count)}</span>' if count else ""
    return f'<div class="ss-section"><h3>{esc(title)}</h3>{count_html}</div>'


def flags(flag_list: Iterable) -> str:
    cards = []
    for flag in flag_list:
        severity = _SEVERITY_CLASS.get(flag.severity, "medium")
        # Rules-only runs must not be labelled as if the model agreed with them.
        if flag.source == "rules":
            source = "rule"
        elif flag.corroborated:
            source = "rule + AI"
        else:
            source = "AI · unverified"
        quote = (
            f'<div class="ss-quote">“{esc(flag.evidence)}”</div>' if flag.evidence else ""
        )
        learn = (
            f'<div class="ss-learn">🧠 {esc(flag.learned_note)}</div>'
            if getattr(flag, "learned_note", "")
            else ""
        )
        why = (
            f'<div class="ss-why">{esc(flag.why_it_matters)}</div>'
            if flag.why_it_matters
            else ""
        )
        cards.append(
            f'<div class="ss-flag {severity}">'
            f'<div class="ss-flag-top"><span class="ss-flag-title">{esc(flag.title)}</span>'
            f'<span class="ss-sev">{esc(flag.severity)} · {esc(source)}</span></div>'
            f"{quote}{why}{learn}</div>"
        )
    return "".join(cards)


def entities(entity_list: Iterable[Entity]) -> str:
    icons = {"email": "✉️", "url": "🔗", "domain": "🌐", "phone": "📞", "personal": "🪪"}
    rows = []
    for entity in entity_list:
        why = " ".join(entity.reasons[:2])
        rows.append(
            f'<div class="ss-entity risk-{esc(entity.risk)}">'
            f'<div style="font-size:1.1rem">{icons.get(entity.kind, "•")}</div>'
            f'<div class="ss-entity-body">'
            f'<div class="ss-entity-value">{esc(entity.value)}</div>'
            f'<div class="ss-entity-kind">{esc(entity.label)}</div>'
            f'<div class="ss-entity-why">{esc(why)}</div>'
            f"</div>"
            f'<span class="ss-entity-risk">{esc(entity.risk)}</span>'
            f"</div>"
        )
    return "".join(rows)


def similar(cases: Iterable[SimilarCase]) -> str:
    labels = {"HIGH": "🔴 scam", "MEDIUM": "🟠 suspicious", "LOW": "🟢 legitimate"}
    rows = []
    for case in cases:
        rows.append(
            f'<div class="ss-entity">'
            f'<div class="ss-entity-body"><div class="ss-entity-value">'
            f"{case.similarity}% similar wording</div>"
            f'<div class="ss-entity-why">Checked {esc(case.created_at[:10])} — that message was '
            f'{labels.get(case.level, case.level)} ({case.score}/100).</div></div></div>'
        )
    return "".join(rows)


def steps(items: Sequence[tuple[str, str, str]]) -> str:
    cards = "".join(
        f'<div class="ss-step"><div class="ss-num">{esc(num)}</div>'
        f"<h4>{esc(title)}</h4><p>{esc(body)}</p></div>"
        for num, title, body in items
    )
    return f'<div class="ss-steps">{cards}</div>'


def metrics(items: Sequence[tuple[str, str]]) -> str:
    cards = "".join(
        f'<div class="ss-metric"><div class="ss-value">{esc(value)}</div>'
        f'<div class="ss-label">{esc(label)}</div></div>'
        for value, label in items
    )
    return f'<div class="ss-metrics">{cards}</div>'


def note(body: str) -> str:
    return f'<div class="ss-note">{body}</div>'


def table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    head = "".join(f"<th>{esc(h)}</th>" for h in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows
    )
    return f'<table class="ss-table"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'
