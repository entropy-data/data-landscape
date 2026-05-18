#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "playwright>=1.50",
# ]
# ///
"""Generate media/social/industry-ontologies.png — the og:image card.

Run standalone with uv (no pre-install needed):

    ./scripts/generate-industry-ontologies-preview.py
    # or:
    uv run scripts/generate-industry-ontologies-preview.py

A BASE_URL arg is accepted for CI compatibility but ignored: the card is a
purpose-built 1200x630 layout rendered from a self-contained template (not a
screenshot of the live page, which produced tiny, blurry text). It mirrors
the page's own card/badge styling and uses the repo's Inter webfont, loaded
via file:// so no server is needed.

The tile grid lists every ontology on the page plus a CTA tile asking the
community to suggest more — keep ONTOLOGIES in sync with industry-ontologies.html.

The script bootstraps a Chromium build via `playwright install chromium`
on first run, so it works on a fresh machine with no manual setup.
"""
import argparse
import asyncio
import subprocess
import sys
import tempfile
from pathlib import Path

from playwright.async_api import async_playwright, Error as PlaywrightError

ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = ROOT / "media" / "social" / "industry-ontologies.png"
FONTS = ROOT / "fonts"
LOGO = ROOT / "media" / "logo_fuchsia_v2.svg"

# Standard og:image dimensions for a summary_large_image card. Rendered at
# 2x device scale so the output is crisp on retina/social-card displays.
WIDTH = 1200
HEIGHT = 630

# Name, domain badge label, badge palette key, issuer. Mirror of the
# .ont-card list in industry-ontologies.html — keep in sync.
ONTOLOGIES = [
    ("FIBO",            "Finance",      "finance",  "EDM Council"),
    ("TM Forum SID",    "Telco",        "telco",    "TM Forum"),
    ("CGMES",           "Energy",       "energy",   "IEC / ENTSO-E"),
    ("IDMP",            "Pharma",       "pharma",   "ISO / Pistoia Alliance"),
    ("EPCIS",           "Supply Chain", "supply",   "GS1"),
    ("IATA ONE Record", "Air Cargo",    "aircargo", "IATA"),
    ("EBU Core Plus",   "Media",        "media",    "EBU / SMPTE"),
    ("GoodRelations",   "E-Commerce",   "commerce", "Martin Hepp / schema.org"),
]

# Copied verbatim from the .badge-* rules in industry-ontologies.html.
BADGES = {
    "finance":  ("#faf5ff", "#7e22ce", "rgba(147, 51, 234, 0.2)"),
    "telco":    ("#f0f9ff", "#0369a1", "rgba(2, 132, 199, 0.2)"),
    "energy":   ("#fffbeb", "#b45309", "rgba(217, 119, 6, 0.2)"),
    "pharma":   ("#f0fdf4", "#15803d", "rgba(22, 163, 74, 0.2)"),
    "supply":   ("#f0fdfa", "#0f766e", "rgba(13, 148, 136, 0.2)"),
    "aircargo": ("#f0f9ff", "#0369a1", "rgba(2, 132, 199, 0.2)"),
    "media":    ("#eff6ff", "#1d4ed8", "rgba(37, 99, 235, 0.2)"),
    "commerce": ("#fff1f2", "#be123c", "rgba(225, 29, 72, 0.2)"),
}


def font_face(weight: int, style_name: str) -> str:
    woff2 = (FONTS / f"inter-v12-latin-{style_name}.woff2").as_uri()
    return (
        "@font-face{font-family:'Inter';font-style:normal;"
        f"font-weight:{weight};font-display:block;"
        f"src:url('{woff2}') format('woff2');}}"
    )


