"""One-page PDF verdict — the file a user forwards to the friend who is about to pay.

The Markdown report is for the user's own record; this is the *share* artefact. It has to
survive being opened on a cheap phone inside WhatsApp: one page, large type, the verdict and
the quoted evidence only, no scrolling.

Written by hand against the PDF 1.4 spec with the standard library alone: no reportlab, no
weasyprint, no headless browser. The project installs nothing extra for this, and the file is
produced on the machine with Wi-Fi off, like everything else.

The base-14 Helvetica faces are used, which are single-byte WinAnsi. Text is therefore
transliterated to Latin-1 before drawing (curly quotes, dashes, é, arrows) and characters that
cannot be represented — emoji, Urdu script — are dropped rather than rendered as boxes. That is
a deliberate trade: embedding a Unicode TTF would mean shipping a font file (~700 KB) and
licensing it, for a page whose whole content is the Latin text the user pasted.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from .engine import Analysis

PAGE_W, PAGE_H = 595.28, 841.89  # A4 in points
MARGIN = 44.0
FOOTER_H = 78.0  # reserved at the bottom of every page

BRAND = "#1d4ed8"
BRAND_DARK = "#1e3a8a"
INK = "#0f172a"
MUTED = "#4a5568"
FAINT = "#8b98a9"
RULE = "#d9e2ef"
QUOTE_BG = "#f2f5fa"
NAVY = "#101a2e"

LEVEL_FILL = {"HIGH": "#b3261e", "MEDIUM": "#8a5200", "LOW": "#15653b"}
SEVERITY_FILL = {
    "critical": "#b3261e",
    "high": "#c2410c",
    "medium": "#8a5200",
    "low": "#15653b",
}

# --------------------------------------------------------------------------------------
# Text hygiene
# --------------------------------------------------------------------------------------

_REPLACE = {
    "\u2018": "'",
    "\u2019": "'",
    "\u201a": "'",
    "\u201b": "'",
    "\u2032": "'",
    "\u201c": '"',
    "\u201d": '"',
    "\u201e": '"',
    "\u2033": '"',
    "\u00ab": '"',
    "\u00bb": '"',
    "\u2010": "-",
    "\u2011": "-",
    "\u2012": "-",
    "\u2013": "-",
    "\u2014": "-",
    "\u2015": "-",
    "\u2212": "-",
    "\u2026": "...",
    "\u2022": "-",
    "\u2023": "-",
    "\u25aa": "-",
    "\u25cf": "-",
    "\u2192": "->",
    "\u2190": "<-",
    "\u2705": "OK",
    "\u2714": "OK",
    "\u26a0": "!",
    "\u2265": ">=",
    "\u2264": "<=",
    "\u00d7": "x",
    "\u20b9": "Rs",
    "\u20a8": "Rs",
    "\u00a0": " ",
    "\u200b": "",
    "\u200c": "",
    "\u200d": "",
    "\ufeff": "",
}


def sanitize(text: str) -> str:
    """Fold text down to what the built-in Helvetica faces can draw."""
    out: list[str] = []
    for char in text:
        mapped = _REPLACE.get(char)
        if mapped is not None:
            out.append(mapped)
            continue
        if ord(char) < 128:
            out.append(char)
            continue
        try:
            char.encode("latin-1")
        except UnicodeEncodeError:
            out.append(" ")
            continue
        out.append(char)
    collapsed = re.sub(r"[ \t]+", " ", "".join(out))
    return re.sub(r" +", " ", collapsed).strip()


def _escape(text: str) -> bytes:
    raw = text.encode("latin-1", "replace")
    return raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


# --------------------------------------------------------------------------------------
# Helvetica metrics (AFM, units per 1000 em), ASCII 32-126
# --------------------------------------------------------------------------------------

_HELV = (
    "278 278 355 556 556 889 667 191 333 333 389 584 278 333 278 278 "
    "556 556 556 556 556 556 556 556 556 556 278 278 584 584 584 556 "
    "1015 667 667 722 722 667 611 778 722 278 500 667 556 833 722 778 "
    "667 778 722 667 611 722 667 944 667 667 611 278 278 278 469 556 "
    "333 556 556 500 556 556 278 556 556 222 222 500 222 833 556 556 "
    "556 556 333 500 278 556 500 722 500 500 500 334 260 334 584"
)
_BOLD = (
    "278 333 474 556 556 889 722 238 333 333 389 584 278 333 278 278 "
    "556 556 556 556 556 556 556 556 556 556 333 333 584 584 584 611 "
    "975 722 722 722 722 667 611 778 722 278 556 722 611 833 722 778 "
    "667 778 722 667 611 722 667 944 667 667 611 333 278 333 584 556 "
    "333 556 611 556 611 556 333 611 611 278 278 556 278 889 611 611 "
    "611 611 389 556 333 611 556 778 556 556 500 389 280 389 584"
)

_WIDTH_TABLE = {
    "F1": [int(v) for v in _HELV.split()],
    "F2": [int(v) for v in _BOLD.split()],
    "F3": [int(v) for v in _HELV.split()],  # Oblique shares Helvetica widths
}


def text_width(text: str, size: float, font: str = "F1") -> float:
    table = _WIDTH_TABLE[font]
    total = 0
    for char in text:
        code = ord(char)
        total += table[code - 32] if 32 <= code <= 126 else 556
    return total * size / 1000.0


def wrap(text: str, size: float, font: str, width: float, limit: int | None = None) -> list[str]:
    """Greedy word wrap; long unbroken tokens are split so nothing overflows the page."""
    text = sanitize(text)
    if not text:
        return []
    words: list[str] = []
    for word in text.split(" "):
        while text_width(word, size, font) > width and len(word) > 1:
            cut = len(word)
            while cut > 1 and text_width(word[:cut], size, font) > width:
                cut -= 1
            words.append(word[:cut])
            word = word[cut:]
        words.append(word)

    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and text_width(candidate, size, font) > width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)

    if limit is not None and len(lines) > limit:
        lines = lines[:limit]
        last = lines[-1]
        while last and text_width(last + "...", size, font) > width:
            last = last[:-1].rstrip()
        lines[-1] = last + "..."
    return lines


# --------------------------------------------------------------------------------------
# Drawing surface
# --------------------------------------------------------------------------------------


def _rgb(hex_colour: str) -> tuple[float, float, float]:
    value = hex_colour.lstrip("#")
    return tuple(int(value[i : i + 2], 16) / 255.0 for i in (0, 2, 4))  # type: ignore[return-value]


class _Canvas:
    """Accumulates a content stream. Coordinates are given from the top-left corner."""

    def __init__(self) -> None:
        self.ops: list[bytes] = []

    def _op(self, text: str) -> None:
        self.ops.append(text.encode("ascii"))

    def rect(self, x: float, top: float, w: float, h: float, fill: str, radius: float = 0.0) -> None:
        y = PAGE_H - top - h
        r, g, b = _rgb(fill)
        self._op(f"{r:.4f} {g:.4f} {b:.4f} rg")
        if radius <= 0:
            self._op(f"{x:.2f} {y:.2f} {w:.2f} {h:.2f} re f")
            return
        k = 0.5523 * radius
        path = [
            f"{x + radius:.2f} {y:.2f} m",
            f"{x + w - radius:.2f} {y:.2f} l",
            f"{x + w - radius + k:.2f} {y:.2f} {x + w:.2f} {y + radius - k:.2f} "
            f"{x + w:.2f} {y + radius:.2f} c",
            f"{x + w:.2f} {y + h - radius:.2f} l",
            f"{x + w:.2f} {y + h - radius + k:.2f} {x + w - radius + k:.2f} {y + h:.2f} "
            f"{x + w - radius:.2f} {y + h:.2f} c",
            f"{x + radius:.2f} {y + h:.2f} l",
            f"{x + radius - k:.2f} {y + h:.2f} {x:.2f} {y + h - radius + k:.2f} "
            f"{x:.2f} {y + h - radius:.2f} c",
            f"{x:.2f} {y + radius:.2f} l",
            f"{x:.2f} {y + radius - k:.2f} {x + radius - k:.2f} {y:.2f} "
            f"{x + radius:.2f} {y:.2f} c",
            "h f",
        ]
        for step in path:
            self._op(step)

    def line(self, x1: float, top1: float, x2: float, top2: float, colour: str, width: float) -> None:
        r, g, b = _rgb(colour)
        self._op(f"{r:.4f} {g:.4f} {b:.4f} RG {width:.2f} w 1 J 1 j")
        self._op(f"{x1:.2f} {PAGE_H - top1:.2f} m {x2:.2f} {PAGE_H - top2:.2f} l S")

    def polyline(self, points: list[tuple[float, float]], colour: str, width: float) -> None:
        r, g, b = _rgb(colour)
        self._op(f"{r:.4f} {g:.4f} {b:.4f} RG {width:.2f} w 1 J 1 j")
        first = points[0]
        self._op(f"{first[0]:.2f} {PAGE_H - first[1]:.2f} m")
        for x, top in points[1:]:
            self._op(f"{x:.2f} {PAGE_H - top:.2f} l")
        self._op("S")

    def text(
        self,
        x: float,
        top: float,
        content: str,
        size: float,
        font: str = "F1",
        colour: str = INK,
        align: str = "left",
        box_width: float | None = None,
    ) -> None:
        """Draw one line. `top` is the top of the line box, not the baseline."""
        if not content:
            return
        baseline = PAGE_H - (top + size * 0.80)
        width = text_width(content, size, font)
        start = x
        if align == "right":
            start = x - width
        elif align == "center":
            start = x - width / 2.0
        r, g, b = _rgb(colour)
        self._op(f"BT /{font} {size:.2f} Tf {r:.4f} {g:.4f} {b:.4f} rg")
        self._op(f"1 0 0 1 {start:.2f} {baseline:.2f} Tm")
        self.ops.append(b"(" + _escape(content) + b") Tj ET")

    def shield(self, x: float, top: float, size: float, fill: str) -> None:
        """The logo's white shield, as vector curves, in a `size` box."""
        s = size
        left, right = x + 0.08 * s, x + 0.92 * s
        ytop, shoulder, tip = top + 0.06 * s, top + 0.46 * s, top + 0.94 * s
        y0, y1, y2 = PAGE_H - ytop, PAGE_H - shoulder, PAGE_H - tip
        r, g, b = _rgb(fill)
        self._op(f"{r:.4f} {g:.4f} {b:.4f} rg")
        parts = [
            f"{left:.2f} {y0:.2f} m",
            f"{right:.2f} {y0:.2f} l",
            f"{right:.2f} {(y0 + y1) / 2:.2f} {right - 0.18 * s:.2f} {(y2 + y1) / 2:.2f} "
            f"{x + 0.5 * s:.2f} {y2:.2f} c",
            f"{x + 0.32 * s:.2f} {(y1 + y2) / 2:.2f} {left + 0.18 * s:.2f} {(y0 + y1) / 2:.2f} "
            f"{left:.2f} {y1:.2f} c",
            "h f",
        ]
        for step in parts:
            self._op(step)


