import requests
import time
import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
STREET_ID = 37319
CHECK_INTERVAL = 300
PORT = int(os.environ.get("PORT", 8080))

API_ACCIDENTS = f"https://api-ztoe-poweron.inneti.net/api/pw_accidents?street.id={STREET_ID}&pagination=false"
API_PLANNED = f"https://api-ztoe-poweron.inneti.net/api/pw_accident_planeds?street.id={STREET_ID}&pagination=false"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; PowerOutageBot/1.0)",
    "Accept": "application/ld+json"
}

known_signatures = set()
last_update_id = 0
is_first_run = True

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
    def log_message(self, format, *args):
        return  # щоб не засмічувати логи

def start_health_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    print(f"Health server on port {PORT}")
    server.serve_forever()

def send_telegram(text, chat_id=None):
    if not TELEGRAM_TOKEN or not (chat_id or CHAT_ID):
        return
    target = chat_id or CHAT_ID
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

def make_signature(item, is_planned=False):
    start = item.get("dateEvent", "")[:16]
    buildings = item.get("buildingNames", "")
    prefix = "p" if is_planned else "a"
    return f"{prefix}|{start}|{buildings}"

def format_outage(item, is_planned=False):
    start = item.get("dateEvent", "")[:16].replace("T", " ")
    end = item.get("datePlanIn", "")[:16].replace("T", " ")
    buildings = item.get("buildingNames", "—")
    city = item.get("city", {}).get("name", "")
    street = item.get("street", {}).get("name", "")
    otg = item.get("otg", {}).get("name", "")
    title = "📅 Планове відключення" if is_planned else "⚡ Аварійне відключення"
    return (
        f"{title}\n\n"
        f"📍 {city}, {street}\n"
        f"🏠 Будинки: <b>{buildings}</b>\n"
        f"🏢 {otg}\n\n"
        f"🕐 Початок: <b>{start}</b>\n"
        f"🕐 Кінець: <b>{end}</b>"
    )

def get_outages(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        return r.json().get("hydra:member", [])
    except Exception as e:
        print(f"Помилка API: {e}")
        return []

def check_outages(notify=True):
    global known_signatures, is_first_run

    accidents = get_outages(API_ACCIDENTS)
    planned = get_outages(API_PLANNED)

    current_signatures = set()
    new_messages = []

    for item in accidents:
        sig = make_signature(item, False)
        current_signatures.add(sig)
        if sig not in known_signatures and notify and not is_first_run:
            new_messages.append(format_outage(item, False))

    for item in planned:
        sig = make_signature(item, True)
        current_signatures.add(sig)
        if sig not in known_signatures and notify and not is_first_run:
            new_messages.append(format_outage(item, True))

    for msg in new_messages:
        send_telegram(msg)
        print(">>> Надіслано НОВЕ сповіщення")

    if known_signatures and not current_signatures and notify and not is_first_run:
        send_telegram("✅ <b>Відключення знято</b>\n\nНа 2 пров. Івана Виговського зараз немає відключень.")

    print(f"[{datetime.now().strftime('%H:%M:%S')}] Відомих: {len(known_signatures)} → Поточних: {len(current_signatures)} | Нових: {len(new_messages)}")
    
    known_signatures = current_signatures
    is_first_run = False
    return accidents, planned

def handle_commands():
    global last_update_id
    if not TELEGRAM_TOKEN:
        return
    try:
        r = requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates",
                         params={"offset": last_update_id + 1, "timeout": 1}, timeout=5)
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
                send_telegram("🔌 <b>Бот моніторингу</b>\n📍 Малин, 2 пров. Івана Виговського\n\n/status — стан\n/check — перевірити\n/plan — планові", chat_id=chat_id)
            elif text in ["/status", "/check"]:
                accidents, planned = check_outages(notify=False)
                if not accidents and not planned:
                    send_telegram("✅ Зараз відключень немає.", chat_id=chat_id)
                else:
                    for item in accidents:
                        send_telegram(format_outage(item, False), chat_id=chat_id)
                    for item in planned:
                        send_telegram(format_outage(item, True), chat_id=chat_id)
            elif text == "/plan":
                planned = get_outages(API_PLANNED)
                if not planned:
                    send_telegram("📅 Планових немає.", chat_id=chat_id)
                else:
                    for item in planned:
                        send_telegram(format_outage(item, True), chat_id=chat_id)
    except Exception as e:
        print(f"Помилка команд: {e}")

if __name__ == "__main__":
    print("Бот запущено...")
    
    # Запускаємо health-сервер у фоні
    threading.Thread(target=start_health_server, daemon=True).start()
    
    check_outages(notify=False)
    
    if TELEGRAM_TOKEN and CHAT_ID:
        send_telegram("🔌 Бот стабільно запущено\nПовідомлення тільки при змінах.")

    last_check = time.time()
    while True:
        handle_commands()
        if time.time() - last_check >= CHECK_INTERVAL:
            check_outages(notify=True)
            last_check = time.time()
        time.sleep(2)