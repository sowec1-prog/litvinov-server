from flask import Flask
import requests
from bs4 import BeautifulSoup

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
            
            # Hokej.cz mívá zápasy v tabulkách nebo v blocích tříd match-row / podobně
            # Zkusíme najít všechny řádky tabulky (tr) nebo divy se zápasy
            radky = soup.find_all('tr')
            
            for r in radky:
                text_radek = r.get_text(separator=" ", strip=True)
                text_bez_diak = odstran_diakritiku(text_radek).lower()
                
                # Řádek musí obsahovat Litvínov nebo Vervu
                if "litvinov" not in text_bez_diak and "verva" not in text_bez_diak:
                    continue
                
                # Zjistíme, jestli obsahuje datum/čas (např. PO, ÚT, ST...) nebo skóre
                # Hledáme den v týdnu následovaný datem
                import re
                match_cas = re.search(r'(po|ut|st|ct|pa|so|ne)\.?\s*(\d{1,2}\.\s*\d{1,2}\.)\s*(\d{2}[.:]\d{2})', text_bez_diak)
                match_skore = re.search(r'\d+\s*:\s*\d+', text_bez_diak)
                
                if not match_cas and not match_skore:
                    continue
                
                den_cas = ""
                if match_cas:
                    den_cas = f"{match_cas.group(1).upper()} {match_cas.group(2)} {match_cas.group(3).replace('.', ':')}"
                elif match_skore:
                    den_cas = match_skore.group(0)
                
                # Extrakce týmů uvnitř tohoto konkrétního řádku (DOM struktury)
                # Zkusíme najít týmy v buňkách (td)
                bunky = r.find_all('td')
                domaci = ""
                hoste = ""
                
                # Často bývá domácí v první buňce s týmem, host v jiné, nebo to vytáhneme bezpečně z textu buněk
                tymy_seznam = [
                    "Kometa Brno", "Kometa", "Sparta Praha", "Sparta",
                    "Pardubice", "Dynamo", "Ocelari Trinec", "Trinec",
                    "Vitkovice", "Mountfield HK", "Hradec", "Skoda Plzen", "Plzen",
                    "Bili Tygri Liberec", "Liberec", "Mlada Boleslav", "Boleslav",
                    "Rytiri Kladno", "Kladno", "Karlovy Vary", "Vary", "Energie",
                    "Olomouc", "Motor C. Budejovice", "Motor", "Budejovice",
                    "Litvinov", "Verva"
                ]
                
                nalezene_tymy = []
                for t in sorted(tymy_seznam, key=len, reverse=True):
                    if t.lower() in text_bez_diak:
                        # Sjednocení názvů
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
                        elif "litvinov" in t.lower() or "verva" in t.lower(): sjednoceny = "HC Verva"
                        
                        if sjednoceny not in nalazene_tymy:
                            nalazene_tymy.append(sjednoceny)
                
                # Musíme najít přesně dva týmy (Litvínov + soupeře)
                souperi = [t for t in nalazene_tymy if t != "HC Verva"]
                if not souperi:
                    continue
                
                souper = souperi[0]
                
                # Zjištění, kdo hraje doma (kdo je v HTML dřív na řádku)
                pozice_verva = text_bez_diak.find("litvinov")
                if pozice_verva == -1: pozice_verva = text_bez_diak.find("verva")
                
                pozice_soup = text_bez_diak.find(souper.lower()[:5])
                
                if pozice_verva < pozice_soup:
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
