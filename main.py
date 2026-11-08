import os
import json
import asyncio
import urllib.parse
import aiohttp
from aiohttp import web

BOT_TOKEN = os.environ.get("BOT_TOKEN", "9218204780:AAFnj7zZ6JcY90xXCVKzB-fcX2cHxE19_ss")
TARGET_CHANNEL_ID = os.environ.get("TARGET_CHANNEL_ID", "-1004468017163")
PORT = int(os.environ.get("PORT", "10000"))

HISTORY_FILE = "posted_pins.txt"

# Comprehensive Adult Categories (Married, Bridal, College, Unmarried, Curvy, Bhabhi)
KEYWORDS = [
    # 1. Newly Married / Bridal / Dulhan Look
    "Nayi dulhan saree lookbook reels",
    "Desi bridal saree transition bold",
    "Newly married bhabhi saree reels",
    "Desi dulhan backless choli reels",
    "Sindoor look bold saree reels",
    
    # 2. Desi Bhabhi & Mature Curvy Aesthetic
    "Desi curvy bhabhi saree reels",
    "Desi bhabhi viral dance reels",
    "Desi aunty curvy saree lookbook",
    "Chubby bhabhi saree fashion reels",
    "Desi bhabhi home styling reels",
    
    # 3. College / Farewell / Young Adult (18+)
    "College farewell saree lookbook reels",
    "College fest baddie ethnic reels",
    "Desi college girl saree transition",
    "University farewell bold saree look",
    
    # 4. Unmarried / Modern Ethnic Baddie
    "Desi unmarried girl saree styling",
    "Desi low waist lehenga transition",
    "Desi crop top backless choli reels",
    "Desi modern baddie lookbook haul",
    "Desi girl attitude walk saree",
    
    # 5. Low Waist / Figure / Curvy Lookbook
    "Desi low waist saree draping reels",
    "Saree low waist thong aesthetic",
    "Desi navel show saree reels",
    "Desi hourglass figure saree transition",
    "Desi transparent saree lookbook reels",
    
    # 6. Deep Neck / Cleavage / Busty Styling
    "Desi deep cleavage blouse reels",
    "Desi deep neck blouse styling reels",
    "Desi busty curvy aesthetic reels",
    "Desi backless dori blouse reels",
    
    # 7. Lingerie / Nightwear / Bold Hauls
    "Desi lingerie try on haul reels",
    "Desi satin nighty bold reels",
    "Desi bikini lookbook haul reels",
    "Desi bold bedroom transition reels"
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

def extract_video_and_thumb(pin, fallback_title):
    """MP4 Video Reels extraction (Duration >= 8s) + Cover Image"""
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
            if raw_duration:
                try:
                    dur = float(raw_duration)
                    if dur > 500:
                        dur = dur / 1000.0
                    if dur < 8.0:
                        return None, None, None
                except Exception:
                    pass

            title = pin.get("title") or pin.get("grid_title") or fallback_title
            return best_url, thumb_url, title

    return None, None, None

async def fetch_pinterest_videos(session: aiohttp.ClientSession, keyword: str, bookmark: str = None):
    csrf = get_csrf(session)
    clean_keyword = keyword.strip()
    source_url = f"/search/pins/?q={urllib.parse.quote(clean_keyword)}"
    
    options = {
        "query": clean_keyword,
        "scope": "pins",
        "page_size": 80
    }
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

                videos = []
                for pin in results:
                    v_url, t_url, title = extract_video_and_thumb(pin, clean_keyword)
                    if v_url:
                        videos.append({
                            "id": str(pin.get("id")),
                            "title": title,
                            "video_url": v_url,
                            "thumb_url": t_url
                        })

                return videos, next_bm
    except Exception as e:
        print(f"⚠️ Search error for '{clean_keyword}': {e}", flush=True)

    return [], None

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
        print(f"⚠️ Telegram Upload Error: {e}", flush=True)
        return False

async def main_worker():
    print(f"🟢 Comprehensive Adult Reels Pipeline Active for Channel: {TARGET_CHANNEL_ID}", flush=True)

    async with aiohttp.ClientSession() as session:
        try:
            await session.get("https://www.pinterest.com/", timeout=15)
        except Exception:
            pass

        while True:
            posted = load_posted()
            print(f"📋 Total {len(posted)} curated reels logged in history.", flush=True)

            for keyword in KEYWORDS:
                print(f"\n🔥 Scanning Pinterest for: '{keyword}'", flush=True)

                bookmark = None
                page_no = 1
                consecutive_empty = 0

                while True:
                    videos, next_bm = await fetch_pinterest_videos(session, keyword, bookmark)
                    print(f"🎯 Page {page_no}: Found {len(videos)} reels (>=8s).", flush=True)

                    if not videos:
                        consecutive_empty += 1
                        if consecutive_empty >= 2 or not next_bm or next_bm == "-end-":
                            break
                    else:
                        consecutive_empty = 0

                    for v in videos:
                        pin_id = v["id"]
                        if pin_id in posted:
                            continue

                        temp_video = f"pin_{pin_id}.mp4"
                        temp_thumb = f"thumb_{pin_id}.jpg"

                        v_ok = await download_file(session, v["video_url"], temp_video, min_size=80000)
                        t_ok = False
                        if v.get("thumb_url"):
                            t_ok = await download_file(session, v["thumb_url"], temp_thumb, min_size=2000)

                        if v_ok:
                            tag = keyword.replace(" ", "_")
                            caption = (
                                f"✨ <b>{v['title'][:65]}</b>\n\n"
                                f"🔥 <b>#DesiLookbook #SareeBaddie #ViralReels</b>\n"
                                f"👑 <b>Join:</b> @InstagramPremiumCollection"
                            )

                            uploaded = await send_to_telegram(
                                session,
                                temp_video,
                                temp_thumb if t_ok else None,
                                caption
                            )

                            if uploaded:
                                print(f"🚀 Delivered Pin {pin_id} to Channel!", flush=True)
                                save_posted(pin_id)
                                posted.add(pin_id)

                            if os.path.exists(temp_video):
                                os.remove(temp_video)
                            if os.path.exists(temp_thumb):
                                os.remove(temp_thumb)

                            await asyncio.sleep(2.5)

                    if not next_bm or next_bm == "-end-" or next_bm == bookmark:
                        break

                    bookmark = next_bm
                    page_no += 1
                    await asyncio.sleep(1.5)

                await asyncio.sleep(2)

            print("💤 Cycle complete. Restarting in 15 seconds...", flush=True)
            await asyncio.sleep(15)

async def handle_ping(request):
    return web.Response(text="Bot Active 24/7!")

async def start_app():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    print(f"🌐 Server active on {PORT}", flush=True)

    await main_worker()

if __name__ == "__main__":
    asyncio.run(start_app())