@dataclass
class Block:
    """One measured piece of the page: its height and how to paint it."""

    height: float
    draw: Callable[[_Canvas, float], float]
    gap: float = 0.0
    anchor: bool = False  # absorbs leftover space above it, keeping the page's foot grounded

    def total(self) -> float:
        return self.height + self.gap


def _space(height: float) -> Block:
    """Vertical whitespace that still advances the cursor."""
    return Block(height, lambda canvas, top: top + height)


# --------------------------------------------------------------------------------------
# Blocks
# --------------------------------------------------------------------------------------


def _header(when: str) -> Block:
    height = 92.0

    def draw(canvas: _Canvas, top: float) -> float:
        canvas.rect(0, top, PAGE_W, height, NAVY)
        canvas.rect(MARGIN, top + 22, 46, 46, BRAND, radius=12)
        canvas.shield(MARGIN + 8, top + 27, 30, "#ffffff")
        canvas.polyline(
            [
                (MARGIN + 8 + 0.26 * 30, top + 27 + 0.52 * 30),
                (MARGIN + 8 + 0.44 * 30, top + 27 + 0.66 * 30),
                (MARGIN + 8 + 0.76 * 30, top + 27 + 0.30 * 30),
            ],
            BRAND,
            3.4,
        )
        canvas.text(MARGIN + 60, top + 24, "ScamShield AI", 17.5, "F2", "#ffffff")
        canvas.text(
            MARGIN + 60,
            top + 46,
            "Offline job-scam check  ·  nothing left this laptop",
            8.6,
            "F1",
            "#9db2cd",
        )
        canvas.text(PAGE_W - MARGIN, top + 26, "VERDICT REPORT", 8.0, "F2", "#9db2cd", align="right")
        canvas.text(PAGE_W - MARGIN, top + 42, when, 8.6, "F1", "#9db2cd", align="right")
        return top + height

    return Block(height, draw)


