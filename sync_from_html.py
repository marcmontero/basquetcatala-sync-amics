"""
Alternativa a sync_calendar.py per a equips on el check anti-bot de
basquetcatala.cat no es deixa passar per l'automatització (per exemple,
perquè ha escalat a un reCAPTCHA real després de massa intents).

En comptes d'obrir un Chrome i visitar la web, aquest script llegeix
fitxers HTML que TU has desat a mà (Cmd+S → "Pàgina web, completa", o
Cmd+Opció+U → copiar el codi font) després de passar la verificació com a
persona normal al teu navegador de tota la vida. La resta de la lògica
(convertir partits en events, crear/actualitzar/esborrar a Google
Calendar) és exactament la mateixa que fa servir sync_calendar.py.

L'equip corresponent a cada HTML es detecta automàticament: es busca a
teams.json quin equip té un club_name que apareix a TOTS els partits
d'aquell HTML (com a local o com a visitant), ja que la pàgina d'un equip
sempre el llista a ell mateix a cada partit.

Ús:
    python3 sync_from_html.py cultural.html natzaret.html palcam.html
"""

import sys

from scrape import parse_matches
from sync_calendar import (
    get_calendar_service,
    get_existing_synced_event_ids,
    load_teams,
    match_to_event,
    upsert_event,
)


def find_team_for_matches(matches, teams):
    if not matches:
        return None
    for team in teams:
        club_name = team["club_name"]
        if all(m.home_team == club_name or m.away_team == club_name for m in matches):
            return team
    return None


def sync_team_from_matches(service, matches, team):
    name = team["name"]
    calendar_id = team["calendar_id"]
    print(f"[{name}] {len(matches)} partits llegits de l'HTML.")

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


def main(html_paths: list[str]):
    if not html_paths:
        print("Ús: python3 sync_from_html.py fitxer1.html fitxer2.html ...")
        sys.exit(1)

    teams = load_teams()
    service = get_calendar_service()

    for path in html_paths:
        with open(path, encoding="utf-8") as f:
            html = f.read()

        try:
            matches = parse_matches(html)
        except Exception as e:
            print(f"[{path}] ERROR llegint l'HTML: {e}")
            continue

        team = find_team_for_matches(matches, teams)
        if team is None:
            print(
                f"[{path}] No he trobat cap equip a teams.json que coincideixi "
                f"amb els partits d'aquest HTML (revisa el club_name)."
            )
            continue

        sync_team_from_matches(service, matches, team)


if __name__ == "__main__":
    main(sys.argv[1:])
