from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait, RPCError
import asyncio
import os
import uuid
from pymongo import MongoClient

# ===== ENV =====
api_id = int(os.environ.get("API_ID"))
api_hash = os.environ.get("API_HASH")
bot_token = os.environ.get("BOT_TOKEN")

BOT_USERNAME = os.environ.get("BOT_USERNAME")
ADMIN = int(os.environ.get("ADMIN"))
DELETE_TIME = int(os.environ.get("DELETE_TIME", 1200))
CHANNELS = os.environ.get("CHANNELS").split(",")

# ===== Mongo (Single Client Only) =====
mongo = MongoClient(os.environ.get("MONGO_URL"), maxPoolSize=50)
db = mongo["telegram_bot"]
files = db["files"]
users = db["users"]

app = Client("bot", api_id=api_id, api_hash=api_hash, bot_token=bot_token)

# ===== Safe Send Wrapper =====
async def safe_send(func, *args, **kwargs):
    try:
        return await func(*args, **kwargs)
    except FloodWait as e:
        await asyncio.sleep(e.value)
        return await func(*args, **kwargs)
    except RPCError:
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
    btn = []
    for i, ch in enumerate(CHANNELS, start=1):
        btn.append([
            InlineKeyboardButton(
                f"📢 Join Channel {i}",
                url=f"https://t.me/{ch.strip().replace('@','')}"
            )
        ])
    btn.append([InlineKeyboardButton("🔄 Try Again", callback_data="retry")])
    return InlineKeyboardMarkup(btn)

# ===== START =====
@app.on_message(filters.command("start"))
async def start(client, message):
    try:
        user_id = message.from_user.id
        await save_user(user_id)

        key = message.command[1] if len(message.command) > 1 else None

        if not await check_join(client, user_id):
            await safe_send(
                message.reply,
                "🚨 Join channels first.",
                reply_markup=join_buttons()
            )
            return

        if not key:
            await safe_send(message.reply, "✅ Verified.")
            return

        data = files.find_one({"key": key})
        if not data:
            await safe_send(message.reply, "❌ File not found.")
            return

        file_list = data.get("files") or [data.get("file_id")]

        sent = []
        for fid in file_list:
            msg = await safe_send(
                client.send_cached_media,
                message.chat.id,
                fid,
                protect_content=True
            )
            if msg:
                sent.append(msg)

        if DELETE_TIME > 0 and sent:
            await asyncio.sleep(DELETE_TIME)
            for m in sent:
                try:
                    await m.delete()
                except:
                    pass

    except Exception:
        pass  # prevents crash

# ===== RETRY =====
@app.on_callback_query(filters.regex("retry"))
async def retry(client, callback_query):
    if not await check_join(client, callback_query.from_user.id):
        await safe_send(
            callback_query.answer,
            "❌ Join first!",
            show_alert=True
        )
    else:
        await safe_send(
            callback_query.message.edit,
            "✅ Verified."
        )

# ===== ADMIN UPLOAD =====
@app.on_message((filters.video | filters.photo) & filters.user(ADMIN))
async def upload(client, message):
    try:
        if message.media_group_id:
            try:
                group = await client.get_media_group(message.chat.id, message.id)
            except:
                return

            if message.id != group[0].id:
                return

            fids = []
            for m in group:
                if m.video:
                    fids.append(m.video.file_id)
                elif m.photo:
                    fids.append(m.photo.file_id)

            key = str(uuid.uuid4())[:8]
            files.insert_one({"key": key, "files": fids})

            link = f"https://t.me/{BOT_USERNAME}?start={key}"
            await safe_send(message.reply, f"✅ Bundle saved.\n🔗 {link}")
            return

        # single
        fid = message.video.file_id if message.video else message.photo.file_id

        key = str(uuid.uuid4())[:8]
        files.insert_one({"key": key, "files": [fid]})

        link = f"https://t.me/{BOT_USERNAME}?start={key}"
        await safe_send(message.reply, f"✅ Saved.\n🔗 {link}")

    except Exception:
        pass

# ===== ADMIN DASHBOARD =====
@app.on_message(filters.command("stats") & filters.user(ADMIN))
async def stats(client, message):
    await safe_send(
        message.reply,
        f"📊 Stats\n\nFiles: {files.count_documents({})}\nUsers: {users.count_documents({})}"
    )

@app.on_message(filters.command("delete") & filters.user(ADMIN))
async def delete_file(client, message):
    if len(message.command) < 2:
        return
    key = message.command[1]
    files.delete_one({"key": key})
    await safe_send(message.reply, "✅ Deleted.")

app.run()
