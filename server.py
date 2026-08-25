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
                    
                    matches = list(re.finditer(r'(PO|UT|ST|CT|PA|SO|NE)\s*(\d{1,2}\.\s*\d{1,2}\.)\s*(\d{2}[.:]\d{2})', cisty))
                    
                    if matches:
                        m = matches[0]
                        den_cas = odstran_diakritiku(f"{m.group(1)} {m.group(2)} {m.group(3).replace('.', ':')}")
                        domaci = "Litvinov"
                        
                        m_end = matches[1].end() if len(matches) > 1 else m.end()
                        hoste_raw = cisty[m_end:].strip()
                        
                        noise = ["HC", "LIT", "KOM", "PCE", "SPA", "PLZ", "MLA", "OLO", "VIT", "LIB", "TRI", "CEB", "KVA", "HRA", "VERVA", "Litvinov", "Litvínov"]
                        h_slova = [s for s in hoste_raw.split() if s not in noise]
                        hoste_str = " ".join(h_slova[:2]) if len(h_slova) >= 2 else (" ".join(h_slova) if h_slova else "Souper")
                        hoste = odstran_diakritiku(hoste_str)
                        
                        return f"{domaci}\n{den_cas}\n{hoste}"
            
            return "Litvinov:\nZadne info\n-"
        else:
            return f"Litvinov:\nChyba serveru\n{resp.status_code}"
            
    except Exception as e:
        return "Litvinov:\nChyba stahovani\n-"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
