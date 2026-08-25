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
                cisty = re.sub(r'<[^>]+>', ' ', r)
                cisty = " ".join(cisty.split())
                cisty_bez_diak = odstran_diakritiku(cisty)
                
                # Řádek musí obsahovat Litvínov nebo Vervu
                if not ("litvinov" in cisty_bez_diak.lower() or "verva" in cisty_bez_diak.lower()):
                    continue
                
                # 1. Najdeme datum/čas nebo živé skóre
                match_cas = re.search(r'(PO|UT|ST|CT|PA|SO|NE)\s*(\d{1,2}\.\s*\d{1,2}\.)\s*(\d{2}[.:]\d{2})', cisty_bez_diak)
                match_skore = re.search(r'\d+\s*:\s*\d+', cisty_bez_diak)
                
                den_cas = "Zatim bez casu"
                if match_cas:
                    den_cas = f"{match_cas.group(1)} {match_cas.group(2)} {match_cas.group(3).replace('.', ':')}"
                elif match_skore:
                    den_cas = match_skore.group(0)
                else:
                    continue
                
                # 2. Seznam všech týmů v extralize
                extraliga_tymu = [
                    "Kometa Brno", "Kometa", "Sparta Praha", "Sparta",
                    "Pardubice", "Dynamo", "Ocelari Trinec", "Trinec",
                    "Vitkovice", "Mountfield HK", "Hradec", "Skoda Plzen", "Plzen",
                    "Bili Tygri Liberec", "Liberec", "Mlada Boleslav", "Boleslav",
                    "Rytiri Kladno", "Kladno", "Karlovy Vary", "Vary", "Energie",
                    "Olomouc", "Motor C. Budejovice", "Motor", "Budejovice"
                ]
                
                # Najdeme, jakého soupeře řádek obsahuje
                nalezeny_souper = None
                for t in sorted(extraliga_tymu, key=len, reverse=True):
                    if t.lower() in cisty_bez_diak.lower():
                        # Sjednotíme názvy
                        if "kometa" in t.lower(): nalezeny_souper = "Kometa Brno"
                        elif "sparta" in t.lower(): nalezeny_souper = "Sparta Praha"
                        elif "pardubice" in t.lower() or "dynamo" in t.lower(): nalezeny_souper = "Pardubice"
                        elif "trinec" in t.lower() or "ocelari" in t.lower(): nalezeny_souper = "Ocelari Trinec"
                        elif "vitkovice" in t.lower(): nalezeny_souper = "Vitkovice"
                        elif "hradec" in t.lower() or "mountfield" in t.lower(): nalezeny_souper = "Mountfield HK"
                        elif "plzen" in t.lower() or "skoda" in t.lower(): nalezeny_souper = "Skoda Plzen"
                        elif "liberec" in t.lower(): nalezeny_souper = "Liberec"
                        elif "boleslav" in t.lower(): nalezeny_souper = "Mlada Boleslav"
                        elif "kladno" in t.lower() or "rytiri" in t.lower(): nalezeny_souper = "Kladno"
                        elif "vary" in t.lower() or "energie" in t.lower(): nalezeny_souper = "Karlovy Vary"
                        elif "olomouc" in t.lower(): nalezeny_souper = "Olomouc"
                        elif "motor" in t.lower() or "budejovice" in t.lower(): nalezeny_souper = "Motor C. Bud."
                        if nalezeny_souper:
                            break
                            
                if not nalezeny_souper:
                    continue # Pokud nenajdeme soupeře, jdeme dál
                
                # 3. Zjistíme, kdo hraje doma a kdo venku podle pozice v textu
                pozice_verva = -1
                for kw in ["litvinov", "verva"]:
                    p = cisty_bez_diak.lower().find(kw)
                    if p != -1:
                        pozice_verva = p
                        break
                        
                pozice_soupeře = cisty_bez_diak.lower().find(nalezeny_souper.lower()[:5]) # hledáme podle začátku názvu
                
                # Pokud je Verva dřív v textu než soupeř, hraje doma. Jinak venku.
                if pozice_verva < pozice_soupeře:
                    return f"HC Verva\n{den_cas}\n{nalezeny_souper}"
                else:
                    return f"{nalezeny_souper}\n{den_cas}\nHC Verva"
            
            return "HC Verva\nZadne info\n-"
        else:
            return f"HC Verva\nChyba serveru\n{resp.status_code}"
            
    except Exception as e:
        return f"HC Verva\nChyba stahovani\n-"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
