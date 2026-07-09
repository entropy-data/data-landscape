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

`npm run build` also runs `npm run prerender`, which regenerates from `standards.json`:

- the static tile markup, JSON-LD, and footer date inside `index.html`
- one page per standard under `standards/<slug>/index.html`
- `sitemap.xml`, `llms.txt`, `llms-full.txt`

All of it is checked in, so GitHub Pages serves the site without a build step. Edit `standards.json`, never the generated files.

## Regenerate artefacts

- **PDF** (`data-landscape.pdf`): start a local server (`npm run dev` or `python -m http.server 8000`), then `uv run scripts/generate-pdf.py http://127.0.0.1:8000/`. Add `--variant full` to produce `data-landscape-full.pdf`, which includes niche & legacy standards.
- **Social preview** (`media/social/data-architecture-landscape.png`, 1200×630, `og:image`): `./scripts/generate-social-preview.sh` — rasterises page 1 of the current PDF and letterboxes it. Requires `poppler` and `imagemagick` (`brew install poppler imagemagick`).

## Deploy

Pushing to `main` deploys via GitHub Pages. The `CNAME` file binds the site to `www.data-landscape.com` (the apex `data-landscape.com` redirects to www).

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md).

## Maintained by

[Entropy Data](https://www.entropy-data.com).
