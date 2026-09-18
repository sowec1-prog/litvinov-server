from flask import Flask, jsonify
import html
import json
import re
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

app = Flask(__name__)

HOKEJ_URL = "https://www.hokej.cz/tipsport-extraliga/zapasy?matchlist-filter-team=823"
ONLINE_URL = "https://s3-eu-west-1.amazonaws.com/hokej.cz/match/2026/short/{match_id}.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (Litvinov scoreboard; contact: github.com/sowec1-prog/litvinov-server)"}
RETRY_COUNT = 3
REQUEST_TIMEOUT = (5, 15)
_last_good_payload = None
_last_good_status = None


def odstran_diakritiku(text):
    return text.translate(str.maketrans(
        "áčďéěíňóřšťúůýžÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ",
        "acdeeinorstuuyzACDEEINORSTUUYZ",
    ))


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
        names = [n.get_text(" ", strip=True) for n in row.select("td.preview__name")]
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


def display_team_name(name, code):
    """Zkrátí jméno z tabulky pro 128px OLED: odstraní duplicitní město a kód."""
    result = re.sub(r"\s+", " ", name).strip()
    if code:
        # V live rozpisu mohou za kódem zůstat kurzy; pro OLED vše za kódem odstranit.
        result = re.sub(rf"\s+{re.escape(code)}(?:\s+.*)?$", "", result)
    words = result.split()
    compact = []
    for word in words:
        if not compact or compact[-1].casefold() != word.casefold():
            compact.append(word)
    # Hokej.cz u nekterych tymu opakuje mesto na konci, napr.
    # "HC Vitkovice Ridera Vitkovice". Zakonny opakovany token odebereme.
    while len(compact) > 1 and compact[-1].casefold() in {word.casefold() for word in compact[:-1]}:
        compact.pop()
    # SSD1306 font v ESP32 nepodporuje českou UTF-8 diakritiku.
    return odstran_diakritiku(" ".join(compact))


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
        names = [cell.select_one("a").get_text(" ", strip=True)
                 for cell in name_cells if cell.select_one("a")]
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


def match_finished(online_json):
    """Vrací True jen po závěrečném hvizdu, ne po konci 1. nebo 2. třetiny."""
    comments = online_json.get("comments", {}).get("comment", [])
    if not isinstance(comments, list):
        comments = [comments]
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


def comment_team(comment, home_name):
    details = comment.get("details", {})
    detail = details.get("detail", {}) if isinstance(details, dict) else {}
    opponent = detail.get("opponent", {}).get("@attributes", {}) if isinstance(detail, dict) else {}
    if opponent.get("code") == "LIT":
        return "home" if "litv" in odstran_diakritiku(home_name).lower() or "verva" in odstran_diakritiku(home_name).lower() else "away"
    text = odstran_diakritiku(message_text(comment)).lower()
    if "litvinov" in text or "verva" in text:
        return "home" if "litv" in odstran_diakritiku(home_name).lower() or "verva" in odstran_diakritiku(home_name).lower() else "away"
    return "away"


def parse_last_goal(match_html, home_name):
    soup = BeautifulSoup(match_html, "html.parser")
    goals = []
    for row in soup.select("tr"):
        cells = row.find_all("td", recursive=False)
        if len(cells) < 3:
            continue
        timestamp = cells[0].get_text(" ", strip=True)
        team_code = cells[1].get_text(" ", strip=True).upper()
        player_link = cells[2].select_one('a[href*="/hrac/"]')
        if not re.match(r"^\d{1,2}:\d{2}$", timestamp) or team_code not in {"LIT", "KOM"} or player_link is None:
            continue
        name = re.sub(r"\s*\(\d+\)\s*$", "", player_link.get_text(" ", strip=True)).title()
        goals.append((game_seconds(timestamp), name, "home" if team_code == "LIT" else "away"))
    if not goals:
        return {"scorer": "", "team": "", "event_id": ""}
    _, scorer, team = max(goals, key=lambda goal: goal[0])
    return {"scorer": scorer, "team": team, "event_id": f"goal-{scorer}-{team}"}


