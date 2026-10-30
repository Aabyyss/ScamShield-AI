"""Build a submission-ready PDF from docs/PROJECT-REPORT.md.

Markdown -> styled HTML (cover, contents, screenshot gallery) -> headless Chrome/Edge print.
No network access: images are embedded as data URIs and the fonts are system fonts.

    python tools/build_pdf.py

Output: docs/ScamShield-AI-Project-Report.pdf
"""

from __future__ import annotations

import base64
import html
import re
import shutil
import subprocess
import tempfile
from datetime import date
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parent.parent
REPORT = ROOT / "docs" / "PROJECT-REPORT.md"
OUTPUT = ROOT / "docs" / "ScamShield-AI-Project-Report.pdf"
LOGO = ROOT / "assets" / "logo.png"
SCREENSHOTS = [
    ("screenshots/app-home.png", "Home screen with the light theme, demo messages and quick examples"),
    ("screenshots/intro-dialog.png", "Three-step onboarding dialog shown on first launch"),
    ("screenshots/verdict-light.png", "A scam verdict: score ring, quoted red flags and next steps"),
    ("screenshots/verdict-dark-final.png", "The same verdict in the dark theme"),
    ("screenshots/verdict-export.png", "Export controls: the one-page PDF, the full Markdown report and a paste-ready caption"),
]

CHROME_CANDIDATES = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
)


def data_uri(path: Path) -> str:
    suffix = path.suffix.lower().lstrip(".")
    mime = {"jpg": "jpeg", "jpeg": "jpeg", "svg": "svg+xml"}.get(suffix, suffix)
    return f"data:image/{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"


def headings(markdown_text: str) -> list[tuple[int, str]]:
    """Level-2 and level-3 headings, ignoring anything inside fenced code blocks."""
    found: list[tuple[int, str]] = []
    in_fence = False
    for line in markdown_text.splitlines():
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        for level in (2, 3):
            marker = "#" * level + " "
            if line.startswith(marker):
                found.append((level, line[len(marker) :].strip()))
                break
    return found


