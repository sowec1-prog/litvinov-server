from flask import Flask, jsonify, request
import hmac
import html
import json
import os
import re
import secrets
import threading
import time
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

app = Flask(__name__)
TFT_FIRMWARE_MANIFEST_PATH = Path(__file__).with_name("tft_firmware_manifest.json")


# Hokej.cz rozlišuje velké `L` v parametru matchList. Bez explicitní sezóny
# může vrátit archiv místo aktuálního rozpisu a nenajde se příští zápas.
HOKEJ_URL = "https://www.hokej.cz/tipsport-extraliga/zapasy?matchList-filter-season=2026&matchList-filter-competition=7562&matchList-filter-team=823"
# Oficiální tabulka klubu není z Renderu blokována jako hokej.cz a obsahuje
# stejný aktuální ligový žebříček.
STANDINGS_URL = "https://www.hcverva.cz/standings/MUZ"
# Oficiální klubový rozpis je záloha pro případ, kdy hokej.cz po zápase
# ještě nezveřejní další termín ve svém seznamu.
VERVA_MATCHES_URL = "https://www.hcverva.cz/matches/MUZ?season=2027"
# Kompletní rozpis ELH 2026/27 pro Litvínov, vyexportovaný z veřejných odkazů
# Hokej.cz. Je to záloha pro Render: pokud cloudová IP nedostane HTML rozpisu,
# známé ID stále otevře veřejný krátký JSON textového přenosu na S3.
KNOWN_TEXT_TRANSFER_IDS = {
    ("2026-09-16", "hc verva litvinov", "kometa"): "2928258",
    ("2026-09-18", "hc verva litvinov", "pardubice"): "2928263",
    ("2026-09-20", "vitkovice", "hc verva litvinov"): "2928275",
    ("2026-09-25", "hc verva litvinov", "sparta"): "2928278",
    ("2026-09-27", "motor cb", "hc verva litvinov"): "2928285",
    ("2026-09-29", "hc verva litvinov", "liberec"): "2928292",
    ("2026-10-02", "trinec", "hc verva litvinov"): "2928297",
    ("2026-10-04", "hc verva litvinov", "rytiri kladno"): "2928307",
    ("2026-10-09", "hc verva litvinov", "olomouc"): "2928314",
    ("2026-10-11", "ml.boleslav", "hc verva litvinov"): "2928319",
    ("2026-10-15", "hc verva litvinov", "mountfield hk"): "2928329",
    ("2026-10-18", "hc verva litvinov", "energie k.v."): "2928332",
    ("2026-10-23", "hc verva litvinov", "hc skoda plzen"): "2928342",
    ("2026-10-25", "hc verva litvinov", "kometa"): "2928349",
    ("2026-10-27", "pardubice", "hc verva litvinov"): "2928355",
    ("2026-10-30", "hc verva litvinov", "vitkovice"): "2928366",
    ("2026-11-01", "sparta", "hc verva litvinov"): "2928369",
    ("2026-11-13", "hc verva litvinov", "motor cb"): "2928376",
    ("2026-11-15", "liberec", "hc verva litvinov"): "2928383",
    ("2026-11-20", "hc verva litvinov", "trinec"): "2928388",
    ("2026-11-22", "kladno", "hc verva litvinov"): "2928398",
    ("2026-11-24", "olomouc", "hc verva litvinov"): "2928405",
    ("2026-11-27", "hc verva litvinov", "ml.boleslav"): "2928410",
    ("2026-11-29", "mountfield hk", "hc verva litvinov"): "2928420",
    ("2026-12-04", "energie k.v.", "hc verva litvinov"): "2928423",
    ("2026-12-06", "hc skoda plzen", "hc verva litvinov"): "2928433",
    ("2026-12-18", "kometa", "hc verva litvinov"): "2928440",
    ("2026-12-20", "hc verva litvinov", "pardubice"): "2928447",
    ("2026-12-22", "vitkovice", "hc verva litvinov"): "2928457",
    ("2026-12-26", "hc verva litvinov", "sparta"): "2928460",
    ("2026-12-28", "motor cb", "hc verva litvinov"): "2928467",
    ("2026-12-30", "hc verva litvinov", "liberec"): "2928474",
    ("2027-01-03", "trinec", "hc verva litvinov"): "2928479",
    ("2027-01-08", "hc verva litvinov", "kladno"): "2928489",
    ("2027-01-10", "hc verva litvinov", "olomouc"): "2928496",
    ("2027-01-15", "ml.boleslav", "hc verva litvinov"): "2928501",
    ("2027-01-17", "hc verva litvinov", "mountfield hk"): "2928511",
    ("2027-01-22", "energie k.v.", "hc verva litvinov"): "2928514",
    ("2027-01-24", "hc verva litvinov", "hc skoda plzen"): "2928524",
    ("2027-01-26", "kometa", "hc verva litvinov"): "2928531",
    ("2027-01-29", "pardubice", "hc verva litvinov"): "2928538",
    ("2027-01-31", "hc verva litvinov", "vitkovice"): "2928548",
    ("2027-02-02", "sparta", "hc verva litvinov"): "2928551",
    ("2027-02-05", "hc verva litvinov", "motor cb"): "2928558",
    ("2027-02-07", "liberec", "hc verva litvinov"): "2928565",
    ("2027-02-17", "hc verva litvinov", "trinec"): "2928570",
    ("2027-02-19", "kladno", "hc verva litvinov"): "2928580",
    ("2027-02-21", "olomouc", "hc verva litvinov"): "2928587",
    ("2027-02-26", "hc verva litvinov", "ml.boleslav"): "2928592",
    ("2027-02-28", "mountfield hk", "hc verva litvinov"): "2928602",
    ("2027-03-02", "hc verva litvinov", "energie k.v."): "2928605",
    ("2027-03-05", "hc skoda plzen", "hc verva litvinov"): "2928615",
}
ONLINE_URL = "https://s3-eu-west-1.amazonaws.com/hokej.cz/match/2026/short/{match_id}.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (Litvinov scoreboard; contact: github.com/sowec1-prog/litvinov-server)"}

RETRY_COUNT = 3
REQUEST_TIMEOUT = (5, 15)
# Tajný klíč je pouze v Render Environment; do GitHubu ani do OLEDu nepatří.
MANUAL_CUE_ARM_SECONDS = 65
MANUAL_CUE_TOTAL_SECONDS = 180
# Poslední ověřený stav pro krizový start Render instance. Tento soubor je
# aktualizován pouze ručně po skutečném úspěšném stažení, nikdy se nevymýšlí.
LEGACY_FALLBACK_PATH = Path(__file__).with_name("legacy_fallback.txt")


def load_legacy_fallback() -> str | None:
    try:
        payload = LEGACY_FALLBACK_PATH.read_text(encoding="utf-8").strip()
        return payload if payload.count("\n") >= 2 else None
    except OSError:
        return None


_last_good_payload = load_legacy_fallback()
_last_good_status = None
_manual_cue = None


def temporary_source_status():
    """Bezpečný OLED payload pro první výpadek zdroje po startu instance.

    Nevydává se za aktuální skóre ani termín. Stav ``scheduled`` využije už
    nasazený firmware bez nového flashování: vykreslí srozumitelnou informaci
    a při dalším běžném pollu se znovu pokusí načíst ověřená data.
    """
    now = int(datetime.now(ZoneInfo("Europe/Prague")).timestamp())
    return {
        "state": "scheduled",
        "match_id": "",
        "home": "HC VERVA Litvinov",
        "away": "Zdroj hokej.cz",
        "home_display": "HC VERVA Litvinov",
        "away_display": "ZDROJ NEDOSTUPNY",
        "home_code": "LIT",
        "away_code": "",
        "game_clock": "ZKUSIM ZNOVU",
        "match_start_epoch": 0,
        "server_epoch": now,
        "is_match_day": False,
        "score_home": 0,
        "score_away": 0,
        "last_goal_scorer": "",
        "last_goal_team": "",
        "last_goal_code": "",
        "event_id": "",
        "audio_cue": "",
        "penalty_indicator": "",
        "cached": True,
        "source_unavailable": True,
    }


