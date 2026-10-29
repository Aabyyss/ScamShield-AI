"""Offline OCR for screenshots of scam messages.

Victims usually have a screenshot, not text they can copy — that is why Scamio and Norton
accept images. This module reads the screenshot on the device with RapidOCR (ONNX models
shipped inside the package: no system binary, no download at runtime), and falls back to
Tesseract if someone already has it installed.

Nothing is uploaded: the image never leaves the process, and the extracted text is handed to
the same rules and model pipeline as a pasted message.
"""

from __future__ import annotations

import io
import threading
import time
from dataclasses import dataclass, field
from functools import lru_cache

MAX_BYTES = 12 * 1024 * 1024
# RapidOCR drops inter-word spaces on small renders, and the rules match on word boundaries,
# so upscale to a width where spacing survives (measured: 900px loses spaces, 1600px keeps them).
MIN_WIDTH = 1600
MAX_SIDE = 4000

_INFERENCE_LOCK = threading.Lock()


class OCRError(RuntimeError):
    """The screenshot could not be read. The message is shown to the user as-is."""


@dataclass
class OCRResult:
    text: str
    engine: str
    lines: list[str] = field(default_factory=list)
    duration_ms: int = 0
    warnings: list[str] = field(default_factory=list)
    mean_confidence: float | None = None

    @property
    def word_count(self) -> int:
        return len(self.text.split())


@lru_cache(maxsize=1)
def _engine_name() -> str | None:
    try:
        import rapidocr_onnxruntime  # noqa: F401
    except ImportError:
        pass
    else:
        return "rapidocr"
    try:
        import pytesseract

        pytesseract.get_tesseract_version()
    except Exception:  # noqa: BLE001 - any failure means "not usable"
        return None
    return "tesseract"


def engine_name() -> str | None:
    """Which local OCR engine is usable, or None. Cached after the first probe."""
    return _engine_name()


def available() -> bool:
    return engine_name() is not None


def install_hint() -> str:
    return "python -m pip install rapidocr-onnxruntime"


@lru_cache(maxsize=1)
def _rapid_engine():
    from rapidocr_onnxruntime import RapidOCR

    return RapidOCR()


def _prepare(image_bytes: bytes) -> "object":
    """Decode, fix EXIF rotation, and scale so small screenshots are readable."""
    try:
        from PIL import Image, ImageOps
    except ImportError as exc:  # pragma: no cover - Pillow is a hard requirement
        raise OCRError("Pillow is not installed, so images cannot be opened.") from exc

    try:
        image = Image.open(io.BytesIO(image_bytes))
        image.load()
    except Exception as exc:  # noqa: BLE001 - any decode failure is user-facing
        raise OCRError("That file could not be opened as an image. Try a PNG or JPG.") from exc

    image = ImageOps.exif_transpose(image).convert("RGB")
    width, height = image.size
    if width == 0 or height == 0:
        raise OCRError("The image is empty.")

    if width < MIN_WIDTH:
        factor = min(3.0, MIN_WIDTH / width)
        image = image.resize((int(width * factor), int(height * factor)), Image.LANCZOS)

    width, height = image.size
    longest = max(width, height)
    if longest > MAX_SIDE:
        factor = MAX_SIDE / longest
        image = image.resize((int(width * factor), int(height * factor)), Image.LANCZOS)

    import numpy as np

    return np.array(image)


def _parse_rapid(raw: object) -> tuple[list[str], list[float]]:
    """RapidOCR's return shape has changed across versions; accept all of them."""
    payload = raw[0] if isinstance(raw, tuple) else raw
    if payload is None:
        return [], []

    txts = getattr(payload, "txts", None)
    if txts is not None:
        scores = getattr(payload, "scores", None) or []
        return [str(t) for t in txts], [float(s) for s in scores]

    lines: list[str] = []
    scores: list[float] = []
    for item in payload:  # [box, text, score]
        try:
            text = str(item[1]).strip()
            score = float(item[2])
        except (IndexError, TypeError, ValueError):
            continue
        if text:
            lines.append(text)
            scores.append(score)
    return lines, scores


def _read_rapid(image: "object") -> tuple[list[str], list[float]]:
    engine = _rapid_engine()
    with _INFERENCE_LOCK:
        raw = engine(image)
    return _parse_rapid(raw)


def _read_tesseract(image_bytes: bytes) -> tuple[list[str], list[float]]:
    import pytesseract
    from PIL import Image

    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    text = pytesseract.image_to_string(image)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines, []


def extract(image_bytes: bytes) -> OCRResult:
    """Read every line of text from a screenshot. Raises OCRError with a usable message."""
    if not image_bytes:
        raise OCRError("The uploaded file is empty.")
    if len(image_bytes) > MAX_BYTES:
        raise OCRError(
            f"That image is {len(image_bytes) / 1_048_576:.1f} MB. "
            f"Please use one under {MAX_BYTES // 1_048_576} MB."
        )

    name = engine_name()
    if name is None:
        raise OCRError(
            "No local OCR engine is installed. Run `" + install_hint() + "` and restart the app."
        )

    started = time.perf_counter()
    warnings: list[str] = []

    if name == "rapidocr":
        try:
            lines, scores = _read_rapid(_prepare(image_bytes))
        except OCRError:
            raise
        except Exception as exc:  # noqa: BLE001 - surface a readable failure
            raise OCRError(f"The OCR engine failed on this image: {exc}") from exc
    else:
        try:
            lines, scores = _read_tesseract(image_bytes)
        except Exception as exc:  # noqa: BLE001
            raise OCRError(f"Tesseract failed on this image: {exc}") from exc

    text = "\n".join(line for line in lines if line.strip())
    mean_confidence = round(sum(scores) / len(scores), 3) if scores else None

    if not text.strip():
        warnings.append(
            "No readable text was found. Try a sharper, larger screenshot with the message "
            "fully visible."
        )
    elif mean_confidence is not None and mean_confidence < 0.6:
        warnings.append(
            "Some words were hard to read, so the text may contain mistakes. Check it before "
            "analysing."
        )

    return OCRResult(
        text=text,
        engine="RapidOCR (ONNX, local)" if name == "rapidocr" else "Tesseract (local)",
        lines=lines,
        duration_ms=int((time.perf_counter() - started) * 1000),
        warnings=warnings,
        mean_confidence=mean_confidence,
    )
