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
        url = "https://www.hokej.cz/tipsport-extraliga/zapasy"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        resp = requests.get(url, headers=headers, timeout=10)
        
        if resp.status_code == 200:
            radecky = resp.text.split("</tr>")
            
            for r in radecky:
                if "VERVA" in r or "Verva" in r or "Litvínov" in r or "Litvinov" in r:
                    cisty = re.sub(r'<[^>]+>', ' ', r)
                    cisty = " ".join(cisty.split())
                    cisty_bez_diak = odstran_diakritiku(cisty)
                    
                    # 1. Najdeme datum a čas
                    matches = list(re.finditer(r'(PO|UT|ST|CT|PA|SO|NE)\s*(\d{1,2}\.\s*\d{1,2}\.)\s*(\d{2}[.:]\d{2})', cisty))
                    den_cas = "Zatim bez casu"
                    if matches:
                        m = matches[0]
                        den_cas = odstran_diakritiku(f"{m.group(1)} {m.group(2)} {m.group(3).replace('.', ':')}")
                    
                    # 2. Seznam všech možných soupeřů v extralize
                    extraliga_tymu = {
                        "Kometa": "Kometa Brno",
                        "Sparta": "Sparta Praha",
                        "Pardubice": "Pardubice",
                        "Dynamo": "Pardubice",
                        "Trinec": "Ocelari Trinec",
                        "Ocelari": "Ocelari Trinec",
                        "Vitkovice": "Vitkovice",
                        "Mountfield": "Mountfield HK",
                        "Hradec": "Mountfield HK",
                        "Plzen": "Skoda Plzen",
                        "Skoda": "Skoda Plzen",
                        "Liberec": "Bili Tygri Liberec",
                        "Boleslav": "Mlada Boleslav",
                        "Kladno": "Rytiri Kladno",
                        "Rytiri": "Rytiri Kladno",
                        "Vary": "Karlovy Vary",
                        "Energie": "Karlovy Vary",
                        "Olomouc": "Olomouc",
                        "Motor": "Motor C. Budejovice",
                        "Budejovice": "Motor C. Budejovice"
                    }
                    
                    souper = "Neznamy soupeř"
                    je_doma = True
                    
                    # Pozice Vervy na řádku (hledáme jakékoliv označení Litvínova)
                    pozice_verva = -1
                    for keyword in ["Litvinov", "Litvínov", "Verva", "VERVA"]:
                        pos = cisty_bez_diak.find(odstran_diakritiku(keyword))
                        if pos != -1:
                            pozice_verva = pos
                            break
                    if pozice_verva == -1:
                        pozice_verva = 99999

                    # Projdeme klíčová slova soupeřů
                    for klic, nazev in extraliga_tymu.items():
                        if klic.lower() in cisty_bez_diak.lower():
                            # Pojistka, ať to nezamění za náš tým
                            if klic.lower() not in ["litvinov", "litvínov", "verva"]:
                                souper = nazev
                                pozice_soupeře = cisty_bez_diak.lower().find(klic.lower())
                                if pozice_soupeře < pozice_verva:
                                    je_doma = False
                                break

                    # 3. Sestavení výsledku s názvem HC Verva
                    if je_doma:
                        return f"HC Verva\n{den_cas}\n{souper}"
                    else:
                        return f"{souper}\n{den_cas}\nHC Verva"
            
            return "HC Verva\nZadne info\n-"
        else:
            return f"HC Verva\nChyba serveru\n{resp.status_code}"
            
    except Exception as e:
        return f"HC Verva\nChyba stahovani\n-"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
