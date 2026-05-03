#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# ///
"""Prerender SEO/LLM-readable artefacts from standards.json.

Reads standards.json (the single source of truth) and writes:

* `index.html`
   - Replaces each `<div class="category-panel-body">` body — between the
     `<!-- prerender:tiles category="X" -->` marker and the matching
     `<!-- /prerender -->` marker — with the static tile buttons that the
     Alpine `x-for` would have produced. Crawlers and LLMs that don't
     execute JS now see all 70+ standards in the static HTML.
   - Rewrites the JSON-LD `<script type="application/ld+json">` ItemList so
     it stays in sync with standards.json (count + entries).
   - Replaces the `<span id="last-updated">` widget with a build-time date
     pulled from the latest git commit (no runtime fetch to api.github.com).

* `sitemap.xml`
   - Root URL plus one entry per standard (`?std=<slug>`) so search engines
     can index the deep-linked drawer state.

* `llms.txt`
   - Markdown summary keyed by category, listing every standard with its
     governance + canonical URL. Convention emerging for LLM-targeted
     summaries; cheap and additive.

Run via `npm run prerender` or as part of `npm run build`. Idempotent —
running it twice produces the same output as running it once.
"""
import json
import re
import subprocess
import sys
from collections import OrderedDict
from datetime import date, datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "index.html"
STANDARDS = ROOT / "standards.json"
SITEMAP = ROOT / "sitemap.xml"
LLMS_TXT = ROOT / "llms.txt"
SITE = "https://www.data-landscape.com"


def load_standards() -> "OrderedDict[str, dict]":
    with STANDARDS.open() as f:
        return json.load(f, object_pairs_hook=OrderedDict)


def categories_of(entry: dict) -> list[str]:
    cat = entry.get("category")
    if cat is None:
        return []
    return cat if isinstance(cat, list) else [cat]


def renderable(entry: dict) -> bool:
    """Whether this entry has enough data to render as a tile."""
    return bool(entry.get("logo")) and bool(entry.get("umbrella"))


