import os
import re
import json
import random
import asyncio
import urllib.parse
import aiohttp
from aiohttp import web
import instaloader

BOT_TOKEN = os.environ.get("BOT_TOKEN", "9218204780:AAFnj7zZ6JcY90xXCVKzB-fcX2cHxE19_ss")
TARGET_CHANNEL_ID = os.environ.get("TARGET_CHANNEL_ID", "-1004468017163")
PORT = int(os.environ.get("PORT", "10000"))
INSTA_SESSION_ID = os.environ.get("INSTA_SESSION_ID", "")

# Persistent History Files (Anti-Duplicate Guarantee)
PIN_HISTORY_FILE = "posted_pins.txt"
STREAM_HISTORY_FILE = "posted_streams.txt"
INSTA_HISTORY_FILE = "posted_insta.txt"

TARGET_INSTA_ACCOUNTS = [
    "ur_wildcat",
    "mayaa_russian",
    "_sofi_russian"
]

SEED_KEYWORDS = [
    "backless baddie",
    "backless baddie reels",
    "desi backless dori blouse reels",
    "backless saree aesthetic reels",
    "desi deep backless choli",
    "backless halter neck reels",
    "desi saree backless walk reels",
    "waist chain aesthetic reels",
    "belly chain baddie reels",
    "desi low waist saree draping reels",
    "saree low waist thong aesthetic",
    "desi navel show saree reels",
    "desi saree pallu drop transition",
    "desi transparent saree lookbook",
    "bodycon mini dress baddie reels",
    "desi tight dress transition reels",
    "desi bold bedroom lookbook haul",
    "desi satin nighty bold reels",
    "desi lingerie try on haul reels",
    "desi bikini lookbook haul reels",
    "gym baddie workout reels",
    "gym tight outfit reels",
    "desi hot dance reels",
    "desi bhabhi room dance reels",
    "desi thumka dance saree reels",
    "desi kamar dance reels",
    "desi hourglass figure saree transition",
    "desi deep cleavage blouse reels",
    "desi busty curvy aesthetic reels",
    "desi curvy figure walk reels",
    "desi bhabhi viral dance reels",
    "desi chubby bhabhi saree lookbook"
]

def load_history(filepath):
    if os.path.exists(filepath):
        with open(filepath, "r") as f:
            return set(line.strip() for line in f if line.strip())
    return set()

def append_history(filepath, item):
    with open(filepath, "a") as f:
        f.write(f"{item}\n")

def extract_stream_signature(url: str) -> str:
    match = re.search(r"/([^/?#]+\.mp4)", url)
    if match:
        return match.group(1)
    return url.split("?")[0][-40:]

def get_csrf(session: aiohttp.ClientSession) -> str:
    for c in session.cookie_jar:
        if c.key == "csrftoken":
            return c.value
    return ""

def init_instaloader():
    # max_connection_attempts=1 se instaloader 660 second freeze nahi karega
    L = instaloader.Instaloader(
        download_pictures=False,
        download_videos=False,
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        compress_json=False,
        max_connection_attempts=1
    )
    if INSTA_SESSION_ID:
        L.context._session.cookies.set("sessionid", INSTA_SESSION_ID, domain=".instagram.com")
        print("🔑 Instagram Session Cookie Loaded!", flush=True)
    return L

def extract_video_and_thumb(pin):
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
    if not found_videos:
        return None, None, None

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
            if raw_duration:
                try:
                    dur = float(raw_duration)
                    if dur > 500:
                        dur = dur / 1000.0
                    if dur < 8.0:
                        return None, None, None
                except Exception:
                    pass

            title = pin.get("title") or pin.get("grid_title") or "Viral Baddie Reel"
            return best_url, thumb_url, title

    return None, None, None

