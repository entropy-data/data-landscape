# Data Landscape

Source for [www.data-landscape.com](https://www.data-landscape.com) — an interactive landscape of the open standards that power a modern data architecture.

Static site, served by GitHub Pages from the repository root.

## Develop

```sh
npm install        # one-off
npm run dev        # tailwind watcher + serve on :3000
```

`npm run dev` starts the Tailwind v4 watcher and a static server on http://localhost:3000.

## Build

```sh
npm run build      # produces dist/output.css (minified)
```

`dist/output.css` is checked in so GitHub Pages can serve the site without a build step.

## Regenerate artefacts

- **PDF** (`data-landscape.pdf`): start a local server (`npm run dev` or `python -m http.server 8000`), then `uv run scripts/generate-pdf.py http://127.0.0.1:8000/`.
- **Social preview** (`media/social/data-architecture-landscape.png`, 1200×630, `og:image`): `./scripts/generate-social-preview.sh` — rasterises page 1 of the current PDF and letterboxes it. Requires `poppler` and `imagemagick` (`brew install poppler imagemagick`).

## Deploy

Pushing to `main` deploys via GitHub Pages. The `CNAME` file binds the site to `www.data-landscape.com` (the apex `data-landscape.com` redirects to www).

## Contributing

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

`firstReleased` shows in the *Compare* table view. `tier` is optional — when present it overrides the derivation from `status`. Valid values: `stable`, `emerging`, `legacy`, `vendor`.

Adding a new tile to the grid still requires an HTML edit in `index.html` (button + logo) plus a matching entry in `standards.json`.

## Maintained by

[Entropy Data](https://www.entropy-data.com).