def _risk_band(result: Analysis) -> Block:
    level = (result.risk_level or "LOW").upper()
    fill = LEVEL_FILL.get(level, LEVEL_FILL["LOW"])
    height = 64.0
    sub = f"confidence {result.confidence}   ·   score {result.risk_score} out of 100"

    def draw(canvas: _Canvas, top: float) -> float:
        canvas.rect(MARGIN, top, PAGE_W - 2 * MARGIN, height, fill, radius=12)
        canvas.text(MARGIN + 18, top + 14, f"{level} RISK", 20.0, "F2", "#ffffff")
        canvas.text(MARGIN + 19, top + 41, sanitize(sub), 8.8, "F1", "#ffffff")
        canvas.text(
            PAGE_W - MARGIN - 18,
            top + 8,
            str(result.risk_score),
            26.0,
            "F2",
            "#ffffff",
            align="right",
        )
        canvas.text(PAGE_W - MARGIN - 18, top + 46, "/ 100", 8.4, "F1", "#ffffff", align="right")
        return top + height

    return Block(height, draw)


def _paragraph(
    text: str,
    size: float,
    font: str,
    colour: str,
    limit: int,
    leading: float | None = None,
    gap: float = 0.0,
) -> Block | None:
    lines = wrap(text, size, font, PAGE_W - 2 * MARGIN, limit=limit)
    if not lines:
        return None
    step = leading or size * 1.32
    height = step * len(lines)

    def draw(canvas: _Canvas, top: float) -> float:
        for index, line in enumerate(lines):
            canvas.text(MARGIN, top + index * step, line, size, font, colour)
        return top + height

    return Block(height, draw, gap)


