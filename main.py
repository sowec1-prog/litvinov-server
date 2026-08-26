from machine import I2C, Pin, PWM
import network
import ssd1306
import time
import urequests

# --- NASTAVENÍ PINOVÉHO ZAPOJENÍ ---
# OLED displej (SDA=8, SCL=9)
i2c = I2C(0, scl=Pin(9), sda=Pin(8))
oled = ssd1306.SSD1306_I2C(128, 64, i2c)

# Bzučák / Buzzer (např. na pinu 15, druhý pin do GND)
BUZZER_PIN = 4

# --- TVÉ ÚDAJE ---
WIFI_SSID = "Vodafone-2g"
WIFI_PASS = "Stehlikova11"
SERVER_URL = "https://litvinov-server.onrender.com/litvinov"
# ----------------

# Paměť pro detekci změny prostředního řádku (začátek zápasu)
predchozi_radek2 = ""


def pripoj_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

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
    else:
        oled.fill(0)
        oled.text("Chyba WiFi!", 0, 0)
        oled.show()
        return False


def spust_znelku_zapasu():
    print("ZAPAS ZACAL! Hraji litvinovskou znelku...")
    
    # Inicializace PWM pro bzučák
    buzzer = PWM(Pin(BUZZER_PIN))
    
    # Melodie (frekvence v Hz, trvání v milisekundách)
    melodie = [
        (523, 200), (523, 200), (659, 400), # C5, C5, E5
        (784, 400), (659, 200), (523, 400), # G5, E5, C5
        (587, 200), (659, 200), (587, 400), # D5, E5, D5
        (523, 600)                          # C5
    ]
    
    for note, duration in melodie:
        if note > 0:
            buzzer.duty(512) # Hlasitost (50%)
            buzzer.freq(note)
        else:
            buzzer.duty(0)   # Ticho
            
        time.sleep_ms(duration)
        buzzer.duty(0)       # Krátká pauza mezi tóny
        time.sleep_ms(50)
        
    buzzer.deinit() # Vypnutí PWM po dohrání


# --- HLAVNÍ SPOUŠTĚNÍ PO STARTU ---
if pripoj_wifi():
    while True:
        try:
            # Kontrola, zda Wi-Fi stále žije
            wlan = network.WLAN(network.STA_IF)
            if wlan.isconnected():
                # Stažení dat z tvého cloudu
                response = urequests.get(SERVER_URL)

                if response.status_code == 200:
                    data = response.text
                    radky = data.split("\n")

                    # Vyčistíme displej a vypíšeme řádky z cloudu
                    oled.fill(0)
                    radek_y = 0
                    for radek in radky:
                        oled.text(radek, 0, radek_y)
                        radek_y += 16  # Posun na další řádek
                    oled.show()

                    # KONTROLA ZAČÁTKU ZÁPASU (pokud máme alespoň 2 řádky)
                    if len(radky) >= 2:
                        aktualni_radek2 = radky[1] # Prostřední řádek (čas / skóre)
                        
                        # Pokud se prostřední řádek liší od minulé kontroly a už tam není datum (datum obsahuje tečku '.')
                        if predchozi_radek2 != "" and predchozi_radek2 != aktualni_radek2:
                            if ":" in aktualni_radek2 and "." not in aktualni_radek2:
                                spust_znelku_zapasu()
                                
                        predchozi_radek2 = aktualni_radek2

                else:
                    oled.fill(0)
                    oled.text("Chyba serveru", 0, 0)
                    oled.show()

                response.close()
            else:
                oled.fill(0)
                oled.text("Ztracena WiFi!", 0, 0)
                oled.show()

        except Exception as e:
            oled.fill(0)
            oled.text("Chyba stahovani", 0, 0)
            oled.show()

        # Opakovat stahování každých 30 sekund
        time.sleep(30)