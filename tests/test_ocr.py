"""Tests for offline OCR: a rendered screenshot in, message text out.

These run the real engine, so they are skipped when RapidOCR is not installed.
"""

from __future__ import annotations

import io
import os
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from scamshield import engine, ocr

FONT_CANDIDATES = (
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)

MESSAGE = (
    "URGENT HIRING - DUBAI HOTEL\n"
    "Visa processing fee: Rs 35,000\n"
    "Send fee on JazzCash 0300-1234567"
)


def _font(size: int):
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)


def _screenshot(lines: str = MESSAGE, size: tuple[int, int] = (1000, 340)) -> bytes:
    image = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(image)
    font = _font(34)
    y = 40
    for line in lines.splitlines():
        draw.text((40, y), line, fill="black", font=font)
        y += 70
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


class OCRTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._old_db = os.environ.get("SCAMSHIELD_DB")
        os.environ["SCAMSHIELD_DB"] = str(Path(self._tmp.name) / "ocr.db")

    def tearDown(self) -> None:
        if self._old_db is None:
            os.environ.pop("SCAMSHIELD_DB", None)
        else:
            os.environ["SCAMSHIELD_DB"] = self._old_db
        self._tmp.cleanup()

    def test_engine_is_available(self) -> None:
        self.assertIsNotNone(ocr.engine_name())

    def test_reads_printed_screenshot(self) -> None:
        result = ocr.extract(_screenshot())
        text = result.text.lower()
        self.assertIn("visa", text)
        self.assertIn("jazzcash", text)
        self.assertGreaterEqual(result.word_count, 8)
        self.assertEqual(result.warnings, [])
        self.assertGreater(result.mean_confidence or 0, 0.5)

    def test_blank_image_warns_instead_of_failing(self) -> None:
        blank = Image.new("RGB", (900, 300), "white")
        buffer = io.BytesIO()
        blank.save(buffer, format="PNG")
        result = ocr.extract(buffer.getvalue())
        self.assertEqual(result.text.strip(), "")
        self.assertTrue(result.warnings)

    def test_invalid_bytes_raise_readable_error(self) -> None:
        with self.assertRaises(ocr.OCRError):
            ocr.extract(b"this is not an image")

    def test_oversized_file_is_rejected_before_decoding(self) -> None:
        with self.assertRaises(ocr.OCRError) as ctx:
            ocr.extract(b"x" * (ocr.MAX_BYTES + 1))
        self.assertIn("MB", str(ctx.exception))

    def test_ocr_text_flows_into_the_detector(self) -> None:
        result = ocr.extract(_screenshot())
        analysis = engine.analyze(result.text, use_ai=False, use_learning=False)
        self.assertGreater(len(analysis.rule_hits), 0)
        self.assertNotEqual(analysis.risk_level, "LOW")


if __name__ == "__main__":
    unittest.main()
