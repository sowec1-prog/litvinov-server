from flask import Flask
import requests
from bs4 import BeautifulSoup
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
        url = "https://www.hokej.cz/tipsport-extraliga/zapasy?matchlist-filter-team=823"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        resp = requests.get(url, headers=headers, timeout=10)
        
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            radky = soup.find_all('tr')
            
            for r in radky:
                text_radek = r.get_text(separator=" ", strip=True)
                text_bez_diak = odstran_diakritiku(text_radek).lower()
                
                # Zajímá nás jen řádek, kde hraje Litvínov/Verva
                if "litvinov" not in text_bez_diak and "verva" not in text_bez_diak:
                    continue
                
                # Hledáme čas nebo skóre
                match_cas = re.search(r'(po|ut|st|ct|pa|so|ne)\.?\s*(\d{1,2}\.\s*\d{1,2}\.)\s*(\d{2}[.:]\d{2})', text_bez_diak)
                match_skore = re.search(r'\d+\s*:\s*\d+', text_bez_diak)
                
                if not match_cas and not match_skore:
                    continue
                
                den_cas = ""
                pozice_start = -1
                pozice_konec = -1
                
                if match_cas:
                    den_cas = f"{match_cas.group(1).upper()} {match_cas.group(2)} {match_cas.group(3).replace('.', ':')}"
                    pozice_start = match_cas.start()
                    pozice_konec = match_cas.end()
                elif match_skore:
                    den_cas = match_skore.group(0)
                    pozice_start = match_skore.start()
                    pozice_konec = match_skore.end()
                
                # Seznam extraligových týmů
                extraliga_tymu = [
                    "Kometa Brno", "Kometa", "Sparta Praha", "Sparta",
                    "Pardubice", "Dynamo", "Ocelari Trinec", "Trinec",
                    "Vitkovice", "Mountfield HK", "Hradec", "Skoda Plzen", "Plzen",
                    "Bili Tygri Liberec", "Liberec", "Mlada Boleslav", "Boleslav",
                    "Rytiri Kladno", "Kladno", "Karlovy Vary", "Vary", "Energie",
                    "Olomouc", "Motor C. Budejovice", "Motor", "Budejovice"
                ]
                
                nalezene_soupere = []
                for t in sorted(extraliga_tymu, key=len, reverse=True):
                    if t.lower() in text_bez_diak:
                        sjednoceny = t
                        if "kometa" in t.lower(): sjednoceny = "Kometa Brno"
                        elif "sparta" in t.lower(): sjednoceny = "Sparta Praha"
                        elif "pardubice" in t.lower() or "dynamo" in t.lower(): sjednoceny = "Pardubice"
                        elif "trinec" in t.lower() or "ocelari" in t.lower(): sjednoceny = "Ocelari Trinec"
                        elif "vitkovice" in t.lower(): sjednoceny = "Vitkovice"
                        elif "hradec" in t.lower() or "mountfield" in t.lower(): sjednoceny = "Mountfield HK"
                        elif "plzen" in t.lower() or "skoda" in t.lower(): sjednoceny = "Skoda Plzen"
                        elif "liberec" in t.lower(): sjednoceny = "Liberec"
                        elif "boleslav" in t.lower(): sjednoceny = "Mlada Boleslav"
                        elif "kladno" in t.lower() or "rytiri" in t.lower(): sjednoceny = "Kladno"
                        elif "vary" in t.lower() or "energie" in t.lower(): sjednoceny = "Karlovy Vary"
                        elif "olomouc" in t.lower(): sjednoceny = "Olomouc"
                        elif "motor" in t.lower() or "budejovice" in t.lower(): sjednoceny = "Motor C. Bud."
                        
                        if sjednoceny not in nalezene_soupere:
                            nalezene_soupere.append(sjednoceny)
                
                if not nalezene_soupere:
                    continue
                
                souper = nalezene_soupere[0] # První nalezený soupeř v řádku
                
                # Zjištění, zda hraje Litvínov doma nebo venku podle pozice vůči času
                leva_cast = text_bez_diak[:pozice_start]
                
                if "litvinov" in leva_cast or "verva" in leva_cast:
                    return f"HC Verva\n{den_cas}\n{souper}"
                else:
                    return f"{souper}\n{den_cas}\nHC Verva"
            
            return "HC Verva\nZadne info\n-"
        else:
            return f"HC Verva\nChyba serveru\n{resp.status_code}"
            
    except Exception as e:
        return f"HC Verva\nChyba stahovani\n{str(e)}"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