def manual_cue_payload(payload):
    """Vrátí krátký dvoufázový síťový test bzučáku bez příchozího spojení do ESP.

    První fáze pouze nastaví klientům baseline eventu. Druhá změní event ID a
    firmware již zahraje svou existující znělku lit_goal. Funguje i mimo zápas.
    """
    global _manual_cue
    if _manual_cue is None:
        return payload
    now = time.time()
    if now >= _manual_cue["expires_at"]:
        _manual_cue = None
        return payload

    result = dict(payload)
    result["state"] = "live"  # Stávající OLED zpracovává audio cue jen v live větvi.
    result["game_clock"] = "TEST ZVUKU"
    result["intermission"] = False
    result["penalty_indicator"] = ""
    result["last_goal_scorer"] = "TEST"
    result["last_goal_code"] = "LIT"
    if now < _manual_cue["cue_at"]:
        result["event_id"] = f"manual-arm-{_manual_cue['id']}"
        result["audio_cue"] = ""
    else:
        result["event_id"] = f"manual-gol-{_manual_cue['id']}"
        result["audio_cue"] = "lit_goal"
    return result


def odstran_diakritiku(text):
    """Převede jméno na ASCII pro font OLEDu (KÄMPF → KAMPF)."""
    text = str(text).replace("ß", "ss").replace("ẞ", "SS")
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


def request_text(url):
    last_error = None
    for attempt in range(RETRY_COUNT):
        response = None
        try:
            response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            return response.text
        except requests.RequestException as error:
            last_error = error
            if attempt < RETRY_COUNT - 1:
                time.sleep(attempt + 1)
        finally:
            if response is not None:
                response.close()
    raise last_error


def get_litvinov_table_position(html_text):
    """Vrátí pořadí HC VERVA Litvínov z aktuální extraligové tabulky."""
    soup = BeautifulSoup(html_text, "html.parser")
    for row in soup.find_all("tr"):
        cells = row.find_all("td", recursive=False)
        if len(cells) < 2:
            continue
        club = odstran_diakritiku(cells[1].get_text(" ", strip=True)).lower()
        if "litvinov" not in club and "verva" not in club:
            continue
        found = re.search(r"(\d+)", cells[0].get_text(" ", strip=True))
        if found:
            return int(found.group(1))
    raise ValueError("Pozice HC VERVA Litvínov v extraligové tabulce nebyla nalezena")


def add_table_position(payload):
    """Doplní samostatné malé pole pro horní lištu; výpadek tabulky neshodí skóre."""
    try:
        payload["table_position"] = get_litvinov_table_position(request_text(STANDINGS_URL))
    except (requests.RequestException, ValueError) as error:
        app.logger.warning("standings request failed: %s", error)
        payload["table_position"] = None
    return payload


def parse_match_row(html_text):
    """Vrátí nejnovější rozehraný/odehraný zápas Litvínova se skóre z rozpisu.

    Tabulka je řazená chronologicky. První řádek se skóre proto může být včerejší
    zápas; pro live stav musí přednost dostat poslední řádek se skóre.
    """
    soup = BeautifulSoup(html_text, "html.parser")
    matches = []
    for row in soup.find_all("tr"):
        text = row.get_text(" ", strip=True)
        plain = odstran_diakritiku(text).lower()
        if "litvinov" not in plain and "verva" not in plain:
            continue
        scores = row.select("td.preview__score")
        if len(scores) < 2:
            continue
        left, right = (cell.get_text(strip=True) for cell in scores[:2])
        if not (left.isdigit() and right.isdigit()):
            continue
        href = row.get("data-href", "")
        match = re.search(r"/zapas/(\d+)", href)
        raw_names = [n.get_text(" ", strip=True) for n in row.select("td.preview__name")]
        names = [normalize_team_name(name) for name in raw_names]
        home, away = (names + ["HC Verva", "Soupeř"])[:2]
        matches.append({
            "match_id": match.group(1) if match else "",
            "home": home,
            "away": away,
            "score_home": int(left),
            "score_away": int(right),
        })
    if matches:
        return matches[-1]
    raise ValueError("Aktuální zápas Litvínova se skóre nebyl v seznamu nalezen")


def parse_scheduled_epoch(game_clock):
    """Převede text programu „PÁ 18. 09. 17:30“ na epochu v Praze."""
    # Hokejový rozpis je v českém čase; nepřebírat časové pásmo Linux/Render kontejneru.
    now = datetime.now(ZoneInfo("Europe/Prague"))
    found = re.search(r"(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{1,2}):(\d{2})", game_clock)
    if not found:
        return 0, int(now.timestamp()), False
    day, month, hour, minute = map(int, found.groups())
    try:
        start = datetime(now.year, month, day, hour, minute, tzinfo=now.tzinfo)
        # Při prosincovém seznamu může nejbližší utkání patřit do dalšího roku.
        if start.date() < now.date():
            start = start.replace(year=now.year + 1)
    except ValueError:
        return 0, int(now.timestamp()), False
    return int(start.timestamp()), int(now.timestamp()), start.date() == now.date()


TEAM_NAME_ALIASES = {
    "Litvínov": "HC VERVA Litvínov",
    "Banes Motor Č. Budějovice": "Motor Č. Budějovice",
    "BYD Energie Karlovy Vary": "Energie K.V.",
    "BYD Energie KV": "Energie K.V.",
    "Mountfield HK Hradec Králové": "Mountfield HK",
    "Mountfield HK Hr. Králové": "Mountfield HK",
    "Mountfield HK Hr. Kralove": "Mountfield HK",
    "Plzeň": "HC ŠKODA Plzeň",
    "HC Škoda Plzeň": "HC ŠKODA Plzeň",
    "HC ŠKODA Plzeň": "HC ŠKODA Plzeň",
}


def normalize_team_name(name):
    """Vrátí jedno stabilní klubové jméno pro API i všechny klienty."""
    result = re.sub(r"\s+", " ", name).strip()
    # Hokej.cz do buňky přidává třípísmenný kód a někdy i další obsah za ním.
    result = re.sub(r"\s+\b[A-Z]{3}\b(?:\s+.*)?$", "", result)
    words = result.split()
    compact = []
    for word in words:
        if not compact or compact[-1].casefold() != word.casefold():
            compact.append(word)
    # Hokej.cz u některých týmů opakuje město na konci, např.
    # "Banes Motor Č. Budějovice Č. Budějovice".
    while len(compact) > 1 and compact[-1].casefold() in {word.casefold() for word in compact[:-1]}:
        compact.pop()
    return TEAM_NAME_ALIASES.get(" ".join(compact), " ".join(compact))


def display_team_name(name, code):
    """Zkrátí normalizovaný název pro OLED bez UTF-8 diakritiky."""
    return odstran_diakritiku(normalize_team_name(name))



def team_code(name):
    """Stabilní kód týmu i když ho živý řádek Hokej.cz neobsahuje."""
    plain = odstran_diakritiku(normalize_team_name(name)).lower()
    if "litvinov" in plain or "verva" in plain:
        return "LIT"
    if "motor" in plain or "budejovic" in plain:
        return "MOT"
    known = club_team_code(name)
    if known:
        return known
    codes = re.findall(r"[A-Z]{3}", name)
    return codes[-1] if codes else ""


def team_source_codes(name):
    """Codes used by hokej.cz details for a named club."""
    plain = odstran_diakritiku(normalize_team_name(name)).lower()
    if "motor" in plain or "budejovic" in plain:
        return {"MOT", "CEB"}
    code = team_code(name)
    return {code} if code else set()