def html_attr(value: str) -> str:
    """Escape a string for use inside double-quoted HTML attributes."""
    return (
        value.replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def render_tile(slug: str, entry: dict, indent: str = "              ") -> str:
    """Produce the static HTML for one tile button."""
    classes = ["item"]
    if entry.get("highlight"):
        classes.append("item-highlight")
    if entry.get("vendor"):
        classes.append("item-vendor")
    if entry.get("niche"):
        classes.append("item-niche")
    if entry.get("tier") == "legacy":
        classes.append("item-legacy")
    cls = " ".join(classes)
    umbrella_search = entry.get("umbrellaSearch") or entry.get("umbrella", "")
    return (
        f'{indent}<button type="button" class="{html_attr(cls)}"\n'
        f'{indent}        data-umbrella="{html_attr(umbrella_search)}"\n'
        f'{indent}        @click="selectedId = \'{slug}\'">\n'
        f'{indent}  <img class="item-logo" src="{html_attr(entry["logo"])}" alt="" loading="lazy">\n'
        f'{indent}  <span class="item-name">{html_attr(entry["name"])}</span>\n'
        f'{indent}  <span class="item-umbrella">{html_attr(entry["umbrella"])}</span>\n'
        f'{indent}</button>'
    )


def replace_panel_bodies(html: str, standards: "OrderedDict[str, dict]") -> str:
    """Replace prerender marker blocks with the static tile HTML for that category.

    Each panel body has the shape:

        <div class="category-panel-body">
          <!-- prerender:tiles category="API Interfaces" -->
          ...prerendered tile buttons (overwritten on every run)...
          <!-- /prerender:tiles -->
        </div>
    """
    pattern = re.compile(
        r'(?P<indent>[ \t]*)<!-- prerender:tiles category="(?P<category>[^"]+)" -->'
        r'.*?'
        r'<!-- /prerender:tiles -->',
        re.DOTALL,
    )

    def tile_order(entry: dict) -> int:
        """Stable tiles first, then niche, then legacy at the bottom of each panel."""
        if entry.get("tier") == "legacy":
            return 2
        if entry.get("niche"):
            return 1
        return 0

    def replace(match: re.Match) -> str:
        category = match.group("category")
        indent = match.group("indent")
        candidates = [
            (slug, entry)
            for slug, entry in standards.items()
            if renderable(entry) and category in categories_of(entry)
        ]
        # Preserve JSON insertion order within each tier bucket.
        candidates.sort(key=lambda pair: tile_order(pair[1]))
        tiles = [render_tile(slug, entry, indent=indent) for slug, entry in candidates]
        body = "\n".join(tiles)
        marker_open = f'{indent}<!-- prerender:tiles category="{category}" -->'
        marker_close = f'{indent}<!-- /prerender:tiles -->'
        if body:
            return f"{marker_open}\n{body}\n{marker_close}"
        return f"{marker_open}\n{marker_close}"

    new_html, n = pattern.subn(replace, html)
    if n == 0:
        raise SystemExit("prerender: no panel bodies matched — has the markup drifted?")
    print(f"  panels rerendered: {n}")
    return new_html


def replace_jsonld(html: str, standards: "OrderedDict[str, dict]") -> str:
    """Rewrite the JSON-LD ItemList block so it lists every renderable entry."""
    item_list_entries = []
    for i, (slug, entry) in enumerate(
        ((s, e) for s, e in standards.items() if renderable(e)), start=1
    ):
        item_list_entries.append(
            {
                "@type": "ListItem",
                "position": i,
                "item": {
                    "@type": "DefinedTerm",
                    "name": entry["name"],
                    "url": f"{SITE}/?std={slug}",
                },
            }
        )

    graph = [
        {
            "@type": "TechArticle",
            "@id": f"{SITE}/#article",
            "headline": "Data Landscape — Open Standards for Modern Data Architecture",
            "description": (
                "An opinionated, interactive map of the open standards that power a "
                "modern data architecture — ODCS, ODPS, OSI, OpenAPI, Iceberg, "
                "OpenLineage, OpenTelemetry and more. Curated by Entropy Data."
            ),
            "datePublished": "2026-04-28",
            "author": {
                "@type": "Person",
                "name": "Dr. Simon Harrer",
                "url": "https://www.linkedin.com/in/simonharrer/",
            },
            "publisher": {
                "@type": "Organization",
                "name": "Entropy Data",
                "url": "https://www.entropy-data.com",
                "logo": {
                    "@type": "ImageObject",
                    "url": f"{SITE}/media/logo_fuchsia_v2.png",
                },
            },
            "image": f"{SITE}/media/social/data-architecture-landscape.png",
            "mainEntityOfPage": {
                "@type": "WebPage",
                "@id": f"{SITE}/",
            },
        },
        {
            "@type": "ItemList",
            "@id": f"{SITE}/#standards",
            "name": "Open Standards for Modern Data Architecture",
            "numberOfItems": len(item_list_entries),
            "itemListElement": item_list_entries,
        },
    ]
    payload = {"@context": "https://schema.org", "@graph": graph}
    serialised = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)

    pattern = re.compile(
        r'<script type="application/ld\+json">.*?</script>',
        re.DOTALL,
    )
    new_html, n = pattern.subn(
        f'<script type="application/ld+json">{serialised}</script>',
        html,
        count=1,
    )
    if n != 1:
        raise SystemExit("prerender: JSON-LD block not found")
    print(f"  json-ld synced: {len(item_list_entries)} items")
    return new_html


def last_commit_date() -> tuple[str, str]:
    """Returns (iso_yyyy_mm_dd, friendly 'Month Year') for the latest commit."""
    try:
        out = subprocess.check_output(
            ["git", "log", "-1", "--format=%cI", "--", "."], cwd=ROOT, text=True
        ).strip()
        dt = datetime.fromisoformat(out)
    except Exception:
        dt = datetime.now(tz=timezone.utc)
    iso = dt.date().isoformat()
    friendly = dt.strftime("%B %Y")
    return iso, friendly


