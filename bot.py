from pyrogram import Client, filters
import asyncio
import os

api_id = int(os.environ.get("API_ID"))
api_hash = os.environ.get("API_HASH")
bot_token = os.environ.get("BOT_TOKEN")

CHANNELS = ["@JustvoicemagicXdeals", "@earningverseeebackup"]

app = Client("bot", api_id=api_id, api_hash=api_hash, bot_token=bot_token)

@app.on_message(filters.command("start"))
async def start(client, message):
    user_id = message.from_user.id

    for ch in CHANNELS:
    try:
        member = await client.get_chat_member(ch, user_id)
        if member.status in ["left", "kicked"]:
            await message.reply(f"Join {ch} and press /start again.")
            return
    except:
        await message.reply(f"Join {ch} and press /start again.")
        return

    sent = await message.reply_text("Access granted ✅")

    await asyncio.sleep(1200)
    await sent.delete()

app.run()