def parse_next_match(html_text):
    """Vrátí nejbližší nenahraný zápas Litvínova ze seznamu soutěže."""
    soup = BeautifulSoup(html_text, "html.parser")
    for row in soup.select("tr.js-preview__link[data-href]"):
        text = row.get_text(" ", strip=True)
        plain = odstran_diakritiku(text).lower()
        if "litvinov" not in plain and "verva" not in plain:
            continue
        if row.select("td.preview__score"):
            continue
        name_cells = row.select("td.preview__name")
        raw_names = [cell.select_one("a").get_text(" ", strip=True)
                     for cell in name_cells if cell.select_one("a")]
        names = [normalize_team_name(name) for name in raw_names]
        codes = []
        for cell in name_cells:
            found = re.findall(r"\b[A-Z]{3}\b", cell.get_text(" ", strip=True))
            codes.append(found[-1] if found else "")
        if len(names) != 2:
            continue
        time_cell = row.select_one("td.preview__desktop, td.preview__mobile")
        game_clock = time_cell.get_text(" ", strip=True) if time_cell else "Termín se upřesňuje"
        start_epoch, server_epoch, is_match_day = parse_scheduled_epoch(game_clock)
        match = re.search(r"/zapas/(\d+)", row.get("data-href", ""))
        return {
            "state": "scheduled",
            "match_id": match.group(1) if match else "",
            "home": names[0],
            "away": names[1],
            "home_display": display_team_name(names[0], codes[0] if len(codes) > 0 else ""),
            "away_display": display_team_name(names[1], codes[1] if len(codes) > 1 else ""),
            "home_code": codes[0] if len(codes) > 0 else "",
            "away_code": codes[1] if len(codes) > 1 else "",
            "game_clock": game_clock,
            "match_start_epoch": start_epoch,
            "server_epoch": server_epoch,
            "is_match_day": is_match_day,
            "score_home": 0,
            "score_away": 0,
            "last_goal_scorer": "DALŠÍ ZÁPAS",
            "last_goal_team": "",
            "last_goal_code": "",
            "event_id": "",
            "power_play": "Zápas ještě nezačal",
            "penalties": [],
            "penalty_indicator": "",
            "source": "hokej.cz program",
        }
    raise ValueError("Další zápas Litvínova nebyl v programu nalezen")


TEAM_CODES = {
    "litvinov": "LIT", "vitkovice": "VIT", "sparta": "SPA", "kometa": "KOM",
    "pardubice": "PCE", "motor cb": "CEB", "liberec": "LIB", "trinec": "TRI",
    "plzen": "PLZ", "kladno": "KLA", "olomouc": "OLO", "mlada boleslav": "MBL",
    "karlovy vary": "KVA", "energie kv": "KVA", "energie k.v.": "KVA", "mountfield": "MHK",
}


def club_team_code(name):
    plain = odstran_diakritiku(name).lower()
    return next((code for needle, code in TEAM_CODES.items() if needle in plain), "")


def known_text_transfer_id(match):
    """Vrátí ověřené ID textového přenosu pro klubový fallback, je-li známé."""
    start_epoch = int(match.get("match_start_epoch") or 0)
    if start_epoch <= 0:
        return ""
    start_date = datetime.fromtimestamp(start_epoch, ZoneInfo("Europe/Prague")).date().isoformat()
    home = odstran_diakritiku(match.get("home", "")).casefold()
    away = odstran_diakritiku(match.get("away", "")).casefold()
    direct = KNOWN_TEXT_TRANSFER_IDS.get((start_date, home, away), "")
    if direct:
        return direct

    # Klubový rozpis zkracuje názvy (např. „Litvínov“ místo „HC VERVA
    # Litvínov“). Pro záložní cestu proto porovnáme i stabilní třípísmenné
    # klubové kódy, ne pouze přesné názvy v textu.
    home_code, away_code = club_team_code(match.get("home", "")), club_team_code(match.get("away", ""))
    if not home_code or not away_code:
        return ""
    for (known_date, known_home, known_away), transfer_id in KNOWN_TEXT_TRANSFER_IDS.items():
        if known_date == start_date and home_code == club_team_code(known_home) and away_code == club_team_code(known_away):
            return transfer_id
    return ""


def parse_verva_next_match(html_text):
    """Vrátí budoucí zápas z oficiálního rozpisu HC VERVA Litvínov."""
    soup = BeautifulSoup(html_text, "html.parser")
    now = datetime.now(ZoneInfo("Europe/Prague"))
    for row in soup.select("tr.u-clickable"):
        cells = [cell.get_text(" ", strip=True) for cell in row.find_all("td", recursive=False)]
        if len(cells) < 6:
            continue
        date_text, home, away, time_text = cells[1], normalize_team_name(cells[3]), normalize_team_name(cells[4]), cells[5]
        found = re.search(r"(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})", date_text)
        clock = re.fullmatch(r"(\d{1,2}):(\d{2})", time_text)
        if not found or not clock:
            continue  # Odehrané utkání má ve sloupci výsledek, ne čas.
        day, month, year = map(int, found.groups())
        hour, minute = map(int, clock.groups())
        try:
            start = datetime(year, month, day, hour, minute, tzinfo=now.tzinfo)
        except ValueError:
            continue
        # V den zápasu ponecháme i už rozehrané utkání: jeho ověřené ID může
        # dál otevřít textový přenos. Extraligový tým nemá dva zápasy v jeden den.
        if start <= now and start.date() != now.date():
            continue
        home_code, away_code = club_team_code(home), club_team_code(away)
        return {
            "state": "scheduled",
            "match_id": f"verva-{start:%Y%m%d}-{odstran_diakritiku(home)}-{odstran_diakritiku(away)}",
            "home": home,
            "away": away,
            "home_display": display_team_name(home, home_code),
            "away_display": display_team_name(away, away_code),
            "home_code": home_code,
            "away_code": away_code,
            "game_clock": f"{start:%d. %m. %H:%M}",
            "match_start_epoch": int(start.timestamp()),
            "server_epoch": int(now.timestamp()),
            "is_match_day": start.date() == now.date(),
            "score_home": 0,
            "score_away": 0,
            "last_goal_scorer": "DALSI ZAPAS",
            "last_goal_team": "",
            "last_goal_code": "",
            "event_id": "",
            "power_play": "Zapas jeste nezacal",
            "penalties": [],
            "penalty_indicator": "",
            "source": "oficialni program hcverva.cz",
        }
    raise ValueError("Další zápas Litvínova nebyl nalezen ani v oficiálním programu")


def live_comments(online_json):
    """Normalizuje komentáře Hokej.cz a zahodí neudálostní textové položky.

    Zdroj občas vloží do seznamu ``comments.comment`` obyčejný řetězec. Ten
    není sportovní událost a nesmí shodit celý live payload při volání ``.get``.
    """
    comments = online_json.get("comments", {}).get("comment", [])
    if not isinstance(comments, list):
        comments = [comments]
    return [item for item in comments if isinstance(item, dict)]


def text_transfer_started(online_json):
    """Text přenos je živý až po explicitním hlášení úvodního buly.

    Hokej.cz publikuje před utkáním články a statistiky v tomtéž JSONu. Jejich
    zmínky o prodloužení, gólech nebo trestech nejsou živý stav tohoto zápasu.
    """
    comments = live_comments(online_json)
    if any(
        "utkani prave zacalo" in odstran_diakritiku(message_text(item)).lower()
        for item in comments
    ):
        return True
    # Hokej.cz drží jen omezené okno posledních komentářů. Po několika minutách
    # startovní věta zmizí, ale reálný čas MM:SS je stále jednoznačný live signál.
    return any(game_seconds(item.get("time")) > 0 for item in comments)


def match_finished(online_json):
    """Vrací True jen po závěrečném hvizdu, ne po konci 1. nebo 2. třetiny."""
    comments = live_comments(online_json)
    final_messages = ("konec zapasu", "utkani skoncilo", "zapas skoncil")
    for item in comments[:12]:
        normalized = odstran_diakritiku(message_text(item)).lower()
        if any(phrase in normalized for phrase in final_messages):
            return True
    return False


def game_seconds(value):
    found = re.match(r"^(\d+):(\d{2})$", str(value or ""))
    return int(found.group(1)) * 60 + int(found.group(2)) if found else 0


def message_text(comment):
    return html.unescape(re.sub(r"<[^>]*>", " ", comment.get("message", "")).replace("\n", " ")).strip()


def display_period_clock(value):
    """Převede kumulativní čas Hokej.cz na čas právě hrané třetiny."""
    seconds = game_seconds(value)
    if seconds >= 60 * 60:
        seconds -= 60 * 60
    elif seconds >= 40 * 60:
        seconds -= 40 * 60
    elif seconds >= 20 * 60:
        seconds -= 20 * 60
    return f"{seconds // 60:02d}:{seconds % 60:02d}" if seconds or str(value) == "00:00" else str(value)


