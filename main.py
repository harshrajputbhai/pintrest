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

async def test_telegram_channel(session: aiohttp.ClientSession):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TARGET_CHANNEL_ID,
        "text": "🟢 <b>Reels Bot Live!</b> Scraping Pinterest & posting reels...",
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
                print("⚠️ Bot ko channel -1004468017163 me ADMIN banayein!", flush=True)
                return False
    except Exception as e:
        print(f"❌ Connection Error: {e}", flush=True)
        return False

async def fetch_pinterest_page(session: aiohttp.ClientSession, keyword: str, bookmark: str = None):
    url = "https://www.pinterest.com/resource/BaseSearchResource/get/"
    options = {
        "query": f"{keyword} reels video",
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
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json, text/javascript, */*, q=0.01",
        "Referer": "https://www.pinterest.com/"
    }

    try:
        async with session.get(url, params=params, headers=headers, timeout=25) as resp:
            print(f"📡 Pinterest Status: {resp.status} for '{keyword}'", flush=True)
            if resp.status != 200:
                return [], None
            
            data = await resp.json()
            resource_resp = data.get("resource_response", {})
            results = resource_resp.get("data", {}).get("results", [])
            next_bookmark = resource_resp.get("bookmark")

            video_pins = []
            for pin in results:
                v_obj = pin.get("videos")
                if v_obj and v_obj.get("video_list"):
                    v_list = v_obj["video_list"]
                    best_url = None
                    for q in ["V_720P", "V_EXP7", "V_480P", "V_EXP6", "V_EXP5"]:
                        if q in v_list and v_list[q].get("url") and v_list[q]["url"].endswith(".mp4"):
                            best_url = v_list[q]["url"]
                            break
                    
                    if best_url:
                        video_pins.append({
                            "id": str(pin.get("id")),
                            "title": pin.get("title") or pin.get("grid_title") or keyword,
                            "video_url": best_url
                        })

            return video_pins, next_bookmark
    except Exception as e:
        print(f"⚠️ Search error on '{keyword}': {e}", flush=True)
        return [], None

async def download_file(session: aiohttp.ClientSession, url: str, filename: str) -> bool:
    try:
        async with session.get(url, timeout=40) as resp:
            if resp.status == 200:
                with open(filename, "wb") as f:
                    f.write(await resp.read())
                return os.path.exists(filename) and os.path.getsize(filename) > 50000
    except Exception as e:
        print(f"⚠️ Download error: {e}", flush=True)
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
    print(f"🟢 Pipeline Engine Started for Channel: {TARGET_CHANNEL_ID}", flush=True)

    async with aiohttp.ClientSession() as session:
        # Step 1: Channel access test
        await test_telegram_channel(session)

        # Step 2: Main Scraping Loop
        while True:
            posted_ids = load_posted_ids()
            print(f"📋 Record: Total {len(posted_ids)} reels pehle se posted hain.", flush=True)

            for keyword in KEYWORDS:
                print(f"\n🔥 Scanning Keyword: '{keyword}'", flush=True)
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

                            await asyncio.sleep(12)

                    if not next_bookmark or next_bookmark == "-end-" or next_bookmark == bookmark:
                        break

                    bookmark = next_bookmark
                    page_no += 1
                    await asyncio.sleep(4)

                await asyncio.sleep(5)

            print("💤 All keywords cycled. Waiting 10 minutes...", flush=True)
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