async def fetch_pinterest_search(session: aiohttp.ClientSession, keyword: str, bookmark: str = None):
    csrf = get_csrf(session)
    source_url = f"/search/pins/?q={urllib.parse.quote(keyword)}"
    options = {"query": keyword, "scope": "pins", "page_size": 60}
    if bookmark:
        options["bookmarks"] = [bookmark]

    params = {
        "source_url": source_url,
        "data": json.dumps({"options": options, "context": {}})
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
                results = data.get("resource_response", {}).get("data", {}).get("results", [])
                next_bm = data.get("resource_response", {}).get("bookmark")
                return results, next_bm
    except Exception as e:
        print(f"⚠️ Pinterest search error for '{keyword}': {e}", flush=True)
    return [], None

async def fetch_pinterest_related(session: aiohttp.ClientSession, pin_id: str):
    csrf = get_csrf(session)
    source_url = f"/pin/{pin_id}/"
    params = {
        "source_url": source_url,
        "data": json.dumps({"options": {"pin_id": str(pin_id), "page_size": 50}, "context": {}})
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
        print(f"⚠️ Pinterest related error on Pin {pin_id}: {e}", flush=True)
    return []

def fetch_insta_posts_sync(L, username: str):
    reels = []
    try:
        profile = instaloader.Profile.from_username(L.context, username)
        count = 0
        for post in profile.get_posts():
            if post.is_video:
                if post.video_duration and post.video_duration < 8.0:
                    continue
                reels.append({
                    "shortcode": post.shortcode,
                    "video_url": post.video_url,
                    "thumb_url": post.url,
                    "caption": post.caption or "",
                    "user": username
                })
                count += 1
                if count >= 15:  # Batch safe limit to prevent 429
                    break
    except Exception as e:
        print(f"⚠️ Instagram notice on @{username}: {e}", flush=True)
    return reels

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

seen_pins = set()
seen_streams = set()
seen_insta = set()

upload_queue = asyncio.Queue(maxsize=300)
pinterest_spider_queue = asyncio.Queue(maxsize=5000)

async def register_pinterest_pins(pins: list):
    for p in pins:
        pid = str(p.get("id"))
        if not pid or pid in seen_pins:
            continue
        seen_pins.add(pid)

        v_url, t_url, title = extract_video_and_thumb(p)
        if v_url:
            sig = extract_stream_signature(v_url)
            if sig in seen_streams:
                continue
            seen_streams.add(sig)

            if not upload_queue.full():
                await upload_queue.put({
                    "source": "pinterest",
                    "id": pid,
                    "sig": sig,
                    "video_url": v_url,
                    "thumb_url": t_url,
                    "title": title
                })

        if not pinterest_spider_queue.full():
            await pinterest_spider_queue.put(pid)

async def producer_pinterest_search(session: aiohttp.ClientSession):
    print("🟢 Pinterest Search Producer Active!", flush=True)
    bookmarks = {kw: None for kw in SEED_KEYWORDS}

    while True:
        shuffled = list(SEED_KEYWORDS)
        random.shuffle(shuffled)

        for kw in shuffled:
            if upload_queue.qsize() > 150:
                await asyncio.sleep(5)
                continue

            bm = bookmarks.get(kw)
            pins, next_bm = await fetch_pinterest_search(session, kw, bm)

            if pins:
                await register_pinterest_pins(pins)

            if not next_bm or next_bm == "-end-" or next_bm == bm:
                bookmarks[kw] = None
            else:
                bookmarks[kw] = next_bm

            await asyncio.sleep(2.0)

        await asyncio.sleep(5)

async def producer_pinterest_spider(session: aiohttp.ClientSession):
    print("🟢 Pinterest Spider Producer Active!", flush=True)

    while True:
        try:
            pid = await asyncio.wait_for(pinterest_spider_queue.get(), timeout=8.0)
            related = await fetch_pinterest_related(session, pid)
            if related:
                await register_pinterest_pins(related)
            pinterest_spider_queue.task_done()
            await asyncio.sleep(1.0)
        except asyncio.TimeoutError:
            await asyncio.sleep(3)
        except Exception as e:
            print(f"⚠️ Spider crawler error: {e}", flush=True)
            await asyncio.sleep(2)

async def producer_instagram():
    print("🟢 Instagram Safe Harvester Producer Active!", flush=True)
    L = init_instaloader()

    while True:
        for user in TARGET_INSTA_ACCOUNTS:
            print(f"🔎 Scanning Instagram Profile: @{user}...", flush=True)
            loop = asyncio.get_running_loop()
            reels = await loop.run_in_executor(None, fetch_insta_posts_sync, L, user)

            new_reels = 0
            for r in reels:
                code = r["shortcode"]
                if code in seen_insta:
                    continue
                seen_insta.add(code)

                if not upload_queue.full():
                    await upload_queue.put({
                        "source": "instagram",
                        "id": code,
                        "sig": code,
                        "video_url": r["video_url"],
                        "thumb_url": r["thumb_url"],
                        "title": r["caption"],
                        "user": r["user"]
                    })
                    new_reels += 1

            if new_reels > 0:
                print(f"🎯 @{user}: Queued {new_reels} fresh reels.", flush=True)
            
            # Anti-429 Cooldown between Instagram accounts
            await asyncio.sleep(25)

        print("💤 Instagram cycle complete. Pausing 10 minutes to protect IP...", flush=True)
        await asyncio.sleep(600)

async def unified_consumer_uploader(session: aiohttp.ClientSession):
    print("🟢 Unified Channel Uploader Active (Max Safe Speed)!", flush=True)

    while True:
        item = await upload_queue.get()
        source = item["source"]
        item_id = item["id"]
        sig = item["sig"]

        temp_video = f"{source}_{item_id}.mp4"
        temp_thumb = f"{source}_thumb_{item_id}.jpg"

        v_ok = await download_file(session, item["video_url"], temp_video, min_size=80000)
        t_ok = False
        if item.get("thumb_url"):
            t_ok = await download_file(session, item["thumb_url"], temp_thumb, min_size=2000)

        if v_ok:
            if source == "instagram":
                caption = (
                    f"✨ <b>Exclusive Instagram Reel</b>\n\n"
                    f"🔥 <b>#{item.get('user', 'Baddie')} #InstagramReels #ViralDance #Hot</b>\n"
                    f"👑 <b>Join:</b> @InstagramPremiumCollection"
                )
            else:
                clean_title = re.sub(r'https?://\S+', '', item['title']).strip()[:65]
                caption = (
                    f"✨ <b>{clean_title if clean_title else 'Exclusive Desi Baddie Reel'}</b>\n\n"
                    f"🔥 <b>#BacklessBaddie #SareeCurves #ViralReels #Desi</b>\n"
                    f"👑 <b>Join:</b> @InstagramPremiumCollection"
                )

            uploaded = await send_to_telegram(session, temp_video, temp_thumb if t_ok else None, caption)
            if uploaded:
                print(f"🚀 [Posted {source.upper()}] ID: {item_id} | Queue Remaining: {upload_queue.qsize()}", flush=True)
                if source == "instagram":
                    append_history(INSTA_HISTORY_FILE, item_id)
                else:
                    append_history(PIN_HISTORY_FILE, item_id)
                    append_history(STREAM_HISTORY_FILE, sig)

        if os.path.exists(temp_video):
            os.remove(temp_video)
        if os.path.exists(temp_thumb):
            os.remove(temp_thumb)

        upload_queue.task_done()
        await asyncio.sleep(1.8)

async def handle_ping(request):
    return web.Response(text="Dual Engine Active 24/7!")

async def start_app():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    print(f"🌐 Keep-Alive Server active on {PORT}", flush=True)

    seen_pins.update(load_history(PIN_HISTORY_FILE))
    seen_streams.update(load_history(STREAM_HISTORY_FILE))
    seen_insta.update(load_history(INSTA_HISTORY_FILE))
    print(f"📋 Loaded {len(seen_pins)} Pins, {len(seen_streams)} Streams, and {len(seen_insta)} Instagram Reels from history.", flush=True)

    async with aiohttp.ClientSession() as session:
        try:
            await session.get("https://www.pinterest.com/", timeout=15)
        except Exception:
            pass

        await asyncio.gather(
            producer_pinterest_search(session),
            producer_pinterest_spider(session),
            producer_instagram(),
            unified_consumer_uploader(session)
        )

if __name__ == "__main__":
    asyncio.run(start_app())