def comment_team(comment, home_name):
    """Resolve the event team from hokej.cz detail code, not commentary prose."""
    details = comment.get("details", {})
    detail = details.get("detail", {}) if isinstance(details, dict) else {}
    if isinstance(detail, list):
        detail = next((entry for entry in detail if isinstance(entry, dict)), {})
    opponent = detail.get("opponent", {}).get("@attributes", {}) if isinstance(detail, dict) else {}
    source_code = opponent.get("code", "")
    if source_code:
        return "home" if source_code in team_source_codes(home_name) else "away"
    text = odstran_diakritiku(message_text(comment)).lower()
    if "litvinov" in text or "verva" in text:
        return "home" if "litv" in odstran_diakritiku(home_name).lower() or "verva" in odstran_diakritiku(home_name).lower() else "away"
    return "away"

def empty_net_status(comments, home_name, away_name):
    """Return the current pulled-goalie status from recent Hokej.cz commentary.

    The source uses prose rather than a structured goalie flag.  Comments arrive
    newest-first, so a newer return-to-goal message cancels an older pull.  Team
    resolution uses the generic home/away wording first and falls back to a team
    name token; it is deliberately not tied to Litvínov or Karlovy Vary.
    """
    clear_markers = ("vraci se do branky", "se vraci do branky", "vratil se do branky", "brankar je zpet", "zpet v brance")
    pull_markers = ("branka hostu je prazdna", "branka domacich je prazdna", "prazdna branka", "bez brankare", "sesti bruslari", "odvolal brankare")
    ignored_tokens = {"hc", "hokejovy", "klub", "verva"}

    def mentioned_side(normalized):
        if "host" in normalized:
            return "away"
        if "domac" in normalized:
            return "home"
        for side, name in (("home", home_name), ("away", away_name)):
            tokens = [token for token in re.findall(r"[a-z0-9]+", odstran_diakritiku(name).lower()) if len(token) >= 4 and token not in ignored_tokens]
            if any(token in normalized for token in tokens):
                return side
        return ""

    for item in comments:
        normalized = odstran_diakritiku(message_text(item)).lower()
        if any(marker in normalized for marker in clear_markers):
            return ""
        if any(marker in normalized for marker in pull_markers):
            side = mentioned_side(normalized)
            if side:
                code = team_code(home_name if side == "home" else away_name)
                return f"{code} PRAZDNA BRANA" if code else "PRAZDNA BRANA"
    return ""


def final_whistle_epoch(online_json):
    """Cas zaverecne pistalky v Praze; 0 kdyz zdroj cas neposkytne."""
    comments = live_comments(online_json)
    final_messages = ("konec zapasu", "utkani skoncilo", "zapas skoncil")
    for item in comments:
        normalized = odstran_diakritiku(message_text(item)).lower()
        if not any(phrase in normalized for phrase in final_messages):
            continue
        written = item.get("@attributes", {}).get("written", "")
        try:
            return int(datetime.strptime(written, "%Y-%m-%d %H:%M:%S").replace(tzinfo=ZoneInfo("Europe/Prague")).timestamp())
        except ValueError:
            return 0
    return 0


# Po závěrečné siréně držíme výsledek 10 minut; potom OLED střídá další termín a logo.
FINISHED_DISPLAY_SECONDS = 600
COMMERCIAL_BREAK_SECONDS = 30
OPPONENT_GOAL_DISPLAY_SECONDS = 15


def finished_payload(match, online_json, finished_at):
    """Konec zápasu zůstane na OLED 10 minut; finální skóre bere z live přenosu."""
    home_code = team_code(match["home"]) or "LIT"
    away_code = team_code(match["away"]) or "?"
    score_home, score_away = match.get("score_home", 0), match.get("score_away", 0)
    comments = live_comments(online_json)
    for item in comments:  # Nejnovější (včetně Konec zápasu) je první.
        attrs = item.get("@attributes", {})
        if str(attrs.get("score1", "")).isdigit() and str(attrs.get("score2", "")).isdigit():
            score_home, score_away = int(attrs["score1"]), int(attrs["score2"])
            break
    return {
        **match,
        "state": "finished",
        "home_code": home_code,
        "away_code": away_code,
        "home_display": display_team_name(match["home"], home_code),
        "away_display": display_team_name(match["away"], away_code),
        "score_home": score_home,
        "score_away": score_away,
        "game_clock": "KONEC ZAPASU",
        "penalty_indicator": "",
        "penalties": [],
        "finished_until_epoch": finished_at + FINISHED_DISPLAY_SECONDS,
    }


def comment_written_epoch(comment):
    written = comment.get("@attributes", {}).get("written", "")
    try:
        return int(datetime.strptime(written, "%Y-%m-%d %H:%M:%S").replace(tzinfo=ZoneInfo("Europe/Prague")).timestamp())
    except ValueError:
        return 0


def show_opponent_goal_temporarily(last_goal, lit_side, now_epoch):
    """Soupeřův střelec je na OLEDu jen krátce, pak se vrátí poslední LIT gól."""
    return (
        bool(last_goal["event_id"])
        and last_goal["team"] != lit_side
        and now_epoch < last_goal.get("written_epoch", 0) + OPPONENT_GOAL_DISPLAY_SECONDS
    )


def parse_last_goal(match_html, home_name):
    """Poslední střelec domácího Litvínova z detailu zápasu.

    Krátký live JSON po čase nemusí držet starší gólové události; detail zápasu
    zachová střelce, který se má po krátkém zobrazení soupeřova gólu vrátit.
    """
    home_code = team_code(home_name) or "LIT"
    goals = []
    soup = BeautifulSoup(match_html, "html.parser")
    for row in soup.select("tr"):
        cells = row.find_all("td", recursive=False)
        if len(cells) < 3:
            continue
        timestamp = cells[0].get_text(" ", strip=True)
        row_code = cells[1].get_text(" ", strip=True).upper()
        player_link = cells[2].select_one('a[href*="/hrac/"]')
        if not re.match(r"^\d{1,2}:\d{2}$", timestamp) or row_code != home_code or player_link is None:
            continue
        name = re.sub(r"\s*\(\d+\)\s*$", "", player_link.get_text(" ", strip=True)).title()
        goals.append((game_seconds(timestamp), name))
    if not goals:
        return {"scorer": "", "team": "", "event_id": "", "written_epoch": 0}
    _, scorer = max(goals, key=lambda goal: goal[0])
    return {"scorer": scorer, "team": "home", "event_id": f"last-lit-goal-{scorer}", "written_epoch": 0}


def commercial_break_until_epoch(comments, now_epoch=None):
    """Pevný 30s interval od poslední zprávy „komerční přestávka“.

    Textový přenos nemá samostatnou událost konce pauzy. Čas se proto kotví do
    timestampu Hokej.cz, aby se při každém pollu neprodloužil znovu o 30 sekund.
    """
    if now_epoch is None:
        now_epoch = int(datetime.now(ZoneInfo("Europe/Prague")).timestamp())
    for item in comments:  # Nejnovější zpráva je první.
        if "komercni prestavka" not in odstran_diakritiku(message_text(item)).lower():
            continue
        written = item.get("@attributes", {}).get("written", "")
        try:
            started = datetime.strptime(written, "%Y-%m-%d %H:%M:%S").replace(tzinfo=ZoneInfo("Europe/Prague"))
        except ValueError:
            return 0
        until = int((started + timedelta(seconds=COMMERCIAL_BREAK_SECONDS)).timestamp())
        return until if now_epoch < until else 0
    return 0


def overtime_active(comments):
    """Rozpozná vyhlášené nebo rozehrané prodloužení z veřejného přenosu."""
    for item in comments[:12]:
        text = odstran_diakritiku(message_text(item)).lower()
        if "ceka nas prodlouzeni" in text or "prodlouzeni" in text:
            return True
        if game_seconds(item.get("time")) >= 60 * 60:
            return True
    return False


