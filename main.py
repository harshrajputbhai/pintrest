import nest_asyncio
nest_asyncio.apply()

import os
import asyncio
import pyrogram.utils
from pyrogram import Client, enums
from pyrogram.errors import FloodWait

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

API_ID = 37025158
API_HASH = "4bfdef0d097d4d7d97d5b61a077a0962"
TARGET_CHANNEL_ID = -1004468017163  # Aapka Warehouse / Reels Channel

# Public Reels Channels (Aesthetic, Baddie, Desi Saree content)
SOURCE_CHANNELS = [
    "Hot_Reels_Hub",
    "Desi_Baddies_Official",
    "Saree_Lovers_Club",
    "Instagram_Trending_Reels_HQ"
]

HISTORY_FILE = "posted_tg_reels.txt"

def load_posted():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r") as f:
            return set(line.strip() for line in f if line.strip())
    return set()

def save_posted(msg_id_str):
    with open(HISTORY_FILE, "a") as f:
        f.write(f"{msg_id_str}\n")

app = Client("account_revert_session", api_id=API_ID, api_hash=API_HASH)

async def harvest_reels():
    async with app:
        posted = load_posted()
        print(f"🟢 Reels Harvester Started! Posting directly to: {TARGET_CHANNEL_ID}\n")

        for ch in SOURCE_CHANNELS:
            print(f"🔎 Scanning Channel: @{ch}...")
            try:
                # Har channel ki pichli 100 media posts scan karein
                async for msg in app.get_chat_history(ch, limit=100):
                    if msg.video:
                        unique_key = f"{ch}_{msg.id}"
                        if unique_key in posted:
                            continue

                        caption = (
                            "✨ <b>Exclusive Viral Reel</b>\n\n"
                            "🔥 #Baddie #DesiSaree #TrendingReels\n"
                            "👑 <b>Join:</b> @InstagramPremiumCollection"
                        )

                        while True:
                            try:
                                # Clean copy bina kisi forward tag ke
                                await msg.copy(
                                    chat_id=TARGET_CHANNEL_ID,
                                    caption=caption,
                                    parse_mode=enums.ParseMode.HTML
                                )
                                print(f"✅ Video Sent from @{ch} (ID: {msg.id})")
                                save_posted(unique_key)
                                posted.add(unique_key)
                                break
                            except FloodWait as e:
                                print(f"⏳ FloodWait: Waiting {e.value} seconds...")
                                await asyncio.sleep(e.value)
                            except Exception as pe:
                                print(f"⚠️ Upload error: {pe}")
                                break

                        # Channel spamming avoid karne ke liye safe gap
                        await asyncio.sleep(6)
            except Exception as e:
                print(f"⚠️ Error reading @{ch}: {e}")

        print("\n🏁 Saari channels se videos harvest ho chuki hain!")

await harvest_reels()
