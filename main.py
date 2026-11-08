import os
import re
import json
import asyncio
import urllib.parse
import aiohttp
from aiohttp import web

BOT_TOKEN = os.environ.get("BOT_TOKEN", "9218204780:AAFnj7zZ6JcY90xXCVKzB-fcX2cHxE19_ss")
TARGET_CHANNEL_ID = os.environ.get("TARGET_CHANNEL_ID", "-1004468017163")
PORT = int(os.environ.get("PORT", "10000"))

HISTORY_FILE = "posted_pins.txt"

KEYWORDS = [
    "Baddie",
    "Desi Baddie",
    "Baddie Bhabhi",
    "Bold Beauty",
    "Bold lookbook reels",
    "Attitude baddie reels",
    "Desi aesthetic baddie",
    "Hot Reels",
    "Hot Bhabhi",
    "Sexy Vibes",
    "Glamour Girl",
    "Hot Desi Reels",
    "18+ Trending Reels",
    "Hot reels Instagram ideas",
    "Desi glam vibes",
    "Hot aesthetic transitions",
    "Saree baddie aesthetic",
    "Ethnic bold styling",
    "Saree low waist styling reels",
    "Saree backless blouse aesthetic",
    "Desi girl saree transition reels"
]

def load_posted_ids():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r") as f:
            return set(line.strip() for line in f if line.strip())
    return set()

def save_posted_id(pin_id):
    with open(HISTORY_FILE, "a") as f:
        f.write(f"{pin_id}\n")

def get_csrf_token(session: aiohttp.ClientSession) -> str:
    for cookie in session.cookie_jar:
        if cookie.key == "csrftoken":
            return cookie.value
    return ""

