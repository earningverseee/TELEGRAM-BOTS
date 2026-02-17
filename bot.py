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
files_collection = db["files"]
users_collection = db["users"]

app = Client("bot", api_id=api_id, api_hash=api_hash, bot_token=bot_token)

# ===== Save User =====
async def save_user(user_id):
    if not users_collection.find_one({"user_id": user_id}):
        users_collection.insert_one({"user_id": user_id})


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
    btn = []
    for i, ch in enumerate(CHANNELS, start=1):
        ch = ch.strip()
        btn.append(
            [InlineKeyboardButton(f"📢 Join Channel {i}", url=f"https://t.me/{ch.replace('@','')}")]
        )
    btn.append([InlineKeyboardButton("🔄 Try Again", callback_data="retry")])
    return InlineKeyboardMarkup(btn)


# ===== START COMMAND =====
@app.on_message(filters.command("start"))
async def start(client, message):
    user_id = message.from_user.id
    await save_user(user_id)

    key = message.command[1] if len(message.command) > 1 else None

    joined = await check_join(client, user_id)
    if not joined:
        await message.reply(
            "🚨 You must join all channels to use this bot.",
            reply_markup=join_buttons()
        )
        return

    if key:
        data = files_collection.find_one({"key": key})

        if data:
            # Backward compatibility
            if "files" in data:
                file_list = data["files"]
            elif "file_id" in data:
                file_list = [data["file_id"]]
            else:
                await message.reply("❌ File data corrupted.")
                return

            sent_messages = []
            for file_id in file_list:
                sent = await message.reply_cached_media(
                    file_id,
                    protect_content=True  # Anti-forward
                )
                sent_messages.append(sent)

            if DELETE_TIME > 0:
                await asyncio.sleep(DELETE_TIME)
                for msg in sent_messages:
                    await msg.delete()
        else:
            await message.reply("❌ File not found.")
        return

    await message.reply("✅ You are verified!")


# ===== Retry Button =====
@app.on_callback_query(filters.regex("retry"))
async def retry(client, callback_query):
    user_id = callback_query.from_user.id

    joined = await check_join(client, user_id)
    if not joined:
        await callback_query.answer("❌ Join all channels first!", show_alert=True)
        return

    await callback_query.message.edit("✅ You are verified now!")


# ===== Admin Upload Single =====
@app.on_message((filters.video | filters.photo) & filters.user(ADMIN))
async def save_single_file(client, message):
    if message.video:
        file_id = message.video.file_id
    elif message.photo:
        file_id = message.photo.file_id
    else:
        return

    key = str(uuid.uuid4())[:8]

    files_collection.insert_one({
        "key": key,
        "files": [file_id]
    })

    link = f"https://t.me/{BOT_USERNAME}?start={key}"
    await message.reply(f"✅ File saved!\n🔗 Link:\n{link}")


# ===== Admin Upload Bundle (Album) =====
@app.on_message(filters.media_group & filters.user(ADMIN))
async def save_bundle(client, messages):
    file_ids = []

    for msg in messages:
        if msg.video:
            file_ids.append(msg.video.file_id)
        elif msg.photo:
            file_ids.append(msg.photo.file_id)

    if not file_ids:
        return

    key = str(uuid.uuid4())[:8]

    files_collection.insert_one({
        "key": key,
        "files": file_ids
    })

    link = f"https://t.me/{BOT_USERNAME}?start={key}"
    await messages[0].reply(f"✅ Bundle saved!\n🔗 Link:\n{link}")


# ===== ADMIN DASHBOARD =====

@app.on_message(filters.command("stats") & filters.user(ADMIN))
async def stats(client, message):
    total_files = files_collection.count_documents({})
    total_users = users_collection.count_documents({})
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
    result = files_collection.delete_one({"key": key})

    if result.deleted_count:
        await message.reply("✅ File deleted successfully.")
    else:
        await message.reply("❌ File not found.")


app.run()
