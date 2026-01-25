# HutWatch

BLE-lämpötilaseuranta Telegram-botilla. Lukee lämpötiladataa RuuviTag- ja Xiaomi LYWSD03MMC -antureista ja lähettää tiedot Telegramiin.

## Ominaisuudet

- RuuviTag (Data Format 3/5) tuki
- Xiaomi LYWSD03MMC (ATC/PVVX custom firmware) tuki
- Telegram-komennot: `/temps`, `/status`, `/history`
- Ajastetut raportit (oletus 1h välein)
- 24h historia
- Systemd-palvelu

## Vaatimukset

- Python 3.8+
- Bluetooth-adapteri
- Linux (testattu Ubuntu 20.04)

## Asennus

```bash
# Kloonaa repo
git clone https://github.com/YOUR_USERNAME/hutwatch.git
cd hutwatch

# Asenna riippuvuudet
pip3 install -r requirements.txt

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
```

### Telegram-botin luonti

1. Avaa Telegram ja etsi `@BotFather`
2. Lähetä `/newbot` ja seuraa ohjeita
3. Kopioi token config.yaml-tiedostoon

### Chat ID:n hakeminen

1. Lähetä viesti botillesi Telegramissa
2. Aja:
```bash
python3 -c "
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
python3 -c "
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

## Käyttö

### Manuaalinen käynnistys

```bash
python3 -m hutwatch -c config.yaml -v
```

### Systemd-palvelu

```bash
# Muokkaa polut hutwatch.service-tiedostossa
sudo cp hutwatch.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now hutwatch

# Tarkista tila
sudo systemctl status hutwatch

# Lokit
journalctl -u hutwatch -f
```

## Telegram-komennot

| Komento | Kuvaus |
|---------|--------|
| `/temps` | Kaikkien anturien lämpötilat |
| `/status` | Järjestelmän tila, signaalivoimakkuudet |
| `/history` | Lämpötilahistoria (6h oletus) |
| `/history 12` | 12 tunnin historia |
| `/history Ulkona 24` | Tietyn anturin 24h historia |
| `/help` | Ohje |

## Vinkki: AI-avusteinen konfigurointi

Telegram-botin luonti, chat ID:n hakeminen ja anturien etsiminen onnistuu helposti myös AI-apurin avulla. Esimerkiksi [Claude Code](https://claude.ai/download) osaa:

- Skannata BLE-laitteet ja tunnistaa anturit automaattisesti
- Hakea Telegram chat ID:n puolestasi
- Generoida config.yaml-tiedoston löydetyillä antureilla
- Asentaa ja käynnistää palvelun

Kerro vain mitä haluat tehdä, niin AI hoitaa loput. :)

## Xiaomi-anturin firmware

Xiaomi LYWSD03MMC vaatii custom firmwaren BLE-mainosten lähettämiseen:

- [ATC firmware](https://github.com/atc1441/ATC_MiThermometer)
- [PVVX firmware](https://github.com/pvvx/ATC_MiThermometer)

Flashaus onnistuu selaimella: https://pvvx.github.io/ATC_MiThermometer/TelinkMiFlasher.html

## Lisenssi

MIT
