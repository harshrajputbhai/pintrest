import os
import re
import asyncio
import urllib.parse
import aiohttp
from aiohttp import web
import yt_dlp

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

async def test_telegram(session: aiohttp.ClientSession):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TARGET_CHANNEL_ID,
        "text": "🟢 <b>Pinterest Engine Live!</b>\nSearching & downloading keyword reels...",
        "parse_mode": "HTML"
    }
    try:
        async with session.post(url, json=payload, timeout=15) as r:
            data = await r.json()
            if data.get("ok"):
                print("✅ Telegram Connected Successfully!", flush=True)
                return True
            else:
                print(f"❌ Telegram Error: {data.get('description')}", flush=True)
    except Exception as e:
        print(f"❌ Telegram Test Error: {e}", flush=True)
    return False

async def get_pinterest_pins_for_keyword(session: aiohttp.ClientSession, keyword: str) -> list:
    """DuckDuckGo se Pinterest ke actual video pin links extract karein"""
    query = f"site:pinterest.com/pin/ {keyword} video"
    url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    }

    pin_ids = []
    try:
        async with session.get(url, headers=headers, timeout=20) as r:
            if r.status == 200:
                html = await r.text()
                # Pinterest Pin IDs dhoondhein (12-19 digits)
                matches = re.findall(r"pinterest\.com/pin/(\d+)", html)
                for pid in matches:
                    if pid not in pin_ids:
                        pin_ids.append(pid)
    except Exception as e:
        print(f"⚠️ Search fetch failed for '{keyword}': {e}", flush=True)

    return pin_ids

def download_pinterest_video(pin_id: str) -> str:
    """yt-dlp ke native Pinterest extractor se video download karein"""
    url = f"https://www.pinterest.com/pin/{pin_id}/"
    output_filename = f"pin_{pin_id}.mp4"

    ydl_opts = {
        "outtmpl": output_filename,
        "format": "bestvideo+bestaudio/best",
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 30
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        if os.path.exists(output_filename) and os.path.getsize(output_filename) > 30000:
            return output_filename
    except Exception:
        # Pin video nahi hai (sirf image hai) ya private hai
        if os.path.exists(output_filename):
            os.remove(output_filename)
    return None

async def send_to_telegram(session: aiohttp.ClientSession, video_path: str, caption: str) -> bool:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendVideo"
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

        async with session.post(url, data=data, timeout=120) as resp:
            res = await resp.json()
            return res.get("ok", False)
    except Exception as e:
        print(f"⚠️ Upload Error: {e}", flush=True)
        return False

async def main_pipeline():
    print(f"🟢 Starting Pinterest Engine for Channel: {TARGET_CHANNEL_ID}", flush=True)

    async with aiohttp.ClientSession() as session:
        await test_telegram(session)

        while True:
            posted = load_posted()
            print(f"📋 Total {len(posted)} pins already processed.", flush=True)

            for keyword in KEYWORDS:
                print(f"\n==========================================", flush=True)
                print(f"🔥 Searching Pinterest for: '{keyword}'", flush=True)
                print(f"==========================================", flush=True)

                pins = await get_pinterest_pins_for_keyword(session, keyword)
                print(f"🎯 Found {len(pins)} Pinterest Pins for '{keyword}'", flush=True)

                for pid in pins:
                    if pid in posted:
                        continue

                    # yt-dlp running in async executor to avoid blocking the event loop
                    loop = asyncio.get_event_loop()
                    video_file = await loop.run_in_executor(None, download_pinterest_video, pid)

                    if video_file:
                        print(f"✅ Video Downloaded: Pin {pid}", flush=True)
                        caption = (
                            f"✨ <b>Viral Reel: {keyword}</b>\n\n"
                            f"🔥 <i>#{keyword.replace(' ', '_')} #PinterestReels</i>\n"
                            f"👑 <b>Join:</b> @InstagramPremiumCollection"
                        )

                        print(f"📤 Uploading Pin {pid} to Telegram...", flush=True)
                        sent = await send_to_telegram(session, video_file, caption)
                        if sent:
                            print(f"🚀 Delivered Pin {pid} to Channel!", flush=True)
                            save_posted(pid)
                            posted.add(pid)

                        if os.path.exists(video_file):
                            os.remove(video_file)

                        await asyncio.sleep(12)  # Delay between uploads
                    else:
                        # Image pin thi, record kar liya taaki bar-bar download na try kare
                        save_posted(pid)
                        posted.add(pid)

                await asyncio.sleep(6)

            print("💤 Sabhi keywords complete. Waiting 15 minutes for fresh pins...", flush=True)
            await asyncio.sleep(900)

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

    await main_pipeline()

if __name__ == "__main__":
    asyncio.run(start_app())
