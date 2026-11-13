import requests
import time
import os
from datetime import datetime

# === Налаштування ===
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
STREET_ID = 37319
CHECK_INTERVAL = 300  # 5 хвилин

API_ACCIDENTS = f"https://api-ztoe-poweron.inneti.net/api/pw_accidents?street.id={STREET_ID}&pagination=false"
API_PLANNED = f"https://api-ztoe-poweron.inneti.net/api/pw_accident_planeds?street.id={STREET_ID}&pagination=false"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; PowerOutageBot/1.0)",
    "Accept": "application/ld+json"
}

# Стан в пам'яті (не скидається під час роботи)
known_ids = set()
last_update_id = 0
initialized = False

def send_telegram(text, chat_id=None):
    if not TELEGRAM_TOKEN:
        return

    target = chat_id or CHAT_ID
    if not target:
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    for chat in str(target).split(","):
        try:
            requests.post(url, json={
                "chat_id": chat.strip(),
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True
            }, timeout=10)
        except Exception as e:
            print(f"Помилка відправки: {e}")

def format_outage(item, is_planned=False):
    start = item.get("dateEvent", "")[:16].replace("T", " ")
    end = item.get("datePlanIn", "")[:16].replace("T", " ")
    buildings = item.get("buildingNames", "—")
    otg = item.get("otg", {}).get("name", "")
    city = item.get("city", {}).get("name", "")
    street = item.get("street", {}).get("name", "")

    title = "📅 Планове відключення" if is_planned else "⚡ Аварійне відключення"

    return (
        f"{title}\n\n"
        f"📍 {city}, {street}\n"
        f"🏠 Будинки: <b>{buildings}</b>\n"
        f"🏢 {otg}\n\n"
        f"🕐 Початок: <b>{start}</b>\n"
        f"🕐 Кінець: <b>{end}</b>\n\n"
        f"<i>Дані з Житомиробленерго</i>"
    )

def get_outages(api_url):
    try:
        r = requests.get(api_url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        return r.json().get("hydra:member", [])
    except Exception as e:
        print(f"Помилка API: {e}")
        return []

def check_outages(notify=True):
    global known_ids, initialized

    accidents = get_outages(API_ACCIDENTS)
    planned = get_outages(API_PLANNED)

    current_ids = set()
    new_messages = []

    for item in accidents:
        oid = f"a_{item.get('id')}"
        current_ids.add(oid)
        if oid not in known_ids and notify and initialized:
            new_messages.append(format_outage(item, is_planned=False))

    for item in planned:
        oid = f"p_{item.get('id')}"
        current_ids.add(oid)
        if oid not in known_ids and notify and initialized:
            new_messages.append(format_outage(item, is_planned=True))

    # Надсилаємо тільки справді нові
    for msg in new_messages:
        send_telegram(msg)
        print("Надіслано нове сповіщення")

    # Якщо раніше були відключення, а зараз немає
    if known_ids and not current_ids and notify and initialized:
        send_telegram("✅ <b>Відключення знято</b>\n\nНа 2 пров. Івана Виговського зараз немає відключень.")

    known_ids = current_ids
    initialized = True

    print(f"[{datetime.now().strftime('%H:%M:%S')}] Аварійних: {len(accidents)}, Планових: {len(planned)}")
    return accidents, planned

def handle_commands():
    global last_update_id
    if not TELEGRAM_TOKEN:
        return

    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
        r = requests.get(url, params={"offset": last_update_id + 1, "timeout": 1}, timeout=5)
        data = r.json()

        if not data.get("ok"):
            return

        for update in data.get("result", []):
            last_update_id = update["update_id"]
            message = update.get("message")
            if not message:
                continue

            chat_id = message["chat"]["id"]
            text = message.get("text", "").strip().lower()

            if text in ["/start", "/help"]:
                send_telegram(
                    "🔌 <b>Бот моніторингу відключень</b>\n"
                    "📍 Малин, 2 пров. Івана Виговського\n\n"
                    "Команди:\n"
                    "/status — поточний стан\n"
                    "/check — перевірити зараз\n"
                    "/plan — планові відключення\n"
                    "/help — ця довідка",
                    chat_id=chat_id
                )

            elif text in ["/status", "/check"]:
                accidents, planned = check_outages(notify=False)
                if not accidents and not planned:
                    send_telegram("✅ Зараз відключень немає.", chat_id=chat_id)
                else:
                    for item in accidents:
                        send_telegram(format_outage(item, is_planned=False), chat_id=chat_id)
                    for item in planned:
                        send_telegram(format_outage(item, is_planned=True), chat_id=chat_id)

            elif text == "/plan":
                planned = get_outages(API_PLANNED)
                if not planned:
                    send_telegram("📅 Планових відключень зараз немає.", chat_id=chat_id)
                else:
                    for item in planned:
                        send_telegram(format_outage(item, is_planned=True), chat_id=chat_id)

    except Exception as e:
        print(f"Помилка команд: {e}")

if __name__ == "__main__":
    print("Бот запущено...")
    
    # При старті запам'ятовуємо поточні відключення (щоб не спамити)
    check_outages(notify=False)
    
    if TELEGRAM_TOKEN and CHAT_ID:
        send_telegram("🔌 Бот запущено\n📍 Малин, 2 пров. Івана Виговського\n\nТепер повідомлення приходитимуть тільки при появі нових відключень.")
    
    last_check = time.time()
    
    while True:
        handle_commands()
        
        now = time.time()
        if now - last_check >= CHECK_INTERVAL:
            check_outages(notify=True)
            last_check = now
        
        time.sleep(2)
