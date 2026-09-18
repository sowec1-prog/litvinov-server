from flask import Flask, jsonify
import html
import json
import re
import time
from datetime import datetime

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
    soup = BeautifulSoup(html_text, "html.parser")
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
        return {
            "match_id": match.group(1) if match else "",
            "home": home,
            "away": away,
            "score_home": int(left),
            "score_away": int(right),
        }
    raise ValueError("Aktuální zápas Litvínova se skóre nebyl v seznamu nalezen")


def parse_scheduled_epoch(game_clock):
    """Převede text programu „PÁ 18. 09. 17:30“ na epochu v Praze."""
    # Server běží na domácím PC v českém místním čase; nevyžaduje externí databázi pásem.
    now = datetime.now().astimezone()
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
            "event_id": "",
            "power_play": "Zápas ještě nezačal",
            "penalties": [],
            "source": "hokej.cz program",
        }
    raise ValueError("Další zápas Litvínova nebyl v programu nalezen")


def match_finished(online_json):
    comments = online_json.get("comments", {}).get("comment", [])
    if not isinstance(comments, list):
        comments = [comments]
    for item in comments[:12]:
        attrs = item.get("@attributes", {})
        if attrs.get("label") == "time" and attrs.get("type") == "end":
            return True
        if "konec zapasu" in odstran_diakritiku(message_text(item)).lower():
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


def extract_live_state(online_json, match, match_html=None):
    comments = online_json.get("comments", {}).get("comment", [])
    if not isinstance(comments, list):
        comments = [comments]
    chronological = list(reversed(comments))
    current = comments[0] if comments else {"@attributes": {}}
    attrs = current.get("@attributes", {})
    now = game_seconds(current.get("time"))
    active = []
    last_goal = {"scorer": "", "team": "", "event_id": ""}

    for item in chronological:
        item_attrs = item.get("@attributes", {})
        label = item_attrs.get("label", "")
        text = message_text(item)
        normalized = odstran_diakritiku(text).lower()
        team = comment_team(item, match["home"])
        if label == "penalty":
            detail = item.get("details", {}).get("detail", {})
            player = detail.get("player1", {}).get("@attributes", {}).get("name", "hráč")
            penalty = detail.get("player1", {}).get("penalties", {}).get("penalty", {})
            if isinstance(penalty, list):
                penalty = penalty[0]
            minutes = int(penalty.get("@attributes", {}).get("length", "2") or 2)
            active.append({"team": team, "player": player, "until": game_seconds(item.get("time")) + minutes * 60})
        elif " v plnem poctu" in normalized:
            # Textový přenos výslovně potvrzuje konec oslabení; odstraníme nejstarší trest týmu.
            for index, penalty in enumerate(active):
                if penalty["team"] == team:
                    active.pop(index)
                    break
        if label == "goal" or "gol" in normalized and ("branka" in normalized or "gól" in text.lower()):
            detail = item.get("details", {}).get("detail", {})
            scorer = detail.get("player1", {}).get("@attributes", {}).get("name", "")
            if scorer:
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

    return {
        **match,
        "game_clock": current.get("time", ""),
        "score_home": int(attrs.get("score1", match["score_home"])),
        "score_away": int(attrs.get("score2", match["score_away"])),
        "last_goal_scorer": last_goal["scorer"],
        "last_goal_team": last_goal["team"],
        "event_id": last_goal["event_id"] or attrs.get("id", ""),
        "power_play": power_play,
        "penalties": [{"team": p["team"], "player": p["player"]} for p in active],
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
