"""
Sincronitza els partits d'equips de DIFERENTS clubs (definits a teams.json,
cadascun amb el seu propi club_id i team_id) amb el seu propi Google
Calendar.

Pensat per executar-se MANUALMENT: no hi ha GitHub Actions ni self-hosted
runner en aquest repo, simplement l'executes (python3 sync_calendar.py)
quan vulguis actualitzar els calendaris.

Cada partit es converteix en un event amb un ID determinista (basat en
l'ID del partit a basquetcatala.cat), així que tornar a executar aquest
script no crea duplicats: actualitza els que han canviat, crea els nous,
i esborra de Google Calendar els que ja no apareixen a la web.
"""

import json
import os
import random
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from google.oauth2 import service_account
from googleapiclient.discovery import build

from scrape import get_matches_for_team, open_browser_context

TIMEZONE = ZoneInfo("Europe/Madrid")
GAME_DURATION_MINUTES = int(os.environ.get("GAME_DURATION_MINUTES", "120"))
CREDENTIALS_PATH = os.environ.get("GOOGLE_CREDENTIALS_PATH", "credentials.json")
TEAMS_FILE = os.environ.get("TEAMS_FILE", "teams.json")

# Diferent del tag del repo del Badalonès, per si algun dia comparteixes
# un mateix calendari entre els dos scripts sense que es trepitgin.
SOURCE_TAG = "basquetcatala-sync-amics"

SCOPES = ["https://www.googleapis.com/auth/calendar"]


def load_teams() -> list[dict]:
    with open(TEAMS_FILE, encoding="utf-8") as f:
        teams = json.load(f)
    for team in teams:
        if not team.get("calendar_id") or team["calendar_id"].startswith("OMPLE_AQUI"):
            raise RuntimeError(
                f"L'equip '{team.get('name')}' no té calendar_id configurat a {TEAMS_FILE}."
            )
        if not team.get("club_id") or team["club_id"].startswith("OMPLE_AQUI"):
            raise RuntimeError(
                f"L'equip '{team.get('name')}' no té club_id configurat a {TEAMS_FILE}."
            )
        if not team.get("team_id") or team["team_id"].startswith("OMPLE_AQUI"):
            raise RuntimeError(
                f"L'equip '{team.get('name')}' no té team_id configurat a {TEAMS_FILE}."
            )
    return teams


def get_calendar_service():
    creds = service_account.Credentials.from_service_account_file(
        CREDENTIALS_PATH, scopes=SCOPES
    )
    return build("calendar", "v3", credentials=creds)


def event_id_for(match_id: str) -> str:
    # Google Calendar exigeix IDs amb només lletres a-v minúscules i dígits,
    # de com a mínim 5 caràcters.
    return f"partit{match_id}"


def match_to_event(match, team: dict) -> dict:
    start_dt = datetime.strptime(
        f"{match.date} {match.time}", "%d/%m/%Y %H:%M"
    ).replace(tzinfo=TIMEZONE)
    end_dt = start_dt + timedelta(minutes=GAME_DURATION_MINUTES)

    location = match.venue_name
    if match.venue_address:
        location = f"{match.venue_name}, {match.venue_address}"

    club_name = team["club_name"]
    short_name = team["name"]

    is_home_game = match.home_team == club_name
    is_away_game = match.away_team == club_name

    home_label = short_name if is_home_game else match.home_team
    away_label = short_name if is_away_game else match.away_team

    if is_home_game:
        prefix = "🏠 "
        color_id = "6"  # Tangerine (taronja)
    elif is_away_game:
        prefix = "🚗 "
        color_id = "9"  # Blueberry (blau)
    else:
        prefix = ""
        color_id = None

    event = {
        "id": event_id_for(match.match_id),
        "summary": f"{prefix}{home_label} - {away_label}",
        "location": location,
        "description": f"{match.category}\nhttps://www.basquetcatala.cat/partits/llistatpartits/{match.match_id}",
        "start": {"dateTime": start_dt.isoformat(), "timeZone": "Europe/Madrid"},
        "end": {"dateTime": end_dt.isoformat(), "timeZone": "Europe/Madrid"},
        "extendedProperties": {"private": {"source": SOURCE_TAG}},
    }
    if color_id:
        event["colorId"] = color_id
    return event


def get_existing_synced_event_ids(service, calendar_id: str) -> set[str]:
    ids = set()
    page_token = None
    while True:
        resp = (
            service.events()
            .list(
                calendarId=calendar_id,
                privateExtendedProperty=f"source={SOURCE_TAG}",
                pageToken=page_token,
                showDeleted=False,
                maxResults=250,
            )
            .execute()
        )
        for item in resp.get("items", []):
            ids.add(item["id"])
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return ids


def upsert_event(service, calendar_id: str, event: dict) -> str:
    try:
        service.events().update(
            calendarId=calendar_id, eventId=event["id"], body=event
        ).execute()
        return "updated"
    except Exception as e:
        if "404" in str(e) or "Not Found" in str(e):
            service.events().insert(calendarId=calendar_id, body=event).execute()
            return "created"
        raise


def sync_team(service, context, team: dict):
    name = team["name"]
    calendar_id = team["calendar_id"]

    matches = get_matches_for_team(context, team["team_id"], team["club_id"])
    print(f"[{name}] {len(matches)} partits trobats.")

    existing_ids = get_existing_synced_event_ids(service, calendar_id)
    seen_ids = set()

    created = updated = 0
    for match in matches:
        event = match_to_event(match, team)
        seen_ids.add(event["id"])
        result = upsert_event(service, calendar_id, event)
        if result == "created":
            created += 1
        else:
            updated += 1

    stale_ids = existing_ids - seen_ids
    deleted = 0
    for stale_id in stale_ids:
        service.events().delete(calendarId=calendar_id, eventId=stale_id).execute()
        deleted += 1

    print(f"[{name}] Creats: {created} | Actualitzats: {updated} | Esborrats: {deleted}")


def sync():
    teams = load_teams()
    service = get_calendar_service()

    errors = []
    with open_browser_context() as context:
        for i, team in enumerate(teams):
            if i > 0:
                # Pausa breu entre equips perquè la web no ens freni per
                # excés de peticions seguides.
                time.sleep(1.5 + random.uniform(0, 1.5))
            try:
                sync_team(service, context, team)
            except Exception as e:
                print(f"[{team.get('name')}] ERROR: {e}")
                errors.append(team.get("name"))

    if errors:
        print(f"\nEquips sense sincronitzar aquesta vegada: {', '.join(errors)}")
        print("(normalment perquè encara no tenen calendari publicat a la web)")

    if errors and len(errors) == len(teams):
        raise RuntimeError(
            "Ha fallat la sincronització de TOTS els equips, sembla un "
            "problema real (no només equips sense calendari publicat)."
        )


if __name__ == "__main__":
    sync()