def _section(title: str) -> Block:
    height = 20.0

    def draw(canvas: _Canvas, top: float) -> float:
        canvas.text(MARGIN, top + 4, title, 8.6, "F2", FAINT)
        return top + height

    return Block(height, draw)


def _flag_block(flag, index: int) -> Block:
    severity = (flag.severity or "medium").lower()
    accent = SEVERITY_FILL.get(severity, SEVERITY_FILL["medium"])
    inner_left = MARGIN + 14
    inner_width = PAGE_W - 2 * MARGIN - 14

    title_lines = wrap(
        f"{index}. {flag.title}", 10.2, "F2", inner_width, limit=2
    )
    quote_lines = wrap(flag.evidence or "", 9.0, "F3", inner_width - 18, limit=2)
    why_lines = wrap(flag.why_it_matters or "", 8.8, "F1", inner_width, limit=2)

    title_h = len(title_lines) * 13.2
    quote_h = (len(quote_lines) * 11.8 + 13.0) if quote_lines else 0.0
    why_h = len(why_lines) * 11.8 + (2.0 if why_lines else 0.0)
    height = title_h + (3.0 if quote_h else 0.0) + quote_h + (3.0 if why_h else 0.0) + why_h + 11.0

    def draw(canvas: _Canvas, top: float) -> float:
        cursor = top
        canvas.rect(MARGIN, cursor + 4, 4.0, title_h - 5, accent, radius=2)
        for line in title_lines:
            canvas.text(inner_left, cursor, line, 10.2, "F2", INK)
            cursor += 13.2
        if quote_lines:
            cursor += 3.0
            canvas.rect(inner_left, cursor, inner_width, quote_h, QUOTE_BG, radius=5)
            canvas.rect(inner_left, cursor, 2.6, quote_h, accent)
            inner = cursor + 6.0
            for line in quote_lines:
                canvas.text(inner_left + 9, inner, line, 9.0, "F3", "#334155")
                inner += 11.8
            cursor += quote_h
        if why_lines:
            cursor += 3.0
            for line in why_lines:
                canvas.text(inner_left, cursor, line, 8.8, "F1", MUTED)
                cursor += 11.8
        return top + height

    return Block(height, draw, gap=11.0)


