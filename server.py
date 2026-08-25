from flask import Flask
import requests
import re

app = Flask(__name__)

def odstran_diakritiku(text):
    s_diakritikou = "áčďéěíňóřšťúůýžÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ"
    bez_diakritiky = "acdeeinorstuuyzACDEEINORSTUUYZ"
    preklad = str.maketrans(s_diakritikou, bez_diakritiky)
    return text.translate(preklad)

@app.route("/")
def domov():
    return "HC Verva Hokej Server běží!"

@app.route("/litvinov")
def get_litvinov():
    try:
        url = "https://www.hokej.cz/tipsport-extraliga/zapasy?matchlist-filter-season=2026&matchlist-filter-competition=7567&matchlist-filter-team=823"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        resp = requests.get(url, headers=headers, timeout=10)
        
        if resp.status_code == 200:
            radecky = resp.text.split("</tr>")
            
            for r in radecky:
                if "VERVA" in r or "Verva" in r or "Litvínov" in r or "Litvinov" in r:
                    cisty = re.sub(r'<[^>]+>', ' ', r)
                    cisty = " ".join(cisty.split())
                    cisty_bez_diak = odstran_diakritiku(cisty)
                    
                    # 1. Hledáme buď datum/čas (před zápasem) nebo živé skóre (během zápasu)
                    match_cas = re.search(r'(PO|UT|ST|CT|PA|SO|NE)\s*(\d{1,2}\.\s*\d{1,2}\.)\s*(\d{2}[.:]\d{2})', cisty_bez_diak)
                    match_skore = re.search(r'\d+\s*:\s*\d+', cisty_bez_diak)
                    
                    den_cas = "Zatim bez casu"
                    pozice_start = -1
                    pozice_konec = -1
                    
                    if match_cas:
                        den_cas = f"{match_cas.group(1)} {match_cas.group(2)} {match_cas.group(3).replace('.', ':')}"
                        pozice_start = match_cas.start()
                        pozice_konec = match_cas.end()
                    elif match_skore:
                        den_cas = match_skore.group(0)
                        pozice_start = match_skore.start()
                        pozice_konec = match_skore.end()
                    else:
                        continue # Pokud tam není čas ani skóre, řádek přeskočíme
                    
                    leva_cast = cisty_bez_diak[:pozice_start]
                    prava_cast = cisty_bez_diak[pozice_konec:]
                    
                    # Seznam extraligových týmů pro spolehlivé parsování
                    extraliga_tymu = [
                        "Litvinov", "Litvínov", "Verva", "VERVA",
                        "Kometa Brno", "Kometa", "Sparta Praha", "Sparta",
                        "Pardubice", "Dynamo", "Ocelari Trinec", "Trinec",
                        "Vitkovice", "Mountfield HK", "Hradec", "Skoda Plzen", "Plzen",
                        "Bili Tygri Liberec", "Liberec", "Mlada Boleslav", "Boleslav",
                        "Rytiri Kladno", "Kladno", "Karlovy Vary", "Vary", "Energie",
                        "Olomouc", "Motor C. Budejovice", "Motor", "Budejovice"
                    ]
                    
                    def najdi_tym(text):
                        text_lower = text.lower()
                        for t in sorted(extraliga_tymu, key=len, reverse=True):
                            if t.lower() in text_lower:
                                if "kometa" in t.lower(): return "Kometa Brno"
                                if "sparta" in t.lower(): return "Sparta Praha"
                                if "pardubice" in t.lower() or "dynamo" in t.lower(): return "Pardubice"
                                if "trinec" in t.lower() or "ocelari" in t.lower(): return "Ocelari Trinec"
                                if "vitkovice" in t.lower(): return "Vitkovice"
                                if "hradec" in t.lower() or "mountfield" in t.lower(): return "Mountfield HK"
                                if "plzen" in t.lower() or "skoda" in t.lower(): return "Skoda Plzen"
                                if "liberec" in t.lower(): return "Liberec"
                                if "boleslav" in t.lower(): return "Mlada Boleslav"
                                if "kladno" in t.lower() or "rytiri" in t.lower(): return "Kladno"
                                if "vary" in t.lower() or "energie" in t.lower(): return "Karlovy Vary"
                                if "olomouc" in t.lower(): return "Olomouc"
                                if "motor" in t.lower() or "budejovice" in t.lower(): return "Motor C. Bud."
                                if "litvinov" in t.lower() or "verva" in t.lower(): return "HC Verva"
                        return "Soupeř"

                    domaci = najdi_tym(leva_cast)
                    hoste = najdi_tym(prava_cast)
                    
                    # Vrátíme přesně 3 řádky pro displej
                    return f"{domaci}\n{den_cas}\n{hoste}"
            
            return "HC Verva\nZadne info\n-"
        else:
            return f"HC Verva\nChyba serveru\n{resp.status_code}"
            
    except Exception as e:
        return f"HC Verva\nChyba stahovani\n-"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
