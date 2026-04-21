from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait, RPCError
import asyncio
import os
import uuid
import time
from pymongo import MongoClient

# ================= ENV =================
api_id = int(os.environ.get("API_ID"))
api_hash = os.environ.get("API_HASH")
bot_token = os.environ.get("BOT_TOKEN")

BOT_USERNAME = os.environ.get("BOT_USERNAME")
ADMIN = int(os.environ.get("ADMIN"))
DELETE_TIME = int(os.environ.get("DELETE_TIME", 900))

CHANNELS = os.environ.get("CHANNELS", "").split(",")

CHANNEL_LINKS = os.environ.get("CHANNEL_LINKS")
CHANNEL_LINKS = CHANNEL_LINKS.split(",") if CHANNEL_LINKS else []

# ================= DATABASE =================
mongo = MongoClient(os.environ.get("MONGO_URL"), maxPoolSize=30)

db = mongo["telegram_bot"]
files = db["files"]
users = db["users"]
deletions = db["deletions"]

app = Client("bot", api_id=api_id, api_hash=api_hash, bot_token=bot_token)

worker_started = False

# ================= SAFE CALL =================
async def safe_call(func, *args, **kwargs):
    while True:
        try:
            return await func(*args, **kwargs)
        except FloodWait as e:
            await asyncio.sleep(e.value)
        except RPCError:
            return None
        except Exception:
            return None

# ================= DELETE WORKER =================
async def delete_worker():
    while True:
        try:
            now = int(time.time())
            expired = deletions.find({"expire_at": {"$lte": now}})

            for doc in expired:
                try:
                    await app.delete_messages(doc["chat_id"], doc["message_id"])
                except:
                    pass
                deletions.delete_one({"_id": doc["_id"]})
        except:
            pass

        await asyncio.sleep(30)

# ================= SAVE USER =================
async def save_user(user_id):
    if not users.find_one({"user_id": user_id}):
        users.insert_one({"user_id": user_id})

# ================= FORCE JOIN (ULTIMATE FIX) =================
async def check_join(user_id):
    for ch in CHANNELS:
        ch = ch.strip()
        if not ch:
            continue

        success = False

        for _ in range(3):  # retry 3 times
            try:
                if ch.startswith("@"):
                    chat = await app.get_chat(ch)
                    member = await app.get_chat_member(chat.id, user_id)
                else:
                    member = await app.get_chat_member(int(ch), user_id)

                if member.status not in ["left", "kicked"]:
                    success = True
                    break
                else:
                    return False

            except FloodWait as e:
                await asyncio.sleep(e.value)

            except:
                await asyncio.sleep(1)

        if not success:
            return False

    return True

# ================= JOIN BUTTONS =================
def join_buttons():
    buttons = []

    for i, link in enumerate(CHANNEL_LINKS, start=1):
        link = link.strip()
        if not link:
            continue

        buttons.append([
            InlineKeyboardButton(
                f"📢 Join Channel {i}",
                url=link
            )
        ])

    buttons.append([
        InlineKeyboardButton("🔄 Try Again", callback_data="retry")
    ])

    return InlineKeyboardMarkup(buttons)

# ================= START =================
@app.on_message(filters.command("start"))
async def start(client, message):

    global worker_started

    if not worker_started:
        asyncio.create_task(delete_worker())
        worker_started = True

    if not message.from_user:
        return

    user_id = message.from_user.id
    await save_user(user_id)

    key = message.command[1] if len(message.command) > 1 else None

    joined = await check_join(user_id)

    if not joined:
        await safe_call(
            message.reply,
            "🚨 Join all channels first.",
            reply_markup=join_buttons()
        )
        return

    if not key:
        await safe_call(message.reply, "✅ Verified.")
        return

    data = files.find_one({"key": key})
    if not data:
        await safe_call(message.reply, "❌ File not found.")
        return

    file_list = data.get("files", [])

    sent_msgs = []
    for fid in file_list:
        await asyncio.sleep(0.3)
        msg = await safe_call(
            client.send_cached_media,
            message.chat.id,
            fid,
            protect_content=True
        )
        if msg:
            sent_msgs.append(msg)

    expire_time = int(time.time()) + DELETE_TIME

    for m in sent_msgs:
        deletions.insert_one({
            "chat_id": message.chat.id,
            "message_id": m.id,
            "expire_at": expire_time
        })

# ================= RETRY (FIXED) =================
@app.on_callback_query(filters.regex("retry"))
async def retry(client, callback_query):

    if not callback_query.from_user:
        return

    user_id = callback_query.from_user.id

    # answer immediately
    try:
        await callback_query.answer()
    except:
        pass

    joined = await check_join(user_id)

    if joined:
        await safe_call(
            callback_query.message.edit,
            "✅ Verified. Click the link again."
        )
    else:
        try:
            await callback_query.answer(
                "❌ Join all channels first!",
                show_alert=True
            )
        except:
            pass

# ================= ADMIN UPLOAD =================
@app.on_message((filters.video | filters.photo) & filters.user(ADMIN))
async def upload(client, message):

    if not message.from_user:
        return

    try:
        if message.media_group_id:
            group = await client.get_media_group(message.chat.id, message.id)

            if message.id != group[0].id:
                return

            file_ids = []
            for m in group:
                if m.video:
                    file_ids.append(m.video.file_id)
                elif m.photo:
                    file_ids.append(m.photo.file_id)

            key = str(uuid.uuid4())[:8]
            files.insert_one({
                "key": key,
                "files": file_ids,
                "clicks": 0
            })

            link = f"https://t.me/{BOT_USERNAME}?start={key}"
            await safe_call(message.reply, f"✅ Bundle saved.\n🔗 {link}")
            return

        fid = message.video.file_id if message.video else message.photo.file_id
        key = str(uuid.uuid4())[:8]

        files.insert_one({
            "key": key,
            "files": [fid],
            "clicks": 0
        })

        link = f"https://t.me/{BOT_USERNAME}?start={key}"
        await safe_call(message.reply, f"✅ Saved.\n🔗 {link}")

    except:
        pass

# ================= ADMIN STATS =================
@app.on_message(filters.command("stats") & filters.user(ADMIN))
async def stats(client, message):
    await safe_call(
        message.reply,
        f"📊 Stats\n\nFiles: {files.count_documents({})}\nUsers: {users.count_documents({})}"
    )

# ================= RUN =================
app.run()
