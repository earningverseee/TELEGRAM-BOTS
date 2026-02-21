from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait, RPCError
import asyncio
import os
import uuid
import time
from pymongo import MongoClient

# ===== ENV =====
api_id = int(os.environ.get("API_ID"))
api_hash = os.environ.get("API_HASH")
bot_token = os.environ.get("BOT_TOKEN")

BOT_USERNAME = os.environ.get("BOT_USERNAME")
ADMIN = int(os.environ.get("ADMIN"))
DELETE_TIME = int(os.environ.get("DELETE_TIME", 900))
CHANNELS = os.environ.get("CHANNELS").split(",")

# ===== Mongo (Optimized Pool) =====
mongo = MongoClient(os.environ.get("MONGO_URL"), maxPoolSize=10)
db = mongo["telegram_bot"]
files = db["files"]
users = db["users"]
deletions = db["deletions"]

app = Client("bot", api_id=api_id, api_hash=api_hash, bot_token=bot_token)

# ===== Verified Cache =====
verified_users = set()

# ===== Safe Telegram Call =====
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

# ===== Save User =====
async def save_user(user_id):
    if not users.find_one({"user_id": user_id}):
        users.insert_one({"user_id": user_id})

# ===== Force Join =====
async def check_join(client, user_id):
    for ch in CHANNELS:
        try:
            member = await client.get_chat_member(ch.strip(), user_id)
            if member.status in ["left", "kicked"]:
                return False
        except:
            return False
    return True

def join_buttons():
    buttons = []
    for i, ch in enumerate(CHANNELS, start=1):
        buttons.append([
            InlineKeyboardButton(
                f"📢 Join Channel {i}",
                url=f"https://t.me/{ch.strip().replace('@','')}"
            )
        ])
    buttons.append([InlineKeyboardButton("🔄 Try Again", callback_data="retry")])
    return InlineKeyboardMarkup(buttons)

# ===== START =====
@app.on_message(filters.command("start"))
async def start(client, message):

    if not message.from_user:
        return

    user_id = message.from_user.id
    await save_user(user_id)

    key = message.command[1] if len(message.command) > 1 else None

    # ===== Join Cache =====
    if user_id in verified_users:
        joined = True
    else:
        joined = await check_join(client, user_id)
        if joined:
            verified_users.add(user_id)

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

    file_list = data.get("files") or [data.get("file_id")]

    sent_msgs = []
    for fid in file_list:
        await asyncio.sleep(0.7)
        msg = await safe_call(
            client.send_cached_media,
            message.chat.id,
            fid,
            protect_content=True
        )
        if msg:
            sent_msgs.append(msg)

    # ===== Persistent Delete Schedule =====
    expire_time = int(time.time()) + DELETE_TIME

    for m in sent_msgs:
        deletions.insert_one({
            "chat_id": message.chat.id,
            "message_id": m.id,
            "expire_at": expire_time
        })

# ===== RETRY =====
@app.on_callback_query(filters.regex("retry"))
async def retry(client, callback_query):

    if not callback_query.from_user:
        return

    user_id = callback_query.from_user.id

    if user_id in verified_users:
        await safe_call(
            callback_query.message.edit,
            "✅ Verified. Click link again."
        )
        return

    joined = await check_join(client, user_id)

    if joined:
        verified_users.add(user_id)
        await safe_call(
            callback_query.message.edit,
            "✅ Verified. Click link again."
        )
    else:
        await safe_call(
            callback_query.answer,
            "❌ Join all channels first!",
            show_alert=True
        )

# ===== ADMIN UPLOAD =====
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
            files.insert_one({"key": key, "files": file_ids})

            link = f"https://t.me/{BOT_USERNAME}?start={key}"
            await safe_call(message.reply, f"✅ Bundle saved.\n🔗 {link}")
            return

        fid = message.video.file_id if message.video else message.photo.file_id

        key = str(uuid.uuid4())[:8]
        files.insert_one({"key": key, "files": [fid]})

        link = f"https://t.me/{BOT_USERNAME}?start={key}"
        await safe_call(message.reply, f"✅ Saved.\n🔗 {link}")

    except:
        pass

# ===== DELETE WORKER (Survives Restart) =====
async def delete_worker():
    while True:
        now = int(time.time())
        expired = deletions.find({"expire_at": {"$lte": now}})

        for doc in expired:
            try:
                await app.delete_messages(
                    doc["chat_id"],
                    doc["message_id"]
                )
            except:
                pass

            deletions.delete_one({"_id": doc["_id"]})

        await asyncio.sleep(30)

@app.on_startup()
async def startup():
    asyncio.create_task(delete_worker())

# ===== ADMIN STATS =====
@app.on_message(filters.command("stats") & filters.user(ADMIN))
async def stats(client, message):
    await safe_call(
        message.reply,
        f"📊 Stats\n\nFiles: {files.count_documents({})}\nUsers: {users.count_documents({})}"
    )

app.run()
