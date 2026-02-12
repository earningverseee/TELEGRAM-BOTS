from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import asyncio
import os

api_id = int(os.environ.get("API_ID"))
api_hash = os.environ.get("API_HASH")
bot_token = os.environ.get("BOT_TOKEN")

# 👉 PUT YOUR TWO CHANNEL USERNAMES
CHANNELS = ["@JustvoicemagicXdeals", "@earningverseeebackup"]

app = Client("bot", api_id=api_id, api_hash=api_hash, bot_token=bot_token)


async def check_join(client, user_id):
    for ch in CHANNELS:
        try:
            member = await client.get_chat_member(ch, user_id)
            if member.status in ["left", "kicked"]:
                return False
        except:
            return False
    return True


def join_buttons():
    btn = []

    for ch in CHANNELS:
        btn.append(
            [InlineKeyboardButton(f"📢 Join {ch}", url=f"https://t.me/{ch.replace('@','')}")]
        )

    btn.append([InlineKeyboardButton("🔄 Try Again", callback_data="retry")])

    return InlineKeyboardMarkup(btn)


@app.on_message(filters.command("start"))
async def start(client, message):
    user_id = message.from_user.id

    joined = await check_join(client, user_id)

    if not joined:
        await message.reply(
            "🚨 You must join all channels to use this bot.",
            reply_markup=join_buttons()
        )
        return

    sent = await message.reply_text("✅ Access granted!")

    await asyncio.sleep(1200)
    await sent.delete()


@app.on_callback_query(filters.regex("retry"))
async def retry(client, callback_query):
    user_id = callback_query.from_user.id

    joined = await check_join(client, user_id)

    if not joined:
        await callback_query.answer("❌ Join all channels first!", show_alert=True)
        return

    await callback_query.message.edit("✅ Access granted!")

    await asyncio.sleep(1200)
    await callback_query.message.delete()


app.run()