CSS = """
@page { size: A4; margin: 17mm 15mm 17mm 15mm; }
* { box-sizing: border-box; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body {
  margin: 0; color: #16223a; background: #ffffff;
  font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
  font-size: 9.9pt; line-height: 1.52;
}
h1, h2, h3, h4 { color: #0a1628; font-weight: 700; letter-spacing: -0.2px; }
h2 {
  font-size: 15pt; margin: 20pt 0 7pt; padding-bottom: 3pt;
  border-bottom: 1.6pt solid #dfe7f4; break-after: avoid;
}
h3 { font-size: 11.4pt; margin: 14pt 0 5pt; color: #14315c; break-after: avoid; }
h4 { font-size: 10pt; margin: 11pt 0 4pt; break-after: avoid; }
p { margin: 0 0 6pt; }
a { color: #1d4ed8; text-decoration: none; }
strong { color: #0a1628; }
ul, ol { margin: 2pt 0 7pt 0; padding-left: 15pt; }
li { margin-bottom: 2.5pt; }
hr { border: none; border-top: 1pt solid #e2e8f4; margin: 14pt 0; }

table {
  width: 100%; border-collapse: collapse; margin: 6pt 0 10pt;
  font-size: 8.6pt; line-height: 1.4;
}
th {
  background: #eaf1ff; color: #14315c; text-align: left;
  font-size: 8pt; letter-spacing: 0.3px; text-transform: uppercase;
  padding: 5pt 6pt; border: 0.6pt solid #d7e2f3;
}
td { padding: 4.5pt 6pt; border: 0.6pt solid #e2e8f4; vertical-align: top; }
tbody tr:nth-child(even) td { background: #f8fafd; }
tr { break-inside: avoid; }

pre {
  background: #f6f8fc; border: 0.6pt solid #e2e8f4; border-left: 2.4pt solid #2563eb;
  border-radius: 4pt; padding: 7pt 9pt; margin: 6pt 0 9pt;
  font-size: 8pt; line-height: 1.4; white-space: pre-wrap; word-break: break-word;
  break-inside: avoid;
}
code {
  font-family: Consolas, "SFMono-Regular", Menlo, monospace;
  font-size: 8.6pt; background: #f1f5fb; border-radius: 3pt; padding: 0 2.5pt;
}
pre code { background: none; padding: 0; font-size: 8pt; }
blockquote {
  margin: 7pt 0; padding: 7pt 10pt; background: #f7faff;
  border-left: 2.4pt solid #2563eb; border-radius: 0 4pt 4pt 0; color: #33455f;
}
blockquote p { margin: 0 0 4pt; }
blockquote p:last-child { margin-bottom: 0; }
img { max-width: 100%; }

/* ---------- cover ---------- */
.cover {
  height: 258mm; display: flex; flex-direction: column; justify-content: space-between;
  break-after: page;
}
.cover-top { display: flex; align-items: center; gap: 14pt; }
.cover-logo { width: 58pt; height: 58pt; border-radius: 14pt; }
.cover-kicker {
  color: #2563eb; font-size: 8pt; font-weight: 700; letter-spacing: 2pt; text-transform: uppercase;
}
.cover h1 { font-size: 34pt; line-height: 1.08; margin: 26pt 0 10pt; letter-spacing: -1.2pt; }
.cover .lede { font-size: 12.4pt; color: #4a5d7a; max-width: 135mm; line-height: 1.5; }
.cover .rule { height: 3.2pt; width: 84pt; background: #2563eb; border-radius: 2pt; margin: 20pt 0; }
.cover-meta { width: 100%; font-size: 9pt; border-collapse: collapse; margin-top: 8pt; }
.cover-meta td { border: none; border-top: 0.6pt solid #e2e8f4; padding: 6pt 4pt; }
.cover-meta td:first-child { width: 34mm; color: #6b7d99; text-transform: uppercase; font-size: 7.6pt; letter-spacing: 0.8px; }
.cover-foot { color: #7c8ca6; font-size: 8.4pt; border-top: 0.6pt solid #e2e8f4; padding-top: 8pt; }
.cover-stats { display: flex; gap: 7mm; margin-top: 34pt; }
.cover-stats div {
  flex: 1; border-top: 2.4pt solid #2563eb; padding-top: 7pt;
}
.cover-stats b { display: block; font-size: 19pt; color: #0a1628; letter-spacing: -0.6pt; line-height: 1.1; }
.cover-stats span { display: block; font-size: 8.4pt; color: #6b7d99; margin-top: 3pt; line-height: 1.35; }

/* ---------- contents + gallery ---------- */
.toc { break-after: page; height: 258mm; display: flex; flex-direction: column; }
.toc .reading-guide { margin-top: auto; }
.toc h2 { border: none; margin-top: 0; }
.toc ul { list-style: none; padding: 0; margin: 0; columns: 2; column-gap: 10mm; font-size: 9.2pt; }
.toc li { margin-bottom: 3.4pt; break-inside: avoid; }
.toc li.lvl2 { font-weight: 600; color: #0a1628; margin-top: 5pt; }
.toc li.lvl3 { padding-left: 7pt; color: #55688a; font-size: 8.8pt; margin-bottom: 1.6pt; }
.reading-guide { border-top: 1pt solid #e2e8f4; padding-top: 9pt; }
.reading-guide h3 { font-size: 9pt; text-transform: uppercase; letter-spacing: 1.2pt; color: #2563eb; margin: 0 0 8pt; }
.reading-guide dl { display: flex; flex-wrap: wrap; margin: 0; }
.reading-guide div { width: 50%; padding-right: 8mm; margin-bottom: 8pt; }
.reading-guide dt { font-weight: 700; color: #0a1628; font-size: 9.4pt; margin-bottom: 2pt; }
.reading-guide dd { margin: 0; color: #55688a; font-size: 8.8pt; line-height: 1.45; }

.gallery { break-after: page; }
.gallery-grid { display: block; }
.shot { break-inside: avoid; margin: 0 0 4mm; }
.shot img {
  max-height: 76mm; max-width: 100%; width: auto; display: block; margin: 0 auto;
  border: 0.6pt solid #dfe7f4; border-radius: 4pt;
}
p > img {
  display: block; width: 86%; max-height: 92mm; object-fit: contain; margin: 9pt auto 3pt;
  border: 0.6pt solid #dfe7f4; border-radius: 4pt;
}
.shot figcaption { color: #6b7d99; font-size: 8pt; margin-top: 3pt; text-align: center; }

.note {
  background: #f7faff; border: 0.6pt solid #dfe7f4; border-radius: 4pt;
  padding: 7pt 9pt; color: #4a5d7a; font-size: 8.8pt; margin: 7pt 0;
}
.page-break { break-after: page; }
"""