def replace_last_updated(html: str) -> str:
    """Replace the JS-fetched last-updated widget with a build-time injection."""
    iso, friendly = last_commit_date()

    # 1) Replace the span: pre-fill content + drop the `hidden` attribute.
    span_pattern = re.compile(
        r'<span id="last-updated"[^>]*>.*?</span>', re.DOTALL
    )
    span_replacement = (
        f'<span id="last-updated" class="text-gray-400">'
        f'Updated <time datetime="{iso}">{friendly}</time>'
        f'</span>'
    )
    html, n1 = span_pattern.subn(span_replacement, html, count=1)
    if n1 != 1:
        raise SystemExit("prerender: last-updated span not found")

    # 2) Remove the runtime fetch script that updates the span.
    script_pattern = re.compile(
        r'<script>\s*fetch\(\s*\'https://api\.github\.com/repos/entropy-data/'
        r'data-landscape/commits[^<]*</script>',
        re.DOTALL,
    )
    html, n2 = script_pattern.subn("", html, count=1)
    if n2 != 1:
        # Already removed — that's fine on subsequent runs.
        pass

    print(f"  last-updated: {friendly} ({iso})")
    return html


def write_sitemap(standards: "OrderedDict[str, dict]") -> None:
    today = date.today().isoformat()
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        "  <url>",
        f"    <loc>{SITE}/</loc>",
        f"    <lastmod>{today}</lastmod>",
        "    <changefreq>weekly</changefreq>",
        "    <priority>1.0</priority>",
        "  </url>",
    ]
    for slug, entry in standards.items():
        if not renderable(entry):
            continue
        lines.append("  <url>")
        lines.append(f"    <loc>{SITE}/?std={slug}</loc>")
        lines.append(f"    <lastmod>{today}</lastmod>")
        lines.append("    <changefreq>monthly</changefreq>")
        lines.append("    <priority>0.7</priority>")
        lines.append("  </url>")
    lines.append("</urlset>")
    SITEMAP.write_text("\n".join(lines) + "\n")
    rendered = sum(1 for e in standards.values() if renderable(e))
    print(f"  sitemap.xml: 1 root + {rendered} standards")


def write_llms_txt(standards: "OrderedDict[str, dict]") -> None:
    """Write llms.txt — markdown summary aimed at LLM crawlers."""
    by_category: "OrderedDict[str, list[tuple[str, dict]]]" = OrderedDict()
    for slug, entry in standards.items():
        if not renderable(entry):
            continue
        for cat in categories_of(entry):
            by_category.setdefault(cat, []).append((slug, entry))

    out = []
    out.append("# Data Landscape — Open Standards for Modern Data Architecture")
    out.append("")
    out.append(
        "An opinionated, interactive map of the open standards that power a modern "
        "data architecture. Curated by Entropy Data. Source of truth: "
        f"{SITE}/standards.json (JSON, machine-readable, freely fetchable)."
    )
    out.append("")
    out.append(f"- Site: {SITE}/")
    out.append(f"- Data: {SITE}/standards.json")
    out.append(f"- Sitemap: {SITE}/sitemap.xml")
    out.append("")
    out.append("## Standards by category")
    out.append("")
    for cat, items in by_category.items():
        out.append(f"### {cat}")
        out.append("")
        for slug, entry in items:
            tier = entry.get("tier")
            niche = entry.get("niche")
            tags = []
            if entry.get("highlight"):
                tags.append("highlighted")
            if niche:
                tags.append("niche")
            if tier == "legacy":
                tags.append("legacy")
            if entry.get("vendor"):
                tags.append("vendor")
            tag_str = f" _{', '.join(tags)}_" if tags else ""
            governance = entry.get("governance", "")
            out.append(
                f"- [{entry['name']}]({SITE}/?std={slug}) — "
                f"{entry.get('fullName', entry['name'])}. "
                f"Governance: {governance}.{tag_str}"
            )
        out.append("")
    LLMS_TXT.write_text("\n".join(out))
    print(f"  llms.txt: {sum(len(v) for v in by_category.values())} entries (counted across categories)")


def main() -> int:
    standards = load_standards()
    html = INDEX.read_text()

    html = replace_panel_bodies(html, standards)
    html = replace_jsonld(html, standards)
    html = replace_last_updated(html)

    INDEX.write_text(html)

    write_sitemap(standards)
    write_llms_txt(standards)

    print("prerender: done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
