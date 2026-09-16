from flask import Flask
import requests
from bs4 import BeautifulSoup
import re
import time

app = Flask(__name__)

HOKEJ_URL = "https://www.hokej.cz/tipsport-extraliga/zapasy?matchlist-filter-team=823"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
RETRY_COUNT = 3
REQUEST_TIMEOUT = (5, 15)  # connect / read seconds
_last_good_payload = None


def odstran_diakritiku(text):
    s_diakritikou = "áčďéěíňóřšťúůýžÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ"
    bez_diakritiky = "acdeeinorstuuyzACDEEINORSTUUYZ"
    preklad = str.maketrans(s_diakritikou, bez_diakritiky)
    return text.translate(preklad)


def zpracuj_html(html):
    soup = BeautifulSoup(html, "html.parser")
    radky = soup.find_all("tr")

    for r in radky:
        text_radek = r.get_text(separator=" ", strip=True)
        text_bez_diak = odstran_diakritiku(text_radek).lower()

        if "litvinov" not in text_bez_diak and "verva" not in text_bez_diak:
            continue

        # Hlavní skóre je v samostatných buňkách. Neber první výraz „0:0“
        # z rozepsaných třetin (např. „(0:0, 1:0, 0:0)“).
        score_cells = r.select("td.preview__score")
        hlavni_skore = None
        if len(score_cells) >= 2:
            levy_skor = score_cells[0].get_text(strip=True)
            pravy_skor = score_cells[1].get_text(strip=True)
            if levy_skor.isdigit() and pravy_skor.isdigit():
                hlavni_skore = f"{levy_skor}:{pravy_skor}"

        match_cas = re.search(
            r"(po|ut|st|ct|pa|so|ne)\.?\s*(\d{1,2}\.\s*\d{1,2}\.)\s*(\d{2}[.:]\d{2})",
            text_bez_diak,
        )
        match_skore = re.search(r"\d+\s*:\s*\d+", text_bez_diak) if hlavni_skore is None else None
        if not match_cas and not hlavni_skore and not match_skore:
            continue

        if hlavni_skore is not None:
            den_cas = hlavni_skore
            pozice_start = text_bez_diak.find(levy_skor)
        elif match_cas:
            den_cas = f"{match_cas.group(1).upper()} {match_cas.group(2)} {match_cas.group(3).replace('.', ':')}"
            pozice_start = match_cas.start()
        else:
            den_cas = match_skore.group(0)
            pozice_start = match_skore.start()

        extraliga_tymu = [
            "Kometa Brno", "Kometa", "Sparta Praha", "Sparta",
            "Pardubice", "Dynamo", "Ocelari Trinec", "Trinec",
            "Vitkovice", "Mountfield HK", "Hradec", "Skoda Plzen", "Plzen",
            "Bili Tygri Liberec", "Liberec", "Mlada Boleslav", "Boleslav",
            "Rytiri Kladno", "Kladno", "Karlovy Vary", "Vary", "Energie",
            "Olomouc", "Motor C. Budejovice", "Motor", "Budejovice",
        ]
        nalezene_soupere = []
        for tym in sorted(extraliga_tymu, key=len, reverse=True):
            if tym.lower() not in text_bez_diak:
                continue
            souper = tym
            if "kometa" in tym.lower():
                souper = "Kometa Brno"
            elif "sparta" in tym.lower():
                souper = "Sparta Praha"
            elif "pardubice" in tym.lower() or "dynamo" in tym.lower():
                souper = "Pardubice"
            elif "trinec" in tym.lower() or "ocelari" in tym.lower():
                souper = "Ocelari Trinec"
            elif "vitkovice" in tym.lower():
                souper = "Vitkovice"
            elif "hradec" in tym.lower() or "mountfield" in tym.lower():
                souper = "Mountfield HK"
            elif "plzen" in tym.lower() or "skoda" in tym.lower():
                souper = "Skoda Plzen"
            elif "liberec" in tym.lower():
                souper = "Liberec"
            elif "boleslav" in tym.lower():
                souper = "Mlada Boleslav"
            elif "kladno" in tym.lower() or "rytiri" in tym.lower():
                souper = "Kladno"
            elif "vary" in tym.lower() or "energie" in tym.lower():
                souper = "Karlovy Vary"
            elif "olomouc" in tym.lower():
                souper = "Olomouc"
            elif "motor" in tym.lower() or "budejovice" in tym.lower():
                souper = "Motor C. Bud."
            if souper not in nalezene_soupere:
                nalezene_soupere.append(souper)

        if not nalezene_soupere:
            continue

        if "litvinov" in text_bez_diak[:pozice_start] or "verva" in text_bez_diak[:pozice_start]:
            return f"HC Verva\n{den_cas}\n{nalezene_soupere[0]}"
        return f"{nalezene_soupere[0]}\n{den_cas}\nHC Verva"

    return "HC Verva\nZadne info\n-"


def stahni_a_zpracuj():
    posledni_chyba = None
    for pokus in range(RETRY_COUNT):
        response = None
        try:
            response = requests.get(HOKEJ_URL, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            return zpracuj_html(response.text)
        except requests.RequestException as chyba:
            posledni_chyba = chyba
            if pokus < RETRY_COUNT - 1:
                time.sleep(pokus + 1)
        finally:
            if response is not None:
                response.close()
    raise posledni_chyba


@app.route("/")
def domov():
    return "HC Verva Hokej Server bezi!"


@app.route("/litvinov")
def get_litvinov():
    global _last_good_payload
    try:
        payload = stahni_a_zpracuj()
        _last_good_payload = payload
        return payload
    except requests.RequestException as chyba:
        app.logger.warning("hokej.cz request failed after retries: %s", chyba)
        if _last_good_payload is not None:
            return _last_good_payload
        return "HC Verva\nChyba spojeni\nZkus to za chvili", 503


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
