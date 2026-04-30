# Data Landscape

Source for [data-landscape.com](https://data-landscape.com) — an interactive landscape of the open standards that power a modern data architecture.

Static site, served by GitHub Pages from the repository root. No build step.

## Local preview

Any static file server works, e.g.:

```sh
python3 -m http.server 8000
# or
npx serve .
```

Then open http://localhost:8000.

## Deploying

Pushing to `main` deploys via GitHub Pages. The `CNAME` file binds the site to `data-landscape.com`.

## Maintained by

[Entropy Data](https://www.entropy-data.com).