def _note_block(text: str) -> Block:
    return _paragraph(text, 9.4, "F1", MUTED, limit=3, gap=6.0) or Block(0, lambda c, t: t)


# One short name per family, in the same order as rules.RULES. Kept here as plain words so the
# footer reads as a sentence instead of a wall of internal labels.
_FAMILIES = (
    "upfront fees",
    "private wallets",
    "guaranteed visas",
    "document harvesting",
    "daily-task scams",
    "lookalike links",
    "above-market pay",
    "free mailboxes",
    "skipped interviews",
    "manufactured urgency",
    "unnamed employers",
    "bulk blasts",
)


def _family_list() -> str:
    from .rules import RULES

    names = _FAMILIES[: len(RULES)] if len(RULES) <= len(_FAMILIES) else ()
    if not names:
        return f"Checked against {len(RULES)} job-fraud families."
    joined = ", ".join(names[:-1]) + " and " + names[-1]
    return f"Checked against {len(RULES)} job-fraud families: {joined}."


def _report_block() -> Block:
    rows = (
        ("FIA cybercrime helpline 1991", "Pakistan's federal cybercrime unit takes job-fraud reports"),
        ("PTA pta.gov.pk", "for the phone numbers and SIMs used to run the scam"),
        ("The app it arrived on", "WhatsApp, Telegram, the job board - and your bank if you paid"),
    )
    height = len(rows) * 12.6

    def draw(canvas: _Canvas, top: float) -> float:
        cursor = top
        for label, note in rows:
            canvas.text(MARGIN, cursor, label, 8.8, "F2", "#1f2937")
            start = MARGIN + text_width(label, 8.8, "F2") + 10
            room = PAGE_W - MARGIN - start
            clipped = wrap(note, 8.4, "F1", room, limit=1)
            if clipped:
                canvas.text(start, cursor, clipped[0], 8.4, "F1", MUTED)
            cursor += 12.6
        return top + height

    return Block(height, draw)


def _questions_block(questions: list[str]) -> Block:
    items: list[list[str]] = [
        wrap(f"-  {question}", 9.0, "F1", PAGE_W - 2 * MARGIN, limit=2) for question in questions[:3]
    ]
    height = sum(len(lines) * 12.2 + 1.5 for lines in items)

    def draw(canvas: _Canvas, top: float) -> float:
        cursor = top
        for lines in items:
            for line in lines:
                canvas.text(MARGIN, cursor, line, 9.0, "F1", "#334155")
                cursor += 12.2
            cursor += 1.5
        return top + height

    return Block(height, draw)