def intermission_still_active(until_epoch, now_epoch):
    """Přestávka končí přesně v oznámený čas, ne až dalším komentářem."""
    return bool(until_epoch) and now_epoch < until_epoch


def parse_intermission(text):
    """Vrátí (je_přestávka, epoch_začátku_další_třetiny, stručný text pro OLED)."""
    found = re.search(r"Dalsi tretina zacne priblizne v\s*(\d{1,2}):(\d{2})", odstran_diakritiku(text), re.IGNORECASE)
    if not found:
        return False, 0, ""
    now = datetime.now(ZoneInfo("Europe/Prague"))
    hour, minute = map(int, found.groups())
    start = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    # Po plánovaném začátku o pár sekund nesmí OLED dostat zítřejší datum.
    # Přes půlnoc se na další den překlápí pouze při skutečně velkém rozdílu.
    if (now - start).total_seconds() > 12 * 60 * 60:
        start += timedelta(days=1)
    return True, int(start.timestamp()), f"PRESTAVKA DO {hour:02d}:{minute:02d}"


def extract_live_state(online_json, match, match_html=None):
    comments = live_comments(online_json)
    chronological = list(reversed(comments))
    newest = comments[0] if comments else {"@attributes": {}}
    # O přestávce může nejnovější zpráva nést místo času objekt {period: "1INT"}.
    # Skóre a poslední platný herní čas vezmeme z nejnovějšího řádku MM:SS.
    current = next((item for item in comments if game_seconds(item.get('time')) or str(item.get('time')) == '00:00'), newest)
    attrs = current.get("@attributes", {})
    now = game_seconds(current.get("time"))
    newest_time = newest.get("time", "")
    if isinstance(newest_time, dict) and str(newest_time.get("@attributes", {}).get("period", "")).endswith("INT"):
        display_clock = "PRESTAVKA"
    else:
        display_clock = display_period_clock(current.get("time", ""))
    # Hokej.cz po oznámení času další třetiny přidává ještě shrnutí periody.
    # Dokud nejnovější položka nese 1INT/2INT, hledáme oznámení v tomtéž bloku.
    intermission, intermission_until_epoch, intermission_note = False, 0, ""
    if isinstance(newest_time, dict) and str(newest_time.get("@attributes", {}).get("period", "")).endswith("INT"):
        for item in comments:
            intermission, intermission_until_epoch, intermission_note = parse_intermission(message_text(item))
            if intermission:
                break
    now_epoch = int(datetime.now(ZoneInfo("Europe/Prague")).timestamp())
    if intermission and not intermission_still_active(intermission_until_epoch, now_epoch):
        # Čas další třetiny je ověřený přímo z konce periody. Po jeho uplynutí
        # OLED nesmí zůstat na přestávce jen proto, že Hokej.cz komentář zpozdil.
        intermission, intermission_until_epoch, intermission_note = False, 0, ""
        if display_clock == "PRESTAVKA":
            display_clock = "CEKAM NA TEXT"
    overtime = overtime_active(comments)
    commercial_break_until = commercial_break_until_epoch(comments)
    commercial_break = commercial_break_until > 0
    if commercial_break:
        intermission, intermission_until_epoch, intermission_note = True, commercial_break_until, "$ KOMERCNI PRESTAVKA"
    home_code = team_code(match["home"])
    away_code = team_code(match["away"])
    home_source_codes = team_source_codes(match["home"])
    away_source_codes = team_source_codes(match["away"])
    active = []
    lit_side = "home" if "litv" in odstran_diakritiku(match["home"]).lower() or "verva" in odstran_diakritiku(match["home"]).lower() else "away"
    last_goal = {"scorer": "", "team": "", "event_id": "", "written_epoch": 0}
    last_lit_goal = {"scorer": "", "team": "", "event_id": "", "written_epoch": 0}

    for item in chronological:
        item_attrs = item.get("@attributes", {})
        label = item_attrs.get("label", "")
        text = message_text(item)
        normalized = odstran_diakritiku(text).lower()
        team = comment_team(item, match["home"])
        if label == "penalty":
            details = item.get("details", {}).get("detail", {})
            detail_entries = details if isinstance(details, list) else [details]
            for detail in detail_entries:
                if not isinstance(detail, dict):
                    continue
                penalty_code = detail.get("opponent", {}).get("@attributes", {}).get("code", "")
                penalty_team = "home" if penalty_code in home_source_codes else "away" if penalty_code in away_source_codes else team
                player = detail.get("player1", {}).get("@attributes", {}).get("name", "hráč")
                penalty = detail.get("player1", {}).get("penalties", {}).get("penalty", {})
                if isinstance(penalty, list):
                    penalty = penalty[0]
                minutes = int(penalty.get("@attributes", {}).get("length", "2") or 2)
                active.append({"team": penalty_team, "player": player, "until": game_seconds(item.get("time")) + minutes * 60, "length": minutes})
        elif " v plnem poctu" in normalized:
            # „Pardubice jsou v plném počtu“ / „Litvínov je v plném počtu“
            # je explicitní konec oslabení: pro OLED zrušíme indikátor trestu daného týmu.
            active = [penalty for penalty in active if penalty["team"] != team]
        if label == "goal":
            details_block = item.get("details", {})
            detail = details_block.get("detail", {}) if isinstance(details_block, dict) else {}
            if isinstance(detail, list):
                detail = next((entry for entry in detail if isinstance(entry, dict)), {})
            if not isinstance(detail, dict):
                detail = {}
            scorer = detail.get("player1", {}).get("@attributes", {}).get("name", "")
            if scorer:
                # Pravidlo 16.2: jen tým ve skutečném početním oslabení po inkasovaném
                # gólu ztratí menší trest, a to ten s nejkratším zbývajícím časem.
                home_minors = [p for p in active if p["team"] == "home" and p["length"] in (2, 4)]
                away_minors = [p for p in active if p["team"] == "away" and p["length"] in (2, 4)]
                penalized_team = "home" if len(home_minors) > len(away_minors) and team == "away" else "away" if len(away_minors) > len(home_minors) and team == "home" else ""
                if penalized_team:
                    candidate = min(home_minors if penalized_team == "home" else away_minors, key=lambda penalty: penalty["until"])
                    if candidate["length"] == 2:
                        active.remove(candidate)
                    else:  # dvojitý menší: zruší se první dvouminutová část, druhá zůstává.
                        candidate["length"] = 2
                        candidate["until"] -= 120
                goal = {"scorer": scorer, "team": team, "event_id": item_attrs.get("id", ""), "written_epoch": comment_written_epoch(item)}
                last_goal = goal
                if team == lit_side:
                    last_lit_goal = goal

    active = [p for p in active if p["until"] > now]
    if not last_lit_goal["event_id"] and match_html:
        last_lit_goal = parse_last_goal(match_html, match["home"])
    # A goal event must come only from the semantic label=goal in live JSON.
    home_penalties = sum(p["team"] == "home" for p in active)
    away_penalties = sum(p["team"] == "away" for p in active)
    lit_side = "home" if "litv" in odstran_diakritiku(match["home"]).lower() or "verva" in odstran_diakritiku(match["home"]).lower() else "away"
    lit_penalties = home_penalties if lit_side == "home" else away_penalties
    opponent_penalties = away_penalties if lit_side == "home" else home_penalties
    if lit_penalties > opponent_penalties:
        power_play = f"LIT osl. {max(3, 5-lit_penalties)}:5"
    elif opponent_penalties > lit_penalties:
        power_play = f"LIT pres. 5:{max(3, 5-opponent_penalties)}"
    elif lit_penalties:
        players = max(3, 5-lit_penalties)
        power_play = f"{players} na {players}"
    else:
        power_play = "Plný počet 5:5"

    home_code = team_code(match["home"])
    away_code = team_code(match["away"])

    active_codes = []
    for penalty in active:
        code = home_code if penalty["team"] == "home" else away_code
        if code and code not in active_codes:
            active_codes.append(code)
    penalty_indicator = "TREST-" + "/".join(active_codes) if active_codes else ""
    empty_net = empty_net_status(comments, match["home"], match["away"])

    audio_cue = ""
    if last_goal["event_id"]:
        audio_cue = "lit_goal" if last_goal["team"] == lit_side else "conceded_goal"
    display_goal = last_goal if last_goal["team"] == lit_side or show_opponent_goal_temporarily(last_goal, lit_side, now_epoch) else last_lit_goal

    return {
        **match,
        "state": "live",
        "home_code": home_code,
        "away_code": away_code,
        "home_display": display_team_name(match["home"], home_code),
        "away_display": display_team_name(match["away"], away_code),
        "audio_cue": audio_cue,
        "game_clock": display_clock,
        "intermission": intermission,
        "commercial_break": commercial_break,
        "overtime": overtime,
        "intermission_until_epoch": intermission_until_epoch,
        "server_epoch": int(datetime.now(ZoneInfo("Europe/Prague")).timestamp()),
        "intermission_note": intermission_note,
        "score_home": int(attrs.get("score1", match["score_home"])),
        "score_away": int(attrs.get("score2", match["score_away"])),
        # OLED firmware displays last_goal_* on its live information row. During
        # an active power play that row must show the current advantage, not a
        # stale scorer from an earlier goal. Audio still uses event_id/audio_cue.
        # Empty net gets precedence so it is visible even if the opponent has an
        # active penalty; a numeric 6:5 is intentionally not guessed from prose.
        "last_goal_scorer": empty_net or power_play if active else empty_net or "PRODLOUZENI" if overtime else odstran_diakritiku(display_goal["scorer"]),
        "last_goal_team": "" if (empty_net or overtime) else display_goal["team"],
        "last_goal_code": "" if (empty_net or active or overtime) else home_code if display_goal["team"] == "home" else away_code if display_goal["team"] == "away" else "",
        "event_id": last_goal["event_id"] or attrs.get("id", ""),
        "power_play": power_play,
        "penalties": [{"team": p["team"], "player": p["player"]} for p in active],
        "penalty_indicator": penalty_indicator,
        "source": "hokej.cz textový přenos",
    }


