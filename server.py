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
            url = "https://www.hokej.cz/tipsport-extraliga/zapasy"
            headers = {"User-Agent": "Mozilla/5.0"}
            resp = requests.get(url, headers=headers)
            
            if resp.status_code == 200:
                radecky = resp.text.split("</tr>")
                nalezeno = False
                
                for r in radecky:
                    if "Litvínov" in r or "Litvinov" in r:
                        cisty = re.sub(r'<[^>]+>', ' ', r)
                        cisty = " ".join(cisty.split())
                        
                        # Najdeme všechny výskyty data a času v řádku
                        matches = list(re.finditer(r'(PO|UT|ST|CT|PA|SO|NE)\s*(\d{1,2}\.\s*\d{1,2}\.)\s*(\d{2}[.:]\d{2})', cisty))
                        
                        if matches:
                            m = matches[0]
                            den_cas = odstran_diakritiku(f"{m.group(1)} {m.group(2)} {m.group(3).replace('.', ':')}")
                            
                            domaci_raw = cisty[:m.start()].strip()
                            domaci = "Litvinov" if "Litv" in domaci_raw else odstran_diakritiku(domaci_raw)
                            
                            m_end = matches[1].end() if len(matches) > 1 else m.end()
                            hoste_raw = cisty[m_end:].strip()
                            
                            noise = ["HC", "LIT", "KOM", "PCE", "SPA", "PLZ", "MLA", "OLO", "VIT", "LIB", "TRI", "CEB", "KVA", "HRA", "VERVA"]
                            h_slova = [s for s in hoste_raw.split() if s not in noise]
                            hoste_str = " ".join(h_slova[:2]) if len(h_slova) >= 2 else (" ".join(h_slova) if h_slova else "Souper")
                            hoste = odstran_diakritiku(hoste_str)
                            
                            # Uložíme formát pro displej (3 řádky oddělené \n)
                            litvinov_data = f"{domaci}\n{den_cas}\n{hoste}"
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

if __name__ == "__main__":
    t = threading.Thread(target=aktualizuj_litvinov, daemon=True)
    t.start()
    app.run(host="0.0.0.0", port=5000, debug=False)
else:
    t = threading.Thread(target=aktualizuj_litvinov, daemon=True)
    t.start()