def _actions_block(actions: list[str]) -> Block:
    items: list[list[str]] = []
    for action in actions[:4]:
        items.append(wrap(f"{len(items) + 1}.  {action}", 9.2, "F1", PAGE_W - 2 * MARGIN, limit=2))
    height = sum(len(lines) * 12.4 + 2.0 for lines in items)

    def draw(canvas: _Canvas, top: float) -> float:
        cursor = top
        for lines in items:
            for line in lines:
                canvas.text(MARGIN, cursor, line, 9.2, "F1", "#1f2937")
                cursor += 12.4
            cursor += 2.0
        return top + height

    return Block(height, draw)


def _entities_block(entities: list) -> Block | None:
    rows: list[tuple[str, str]] = []
    for entity in entities[:3]:
        head = sanitize(entity.value)
        tail = sanitize(f"  ·  {entity.label}, {entity.risk} risk")
        if wrap(head + tail, 8.8, "F1", PAGE_W - 2 * MARGIN, limit=1):
            rows.append((head, tail))
    if not rows:
        return None
    height = len(rows) * 13.4

    def draw(canvas: _Canvas, top: float) -> float:
        cursor = top
        for head, tail in rows:
            canvas.text(MARGIN, cursor, head, 8.8, "F2", "#1f2937")
            start = MARGIN + text_width(head, 8.8, "F2")
            canvas.text(start, cursor, tail, 8.8, "F1", MUTED)
            cursor += 13.4
        return top + height

    return Block(height, draw, gap=6.0)


def _positives_block(items: list[str]) -> Block:
    lines: list[list[str]] = [
        wrap(f"+  {item}", 9.2, "F1", PAGE_W - 2 * MARGIN, limit=2) for item in items[:3]
    ]
    height = sum(len(set_of) * 12.4 + 2.0 for set_of in lines)

    def draw(canvas: _Canvas, top: float) -> float:
        cursor = top
        for group in lines:
            for line in group:
                canvas.text(MARGIN, cursor, line, 9.2, "F1", "#15653b")
                cursor += 12.4
            cursor += 2.0
        return top + height

    return Block(height, draw)


# --------------------------------------------------------------------------------------
# Composition
# --------------------------------------------------------------------------------------


def _compose(
    result: Analysis,
    when: str,
    max_flags: int,
    summary_limit: int,
    max_questions: int,
    families: bool,
) -> list[Block]:
    blocks: list[Block] = [_header(when)]
    blocks.append(_space(20.0))
    blocks.append(_risk_band(result))
    blocks.append(_space(16.0))

    headline = _paragraph(result.headline or "", 13.2, "F2", INK, limit=2, gap=0.0)
    if headline:
        blocks.append(headline)
        blocks.append(_space(4.0))
    summary = _paragraph(result.summary or "", 9.3, "F1", MUTED, limit=summary_limit, gap=2.0)
    if summary:
        blocks.append(summary)

    blocks.append(_space(12.0))

    flags = result.red_flags[:max_flags]
    if flags:
        blocks.append(_section("WHY THIS IS RISKY"))
        blocks.append(_space(2.0))
        for index, flag in enumerate(flags, 1):
            blocks.append(_flag_block(flag, index))
    else:
        blocks.append(_section("WHAT WE FOUND"))
        blocks.append(_space(2.0))
        blocks.append(
            _note_block(
                "No known scam pattern matched this message. That is good news, not a "
                "guarantee - check the employer independently before sending documents or money."
            )
        )
        positives = [p for p in result.positive_signals if p]
        if positives:
            blocks.append(_positives_block(positives))

    hidden = len(result.red_flags) - len(flags)
    if hidden > 0:
        note = (
            "1 more flag is in the full report inside the app."
            if hidden == 1
            else f"{hidden} more flags are in the full report inside the app."
        )
        blocks.append(_paragraph(note, 8.4, "F1", FAINT, limit=1, gap=8.0) or _space(0))

    if result.entities:
        block = _entities_block(result.entities)
        if block:
            blocks.append(_space(6.0))
            blocks.append(_section("CONTACT POINTS IN THIS MESSAGE"))
            blocks.append(_space(2.0))
            blocks.append(block)

    if max_questions and result.questions_to_ask:
        blocks.append(_space(6.0))
        blocks.append(_section("ASK THEM THIS BEFORE YOU REPLY"))
        blocks.append(_space(2.0))
        blocks.append(_questions_block(result.questions_to_ask[:max_questions]))

    if result.recommended_actions:
        blocks.append(_space(10.0))
        blocks.append(_section("WHAT TO DO NOW"))
        blocks.append(_space(2.0))
        blocks.append(_actions_block(result.recommended_actions))

    if families:
        blocks.append(_space(14.0))
        blocks.append(_paragraph(_family_list(), 7.6, "F1", FAINT, limit=2) or _space(0))

    # The reporting contacts anchor the bottom of the page: any leftover space goes above them.
    anchor = Block(0.0, lambda c, t: t)
    anchor.anchor = True
    blocks.append(anchor)
    blocks.append(_section("REPORT IT"))
    blocks.append(_space(2.0))
    blocks.append(_report_block())

    return blocks


