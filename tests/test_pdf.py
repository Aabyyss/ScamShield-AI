"""Tests for the one-page PDF export.

No PDF library is installed, so these check the file's own structure: the header, the cross
reference offsets pointing at real objects, a single page, and the text actually reaching the
content stream. PyMuPDF is a build tool here, not a dependency, so it is not used.
"""

from __future__ import annotations

import re
import unittest

from scamshield.engine import Analysis, Flag
from scamshield.pdf import build_verdict_pdf, build_whatsapp_text, verdict_pdf_filename
from scamshield.samples import SAMPLE_BY_KEY


def _page_count(pdf: bytes) -> int:
    return len(re.findall(rb"/Type\s*/Page[^s]", pdf))


def _analysis(**kwargs) -> Analysis:
    defaults = dict(
        risk_level="HIGH",
        risk_score=82,
        verdict="scam",
        category="job_fraud",
        headline="This matches a known job-scam pattern. Do not pay.",
        summary="The message asks for a visa fee through a private wallet.",
        red_flags=[
            Flag(
                title="Demands an upfront fee",
                evidence="Visa processing fee: Rs 35,000",
                why_it_matters="Employers never charge a candidate for a visa.",
                severity="critical",
                source="rules",
            )
        ],
        recommended_actions=["Stop all payments.", "Do not send documents."],
        questions_to_ask=["Which company is hiring, and what is its website?"],
        model="gemma4:e2b",
    )
    defaults.update(kwargs)
    return Analysis(**defaults)


class PdfExportTests(unittest.TestCase):
    def test_produces_a_single_page_pdf(self) -> None:
        pdf = build_verdict_pdf(_analysis())
        self.assertTrue(pdf.startswith(b"%PDF-1.4"))
        self.assertTrue(pdf.rstrip().endswith(b"%%EOF"))
        self.assertEqual(_page_count(pdf), 1)

    def test_cross_reference_offsets_point_at_objects(self) -> None:
        pdf = build_verdict_pdf(_analysis())
        self.assertIn(b"startxref", pdf)
        # Split on the table's own header line: "startxref" also contains "xref".
        table = pdf.rsplit(b"\nxref\n", 1)[1].split(b"trailer", 1)[0].splitlines()
        entries = [line for line in table if line.rstrip().endswith(b" n")]
        self.assertGreaterEqual(len(entries), 6)
        for entry in entries:
            offset = int(entry[:10])
            self.assertRegex(pdf[offset : offset + 12], rb"\d+ 0 obj")

    def test_verdict_text_reaches_the_page(self) -> None:
        pdf = build_verdict_pdf(_analysis())
        self.assertIn(b"HIGH RISK", pdf)
        self.assertIn(b"82", pdf)
        self.assertIn(b"ScamShield AI", pdf)
        self.assertIn(b"Visa processing fee: Rs 35,000", pdf)

    def test_low_risk_page_says_so_instead_of_showing_alarms(self) -> None:
        pdf = build_verdict_pdf(
            _analysis(
                risk_level="LOW",
                risk_score=0,
                red_flags=[],
                headline="No known scam pattern found - still verify independently.",
            )
        )
        self.assertIn(b"LOW RISK", pdf)
        self.assertIn(b"No known scam pattern matched this message", pdf)
        self.assertEqual(_page_count(pdf), 1)

    def test_very_long_verdict_still_fits_one_page(self) -> None:
        flags = [
            Flag(
                title=f"Red flag number {index} with a deliberately long and wordy title",
                evidence="A quoted fragment of the message that is also quite long indeed " * 2,
                why_it_matters="An explanation that runs on for a while so the layout has to cope. " * 3,
                severity="critical",
                source="rules",
            )
            for index in range(1, 13)
        ]
        pdf = build_verdict_pdf(
            _analysis(red_flags=flags, summary="A long summary. " * 40, questions_to_ask=["Q?"] * 6)
        )
        self.assertEqual(_page_count(pdf), 1)

    def test_emoji_and_urdu_do_not_break_the_file(self) -> None:
        pdf = build_verdict_pdf(
            _analysis(
                headline="🛡️ نوکری کا جھانسہ — “visa” fee 🚨",
                summary="Send Rs 5,000 – fast · 100% guaranteed",
                red_flags=[
                    Flag(
                        title="Fee (Rs 35,000) — “refundable”",
                        evidence="پیسے بھیجیں — “Send fee”",
                        why_it_matters="Brackets ( ) and backslashes \\ must be escaped.",
                        severity="critical",
                        source="rules",
                    )
                ],
            )
        )
        self.assertEqual(_page_count(pdf), 1)
        # Everything drawn must be single-byte Latin-1 with balanced escapes.
        self.assertIn(b"\\( \\)", pdf)
        self.assertIn(b"\\\\", pdf)
        text = pdf.decode("latin-1")
        self.assertIn("Fee \\(Rs 35,000\\)", text)
        # Arabic script cannot be drawn by the built-in fonts, so it is dropped rather than
        # rendered as boxes; the Latin part of the same string must survive.
        self.assertNotIn("نوکری", text)
        self.assertIn('"visa" fee', text)

    def test_sample_messages_all_render(self) -> None:
        from scamshield.engine import analyze

        for key, sample in SAMPLE_BY_KEY.items():
            with self.subTest(sample=key):
                result = analyze(sample.text, use_ai=False)
                pdf = build_verdict_pdf(result, sample.text)
                self.assertEqual(_page_count(pdf), 1)
                self.assertIn(result.risk_level.encode(), pdf)

    def test_filename_and_caption(self) -> None:
        result = _analysis()
        self.assertTrue(verdict_pdf_filename(result).startswith("scamshield-high-"))
        self.assertTrue(verdict_pdf_filename(result).endswith(".pdf"))
        caption = build_whatsapp_text(result)
        self.assertIn("HIGH risk", caption)
        self.assertIn("Visa processing fee", caption)
        self.assertNotIn("🛡️", caption)  # sanitised for the message box


if __name__ == "__main__":
    unittest.main()
