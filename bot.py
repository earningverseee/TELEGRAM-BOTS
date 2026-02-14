from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import asyncio
import os
import uuid
from pymongo import MongoClient

api_id = int(os.environ.get("API_ID"))
api_hash = os.environ.get("API_HASH")
bot_token = os.environ.get("BOT_TOKEN")

BOT_USERNAME = os.environ.get("BOT_USERNAME")
ADMIN = int(os.environ.get("ADMIN"))
DELETE_TIME = int(os.environ.get("DELETE_TIME", 1200))

CHANNELS = os.environ.get("CHANNELS").split(",")

# MongoDB
mongo = MongoClient(os.environ.get("MONGO_URL"))
db = mongo["telegram_bot"]
files = db["files"]

app = Client("bot", api_id=api_id, api_hash=api_hash, bot_token=bot_token)


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
        ch = ch.strip()
        btn.append(
            [InlineKeyboardButton(f"📢 Join Channel {i}", url=f"https://t.me/{ch.replace('@','')}")]
        )

    btn.append([InlineKeyboardButton("🔄 Try Again", callback_data="retry")])
    return InlineKeyboardMarkup(btn)


@app.on_message(filters.command("start"))
async def start(client, message):
    user_id = message.from_user.id
    key = message.command[1] if len(message.command) > 1 else None

    joined = await check_join(client, user_id)

    if not joined:
        await message.reply(
            "🚨 You must join all channels to use this bot.",
            reply_markup=join_buttons()
        )
        return

    if key:
        data = files.find_one({"key": key})

        if data:
            sent = await message.reply_video(data["file_id"])
            await asyncio.sleep(DELETE_TIME)
            await sent.delete()
        else:
            await message.reply("❌ File not found.")
        return

    await message.reply("✅ You are verified!")


@app.on_callback_query(filters.regex("retry"))
async def retry(client, callback_query):
    user_id = callback_query.from_user.id

    joined = await check_join(client, user_id)

    if not joined:
        await callback_query.answer("❌ Join all channels first!", show_alert=True)
        return

    await callback_query.message.edit("✅ You are verified now!")


# ADMIN upload
@app.on_message(filters.video & filters.user(ADMIN))
async def save_file(client, message):
    file_id = message.video.file_id

    key = str(uuid.uuid4())[:8]

    files.insert_one({
        "key": key,
        "file_id": file_id
    })

    link = f"https://t.me/{BOT_USERNAME}?start={key}"

    await message.reply(f"✅ File saved permanently!\n🔗 Link:\n{link}")


app.run()
