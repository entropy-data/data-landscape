#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "playwright>=1.50",
# ]
# ///
"""Generate data-landscape.pdf from the rendered site.

Run standalone with uv (no pre-install needed):

    ./scripts/generate-pdf.py [BASE_URL]
    # or:
    uv run scripts/generate-pdf.py [BASE_URL]

BASE_URL defaults to http://127.0.0.1:8000/. In CI we serve the repo with
`python -m http.server 8000` and point the script at that, so the PDF
reflects exactly the version about to be deployed.

The script bootstraps a Chromium build via `playwright install chromium`
on first run, so it works on a fresh machine with no manual setup.
"""
import asyncio
import subprocess
import sys
from datetime import date
from pathlib import Path

from playwright.async_api import async_playwright, Error as PlaywrightError

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data-landscape.pdf"
DEFAULT_URL = "http://127.0.0.1:8000/"

PDF_STYLE = """
.github-corner,
.landscape-toolbar,
main > div.mx-auto.max-w-7xl.px-6.lg\\:px-8.mt-10.mb-8,
.faq-section,
.thank-you-section,
.contribute-cta,
footer { display: none !important; }

main { margin: 0 !important; padding: 0 !important; }
.landscape { background: white !important; border: 0 !important; padding: 0 !important; }
.landscape-section + .landscape-section { margin-top: 1.25rem; }
.landscape-section { break-inside: avoid; page-break-inside: avoid; }

#pdf-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 0 0 16px;
  margin: 0 0 20px;
  border-bottom: 1px solid #e5e7eb;
}
#pdf-header img { height: 36px; width: auto; }
#pdf-header .titles { line-height: 1.2; }
#pdf-header h1 { margin: 0; font-size: 18px; font-weight: 700; color: #111827; }
#pdf-header p { margin: 2px 0 0; font-size: 12px; color: #4f46e5; font-weight: 500; }

#pdf-footer {
  margin-top: 24px;
  padding-top: 12px;
  border-top: 1px solid #e5e7eb;
  display: flex;
  justify-content: space-between;
  font-size: 10px;
  color: #6b7280;
}
#pdf-footer a { color: #4f46e5; text-decoration: none; }

@page { size: A3 landscape; margin: 0; }
body { margin: 0; padding: 12mm; box-sizing: border-box; }
"""

HIDE_SCRIPT = r"""
() => {
  const main = document.querySelector('main');
  if (!main) return;
  const matchByHeading = (heading) => {
    return [...main.querySelectorAll('h2')]
      .find(h => h.textContent.trim().toLowerCase() === heading.toLowerCase())
      ?.closest('div');
  };
  matchByHeading('FAQ')?.classList.add('faq-section');
  matchByHeading('Thank you')?.classList.add('thank-you-section');

  document
    .querySelector('div.rounded-lg.border.border-indigo-200.bg-indigo-50')
    ?.classList.add('contribute-cta');
}
"""

INJECT_HEADER_FOOTER = r"""
({ generatedDate }) => {
  const landscape = document.querySelector('.landscape');
  if (!landscape) return;

  const header = document.createElement('div');
  header.id = 'pdf-header';
  header.innerHTML = `
    <img src="/media/logo_fuchsia_v2.svg" alt="Entropy Data">
    <div class="titles">
      <h1>Data Landscape — Open Standards for Modern Data Architecture</h1>
      <p>Curated by Entropy Data · www.data-landscape.com</p>
    </div>
  `;
  landscape.parentNode.insertBefore(header, landscape);

  const footer = document.createElement('div');
  footer.id = 'pdf-footer';
  footer.innerHTML = `
    <span>Generated ${generatedDate}</span>
    <a href="https://www.data-landscape.com/">www.data-landscape.com</a>
  `;
  landscape.parentNode.appendChild(footer);
}
"""


def ensure_chromium() -> None:
    """Install Chromium on first run so the script is genuinely standalone."""
    print("Installing Chromium for Playwright (one-time)...", file=sys.stderr)
    subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        check=True,
    )


async def render(base_url: str) -> None:
    # Render onto a single A3 landscape page. Scale the rendered content
    # down just enough to fit, so the result fills the full A3 area.
    PAGE_WIDTH_PX = 1587   # 420 mm @ 96 dpi
    PAGE_HEIGHT_PX = 1123  # 297 mm @ 96 dpi
    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch()
        except PlaywrightError as e:
            if "Executable doesn't exist" not in str(e):
                raise
            ensure_chromium()
            browser = await p.chromium.launch()

        context = await browser.new_context(viewport={"width": PAGE_WIDTH_PX, "height": PAGE_HEIGHT_PX})
        page = await context.new_page()
        await page.goto(base_url, wait_until="networkidle")

        await page.evaluate(HIDE_SCRIPT)
        await page.evaluate(
            INJECT_HEADER_FOOTER,
            {"generatedDate": date.today().isoformat()},
        )
        await page.add_style_tag(content=PDF_STYLE)
        await page.wait_for_timeout(300)
        await page.emulate_media(media="print")

        content_height_px = await page.evaluate(
            "() => Math.ceil(document.documentElement.getBoundingClientRect().height)"
        )
        scale = min(1.0, PAGE_HEIGHT_PX / content_height_px)
        # Playwright clamps scale to [0.1, 2.0]; keep a tiny margin below 1.0
        # so rounding never tips the content over a page boundary.
        scale = max(0.1, min(scale - 0.005, 2.0))

        await page.pdf(
            path=str(OUT),
            format="A3",
            landscape=True,
            scale=scale,
            print_background=True,
            margin={"top": "0", "bottom": "0", "left": "0", "right": "0"},
        )
        print(f"  content height: {content_height_px}px  scale: {scale:.3f}")
        await browser.close()


def main() -> int:
    base = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL
    asyncio.run(render(base))
    size = OUT.stat().st_size
    print(f"Wrote {OUT.relative_to(ROOT)} ({size:,} bytes) from {base}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
