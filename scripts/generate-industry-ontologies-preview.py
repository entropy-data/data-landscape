#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "playwright>=1.50",
# ]
# ///
"""Generate media/social/industry-ontologies.png from the rendered subpage.

Run standalone with uv (no pre-install needed):

    ./scripts/generate-industry-ontologies-preview.py [BASE_URL]
    # or:
    uv run scripts/generate-industry-ontologies-preview.py [BASE_URL]

BASE_URL defaults to http://127.0.0.1:8000/. In CI we serve the repo with
`python -m http.server 8000` and point the script at that, so the og:image
reflects exactly the version about to be deployed.

The industry-ontologies page has no PDF (unlike the main landscape), so the
preview is a 1200x630 viewport screenshot of the page header/intro — the
standard og:image size for summary_large_image cards.

The script bootstraps a Chromium build via `playwright install chromium`
on first run, so it works on a fresh machine with no manual setup.
"""
import argparse
import asyncio
import subprocess
import sys
from pathlib import Path

from playwright.async_api import async_playwright, Error as PlaywrightError

ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = ROOT / "media" / "social" / "industry-ontologies.png"
DEFAULT_URL = "http://127.0.0.1:8000/"
PAGE = "industry-ontologies.html"

# Standard og:image dimensions for a summary_large_image card.
WIDTH = 1200
HEIGHT = 630


def ensure_chromium() -> None:
    """Install Chromium on first run so the script is genuinely standalone."""
    print("Installing Chromium for Playwright (one-time)...", file=sys.stderr)
    subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        check=True,
    )


async def render(base_url: str) -> Path:
    url = base_url.rstrip("/") + "/" + PAGE
    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch()
        except PlaywrightError as e:
            if "Executable doesn't exist" not in str(e):
                raise
            ensure_chromium()
            browser = await p.chromium.launch()

        # Use a 2x device scale for a crisp preview, then the clip below keeps
        # the output at exactly 1200x630.
        context = await browser.new_context(
            viewport={"width": WIDTH, "height": HEIGHT},
            device_scale_factor=2,
        )
        page = await context.new_page()
        await page.goto(url, wait_until="networkidle")
        await page.wait_for_timeout(300)

        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        await page.screenshot(
            path=str(OUT_PATH),
            clip={"x": 0, "y": 0, "width": WIDTH, "height": HEIGHT},
        )
        await browser.close()
        return OUT_PATH


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate the industry-ontologies social preview image."
    )
    parser.add_argument("base_url", nargs="?", default=DEFAULT_URL,
                        help=f"Base URL to render (default: {DEFAULT_URL})")
    args = parser.parse_args()

    out_path = asyncio.run(render(args.base_url))
    size = out_path.stat().st_size
    print(f"Wrote {out_path.relative_to(ROOT)} ({size:,} bytes, {WIDTH}x{HEIGHT}) "
          f"from {args.base_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