def inline_local_images(markdown_text: str) -> str:
    """Replace relative image links with data URIs so the printed HTML is self-contained.

    Chrome resolves `../assets/logo.png` against the temp HTML file rather than the report,
    which renders a broken-image icon in the PDF.
    """

    def replace(match: re.Match[str]) -> str:
        alt, src = match.group(1), match.group(2).strip()
        if src.startswith(("http://", "https://", "data:")):
            return match.group(0)
        path = (REPORT.parent / src).resolve()
        # The logo is already on the cover; repeating it full-bleed mid-document wastes a page.
        if not path.exists() or path.stem.lower().startswith("logo"):
            return ""
        return f"![{alt}]({data_uri(path)})"

    return re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", replace, markdown_text)


def build_html(markdown_text: str) -> str:
    body = markdown.markdown(
        inline_local_images(markdown_text),
        extensions=["tables", "fenced_code", "sane_lists", "attr_list"],
        output_format="html5",
    )
    # The cover replaces the markdown title, so drop a leading <h1>.
    body = re.sub(r"^\s*<h1>.*?</h1>\s*", "", body, count=1, flags=re.S)

    toc_items = "".join(
        f'<li class="lvl{level}">{html.escape(h)}</li>' for level, h in headings(markdown_text)
    )
    logo = data_uri(LOGO) if LOGO.exists() else ""

    shots = []
    for relative, caption in SCREENSHOTS:
        path = ROOT / relative
        if not path.exists():
            continue
        shots.append(
            '<figure class="shot">'
            f'<img src="{data_uri(path)}" alt="{html.escape(caption)}">'
            f"<figcaption>{html.escape(caption)}</figcaption>"
            "</figure>"
        )
    gallery = "".join(shots)

    today = date.today().strftime("%d %B %Y")
    cover = f"""
<section class="cover">
  <div>
    <div class="cover-top">
      <img class="cover-logo" src="{logo}" alt="ScamShield AI logo">
      <div>
        <div class="cover-kicker">Agent Skills Hackathon · Best use of Gemma 4</div>
        <div style="font-weight:700;font-size:12pt;color:#0a1628">ScamShield AI</div>
      </div>
    </div>
    <h1>Know a job scam<br>before you pay.</h1>
    <div class="rule"></div>
    <p class="lede">An offline job-scam detector for Pakistan's job seekers: quoted red flags,
      local AI reasoning, screenshot reading and on-device learning — with no message ever
      leaving the laptop.</p>
    <div class="cover-stats">
      <div><b>0</b><span>messages sent to a server — works with the Wi-Fi off</span></div>
      <div><b>12</b><span>rule families scoring the text, links, mailboxes and numbers</span></div>
      <div><b>55</b><span>automated tests covering the engine, guardrails, PDF, OCR and learning</span></div>
    </div>
  </div>
  <div>
    <table class="cover-meta">
      <tr><td>Project report</td><td>Architecture, functions, libraries, problems and solutions, limitations</td></tr>
      <tr><td>Repository</td><td>github.com/Aabyyss/ScamShield-AI</td></tr>
      <tr><td>Stack</td><td>Python 3.14 · Streamlit · Ollama (Gemma 4 E2B) · RapidOCR/ONNX · SQLite</td></tr>
      <tr><td>Status</td><td>Working end to end · 55 automated tests passing</td></tr>
      <tr><td>Date</td><td>{today}</td></tr>
    </table>
    <div class="cover-foot">Student hackathon project. ScamShield gives guidance, not legal
      advice, and never declares a company criminal.</div>
  </div>
</section>

<section class="toc">
  <h2>Contents</h2>
  <ul>{toc_items}</ul>
  <div class="reading-guide">
    <h3>Where to read if you have five minutes</h3>
    <dl>
      <div><dt>The pitch (§1 – §3)</dt><dd>What the problem costs a student, and what the
        user actually sees on screen.</dd></div>
      <div><dt>How it is built (§4 – §7)</dt><dd>Request lifecycle, every module, the rule
        taxonomy, and the stack with the reasons behind each choice.</dd></div>
      <div><dt>Why the verdict holds up (§8 – §11)</dt><dd>Guardrails against a small local
        model, the learning maths, the 19 problems hit while building, and the tests.</dd></div>
      <div><dt>Honest limits (§12 – §17)</dt><dd>What was measured, what was not, what the
        project cannot do, and what we would build next.</dd></div>
    </dl>
  </div>
</section>

<section class="gallery">
  <h2>Interface</h2>
  <div class="gallery-grid">{gallery}</div>
</section>
"""

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>ScamShield AI — Project Report</title>
<style>{CSS}</style></head>
<body>{cover}{body}</body></html>"""


def find_chrome() -> str | None:
    for candidate in CHROME_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    for name in ("chrome", "chromium", "msedge"):
        found = shutil.which(name)
        if found:
            return found
    return None


def print_pdf(html_path: Path, pdf_path: Path) -> None:
    chrome = find_chrome()
    if not chrome:
        raise RuntimeError(
            "Chrome or Edge was not found. Open docs/build/report.html in a browser and "
            "use Print → Save as PDF."
        )
    with tempfile.TemporaryDirectory() as profile:
        command = [
            chrome,
            "--headless=new",
            "--disable-gpu",
            "--no-first-run",
            "--no-default-browser-check",
            "--no-pdf-header-footer",
            f"--user-data-dir={profile}",
            f"--print-to-pdf={pdf_path}",
            html_path.resolve().as_uri(),
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=180)
    if not pdf_path.exists():
        # Older builds reject --no-pdf-header-footer; retry with default header/footer.
        command = [c for c in command if c != "--no-pdf-header-footer"]
        subprocess.run(command, capture_output=True, text=True, timeout=180)
    if not pdf_path.exists():
        raise RuntimeError(
            f"PDF was not created. Chrome said:\n{result.stdout[-800:]}\n{result.stderr[-800:]}"
        )


def stamp_page_numbers(pdf_path: Path) -> None:
    """Add a discreet footer after printing; Chromium cannot do page counters via CSS."""
    try:
        import pymupdf
    except ImportError:
        return
    document = pymupdf.open(pdf_path)
    total = document.page_count
    for index, page in enumerate(document):
        if index == 0:
            continue
        label = f"ScamShield AI \u2014 Project Report    \u00b7    {index + 1} / {total}"
        page.insert_text(
            (42, page.rect.height - 26),
            label,
            fontsize=7.5,
            fontname="helv",
            color=(0.42, 0.49, 0.60),
        )
    document.saveIncr()
    document.close()


def main() -> None:
    if not REPORT.exists():
        raise SystemExit(f"Report not found: {REPORT}")
    markdown_text = REPORT.read_text(encoding="utf-8")
    markup = build_html(markdown_text)

    build_dir = ROOT / "data" / "report-build"
    build_dir.mkdir(parents=True, exist_ok=True)
    html_path = build_dir / "report.html"
    html_path.write_text(markup, encoding="utf-8")

    print_pdf(html_path, OUTPUT)
    stamp_page_numbers(OUTPUT)
    size_mb = OUTPUT.stat().st_size / 1_048_576
    print(f"Wrote {OUTPUT} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
