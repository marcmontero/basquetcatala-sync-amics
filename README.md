# Calendaris d'amics → Google Calendar

Repo separat del del Badalonès. Aquí cada equip de `teams.json` pot ser
d'un club **diferent** (un amic a cada club), i el sync **NO és
automàtic**: no hi ha GitHub Actions ni self-hosted runner, simplement
l'executes tu quan vulguis actualitzar els calendaris.

## Com funciona

1. `teams.json` llista els equips a sincronitzar: de quin club i quin
   equip és cadascun (a basquetcatala.cat), i a quin Google Calendar s'han
   de crear els seus partits.
2. `scrape.py` obre un Chrome real (per esquivar el check anti-bot de la
   web, igual que al repo del Badalonès) i n'extreu la taula de partits
   d'un equip concret d'un club concret.
3. `sync_calendar.py` recorre `teams.json` i, per cada equip, sincronitza
   els seus partits amb el seu calendari corresponent (crea, actualitza o
   esborra events segons calgui).

## Configuració

### 1. Troba el club_id i el team_id de cada amic

A basquetcatala.cat, busca l'equip del teu amic i mira la URL del seu
calendari, que té aquesta forma:

```
https://www.basquetcatala.cat/partits/calendari_equip_global/<CLUB_ID>/<TEAM_ID>
```

Per exemple, per al Badalonès (club_id `150`) i el seu Senior A (team_id
`88829`):
`.../calendari_equip_global/150/88829`

### 2. Crea un Google Calendar per a cada amic

Per cada equip de `teams.json`:

1. A [Google Calendar](https://calendar.google.com/), crea un calendari
   nou (per exemple amb el nom de l'amic o de l'equip).
2. Configuració del calendari → **Compartir amb persones concretes** →
   afegeix l'adreça del compte de servei de Google amb permís **Fer canvis
   als esdeveniments**.
   - Si ja tens un compte de servei del repo del Badalonès, pots
     reutilitzar el mateix (és només un compte que escriu a calendaris,
     no cal que sigui un de nou).
3. A **Integrar el calendari**, copia l'**ID del calendari**.

### 3. Omple `teams.json`

Un objecte per equip, per exemple:

```json
{
  "name": "Joan",
  "club_id": "150",
  "team_id": "88829",
  "club_name": "A.E. BADALONÈS - PINTURAS CORBACHO",
  "calendar_id": "abc123xyz@group.calendar.google.com"
}
```

`club_name` ha de ser el nom EXACTE tal com surt a la web (així el script
sap si cada partit és de local o de visitant, per posar 🏠/🚗).

### 4. Credencials de Google (compte de servei)

Si no en tens cap encara:

1. Crea un projecte a
   [Google Cloud Console](https://console.cloud.google.com/), habilita la
   **Google Calendar API**.
2. Crea un **compte de servei** i descarrega'n la clau en format JSON com
   a `credentials.json` (mai el pugis al repo, ja està al `.gitignore`).

### 5. Instal·la i executa

```bash
pip3 install -r requirements.txt
playwright install chrome  # només el primer cop, si no tens Chrome via Playwright

export GOOGLE_CREDENTIALS_PATH=ruta/al/teu/credentials.json
python3 sync_calendar.py
```

Cada vegada que ho executis, s'obrirà un Chrome (necessita finestra real,
no funciona en mode headless), sincronitzarà tots els equips de
`teams.json`, i tancarà sol en acabar.

## Configuració opcional

Variables d'entorn:

- `GAME_DURATION_MINUTES`: durada estimada de cada partit (per defecte
  120).
- `TEAMS_FILE`: ruta al fitxer de configuració d'equips (per defecte
  `teams.json`).

## Notes

- Cada event es marca amb una propietat interna
  (`source=basquetcatala-sync-amics`), diferent de la del repo del
  Badalonès, així que pots compartir calendaris o comptes de servei entre
  els dos sense que es trepitgin.
- Com que és manual, no cal Mac sempre engegat ni self-hosted runner: quan
  vulguis actualitzar, l'executes des del teu ordinador.
- Per afegir o treure amics/equips, edita `teams.json` directament.
