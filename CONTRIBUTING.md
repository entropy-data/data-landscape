# Contributing

Thanks for your interest in improving [data-landscape.com](https://www.data-landscape.com). This guide covers how to add, fix, or extend standards on the landscape.

## Getting started

```sh
npm install        # one-off
npm run dev        # tailwind watcher + serve on :3000
```

Open http://localhost:3000 to see your changes.

## Editing a standard

Every standard — both its tile on the landscape and its drawer content — lives in [`standards.json`](./standards.json). To add, fix, or extend a standard, edit that file. The HTML in `index.html` only declares the panel layout; tiles render automatically from the JSON via Alpine `x-for`.

Each entry is keyed by a slug and has the shape:

```json
{
  "name": "ODCS",
  "fullName": "Open Data Contract Standard",
  "category": "API Interfaces",
  "logo": "/media/icons/standards-map/logos/bitol.svg",
  "umbrella": "BITOL @ LF",
  "highlight": true,
  "governance": "BITOL / Linux Foundation",
  "status": "v3.1 stable; v3.2 in progress",
  "description": [
    "First paragraph.",
    "Second paragraph."
  ],
  "note": "Optional amber callout, e.g. acronym collisions.",
  "links": [
    { "label": "Official site", "url": "https://bitol.io" }
  ],
  "firstReleased": 2023,
  "tier":          "stable"
}
```

- `category` must match one of the panel headers in `index.html` (e.g. *API Interfaces*, *File Formats*, *Catalog APIs*). Mismatched categories silently drop the tile.
- `logo` is the path to the tile's logo asset under `/media/icons/standards-map/logos/`. Without it the entry won't render as a tile (useful when adding a draft entry).
- `umbrella` is the short label shown beneath the name on the tile (e.g. `LF`, `BITOL @ LF`, `OASIS`). It also drives the org filter chips — clicking *LF* keeps every tile whose `umbrella` (or `umbrellaSearch`) contains "LF".
- `umbrellaSearch` (optional) — separate string used only for filter matching when the visible label differs from the search keywords. Example: tile shows `ODM` but `umbrellaSearch` is `OpenDataMesh` so the *LF* filter still picks it up.
- `vendor: true` (optional) — applies the muted single-vendor styling to the tile and the *Vendor* filter chip counts it.
- `highlight: true` (optional) — applies the indigo "highlighted" treatment used for the picks Entropy Data bets on.

- `firstReleased` shows in the *Compare* table view.
- `tier` is optional — when present it overrides the derivation from `status`. Valid values: `stable`, `emerging`, `legacy`, `vendor`.
- `niche` (boolean, optional) — set to `true` for narrowly-used or specialised standards. Niche entries are hidden from the default landscape and from the PDF, and only appear when a visitor flips the **Niche** toggle in the toolbar (`?include=niche` in the URL). Use this to admit deliberate omissions without bloating the headline grid.
- `nicheReason` (string, required when `niche: true`) — short explanation of *why* the entry is niche. Surfaced as a slate callout at the top of the drawer ("Why this is listed as niche") so curious readers see the editorial rationale before the description.
- Setting `tier: "legacy"` does double duty: it drives the gray *legacy* badge in the drawer **and** hides the entry behind the **Legacy** toggle (`?include=legacy`). Legacy entries get a strong black border on the tile when the toggle is on so they read as "superseded but still in use".

## Adding a new standard

1. Drop the logo asset into `/media/icons/standards-map/logos/` (SVG preferred, PNG OK).
2. Add a new entry to `standards.json` keyed by a unique slug, with at minimum `name`, `category`, `logo`, `umbrella`, `description`, and `links`. The tile appears automatically in the matching panel.
3. If your `category` is brand new (not already listed in `index.html` as a panel), add the panel block to the relevant section in `index.html` — header (icon + `<span class="name">`) and a `category-panel-body` with the standard `x-for` template. Existing categories require no HTML changes.

For a niche or legacy standard (one you want available behind a toolbar toggle but not in the default landscape or the PDF):

- Set `"niche": true` (with a `nicheReason`) or `"tier": "legacy"` on the entry. That's all — `tilesIn()` filters them out by default and the relevant toolbar toggle (`?include=niche` / `?include=legacy`) reveals them.

Category count badges, chip counts, and Compare-table rows update reactively from the JSON — nothing in the HTML needs editing for a regular tile addition.

## Submitting changes

1. Fork the repo and create a branch.
2. Verify your change locally with `npm run dev`. Open the drawer for the standard you touched and confirm the content renders correctly in both the grid and *Compare* views.
3. Open a pull request describing the standard and citing the source(s) for any factual claims (governance body, version status, release year).

## Regenerating artefacts

These only need updating when the visual layout or content of the landscape changes meaningfully. Maintainers typically handle this before release.

- **PDF** (`data-landscape.pdf`): start a local server (`npm run dev` or `python -m http.server 8000`), then `uv run scripts/generate-pdf.py http://127.0.0.1:8000/`.
- **Social preview** (`media/social/data-architecture-landscape.png`, 1200×630, `og:image`): `./scripts/generate-social-preview.sh` — rasterises page 1 of the current PDF and letterboxes it. Requires `poppler` and `imagemagick` (`brew install poppler imagemagick`).

## Editorial guidelines

- Keep `description` factual and neutral. Two short paragraphs is plenty.
- Use `note` sparingly — reserve it for genuine ambiguity (e.g. acronym collisions, deprecated names).
- Prefer official project URLs over blog posts or vendor pages in `links`.
- `governance` should name the body that stewards the standard, not the company that originated it.

## Questions

Open an issue on the repository, or reach out to the maintainers at [Entropy Data](https://www.entropy-data.com).
