import os
import random
import logging
import asyncio
import aiosqlite
from aiohttp import web

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    Message, 
    CallbackQuery, 
    InlineKeyboardMarkup, 
    InlineKeyboardButton, 
    ChatMemberUpdated,
    ReactionTypeEmoji
)
from aiogram.filters.chat_member_updated import ChatMemberUpdatedFilter, ADMINISTRATOR, KICKED, LEFT

# --- তোমার নতুন তথ্যসমূহ ---
BOT_TOKEN = "8524155791:AAFTtD0aieHOwTireiEMLhOE3nsnTR97Wmc"
REQUIRED_CHANNEL = "@maxcommunity100pr"
CHANNEL_LINK = "https://t.me/maxcommunity100pr"

# ডিফল্ট রিঅ্যাকশন তালিকা
DEFAULT_EMOJIS = ["👍", "❤️", "🔥", "🥰", "👏", "😁", "🎉", "🤩", "🙏", "👌"]

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# গ্লোবাল বটের ইউজারনেম
BOT_USERNAME = ""

# --- ডাটাবেজ সেটআপ ---
async def init_db():
    async with aiosqlite.connect("database.db") as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS channels (
                channel_id INTEGER PRIMARY KEY,
                owner_id INTEGER
            )
        """)
        await db.commit()

async def add_channel_db(channel_id: int, owner_id: int):
    async with aiosqlite.connect("database.db") as db:
        await db.execute("INSERT OR REPLACE INTO channels (channel_id, owner_id) VALUES (?, ?)", (channel_id, owner_id))
        await db.commit()

async def remove_channel_db(channel_id: int):
    async with aiosqlite.connect("database.db") as db:
        await db.execute("DELETE FROM channels WHERE channel_id = ?", (channel_id,))
        await db.commit()

async def get_channel_owner(channel_id: int):
    async with aiosqlite.connect("database.db") as db:
        async with db.execute("SELECT owner_id FROM channels WHERE channel_id = ?", (channel_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

# --- মেম্বারশিপ যাচাই ---
async def is_subscribed(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(REQUIRED_CHANNEL, user_id)
        return member.status in ["creator", "administrator", "member"]
    except Exception as e:
        logging.error(f"Membership check error: {e}")
        return False

# --- /start হ্যান্ডলার ---
@dp.message(CommandStart())
async def start_handler(message: Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Join Channel / চ্যানেলে জয়েন করুন", url=CHANNEL_LINK)],
        [InlineKeyboardButton(text="✅ Verify / যাচাই করুন", callback_data="verify_sub")]
    ])
    text = (
        "👋 **স্বাগতম! / Welcome!**\n\n"
        "বটটি ব্যবহার করতে প্রথমে নিচের চ্যানেলে জয়েন করুন।\n"
        "_To use this bot, please join our channel first._"
    )
    await message.answer(text, reply_markup=keyboard, parse_mode="Markdown")

# --- ভেরিফাই বাটন ---
@dp.callback_query(F.data == "verify_sub")
async def verify_callback(call: CallbackQuery):
    user_id = call.from_user.id
    if await is_subscribed(user_id):
        add_url = f"https://t.me/{BOT_USERNAME}?startchannel=true&admin=post_messages"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Add to Channel / চ্যানেলে অ্যাড করুন", url=add_url)]
        ])
        text = (
            "✅ **ভেরিফিকেশন সফল হয়েছে! / Verification Successful!**\n\n"
            "এবার নিচের বাটনে চাপ দিয়ে আপনার চ্যানেলে বটটিকে **Admin** হিসেবে যুক্ত করুন।\n"
            "_Now click the button below to add the bot as an Admin to your channel._"
        )
        await call.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")
    else:
        await call.answer("❌ আপনি এখনো জয়েন করেননি! আগে চ্যানেলে জয়েন করুন।", show_alert=True)

# --- চ্যানেলে বট অ্যাডমিন হলে সেভ করা ---
@dp.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=ADMINISTRATOR))
async def bot_added(event: ChatMemberUpdated):
    if event.chat.type == "channel":
        owner_id = event.from_user.id
        channel_id = event.chat.id
        await add_channel_db(channel_id, owner_id)
        logging.info(f"Bot added to channel {channel_id} by owner {owner_id}")

# --- বট অ্যাডমিন থেকে রিমুভ হলে মুছে ফেলা ---
@dp.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=KICKED | LEFT))
async def bot_removed(event: ChatMemberUpdated):
    if event.chat.type == "channel":
        await remove_channel_db(event.chat.id)
        logging.info(f"Bot removed from channel {event.chat.id}")

# --- নতুন পোস্টে স্বয়ংক্রিয় রিঅ্যাকশন ---
@dp.channel_post()
async def auto_reaction(post: Message):
    channel_id = post.chat.id
    owner_id = await get_channel_owner(channel_id)
    
    # মালিক এখনও স্পনসর চ্যানেলে আছে কি না চেক
    if owner_id and not await is_subscribed(owner_id):
        return

    # রিঅ্যাকশন নির্বাচন
    chosen_emoji = random.choice(DEFAULT_EMOJIS)
    try:
        chat = await bot.get_chat(channel_id)
        if chat.available_reactions:
            allowed = [r.emoji for r in chat.available_reactions if hasattr(r, 'emoji') and r.emoji]
            if allowed:
                chosen_emoji = random.choice(allowed)
    except Exception:
        pass

    # রিঅ্যাকশন পাঠানো
    try:
        await bot.set_message_reaction(
            chat_id=channel_id,
            message_id=post.message_id,
            reaction=[ReactionTypeEmoji(emoji=chosen_emoji)]
        )
    except Exception as e:
        # ব্যাকআপ ট্রাই (👍)
        try:
            await bot.set_message_reaction(
                chat_id=channel_id,
                message_id=post.message_id,
                reaction=[ReactionTypeEmoji(emoji="👍")]
            )
        except Exception:
            logging.error(f"Failed to react: {e}")

# --- Render সার্ভার টিকিয়ে রাখার ফেক ওয়েব সার্ভার ---
async def ping_handler(request):
    return web.Response(text="Bot is running alive 24/7!")

async def start_web():
    app = web.Application()
    app.router.add_get('/', ping_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

# --- মূল রানার ---
async def main():
    global BOT_USERNAME
    me = await bot.get_me()
    BOT_USERNAME = me.username
    logging.info(f"Bot started successfully as @{BOT_USERNAME}")

    await init_db()
    await start_web()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
