import os
import json
import urllib.parse
import asyncio

# Render Python 3.12+ / 3.14 Event Loop Crash Fix
try:
    asyncio.get_event_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

import aiohttp
from aiohttp import web
import pyrogram.utils
from pyrogram import Client, enums
from pyrogram.errors import FloodWait

# 64-bit Telegram Peer ID Fix
def patched_get_peer_type(peer_id: int) -> str:
    if peer_id < 0:
        if peer_id <= -1000000000000:
            return "channel"
        if -2147483647 <= peer_id < 0:
            return "chat"
    elif peer_id > 0:
        return "user"
    raise ValueError(f"Peer id invalid: {peer_id}")

pyrogram.utils.get_peer_type = patched_get_peer_type

# Configuration
API_ID = int(os.environ.get("API_ID", "37025158"))
API_HASH = os.environ.get("API_HASH", "4bfdef0d097d4d7d97d5b61a077a0962")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "9218204780:AAFnj7zZ6JcY90xXCVKzB-fcX2cHxE19_ss")

# Aapka Target Channel ID (Reels seedha is channel me jayengi)
TARGET_CHANNEL_ID = int(os.environ.get("TARGET_CHANNEL_ID", "-1004468017163"))
PORT = int(os.environ.get("PORT", "8080"))

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

bot = Client("pinterest_reels_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

def load_posted_ids():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r") as f:
            return set(line.strip() for line in f if line.strip())
    return set()

def save_posted_id(pin_id):
    with open(HISTORY_FILE, "a") as f:
        f.write(f"{pin_id}\n")

async def fetch_pinterest_page(session: aiohttp.ClientSession, keyword: str, bookmark: str = None):
    url = "https://www.pinterest.com/resource/BaseSearchResource/get/"
    options = {
        "query": keyword,
        "scope": "pins"
    }
    if bookmark:
        options["bookmarks"] = [bookmark]

    params = {
        "source_url": f"/search/pins/?q={urllib.parse.quote(keyword)}",
        "data": json.dumps({
            "options": options,
            "context": {}
        })
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json, text/javascript, */*, q=0.01",
        "Referer": "https://www.pinterest.com/"
    }

    try:
        async with session.get(url, params=params, headers=headers, timeout=20) as resp:
            if resp.status != 200:
                return [], None
            data = await resp.json()
            resource_resp = data.get("resource_response", {})
            results = resource_resp.get("data", {}).get("results", [])
            next_bookmark = resource_resp.get("bookmark")

            video_pins = []
            for pin in results:
                if pin.get("videos") and pin["videos"].get("video_list"):
                    video_list = pin["videos"]["video_list"]
                    best_stream = None
                    for quality in ["V_720P", "V_EXP7", "V_480P", "V_EXP6", "V_EXP5"]:
                        if quality in video_list and video_list[quality].get("url"):
                            best_stream = video_list[quality]["url"]
                            break
                    
                    if best_stream and best_stream.endswith(".mp4"):
                        video_pins.append({
                            "id": str(pin.get("id")),
                            "title": pin.get("title") or pin.get("grid_title") or keyword,
                            "video_url": best_stream
                        })

            return video_pins, next_bookmark
    except Exception as e:
        print(f"⚠️ Search error on '{keyword}': {e}")
        return [], None

async def download_file(session: aiohttp.ClientSession, url: str, filename: str) -> bool:
    try:
        async with session.get(url, timeout=30) as resp:
            if resp.status == 200:
                with open(filename, "wb") as f:
                    f.write(await resp.read())
                return os.path.exists(filename) and os.path.getsize(filename) > 10000
    except Exception as e:
        print(f"⚠️ Video download error: {e}")
    return False

async def infinite_reels_pipeline():
    await bot.start()
    print(f"🟢 Bot Online! Targeting Channel: {TARGET_CHANNEL_ID}")

    async with aiohttp.ClientSession() as session:
        while True:
            posted_ids = load_posted_ids()
            print(f"📋 Record: Total {len(posted_ids)} reels pehle se posted hain.")

            for keyword in KEYWORDS:
                print(f"\n🔥 Scanning Keyword: '{keyword}'")
                bookmark = None
                page_no = 1
                consecutive_empty = 0

                while True:
                    video_pins, next_bookmark = await fetch_pinterest_page(session, keyword, bookmark)

                    if not video_pins:
                        consecutive_empty += 1
                        if consecutive_empty >= 2 or not next_bookmark or next_bookmark == "-end-":
                            break
                    else:
                        consecutive_empty = 0

                    for pin in video_pins:
                        pin_id = pin["id"]
                        if pin_id in posted_ids:
                            continue

                        temp_file = f"temp_{pin_id}.mp4"
                        success = await download_file(session, pin["video_url"], temp_file)

                        if success:
                            caption = (
                                f"✨ <b>{pin['title'][:60]}</b>\n\n"
                                f"🔥 <i>#{keyword.replace(' ', '_')}</i>\n"
                                f"👑 <b>Join:</b> @InstagramPremiumCollection"
                            )

                            while True:
                                try:
                                    # Post directly to your Channel -1004468017163
                                    await bot.send_video(
                                        chat_id=TARGET_CHANNEL_ID,
                                        video=temp_file,
                                        caption=caption,
                                        parse_mode=enums.ParseMode.HTML
                                    )
                                    print(f"✅ Posted Pin ID {pin_id} to Channel {TARGET_CHANNEL_ID}!")
                                    save_posted_id(pin_id)
                                    posted_ids.add(pin_id)
                                    break
                                except FloodWait as e:
                                    print(f"⏳ FloodWait: Waiting {e.value} seconds...")
                                    await asyncio.sleep(e.value)
                                except Exception as post_err:
                                    print(f"❌ Upload Error: {post_err}")
                                    break

                            if os.path.exists(temp_file):
                                os.remove(temp_file)

                            await asyncio.sleep(8)

                    if not next_bookmark or next_bookmark == "-end-" or next_bookmark == bookmark:
                        break

                    bookmark = next_bookmark
                    page_no += 1
                    await asyncio.sleep(3)

                await asyncio.sleep(4)

            print("💤 Sabhi keywords complete. Waiting 10 minutes...")
            await asyncio.sleep(600)

async def handle_ping(request):
    return web.Response(text="Reels Automation Bot 24x7 Active!")

async def main():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    print(f"🌐 Keep-Alive Web Server started on port {PORT}")

    await infinite_reels_pipeline()

if __name__ == "__main__":
    asyncio.run(main())
