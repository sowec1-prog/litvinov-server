# 🏒 HC Verva Litvínov Hokej IoT Tracker

ESP32/MicroPython s OLED displejem ukazuje nadcházející zápas nebo živé skóre HC Verva Litvínov. Flask server čte data z hokej.cz a ESP32 stahuje zkrácený třířádkový výstup.

## Struktura

```text
server.py          Flask scraper pro nasazení na Renderu
requirements.txt   Python závislosti serveru
main.py            MicroPython firmware pro ESP32
boot.py             MicroPython boot soubor
sh1106.py           ovladač OLED
config.py.example   šablona lokální Wi-Fi konfigurace
```

## Bezpečné nastavení Wi-Fi

Wi-Fi údaje nejsou součástí repozitáře.

1. Zkopíruj `config.py.example` na ESP32 jako `config.py`.
2. Doplň vlastní `WIFI_SSID` a `WIFI_PASS` pouze do `config.py`.
3. Nahraj na ESP32 `main.py`, `config.py` a potřebný ovladač OLED.

`config.py` je v `.gitignore`; nikdy ho nepřidávej do commitu ani na GitHub.

## Server

```bash
pip install -r requirements.txt
gunicorn server:app
```

Endpoint pro displej: `/litvinov`.
