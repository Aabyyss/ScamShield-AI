"""Generate the ScamShield AI logo and desktop icon.

Everything is drawn with Pillow at 4x, then downsampled, so the edges stay clean at every size.
Run:  python tools/make_logo.py
Outputs: assets/logo.png (512), assets/logo-192.png, assets/icon.ico
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
SCALE = 4  # supersampling factor
SIZE = 1024 * SCALE / 4  # logical canvas is 1024; we draw at 4096
CANVAS = int(SIZE * SCALE) if False else 4096

TOP = (59, 130, 246)  # #3b82f6
BOTTOM = (30, 64, 175)  # #1e40af
ACCENT = (29, 78, 216)  # #1d4ed8


def _lerp(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))  # type: ignore[return-value]


def _cubic(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
    steps: int = 90,
) -> list[tuple[float, float]]:
    points = []
    for i in range(steps + 1):
        t = i / steps
        u = 1 - t
        x = u**3 * p0[0] + 3 * u**2 * t * p1[0] + 3 * u * t**2 * p2[0] + t**3 * p3[0]
        y = u**3 * p0[1] + 3 * u**2 * t * p1[1] + 3 * u * t**2 * p2[1] + t**3 * p3[1]
        points.append((x, y))
    return points


def _shield_points(canvas: int) -> list[tuple[float, float]]:
    """A classic shield: flat top, straight shoulders, curved sides into a point."""
    s = canvas / 1024
    top, shoulder, tip = 292 * s, 548 * s, 820 * s
    left, right, centre = 288 * s, 736 * s, 512 * s
    points: list[tuple[float, float]] = [(left, top), (right, top)]
    points += _cubic((right, top), (right, shoulder), (700 * s, 780 * s), (centre, tip))
    points += _cubic((centre, tip), (324 * s, 780 * s), (left, shoulder), (left, top))
    return points


def build(canvas: int = CANVAS) -> Image.Image:
    # Diagonal gradient: build a tall strip, rotate it, then crop the centre.
    strip = Image.new("RGB", (1, canvas * 2))
    strip_draw = ImageDraw.Draw(strip)
    for y in range(canvas * 2):
        strip_draw.point((0, y), fill=_lerp(TOP, BOTTOM, y / (canvas * 2 - 1)))
    strip = strip.resize((canvas * 2, canvas * 2), Image.BILINEAR).rotate(
        38, resample=Image.BICUBIC, expand=False
    )
    left = (canvas * 2 - canvas) // 2
    image = strip.crop((left, left, left + canvas, left + canvas)).convert("RGB")

    # Rounded-square app tile mask.
    mask = Image.new("L", (canvas, canvas), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, canvas - 1, canvas - 1], radius=int(canvas * 0.225), fill=255
    )

    draw = ImageDraw.Draw(image)
    draw.polygon(_shield_points(canvas), fill=(255, 255, 255))

    # Checkmark, with round caps so it survives 16px rendering.
    s = canvas / 1024
    stroke = int(62 * s)
    check = [(400 * s, 556 * s), (487 * s, 646 * s), (634 * s, 456 * s)]
    draw.line(check, fill=ACCENT, width=stroke, joint="curve")
    for x, y in check:
        r = stroke / 2
        draw.ellipse((x - r, y - r, x + r, y + r), fill=ACCENT)

    tiled = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    tiled.paste(image, (0, 0), mask)
    return tiled


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    master = build()
    logo = master.resize((512, 512), Image.LANCZOS)
    logo.save(ASSETS / "logo.png")
    master.resize((192, 192), Image.LANCZOS).save(ASSETS / "logo-192.png")
    master.resize((256, 256), Image.LANCZOS).save(
        ASSETS / "icon.ico",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print("wrote", ASSETS / "logo.png", ASSETS / "logo-192.png", ASSETS / "icon.ico")


if __name__ == "__main__":
    main()