def parse_intermission(text):
    """Vrátí (je_přestávka, epoch_začátku_další_třetiny, stručný text pro OLED)."""
    found = re.search(r"Dalsi tretina zacne priblizne v\s*(\d{1,2}):(\d{2})", odstran_diakritiku(text), re.IGNORECASE)
    if not found:
        return False, 0, ""
    now = datetime.now(ZoneInfo("Europe/Prague"))
    hour, minute = map(int, found.groups())
    start = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if start < now:
        start = start.replace(day=now.day + 1)
    return True, int(start.timestamp()), f"PRESTAVKA DO {hour:02d}:{minute:02d}"


def extract_live_state(online_json, match, match_html=None):
    comments = online_json.get("comments", {}).get("comment", [])
    if not isinstance(comments, list):
        comments = [comments]
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
        display_clock = str(current.get("time", ""))
    intermission, intermission_until_epoch, intermission_note = parse_intermission(message_text(newest))
    home_codes = re.findall(r"\b[A-Z]{3}\b", match["home"])
    away_codes = re.findall(r"\b[A-Z]{3}\b", match["away"])
    home_code = home_codes[-1] if home_codes else ""
    away_code = away_codes[-1] if away_codes else ""
    active = []
    last_goal = {"scorer": "", "team": "", "event_id": ""}

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
                penalty_team = "home" if penalty_code == home_code else "away" if penalty_code == away_code else team
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
                last_goal = {"scorer": scorer, "team": team, "event_id": item_attrs.get("id", "")}

    active = [p for p in active if p["until"] > now]
    if not last_goal["scorer"] and match_html:
        last_goal = parse_last_goal(match_html, match["home"])
    home_penalties = sum(p["team"] == "home" for p in active)
    away_penalties = sum(p["team"] == "away" for p in active)
    if home_penalties > away_penalties:
        power_play = f"LIT osl. {max(3, 5-home_penalties)}:5"
    elif away_penalties > home_penalties:
        power_play = f"LIT pres. 5:{max(3, 5-away_penalties)}"
    else:
        power_play = "Plný počet 5:5"

    home_codes = re.findall(r"\b[A-Z]{3}\b", match["home"])
    away_codes = re.findall(r"\b[A-Z]{3}\b", match["away"])
    home_code = home_codes[-1] if home_codes else ""
    away_code = away_codes[-1] if away_codes else ""

    active_codes = []
    for penalty in active:
        code = home_code if penalty["team"] == "home" else away_code
        if code and code not in active_codes:
            active_codes.append(code)
    penalty_indicator = "TRES-" + "/".join(active_codes) if active_codes else ""

    lit_side = "home" if "litv" in odstran_diakritiku(match["home"]).lower() or "verva" in odstran_diakritiku(match["home"]).lower() else "away"
    audio_cue = ""
    if last_goal["event_id"]:
        audio_cue = "lit_goal" if last_goal["team"] == lit_side else "conceded_goal"

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
        "intermission_until_epoch": intermission_until_epoch,
        "server_epoch": int(datetime.now(ZoneInfo("Europe/Prague")).timestamp()),
        "intermission_note": intermission_note,
        "score_home": int(attrs.get("score1", match["score_home"])),
        "score_away": int(attrs.get("score2", match["score_away"])),
        "last_goal_scorer": odstran_diakritiku(last_goal["scorer"]),
        "last_goal_team": last_goal["team"],
        "last_goal_code": home_code if last_goal["team"] == "home" else away_code if last_goal["team"] == "away" else "",
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


def stahni_live_stav():
    schedule_html = request_text(HOKEJ_URL)
    match = parse_match_row(schedule_html)
    if not match["match_id"]:
        raise ValueError("Chybí ID zápasu pro textový přenos")
    online = json.loads(request_text(ONLINE_URL.format(**match)))
    if match_finished(online):
        return parse_next_match(schedule_html)
    detail_html = request_text(f"https://www.hokej.cz/zapas/{match['match_id']}")
    return extract_live_state(online, match, detail_html)


@app.route("/")
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


@app.route("/api/live")
def get_live_status():
    global _last_good_status
    try:
        _last_good_status = stahni_live_stav()
        return jsonify(_last_good_status)
    except (requests.RequestException, ValueError) as error:
        app.logger.warning("live status failed after retries: %s", error)
        if _last_good_status is not None:
            cached = dict(_last_good_status)
            cached["cached"] = True
            return jsonify(cached)
        return jsonify({"error": "Zdroj hokej.cz je dočasně nedostupný"}), 503


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
