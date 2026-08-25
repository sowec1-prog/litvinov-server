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
    return "Litvinov Hokej Server běží!"

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
                    
                    # 1. Zjistíme datum a čas
                    matches = list(re.finditer(r'(PO|UT|ST|CT|PA|SO|NE)\s*(\d{1,2}\.\s*\d{1,2}\.)\s*(\d{2}[.:]\d{2})', cisty))
                    den_cas = "Zatim bez casu"
                    if matches:
                        m = matches[0]
                        den_cas = odstran_diakritiku(f"{m.group(1)} {m.group(2)} {m.group(3).replace('.', ':')}")
                    
                    stredny_radek = den_cas  # Tady v sezóně skočí živé skóre a čas
                    
                    # 2. Očištění textu pro nalezení týmů
                    noise = ["HC", "LIT", "KOM", "PCE", "SPA", "PLZ", "MLA", "OLO", "VIT", "LIB", "TRI", "CEB", "KVA", "HRA", "VERVA", "ELH", "Tipsport"]
                    slova = [s for s in cisty.split() if s not in noise and len(s) > 1]
                    
                    # Pokusíme se najít pozici Litvínova a soupeře v textu řádku
                    # Hokej.cz obvykle vypisuje: [Domácí tým] [Čas/Skóre] [Hostující tým]
                    # Zkusíme rozdělit řádek podle data/času na levou (domácí) a pravou (hosté) část
                    
                    if matches:
                        m_start = matches[0].start()
                        leva_strana = cisty[:m_start]
                        prava_strana = cisty[m_start:]
                        
                        # Vytažení prvního týmu z levé strany
                        leva_slova = [s for s in leva_strana.split() if s not in noise and len(s) > 2]
                        domaci_str = " ".join(leva_slova[:2]) if len(leva_slova) >= 2 else (" ".join(leva_slova) if leva_slova else "Domaci")
                        
                        # Vytažení druhého týmu z pravé strany
                        prava_slova = [s for s in prava_strana.split() if s not in noise and len(s) > 2]
                        hoste_str = " ".join(prava_slova[:2]) if len(prava_slova) >= 2 else (" ".join(prava_slova) if prava_slova else "Hoste")
                        
                        domaci = odstran_diakritiku(domaci_str)
                        hoste = odstran_diakritiku(hoste_str)
                        
                        # Bezpečnostní pojistka, kdyby se parsování spletlo, zajistíme, že tam Litvínov bude
                        if "Litvinov" not in domaci and "Litvinov" not in hoste and "Litvinov" in cisty:
                            if cisty.find("Litvinov") < m_start:
                                domaci = "Litvinov"
                            else:
                                hoste = "Litvinov"
                                
                        return f"{domaci}\n{stredny_radek}\n{hoste}"
            
            return "Litvinov:\nZadne info\n-"
        else:
            return f"Litvinov:\nChyba serveru\n{resp.status_code}"
            
    except Exception as e:
        return f"Litvinov:\nChyba stahovani\n-"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
