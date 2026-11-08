import os
import json
import asyncio
import urllib.parse
from collections import deque
import aiohttp
from aiohttp import web

BOT_TOKEN = os.environ.get("BOT_TOKEN", "9218204780:AAFnj7zZ6JcY90xXCVKzB-fcX2cHxE19_ss")
TARGET_CHANNEL_ID = os.environ.get("TARGET_CHANNEL_ID", "-1004468017163")
PORT = int(os.environ.get("PORT", "10000"))

HISTORY_FILE = "posted_pins.txt"

# 40+ High-Converting Viral Desi Dance, Saree, Bhabhi & Lookbook Keywords
SEED_KEYWORDS = [
    # Viral Dance & Thumka Moves
    "Desi hot dance reels",
    "Desi bhabhi viral dance reels",
    "Desi bhabhi room dance reels",
    "Desi girl belly dance saree",
    "Desi thumka dance saree reels",
    "Desi kamar dance reels",
    "Desi hot reel sound dance",

    # Low-Waist, Pallu & Saree Draping
    "Desi low waist saree draping reels",
    "Saree low waist thong aesthetic",
    "Desi saree pallu drop transition",
    "Desi transparent saree lookbook",
    "Desi saree backless dori reels",
    "Desi navel show saree reels",
    "Saree draping style bold reels",
    "Desi chiffon saree bold look",
    "Desi saree walk slowmo reels",

    # Curvy Figures, Blouse & Cleavage Styling
    "Desi hourglass figure saree transition",
    "Desi deep cleavage blouse reels",
    "Desi busty curvy aesthetic reels",
    "Desi deep neck blouse styling",
    "Desi curvy figure walk reels",
    "Desi backless choli bold reels",
    "Desi sleeveless blouse saree look",
    "Desi crop top backless choli reels",

    # Curvy Bhabhi & Mature Aesthetic
    "Desi curvy bhabhi saree reels",
    "Desi chubby bhabhi saree lookbook",
    "Desi aunty curvy saree reels",
    "Desi mature bhabhi styling reels",
    "Desi kaamwali saree aesthetic reels",
    "Desi bhabhi home styling reels",
    "Desi bhabhi night saree reels",

    # Lingerie, Nightwear & Bedroom Lookbooks
    "Desi bold bedroom lookbook haul",
    "Desi lingerie try on haul reels",
    "Desi bikini lookbook haul reels",
    "Desi satin nighty bold reels",
    "Desi mini dress clubbing baddie",
    "Desi crop top low waist dance",
    "Desi towel transition reels",
    "Desi gym baddie tight outfit",
    "College farewell bold saree look",
    "Desi salwar suit backless styling"
]

def load_posted():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r") as f:
            return set(line.strip() for line in f if line.strip())
    return set()

def save_posted(pin_id):
    with open(HISTORY_FILE, "a") as f:
        f.write(f"{pin_id}\n")

def get_csrf(session: aiohttp.ClientSession) -> str:
    for c in session.cookie_jar:
        if c.key == "csrftoken":
            return c.value
    return ""

def extract_video_and_thumb(pin):
    """MP4 Video (>=8s) + Cover Image extractor"""
    raw_duration = None
    if "videos" in pin and isinstance(pin["videos"], dict):
        raw_duration = pin["videos"].get("duration")

    found_videos = []
    thumb_url = None

    images = pin.get("images", {})
    for res in ["736x", "orig", "474x", "170x"]:
        if res in images and isinstance(images[res], dict) and images[res].get("url"):
            thumb_url = images[res]["url"]
            break

    def find_video_lists(obj):
        if isinstance(obj, dict):
            if "video_list" in obj and isinstance(obj["video_list"], dict):
                found_videos.append(obj["video_list"])
            for v in obj.values():
                find_video_lists(v)
        elif isinstance(obj, list):
            for item in obj:
                find_video_lists(item)

    find_video_lists(pin)

    for v_list in found_videos:
        best_url = None
        for q in ["V_720P", "V_EXP7", "V_480P", "V_EXP6", "V_EXP5"]:
            if q in v_list and isinstance(v_list[q], dict):
                u = v_list[q].get("url")
                if u and ".mp4" in u:
                    best_url = u
                    if not raw_duration and v_list[q].get("duration"):
                        raw_duration = v_list[q].get("duration")
                    if not thumb_url and v_list[q].get("thumbnail"):
                        thumb_url = v_list[q]["thumbnail"]
                    break
        
        if best_url:
            # Strictly Filter: Minimum 8 Seconds
            if raw_duration:
                try:
                    dur = float(raw_duration)
                    if dur > 500:
                        dur = dur / 1000.0
                    if dur < 8.0:
                        return None, None, None
                except Exception:
                    pass

            title = pin.get("title") or pin.get("grid_title") or "Viral Desi Reel"
            return best_url, thumb_url, title

    return None, None, None

