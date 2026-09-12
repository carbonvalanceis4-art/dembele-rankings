#!/usr/bin/env python3
"""Fetch Dembélé player records from an Apify Transfermarkt actor and write the site's JSON."""

import json
import os
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ACTOR_ID = "incognito_mode~transfermarkt-player-scraper"
API_URL = f"https://api.apify.com/v2/actors/{ACTOR_ID}/run-sync-get-dataset-items"
OUT = Path("data/players.json")


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
    if text.endswith("bn") or text.endswith("b"):
        multiplier = 1_000_000_000
        text = text[:-2] if text.endswith("bn") else text[:-1]
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


def main():
    token = os.environ.get("APIFY_API_TOKEN")
    if not token:
        print("APIFY_API_TOKEN is not set. Add it as a GitHub Actions secret.", file=sys.stderr)
        return 2

    # The actor uses searchQueries/maxPlayersPerQuery (not searchQuery/maxResults).
    # Ask for the largest available result set for the surname search, then apply
    # our own exact-surname filter below.
    payload = {
        "searchQueries": ["Dembele"],
        "maxPlayersPerQuery": 50,
        "includeMarketValueHistory": False,
        "includeTransferHistory": False,
        "maxItems": 50,
    }
    request = Request(
        API_URL,
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
        print(f"Apify request failed: {exc}", file=sys.stderr)
        return 1

    if not isinstance(records, list):
        print("Unexpected Apify response: expected a JSON array.", file=sys.stderr)
        return 1

    players = []
    seen = set()
    for record in records:
        if not isinstance(record, dict):
            continue
        name = first_value(record, "name", "full_name", "fullName")
        if not name or not surname_is_dembele(name):
            continue

        player_id = first_value(record, "playerId", "player_id", "id")
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

        key = str(player_id or normalize(name))
        if key in seen:
            continue
        seen.add(key)
        players.append({
            "id": player_id,
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

    players.sort(key=lambda p: (p["marketValue"] or 0), reverse=True)
    output = {
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "source": "Transfermarkt via Apify actor",
        "players": players,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(players)} Dembélé players to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
