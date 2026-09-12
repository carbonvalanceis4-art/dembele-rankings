#!/usr/bin/env python3
"""Discover a broad Dembélé surname population, then enrich those Transfermarkt IDs."""

import json
import os
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# Discovery uses a scraper whose search endpoint supports up to 500 results.
# Enrichment uses the ID-based actor so the final values come from individual
# Transfermarkt player profiles rather than search ranking.
DISCOVERY_ACTOR_ID = "studio-amba~transfermarkt-scraper"
ENRICHMENT_ACTOR_ID = "incognito_mode~transfermarkt-player-scraper"
APIFY_BASE = "https://api.apify.com/v2/actors"
OUT = Path("data/players.json")
DISCOVERY_QUERIES = ["Dembele", "Dembélé"]
DISCOVERY_LIMIT = 500
ENRICHMENT_BATCH_SIZE = 50


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    return "".join(ch for ch in value if not unicodedata.combining(ch)).lower().strip()


def surname_is_dembele(name: str) -> bool:
    parts = normalize(name).replace("-", " ").split()
    return bool(parts) and parts[-1] == "dembele"


def first_value(record, *keys):
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return value
    return None


def as_number(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    if not isinstance(value, str):
        return None
    text = value.strip().lower().replace("€", "").replace(",", "")
    multiplier = 1
    if text.endswith("bn"):
        multiplier = 1_000_000_000
        text = text[:-2]
    elif text.endswith("b"):
        multiplier = 1_000_000_000
        text = text[:-1]
    elif text.endswith("m") or "mio" in text:
        multiplier = 1_000_000
        text = text.replace("mio", "").replace("m", "")
    elif text.endswith("k"):
        multiplier = 1_000
        text = text[:-1]
    try:
        return int(float(text.strip()) * multiplier)
    except ValueError:
        digits = "".join(ch for ch in value if ch.isdigit())
        return int(digits) if digits else None


def apify_run(actor_id, payload, token):
    url = f"{APIFY_BASE}/{actor_id}/run-sync-get-dataset-items"
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=300) as response:
            records = json.load(response)
    except (HTTPError, URLError, TimeoutError) as exc:
        raise RuntimeError(f"Apify request failed for {actor_id}: {exc}") from exc
    if not isinstance(records, list):
        raise RuntimeError(f"Unexpected Apify response from {actor_id}: expected a JSON array.")
    return records


def discover_player_ids(token):
    """Search broadly for both spellings, then require an exact normalized surname.

    The discovery actor supports up to 500 results per search. If a query fills
    that ceiling, we refuse to publish because the population may be truncated.
    """
    discovered = {}

    for query in DISCOVERY_QUERIES:
        payload = {
            "searchQuery": query,
            "maxResults": DISCOVERY_LIMIT,
            "includeTransferHistory": False,
            "includeMarketValueHistory": False,
        }
        records = apify_run(DISCOVERY_ACTOR_ID, payload, token)
        if len(records) >= DISCOVERY_LIMIT:
            raise RuntimeError(
                f'Discovery query "{query}" returned the {DISCOVERY_LIMIT}-player cap. '
                "The population may be truncated; refusing to publish incomplete data."
            )

        for record in records:
            if not isinstance(record, dict):
                continue
            name = first_value(record, "name", "full_name", "fullName")
            player_id = first_value(record, "playerId", "player_id", "id")
            if not name or not player_id or not surname_is_dembele(name):
                continue
            discovered[str(player_id)] = {
                "id": str(player_id),
                "name": name,
                "profileUrl": first_value(record, "profileUrl", "profile_url", "url"),
            }

    return list(discovered.values())


def enrich_players(player_ids, token):
    """Fetch current Transfermarkt profile data for the discovered IDs."""
    records = []
    for start in range(0, len(player_ids), ENRICHMENT_BATCH_SIZE):
        batch = player_ids[start:start + ENRICHMENT_BATCH_SIZE]
        payload = {
            "playerIds": batch,
            "includeMarketValueHistory": False,
            "includeTransferHistory": False,
            "maxItems": len(batch),
        }
        records.extend(apify_run(ENRICHMENT_ACTOR_ID, payload, token))
    return records


def main():
    token = os.environ.get("APIFY_API_TOKEN")
    if not token:
        print("APIFY_API_TOKEN is not set. Add it as a GitHub Actions secret.", file=sys.stderr)
        return 2

    try:
        discovered = discover_player_ids(token)
        print(f"Discovered {len(discovered)} exact Dembélé surname matches.")
        player_ids = [player["id"] for player in discovered]
        records = enrich_players(player_ids, token)
        print(f"Enriched {len(records)} Transfermarkt player profiles.")
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    players = []
    seen = set()
    for record in records:
        if not isinstance(record, dict):
            continue
        name = first_value(record, "name", "full_name", "fullName")
        player_id = first_value(record, "playerId", "player_id", "id")
        if not name or not player_id or not surname_is_dembele(name):
            continue

        key = str(player_id)
        if key in seen:
            continue
        seen.add(key)

        market_value = as_number(first_value(record, "marketValue", "market_value", "market_value_in_eur"))
        club = first_value(record, "clubName", "currentClub", "club_name", "current_club", "current_club_name")
        nationality = first_value(record, "nationality", "citizenship")
        if isinstance(nationality, list):
            nationality = ", ".join(map(str, nationality))
        age = as_number(first_value(record, "age"))
        position = first_value(record, "position", "positionGroup", "position_group")
        profile_url = first_value(record, "profileUrl", "profile_url", "url")
        portrait_url = first_value(record, "portraitUrl", "portrait_url", "image_url")
        market_value_date = first_value(record, "marketValueLastUpdate", "market_value_last_update")

        players.append({
            "id": key,
            "name": name,
            "club": club,
            "nationality": nationality,
            "age": age,
            "position": position,
            "marketValue": market_value,
            "marketValueDate": market_value_date,
            "profileUrl": profile_url,
            "portraitUrl": portrait_url,
        })

    discovered_ids = {player["id"] for player in discovered}
    enriched_ids = {str(player.get("id")) for player in players}
    missing_ids = sorted(discovered_ids - enriched_ids)
    if missing_ids:
        raise RuntimeError(
            f"Enrichment failed to return {len(missing_ids)} discovered player(s): "
            + ", ".join(missing_ids)
        )

    players.sort(key=lambda p: (p["marketValue"] or 0), reverse=True)
    output = {
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "source": "Transfermarkt via Apify discovery + profile actors",
        "discoveryQueries": DISCOVERY_QUERIES,
        "discoveryCount": len(discovered),
        "players": players,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(players)} complete Dembélé player records to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