def zpracuj_html(html_text):
    match = parse_match_row(html_text)
    home = "HC Verva" if "litv" in odstran_diakritiku(match["home"]).lower() or "verva" in odstran_diakritiku(match["home"]).lower() else match["home"]
    away = re.sub(r"^HC\s+", "", match["away"], flags=re.IGNORECASE)
    return f"{home}\n{match['score_home']}:{match['score_away']}\n{away}"


def stahni_a_zpracuj():
    return zpracuj_html(request_text(HOKEJ_URL))


def fallback_from_club_schedule():
    """Klubový rozpis + ověřený textový přenos, když Render nedostane Hokej.cz program."""
    fallback = parse_verva_next_match(request_text(VERVA_MATCHES_URL))
    fallback["source"] = "oficialni program hcverva.cz (hokej.cz program docasne nedostupny)"
    transfer_id = known_text_transfer_id(fallback)
    if not transfer_id:
        return fallback

    fallback["match_id"] = transfer_id
    # Před úvodním buly je JSON textového přenosu prázdný; zůstane korektní
    # naplánovaný stav. Od začátku zápasu jde o stejný veřejný datový zdroj,
    # který načítá stránka /on-line.
    if int(time.time()) < fallback["match_start_epoch"]:
        return fallback
    online = json.loads(request_text(ONLINE_URL.format(match_id=transfer_id)))
    # Před úvodním buly obsahuje tentýž JSON pouze preview text; OLED musí
    # zůstat u ověřeného naplánovaného stavu až do hlášky „Utkání právě začalo.“
    if not text_transfer_started(online):
        return fallback
    if match_finished(online):
        return finished_payload(fallback, online, final_whistle_epoch(online) or int(time.time()))
    return extract_live_state(online, fallback)


def stahni_live_stav():
    # Hokej.cz blokuje některé cloudové IP adresy (403), zatímco oficiální
    # rozpis klubu je dostupný. Mimo právě rozehraný zápas proto zachováme
    # užitečný a ověřený termín místo prázdného retry stavu.
    try:
        schedule_html = request_text(HOKEJ_URL)
        match = parse_match_row(schedule_html)
    except (requests.RequestException, ValueError):
        return fallback_from_club_schedule()
    if not match["match_id"]:
        raise ValueError("Chybí ID zápasu pro textový přenos")
    online = json.loads(request_text(ONLINE_URL.format(**match)))
    # Hokej.cz vkládá preview do stejného JSONu jako živý přenos. Dokud nepřijde
    # přesná startovní hláška, nesmí se žádný jeho text vykreslit jako live stav.
    if not text_transfer_started(online):
        return match
    if match_finished(online):
        finished_at = final_whistle_epoch(online)
        now_epoch = int(datetime.now(ZoneInfo("Europe/Prague")).timestamp())
        if finished_at and now_epoch < finished_at + FINISHED_DISPLAY_SECONDS:
            return finished_payload(match, online, finished_at)
        # Rozpis hokej.cz po posledním odehraném utkání nemusí ještě obsahovat
        # další termín. OLED nesmí kvůli tomu dostat HTTP 503; zobrazí poslední
        # ověřený výsledek, dokud se další zápas v programu neobjeví.
        try:
            return parse_next_match(schedule_html)
        except ValueError:
            # Hokej.cz po posledním výsledku někdy další kolo do svého seznamu
            # nedoplní. Oficiální rozpis klubu obsahuje celý ročník.
            try:
                return parse_verva_next_match(request_text(VERVA_MATCHES_URL))
            except ValueError:
                payload = finished_payload(match, online, finished_at or now_epoch)
                payload["source"] = "poslední ověřený výsledek; další termín zatím není zveřejněn"
                payload["schedule_pending"] = True
                return payload
    detail_html = request_text(f"https://www.hokej.cz/zapas/{match['match_id']}")
    return extract_live_state(online, match, detail_html)


SPARTA_CALENDAR_URL = "https://sparta.cz/en/zapasy/1-muzi-a/2026-2027/kalendar"
CHANCE_STANDINGS_URL = "https://www.chanceliga.cz/tabulka/2027/aktualni?id_stage=1"
FOOTBALL_CACHE_SECONDS = 300
_last_tft_football_payload = None
_last_tft_football_refresh = 0.0
_last_tft_slavia_payload = None
_last_tft_slavia_refresh = 0.0
_last_tft_hockey_payload = None
_last_tft_hockey_refresh = 0.0
_tft_hockey_refresh_inflight = False
_tft_hockey_cache_lock = threading.Lock()
_tft_football_refresh_inflight = False
_tft_slavia_refresh_inflight = False
_tft_football_cache_lock = threading.Lock()