def _content_height(blocks: list[Block]) -> float:
    return sum(block.total() for block in blocks)


def _justify(blocks: list[Block], headroom: float) -> None:
    """Give leftover space back as breathing room instead of leaving a blank half-page."""
    slack = headroom - _content_height(blocks)
    gaps = [block for block in blocks if block.gap > 0]
    if not gaps:
        return
    anchors = [block for block in blocks if block.anchor]
    if slack > 0 and anchors:
        taken = min(slack, 96.0)
        anchors[0].gap += taken
        slack -= taken
    if slack > 0:
        per = slack / len(gaps)
        for block in gaps:
            block.gap += per


def _draw_footer(canvas: _Canvas, when: str, model: str) -> None:
    top = PAGE_H - FOOTER_H
    canvas.rect(0, top - 8, PAGE_W, FOOTER_H + 8, "#ffffff")
    canvas.line(MARGIN, top, PAGE_W - MARGIN, top, RULE, 0.8)
    y = top + 10
    for line in wrap(
        "ScamShield gives guidance, not a legal accusation. It never claims a company is criminal — "
        "only that a message behaves like known job fraud. Verify the employer independently and never "
        "send money, documents or OTPs to an unverified contact.",
        7.4,
        "F1",
        PAGE_W - 2 * MARGIN,
        limit=2,
    ):
        canvas.text(MARGIN, y, line, 7.4, "F1", FAINT)
        y += 9.4
    canvas.rect(0, PAGE_H - 16, PAGE_W, 16, BRAND_DARK)
    canvas.text(
        MARGIN, PAGE_H - 12.6, "ScamShield AI  ·  free, offline, open source", 7.4, "F2", "#dbeafe"
    )
    canvas.text(
        PAGE_W - MARGIN,
        PAGE_H - 12.6,
        f"{sanitize(model or 'rules only')}  ·  all on this device",
        7.4,
        "F1",
        "#bfd4f5",
        align="right",
    )


# --------------------------------------------------------------------------------------
# PDF assembly
# --------------------------------------------------------------------------------------


