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

def load_posted():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r") as f:
            return set(line.strip() for line in f if line.strip())
    return set()

def save_posted(pin_id):
    with open(HISTORY_FILE, "a") as f:
        f.write(f"{pin_id}\n")

async def test_telegram_channel(session: aiohttp.ClientSession):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TARGET_CHANNEL_ID,
        "text": "🟢 <b>Pinterest Engine Connected!</b>\nDirect Pinterest scraper active...",
        "parse_mode": "HTML"
    }
    try:
        async with session.post(url, json=payload, timeout=15) as resp:
            data = await resp.json()
            if data.get("ok"):
                print("✅ Telegram Channel Test Passed!", flush=True)
                return True
            else:
                print(f"❌ Telegram Error: {data.get('description')}", flush=True)
    except Exception as e:
        print(f"❌ Connection Error: {e}", flush=True)
    return False

def get_csrf(session: aiohttp.ClientSession) -> str:
    for c in session.cookie_jar:
        if c.key == "csrftoken":
            return c.value
    return ""

async def fetch_pinterest_videos(session: aiohttp.ClientSession, keyword: str, bookmark: str = None):
    """Pinterest internal API with load-bearing PWS-Handler header to bypass 403"""
    csrf = get_csrf(session)
    source_url = f"/search/pins/?q={urllib.parse.quote(keyword)}"
    
    options = {
        "query": f"{keyword} reels",
        "scope": "pins",
        "page_size": 25
    }
    if bookmark:
        options["bookmarks"] = [bookmark]

    params = {
        "source_url": source_url,
        "data": json.dumps({"options": options, "context": {}})
    }

    # Inhi 4 headers ki kami se Pinterest pehle 403 de raha tha
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
            print(f"📡 Pinterest API Status: {resp.status} for '{keyword}'", flush=True)
            if resp.status == 200:
                data = await resp.json()
                results = data.get("resource_response", {}).get("data", {}).get("results", [])
                next_bm = data.get("resource_response", {}).get("bookmark")

                videos = []
                for pin in results:
                    v_dict = pin.get("videos")
                    if v_dict and isinstance(v_dict, dict) and "video_list" in v_dict:
                        v_list = v_dict["video_list"]
                        best_stream = None
                        for q in ["V_720P", "V_EXP7", "V_480P", "V_EXP6", "V_EXP5"]:
                            if q in v_list and v_list[q].get("url") and ".mp4" in v_list[q]["url"]:
                                best_stream = v_list[q]["url"]
                                break
                        
                        if best_stream:
                            videos.append({
                                "id": str(pin.get("id")),
                                "title": pin.get("title") or pin.get("grid_title") or keyword,
                                "video_url": best_stream
                            })

                return videos, next_bm
    except Exception as e:
        print(f"⚠️ Search error for '{keyword}': {e}", flush=True)

    return [], None

async def download_file(session: aiohttp.ClientSession, url: str, filename: str) -> bool:
    try:
        async with session.get(url, timeout=40) as resp:
            if resp.status == 200:
                with open(filename, "wb") as f:
                    f.write(await resp.read())
                return os.path.exists(filename) and os.path.getsize(filename) > 30000
    except Exception as e:
        print(f"⚠️ Video download error: {e}", flush=True)
    return False

async def send_to_telegram(session: aiohttp.ClientSession, video_path: str, caption: str) -> bool:
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
                print(f"❌ Telegram Error: {res.get('description')}", flush=True)
                return False
    except Exception as e:
        print(f"⚠️ Telegram Upload Error: {e}", flush=True)
        return False

async def main_worker():
    print(f"🟢 Pinterest Pipeline Live for Channel: {TARGET_CHANNEL_ID}", flush=True)

    async with aiohttp.ClientSession() as session:
        # Pre-warm cookies to get csrftoken
        try:
            await session.get("https://www.pinterest.com/", timeout=15)
        except Exception:
            pass

        await test_telegram_channel(session)

        while True:
            posted = load_posted()
            print(f"📋 Record: {len(posted)} reels pehle se posted hain.", flush=True)

            for keyword in KEYWORDS:
                print(f"\n==========================================", flush=True)
                print(f"🔥 Scanning Pinterest for: '{keyword}'", flush=True)
                print(f"==========================================", flush=True)

                bookmark = None
                page_no = 1

                while True:
                    videos, next_bm = await fetch_pinterest_videos(session, keyword, bookmark)
                    print(f"🎯 Page {page_no}: Found {len(videos)} video reels.", flush=True)

                    if not videos:
                        break

                    for v in videos:
                        pin_id = v["id"]
                        if pin_id in posted:
                            continue

                        temp_name = f"pin_{pin_id}.mp4"
                        print(f"⬇️ Downloading Pinterest Video: {pin_id}...", flush=True)
                        if await download_file(session, v["video_url"], temp_name):
                            caption = (
                                f"✨ <b>{v['title'][:60]}</b>\n\n"
                                f"🔥 <i>#{keyword.replace(' ', '_')} #PinterestReels</i>\n"
                                f"👑 <b>Join:</b> @InstagramPremiumCollection"
                            )

                            print(f"📤 Uploading to Telegram Channel...", flush=True)
                            uploaded = await send_to_telegram(session, temp_name, caption)
                            if uploaded:
                                print(f"🚀 Delivered Pin {pin_id} to Channel!", flush=True)
                                save_posted(pin_id)
                                posted.add(pin_id)

                            if os.path.exists(temp_name):
                                os.remove(temp_name)

                            await asyncio.sleep(12)  # Safe delay between uploads

                    if not next_bm or next_bm == "-end-" or next_bm == bookmark:
                        break

                    bookmark = next_bm
                    page_no += 1
                    await asyncio.sleep(4)

                await asyncio.sleep(5)

            print("💤 Saare keywords complete ho gaye. 10 minute me naya round chalega...", flush=True)
            await asyncio.sleep(600)

async def handle_ping(request):
    return web.Response(text="Pinterest Video Scraper Active 24/7!")

async def start_app():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    print(f"🌐 Keep-Alive Web Server active on port {PORT}", flush=True)

    await main_worker()

if __name__ == "__main__":
    asyncio.run(start_app())