def build_html() -> str:
    badge_css = "\n".join(
        f".badge-{k}{{background:{bg};color:{fg};box-shadow:inset 0 0 0 1px {ring};}}"
        for k, (bg, fg, ring) in BADGES.items()
    )

    tiles = ""
    for name, label, key, issuer in ONTOLOGIES:
        tiles += f"""
      <div class="card">
        <div class="card-top">
          <span class="ont-name">{name}</span>
          <span class="badge badge-{key}">{label}</span>
        </div>
        <p class="issuer">{issuer}</p>
      </div>"""

    # CTA tile — completes the 3x3 grid (8 ontologies + 1 CTA).
    tiles += """
      <div class="card cta">
        <div class="cta-plus">+</div>
        <p class="cta-title">Help us add other standards as well</p>
        <p class="cta-sub">Suggest one at data-landscape.com/industry-ontologies</p>
      </div>"""

    logo_svg = LOGO.read_text()

    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
{font_face(400, "regular")}
{font_face(500, "500")}
{font_face(600, "600")}
{font_face(700, "700")}
*{{margin:0;padding:0;box-sizing:border-box;}}
html,body{{width:{WIDTH}px;height:{HEIGHT}px;}}
body{{
  font-family:'Inter',system-ui,sans-serif;
  background:#f5f5ff;
  background-image:radial-gradient(circle at 85% 12%,#eef2ff 0%,#f5f5ff 45%);
  padding:40px 52px 44px;
  display:flex;flex-direction:column;
  -webkit-font-smoothing:antialiased;
}}
.header{{display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:20px;}}
.eyebrow{{
  font-size:14px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;
  color:#4f46e5;margin-bottom:6px;
}}
.title{{font-size:36px;font-weight:700;color:#111827;letter-spacing:-.02em;line-height:1.1;}}
.brand{{display:flex;align-items:center;gap:11px;padding-top:2px;}}
.brand svg{{width:38px;height:42px;}}
.brand .wm{{font-size:15px;font-weight:600;color:#6b7280;}}
.grid{{
  flex:1;min-height:0;display:grid;
  grid-template-columns:repeat(3,1fr);
  grid-template-rows:repeat(3,1fr);
  gap:14px;
}}
.card{{
  background:#fff;border:1px solid #e5e7eb;border-radius:12px;
  padding:0 22px;display:flex;flex-direction:column;justify-content:center;
  box-shadow:0 1px 2px 0 rgba(0,0,0,.04);overflow:hidden;
}}
.card-top{{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:7px;}}
.ont-name{{font-size:21px;font-weight:700;color:#111827;letter-spacing:-.01em;}}
.issuer{{font-size:14px;color:#6b7280;}}
.badge{{
  display:inline-flex;align-items:center;border-radius:9999px;
  padding:3px 11px;font-size:12.5px;font-weight:600;white-space:nowrap;
}}
{badge_css}
.cta{{
  background:#eef2ff;border:2px dashed #a5b4fc;box-shadow:none;
  align-items:center;text-align:center;gap:5px;padding:0 16px;
}}
.cta-plus{{
  width:30px;height:30px;border-radius:9999px;background:#4f46e5;color:#fff;
  font-size:21px;font-weight:600;line-height:30px;margin-bottom:3px;
}}
.cta-title{{font-size:16px;font-weight:700;color:#3730a3;line-height:1.2;}}
.cta-sub{{font-size:12px;font-weight:500;color:#6366f1;line-height:1.3;}}
</style></head><body>
  <div class="header">
    <div>
      <div class="eyebrow">Industry Ontology Standards</div>
      <div class="title">Ontologies for specific industries</div>
    </div>
    <div class="brand">{logo_svg}<span class="wm">data-landscape.com</span></div>
  </div>
  <div class="grid">{tiles}
  </div>
</body></html>"""


def ensure_chromium() -> None:
    """Install Chromium on first run so the script is genuinely standalone."""
    print("Installing Chromium for Playwright (one-time)...", file=sys.stderr)
    subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        check=True,
    )


async def render() -> Path:
    html = build_html()
    with tempfile.NamedTemporaryFile(
        "w", suffix=".html", dir=ROOT, delete=False, encoding="utf-8"
    ) as fh:
        tmp = Path(fh.name)
        fh.write(html)

    try:
        async with async_playwright() as p:
            try:
                browser = await p.chromium.launch()
            except PlaywrightError as e:
                if "Executable doesn't exist" not in str(e):
                    raise
                ensure_chromium()
                browser = await p.chromium.launch()

            context = await browser.new_context(
                viewport={"width": WIDTH, "height": HEIGHT},
                device_scale_factor=2,
            )
            page = await context.new_page()
            await page.goto(tmp.as_uri(), wait_until="networkidle")
            await page.evaluate("document.fonts.ready")
            await page.wait_for_timeout(200)

            OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
            await page.screenshot(
                path=str(OUT_PATH),
                clip={"x": 0, "y": 0, "width": WIDTH, "height": HEIGHT},
            )
            await browser.close()
    finally:
        tmp.unlink(missing_ok=True)
    return OUT_PATH


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate the industry-ontologies social preview card."
    )
    # Accepted for CI parity with the other generators; the card is template
    # driven and does not read the served site.
    parser.add_argument("base_url", nargs="?", default=None,
                        help="Ignored (kept for CI invocation parity).")
    parser.parse_args()

    out_path = asyncio.run(render())
    size = out_path.stat().st_size
    print(f"Wrote {out_path.relative_to(ROOT)} ({size:,} bytes, {WIDTH}x{HEIGHT}@2x)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
