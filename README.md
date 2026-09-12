# Dembélé Rankings

A small GitHub Pages site that ranks football players whose surname is **Dembélé** by current market value.

## Architecture

- `index.html` — static site shell
- `style.css` — responsive styling
- `app.js` — client-side search, sorting, and rendering
- `data/players.json` — generated ranking data
- `scripts/update_data.py` — filters and normalizes the source records
- `.github/workflows/update-data.yml` — scheduled data refresh
- `.github/workflows/pages.yml` — GitHub Pages deployment

## Live data pipeline

Transfermarkt does not offer a documented public developer API. The project therefore uses a third-party Apify actor that exposes Transfermarkt player records as structured JSON. The scheduled GitHub Action queries the actor for `Dembele`, keeps records whose normalized surname is exactly `dembele`, sorts them by market value, and commits the resulting JSON to the repository.

Apify's API supports running Actors synchronously and returning their dataset items. See the [Apify Actor API documentation](https://docs.apify.com/actors/running).

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
