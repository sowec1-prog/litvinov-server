from flask import Flask
import requests
from bs4 import BeautifulSoup
import re
import threading
import time
import os

app = Flask(__name__)

litvinov_data = "Litvinov:\nHledam zapas..."

def odstran_diakritiku(text):
    """Funkce pro odstranění háčků a čárek pro OLED displej."""
    s_diakritikou = "áčďéěíňóřšťúůýžÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ"
    bez_diakritiky = "acdeeinorstuuyzACDEEINORSTUUYZ"
    preklad = str.maketrans(s_diakritikou, bez_diakritiky)
    return text.translate(preklad)

def aktualizuj_litvinov():
    global litvinov_data
    while True:
        try:
            print("Hledam zapas Litvinova...")
            url = "https://www.hokej.cz/tipsport-extraliga/zapasy?matchlist-filter-season=2026&matchlist-filter-competition=7567&matchlist-filter-team=823"
            headers = {"User-Agent": "Mozilla/5.0"}
            resp = requests.get(url, headers=headers)
            
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, 'html.parser')
                nalezeno = False
                
                for tr in soup.find_all('tr'):
                    tr_text = tr.get_text(" ", strip=True)
                    if "Litvínov" in tr_text or "Litvinov" in tr_text:
                        
                        tds = tr.find_all('td')
                        bunky_teksty = []
                        for td in tds:
                            t = td.get_text(" ", strip=True)
                            if t and t not in bunky_teksty:
                                bunky_teksty.append(t)
                        
                        cely_text = odstran_diakritiku(" ".join(bunky_teksty))
                        
                        slova = cely_text.split()
                        unikatni_slova = []
                        for s in slova:
                            if not unikatni_slova or unikatni_slova[-1] != s:
                                unikatni_slova.append(s)
                        
                        cista_veta = " ".join(unikatni_slova)
                        noise = ["HC", "LIT", "KOM", "PCE", "SPA", "PLZ", "MLA", "OLO", "VIT", "LIB", "TRI", "CEB", "KVA", "HRA", "VERVA"]
                        
                        skore_match = re.search(r'(\d+)\s*:\s*(\d+)', cista_veta)
                        # OPRAVENO: [.:] zohlední tečku i dvojtečku v čase zápasu (např. 17.30)
                        cas_match = re.search(r'(PO|UT|ST|CT|PA|SO|NE)\s*(\d{1,2}\.\s*\d{1,2}\.)\s*(\d{2}[.:]\d{2})', cista_veta)
                        
                        if skore_match and not cas_match:
                            skore = f"{skore_match.group(1)} : {skore_match.group(2)}"
                            pred_skore = cista_veta[:skore_match.start()].strip()
                            za_skore = cista_veta[skore_match.end():].strip()
                            
                            d_slova = [s for s in pred_skore.split() if s not in noise]
                            h_slova = [s for s in za_skore.split() if s not in noise]
                            
                            domaci_str = " ".join(d_slova[-2:]) if len(d_slova) >= 2 else (" ".join(d_slova) if d_slova else "Litvinov")
                            hoste_str = " ".join(h_slova[:2]) if len(h_slova) >= 2 else (" ".join(h_slova) if h_slova else "Souper")
                            
                            litvinov_data = f"{domaci_str}\n{skore}\n{hoste_str}"
                            nalezeno = True
                            break
                            
                        elif cas_match:
                            den = cas_match.group(1)
                            datum = cas_match.group(2)
                            # Sjednotíme tečku v čase na dvojtečku pro hezčí vzhled
                            cas = cas_match.group(3).replace('.', ':')
                            datum_cas = f"{den} {datum} {cas}"
                            
                            domaci_raw = cista_veta[:cas_match.start()].strip()
                            d_slova = [s for s in domaci_raw.split() if s not in noise]
                            domaci_str = " ".join(d_slova[-2:]) if len(d_slova) >= 2 else (" ".join(d_slova) if d_slova else "Litvinov")
                            
                            hoste_raw = cista_veta[cas_match.end():].strip()
                            h_slova = [s for s in hoste_raw.split() if s not in noise]
                            hoste_str = " ".join(h_slova[:2]) if len(h_slova) >= 2 else (" ".join(h_slova) if h_slova else "Souper")
                            
                            litvinov_data = f"{domaci_str}\n{datum_cas}\n{hoste_str}"
                            nalezeno = True
                            break
                
                if not nalezeno:
                    litvinov_data = "Litvinov:\nZadne info\n-"
            
            print("Data pro Litvínov aktualizována.")
            
        except Exception as e:
            print("Chyba ve vlákně:", e)
            
        time.sleep(60)

@app.route("/")
def domov():
    return "Litvinov Hokej Server běží!"

@app.route("/litvinov")
def get_litvinov():
    return litvinov_data

# Spuštění vlákna pro stahování dat jak lokálně, tak v cloudu
if __name__ == "__main__":
    t = threading.Thread(target=aktualizuj_litvinov, daemon=True)
    t.start()
    app.run(host="0.0.0.0", port=5000, debug=False)
else:
    # Pro Gunicorn v cloudu
    t = threading.Thread(target=aktualizuj_litvinov, daemon=True)
    t.start()
