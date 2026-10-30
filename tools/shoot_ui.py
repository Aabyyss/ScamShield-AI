"""Capture the four interface screenshots used in the README and the PDF report.

Driven by Playwright against a running local server, at a fixed 1440x900 viewport, so the
images are reproducible instead of hand-cropped. Usage:

    python -m streamlit run app.py --server.port=8501 &
    python tools/shoot_ui.py --url http://127.0.0.1:8501
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout, sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "screenshots"


def settle(page: Page, ms: int = 1200) -> None:
    page.wait_for_timeout(ms)


def wait_idle(page: Page) -> None:
    """Wait until Streamlit's rerun is finished; mid-rerun it dims the whole page."""
    try:
        page.wait_for_function(
            "() => !document.querySelector('[data-testid=\"stStatusWidget\"]')",
            timeout=25_000,
        )
    except PlaywrightTimeout:
        pass
    settle(page, 900)


def shot(page: Page, name: str) -> None:
    OUT.mkdir(exist_ok=True)
    page.screenshot(path=str(OUT / name), full_page=False)
    print(f"wrote screenshots/{name}")


def dismiss_dialog(page: Page, keep_sample: bool = False) -> None:
    """Close the onboarding dialog, optionally loading the demo message on the way out."""
    label = "Try a real scam message" if keep_sample else "Paste my own message"
    button = page.get_by_role("button", name=label)
    if button.count():
        button.first.click()
        settle(page)
    # Anything still open would swallow the next click, so close it for sure.
    for _ in range(3):
        if not page.locator('[data-testid="stDialog"]').count():
            break
        escape = page.locator('[data-testid="stDialog"] button[aria-label="Close"]')
        if escape.count():
            escape.first.click()
        else:
            page.keyboard.press("Escape")
        settle(page, 900)


def pick_theme(page: Page, label: str) -> None:
    page.get_by_text(label, exact=True).first.click()
    wait_idle(page)
    settle(page, 1200)


def analyse(page: Page, wait_for_ai: bool = True) -> None:
    page.get_by_text("Analyse message").first.click()
    # The rules verdict paints immediately; wait for the score ring to exist.
    page.wait_for_selector(".ss-verdict", state="attached", timeout=30_000)
    if wait_for_ai:
        # Phase 2 replaces it with the model-backed verdict; that is the one worth showing.
        try:
            page.wait_for_selector("text=local AI · ", timeout=200_000)
        except PlaywrightTimeout:
            print("warning: AI verdict did not arrive; keeping the rules verdict", file=sys.stderr)
    wait_idle(page)
    settle(page, 1200)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8501")
    args = parser.parse_args()

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome")
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(args.url, wait_until="networkidle")
        page.wait_for_selector("text=Local engine", timeout=30_000)
        settle(page, 2500)

        # 1. Onboarding dialog, as a first-time user sees it.
        shot(page, "intro-dialog.png")

        # 2. Home screen with the dialog dismissed and a demo message loaded.
        dismiss_dialog(page, keep_sample=True)
        settle(page, 1500)
        page.mouse.wheel(0, -4000)
        settle(page, 700)
        shot(page, "app-home.png")

        # 3. Verdict, light mode — taller viewport so the whole card fits.
        page.set_viewport_size({"width": 1440, "height": 1180})
        settle(page, 900)
        analyse(page)
        page.locator(".ss-verdict").first.scroll_into_view_if_needed()
        page.mouse.wheel(0, -150)
        settle(page, 900)
        shot(page, "verdict-light.png")

        # 4. Same verdict in dark mode. Switching the theme reloads the page, so the message
        #    has to be loaded and analysed again.
        page.mouse.wheel(0, -4000)
        settle(page, 600)
        pick_theme(page, "Dark")
        page.get_by_role("button", name="Dubai hotel").first.click()
        settle(page, 1200)
        analyse(page)
        page.locator(".ss-verdict").first.scroll_into_view_if_needed()
        page.mouse.wheel(0, -150)
        settle(page, 900)
        shot(page, "verdict-dark-final.png")

        browser.close()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except PlaywrightTimeout as exc:
        print(f"Timed out waiting for the UI: {exc}", file=sys.stderr)
        sys.exit(1)