async def fetch_search_pins(session: aiohttp.ClientSession, keyword: str):
    csrf = get_csrf(session)
    source_url = f"/search/pins/?q={urllib.parse.quote(keyword)}"
    params = {
        "source_url": source_url,
        "data": json.dumps({
            "options": {"query": keyword, "scope": "pins", "page_size": 60},
            "context": {}
        })
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Accept": "application/json, text/javascript, */*, q=0.01",
        "X-Requested-With": "XMLHttpRequest",
        "X-Pinterest-AppState": "active",
        "X-Pinterest-PWS-Handler": "www/search/[scope].js",
        "X-CSRFToken": csrf,
        "Referer": f"https://www.pinterest.com{source_url}",
        "Origin": "https://www.pinterest.com"
    }

    url = "https://www.pinterest.com/resource/BaseSearchResource/get/"
    try:
        async with session.get(url, params=params, headers=headers, timeout=25) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get("resource_response", {}).get("data", {}).get("results", [])
    except Exception as e:
        print(f"⚠️ Search error for '{keyword}': {e}", flush=True)
    return []

async def fetch_related_pins(session: aiohttp.ClientSession, pin_id: str):
    csrf = get_csrf(session)
    source_url = f"/pin/{pin_id}/"
    params = {
        "source_url": source_url,
        "data": json.dumps({
            "options": {"pin_id": str(pin_id), "page_size": 50},
            "context": {}
        })
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Accept": "application/json, text/javascript, */*, q=0.01",
        "X-Requested-With": "XMLHttpRequest",
        "X-Pinterest-AppState": "active",
        "X-Pinterest-PWS-Handler": "www/pin/[id].js",
        "X-CSRFToken": csrf,
        "Referer": f"https://www.pinterest.com{source_url}",
        "Origin": "https://www.pinterest.com"
    }

    url = "https://www.pinterest.com/resource/RelatedPinFeedResource/get/"
    try:
        async with session.get(url, params=params, headers=headers, timeout=25) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get("resource_response", {}).get("data", {}).get("results", [])
    except Exception as e:
        print(f"⚠️ Related fetch error for Pin {pin_id}: {e}", flush=True)
    return []

async def download_file(session: aiohttp.ClientSession, url: str, filename: str, min_size: int = 1000) -> bool:
    try:
        async with session.get(url, timeout=35) as resp:
            if resp.status == 200:
                with open(filename, "wb") as f:
                    f.write(await resp.read())
                return os.path.exists(filename) and os.path.getsize(filename) > min_size
    except Exception as e:
        print(f"⚠️ Download failed: {e}", flush=True)
    return False

async def send_to_telegram(session: aiohttp.ClientSession, video_path: str, thumb_path: str, caption: str) -> bool:
    telegram_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendVideo"
    try:
        data = aiohttp.FormData()
        data.add_field("chat_id", str(TARGET_CHANNEL_ID))
        data.add_field("caption", caption)
        data.add_field("parse_mode", "HTML")
        data.add_field("supports_streaming", "true")
        data.add_field(
            "video",
            open(video_path, "rb"),
            filename=os.path.basename(video_path),
            content_type="video/mp4"
        )
        if thumb_path and os.path.exists(thumb_path):
            data.add_field(
                "thumbnail",
                open(thumb_path, "rb"),
                filename="thumb.jpg",
                content_type="image/jpeg"
            )

        async with session.post(telegram_url, data=data, timeout=120) as resp:
            res = await resp.json()
            return res.get("ok", False)
    except Exception as e:
        print(f"⚠️ Telegram upload error: {e}", flush=True)
        return False

