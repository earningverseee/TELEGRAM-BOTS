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

app = Client("bot", api_id=api_id, api_hash=api_hash, bot_token=bot_token)

# ===== Force Join =====
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
        key = message.command[1] if len(message.command) > 1 else None

        joined = await check_join(client, user_id)
        if not joined:
            await message.reply(
                "🚨 You must join all channels to use this bot.",
                reply_markup=join_buttons()
            )
            return

        if not key:
            await message.reply("✅ You are verified!")
            return

        data = files.find_one({"key": key})

        if not data:
            await message.reply("❌ File not found.")
            return

        if "files" in data:
            file_list = data["files"]
        elif "file_id" in data:
            file_list = [data["file_id"]]
        else:
            await message.reply("❌ File data corrupted.")
            return

        sent_messages = []
        for fid in file_list:
            msg = await client.send_cached_media(
                chat_id=message.chat.id,
                file_id=fid,
                protect_content=True
            )
            sent_messages.append(msg)

        if DELETE_TIME > 0:
            await asyncio.sleep(DELETE_TIME)
            for m in sent_messages:
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
        await callback_query.answer("❌ Join all channels first!", show_alert=True)
    else:
        await callback_query.message.edit("✅ You are verified now!")

# ===== ADMIN UPLOAD =====
@app.on_message((filters.video | filters.photo) & filters.user(ADMIN))
async def upload_file(client, message):
    try:
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

        await message.reply(f"✅ File saved!\n🔗 Link:\n{link}")

    except Exception as e:
        await message.reply(f"⚠ Upload Error: {str(e)}")

app.run()
