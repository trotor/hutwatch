# HutWatch

BLE-lämpötilaseuranta Telegram-botilla. Lukee lämpötiladataa RuuviTag- ja Xiaomi LYWSD03MMC -antureista, hakee ulkosään yr.no:sta ja lähettää tiedot Telegramiin.

## Ominaisuudet

- RuuviTag (Data Format 3/5) tuki
- Xiaomi LYWSD03MMC (ATC/PVVX custom firmware) tuki
- Ulkosää MET Norway API:sta (yr.no)
- Telegram-komennot: `/temps`, `/weather`, `/history`, `/stats`, `/graph`
- Interaktiivinen valikko inline-napeilla (`/menu`)
- Ajastetut raportit (oletus 1h välein)
- SQLite-tietokanta pitkäaikaishistorialle
- 24h muistivälimuisti + 90 päivän tietokantahistoria
- Systemd-palvelu

## Vaatimukset

- Python 3.10+
- Bluetooth-adapteri (BLE-tuki)
- Linux (testattu Ubuntu 20.04/22.04)

## Asennus

```bash
# Kloonaa repo
git clone https://github.com/trotor/hutwatch.git
cd hutwatch

# Luo virtuaaliympäristö ja asenna riippuvuudet
python3 -m venv venv
./venv/bin/pip install -r requirements.txt

# Kopioi ja muokkaa konfiguraatio
cp config.example.yaml config.yaml
nano config.yaml
```

## Konfiguraatio

Muokkaa `config.yaml`:

```yaml
sensors:
  - mac: "AA:BB:CC:DD:EE:FF"
    name: "Ulkona"
    type: ruuvi
  - mac: "11:22:33:44:55:66"
    name: "Sisällä"
    type: xiaomi

telegram:
  token: "YOUR_BOT_TOKEN"
  chat_id: YOUR_CHAT_ID
  report_interval: 3600

# Ulkosää yr.no:sta (valinnainen)
weather:
  latitude: 60.1699
  longitude: 24.9384
  location_name: "Helsinki"
```

### Telegram-botin luonti

1. Avaa Telegram ja etsi `@BotFather`
2. Lähetä `/newbot` ja seuraa ohjeita
3. Kopioi token config.yaml-tiedostoon

### Chat ID:n hakeminen

1. Lähetä viesti botillesi Telegramissa
2. Aja:
```bash
./venv/bin/python -c "
import asyncio
from telegram import Bot
bot = Bot('YOUR_TOKEN')
updates = asyncio.run(bot.get_updates())
for u in updates:
    if u.message:
        print(f'chat_id: {u.message.chat.id}')
"
```

### Anturien MAC-osoitteiden etsiminen

```bash
./venv/bin/python -c "
import asyncio
from bleak import BleakScanner

async def scan():
    devices = await BleakScanner.discover(timeout=10, return_adv=True)
    for addr, (dev, adv) in devices.items():
        if 'Ruuvi' in (dev.name or '') or 'ATC' in (dev.name or ''):
            print(f'{addr}: {dev.name}')

asyncio.run(scan())
"
```

### Koordinaattien etsiminen säälle

Hae koordinaatit esim. [latlong.net](https://www.latlong.net/) -palvelusta.

## Käyttö

### Manuaalinen käynnistys

```bash
./venv/bin/python -m hutwatch -c config.yaml -v
```

### Systemd-palvelu

```bash
# Muokkaa polut hutwatch.service-tiedostossa tarvittaessa
sudo cp hutwatch.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now hutwatch

# Tarkista tila
sudo systemctl status hutwatch

# Lokit
sudo journalctl -u hutwatch -f
```

## Telegram-komennot

### Peruskomennot

| Komento | Kuvaus |
|---------|--------|
| `/menu` | Interaktiivinen valikko napeilla |
| `/temps` | Kaikkien anturien lämpötilat + sää |
| `/weather` | Yksityiskohtainen säätila |
| `/status` | Järjestelmän tila |
| `/help` | Ohje |

### Historia ja tilastot

| Komento | Kuvaus |
|---------|--------|
| `/history` | Lämpötilahistoria (6h oletus) |
| `/history 24h` | 24 tunnin historia |
| `/history 7d` | 7 päivän historia |
| `/stats 1d` | Päivän tilastot (min/max/avg) |
| `/graph 1 24h` | ASCII-graafi anturille 1 |
| `/graph sää 48h` | Sään lämpötilagraafi |

### Laitteiden hallinta

| Komento | Kuvaus |
|---------|--------|
| `/devices` | Listaa laitteet numeroineen |
| `/rename 1 Olohuone` | Nimeä laite 1 uudelleen |
| `/report on/off` | Ajastetut raportit päälle/pois |

## Interaktiivinen valikko

Komento `/menu` tai `/start` avaa interaktiivisen valikon inline-napeilla:

- Lämpötilat ja sää yhdellä napilla
- Historia 1d / 7d / 30d
- Tilastot 1d / 7d / 30d
- Päivitä-nappi jokaisessa näkymässä

## Vinkki: AI-avusteinen konfigurointi

Telegram-botin luonti, chat ID:n hakeminen ja anturien etsiminen onnistuu helposti myös AI-apurin avulla. Esimerkiksi [Claude Code](https://claude.ai/download) osaa:

- Skannata BLE-laitteet ja tunnistaa anturit automaattisesti
- Hakea Telegram chat ID:n puolestasi
- Generoida config.yaml-tiedoston löydetyillä antureilla
- Asentaa ja käynnistää palvelun

Kerro vain mitä haluat tehdä, niin AI hoitaa loput.

## Xiaomi-anturin firmware

Xiaomi LYWSD03MMC vaatii custom firmwaren BLE-mainosten lähettämiseen:

- [ATC firmware](https://github.com/atc1441/ATC_MiThermometer)
- [PVVX firmware](https://github.com/pvvx/ATC_MiThermometer)

Flashaus onnistuu selaimella: https://pvvx.github.io/ATC_MiThermometer/TelinkMiFlasher.html

## Lisenssi

MIT
