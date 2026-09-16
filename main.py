from machine import I2C, Pin, PWM
import network
import ssd1306
import time
import urequests

# Wi-Fi údaje jsou pouze v lokálním config.py (soubor není v GitHubu).
# Zkopíruj config.py.example jako config.py a doplň vlastní hodnoty.
try:
    from config import WIFI_SSID, WIFI_PASS
except ImportError:
    WIFI_SSID = ""
    WIFI_PASS = ""

# --- NASTAVENÍ PINOVÉHO ZAPOJENÍ ---
# OLED displej (SDA=8, SCL=9)
i2c = I2C(0, scl=Pin(9), sda=Pin(8))
oled = ssd1306.SSD1306_I2C(128, 64, i2c)

# Bzučák / Buzzer (např. na pinu 4, druhý pin do GND)
BUZZER_PIN = 4
SERVER_URL = "https://litvinov-server.onrender.com/litvinov"

# Paměť pro detekci změny prostředního řádku (začátek zápasu)
predchozi_radek2 = ""


def pripoj_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

    if not WIFI_SSID or not WIFI_PASS:
        oled.fill(0)
        oled.text("Chybi config.py", 0, 0)
        oled.show()
        return False

    if not wlan.isconnected():
        oled.fill(0)
        oled.text("Pripojuji WiFi...", 0, 0)
        oled.show()
        wlan.connect(WIFI_SSID, WIFI_PASS)

        # Čekáme na připojení (timeout 15 sekund)
        pokusy = 0
        while not wlan.isconnected() and pokusy < 15:
            time.sleep(1)
            pokusy += 1

    if wlan.isconnected():
        oled.fill(0)
        oled.text("WiFi OK!", 0, 0)
        oled.show()
        time.sleep(1)
        return True

    oled.fill(0)
    oled.text("Chyba WiFi!", 0, 0)
    oled.show()
    return False


def spust_znelku_zapasu():
    print("ZAPAS ZACAL! Hraji litvinovskou znelku...")
    buzzer = PWM(Pin(BUZZER_PIN))
    melodie = [
        (523, 200), (523, 200), (659, 400),
        (784, 400), (659, 200), (523, 400),
        (587, 200), (659, 200), (587, 400),
        (523, 600)
    ]

    for note, duration in melodie:
        if note > 0:
            buzzer.duty(512)
            buzzer.freq(note)
        else:
            buzzer.duty(0)
        time.sleep_ms(duration)
        buzzer.duty(0)
        time.sleep_ms(50)

    buzzer.deinit()


if pripoj_wifi():
    while True:
        response = None
        try:
            wlan = network.WLAN(network.STA_IF)
            if wlan.isconnected():
                response = urequests.get(SERVER_URL)

                if response.status_code == 200:
                    data = response.text
                    radky = data.split("\n")
                    oled.fill(0)
                    radek_y = 0
                    for radek in radky:
                        oled.text(radek, 0, radek_y)
                        radek_y += 16
                    oled.show()

                    if len(radky) >= 2:
                        aktualni_radek2 = radky[1]
                        if predchozi_radek2 != "" and predchozi_radek2 != aktualni_radek2:
                            if ":" in aktualni_radek2 and "." not in aktualni_radek2:
                                spust_znelku_zapasu()
                        predchozi_radek2 = aktualni_radek2
                else:
                    oled.fill(0)
                    oled.text("Chyba serveru", 0, 0)
                    oled.show()
            else:
                oled.fill(0)
                oled.text("Ztracena WiFi!", 0, 0)
                oled.show()
        except Exception as e:
            print("Chyba stahovani:", e)
            oled.fill(0)
            oled.text("Chyba stahovani", 0, 0)
            oled.show()
        finally:
            if response is not None:
                response.close()

        time.sleep(30)
