import requests
import time
import json
import os
from datetime import datetime

# === Налаштування з Railway Variables ===
TELEGRAM_TOKEN = os.environ.get("9125931506:AAFkp0ipNVLPvW6LzwsKqVFEVBUqYAxL1cc")
CHAT_ID = os.environ.get("9125931506")
STREET_ID = 37319                 # 2 пров. Івана Виговського
CHECK_INTERVAL = 300              # 5 хвилин

STATE_FILE = "last_outages.json"
API_URL = f"https://api-ztoe-poweron.inneti.net/api/pw_accidents?street.id={STREET_ID}&pagination=false"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; PowerOutageBot/1.0)",
    "Accept": "application/ld+json"
}

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except:
            return set()
    return set()

def save_state(ids):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(list(ids), f)

def send_telegram(text):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("Помилка: не задані TELEGRAM_TOKEN або CHAT_ID")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    for chat in str(CHAT_ID).split(","):
        try:
            requests.post(url, json={
                "chat_id": chat.strip(),
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True
            }, timeout=10)
        except Exception as e:
            print(f"Помилка відправки: {e}")

def format_outage(item):
    start = item.get("dateEvent", "")[:16].replace("T", " ")
    end = item.get("datePlanIn", "")[:16].replace("T", " ")
    buildings = item.get("buildingNames", "—")
    otg = item.get("otg", {}).get("name", "")
    city = item.get("city", {}).get("name", "")
    street = item.get("street", {}).get("name", "")

    return (
        f"⚡ <b>Аварійне відключення</b>\n\n"
        f"📍 {city}, {street}\n"
        f"🏠 Будинки: <b>{buildings}</b>\n"
        f"🏢 {otg}\n\n"
        f"🕐 Початок: <b>{start}</b>\n"
        f"🕐 Очікуване відновлення: <b>{end}</b>\n\n"
        f"<i>Дані з Житомиробленерго</i>"
    )

def check_outages():
    try:
        r = requests.get(API_URL, headers=HEADERS, timeout=15)
        r.raise_for_status()
        data = r.json()
        members = data.get("hydra:member", [])
    except Exception as e:
        print(f"Помилка API: {e}")
        return

    known = load_state()
    current_ids = set()
    new_messages = []

    for item in members:
        oid = str(item.get("id"))
        current_ids.add(oid)
        if oid not in known:
            new_messages.append(format_outage(item))

    for msg in new_messages:
        send_telegram(msg)
        print(f"Надіслано: {msg[:60]}...")

    if known and not current_ids:
        send_telegram("✅ <b>Відключення знято</b>\n\nНа 2 пров. Івана Виговського (Малин) зараз немає аварійних відключень.")

    save_state(current_ids)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Перевірено. Активних: {len(current_ids)}")

if __name__ == "__main__":
    print("Бот запущено...")
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("ПОМИЛКА: Встанови TELEGRAM_TOKEN і CHAT_ID у Variables на Railway!")
    else:
        send_telegram("🔌 Бот моніторингу відключень запущено\n📍 Малин, 2 пров. Івана Виговського")
    
    while True:
        check_outages()
        time.sleep(CHECK_INTERVAL)
