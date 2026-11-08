import os
import asyncio
import aiohttp
from aiohttp import web

BOT_TOKEN = os.environ.get("BOT_TOKEN", "9218204780:AAFnj7zZ6JcY90xXCVKzB-fcX2cHxE19_ss")
TARGET_CHANNEL_ID = os.environ.get("TARGET_CHANNEL_ID", "-1004468017163")
PORT = int(os.environ.get("PORT", "10000"))

HISTORY_FILE = "posted_reels.txt"

# Target Subreddits (Desi, Baddie, Saree, Hot Aesthetic Reels)
SUBREDDITS = [
    "SareeBait",
    "DesiCelebHub",
    "IndianBabes",
    "DesiBeauties",
    "DesiBhabhis",
    "SareeCuck",
    "tiktok_baddies",
    "IndianInstagramReels"
]

def load_posted():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r") as f:
            return set(line.strip() for line in f if line.strip())
    return set()

def save_posted(post_id):
    with open(HISTORY_FILE, "a") as f:
        f.write(f"{post_id}\n")

async def fetch_reddit_videos(session: aiohttp.ClientSession, sub: str):
    """Reddit JSON API se video posts extract karein (No 403 on Render)"""
    url = f"https://www.reddit.com/r/{sub}/hot.json?limit=30"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0.0.0"}
    
    videos = []
    try:
        async with session.get(url, headers=headers, timeout=20) as r:
            print(f"📡 Scanning r/{sub} -> Status: {r.status}", flush=True)
            if r.status == 200:
                data = await r.json()
                posts = data.get("data", {}).get("children", [])
                for p in posts:
                    pdata = p.get("data", {})
                    # Sirf direct video posts pick karein
                    if pdata.get("is_video") and pdata.get("media"):
                        fallback_url = pdata["media"].get("reddit_video", {}).get("fallback_url")
                        if fallback_url:
                            # Clean audio/video stream URL
                            clean_url = fallback_url.split("?")[0]
                            videos.append({
                                "id": pdata.get("id"),
                                "title": pdata.get("title") or "Viral Reel",
                                "video_url": clean_url,
                                "sub": sub
                            })
    except Exception as e:
        print(f"⚠️ Error fetching r/{sub}: {e}", flush=True)
    return videos

async def download_file(session: aiohttp.ClientSession, url: str, filename: str) -> bool:
    try:
        async with session.get(url, timeout=40) as r:
            if r.status == 200:
                with open(filename, "wb") as f:
                    f.write(await r.read())
                return os.path.exists(filename) and os.path.getsize(filename) > 30000
    except Exception as e:
        print(f"⚠️ Download failed: {e}", flush=True)
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
        print(f"⚠️ Upload Error: {e}", flush=True)
        return False

async def main_worker():
    print(f"🟢 Reddit Reels Pipeline Live for Channel: {TARGET_CHANNEL_ID}", flush=True)
    async with aiohttp.ClientSession() as session:
        while True:
            posted = load_posted()
            print(f"📋 Total {len(posted)} posts already uploaded.", flush=True)

            for sub in SUBREDDITS:
                vids = await fetch_reddit_videos(session, sub)
                print(f"🎯 r/{sub}: Found {len(vids)} video reels.", flush=True)

                for v in vids:
                    if v["id"] in posted:
                        continue

                    temp_name = f"reel_{v['id']}.mp4"
                    print(f"⬇️ Downloading: {v['id']}...", flush=True)
                    if await download_file(session, v["video_url"], temp_name):
                        caption = (
                            f"✨ <b>{v['title'][:65]}</b>\n\n"
                            f"🔥 <i>#{v['sub']} #ViralReels</i>\n"
                            f"👑 <b>Backup:</b> @InstagramPremiumCollection"
                        )
                        print(f"📤 Posting to Telegram Channel...", flush=True)
                        if await send_to_telegram(session, temp_name, caption):
                            print(f"✅ Video Sent: {v['id']}", flush=True)
                            save_posted(v["id"])
                            posted.add(v["id"])

                        if os.path.exists(temp_name):
                            os.remove(temp_name)

                        await asyncio.sleep(12)  # Safe delay

                await asyncio.sleep(5)

            print("💤 Cycle complete. Waiting 10 minutes...", flush=True)
            await asyncio.sleep(600)

async def handle_ping(request):
    return web.Response(text="Bot Live!")

async def main():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    print(f"🌐 Keep-Alive Server active on {PORT}", flush=True)
    await main_worker()

if __name__ == "__main__":
    asyncio.run(main())
