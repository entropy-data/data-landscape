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

## Deploy

Pushing to `main` deploys via GitHub Pages. The `CNAME` file binds the site to `www.data-landscape.com` (the apex `data-landscape.com` redirects to www).

## Maintained by

[Entropy Data](https://www.entropy-data.com).
