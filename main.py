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
        "text": "🟢 <b>Pinterest Reels Bot Active!</b>\nScraping high-quality reels...",
        "parse_mode": "HTML"
    }
    try:
        async with session.post(url, json=payload, timeout=15) as resp:
            data = await resp.json()
            if data.get("ok"):
                print("✅ Telegram Connected to Channel Successfully!", flush=True)
                return True
            else:
                print(f"❌ Telegram Error: {data.get('description')}", flush=True)
                return False
    except Exception as e:
        print(f"❌ Connection Error: {e}", flush=True)
        return False

def extract_pinterest_mp4_links(html: str) -> list:
    """Pinterest page HTML aur JSON ke andar se raw video streams extract karein"""
    clean_html = html.replace(r"\/", "/")
    
    # 1. Direct 720p / 480p / Exp mp4 links
    mp4_urls = re.findall(r'https://[a-zA-Z0-9./_-]+(?:videos|v1\.pinimg\.com)[a-zA-Z0-9./_-]+\.mp4', clean_html)
    
    # 2. General fallback for any pinimg mp4
    if not mp4_urls:
        mp4_urls = re.findall(r'https://v\d?\.pinimg\.com/[^"\'\s<>]+\.mp4', clean_html)

    unique_urls = list(set(mp4_urls))
    videos = []
    for u in unique_urls:
        # Unique ID based on hash
        pin_id = str(abs(hash(u)) % 1000000000)
        videos.append({
            "id": pin_id,
            "video_url": u
        })
    return videos

async def fetch_pinterest_keyword_videos(session: aiohttp.ClientSession, keyword: str):
    search_query = f"{keyword} reels video"
    url = f"https://www.pinterest.com/search/pins/?q={urllib.parse.quote(search_query)}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Sec-Ch-Ua": '"Chromium";v="128", "Not;A=Brand";v="24"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1"
    }

    try:
        async with session.get(url, headers=headers, timeout=30) as resp:
            print(f"📡 Pinterest Web Fetch: {resp.status} for '{keyword}'", flush=True)
            if resp.status == 200:
                html = await resp.text()
                videos = extract_pinterest_mp4_links(html)
                return videos
    except Exception as e:
        print(f"⚠️ Search error for '{keyword}': {e}", flush=True)
    return []

async def download_file(session: aiohttp.ClientSession, url: str, filename: str) -> bool:
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        async with session.get(url, headers=headers, timeout=45) as resp:
            if resp.status == 200:
                with open(filename, "wb") as f:
                    f.write(await resp.read())
                return os.path.exists(filename) and os.path.getsize(filename) > 40000
    except Exception as e:
        print(f"⚠️ Download failed: {e}", flush=True)
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
        print(f"⚠️ Upload Error: {e}", flush=True)
        return False

async def main_worker():
    print(f"🟢 Pipeline Engine Live for Channel: {TARGET_CHANNEL_ID}", flush=True)

    async with aiohttp.ClientSession() as session:
        await test_telegram_channel(session)

        while True:
            posted = load_posted()
            print(f"📋 Record: {len(posted)} videos pehle se posted hain.", flush=True)

            for keyword in KEYWORDS:
                print(f"\n==========================================", flush=True)
                print(f"🔥 Scanning Keyword: '{keyword}'", flush=True)
                print(f"==========================================", flush=True)

                videos = await fetch_pinterest_keyword_videos(session, keyword)
                print(f"🎯 Found {len(videos)} video reels for '{keyword}'", flush=True)

                for v in videos:
                    pin_id = v["id"]
                    if pin_id in posted:
                        continue

                    temp_name = f"reel_{pin_id}.mp4"
                    print(f"⬇️ Downloading: {pin_id}...", flush=True)
                    success = await download_file(session, v["video_url"], temp_name)

                    if success:
                        caption = (
                            f"✨ <b>Viral Reel: {keyword}</b>\n\n"
                            f"🔥 <i>#{keyword.replace(' ', '_')} #Baddie</i>\n"
                            f"👑 <b>Join:</b> @InstagramPremiumCollection"
                        )
                        print(f"📤 Uploading to Telegram Channel...", flush=True)
                        uploaded = await send_video_to_telegram(session, temp_name, caption)
                        if uploaded:
                            print(f"✅ Video Sent Successfully: {pin_id}", flush=True)
                            save_posted(pin_id)
                            posted.add(pin_id)

                        if os.path.exists(temp_name):
                            os.remove(temp_name)

                        await asyncio.sleep(12)

                await asyncio.sleep(5)

            print("💤 Saare keywords complete. 10 minute me naya scan shuru hoga...", flush=True)
            await asyncio.sleep(600)

async def handle_ping(request):
    return web.Response(text="Bot Live 24/7!")

async def start_app():
    # Web server on port 10000 for Render
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
