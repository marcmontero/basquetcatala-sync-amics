"""
Scraper del calendari de partits de basquetcatala.cat, generalitzat perquè
cada equip pugui pertànyer a un club DIFERENT (a diferència del repo del
Badalonès, on tots els equips són del mateix club i el club_id és una sola
variable global, aquí el club_id es passa per equip).

La web protegeix les pàgines amb un "check" anti-bot que detecta navegadors
automatitzats. Per esquivar-ho fem servir el Chrome real del sistema (no
el Chromium que porta Playwright), sense mode headless, amb pedaços
"stealth" que amaguen les empremtes típiques d'automatització.

Aquest repo s'executa MANUALMENT (no hi ha GitHub Actions ni self-hosted
runner): simplement l'executes des del teu Mac quan vulguis actualitzar
els calendaris dels amics.
"""

import os
import random
import re
import time
from contextlib import contextmanager
from dataclasses import dataclass

from bs4 import BeautifulSoup
from playwright.sync_api import BrowserContext, sync_playwright
from playwright_stealth import Stealth


def calendar_url_for(team_id: str, club_id: str) -> str:
    return f"https://www.basquetcatala.cat/partits/calendari_equip_global/{club_id}/{team_id}"


@dataclass
class Match:
    match_id: str
    date: str  # DD/MM/YYYY
    time: str  # HH:MM
    home_team: str
    away_team: str
    category: str
    venue_name: str
    venue_address: str


@contextmanager
def open_browser_context():
    """Obre un únic Chrome real (no headless) amb pedaços stealth, reutilitzable
    per fer-hi diverses pestanyes (una per equip)."""
    with sync_playwright() as p:
        browser = p.chromium.launch(
            channel="chrome",
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--start-minimized",
                "--window-position=2000,2000",
            ],
        )
        context = browser.new_context(
            locale="ca-ES",
            timezone_id="Europe/Madrid",
            viewport={"width": 1366, "height": 900},
        )
        # Amaga les empremtes típiques que delaten un navegador automatitzat.
        Stealth().apply_stealth_sync(context)
        try:
            yield context
        finally:
            browser.close()


def fetch_rendered_html(context: BrowserContext, url: str, debug_name: str = "failure") -> str:
    """Obre la URL en una pestanya nova del context donat, espera que la
    taula de partits carregui, i força que es mostrin TOTS els partits
    (per defecte, DataTables només en renderitza 10 a la vegada)."""
    page = context.new_page()
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=15000)

        try:
            # El check anti-bot redirigeix i torna sol; esperem que la
            # taula de partits (el contenidor) estigui present. Si l'equip
            # encara no té calendari publicat, la taula hi és però sense
            # cap fila — això no és un error, vol dir 0 partits.
            page.wait_for_selector("#tbl-clubs-list", timeout=10000)
            page.wait_for_timeout(300)

            page.evaluate(
                "() => { if (window.jQuery && jQuery.fn.dataTable.isDataTable('#tbl-clubs-list')) "
                "{ jQuery('#tbl-clubs-list').DataTable().page.len(-1).draw(); } }"
            )
            page.wait_for_timeout(300)
        except Exception:
            print(f"URL final: {page.url}")
            print(f"Títol de la pàgina: {page.title()}")
            os.makedirs("debug", exist_ok=True)
            page.screenshot(path=f"debug/{debug_name}.png", full_page=True)
            with open(f"debug/{debug_name}.html", "w", encoding="utf-8") as f:
                f.write(page.content())
            raise

        return page.content()
    finally:
        page.close()


def get_matches_for_team(
    context: BrowserContext, team_id: str, club_id: str, retries: int = 1
) -> list[Match]:
    url = calendar_url_for(team_id, club_id)
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            html = fetch_rendered_html(
                context, url, debug_name=f"failure_{club_id}_{team_id}"
            )
            return parse_matches(html)
        except Exception as e:
            last_error = e
            if attempt < retries:
                time.sleep(3 + random.uniform(0, 2))
    raise last_error


def parse_matches(html: str) -> list[Match]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", id="tbl-clubs-list")
    if table is None:
        raise RuntimeError("No s'ha trobat la taula de partits (#tbl-clubs-list)")

    matches = []
    tbody = table.find("tbody")
    if tbody is None:
        # Taula present però sense cap fila (l'equip encara no té
        # calendari publicat): 0 partits, no és un error.
        return matches

    for row in tbody.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 7:
            continue

        date_box = cells[0].find("div", class_="box")
        time_box = cells[1].find("div", class_="box")
        date = date_box.get_text(strip=True) if date_box else ""
        time = time_box.get_text(strip=True) if time_box else ""

        home_team = cells[2].get_text(strip=True)
        away_team = cells[3].get_text(strip=True)
        category = cells[4].get_text(strip=True)

        venue_cell = cells[5]
        venue_html = venue_cell.decode_contents()
        venue_parts = [
            re.sub(r"\s+", " ", part).strip()
            for part in venue_html.split("<br/>")
        ]
        venue_parts = [p for p in venue_parts if p]
        venue_name = venue_parts[0] if len(venue_parts) > 0 else ""
        venue_address = venue_parts[1] if len(venue_parts) > 1 else ""

        info_link = cells[6].find("a")
        match_id = ""
        if info_link and info_link.get("href"):
            m = re.search(r"llistatpartits/(\d+)", info_link["href"])
            if m:
                match_id = m.group(1)

        if not match_id or not date or not time:
            # Sense ID únic o sense data/hora fixada encara, no el sincronitzem.
            continue

        matches.append(
            Match(
                match_id=match_id,
                date=date,
                time=time,
                home_team=home_team,
                away_team=away_team,
                category=category,
                venue_name=venue_name,
                venue_address=venue_address,
            )
        )

    return matches


if __name__ == "__main__":
    # Prova ràpida: substitueix club_id/team_id pels que vulguis comprovar.
    with open_browser_context() as ctx:
        for m in get_matches_for_team(ctx, team_id="88829", club_id="150"):
            print(m)
