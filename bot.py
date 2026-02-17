from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import asyncio
import os
import uuid
from pymongo import MongoClient

# ===== ENV VARIABLES =====
api_id = int(os.environ.get("API_ID"))
api_hash = os.environ.get("API_HASH")
bot_token = os.environ.get("BOT_TOKEN")

BOT_USERNAME = os.environ.get("BOT_USERNAME")
ADMIN = int(os.environ.get("ADMIN"))
DELETE_TIME = int(os.environ.get("DELETE_TIME", 1200))
CHANNELS = os.environ.get("CHANNELS").split(",")

# ===== MongoDB Setup =====
mongo = MongoClient(os.environ.get("MONGO_URL"))
db = mongo["telegram_bot"]
files = db["files"]
users = db["users"]

app = Client("bot", api_id=api_id, api_hash=api_hash, bot_token=bot_token)

# ===== Save User =====
async def save_user(user_id):
    if not users.find_one({"user_id": user_id}):
        users.insert_one({"user_id": user_id})

# ===== Force Join Check =====
async def check_join(client, user_id):
    for ch in CHANNELS:
        ch = ch.strip()
        try:
            member = await client.get_chat_member(ch, user_id)
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

# ===== START COMMAND =====
@app.on_message(filters.command("start"))
async def start(client, message):
    try:
        user_id = message.from_user.id
        await save_user(user_id)

        key = message.command[1] if len(message.command) > 1 else None

        joined = await check_join(client, user_id)
        if not joined:
            await message.reply("🚨 Join all channels first.", reply_markup=join_buttons())
            return

        if not key:
            await message.reply("✅ You are verified!")
            return

        data = files.find_one({"key": key})
        if not data:
            await message.reply("❌ File not found.")
            return

        file_list = data.get("files") or [data.get("file_id")]

        sent_msgs = []
        for fid in file_list:
            msg = await client.send_cached_media(
                chat_id=message.chat.id,
                file_id=fid,
                protect_content=True
            )
            sent_msgs.append(msg)

        if DELETE_TIME > 0:
            await asyncio.sleep(DELETE_TIME)
            for m in sent_msgs:
                try:
                    await m.delete()
                except:
                    pass

    except Exception as e:
        await message.reply(f"⚠ Error: {str(e)}")

# ===== RETRY BUTTON =====
@app.on_callback_query(filters.regex("retry"))
async def retry(client, callback_query):
    joined = await check_join(client, callback_query.from_user.id)
    if not joined:
        await callback_query.answer("❌ Join first!", show_alert=True)
    else:
        await callback_query.message.edit("✅ Verified. Click link again.")

# ===== ADMIN UPLOAD (Single + Bundle Unified) =====
@app.on_message((filters.video | filters.photo) & filters.user(ADMIN))
async def upload(client, message):

    # ===== BUNDLE =====
    if message.media_group_id:
        try:
            media_group = await client.get_media_group(
                chat_id=message.chat.id,
                message_id=message.id
            )
        except:
            return

        if message.id != media_group[0].id:
            return

        file_ids = []
        for msg in media_group:
            if msg.video:
                file_ids.append(msg.video.file_id)
            elif msg.photo:
                file_ids.append(msg.photo.file_id)

        key = str(uuid.uuid4())[:8]

        files.insert_one({
            "key": key,
            "files": file_ids
        })

        link = f"https://t.me/{BOT_USERNAME}?start={key}"
        await message.reply(f"✅ Bundle saved.\n🔗 {link}")
        return

    # ===== SINGLE FILE =====
    if message.video:
        fid = message.video.file_id
    else:
        fid = message.photo.file_id

    key = str(uuid.uuid4())[:8]

    files.insert_one({
        "key": key,
        "files": [fid]
    })

    link = f"https://t.me/{BOT_USERNAME}?start={key}"
    await message.reply(f"✅ Saved.\n🔗 {link}")

# ===== ADMIN DASHBOARD =====

@app.on_message(filters.command("stats") & filters.user(ADMIN))
async def stats(client, message):
    total_files = files.count_documents({})
    total_users = users.count_documents({})
    await message.reply(
        f"📊 Admin Dashboard\n\n"
        f"Total Files: {total_files}\n"
        f"Total Users: {total_users}"
    )

@app.on_message(filters.command("delete") & filters.user(ADMIN))
async def delete_file(client, message):
    if len(message.command) < 2:
        await message.reply("Usage: /delete filekey")
        return

    key = message.command[1]
    result = files.delete_one({"key": key})

    if result.deleted_count:
        await message.reply("✅ File deleted.")
    else:
        await message.reply("❌ File not found.")

@app.on_message(filters.command("list") & filters.user(ADMIN))
async def list_files(client, message):
    recent = files.find().sort("_id", -1).limit(10)
    text = "📁 Recent Files:\n\n"
    for doc in recent:
        text += f"{doc['key']}\n"
    await message.reply(text)

app.run()