# Shared Producer-Consumer Async Queue
video_queue = asyncio.Queue(maxsize=120)
spider_history_set = set()

async def producer_spider(session: aiohttp.ClientSession):
    """24x7 Non-stop Harvester: Ensures the queue never runs out of videos"""
    posted = load_posted()
    spider_history_set.update(posted)

    print("🟢 Producer Spider Engine Started!", flush=True)

    while True:
        for kw in SEED_KEYWORDS:
            # Queue bhar gaya ho toh hold karein, khaali hone par instant refill
            if video_queue.qsize() > 80:
                await asyncio.sleep(5)
                continue

            pins = await fetch_search_pins(session, kw)
            for p in pins:
                pid = str(p.get("id"))
                if pid and pid not in spider_history_set:
                    spider_history_set.add(pid)
                    v_url, t_url, title = extract_video_and_thumb(p)
                    if v_url:
                        await video_queue.put({
                            "id": pid,
                            "video_url": v_url,
                            "thumb_url": t_url,
                            "title": title
                        })

                        # Har valid video pin se related recommendations crawl karein
                        related = await fetch_related_pins(session, pid)
                        for rp in related:
                            r_id = str(rp.get("id"))
                            if r_id and r_id not in spider_history_set:
                                spider_history_set.add(r_id)
                                rv_url, rt_url, r_title = extract_video_and_thumb(rp)
                                if rv_url:
                                    await video_queue.put({
                                        "id": r_id,
                                        "video_url": rv_url,
                                        "thumb_url": rt_url,
                                        "title": r_title
                                    })

            await asyncio.sleep(1.5)

async def consumer_uploader(session: aiohttp.ClientSession):
    """Maximum Speed Uploader: Consumes queue items at Telegram's fastest safe limit"""
    posted = load_posted()
    print("🟢 Consumer Uploader Engine Started!", flush=True)

    while True:
        item = await video_queue.get()
        pid = item["id"]

        if pid in posted:
            video_queue.task_done()
            continue

        temp_video = f"pin_{pid}.mp4"
        temp_thumb = f"thumb_{pid}.jpg"

        v_ok = await download_file(session, item["video_url"], temp_video, min_size=80000)
        t_ok = False
        if item.get("thumb_url"):
            t_ok = await download_file(session, item["thumb_url"], temp_thumb, min_size=2000)

        if v_ok:
            caption = (
                f"✨ <b>{item['title'][:65]}</b>\n\n"
                f"🔥 <b>#ViralDance #DesiBaddie #HotReels #Saree</b>\n"
                f"👑 <b>Join:</b> @InstagramPremiumCollection"
            )

            uploaded = await send_to_telegram(session, temp_video, temp_thumb if t_ok else None, caption)
            if uploaded:
                print(f"🚀 [Speed Delivery] Pin {pid} Posted to Channel! (Queue remaining: {video_queue.qsize()})", flush=True)
                save_posted(pid)
                posted.add(pid)

        # Cleanup disk
        if os.path.exists(temp_video):
            os.remove(temp_video)
        if os.path.exists(temp_thumb):
            os.remove(temp_thumb)

        video_queue.task_done()

        # Maximum speed: 1.5 seconds between uploads (avoids Telegram 429 FloodWait)
        await asyncio.sleep(1.5)

async def handle_ping(request):
    return web.Response(text="24x7 Ultra-Speed Engine Active!")

async def start_app():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    print(f"🌐 Keep-Alive Server active on {PORT}", flush=True)

    async with aiohttp.ClientSession() as session:
        try:
            await session.get("https://www.pinterest.com/", timeout=15)
        except Exception:
            pass

        # Producer & Consumer running concurrently in background
        await asyncio.gather(
            producer_spider(session),
            consumer_uploader(session)
        )

if __name__ == "__main__":
    asyncio.run(start_app())
