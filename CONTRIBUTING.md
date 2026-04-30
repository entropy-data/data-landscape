# Contributing

Thanks for your interest in improving [data-landscape.com](https://www.data-landscape.com). This guide covers how to add, fix, or extend standards on the landscape.

## Getting started

```sh
npm install        # one-off
npm run dev        # tailwind watcher + serve on :3000
```

Open http://localhost:3000 to see your changes.

## Editing a standard

The drawer content for every standard lives in [`standards.json`](./standards.json). To add, fix, or extend a standard, edit that file — not the inline `<script>` in `index.html`.

Each entry is keyed by a slug (the same id referenced from the button's `@click="selectedId = '<slug>'"` in `index.html`) and has the shape:

```json
{
  "name": "ODCS",
  "fullName": "Open Data Contract Standard",
  "category": "API Interfaces",
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

- `firstReleased` shows in the *Compare* table view.
- `tier` is optional — when present it overrides the derivation from `status`. Valid values: `stable`, `emerging`, `legacy`, `vendor`.

## Adding a new standard

1. Add a new entry to `standards.json` keyed by a unique slug.
2. Add a matching tile (button + logo) to the grid in `index.html`. The button's `@click` must reference the same slug.
3. Drop the logo asset into `media/` and reference it from the new tile.

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