def _serialize(content: bytes, title: str, when: str) -> bytes:
    objects: list[bytes] = []

    def add(body: bytes) -> int:
        # Object 1 is the catalogue and object 2 the page tree, so the rest start at 3.
        objects.append(body)
        return len(objects) + 2

    font_regular = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    font_bold = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
    font_italic = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Oblique /Encoding /WinAnsiEncoding >>")

    content_id = add(
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream"
    )
    page_id = add(
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 "
        + f"{PAGE_W:.2f} {PAGE_H:.2f}".encode()
        + b"] /Resources << /Font << /F1 "
        + f"{font_regular} 0 R".encode()
        + b" /F2 "
        + f"{font_bold} 0 R".encode()
        + b" /F3 "
        + f"{font_italic} 0 R".encode()
        + b" >> >> /Contents "
        + f"{content_id} 0 R".encode()
        + b" >>"
    )

    # Object 1 is the catalogue, 2 the page tree, so they are built last but numbered first.
    catalog = b"<< /Type /Catalog /Pages 2 0 R >>"
    pages = b"<< /Type /Pages /Kids [" + f"{page_id} 0 R".encode() + b"] /Count 1 >>"
    info = (
        b"<< /Title ("
        + _escape(sanitize(title))
        + b") /Author (ScamShield AI) /Creator (ScamShield AI, offline) /CreationDate (D:"
        + when.encode()
        + b") >>"
    )

    ordered = [catalog, pages] + objects + [info]
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets: list[int] = []
    for index, body in enumerate(ordered, start=1):
        offsets.append(len(out))
        out += f"{index} 0 obj\n".encode() + body + b"\nendobj\n"

    xref_at = len(out)
    out += f"xref\n0 {len(ordered) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        b"trailer\n<< /Size "
        + str(len(ordered) + 1).encode()
        + b" /Root 1 0 R /Info "
        + f"{len(ordered)} 0 R".encode()
        + b" >>\nstartxref\n"
        + str(xref_at).encode()
        + b"\n%%EOF\n"
    )
    return bytes(out)


def _now() -> datetime:
    return datetime.now()


def build_verdict_pdf(result: Analysis, message: str = "") -> bytes:
    """Render a single A4 page: verdict, quote-backed flags, next steps, disclaimer.

    `message` is accepted for symmetry with `report.build_report` and deliberately not drawn —
    the shareable page is meant to be forwarded, so it carries the evidence quotes rather than
    the whole conversation.
    """
    stamp = _now()
    when = stamp.strftime("%d %b %Y, %H:%M")
    pdf_date = stamp.strftime("%Y%m%d%H%M%S")

    headroom = PAGE_H - FOOTER_H - 10
    blocks: list[Block] = []
    # Flags earn their space first; the family checklist only appears once the page is short
    # enough to need it, so a HIGH verdict is never trimmed to make room for boilerplate.
    presets = (
        (4, 4, 3, False),
        (4, 3, 2, False),
        (3, 3, 2, False),
        (3, 2, 2, False),
        (2, 2, 2, True),
        (2, 2, 1, True),
        (1, 2, 1, True),
        (0, 2, 1, True),
    )
    for max_flags, summary_limit, max_questions, families in presets:
        blocks = _compose(result, when, max_flags, summary_limit, max_questions, families)
        if _content_height(blocks) <= headroom:
            break

    _justify(blocks, headroom)

    canvas = _Canvas()
    cursor = 0.0
    for block in blocks:
        cursor = block.draw(canvas, cursor)
        cursor += block.gap
    _draw_footer(canvas, when, result.model or "")

    content = b"\n".join(canvas.ops)
    return _serialize(content, f"ScamShield verdict - {result.risk_level} risk", pdf_date)


def verdict_pdf_filename(result: Analysis) -> str:
    stamp = _now().strftime("%Y%m%d-%H%M")
    return f"scamshield-{result.risk_level.lower()}-{stamp}.pdf"


def build_whatsapp_text(result: Analysis) -> str:
    """A paste-ready caption for the PDF, since a document alone arrives without context."""
    level = result.risk_level.upper()
    lines = [f"ScamShield check: {level} risk ({result.risk_score}/100)", result.headline or ""]
    for index, flag in enumerate(result.red_flags[:3], 1):
        quote = f' — "{flag.evidence}"' if flag.evidence else ""
        lines.append(f"{index}. {flag.title}{quote}")
    if result.recommended_actions:
        lines.append("Do this: " + result.recommended_actions[0])
    lines.append("Checked offline on my laptop. Do not send money or documents before verifying.")
    return sanitize("\n".join(line for line in lines if line))
