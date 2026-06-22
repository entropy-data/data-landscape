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
     governance, opinionated judgement, and canonical URL. Convention
     emerging for LLM-targeted summaries; cheap and additive.

* `llms-full.txt`
   - The complete per-standard dump (full description prose, status,
     first-release year, judgement + rationale, links) so answer engines can
     ingest everything in a single fetch without executing JS.

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
LLMS_FULL_TXT = ROOT / "llms-full.txt"
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


_EMERGING_RE = re.compile(r"\b(emerging|experimental)\b|\bv?0\.\d")


def tier_of(entry: dict) -> str:
    """Mirror of the Alpine `tierOf` getter — used here so the prerender
    script can apply tier-driven CSS classes (emerging, legacy, …) to the
    static tile HTML."""
    if entry.get("tier"):
        return entry["tier"]
    status = (entry.get("status") or "").lower()
    if _EMERGING_RE.search(status):
        return "emerging"
    if entry.get("vendor"):
        return "vendor"
    if "legacy" in status:
        return "legacy"
    return "stable"


def html_attr(value: str) -> str:
    """Escape a string for use inside double-quoted HTML attributes."""
    return (
        value.replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


JUDGEMENT_RANK = {
    "Adopt": 0,
    "Situational": 1,
    "Assess": 2,
    "Caution": 3,
}

JUDGEMENT_CLASS = {
    "Adopt": "j-adopt",
    "Situational": "j-situational",
    "Assess": "j-assess",
    "Caution": "j-caution",
}


def judgement_rank(entry: dict) -> int:
    return JUDGEMENT_RANK.get(entry.get("judgement"), len(JUDGEMENT_RANK))


def renderable_name_counts(standards: "OrderedDict[str, dict]") -> dict[str, int]:
    """Count how many distinct renderable entries share each `name`.

    Counts by entry (not by category) so a multi-category standard like Lance
    isn't mistaken for a name collision. Used to disambiguate genuine clashes
    (e.g. the two "ODPS" specs) wherever the name surfaces — JSON-LD, llms.txt.
    """
    counts: dict[str, int] = {}
    for entry in standards.values():
        if renderable(entry):
            counts[entry["name"]] = counts.get(entry["name"], 0) + 1
    return counts


def display_label(entry: dict, name_counts: dict[str, int]) -> str:
    """Entry name, suffixed with its umbrella when the bare name is ambiguous."""
    label = entry["name"]
    if name_counts.get(label, 0) > 1 and entry.get("umbrella"):
        label = f"{label} ({entry['umbrella']})"
    return label


def judgement_line(entry: dict) -> str:
    """`Judgement — reason` as a single citable string, or '' when absent."""
    judgement = entry.get("judgement")
    if not judgement:
        return ""
    reason = (entry.get("judgementReason") or "").strip()
    return f"{judgement} — {reason}" if reason else judgement


def render_tile(
    slug: str,
    entry: dict,
    indent: str = "              ",
    *,
    with_id: bool = True,
) -> str:
    """Produce the static HTML for one tile button.

    `with_id=False` suppresses the `id="<slug>-summary"` attribute — used for
    repeat renderings of the same entry (e.g. dbt appearing in two panels) so
    the id stays unique across the document.
    """
    classes = ["item"]
    if entry.get("vendor"):
        classes.append("item-vendor")
    if entry.get("highlight"):
        classes.append("item-highlighted")
    judgement = entry.get("judgement")
    j_class = JUDGEMENT_CLASS.get(judgement)
    if j_class:
        classes.append(j_class)
    cls = " ".join(classes)
    umbrella_search = entry.get("umbrellaSearch") or entry.get("umbrella", "")
    id_attr = f' id="{slug}-summary"' if with_id else ""
    # Searchable text: name + fullName + umbrella, lowercased. The toolbar
    # search box does substring matching against this attribute, so the
    # data lives on the tile to keep DOM filtering O(N) and JS-light.
    search_text = " ".join(filter(None, [
        slug,
        entry.get("name", ""),
        entry.get("fullName", ""),
        entry.get("umbrella", ""),
        umbrella_search,
    ])).lower()
    judgement_header = (
        f'{indent}  <span class="item-judgement">{html_attr(judgement)}</span>\n'
        if judgement else ""
    )
    pick_ribbon = (
        f'{indent}  <span class="item-pick" role="img" aria-label="Highlighted by Entropy Data" '
        f'data-tooltip="Entropy Data pick">🏅</span>\n'
        if entry.get("highlight") else ""
    )
    return (
        f'{indent}<button type="button"{id_attr} class="{html_attr(cls)}"\n'
        f'{indent}        data-umbrella="{html_attr(umbrella_search)}"\n'
        f'{indent}        data-search="{html_attr(search_text)}"\n'
        f'{indent}        @click="selectedId = \'{slug}\'">\n'
        f'{judgement_header}'
        f'{pick_ribbon}'
        f'{indent}  <img class="item-logo" src="{html_attr(entry["logo"])}" alt="" loading="lazy">\n'
        f'{indent}  <span class="item-name">{html_attr(entry["name"])}</span>\n'
        f'{indent}  <span class="item-umbrella">{html_attr(entry["umbrella"])}</span>\n'
        f'{indent}</button>'
    )


def short_description(entry: dict, max_chars: int = 280) -> str:
    """First paragraph of `description`, trimmed to a sentence near max_chars.

    Used for per-DefinedTerm descriptions in JSON-LD — gives LLMs a one-line
    summary without dumping the full prose.
    """
    paragraphs = entry.get("description") or []
    if not paragraphs:
        return entry.get("fullName") or entry.get("name", "")
    text = paragraphs[0].strip()
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    # Prefer ending on a sentence boundary; fall back to a word boundary.
    last_stop = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "))
    if last_stop >= max_chars - 80:
        return cut[: last_stop + 1].strip()
    last_space = cut.rfind(" ")
    return cut[:last_space].rstrip(",;:") + "…"


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

    def tile_order(entry: dict) -> tuple[int, int]:
        """Order tiles within a panel by judgement (Adopt → Caution); vendor
        specs sink to the bottom of their judgement bucket so the
        independently-governed picks lead each colour band."""
        return (judgement_rank(entry), 1 if entry.get("vendor") else 0)

    # Track which slugs have already been emitted with their id="<slug>-summary"
    # attribute. Multi-category entries (e.g. dbt) appear in more than one panel;
    # only the first occurrence carries the id so the document stays valid.
    seen_ids: set[str] = set()

    def replace(match: re.Match) -> str:
        category = match.group("category")
        indent = match.group("indent")
        candidates = [
            (slug, entry)
            for slug, entry in standards.items()
            if renderable(entry) and category in categories_of(entry)
        ]
        # Preserve JSON insertion order within each judgement bucket.
        candidates.sort(key=lambda pair: tile_order(pair[1]))
        tiles = []
        for slug, entry in candidates:
            with_id = slug not in seen_ids
            seen_ids.add(slug)
            tiles.append(render_tile(slug, entry, indent=indent, with_id=with_id))
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
    name_counts = renderable_name_counts(standards)
    iso_modified, _ = last_commit_date()
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
                    # Disambiguate genuine name clashes (e.g. the two "ODPS"
                    # specs) so answer engines don't conflate them.
                    "name": display_label(entry, name_counts),
                    "description": short_description(entry),
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
            "dateModified": iso_modified,
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
        {
            # The curated dataset behind the page — freely fetchable JSON.
            # Advertising it as a Dataset gives LLM/agent crawlers a direct,
            # machine-readable entry point to the full per-standard facts.
            "@type": "Dataset",
            "@id": f"{SITE}/#dataset",
            "name": "Data Landscape — Open Standards Dataset",
            "description": (
                "Machine-readable catalogue of the open standards that power a "
                "modern data architecture, with governance, status, and an "
                "opinionated adopt/situational/assess/caution judgement per "
                "standard. Curated by Entropy Data."
            ),
            "url": f"{SITE}/",
            "dateModified": iso_modified,
            "isAccessibleForFree": True,
            "creator": {
                "@type": "Organization",
                "name": "Entropy Data",
                "url": "https://www.entropy-data.com",
            },
            "distribution": [
                {
                    "@type": "DataDownload",
                    "encodingFormat": "application/json",
                    "contentUrl": f"{SITE}/standards.json",
                },
                {
                    "@type": "DataDownload",
                    "encodingFormat": "text/markdown",
                    "contentUrl": f"{SITE}/llms-full.txt",
                },
            ],
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
    """Returns (iso_yyyy_mm_dd, friendly 'Month Year') for the last data update.

    Tracks standards.json so the footer reflects when the curated data
    actually changed, not unrelated repo edits.
    """
    try:
        out = subprocess.check_output(
            ["git", "log", "-1", "--format=%cI", "--", "standards.json"],
            cwd=ROOT, text=True,
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
        f'Data last updated <time datetime="{iso}">{friendly}</time>'
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
        "  <url>",
        f"    <loc>{SITE}/industry-ontologies.html</loc>",
        f"    <lastmod>{today}</lastmod>",
        "    <changefreq>monthly</changefreq>",
        "    <priority>0.6</priority>",
        "  </url>",
    ]
    for slug, entry in standards.items():
        if not renderable(entry):
            continue
        # Anchored URL — Google de-duplicates fragment URLs against the canonical
        # root, so these enrich the per-tile signal without competing for ranking.
        lines.append("  <url>")
        lines.append(f"    <loc>{SITE}/#{slug}-summary</loc>")
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

    name_counts = renderable_name_counts(standards)

    out = []
    out.append("# Data Landscape — Open Standards for Modern Data Architecture")
    out.append("")
    out.append(
        "An opinionated, interactive map of the open standards that power a modern "
        "data architecture. Curated by Entropy Data. Source of truth: "
        f"{SITE}/standards.json (JSON, machine-readable, freely fetchable)."
    )
    out.append("")
    out.append(
        "Each standard carries a judgement — Adopt, Situational, Assess, or "
        "Caution — with a one-line rationale. For the full per-standard prose, "
        f"status, and links, see {SITE}/llms-full.txt."
    )
    out.append("")
    out.append(f"- Site: {SITE}/")
    out.append(f"- Data: {SITE}/standards.json")
    out.append(f"- Full text: {SITE}/llms-full.txt")
    out.append(f"- Industry ontologies: {SITE}/industry-ontologies.html")
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
            judgement = entry.get("judgement")
            if judgement:
                tags.append(judgement.lower())
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
            label = display_label(entry, name_counts)
            judgement_str = judgement_line(entry)
            verdict = f" **{judgement_str}**" if judgement_str else ""
            out.append(
                f"- [{label}]({SITE}/?std={slug}) — "
                f"{entry.get('fullName', entry['name'])}. "
                f"Governance: {governance}.{verdict}{tag_str}"
            )
        out.append("")
    LLMS_TXT.write_text("\n".join(out))
    print(f"  llms.txt: {sum(len(v) for v in by_category.values())} entries (counted across categories)")


def write_llms_full_txt(standards: "OrderedDict[str, dict]") -> None:
    """Write llms-full.txt — the complete, citable per-standard dump.

    Where llms.txt is a concise index, this carries everything an answer
    engine needs without executing JS or parsing JSON: full description
    prose, governance, status, first-release year, the opinionated judgement
    with its rationale, and reference links. One fetch, plain markdown.
    Each standard appears once (with all its categories listed) rather than
    duplicated per category.
    """
    name_counts = renderable_name_counts(standards)

    out = []
    out.append("# Data Landscape — Open Standards (Full Reference)")
    out.append("")
    out.append(
        "Complete reference for every open standard in the Data Landscape, "
        "curated by Entropy Data. Each entry lists governance, status, an "
        "opinionated judgement (Adopt / Situational / Assess / Caution) with "
        "rationale, a full description, and links. The concise index lives at "
        f"{SITE}/llms.txt; the machine-readable source is {SITE}/standards.json."
    )
    out.append("")
    out.append(f"- Site: {SITE}/")
    out.append(f"- Data: {SITE}/standards.json")
    out.append(f"- Index: {SITE}/llms.txt")
    out.append("")

    for slug, entry in standards.items():
        if not renderable(entry):
            continue
        label = display_label(entry, name_counts)
        full_name = entry.get("fullName", entry["name"])
        out.append(f"## {label} — {full_name}")
        out.append("")
        out.append(f"- URL: {SITE}/?std={slug}")
        cats = categories_of(entry)
        if cats:
            out.append(f"- Category: {', '.join(cats)}")
        if entry.get("governance"):
            out.append(f"- Governance: {entry['governance']}")
        if entry.get("status"):
            out.append(f"- Status: {entry['status']}")
        if entry.get("firstReleased"):
            out.append(f"- First released: {entry['firstReleased']}")
        judgement_str = judgement_line(entry)
        if judgement_str:
            out.append(f"- Judgement: {judgement_str}")
        out.append("")
        for paragraph in entry.get("description") or []:
            out.append(paragraph.strip())
            out.append("")
        links = entry.get("links") or []
        if links:
            out.append("Links:")
            for link in links:
                lbl = link.get("label") or link.get("url", "")
                url = link.get("url", "")
                out.append(f"- {lbl}: {url}")
            out.append("")

    LLMS_FULL_TXT.write_text("\n".join(out))
    rendered = sum(1 for e in standards.values() if renderable(e))
    print(f"  llms-full.txt: {rendered} standards (full text)")


def main() -> int:
    standards = load_standards()
    html = INDEX.read_text()

    html = replace_panel_bodies(html, standards)
    html = replace_jsonld(html, standards)
    html = replace_last_updated(html)

    INDEX.write_text(html)

    write_sitemap(standards)
    write_llms_txt(standards)
    write_llms_full_txt(standards)

    print("prerender: done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
