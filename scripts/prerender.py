#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# ///
"""Prerender SEO/LLM-readable artefacts from standards.json.

Reads standards.json (the single source of truth) and writes:

* `index.html`
   - Replaces each `<div class="category-panel-body">` body — between the
     `<!-- prerender:tiles category="X" -->` marker and the matching
     `<!-- /prerender -->` marker — with the static tile links that the
     Alpine `x-for` would have produced. Crawlers and LLMs that don't
     execute JS now see all 70+ standards in the static HTML.
   - Rewrites the JSON-LD `<script type="application/ld+json">` graph so it
     stays in sync with standards.json (DefinedTermSet + ItemList + Dataset)
     and with the FAQ markup (FAQPage, parsed straight out of the page).
   - Replaces the `<span id="last-updated">` widget with a build-time date
     pulled from the latest git commit (no runtime fetch to api.github.com).

* `standards/<slug>/index.html`
   - One indexable page per standard: title, description, judgement and its
     rationale, governance, links, and related standards, with self-canonical
     URLs, breadcrumbs, and DefinedTerm JSON-LD. The landscape itself is a
     single JS-driven page, so without these the per-standard prose is
     invisible to crawlers and unaddressable by a search result.

* `categories/<slug>/index.html`
   - One indexable page per category (Contracts, Lineage, Open Table Formats,
     …), listing its standards grouped by judgement. These are the pages that
     answer "which open standard should I use for X?" — the question the
     landscape exists to settle — and they give the per-standard pages a
     parent to sit under.

* `sitemap.xml`
   - Every indexable URL: the two hand-written pages plus one entry per
     category and per standard.

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
import html as html_lib
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
STANDARDS_DIR = ROOT / "standards"
CATEGORIES_DIR = ROOT / "categories"
SITEMAP = ROOT / "sitemap.xml"
LLMS_TXT = ROOT / "llms.txt"
LLMS_FULL_TXT = ROOT / "llms-full.txt"
SITE = "https://www.data-landscape.com"


def std_path(slug: str) -> str:
    """Site-root-relative URL of a standard's own page."""
    return f"/standards/{slug}/"


def std_url(slug: str) -> str:
    """Absolute, canonical URL of a standard's own page."""
    return f"{SITE}{std_path(slug)}"


def cat_slug(category: str) -> str:
    """URL slug for a category name, e.g. 'Open Table Formats' -> 'open-table-formats'."""
    slug = re.sub(r"[^a-z0-9]+", "-", category.lower()).strip("-")
    if not slug:
        raise SystemExit(f"prerender: category {category!r} produced an empty slug")
    return slug


def cat_path(category: str) -> str:
    return f"/categories/{cat_slug(category)}/"


def cat_url(category: str) -> str:
    return f"{SITE}{cat_path(category)}"


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


# The rubric behind every `judgement` value. Repeated verbatim into llms.txt and
# llms-full.txt so an answer engine that fetches only one of them still knows
# what "Adopt" is asserting.
JUDGEMENT_RUBRIC = [
    ("Adopt", "The standard to reach for in new work. Proven, multi-vendor, "
              "clearly the default for its slot."),
    ("Situational", "The right answer in some contexts but not others. Pick "
                    "deliberately based on the constraint."),
    ("Assess", "Promising but not yet proven for production-default use. "
               "Track it and prototype, but don't commit your architecture."),
    ("Caution", "We'd avoid it for new work — superseded or fading, but still "
                "encountered in existing systems."),
]


def sameas_links(entry: dict, limit: int = 3) -> list[str]:
    """Reference URLs that identify the standard (spec homepage, repo, …)."""
    urls = [link.get("url") for link in (entry.get("links") or []) if link.get("url")]
    return urls[:limit]


_TAG_RE = re.compile(r"<[^>]+>")


def html_to_text(fragment: str) -> str:
    """Flatten an HTML fragment to readable plain text.

    Used to lift the FAQ answers out of index.html into FAQPage JSON-LD and the
    llms.txt files, so the questions live in exactly one place — the markup a
    human reads — and every derived artefact stays in sync with it.
    """
    text = re.sub(r"(?i)<li[^>]*>", "\n- ", fragment)
    text = re.sub(r"(?i)</li>", "", text)
    text = re.sub(r"(?i)</(p|ul|div)>", "\n", text)
    text = _TAG_RE.sub("", text)
    text = html_lib.unescape(text)
    # Collapse runs of spaces/tabs, then runs of blank lines.
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{2,}", "\n\n", text)
    # Keep list items adjacent — a blank line between bullets reads as separate
    # one-item lists to a markdown parser.
    text = re.sub(r"\n{2,}(?=- )", "\n", text)
    return text.strip()


_SECTION_RE = re.compile(
    r'<h2 class="landscape-section-title">(?P<title>.*?)</h2>(?P<body>.*?)</section>',
    re.DOTALL,
)
_CATEGORY_MARKER_RE = re.compile(r'<!-- prerender:tiles category="([^"]+)" -->')


def parse_taxonomy(html: str) -> "OrderedDict[str, tuple[str, str]]":
    """Map each category to the landscape section it sits in.

    Derived from index.html rather than hardcoded here: the section headings
    and the `prerender:tiles` markers are already the source of truth for how
    the landscape is grouped, and a second copy of that grouping would drift.

    Returns `{category: (section_name, section_blurb)}`, e.g.
    `{"Contracts": ("Definition", "how data is described"), ...}`.
    """
    taxonomy: "OrderedDict[str, tuple[str, str]]" = OrderedDict()
    for match in _SECTION_RE.finditer(html):
        title = html_lib.unescape(_TAG_RE.sub("", match.group("title"))).strip()
        # "Definition — how data is described" -> ("Definition", "how data is described")
        name, _, blurb = title.partition("—")
        for category in _CATEGORY_MARKER_RE.findall(match.group("body")):
            taxonomy[category] = (name.strip(), blurb.strip())
    if not taxonomy:
        raise SystemExit("prerender: no landscape sections parsed — has the markup drifted?")
    return taxonomy


_FAQ_BLOCK_RE = re.compile(r"<!-- FAQ -->(.*?)<!-- Thank you -->", re.DOTALL)
_DETAILS_RE = re.compile(r"<details\b[^>]*>(.*?)</details>", re.DOTALL)
_SUMMARY_RE = re.compile(r"<summary\b[^>]*>\s*<span>(.*?)</span>", re.DOTALL)


