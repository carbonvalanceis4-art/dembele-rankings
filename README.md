# Dembélé Rankings

A small GitHub Pages site that ranks football players whose surname is **Dembélé** by current market value.

## Architecture

- `index.html` — static site shell
- `style.css` — responsive styling
- `app.js` — client-side search, sorting, and rendering
- `data/players.json` — generated ranking data
- `scripts/update_data.py` — broad player discovery and Transfermarkt ID enrichment
- `.github/workflows/update-data.yml` — scheduled data refresh
- `.github/workflows/pages.yml` — GitHub Pages deployment

## Live data pipeline

Transfermarkt does not offer a documented public developer API. The project therefore uses third-party Apify actors that expose Transfermarkt data as structured JSON.

The refresh is deliberately split into two stages:

1. **Discovery:** a Transfermarkt search actor searches for both `Dembele` and `Dembélé`, requesting up to 500 results per query. The script then applies its own exact normalized-surname test and deduplicates players by Transfermarkt player ID.
2. **Enrichment:** those stable Transfermarkt player IDs are sent directly to the profile actor. This avoids relying on search relevance ordering when retrieving current market values and profile information.

The discovery step refuses to publish data if either query reaches the 500-result ceiling, because that could indicate that the population was truncated. It also refuses to publish if any discovered player cannot be enriched. This is intentional: an incomplete refresh is better than silently publishing an incomplete ranking.

The resulting JSON contains the discovered population, current market values, player metadata, and the discovery queries used for the refresh.

Apify's current Transfermarkt scraper documentation supports up to 500 search results for the discovery actor and direct player-ID lookup for profile enrichment. citeturn1search0turn1search5

### Required GitHub secret

Add an Actions secret named:

```text
APIFY_API_TOKEN
```

The token is used only inside GitHub Actions and is never committed to the repository or exposed to the browser. The workflow can be run manually from **Actions → Update Dembélé rankings → Run workflow** after the secret is configured.

The scheduled refresh currently runs **every six hours**. It can be changed later if a different refresh interval makes more sense.

## GitHub Pages

The repository includes a Pages deployment workflow. In **Settings → Pages**, select **GitHub Actions** as the build/deployment source if GitHub has not already enabled Pages for the repository.

Once enabled, pushes to `main` deploy the static site automatically.

## Development

No frontend build system is required. Serve the repository through a local HTTP server so that `fetch("data/players.json")` works.

```bash
python -m http.server 8000
```

Then open `http://localhost:8000`.

## Data interpretation

Market value is Transfermarkt's editorial estimate, not a transfer fee, salary, or guaranteed sale price. The project is an independent fan project and is not affiliated with Transfermarkt.

The pipeline intentionally does not place an API key in `app.js`: GitHub Pages is a public static host, so any browser-visible credential would be exposed.

## Future ideas

- Historical value charts for each player
- Daily/weekly rank changes
- Player portraits and profile links
- A "biggest risers/fallers" view
- Historical snapshots for comparing the Dembélé family of players over time
