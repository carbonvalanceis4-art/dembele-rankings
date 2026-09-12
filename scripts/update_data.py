#!/usr/bin/env python3
"""Discover Dembélé players broadly, then enrich current Transfermarkt profiles."""

import csv
import gzip
import html
import io
import json
import os
import re
import sys
import unicodedata
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DISCOVERY_ACTOR_ID = "incognito_mode~transfermarkt-player-scraper"
ENRICHMENT_ACTOR_ID = "incognito_mode~transfermarkt-player-scraper"
APIFY_BASE = "https://api.apify.com/v2/actors"
OUT = Path("data/players.json")
DATASET_PLAYERS_URL = "https://pub-e682421888d945d684bcae8890b0ec20.r2.dev/data/players.csv.gz"
FBREF_INDEX_URL = "https://fbref.com/en/players/de/"
ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
BASE_SEARCH_QUERIES = (
    [f"Dembele {letter}" for letter in ALPHABET]
    + [f"Dembélé {letter}" for letter in ALPHABET]
    + ["Dembele", "Dembélé"]
)
DISCOVERY_LIMIT = 50
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
        multiplier, text = 1_000_000_000, text[:-2]
    elif text.endswith("b"):
        multiplier, text = 1_000_000_000, text[:-1]
    elif text.endswith("m") or "mio" in text:
        multiplier, text = 1_000_000, text.replace("mio", "").replace("m", "")
    elif text.endswith("k"):
        multiplier, text = 1_000, text[:-1]
    try:
        return int(float(text.strip()) * multiplier)
    except ValueError:
        digits = "".join(ch for ch in value if ch.isdigit())
        return int(digits) if digits else None


def fetch_bytes(url, timeout=300):
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; DembeleRankings/1.0)", "Accept": "*/*"})
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.read()
    except (HTTPError, URLError, TimeoutError) as exc:
        raise RuntimeError(f"Failed to fetch {url}: {exc}") from exc


class FBrefPlayerParser(HTMLParser):
    """Extract player links from FBref's surname index."""

    def __init__(self):
        super().__init__()
        self.players = {}
        self._href = None
        self._text = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        href = attrs.get("href", "")
        if tag == "a" and re.fullmatch(r"/en/players/[0-9a-f]{8}/[^/]+", href or ""):
            self._href = href
            self._text = []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            name = html.unescape("".join(self._text)).strip()
            if name and surname_is_dembele(name):
                self.players[name] = self._href
            self._href = None
            self._text = []


def discover_from_fbref():
    raw = fetch_bytes(FBREF_INDEX_URL)
    parser = FBrefPlayerParser()
    parser.feed(raw.decode("utf-8", errors="replace"))
    print(f"FBref surname index yielded {len(parser.players)} Dembélé candidates.")
    return parser.players


def discover_from_public_dataset():
    raw = fetch_bytes(DATASET_PLAYERS_URL)
    try:
        text = gzip.decompress(raw).decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise RuntimeError(f"Could not decompress/decode player discovery dataset: {exc}") from exc
    discovered = {}
    reader = csv.DictReader(io.StringIO(text))
    if not {"player_id", "name"}.issubset(set(reader.fieldnames or [])):
        raise RuntimeError("Unexpected player discovery dataset schema; expected player_id and name columns.")
    for row in reader:
        name = row.get("name") or ""
        player_id = row.get("player_id") or ""
        if player_id and surname_is_dembele(name):
            discovered[str(player_id)] = {"id": str(player_id), "name": name, "profileUrl": row.get("url") or None}
    print(f"Public Transfermarkt dataset yielded {len(discovered)} Dembélé surname matches.")
    return discovered


def apify_run(actor_id, payload, token):
    url = f"{APIFY_BASE}/{actor_id}/run-sync-get-dataset-items"
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Accept": "application/json"},
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


def discover_from_live_search(token, discovered, fbref_names):
    # Query exact/full names discovered independently. This is the critical
    # escape hatch from Transfermarkt's weak surname-search relevance ranking.
    exact_name_queries = sorted(fbref_names)
    queries = list(BASE_SEARCH_QUERIES) + exact_name_queries
    all_records = []
    for start in range(0, len(queries), 50):
        batch = queries[start:start + 50]
        payload = {
            "searchQueries": batch,
            "maxPlayersPerQuery": DISCOVERY_LIMIT,
            "includeMarketValueHistory": False,
            "includeTransferHistory": False,
            "maxItems": 5000,
            "language": "en",
        }
        records = apify_run(DISCOVERY_ACTOR_ID, payload, token)
        print(f"Live discovery batch {start + 1}-{start + len(batch)} returned {len(records)} records.")
        all_records.extend(records)

    before = len(discovered)
    for record in all_records:
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
    print(f"Live search added {len(discovered) - before} new player IDs.")
    return discovered


def enrich_players(player_ids, token):
    records = []
    for start in range(0, len(player_ids), ENRICHMENT_BATCH_SIZE):
        batch = player_ids[start:start + ENRICHMENT_BATCH_SIZE]
        payload = {"playerIds": batch, "includeMarketValueHistory": False, "includeTransferHistory": False, "maxItems": len(batch)}
        batch_records = apify_run(ENRICHMENT_ACTOR_ID, payload, token)
        print(f"Enriched batch {start + 1}-{start + len(batch)}: {len(batch_records)} profiles.")
        records.extend(batch_records)
    return records


def main():
    token = os.environ.get("APIFY_API_TOKEN")
    if not token:
        print("APIFY_API_TOKEN is not set. Add it as a GitHub Actions secret.", file=sys.stderr)
        return 2

    try:
        discovered = discover_from_public_dataset()
        fbref_names = discover_from_fbref()
        discovered = discover_from_live_search(token, discovered, fbref_names)
        print(f"Total unique Dembélé IDs to enrich: {len(discovered)}")
        records = enrich_players(list(discovered), token)
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
        nationality = first_value(record, "nationality", "citizenship")
        if isinstance(nationality, list):
            nationality = ", ".join(map(str, nationality))
        players.append({
            "id": key,
            "name": name,
            "club": first_value(record, "clubName", "currentClub", "club_name", "current_club", "current_club_name"),
            "nationality": nationality,
            "age": as_number(first_value(record, "age")),
            "position": first_value(record, "position", "positionGroup", "position_group"),
            "marketValue": as_number(first_value(record, "marketValue", "market_value", "market_value_in_eur")),
            "marketValueDate": first_value(record, "marketValueLastUpdate", "market_value_last_update"),
            "profileUrl": first_value(record, "profileUrl", "profile_url", "url"),
            "portraitUrl": first_value(record, "portraitUrl", "portrait_url", "image_url"),
        })

    missing_ids = sorted(set(discovered) - {p["id"] for p in players})
    if missing_ids:
        raise RuntimeError(f"Enrichment failed to return {len(missing_ids)} discovered player(s): " + ", ".join(missing_ids))

    players.sort(key=lambda p: (p["marketValue"] or 0), reverse=True)
    output = {
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "source": "Transfermarkt via public dataset + FBref surname index + live Apify discovery + profile enrichment",
        "discoverySources": [DATASET_PLAYERS_URL, FBREF_INDEX_URL, "Transfermarkt live search via Apify"],
        "discoveryCount": len(discovered),
        "players": players,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(players)} complete Dembélé player records to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