def extract_faq(html: str) -> list[tuple[str, str]]:
    """Pull (question, answer) pairs out of the FAQ section of index.html."""
    block = _FAQ_BLOCK_RE.search(html)
    if not block:
        raise SystemExit("prerender: FAQ block not found — has the markup drifted?")
    pairs = []
    for details in _DETAILS_RE.findall(block.group(1)):
        summary = _SUMMARY_RE.search(details)
        if not summary:
            continue
        question = html_to_text(summary.group(1))
        answer_html = details.split("</summary>", 1)[1] if "</summary>" in details else ""
        answer = html_to_text(answer_html)
        if question and answer:
            pairs.append((question, answer))
    if not pairs:
        raise SystemExit("prerender: FAQ block matched but no questions parsed")
    return pairs


def render_tile(
    slug: str,
    entry: dict,
    indent: str = "              ",
    *,
    with_id: bool = True,
) -> str:
    """Produce the static HTML for one tile.

    The tile is an `<a>` pointing at the standard's own page, not a `<button>`:
    that gives crawlers 80-odd real internal links to follow, lets people
    middle-click or cmd-click a standard into a new tab, and still works with
    JavaScript off. `openStandard()` intercepts the plain left click and opens
    the drawer instead of navigating.

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
        f'{indent}<a href="{html_attr(std_path(slug))}"{id_attr} class="{html_attr(cls)}"\n'
        f'{indent}   data-umbrella="{html_attr(umbrella_search)}"\n'
        f'{indent}   data-search="{html_attr(search_text)}"\n'
        f'{indent}   @click="openStandard($event, \'{slug}\')">\n'
        f'{judgement_header}'
        f'{pick_ribbon}'
        f'{indent}  <img class="item-logo" src="{html_attr(entry["logo"])}" alt="" loading="lazy">\n'
        f'{indent}  <span class="item-name">{html_attr(entry["name"])}</span>\n'
        f'{indent}  <span class="item-umbrella">{html_attr(entry["umbrella"])}</span>\n'
        f'{indent}</a>'
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


PUBLISHER = {
    "@type": "Organization",
    "name": "Entropy Data",
    "url": "https://www.entropy-data.com",
    "logo": {
        "@type": "ImageObject",
        "url": f"{SITE}/media/logo_fuchsia_v2.png",
    },
}

PAGE_DESCRIPTION = (
    "An opinionated, interactive map of the open standards that power a "
    "modern data architecture — ODCS, ODPS, OSI, OpenAPI, Iceberg, "
    "OpenLineage, OpenTelemetry and more. Curated by Entropy Data."
)


def replace_jsonld(html: str, standards: "OrderedDict[str, dict]") -> str:
    """Rewrite the JSON-LD block so it stays in sync with standards.json + the FAQ.

    The graph carries four things answer engines actually consume: the article
    itself, a DefinedTermSet of every standard (each term carrying its
    judgement as `disambiguatingDescription` and its spec URLs as `sameAs`),
    the FAQ as a FAQPage, and the raw dataset as a fetchable Dataset.
    """
    name_counts = renderable_name_counts(standards)
    iso_modified, _ = last_commit_date()
    term_set_id = f"{SITE}/#standards-set"

    item_list_entries = []
    for i, (slug, entry) in enumerate(
        ((s, e) for s, e in standards.items() if renderable(e)), start=1
    ):
        term = {
            "@type": "DefinedTerm",
            "@id": std_url(slug),
            # Disambiguate genuine name clashes (e.g. the two "ODPS"
            # specs) so answer engines don't conflate them.
            "name": display_label(entry, name_counts),
            "termCode": slug,
            "description": short_description(entry),
            "url": std_url(slug),
            "inDefinedTermSet": {"@id": term_set_id},
        }
        # The opinionated verdict is the whole point of this page — hand it to
        # answer engines as structured data rather than burying it in prose.
        verdict = judgement_line(entry)
        if verdict:
            term["disambiguatingDescription"] = verdict
        same_as = sameas_links(entry)
        if same_as:
            term["sameAs"] = same_as if len(same_as) > 1 else same_as[0]
        item_list_entries.append(
            {"@type": "ListItem", "position": i, "item": term}
        )

    faq_questions = [
        {
            "@type": "Question",
            "name": question,
            "acceptedAnswer": {"@type": "Answer", "text": answer},
        }
        for question, answer in extract_faq(html)
    ]

    graph = [
        {
            "@type": "WebSite",
            "@id": f"{SITE}/#website",
            "url": f"{SITE}/",
            "name": "Data Landscape",
            "description": PAGE_DESCRIPTION,
            "inLanguage": "en",
            "publisher": PUBLISHER,
        },
        {
            "@type": ["WebPage", "FAQPage"],
            "@id": f"{SITE}/",
            "url": f"{SITE}/",
            "name": "Data Landscape — Open Standards for Modern Data Architecture",
            "description": PAGE_DESCRIPTION,
            "inLanguage": "en",
            "isPartOf": {"@id": f"{SITE}/#website"},
            "dateModified": iso_modified,
            "primaryImageOfPage": {
                "@type": "ImageObject",
                "url": f"{SITE}/media/social/data-architecture-landscape.png",
            },
            "mainEntity": faq_questions,
        },
        {
            "@type": "TechArticle",
            "@id": f"{SITE}/#article",
            "headline": "Data Landscape — Open Standards for Modern Data Architecture",
            "description": PAGE_DESCRIPTION,
            "datePublished": "2026-04-28",
            "dateModified": iso_modified,
            "inLanguage": "en",
            "isAccessibleForFree": True,
            "license": "https://opensource.org/licenses/MIT",
            "author": {
                "@type": "Person",
                "name": "Dr. Simon Harrer",
                "url": "https://www.linkedin.com/in/simonharrer/",
            },
            "publisher": PUBLISHER,
            "image": f"{SITE}/media/social/data-architecture-landscape.png",
            "about": {"@id": term_set_id},
            "mainEntityOfPage": {"@id": f"{SITE}/"},
        },
        {
            # A glossary of standards is literally a DefinedTermSet. Typing it
            # as one (rather than only as an ordered ItemList) lets an answer
            # engine treat each tile as a term it can define and cite.
            "@type": "DefinedTermSet",
            "@id": term_set_id,
            "name": "Open Standards for Modern Data Architecture",
            "description": (
                "Every open standard in the Data Landscape, each with an "
                "opinionated judgement: Adopt, Situational, Assess, or Caution."
            ),
            "url": f"{SITE}/",
            "inLanguage": "en",
            "creator": PUBLISHER,
            "hasDefinedTerm": [item["item"]["@id"] for item in item_list_entries],
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
            "license": "https://opensource.org/licenses/MIT",
            "keywords": [
                "open standards",
                "data architecture",
                "data contracts",
                "data products",
                "data mesh",
                "metadata",
            ],
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
        lambda _: f'<script type="application/ld+json">{serialised}</script>',
        html,
        count=1,
    )
    if n != 1:
        raise SystemExit("prerender: JSON-LD block not found")
    print(f"  json-ld synced: {len(item_list_entries)} terms, {len(faq_questions)} FAQ entries")
    return new_html


def file_commit_date(relpath: str) -> str:
    """ISO date of the last commit touching `relpath`, or today if unknown."""
    try:
        out = subprocess.check_output(
            ["git", "log", "-1", "--format=%cI", "--", relpath],
            cwd=ROOT, text=True,
        ).strip()
        return datetime.fromisoformat(out).date().isoformat()
    except Exception:
        return date.today().isoformat()


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
        f'<span id="last-updated" class="text-gray-500">'
        f'Data last updated <time datetime="{iso}">{friendly}</time>'
        f'</span>'
    )
    html, n1 = span_pattern.subn(span_replacement, html, count=1)
    if n1 != 1:
        raise SystemExit("prerender: last-updated span not found")

    # 1b) Keep the Open Graph modified timestamp on the same clock.
    html, _ = re.subn(
        r'<meta property="article:modified_time" content="[^"]*"/>',
        f'<meta property="article:modified_time" content="{iso}"/>',
        html,
        count=1,
    )

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


def write_sitemap(
    standards: "OrderedDict[str, dict]", taxonomy: "OrderedDict[str, tuple[str, str]]"
) -> None:
    data_modified, _ = last_commit_date()
    ontologies_modified = file_commit_date("industry-ontologies.html")
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        "  <url>",
        f"    <loc>{SITE}/</loc>",
        f"    <lastmod>{data_modified}</lastmod>",
        "    <changefreq>weekly</changefreq>",
        "    <priority>1.0</priority>",
        "  </url>",
        "  <url>",
        f"    <loc>{SITE}/industry-ontologies.html</loc>",
        f"    <lastmod>{ontologies_modified}</lastmod>",
        "    <changefreq>monthly</changefreq>",
        "    <priority>0.6</priority>",
        "  </url>",
    ]
    for category in taxonomy:
        lines.append("  <url>")
        lines.append(f"    <loc>{xml_escape(cat_url(category))}</loc>")
        lines.append(f"    <lastmod>{data_modified}</lastmod>")
        lines.append("    <changefreq>monthly</changefreq>")
        lines.append("    <priority>0.8</priority>")
        lines.append("  </url>")
    for slug, entry in standards.items():
        if not renderable(entry):
            continue
        # The standard's own page — a real, self-canonical URL. The old
        # `#<slug>-summary` entries were dropped: crawlers strip the fragment
        # before fetching, so they all collapsed into duplicates of the root.
        lines.append("  <url>")
        lines.append(f"    <loc>{xml_escape(std_url(slug))}</loc>")
        lines.append(f"    <lastmod>{data_modified}</lastmod>")
        lines.append("    <changefreq>monthly</changefreq>")
        lines.append("    <priority>0.7</priority>")
        lines.append("  </url>")
    lines.append("</urlset>")
    SITEMAP.write_text("\n".join(lines) + "\n")
    rendered = sum(1 for e in standards.values() if renderable(e))
    print(f"  sitemap.xml: 2 pages + {len(taxonomy)} categories + {rendered} standards")


PAGE_HEAD_COMMON = """  <link rel="icon" href="/media/logo_fuchsia_v2.svg" type="image/svg+xml"/>
  <link rel="icon" href="/media/logo_fuchsia_v2.ico" type="image/x-icon"/>
  <link rel="apple-touch-icon" href="/media/logo_fuchsia_v2.png"/>
  <link rel="preload" href="/fonts/inter-v12-latin-regular.woff2" as="font" type="font/woff2" crossorigin>
  <link rel="preload" href="/fonts/inter-v12-latin-500.woff2" as="font" type="font/woff2" crossorigin>
  <link rel="stylesheet" href="/dist/output.css">
  <style>
    .sr-only {
      position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px;
      overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border-width: 0;
    }
    .skip-link {
      position: absolute; top: 0; left: 0; z-index: 60; transform: translateY(-120%);
      background: #4f46e5; color: white; font-weight: 600; font-size: 0.875rem;
      padding: 0.6rem 1rem; border-bottom-right-radius: 6px; transition: transform 120ms ease;
    }
    .skip-link:focus { transform: translateY(0); }
    /* Links in running text need more than colour to be distinguishable
       (WCAG 1.4.1) — indigo-600 on gray body copy is under 3:1. */
    main p a[href] {
      text-decoration: underline;
      text-underline-offset: 2px;
      text-decoration-thickness: 1px;
    }
    .fact {
      display: inline-flex; align-items: center; border-radius: 9999px;
      padding: 0.125rem 0.6rem; font-size: 0.75rem; font-weight: 600; line-height: 1.25rem;
      background: #f3f4f6; color: #374151;
    }
    .fact-adopt       { background: #ecfdf5; color: #065f46; }
    .fact-situational { background: #fffbeb; color: #92400e; }
    .fact-assess      { background: #f8fafc; color: #334155; }
    .fact-caution     { background: #fef2f2; color: #991b1b; }
    .callout { border-left-width: 4px; border-radius: 0 0.375rem 0.375rem 0; padding: 1rem; }
    .callout-adopt       { border-color: #10b981; background: #ecfdf5; color: #064e3b; }
    .callout-situational { border-color: #f59e0b; background: #fffbeb; color: #78350f; }
    .callout-assess      { border-color: #94a3b8; background: #f8fafc; color: #1e293b; }
    .callout-caution     { border-color: #ef4444; background: #fef2f2; color: #7f1d1d; }
    .callout-info        { border-color: #6366f1; background: #eef2ff; color: #312e81; }
    .callout-note        { border-color: #fbbf24; background: #fffbeb; color: #78350f; }
    @media (prefers-reduced-motion: reduce) {
      *, *::before, *::after {
        animation-duration: 0.01ms !important; transition-duration: 0.01ms !important;
        scroll-behavior: auto !important;
      }
    }
  </style>
"""

PAGE_FOOTER = """
<footer class="bg-white border-t border-gray-200">
  <div class="mx-auto max-w-7xl px-6 py-8 lg:px-8">
    <nav class="flex flex-wrap items-center justify-center gap-x-6 gap-y-2 text-xs text-gray-500" aria-label="Footer">
      <a href="https://www.entropy-data.com" class="flex items-center gap-1 hover:text-gray-900">
        <img src="/media/logo_fuchsia_v2.svg" alt="" class="h-3 w-auto"/>
        <span>Entropy Data</span>
      </a>
      <a href="/" class="hover:text-gray-900">Data Landscape</a>
      <a href="https://www.entropy-data.com/legal-notice" class="hover:text-gray-900">Legal Notice</a>
      <a href="https://www.entropy-data.com/privacy-policy" class="hover:text-gray-900">Privacy Policy</a>
      <a href="/standards.json" class="hover:text-gray-900" title="Machine-readable source data for the landscape">Data (JSON)</a>
      <a href="/llms.txt" class="hover:text-gray-900" title="LLM-friendly summary of the landscape">llms.txt</a>
      <a href="https://github.com/entropy-data/data-landscape/blob/main/LICENSE" class="hover:text-gray-900" title="MIT License">MIT License</a>
    </nav>
  </div>
</footer>

<script src="/js/script.js"></script>
</body>
</html>
"""

JUDGEMENT_SLUG = {
    "Adopt": "adopt",
    "Situational": "situational",
    "Assess": "assess",
    "Caution": "caution",
}

STANDARDIZATION_LABEL = {
    "formal-standard": "Formal standard",
    "foundation": "Foundation",
    "community": "Community",
    "vendor-led": "Vendor-led",
}


def esc(value) -> str:
    """Escape a value for HTML text content."""
    return html_lib.escape(str(value), quote=False)


def subtitle(entry: dict, label: str) -> str:
    """The entry's fullName, or '' when it just repeats the name.

    13 entries (OpenLineage, GraphQL, Arrow, …) set `fullName` to the name
    itself; rendering both gives "OpenLineage — OpenLineage".
    """
    full_name = entry.get("fullName", "")
    if not full_name or full_name in (entry.get("name"), label):
        return ""
    return full_name


def related_subtitle(entry: dict, name_counts: dict[str, int], cls: str = "text-gray-500") -> str:
    """` — Full Name` span for list rows, omitted when it adds nothing."""
    sub = subtitle(entry, display_label(entry, name_counts))
    return f'<span class="{cls}"> — {esc(sub)}</span>' if sub else ""


def meta_description(text: str, limit: int = 160) -> str:
    """Trim to something a SERP snippet will show whole (~160 chars)."""
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[:limit]
    stop = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "))
    if stop >= limit - 60:
        return cut[: stop + 1].strip()
    return cut[: cut.rfind(" ")].rstrip(",;:") + "…"


# A breadcrumb trail: [(name, site-relative href or None for the current page), …]
Trail = "list[tuple[str, str | None]]"


def breadcrumb_nodes(canonical: str, trail: "Trail") -> dict:
    """A BreadcrumbList. Schema.org wants absolute `item` URLs."""
    return {
        "@type": "BreadcrumbList",
        "@id": f"{canonical}#breadcrumb",
        "itemListElement": [
            {"@type": "ListItem", "position": i, "name": name,
             **({"item": f"{SITE}{href}"} if href else {})}
            for i, (name, href) in enumerate(trail, start=1)
        ],
    }


def breadcrumb_html(trail: "Trail") -> str:
    """Visible breadcrumb matching `breadcrumb_nodes`."""
    crumbs = []
    for name, href in trail:
        if href:
            crumbs.append(f'<li><a href="{html_attr(href)}" class="hover:text-gray-900">{esc(name)}</a></li>')
            crumbs.append('<li aria-hidden="true">/</li>')
        else:
            crumbs.append(f'<li><span aria-current="page" class="text-gray-700">{esc(name)}</span></li>')
    body = "\n        ".join(crumbs)
    return (
        '    <nav aria-label="Breadcrumb" class="text-xs text-gray-500">\n'
        '      <ol class="flex flex-wrap items-center gap-2">\n'
        f'        {body}\n'
        '      </ol>\n'
        '    </nav>'
    )


def by_judgement(
    entries: list[tuple[str, dict]]
) -> "OrderedDict[str, list[tuple[str, dict]]]":
    """Group entries into Adopt/Situational/Assess/Caution buckets, in that order."""
    buckets: "OrderedDict[str, list[tuple[str, dict]]]" = OrderedDict(
        (name, []) for name, _ in JUDGEMENT_RUBRIC
    )
    for slug, entry in entries:
        judgement = entry.get("judgement")
        if judgement in buckets:
            buckets[judgement].append((slug, entry))
    return OrderedDict((k, v) for k, v in buckets.items() if v)


def category_page_html(
    category: str,
    section: tuple[str, str],
    entries: list[tuple[str, dict]],
    siblings: list[str],
    name_counts: dict[str, int],
    iso_modified: str,
) -> str:
    """Render one category's page.

    This is the page that answers "which open standard should I use for
    lineage / table formats / data quality?" — a question people and answer
    engines actually ask, and one the single-page landscape could never rank
    for. It leads with the verdict, then the reasoning.
    """
    section_name, section_blurb = section
    canonical = cat_url(category)
    buckets = by_judgement(entries)
    count = len(entries)
    adopt = [display_label(e, name_counts) for _, e in buckets.get("Adopt", [])]

    lead = (
        f"{count} open standard{'s' if count != 1 else ''} for {category} in a modern "
        f"data architecture, each with an opinionated judgement: Adopt, Situational, "
        f"Assess, or Caution."
    )
    if adopt:
        lead_adopt = (
            f"Start with {', '.join(adopt[:-1]) + ' and ' + adopt[-1] if len(adopt) > 1 else adopt[0]}."
        )
    else:
        lead_adopt = "Nothing here is a safe default yet."
    description = meta_description(f"{lead} {lead_adopt}")

    trail: "Trail" = [("Data Landscape", "/"), (category, None)]
    graph = [
        {
            "@type": ["WebPage", "CollectionPage"],
            "@id": canonical,
            "url": canonical,
            "name": f"{category} — Open Standards | Data Landscape",
            "description": description,
            "inLanguage": "en",
            "isPartOf": {"@id": f"{SITE}/#website"},
            "dateModified": iso_modified,
            "breadcrumb": {"@id": f"{canonical}#breadcrumb"},
            "mainEntity": {"@id": f"{canonical}#standards"},
        },
        breadcrumb_nodes(canonical, trail),
        {
            "@type": "ItemList",
            "@id": f"{canonical}#standards",
            "name": f"Open standards for {category}",
            "numberOfItems": count,
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": i,
                    "item": {
                        "@type": "DefinedTerm",
                        "@id": std_url(slug),
                        "name": display_label(entry, name_counts),
                        "url": std_url(slug),
                        **({"disambiguatingDescription": judgement_line(entry)}
                           if judgement_line(entry) else {}),
                    },
                }
                # Judgement order, so position 1 is the standard we'd actually pick.
                for i, (slug, entry) in enumerate(
                    [pair for bucket in buckets.values() for pair in bucket], start=1
                )
            ],
        },
    ]
    jsonld = json.dumps(
        {"@context": "https://schema.org", "@graph": graph},
        separators=(",", ":"),
        ensure_ascii=False,
    )

    sections = []
    for judgement, pairs in buckets.items():
        meaning = dict(JUDGEMENT_RUBRIC)[judgement]
        j_slug = JUDGEMENT_SLUG[judgement]
        rows = []
        for slug, entry in pairs:
            reason = (entry.get("judgementReason") or "").strip()
            reason_html = f'<p class="mt-1 text-sm text-gray-700">{esc(reason)}</p>' if reason else ""
            governance = entry.get("governance")
            gov_html = (
                f'<p class="mt-1 text-xs text-gray-500">{esc(governance)}</p>' if governance else ""
            )
            rows.append(
                f'        <li class="border-t border-gray-100 py-4">\n'
                f'          <a href="{html_attr(std_path(slug))}" class="font-semibold text-indigo-600 hover:text-indigo-500 hover:underline">'
                f'{esc(display_label(entry, name_counts))}</a>\n'
                f'          {related_subtitle(entry, name_counts, "text-gray-600")}\n'
                f'          {reason_html}\n'
                f'          {gov_html}\n'
                f'        </li>'
            )
        rows_html = "\n".join(rows)
        sections.append(
            f'      <section class="mt-10">\n'
            f'        <h2 class="text-lg font-bold tracking-tight text-gray-900">\n'
            f'          <span class="fact fact-{j_slug}">{esc(judgement)}</span>\n'
            f'          <span class="ml-2">{len(pairs)} standard{"s" if len(pairs) != 1 else ""}</span>\n'
            f'        </h2>\n'
            f'        <p class="mt-2 text-sm text-gray-600">{esc(meaning)}</p>\n'
            f'        <ul class="mt-2">\n{rows_html}\n        </ul>\n'
            f'      </section>'
        )
    sections_html = "\n\n".join(sections)

    siblings_html = ""
    if siblings:
        items = "\n".join(
            f'          <li><a href="{html_attr(cat_path(other))}" '
            f'class="text-indigo-600 hover:text-indigo-500 hover:underline">{esc(other)}</a></li>'
            for other in siblings
        )
        siblings_html = (
            f'      <h2 class="mt-12 text-lg font-bold tracking-tight text-gray-900">'
            f'More in {esc(section_name)}</h2>\n'
            f'      <p class="mt-2 text-sm text-gray-600">{esc(section_name)} covers {esc(section_blurb)}.</p>\n'
            f'      <ul class="mt-4 space-y-2 text-sm list-disc pl-5">\n{items}\n      </ul>'
        )

    social_image = f"{SITE}/media/social/data-architecture-landscape.png"
    title = f"{category} — Open Standards | Data Landscape"

    return f"""<!doctype html>
<html lang="en">
<head>
  <title>{esc(title)}</title>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="description" content="{html_attr(description)}">
  <meta name="robots" content="index,follow,max-image-preview:large,max-snippet:-1">
  <meta name="color-scheme" content="light">
  <meta name="author" content="Dr. Simon Harrer">
  <meta property="og:site_name" content="Data Landscape">
  <meta property="og:type" content="website"/>
  <meta property="og:title" content="{html_attr(category)} — Open Standards"/>
  <meta property="og:description" content="{html_attr(description)}"/>
  <meta property="og:url" content="{canonical}"/>
  <meta property="og:locale" content="en_US"/>
  <meta property="og:image" content="{social_image}"/>
  <meta property="og:image:width" content="1200"/>
  <meta property="og:image:height" content="630"/>
  <meta name="twitter:card" content="summary_large_image"/>
  <meta name="twitter:title" content="{html_attr(category)} — Open Standards"/>
  <meta name="twitter:description" content="{html_attr(description)}"/>
  <meta name="twitter:image" content="{social_image}"/>
  <meta name="theme-color" content="#4f46e5"/>

  <link rel="canonical" href="{canonical}"/>
  <link rel="alternate" type="text/markdown" title="llms-full.txt" href="/llms-full.txt"/>
  <script type="application/ld+json">{jsonld}</script>
{PAGE_HEAD_COMMON}</head>
<body class="bg-white">

<a href="#main" class="skip-link">Skip to content</a>

<main id="main" tabindex="-1" class="mt-8 mb-20">
  <div class="mx-auto max-w-3xl px-6 lg:px-8 mt-10">

{breadcrumb_html(trail)}

    <header class="mt-6">
      <p class="text-xs font-semibold uppercase tracking-wider text-indigo-600">{esc(section_name)} — {esc(section_blurb)}</p>
      <h1 class="mt-2 text-3xl font-bold tracking-tight text-gray-900 sm:text-4xl">{esc(category)}</h1>
      <p class="mt-3 text-lg leading-8 text-gray-600">{esc(lead)}</p>
      <p class="mt-2 text-base leading-7 text-gray-700">{esc(lead_adopt)}</p>
    </header>

{sections_html}

{siblings_html}

    <div class="mt-12 rounded-lg border border-indigo-200 bg-indigo-50 px-6 py-6 text-sm">
      <p class="font-semibold text-gray-900">See {esc(category)} in context</p>
      <p class="mt-1 text-gray-700">
        These standards are one panel of the interactive
        <a href="/" class="text-indigo-600 hover:text-indigo-500">Data Landscape</a>,
        which maps every open standard a modern data architecture is built on. The
        underlying data is a single <a href="/standards.json" class="text-indigo-600 hover:text-indigo-500">JSON file</a>;
        disagree with a judgement?
        <a href="https://github.com/entropy-data/data-landscape/issues/new" target="_blank" rel="noopener"
           class="text-indigo-600 hover:text-indigo-500">Open an issue</a>.
      </p>
    </div>

  </div>
</main>
{PAGE_FOOTER}"""


def write_category_pages(
    standards: "OrderedDict[str, dict]", taxonomy: "OrderedDict[str, tuple[str, str]]"
) -> None:
    """Write `categories/<slug>/index.html` for every landscape category."""
    name_counts = renderable_name_counts(standards)
    iso_modified, _ = last_commit_date()
    CATEGORIES_DIR.mkdir(exist_ok=True)

    wanted = set()
    for category, section in taxonomy.items():
        entries = [
            (slug, entry)
            for slug, entry in standards.items()
            if renderable(entry) and category in categories_of(entry)
        ]
        if not entries:
            continue
        siblings = [
            other for other, other_section in taxonomy.items()
            if other != category and other_section[0] == section[0]
        ]
        slug = cat_slug(category)
        wanted.add(slug)
        page_dir = CATEGORIES_DIR / slug
        page_dir.mkdir(exist_ok=True)
        (page_dir / "index.html").write_text(
            category_page_html(category, section, entries, siblings, name_counts, iso_modified)
        )

    removed = prune_generated_pages(CATEGORIES_DIR, wanted)
    suffix = f", {removed} stale removed" if removed else ""
    print(f"  categories/: {len(wanted)} pages{suffix}")


def prune_generated_pages(root: Path, wanted: set[str]) -> int:
    """Delete generated `<root>/<slug>/index.html` dirs that are no longer wanted.

    Only removes directories whose sole content is the index.html we wrote, so
    a stray file someone parked there is never silently destroyed.
    """
    removed = 0
    for page_dir in root.iterdir():
        if not page_dir.is_dir() or page_dir.name in wanted:
            continue
        contents = list(page_dir.iterdir())
        if contents and all(p.name == "index.html" for p in contents):
            (page_dir / "index.html").unlink()
            page_dir.rmdir()
            removed += 1
    return removed


def related_standards(
    slug: str, entry: dict, standards: "OrderedDict[str, dict]", limit: int = 8
) -> list[tuple[str, dict]]:
    """Other renderable standards sharing a category, best-judged first."""
    cats = set(categories_of(entry))
    siblings = [
        (other_slug, other)
        for other_slug, other in standards.items()
        if other_slug != slug
        and renderable(other)
        and cats & set(categories_of(other))
    ]
    siblings.sort(key=lambda pair: (judgement_rank(pair[1]), pair[1]["name"].lower()))
    return siblings[:limit]


def standard_page_html(
    slug: str,
    entry: dict,
    standards: "OrderedDict[str, dict]",
    name_counts: dict[str, int],
    iso_modified: str,
    taxonomy: "OrderedDict[str, tuple[str, str]]",
) -> str:
    """Render one standard's standalone page.

    These pages exist because the landscape itself is a single JS-driven page:
    every standard's prose lives behind a drawer, invisible to a crawler and
    unaddressable by a search result. One indexable URL per standard turns 80
    hidden drawers into 80 pages that can rank and be cited.
    """
    label = display_label(entry, name_counts)
    name = entry["name"]
    cats = categories_of(entry)
    judgement = entry.get("judgement")
    j_slug = JUDGEMENT_SLUG.get(judgement, "assess")
    description = entry.get("description") or []
    summary = short_description(entry)
    canonical = std_url(slug)
    sub = subtitle(entry, label)
    # NB: `description` above is the list of prose paragraphs from
    # standards.json — keep the meta string under its own name.
    meta_desc = meta_description(summary)
    # The first category the landscape lists this standard under becomes its
    # parent in the breadcrumb; multi-category entries still link them all in
    # the body.
    primary_category = next((c for c in cats if c in taxonomy), None)
    siblings = related_standards(slug, entry, standards)
    # Without a distinct fullName, lean on the category so the title still
    # says what kind of thing this is.
    title = f"{label} — {sub or primary_category or 'Open Standard'} | Data Landscape"
    social_title = f"{label} — {sub}" if sub else label

    # ---- structured data -------------------------------------------------
    term = {
        "@type": "DefinedTerm",
        "@id": canonical,
        "name": label,
        **({"alternateName": sub} if sub else {}),
        "termCode": slug,
        "description": summary,
        "url": canonical,
        "inDefinedTermSet": {
            "@type": "DefinedTermSet",
            "@id": f"{SITE}/#standards-set",
            "name": "Open Standards for Modern Data Architecture",
            "url": f"{SITE}/",
        },
    }
    verdict = judgement_line(entry)
    if verdict:
        term["disambiguatingDescription"] = verdict
    same_as = sameas_links(entry)
    if same_as:
        term["sameAs"] = same_as if len(same_as) > 1 else same_as[0]

    trail: "Trail" = [("Data Landscape", "/")]
    if primary_category:
        trail.append((primary_category, cat_path(primary_category)))
    trail.append((label, None))

    web_page = {
        "@type": "WebPage",
        "@id": canonical,
        "url": canonical,
        "name": title,
        "description": meta_desc,
        "inLanguage": "en",
        "isPartOf": {"@id": f"{SITE}/#website"},
        "dateModified": iso_modified,
        "mainEntity": {"@id": canonical},
        "breadcrumb": {"@id": f"{canonical}#breadcrumb"},
    }
    if siblings:
        web_page["relatedLink"] = [std_url(other) for other, _ in siblings]
    graph = [web_page, breadcrumb_nodes(canonical, trail), term]
    jsonld = json.dumps(
        {"@context": "https://schema.org", "@graph": graph},
        separators=(",", ":"),
        ensure_ascii=False,
    )

    # ---- badges ----------------------------------------------------------
    badges = []
    if judgement:
        badges.append(f'<span class="fact fact-{j_slug}">{esc(judgement)}</span>')
    standardization = entry.get("standardization")
    if standardization:
        badges.append(
            f'<span class="fact">{esc(STANDARDIZATION_LABEL.get(standardization, standardization))}</span>'
        )
    if entry.get("governance"):
        badges.append(f'<span class="fact">{esc(entry["governance"])}</span>')
    if entry.get("firstReleased"):
        badges.append(f'<span class="fact">Since {esc(entry["firstReleased"])}</span>')
    if entry.get("vendor"):
        badges.append('<span class="fact">Single-vendor spec</span>')
    if entry.get("niche"):
        badges.append('<span class="fact">Niche</span>')
    if entry.get("highlight"):
        badges.append('<span class="fact">🏅 Entropy Data pick</span>')

    # ---- body sections ---------------------------------------------------
    parts = []
    if verdict:
        parts.append(
            f'      <div class="mt-8 callout callout-{j_slug} text-sm leading-6">\n'
            f'        <p class="font-semibold">Judgement: {esc(judgement)}</p>\n'
            f'        <p class="mt-1">{esc(entry.get("judgementReason", ""))}</p>\n'
            f'      </div>'
        )
    if description:
        prose = "\n".join(
            f'        <p>{esc(paragraph.strip())}</p>' for paragraph in description
        )
        parts.append(
            f'      <div class="mt-8 space-y-4 text-base leading-7 text-gray-700">\n{prose}\n      </div>'
        )
    if entry.get("standardReason"):
        parts.append(
            f'      <div class="mt-8 callout callout-info text-sm leading-6">\n'
            f'        <p class="font-semibold">Why it counts as a standard</p>\n'
            f'        <p class="mt-1">{esc(entry["standardReason"])}</p>\n'
            f'      </div>'
        )
    if entry.get("nicheReason"):
        parts.append(
            f'      <div class="mt-6 callout callout-assess text-sm leading-6">\n'
            f'        <p class="font-semibold">Why this is listed as niche</p>\n'
            f'        <p class="mt-1">{esc(entry["nicheReason"])}</p>\n'
            f'      </div>'
        )
    if entry.get("note"):
        parts.append(
            f'      <div class="mt-6 callout callout-note text-sm leading-6">\n'
            f'        <p>{esc(entry["note"])}</p>\n'
            f'      </div>'
        )

    facts = []
    if cats:
        facts.append(("Category", esc(", ".join(cats))))
    if entry.get("governance"):
        facts.append(("Governance", esc(entry["governance"])))
    if entry.get("status"):
        facts.append(("Status", esc(entry["status"])))
    if entry.get("firstReleased"):
        facts.append(("First released", esc(entry["firstReleased"])))
    # The judgement is deliberately absent here — the callout above already
    # states it in full, and repeating it verbatim two screens apart is noise.
    facts_html = "\n".join(
        f'          <div class="border-t border-gray-100 pt-3">\n'
        f'            <dt class="text-xs font-semibold uppercase tracking-wide text-gray-500">{term_name}</dt>\n'
        f'            <dd class="mt-1 text-sm text-gray-800">{value}</dd>\n'
        f'          </div>'
        for term_name, value in facts
    )
    parts.append(
        f'      <h2 class="mt-10 text-lg font-bold tracking-tight text-gray-900">At a glance</h2>\n'
        f'      <dl class="mt-4 grid grid-cols-1 gap-x-8 gap-y-3 sm:grid-cols-2">\n{facts_html}\n      </dl>'
    )

    links = entry.get("links") or []
    if links:
        items = "\n".join(
            f'          <li><a href="{html_attr(link["url"])}" target="_blank" rel="noopener"\n'
            f'                 class="text-indigo-600 hover:text-indigo-500 hover:underline">'
            f'{esc(link.get("label") or link["url"])}</a></li>'
            for link in links
            if link.get("url")
        )
        parts.append(
            f'      <h2 class="mt-10 text-lg font-bold tracking-tight text-gray-900">Links</h2>\n'
            f'      <ul class="mt-4 space-y-2 text-sm list-disc pl-5">\n{items}\n      </ul>'
        )

    if siblings:
        items = "\n".join(
            f'          <li><a href="{html_attr(std_path(other_slug))}" '
            f'class="text-indigo-600 hover:text-indigo-500 hover:underline">'
            f'{esc(display_label(other, name_counts))}</a>'
            f'{related_subtitle(other, name_counts)}</li>'
            for other_slug, other in siblings
        )
        linked_cats = " and ".join(
            f'<a href="{html_attr(cat_path(c))}" class="text-indigo-600 hover:text-indigo-500 hover:underline">{esc(c)}</a>'
            if c in taxonomy else esc(c)
            for c in cats
        ) or "the landscape"
        parts.append(
            f'      <h2 class="mt-10 text-lg font-bold tracking-tight text-gray-900">Related standards</h2>\n'
            f'      <p class="mt-2 text-sm text-gray-600">Other standards in {linked_cats}.</p>\n'
            f'      <ul class="mt-4 space-y-2 text-sm list-disc pl-5">\n{items}\n      </ul>'
        )

    body_sections = "\n\n".join(parts)
    logo = entry.get("logo")
    logo_html = (
        f'          <img src="{html_attr(logo)}" alt="" width="56" height="56"\n'
        f'               class="h-14 w-14 flex-shrink-0 object-contain">\n'
        if logo else ""
    )
    badges_html = (
        f'      <div class="mt-5 flex flex-wrap items-center gap-2">\n        '
        + "\n        ".join(badges)
        + "\n      </div>"
        if badges else ""
    )
    subtitle_html = (
        f'          <p class="mt-1 text-lg text-gray-600">{esc(sub)}</p>' if sub else ""
    )
    category_line = " · ".join(
        f'<a href="{html_attr(cat_path(c))}" class="text-indigo-600 hover:text-indigo-500 hover:underline">{esc(c)}</a>'
        if c in taxonomy else esc(c)
        for c in cats
    ) or "Open standard"
    social_image = f"{SITE}/media/social/data-architecture-landscape.png"

    return f"""<!doctype html>
<html lang="en">
<head>
  <title>{esc(title)}</title>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="description" content="{html_attr(meta_desc)}">
  <meta name="robots" content="index,follow,max-image-preview:large,max-snippet:-1">
  <meta name="color-scheme" content="light">
  <meta name="author" content="Dr. Simon Harrer">
  <meta property="og:site_name" content="Data Landscape">
  <meta property="og:type" content="article"/>
  <meta property="og:title" content="{html_attr(social_title)}"/>
  <meta property="og:description" content="{html_attr(meta_desc)}"/>
  <meta property="og:url" content="{canonical}"/>
  <meta property="og:locale" content="en_US"/>
  <meta property="og:image" content="{social_image}"/>
  <meta property="og:image:width" content="1200"/>
  <meta property="og:image:height" content="630"/>
  <meta property="article:modified_time" content="{iso_modified}"/>
  <meta name="twitter:card" content="summary_large_image"/>
  <meta name="twitter:title" content="{html_attr(social_title)}"/>
  <meta name="twitter:description" content="{html_attr(meta_desc)}"/>
  <meta name="twitter:image" content="{social_image}"/>
  <meta name="theme-color" content="#4f46e5"/>

  <link rel="canonical" href="{canonical}"/>
  <link rel="alternate" type="text/markdown" title="llms-full.txt" href="/llms-full.txt"/>
  <script type="application/ld+json">{jsonld}</script>
{PAGE_HEAD_COMMON}</head>
<body class="bg-white">

<a href="#main" class="skip-link">Skip to content</a>

<main id="main" tabindex="-1" class="mt-8 mb-20">
  <div class="mx-auto max-w-3xl px-6 lg:px-8 mt-10">

{breadcrumb_html(trail)}

    <header class="mt-6">
      <p class="text-xs font-semibold uppercase tracking-wider text-indigo-600">{category_line}</p>
      <div class="mt-2 flex items-start gap-4">
{logo_html}        <div>
          <h1 class="text-3xl font-bold tracking-tight text-gray-900 sm:text-4xl">{esc(label)}</h1>
{subtitle_html}
        </div>
      </div>
{badges_html}
    </header>

{body_sections}

    <div class="mt-12 rounded-lg border border-indigo-200 bg-indigo-50 px-6 py-6 text-sm">
      <p class="font-semibold text-gray-900">See {esc(name)} in context</p>
      <p class="mt-1 text-gray-700">
        Open the interactive
        <a href="/?std={html_attr(slug)}" class="text-indigo-600 hover:text-indigo-500">Data Landscape</a>
        to compare {esc(name)} against every other open standard, or grab the
        <a href="/standards.json" class="text-indigo-600 hover:text-indigo-500">raw JSON</a>.
        Spotted something wrong?
        <a href="https://github.com/entropy-data/data-landscape/issues/new" target="_blank" rel="noopener"
           class="text-indigo-600 hover:text-indigo-500">Open an issue</a>.
      </p>
    </div>

  </div>
</main>
{PAGE_FOOTER}"""


def write_standard_pages(
    standards: "OrderedDict[str, dict]", taxonomy: "OrderedDict[str, tuple[str, str]]"
) -> None:
    """Write `standards/<slug>/index.html` for every renderable standard."""
    name_counts = renderable_name_counts(standards)
    iso_modified, _ = last_commit_date()
    STANDARDS_DIR.mkdir(exist_ok=True)

    wanted = {slug for slug, entry in standards.items() if renderable(entry)}
    for slug in sorted(wanted):
        page_dir = STANDARDS_DIR / slug
        page_dir.mkdir(exist_ok=True)
        (page_dir / "index.html").write_text(
            standard_page_html(
                slug, standards[slug], standards, name_counts, iso_modified, taxonomy
            )
        )

    # Drop pages for standards that have since been removed from standards.json.
    removed = prune_generated_pages(STANDARDS_DIR, wanted)
    suffix = f", {removed} stale removed" if removed else ""
    print(f"  standards/: {len(wanted)} pages{suffix}")


def citation_block() -> list[str]:
    """How to cite the landscape — emitted into both llms.txt files."""
    return [
        "## Cite this landscape",
        "",
        "Harrer, S. (2026). *Data Landscape: Open Standards for Modern Data "
        f"Architecture*. Entropy Data. {SITE}/",
        "",
        f"BibTeX: {SITE}/data-landscape.bib. Licensed MIT; attribution appreciated.",
        "",
    ]


def rubric_block() -> list[str]:
    """The meaning of each judgement value."""
    out = ["## What the judgements mean", ""]
    for name, meaning in JUDGEMENT_RUBRIC:
        out.append(f"- **{name}** — {meaning}")
    out.append("")
    return out


def faq_block(html: str) -> list[str]:
    """The page's FAQ, verbatim, as markdown."""
    out = ["## Frequently asked questions", ""]
    for question, answer in extract_faq(html):
        out.append(f"### {question}")
        out.append("")
        out.append(answer)
        out.append("")
    return out


def write_llms_txt(standards: "OrderedDict[str, dict]", html: str) -> None:
    """Write llms.txt — markdown summary aimed at LLM crawlers."""
    by_category: "OrderedDict[str, list[tuple[str, dict]]]" = OrderedDict()
    for slug, entry in standards.items():
        if not renderable(entry):
            continue
        for cat in categories_of(entry):
            by_category.setdefault(cat, []).append((slug, entry))

    name_counts = renderable_name_counts(standards)
    iso_modified, friendly = last_commit_date()

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
        "Caution — with a one-line rationale, and has its own page at "
        f"{SITE}/standards/<slug>/. For the full per-standard prose, status, and "
        f"links in a single fetch, see {SITE}/llms-full.txt."
    )
    out.append("")
    out.append(f"- Site: {SITE}/")
    out.append(f"- Data: {SITE}/standards.json")
    out.append(f"- Full text: {SITE}/llms-full.txt")
    out.append(f"- Industry ontologies: {SITE}/industry-ontologies.html")
    out.append(f"- Sitemap: {SITE}/sitemap.xml")
    out.append(f"- Data last updated: {friendly} ({iso_modified})")
    out.append("")
    out.extend(rubric_block())
    out.append("## Standards by category")
    out.append("")
    for cat, items in by_category.items():
        out.append(f"### {cat}")
        out.append("")
        out.append(f"Category page: {cat_url(cat)}")
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
                f"- [{label}]({std_url(slug)}) — "
                f"{entry.get('fullName', entry['name'])}. "
                f"Governance: {governance}.{verdict}{tag_str}"
            )
        out.append("")
    out.extend(faq_block(html))
    out.extend(citation_block())
    LLMS_TXT.write_text("\n".join(out))
    print(f"  llms.txt: {sum(len(v) for v in by_category.values())} entries (counted across categories)")


def write_llms_full_txt(standards: "OrderedDict[str, dict]", html: str) -> None:
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
    out.extend(rubric_block())

    for slug, entry in standards.items():
        if not renderable(entry):
            continue
        label = display_label(entry, name_counts)
        sub = subtitle(entry, label)
        out.append(f"## {label} — {sub}" if sub else f"## {label}")
        out.append("")
        out.append(f"- URL: {std_url(slug)}")
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

    out.extend(faq_block(html))
    out.extend(citation_block())
    LLMS_FULL_TXT.write_text("\n".join(out))
    rendered = sum(1 for e in standards.values() if renderable(e))
    print(f"  llms-full.txt: {rendered} standards (full text)")


def main() -> int:
    standards = load_standards()
    html = INDEX.read_text()
    taxonomy = parse_taxonomy(html)

    html = replace_panel_bodies(html, standards)
    html = replace_jsonld(html, standards)
    html = replace_last_updated(html)

    INDEX.write_text(html)

    write_standard_pages(standards, taxonomy)
    write_category_pages(standards, taxonomy)
    write_sitemap(standards, taxonomy)
    write_llms_txt(standards, html)
    write_llms_full_txt(standards, html)

    print("prerender: done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
