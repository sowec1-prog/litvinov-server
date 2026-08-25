# 🏒 Litvínov Hokej IoT Tracker (ESP32 + Flask)

Chytré IoT zařízení postavené na **ESP32** a **OLED displeji**, které v reálném čase sleduje zápasy hokejového týmu **HC Litvínov** (Tipsport Extraliga). 

Zařízení automaticky zobrazuje buď datum a čas nadcházejícího zápasu, nebo aktuální živé skóre během probíhajícího utkání. Data získává Python scraperem z webu hokej.cz, díky čemuž běží kompletně nezávisle.

---

## ✨ Hlavní vlastnosti

* **Živý stav i harmonogram:** Před zápasem ukazuje *Domácí / Datum a čas / Hosté*, během zápasu automaticky přepne prostřední řádek na **aktuální skóre**.
* **Mobilní Wi-Fi konfigurace (WiFiManager):** Pokud zařízení nenajde uloženou Wi-Fi, vytvoří vlastníotevřený hotspot `Litvinov-Config`. Připojíš se mobilem, vybereš svou síť ze seznamu, zadáš heslo a je hotovo.
* **Cloudová podpora:** Server lze provozovat lokálně nebo zdarma v cloudu (např. na Renderu), takže funguje odkudkoliv na světě bez nutnosti mít zapnutý domácí počítač.

---

## 📂 Struktura projektu

```text
├── server.py         # Flask server pro stahování a úpravu dat z hokej.cz
├── requirements.txt  # Závislosti pro Python server
└── esp32_code.ino    # Arduino kód pro ESP32 a OLED displej
