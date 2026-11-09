import os
import json
import asyncio
import aiohttp
from aiohttp import web
import instaloader

BOT_TOKEN = os.environ.get("BOT_TOKEN", "9218204780:AAFnj7zZ6JcY90xXCVKzB-fcX2cHxE19_ss")
TARGET_CHANNEL_ID = os.environ.get("TARGET_CHANNEL_ID", "-1004438931877")
PORT = int(os.environ.get("PORT", "10000"))
INSTA_SESSION_ID = os.environ.get("INSTA_SESSION_ID", "")

TARGET_USER = "rohitfitpreneur"
HISTORY_FILE = "posted_rohit.txt"

def load_posted():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r") as f:
            return set(line.strip() for line in f if line.strip())
    return set()

def save_posted(shortcode):
    with open(HISTORY_FILE, "a") as f:
        f.write(f"{shortcode}\n")

async def send_status_alert(session: aiohttp.ClientSession, message: str):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        payload = {
            "chat_id": str(TARGET_CHANNEL_ID),
            "text": message,
            "parse_mode": "HTML"
        }
        async with session.post(url, json=payload, timeout=15) as resp:
            pass
    except Exception:
        pass

async def download_file(session: aiohttp.ClientSession, url: str, filename: str) -> bool:
    try:
        async with session.get(url, timeout=45) as resp:
            if resp.status == 200:
                with open(filename, "wb") as f:
                    f.write(await resp.read())
                return os.path.exists(filename) and os.path.getsize(filename) > 40000
    except Exception:
        pass
    return False

async def send_to_telegram(session: aiohttp.ClientSession, video_path: str, thumb_path: str, caption: str) -> bool:
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
        if thumb_path and os.path.exists(thumb_path):
            data.add_field(
                "thumbnail",
                open(thumb_path, "rb"),
                filename="thumb.jpg",
                content_type="image/jpeg"
            )

        async with session.post(url, data=data, timeout=120) as resp:
            res = await resp.json()
            if not res.get("ok"):
                # Handle Telegram 429 FloodWait
                if res.get("error_code") == 429:
                    wait_sec = res.get("parameters", {}).get("retry_after", 30)
                    print(f"⚠️ Telegram FloodWait: Sleeping for {wait_sec}s", flush=True)
                    await asyncio.sleep(wait_sec)
                return False
            return True
    except Exception as e:
        print(f"⚠️ Telegram upload error: {e}", flush=True)
        return False

def init_instaloader():
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
        print("🔑 Instagram Session Cookie Active!", flush=True)
    return L

async def immortal_harvester(session: aiohttp.ClientSession):
    posted = load_posted()
    await send_status_alert(
        session,
        f"🚀 <b>Overnight Harvester Started!</b>\n\n"
        f"🎯 <b>Target:</b> @{TARGET_USER}\n"
        f"📁 <b>Channel:</b> <code>{TARGET_CHANNEL_ID}</code>\n"
        f"📊 <b>Pre-archived:</b> {len(posted)} reels\n"
        f"⚡ <b>Mode:</b> Newest to Oldest (Zero Disruption)"
    )
    print(f"🟢 Immortal Overnight Harvester Online for @{TARGET_USER}", flush=True)

    L = init_instaloader()

    while True:
        try:
            posted = load_posted()
            profile = instaloader.Profile.from_username(L.context, TARGET_USER)
            print(f"🔍 Connected to @{TARGET_USER}. Scanning feed...", flush=True)

            batch_count = 0

            # get_posts() traverses from Newest (Latest) to Oldest
            for post in profile.get_posts():
                # Strictly Video Reels Only
                if not post.is_video or not post.video_url:
                    continue

                # Filter out short clips under 8 seconds
                if post.video_duration and post.video_duration < 8.0:
                    continue

                code = post.shortcode
                if code in posted:
                    continue

                temp_video = f"reel_{code}.mp4"
                temp_thumb = f"thumb_{code}.jpg"

                try:
                    v_ok = await download_file(session, post.video_url, temp_video)
                    t_ok = False
                    if post.url:
                        t_ok = await download_file(session, post.url, temp_thumb)

                    if v_ok:
                        clean_caption = (post.caption or "").strip()[:80]
                        caption = (
                            f"🏋️ <b>{clean_caption if clean_caption else 'Exclusive Fitness Reel'}</b>\n\n"
                            f"🔥 <b>#{TARGET_USER} #Fitness #Reels #{code}</b>\n"
                            f"👑 <b>Archive Channel:</b> @InstagramPremiumCollection"
                        )

                        uploaded = await send_to_telegram(
                            session,
                            temp_video,
                            temp_thumb if t_ok else None,
                            caption
                        )

                        if uploaded:
                            save_posted(code)
                            posted.add(code)
                            batch_count += 1
                            print(f"🚀 [Delivered] [{code}] | Total: {len(posted)}", flush=True)

                            # Progress alert every 50 reels
                            if batch_count % 50 == 0:
                                await send_status_alert(
                                    session,
                                    f"📈 <b>Progress Milestone:</b> {batch_count} new reels synced! (Total: {len(posted)})"
                                )

                    # 8.0s safe speed: Maximum rate that avoids Render Cloud IP 429 blocks
                    await asyncio.sleep(8.0)

                finally:
                    # Guaranteed memory & disk cleanup to prevent 512MB RAM overflow
                    if os.path.exists(temp_video):
                        os.remove(temp_video)
                    if os.path.exists(temp_thumb):
                        os.remove(temp_thumb)

            await send_status_alert(
                session,
                f"✅ <b>Night Sync Complete!</b>\nTarget @{TARGET_USER} has no more pending reels. Total archived: {len(posted)}"
            )
            print("💤 All posts reviewed. Sleeping 20 minutes before next check...", flush=True)
            await asyncio.sleep(1200)

        except Exception as e:
            err = str(e).lower()
            print(f"⚠️ Exception intercepted: {e}", flush=True)

            if "429" in err or "too many requests" in err or "please wait" in err:
                print("🛑 Rate limit encountered. Entering 10-minute silent cool-down...", flush=True)
                await asyncio.sleep(600)
            else:
                print("🔄 Network glitch encountered. Auto-resuming in 60 seconds...", flush=True)
                await asyncio.sleep(60)

async def handle_ping(request):
    return web.Response(text="Immortal Harvester Active 24/7!")

async def start_app():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    print(f"🌐 Keep-Alive Web Server active on port {PORT}", flush=True)

    async with aiohttp.ClientSession() as session:
        await immortal_harvester(session)

if __name__ == "__main__":
    asyncio.run(start_app())