async def init_pinterest_session(session: aiohttp.ClientSession):
    """Pinterest cookies aur CSRF token initialize karne ke liye"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9"
    }
    try:
        async with session.get("https://www.pinterest.com/", headers=headers, timeout=20) as r:
            await r.read()
            csrf = get_csrf_token(session)
            print(f"🔑 Session Initialized! CSRF Token: {'Found' if csrf else 'Pending'}", flush=True)
    except Exception as e:
        print(f"⚠️ Session init warning: {e}", flush=True)

def extract_videos_from_dict(data) -> list:
    """JSON structure ke andar se recursively video mp4 links dhoondhna"""
    videos = []

    def recursive_search(obj):
        if isinstance(obj, dict):
            if "videos" in obj and isinstance(obj["videos"], dict) and "video_list" in obj["videos"]:
                v_list = obj["videos"]["video_list"]
                best_url = None
                for q in ["V_720P", "V_EXP7", "V_480P", "V_EXP6", "V_EXP5"]:
                    if q in v_list and v_list[q].get("url") and ".mp4" in v_list[q]["url"]:
                        best_url = v_list[q]["url"]
                        break
                if best_url:
                    pin_id = str(obj.get("id") or abs(hash(best_url)) % 100000000)
                    title = obj.get("title") or obj.get("grid_title") or "Viral Reel"
                    videos.append({"id": pin_id, "title": title, "video_url": best_url})
            for k, v in obj.items():
                recursive_search(v)
        elif isinstance(obj, list):
            for item in obj:
                recursive_search(item)

    recursive_search(data)
    
    # Deduplicate
    unique = []
    seen = set()
    for v in videos:
        if v["video_url"] not in seen:
            seen.add(v["video_url"])
            unique.append(v)
    return unique

async def fetch_pinterest_page(session: aiohttp.ClientSession, keyword: str, bookmark: str = None):
    csrf = get_csrf_token(session)
    
    # METHOD 1: Web Page HTML Extraction (Bypasses 403 completely)
    if not bookmark:
        html_url = f"https://www.pinterest.com/search/pins/?q={urllib.parse.quote(keyword)}"
        headers_html = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9"
        }
        try:
            async with session.get(html_url, headers=headers_html, timeout=25) as resp:
                print(f"📡 Web Page Status: {resp.status} for '{keyword}'", flush=True)
                if resp.status == 200:
                    html = await resp.text()
                    
                    # Extract Embedded JSON
                    m = re.search(r'<script id="__PWS_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
                    if m:
                        try:
                            pws_json = json.loads(m.group(1))
                            video_pins = extract_videos_from_dict(pws_json)
                            if video_pins:
                                return video_pins, None
                        except Exception:
                            pass
                    
                    # Fallback Regex MP4 extractor from page
                    raw_mp4s = re.findall(r'(https://[a-zA-Z0-9./_-]+\.mp4)', html)
                    raw_unique = list(set(raw_mp4s))
                    if raw_unique:
                        raw_pins = [{
                            "id": str(abs(hash(u)) % 100000000),
                            "title": keyword,
                            "video_url": u
                        } for u in raw_unique if "v1.pinimg.com" in u or "pinimg" in u]
                        if raw_pins:
                            return raw_pins, None
        except Exception as e:
            print(f"⚠️ HTML search error: {e}", flush=True)

    # METHOD 2: Official BaseSearchResource API (with CSRF and active cookies)
    api_url = "https://www.pinterest.com/resource/BaseSearchResource/get/"
    options = {
        "query": f"{keyword} reels",
        "scope": "pins"
    }
    if bookmark:
        options["bookmarks"] = [bookmark]

    params = {
        "source_url": f"/search/pins/?q={urllib.parse.quote(keyword)}",
        "data": json.dumps({"options": options, "context": {}})
    }
    headers_api = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "X-Requested-With": "XMLHttpRequest",
        "X-CSRFToken": csrf,
        "Accept": "application/json, text/javascript, */*, q=0.01",
        "Referer": f"https://www.pinterest.com/search/pins/?q={urllib.parse.quote(keyword)}",
        "Origin": "https://www.pinterest.com"
    }

    try:
        async with session.get(api_url, params=params, headers=headers_api, timeout=25) as resp:
            print(f"📡 API Resource Status: {resp.status} for '{keyword}'", flush=True)
            if resp.status == 200:
                data = await resp.json()
                results = data.get("resource_response", {}).get("data", {}).get("results", [])
                next_bm = data.get("resource_response", {}).get("bookmark")
                video_pins = extract_videos_from_dict(results)
                return video_pins, next_bm
    except Exception as e:
        print(f"⚠️ API search error on '{keyword}': {e}", flush=True)

    return [], None

async def download_file(session: aiohttp.ClientSession, url: str, filename: str) -> bool:
    try:
        async with session.get(url, timeout=45) as resp:
            if resp.status == 200:
                with open(filename, "wb") as f:
                    f.write(await resp.read())
                return os.path.exists(filename) and os.path.getsize(filename) > 30000
    except Exception as e:
        print(f"⚠️ Video download failed: {e}", flush=True)
    return False

async def send_video_to_telegram(session: aiohttp.ClientSession, video_path: str, caption: str) -> bool:
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

        async with session.post(telegram_url, data=data, timeout=120) as resp:
            res = await resp.json()
            if res.get("ok"):
                return True
            else:
                print(f"❌ Telegram API Error: {res.get('description')}", flush=True)
                return False
    except Exception as e:
        print(f"⚠️ Telegram Upload Error: {e}", flush=True)
        return False

async def infinite_reels_pipeline():
    print(f"🟢 Pipeline Engine Ready for Channel: {TARGET_CHANNEL_ID}", flush=True)

    async with aiohttp.ClientSession() as session:
        # Step 1: Session & Cookies Setup
        await init_pinterest_session(session)

        # Step 2: Continuous Scraping Loop
        while True:
            posted_ids = load_posted_ids()
            print(f"📋 Record: Total {len(posted_ids)} reels pehle se posted hain.", flush=True)

            for keyword in KEYWORDS:
                print(f"\n==========================================", flush=True)
                print(f"🔥 Scanning Keyword: '{keyword}'", flush=True)
                print(f"==========================================", flush=True)
                
                bookmark = None
                page_no = 1

                while True:
                    video_pins, next_bookmark = await fetch_pinterest_page(session, keyword, bookmark)
                    print(f"🎯 Page {page_no}: Found {len(video_pins)} video pins.", flush=True)

                    if not video_pins:
                        break

                    for pin in video_pins:
                        pin_id = pin["id"]
                        if pin_id in posted_ids:
                            continue

                        temp_file = f"temp_{pin_id}.mp4"
                        print(f"⬇️ Downloading Pin {pin_id}...", flush=True)
                        success = await download_file(session, pin["video_url"], temp_file)

                        if success:
                            caption = (
                                f"✨ <b>{pin['title'][:60]}</b>\n\n"
                                f"🔥 <i>#{keyword.replace(' ', '_')}</i>\n"
                                f"👑 <b>Join:</b> @InstagramPremiumCollection"
                            )

                            print(f"📤 Uploading Pin {pin_id} to Telegram...", flush=True)
                            uploaded = await send_video_to_telegram(session, temp_file, caption)
                            if uploaded:
                                print(f"✅ Video Delivered to Channel! [Pin: {pin_id}]", flush=True)
                                save_posted_id(pin_id)
                                posted_ids.add(pin_id)

                            if os.path.exists(temp_file):
                                os.remove(temp_file)

                            await asyncio.sleep(12)  # Delay between uploads

                    if not next_bookmark or next_bookmark == "-end-" or next_bookmark == bookmark:
                        break

                    bookmark = next_bookmark
                    page_no += 1
                    await asyncio.sleep(4)

                await asyncio.sleep(6)

            print("💤 Sabhi keywords complete. Waiting 10 minutes...", flush=True)
            await asyncio.sleep(600)

async def handle_ping(request):
    return web.Response(text="Bot Active!")

async def main():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    print(f"🌐 Keep-Alive Server active on port {PORT}", flush=True)

    await infinite_reels_pipeline()

if __name__ == "__main__":
    asyncio.run(main())
