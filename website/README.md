# OSCAR — Marketing site

Static, zero-build website for the OSCAR project.

```
website/
├── index.html        # all content
├── styles.css        # design tokens + components
├── script.js         # theme toggle + scroll-spy
├── favicon.svg       # brand mark
├── og-image.svg      # social preview (1200×630)
├── robots.txt
├── sitemap.xml
├── vercel.json       # Vercel deploy + cache + security headers
├── netlify.toml      # Netlify deploy + cache + security headers
└── README.md
```

## Stack

Plain HTML + CSS + JS. No framework, no bundler, no build step. Google Fonts (Inter, JetBrains Mono, Fraunces) loaded over the network.

## Local preview

Any static server works. From this directory:

```bash
# Python
python3 -m http.server 8080

# or Node
npx serve .

# then open
open http://localhost:8080
```

## Deploy

### Vercel
```bash
cd website
npx vercel --prod
```
`vercel.json` sets long-lived cache headers on static assets, no-cache on `/`, and adds standard security headers (HSTS, X-Frame-Options, Referrer-Policy, Permissions-Policy).

### Netlify
```bash
cd website
npx netlify-cli deploy --dir=. --prod
```
`netlify.toml` mirrors the Vercel header config.

### GitHub Pages
```bash
# from repo root
git subtree push --prefix website origin gh-pages
```
Then enable Pages → branch `gh-pages` in the repo settings.

### Cloudflare Pages
Point the deploy at this directory (`website/`), build command empty, output directory `.`.

## What to edit

- **Copy / sections** — `index.html`. Sections are clearly demarcated with `<!-- ───── NAME ───── -->` banners.
- **Colors, type, spacing** — `:root` and `[data-theme="dark"]` blocks in `styles.css`.
- **Real numbers in the Results section** — verify against the repo at the tagged version. Commands documented in the on-page callout.
- **OG image** — `og-image.svg`. If a hosting target needs a raster `.png`, render the SVG with e.g. `resvg` or `rsvg-convert`.

## Production checklist

- [x] Semantic HTML5, single `<h1>`, ordered headings
- [x] Skip-to-content link, focus-visible defaults, `prefers-reduced-motion`
- [x] Light + dark theme with `prefers-color-scheme` + manual toggle (persisted)
- [x] Open Graph + Twitter card meta + JSON-LD `SoftwareApplication`
- [x] Long-lived caching on assets, no-cache on root
- [x] HSTS, X-Frame-Options, Referrer-Policy, Permissions-Policy
- [x] Mobile-first, breakpoints at 600 / 720 / 800 / 900 px
- [x] Print stylesheet
- [x] No external runtime deps beyond Google Fonts CSS

## Not included on purpose

Analytics, cookie banners, build pipelines, image processing, blog tooling. Add them only when needed.
