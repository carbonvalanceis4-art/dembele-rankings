# Dembélé Rankings

A small GitHub Pages site that ranks football players whose surname is **Dembélé** by current market value.

## Architecture

- `index.html` — static site shell
- `style.css` — responsive styling
- `app.js` — client-side search, sorting, and rendering
- `data/players.json` — generated player data
- `.github/workflows/update-data.yml` — scheduled data refresh (to be added with the data-source adapter)

## Data source

The intended source is Transfermarkt or a compatible football-data service. Transfermarkt does not provide a simple, official public API for this use case, so the project should **not scrape Transfermarkt directly from the browser**. A server-side/scheduled data collector is preferable, and the static site should consume only the generated JSON.

The displayed values are market-value estimates, not transfer fees or wages.

## GitHub Pages

The site is designed to be completely static and can be served from GitHub Pages. In the repository settings, enable Pages using the `main` branch and the repository root once the project is ready.

## Development

No build system is required for the frontend. Open `index.html` through a local static HTTP server so that `fetch("data/players.json")` works.

For example:

```bash
python -m http.server 8000
```

Then visit `http://localhost:8000`.

## Data-source note

Before automating collection, verify the selected provider's terms of service, robots rules, attribution requirements, and rate limits. If an API key is required, keep it in GitHub Actions Secrets; never put it in `app.js` or committed JSON.