def scheduled_tft_status(upstream):
    """Krátké odpočítávání pro TFT místo statického data v den zápasu."""
    status_text = str(upstream.get("game_clock") or "")
    if str(upstream.get("state", "scheduled")) != "scheduled":
        return status_text
    start_epoch = int(upstream.get("match_start_epoch", 0) or 0)
    server_epoch = int(upstream.get("server_epoch", time.time()) or time.time())
    remaining = start_epoch - server_epoch
    if remaining < 0 or remaining > 24 * 60 * 60:
        return status_text
    hours = remaining // 3600
    if hours:
        return f"ZACATEK ZA {hours} H"
    minutes = max(1, remaining // 60)
    return f"ZACATEK ZA {minutes} MIN"


def build_tft_hockey_payload(upstream):
    """TFT-only JSON contract derived from the existing public hockey feed."""
    home_code = str(upstream.get("home_code", "LIT"))
    away_code = str(upstream.get("away_code", "?"))
    cue = str(upstream.get("audio_cue") or "")
    goal_side = str(upstream.get("goal_side") or upstream.get("goal_team") or "")
    if goal_side not in {"home", "away"}:
        lit_is_home = home_code.upper() == "LIT"
        if cue == "lit_goal":
            goal_side = "home" if lit_is_home else "away"
        elif cue == "conceded_goal":
            goal_side = "away" if lit_is_home else "home"
    return {
        "api_version": 1, "sport": "hockey",
        "state": str(upstream.get("state", "scheduled")),
        "competition": "Tipsport extraliga",
        "home": {"code": home_code, "name": upstream.get("home_display") or home_code, "logo": home_code.lower()},
        "away": {"code": away_code, "name": upstream.get("away_display") or away_code, "logo": away_code.lower()},
        "score_home": int(upstream.get("score_home", 0) or 0),
        "score_away": int(upstream.get("score_away", 0) or 0),
        "status_text": scheduled_tft_status(upstream),
        "match_start_epoch": int(upstream.get("match_start_epoch", 0) or 0),
        "server_epoch": int(upstream.get("server_epoch", time.time()) or time.time()),
        "table_position": int(upstream.get("table_position", 0) or 0),
        "event_id": str(upstream.get("event_id") or ""),
        "audio_cue": cue, "goal_side": goal_side, "timezone": "Europe/Prague",
        "source": "litvinov-server",
    }


def _refresh_tft_hockey_payload():
    global _last_tft_hockey_payload, _last_tft_hockey_refresh, _tft_hockey_refresh_inflight, _last_good_status
    try:
        _last_good_status = add_table_position(stahni_live_stav())
        payload = build_tft_hockey_payload(_last_good_status)
        payload["cached"] = False
        with _tft_hockey_cache_lock:
            _last_tft_hockey_payload = payload
    except (requests.RequestException, ValueError) as error:
        app.logger.warning("TFT hockey source failed: %s", error)
    finally:
        with _tft_hockey_cache_lock:
            _last_tft_hockey_refresh = time.monotonic()
            _tft_hockey_refresh_inflight = False


def current_tft_hockey_payload():
    global _tft_hockey_refresh_inflight
    with _tft_hockey_cache_lock:
        if not _tft_hockey_refresh_inflight and time.monotonic() - _last_tft_hockey_refresh >= 30:
            _tft_hockey_refresh_inflight = True
            threading.Thread(target=_refresh_tft_hockey_payload, daemon=True).start()
        payload = dict(_last_tft_hockey_payload or build_tft_hockey_payload(_last_good_status or temporary_source_status()))
    payload["cached"] = True
    return payload
SLAVIA_MATCHES_URL = "https://www.slavia.cz/cze/matches/1?season=2027&type=future"
FOOTBALL_TEAM_CODES = {
    "AC Sparta Praha": "SPA", "SK Slavia Praha": "SKS", "FC Zbrojovka Brno": "ZBR",
    "FC Baník Ostrava": "FCB", "FK Pardubice": "FKP", "Bohemians Praha 1905": "BOH",
    "FC Viktoria Plzeň": "PLZ", "FK Mladá Boleslav": "MBL", "FK Teplice": "TEP",
    "FK Jablonec": "FKJ", "FC Slovan Liberec": "LIB", "FC Hradec Králové": "HKR",
    "1.FC Slovácko": "FCS", "SK Sigma Olomouc": "SIG", "FC Zlín": "FCZ",
}


def football_code(team_name):
    candidate = str(team_name).strip()
    if candidate in FOOTBALL_TEAM_CODES:
        return FOOTBALL_TEAM_CODES[candidate]
    for official_name, code in FOOTBALL_TEAM_CODES.items():
        if official_name in candidate:
            return code
    return "OPP"


def football_display_name(team_name):
    candidate = str(team_name).strip()
    for official_name in FOOTBALL_TEAM_CODES:
        if official_name in candidate:
            return official_name
    return candidate


def chance_team_table_position(standings_page, club_path):
    for row in re.findall(r"<tr[^>]*>.*?</tr>", standings_page, flags=re.IGNORECASE | re.DOTALL):
        if club_path not in row.lower() or 'class="position">' not in row:
            continue
        value = row.split('class="position">', 1)[1].split("</td>", 1)[0].strip()
        if value.isdigit():
            return int(value)
    raise ValueError("Chance Liga standings did not contain requested club")


def build_tft_slavia_payload(matches_page, standings_page, now_epoch=None):
    """TFT football contract from the official Slavia schedule and Chance Liga table."""
    now_epoch = now_epoch or int(time.time())
    soup = BeautifulSoup(matches_page, "html.parser")
    card = soup.select_one("li.match-card.match-card-future")
    if card is None:
        raise ValueError("Slavia official schedule did not contain a future match")
    metadata = card.select_one(".match-card-metadata")
    competition = metadata.find("span").get_text(" ", strip=True) if metadata else "Fotbal"
    times = card.select(".match-card-metadata-timeline time")
    if len(times) < 2:
        raise ValueError("Slavia official schedule did not contain date and time")
    start = datetime.strptime(f"{times[0].get('datetime')} {times[1].get('datetime')}", "%Y-%m-%d %H:%M").replace(tzinfo=ZoneInfo("Europe/Prague"))
    start_epoch = int(start.timestamp())
    teams = [node.get_text(" ", strip=True) for node in card.select(".match-card-teams h2")]
    if len(teams) < 2:
        raise ValueError("Slavia official schedule did not contain both teams")
    home_name, away_name = (football_display_name(teams[0]), football_display_name(teams[1]))
    home_code, away_code = football_code(home_name), football_code(away_name)
    return {
        "api_version": 1, "sport": "football",
        "state": "scheduled" if now_epoch < start_epoch else "finished",
        "competition": competition, "home": {"code": home_code, "name": home_name, "logo": home_code.lower()},
        "away": {"code": away_code, "name": away_name, "logo": away_code.lower()},
        "score_home": 0, "score_away": 0, "status_text": start.strftime("%d. %m. %H:%M"),
        "match_start_epoch": start_epoch, "server_epoch": now_epoch,
        "table_position": chance_team_table_position(standings_page, "/klub/5-sk-slavia-praha"),
        "timezone": "Europe/Prague", "source": "SK Slavia Praha + Chance Liga",
    }


def chance_sparta_table_position(standings_page):
    """Read AC Sparta Praha's current position from official Chance Liga HTML."""
    for row in re.findall(r"<tr[^>]*>.*?</tr>", standings_page, flags=re.IGNORECASE | re.DOTALL):
        if "/klub/2-ac-sparta-praha" not in row.lower() or 'class="position">' not in row:
            continue
        value = row.split('class="position">', 1)[1].split("</td>", 1)[0].strip()
        if value.isdigit():
            return int(value)
    raise ValueError("Chance Liga standings did not contain AC Sparta Praha")


def build_tft_football_payload(official_page, standings_page, now_epoch=None):
    """TFT football contract from official Sparta calendar + Chance Liga table."""
    now_epoch = now_epoch or int(time.time())
    decoded = official_page.replace(chr(92) + '"', '"')
    matches, decoder = [], json.JSONDecoder()
    for found in re.finditer(r'{"match":', decoded):
        try:
            item, _ = decoder.raw_decode(decoded[found.start():])
        except json.JSONDecodeError:
            continue
        if {"match", "opponent", "league"} <= item.keys():
            matches.append(item)
    if not matches:
        raise ValueError("Sparta official calendar did not contain matches")
    future = [item for item in matches if datetime.fromisoformat(item["match"]["start"].replace("Z", "+00:00")).timestamp() >= now_epoch]
    live = [item for item in matches if item["match"].get("state") == "live"]
    selected = (live or sorted(future, key=lambda item: item["match"]["start"]) or matches)[0]
    match, opponent, league = selected["match"], selected["opponent"], selected["league"]
    start_epoch = int(datetime.fromisoformat(match["start"].replace("Z", "+00:00")).timestamp())
    opponent_code = str(opponent.get("shortName") or "OPP")
    opponent_payload = {"code": opponent_code, "name": str(opponent.get("name") or "Soupeř"), "logo": opponent_code.lower()}
    home = bool(match.get("home"))
    return {
        "api_version": 1, "sport": "football",
        "state": "live" if match.get("state") == "live" else ("scheduled" if now_epoch < start_epoch else "finished"),
        "competition": str(league.get("name") or "Fotbal"),
        "home": {"code": "SPA", "name": "AC Sparta Praha", "logo": "sparta"} if home else opponent_payload,
        "away": opponent_payload if home else {"code": "SPA", "name": "AC Sparta Praha", "logo": "sparta"},
        "score_home": 0, "score_away": 0,
        "status_text": datetime.fromtimestamp(start_epoch, ZoneInfo("Europe/Prague")).strftime("%d. %m. %H:%M"),
        "match_start_epoch": start_epoch, "server_epoch": now_epoch,
        "table_position": chance_sparta_table_position(standings_page),
        "timezone": "Europe/Prague", "source": "AC Sparta Praha + Chance Liga",
    }


def _refresh_tft_football_payload():
    global _last_tft_football_payload, _last_tft_football_refresh, _tft_football_refresh_inflight
    try:
        payload = build_tft_football_payload(request_text(SPARTA_CALENDAR_URL), request_text(CHANCE_STANDINGS_URL))
        payload["cached"] = False
        with _tft_football_cache_lock:
            _last_tft_football_payload = payload
    except (requests.RequestException, ValueError) as error:
        app.logger.warning("football source failed: %s", error)
    finally:
        with _tft_football_cache_lock:
            _last_tft_football_refresh = time.monotonic()
            _tft_football_refresh_inflight = False


def _initial_tft_football_payload():
    now = int(time.time())
    return {
        "api_version": 1, "sport": "football", "state": "scheduled", "competition": "Chance Liga",
        "home": {"code": "SPA", "name": "AC Sparta Praha", "logo": "sparta"},
        "away": {"code": "?", "name": "Načítám", "logo": ""},
        "score_home": 0, "score_away": 0, "status_text": "NACITAM FOTBAL",
        "match_start_epoch": 0, "server_epoch": now, "table_position": 0,
        "timezone": "Europe/Prague", "source": "litvinov-server", "cached": True,
    }


def current_tft_football_payload():
    global _tft_football_refresh_inflight
    with _tft_football_cache_lock:
        if not _tft_football_refresh_inflight and time.monotonic() - _last_tft_football_refresh >= FOOTBALL_CACHE_SECONDS:
            _tft_football_refresh_inflight = True
            threading.Thread(target=_refresh_tft_football_payload, daemon=True).start()
        payload = dict(_last_tft_football_payload or _initial_tft_football_payload())
    payload["cached"] = True
    return payload

def _refresh_tft_slavia_payload():
    global _last_tft_slavia_payload, _last_tft_slavia_refresh, _tft_slavia_refresh_inflight
    try:
        payload = build_tft_slavia_payload(request_text(SLAVIA_MATCHES_URL), request_text(CHANCE_STANDINGS_URL))
        payload["cached"] = False
        with _tft_football_cache_lock:
            _last_tft_slavia_payload = payload
    except (requests.RequestException, ValueError) as error:
        app.logger.warning("Slavia football source failed: %s", error)
    finally:
        with _tft_football_cache_lock:
            _last_tft_slavia_refresh = time.monotonic()
            _tft_slavia_refresh_inflight = False


def _initial_tft_slavia_payload():
    now = int(time.time())
    return {
        "api_version": 1, "sport": "football", "state": "scheduled", "competition": "Chance Liga",
        "home": {"code": "SKS", "name": "SK Slavia Praha", "logo": "slavia"},
        "away": {"code": "?", "name": "Načítám", "logo": ""},
        "score_home": 0, "score_away": 0, "status_text": "NACITAM FOTBAL",
        "match_start_epoch": 0, "server_epoch": now, "table_position": 0,
        "timezone": "Europe/Prague", "source": "litvinov-server", "cached": True,
    }


def current_tft_slavia_payload():
    global _tft_slavia_refresh_inflight
    with _tft_football_cache_lock:
        if not _tft_slavia_refresh_inflight and time.monotonic() - _last_tft_slavia_refresh >= FOOTBALL_CACHE_SECONDS:
            _tft_slavia_refresh_inflight = True
            threading.Thread(target=_refresh_tft_slavia_payload, daemon=True).start()
        payload = dict(_last_tft_slavia_payload or _initial_tft_slavia_payload())
    payload["cached"] = True
    return payload


def domov():
    return "HC Verva Hokej Server bezi!"


@app.route("/litvinov")
def get_litvinov():
    global _last_good_payload
    try:
        _last_good_payload = stahni_a_zpracuj()
        return _last_good_payload
    except (requests.RequestException, ValueError) as error:
        app.logger.warning("hokej.cz request failed after retries: %s", error)
        if _last_good_payload is not None:
            return _last_good_payload
        return "HC Verva\nChyba spojeni\nZkus to za chvili", 503


@app.route("/api/command/gol", methods=["POST"])
def command_gol():
    """Bezpečně zařadí jeden vzdálený test znělky pro připojené OLEDy."""
    global _manual_cue
    expected_token = os.environ.get("LITVINOV_COMMAND_TOKEN", "")
    provided_token = request.headers.get("X-Litvinov-Command-Token", "")
    if not expected_token:
        app.logger.error("LITVINOV_COMMAND_TOKEN is not configured")
        return jsonify({"error": "Remote command is not configured"}), 503
    if not hmac.compare_digest(provided_token, expected_token):
        return jsonify({"error": "Unauthorized"}), 401

    now = time.time()
    command_id = secrets.token_urlsafe(12)
    _manual_cue = {
        "id": command_id,
        "cue_at": now + MANUAL_CUE_ARM_SECONDS,
        "expires_at": now + MANUAL_CUE_TOTAL_SECONDS,
    }
    return jsonify({"accepted": True, "command": "gol", "id": command_id}), 202


@app.route("/api/live")
def get_live_status():
    global _last_good_status
    try:
        _last_good_status = add_table_position(stahni_live_stav())
        return jsonify(manual_cue_payload(_last_good_status))
    except (requests.RequestException, ValueError) as error:
        app.logger.warning("live status failed after retries: %s", error)
        if _last_good_status is not None:
            cached = dict(_last_good_status)
            cached["cached"] = True
            return jsonify(manual_cue_payload(cached))
        # Po studeném startu ještě nemusí existovat cache. Vrať platný, ale
        # výslovně neaktuální OLED payload místo HTTP 503, aby panel nezůstal
        # na obrazovce „Wi-Fi připojena“ a dál samostatně retryoval.
        return jsonify(manual_cue_payload(temporary_source_status()))


def load_tft_firmware_manifest():
    """Read the signed-by-SHA256 release catalog served to remote TFT devices."""
    with TFT_FIRMWARE_MANIFEST_PATH.open(encoding="utf-8") as manifest_file:
        return json.load(manifest_file)


@app.route("/api/v1/tft/firmware")
def get_tft_firmware_manifest():
    channel = request.args.get("channel", "").strip().lower()
    current = request.args.get("current", "").strip()
    try:
        release = load_tft_firmware_manifest().get("channels", {}).get(channel)
    except (OSError, ValueError) as error:
        app.logger.error("TFT firmware manifest unavailable: %s", error)
        return jsonify({"error": "firmware_manifest_unavailable"}), 503
    if not release:
        return jsonify({"error": "unknown_firmware_channel"}), 404
    required = {"version", "url", "sha256"}
    if not required <= release.keys() or not re.fullmatch(r"[0-9a-f]{64}", release["sha256"]):
        app.logger.error("invalid TFT firmware manifest entry for %s", channel)
        return jsonify({"error": "invalid_firmware_manifest"}), 503
    return jsonify({
        "api_version": 1, "channel": channel, "current_version": current,
        "available": current != release["version"],
        "version": release["version"], "url": release["url"], "sha256": release["sha256"],
    })


@app.route("/api/v1/sport/hockey")
def get_tft_hockey_status():
    return jsonify(current_tft_hockey_payload())


@app.route("/api/v1/sport/football")
def get_tft_football_status():
    team = request.args.get("team", "SPA").upper()
    if team not in {"SPA", "SKS"}:
        return jsonify({"error": "unsupported_team", "supported_teams": ["SPA", "SKS"]}), 400
    try:
        return jsonify(current_tft_slavia_payload() if team == "SKS" else current_tft_football_payload())
    except (requests.RequestException, ValueError) as error:
        app.logger.warning("TFT football status failed: %s", error)
        return jsonify({"error": "football_source_unavailable"}), 503


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
