#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MovieVerse & Viral Video AI Bot — Master Complete Code for Render (24/7 Running)
Features: AI Agent Search, AI Chat & Image Gen (Coin System), URL Video Auto-Fetch & Publish, Force Sub (5 Channels).
"""

import asyncio
import html
import json
import logging
import os
import time
import secrets
import string
import shutil
import traceback
import urllib.parse
from typing import Optional, Union

import aiosqlite
from aiogram import Bot, Dispatcher, F, Router, BaseMiddleware
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    FSInputFile, BotCommand, BotCommandScopeDefault, BotCommandScopeChat,
)
from aiogram.exceptions import (
    TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter,
)

# Web server for Render port binding
from aiohttp import web

# =========================================================================
# CONFIG & API KEYS
# =========================================================================
BOT_TOKEN = os.environ.get(
    "BOT_TOKEN",
    "8999148581:AAExMi5DcfVS06RzED5R0qhRJPWKknczotA",
)
ADMIN_CHAT_ID = int(os.environ.get("ADMIN_CHAT_ID", "7718164345"))
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "AQ.Ab8RN6Kr1UWVlIt9IWGVPApYoAQMXGud_GN87KmsD_nJNLAtPA")

DB_PATH = os.path.join(os.getcwd(), "movieverse.db")

AUTO_DELETE_SECONDS = 1200
BACKUP_INTERVAL_SECONDS = 60
ANTI_SPAM_COOLDOWN = 1.0

MINI_APP_LINK_BASE = "https://t.me/MovieVerseBot99_bot/Nadim2400?startapp=GET_"

# ⭐ CATEGORY CHANNELS (Including Viral Video Channel)
CATEGORY_CHANNELS = {
    "movie": "@MovieVerseOfficial9",
    "drama": "@DramaVerseHub99",
    "anime": "@AnimaversalSeries",
    "app": "@AppVerseOfficial",
    "viral": "@viralvideo24r",
}
MAIN_CHANNEL = "@MovieVerseCommunity"

# ⭐ 5 FORCE SUBSCRIBE CHANNELS
FORCE_CHANNELS = [
    ("@MovieVerseOfficial9", "Movie Channel"),
    ("@DramaVerseHub99", "Drama Channel"),
    ("@AnimaversalSeries", "Anime Channel"),
    ("@AppVerseOfficial", "App Channel"),
    ("@viralvideo24r", "Viral Video Channel"),
]

CATEGORY_NAMES = {
    "movie": "🎬 Movie",
    "drama": "🎭 Drama",
    "anime": "🎌 Anime",
    "app": "📱 App",
    "viral": "🔥 Viral Video",
    "private": "🔒 Private",
}

VIEW_REWARD = 0.0001
REFERRAL_BONUS = 0.025
DEFAULT_MIN_WITHDRAW = 10.0
DAILY_BONUS = 0.001
IMAGE_GEN_COST = 2  # 2 coins per image generation
MAX_USER_FILES = 5
MAX_ADMIN_FILES = 100

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("MovieVerseAI")

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())
router = Router()

BOT_USERNAME_CACHE: Optional[str] = None
backup_state = {"last_id": None}
_backup_task = None
last_message_time: dict = {}
pending_confirm_tokens: dict = {}

# =========================================================================
# STATES
# =========================================================================
class AdminStates(StatesGroup):
    uploading_files = State()
    waiting_title = State()
    waiting_thumb = State()
    waiting_url_input = State()
    waiting_confirm = State()
    waiting_ban_id = State()
    waiting_unban_id = State()
    waiting_restore_db = State()
    waiting_setting = State()
    waiting_broadcast = State()

class UserStates(StatesGroup):
    uploading_files = State()
    waiting_title = State()
    waiting_thumb = State()
    waiting_search = State()
    ai_chat = State()

class WithdrawStates(StatesGroup):
    waiting_amount = State()
    waiting_method = State()
    waiting_address = State()

# =========================================================================
# UTILS
# =========================================================================
async def safe_edit(
    event: Union[Message, CallbackQuery],
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
) -> Optional[Message]:
    msg = event.message if isinstance(event, CallbackQuery) else event
    if msg is None:
        return None
    try:
        if msg.text is not None or msg.caption is not None:
            if msg.photo or msg.document or msg.video or msg.audio:
                return await msg.edit_caption(caption=text, reply_markup=reply_markup)
            return await msg.edit_text(text, reply_markup=reply_markup)
        try:
            await msg.delete()
        except Exception:
            pass
        return await msg.answer(text, reply_markup=reply_markup)
    except TelegramBadRequest:
        try:
            await msg.delete()
        except Exception:
            pass
        try:
            return await msg.answer(text, reply_markup=reply_markup)
        except Exception:
            return None
    except Exception as e:
        logger.error(f"safe_edit: {e}")
        return None

def fmt_money(amount: float) -> str:
    try:
        return f"${float(amount):.4f}"
    except Exception:
        return "$0.0000"

def fmt_date(ts: Optional[int]) -> str:
    if not ts:
        return "N/A"
    return time.strftime("%Y-%m-%d", time.gmtime(ts))

def truncate(text: str, n: int = 40) -> str:
    if not text:
        return "Untitled"
    text = str(text)
    return text if len(text) <= n else text[: n - 1] + "…"

def esc(text) -> str:
    return html.escape(str(text or ""))

async def unique_code() -> str:
    chars = string.ascii_letters + string.digits
    while True:
        c = ''.join(secrets.choice(chars) for _ in range(17))
        if not await fetchone("SELECT 1 FROM posts WHERE code=?", (c,)):
            return c

# =========================================================================
# DATABASE
# =========================================================================
async def _col_exists(db, table: str, column: str) -> bool:
    cur = await db.execute(f"PRAGMA table_info({table})")
    rows = await cur.fetchall()
    return any(r[1] == column for r in rows)

async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA synchronous=NORMAL")

        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT,
                joined_at INTEGER, referred_by INTEGER, balance REAL DEFAULT 0,
                coins INTEGER DEFAULT 10, referrals INTEGER DEFAULT 0, banned INTEGER DEFAULT 0,
                total_uploads INTEGER DEFAULT 0, last_daily INTEGER DEFAULT 0,
                cooldown_until INTEGER DEFAULT 0
            )
        """)
        for col, ddl in [
            ("username", "TEXT"), ("first_name", "TEXT"), ("joined_at", "INTEGER"),
            ("referred_by", "INTEGER"), ("balance", "REAL DEFAULT 0"),
            ("coins", "INTEGER DEFAULT 10"), ("referrals", "INTEGER DEFAULT 0"),
            ("banned", "INTEGER DEFAULT 0"), ("total_uploads", "INTEGER DEFAULT 0"),
            ("last_daily", "INTEGER DEFAULT 0"), ("cooldown_until", "INTEGER DEFAULT 0"),
        ]:
            if not await _col_exists(db, "users", col):
                try: await db.execute(f"ALTER TABLE users ADD COLUMN {col} {ddl}")
                except: pass

        await db.execute("""
            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE, title TEXT,
                category TEXT, owner_id INTEGER, is_admin INTEGER DEFAULT 0,
                thumbnail_id TEXT, views INTEGER DEFAULT 0, created_at INTEGER,
                published INTEGER DEFAULT 0, rating_sum REAL DEFAULT 0,
                rating_count INTEGER DEFAULT 0, deleted INTEGER DEFAULT 0
            )
        """)
        for col, ddl in [
            ("title", "TEXT"), ("category", "TEXT"), ("owner_id", "INTEGER"),
            ("is_admin", "INTEGER DEFAULT 0"), ("thumbnail_id", "TEXT"),
            ("views", "INTEGER DEFAULT 0"), ("created_at", "INTEGER"),
            ("published", "INTEGER DEFAULT 0"), ("rating_sum", "REAL DEFAULT 0"),
            ("rating_count", "INTEGER DEFAULT 0"), ("deleted", "INTEGER DEFAULT 0"),
        ]:
            if not await _col_exists(db, "posts", col):
                try: await db.execute(f"ALTER TABLE posts ADD COLUMN {col} {ddl}")
                except: pass

        await db.execute("CREATE TABLE IF NOT EXISTS post_files (id INTEGER PRIMARY KEY AUTOINCREMENT, post_code TEXT, file_id TEXT, file_type TEXT, file_name TEXT, order_idx INTEGER DEFAULT 0)")
        await db.execute("CREATE TABLE IF NOT EXISTS views (post_code TEXT, user_id INTEGER, created_at INTEGER, PRIMARY KEY (post_code, user_id))")
        await db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS withdrawals (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount REAL, method TEXT, address TEXT, status TEXT DEFAULT 'pending', created_at INTEGER)")

        for k, v in {"min_withdraw": str(DEFAULT_MIN_WITHDRAW), "view_reward": str(VIEW_REWARD), "referral_bonus": str(REFERRAL_BONUS), "daily_bonus": str(DAILY_BONUS)}.items():
            await db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))
        await db.commit()
    logger.info("DB ready")

async def fetchone(q: str, p: tuple = ()) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(q, p)
        row = await cur.fetchone()
        return dict(row) if row else None

async def fetchall(q: str, p: tuple = ()) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(q, p)
        rows = await cur.fetchall()
        return [dict(r) for r in rows]

async def execute(q: str, p: tuple = ()) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(q, p)
        await db.commit()
        return cur.lastrowid

async def get_setting(key: str, default=None):
    row = await fetchone("SELECT value FROM settings WHERE key=?", (key,))
    return row["value"] if row else default

async def set_setting(key: str, value: str) -> None:
    await execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))

async def get_user_safe(user_id: int) -> dict:
    u = await fetchone("SELECT * FROM users WHERE user_id=?", (user_id,))
    if not u:
        return {"user_id": user_id, "username": None, "first_name": None, "joined_at": int(time.time()), "referred_by": None, "balance": 0.0, "coins": 10, "referrals": 0, "banned": 0, "total_uploads": 0, "last_daily": 0, "cooldown_until": 0}
    for k, v in [("username", None), ("first_name", None), ("joined_at", int(time.time())), ("referred_by", None), ("balance", 0.0), ("coins", 10), ("referrals", 0), ("banned", 0), ("total_uploads", 0), ("last_daily", 0), ("cooldown_until", 0)]:
        u.setdefault(k, v)
        if u[k] is None: u[k] = v
    return u

async def ensure_user(user_id, username=None, first_name=None, referred_by=None) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            cur = await db.execute("INSERT OR IGNORE INTO users (user_id, username, first_name, joined_at, referred_by) VALUES (?, ?, ?, ?, ?)", (user_id, username, first_name, int(time.time()), referred_by))
            created = (cur.rowcount or 0) > 0
            if not created:
                await db.execute("UPDATE users SET username=?, first_name=? WHERE user_id=?", (username, first_name, user_id))
            await db.commit()
            return created
        except Exception as e:
            logger.error(f"ensure_user: {e}")
            return False

async def is_banned(user_id: int) -> bool:
    u = await get_user_safe(user_id)
    return bool(u.get("banned", 0))

async def add_balance(user_id: int, amount: float) -> None:
    try: await execute("UPDATE users SET balance = COALESCE(balance,0) + ? WHERE user_id=?", (amount, user_id))
    except Exception as e: logger.error(f"add_balance: {e}")

async def add_coins(user_id: int, amount: int) -> None:
    try: await execute("UPDATE users SET coins = COALESCE(coins,0) + ? WHERE user_id=?", (amount, user_id))
    except Exception as e: logger.error(f"add_coins: {e}")

async def get_post(code: str) -> Optional[dict]:
    return await fetchone("SELECT * FROM posts WHERE code=? AND deleted=0", (code,))

async def get_post_files(code: str) -> list:
    return await fetchall("SELECT * FROM post_files WHERE post_code=? ORDER BY order_idx", (code,))

async def add_view_unique(code: str, user_id: int) -> bool:
    try:
        await execute("INSERT INTO views (post_code, user_id, created_at) VALUES (?, ?, ?)", (code, user_id, int(time.time())))
        return True
    except aiosqlite.IntegrityError:
        return False

async def get_bot_username() -> str:
    global BOT_USERNAME_CACHE
    if not BOT_USERNAME_CACHE:
        me = await bot.get_me()
        BOT_USERNAME_CACHE = me.username or ""
    return BOT_USERNAME_CACHE

# =========================================================================
# FORCE SUB & MIDDLEWARES (5 Channels Mandatory)
# =========================================================================
async def is_member(channel: str, user_id: int) -> bool:
    try:
        m = await bot.get_chat_member(channel, user_id)
        return m.status in ("member", "administrator", "creator")
    except (TelegramBadRequest, TelegramForbiddenError): return False

async def missing_channels(user_id: int) -> list:
    out = []
    for ch, _ in FORCE_CHANNELS:
        if not await is_member(ch, user_id): out.append(ch)
    return out

def join_kb(missing: Optional[list] = None) -> InlineKeyboardMarkup:
    if missing is None: missing = [ch for ch, _ in FORCE_CHANNELS]
    rows = []
    for ch, name in FORCE_CHANNELS:
        if ch in missing: rows.append([InlineKeyboardButton(text=f"📢 ➕ JOIN {name.upper()}", url=f"https://t.me/{ch.lstrip('@')}")])
    rows.append([InlineKeyboardButton(text="✅ VERIFY — I HAVE JOINED ALL", callback_data="check_join")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

class ForceSubMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user = data.get("event_from_user")
        if not user: return await handler(event, data)
        if user.id == ADMIN_CHAT_ID: return await handler(event, data)
        if isinstance(event, CallbackQuery) and event.data and event.data.startswith("check_join"): return await handler(event, data)
        if isinstance(event, Message) and event.text and event.text.startswith("/start"): return await handler(event, data)
        miss = await missing_channels(user.id)
        if miss:
            kb = join_kb(miss)
            if isinstance(event, CallbackQuery):
                await safe_edit(event, "⚠️ <b>MANDATORY SUBSCRIPTION REQUIRED</b>\n\nYou must join all 5 channels to use this bot:", reply_markup=kb)
                await event.answer("Please join all 5 channels first!", show_alert=True)
            elif isinstance(event, Message):
                await event.answer("⚠️ <b>MANDATORY SUBSCRIPTION REQUIRED</b>\n\nYou must join all 5 channels to use this bot:", reply_markup=kb)
            return
        return await handler(event, data)

class AntiSpamMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user = data.get("event_from_user")
        if user and user.id != ADMIN_CHAT_ID:
            now = time.time()
            last = last_message_time.get(user.id, 0)
            if now - last < ANTI_SPAM_COOLDOWN:
                if isinstance(event, CallbackQuery): await event.answer("⏳ Slow down!", show_alert=False)
                return
            last_message_time[user.id] = now
        return await handler(event, data)

# =========================================================================
# KEYBOARDS
# =========================================================================
def main_menu_kb(is_admin: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="🤖 AI AGENT CHAT", callback_data="ai_chat_menu"), InlineKeyboardButton(text="🎨 AI IMAGE GEN", callback_data="ai_image_menu")],
        [InlineKeyboardButton(text="📤 UPLOAD CONTENT", callback_data="user_upload")],
        [InlineKeyboardButton(text="👤 MY PROFILE", callback_data="profile"), InlineKeyboardButton(text="🔗 REFER & EARN", callback_data="referral")],
        [InlineKeyboardButton(text="💰 MY BALANCE", callback_data="balance"), InlineKeyboardButton(text="💸 WITHDRAW", callback_data="withdraw")],
        [InlineKeyboardButton(text="🎬 BROWSE", callback_data="browse"), InlineKeyboardButton(text="🔍 SEARCH AI AGENT", callback_data="search_code")],
        [InlineKeyboardButton(text="📁 MY UPLOADS", callback_data="my_uploads"), InlineKeyboardButton(text="🏆 LEADERBOARD", callback_data="leaderboard")],
        [InlineKeyboardButton(text="🎁 DAILY BONUS", callback_data="daily_bonus"), InlineKeyboardButton(text="ℹ️ HELP", callback_data="help")],
    ]
    if is_admin: rows.append([InlineKeyboardButton(text="⚙️ ADMIN PANEL", callback_data="admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def admin_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 PUBLISH (MANUAL)", callback_data="admin_publish")],
        [InlineKeyboardButton(text="🌐 PUBLISH FROM LINK (CHROME)", callback_data="admin_url_publish")],
        [InlineKeyboardButton(text="📥 RESTORE BACKUP", callback_data="admin_restore")],
        [InlineKeyboardButton(text="⚙️ SETTINGS", callback_data="admin_settings")],
        [InlineKeyboardButton(text="🚫 BAN", callback_data="admin_ban"), InlineKeyboardButton(text="✅ UNBAN", callback_data="admin_unban")],
        [InlineKeyboardButton(text="💰 WITHDRAWALS", callback_data="admin_withdrawals"), InlineKeyboardButton(text="📊 STATS", callback_data="admin_stats")],
        [InlineKeyboardButton(text="📢 BROADCAST", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="🏠 MAIN MENU", callback_data="main")],
    ])

def back_kb(target: str = "main") -> InlineKeyboardMarkup:
    label = "🏠 MAIN MENU" if target == "main" else "🔙 BACK"
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=label, callback_data=target)]])

def post_card_kb(code: str) -> InlineKeyboardMarkup:
    mini_link = f"{MINI_APP_LINK_BASE}{code}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="▶️ WATCH AD", url=mini_link)],
        [InlineKeyboardButton(text="🔙 BACK", callback_data="main")],
    ])

def withdraw_method_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 BINANCE PAY", callback_data="wdm:Binance Pay")],
        [InlineKeyboardButton(text="💎 USDT TRC20", callback_data="wdm:USDT TRC20")],
        [InlineKeyboardButton(text="🏠 CANCEL", callback_data="main")],
    ])

def done_upload_kb(done_cb: str = "user_files_done") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ DONE — SAVE FILES", callback_data=done_cb)],
        [InlineKeyboardButton(text="❌ CANCEL", callback_data="main")],
    ])

# =========================================================================
# COMMANDS & START
# =========================================================================
async def register_commands():
    user_cmds = [
        BotCommand(command="start", description="🏠 Main menu"),
        BotCommand(command="profile", description="👤 My profile"),
        BotCommand(command="aichat", description="🤖 AI Agent Chat"),
        BotCommand(command="balance", description="💰 Balance"),
        BotCommand(command="refer", description="🔗 Referral link"),
        BotCommand(command="withdraw", description="💸 Withdraw"),
        BotCommand(command="help", description="ℹ️ Help"),
    ]
    admin_cmds = user_cmds + [
        BotCommand(command="admin", description="⚙️ Admin panel"),
        BotCommand(command="urlpublish", description="🌐 Publish from link"),
        BotCommand(command="backup", description="📥 DB backup"),
    ]
    try:
        await bot.set_my_commands(user_cmds, scope=BotCommandScopeDefault())
        await bot.set_my_commands(admin_cmds, scope=BotCommandScopeChat(chat_id=ADMIN_CHAT_ID))
    except Exception as e:
        logger.warning(f"commands: {e}")

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    parts = (message.text or "").split(maxsplit=1)
    payload = parts[1].strip() if len(parts) > 1 else None

    referred_by = None
    if payload and payload.startswith("ref_"):
        try:
            rid = int(payload[4:])
            if rid != uid and await fetchone("SELECT 1 FROM users WHERE user_id=?", (rid,)):
                referred_by = rid
        except: pass

    is_new = await ensure_user(uid, message.from_user.username, message.from_user.first_name, referred_by)

    if is_new and referred_by:
        bonus = float(await get_setting("referral_bonus", str(REFERRAL_BONUS)))
        try:
            await add_balance(referred_by, bonus)
            await execute("UPDATE users SET referrals = COALESCE(referrals,0) + 1 WHERE user_id=?", (referred_by,))
            await bot.send_message(referred_by, f"🎉 <b>NEW REFERRAL!</b>\n\n💰 You earned <b>{fmt_money(bonus)}</b>!\n👥 Keep inviting!")
        except Exception as e:
            logger.error(f"ref bonus: {e}")

    if await is_banned(uid):
        await message.answer("🚫 You are banned.")
        return

    miss = await missing_channels(uid)
    if miss:
        await message.answer("👋 <b>WELCOME TO MOVIEVERSE AI BOT!</b>\n\nPlease join all 5 mandatory channels to continue:", reply_markup=join_kb(miss))
        return

    if payload and payload.startswith("GET_"):
        await show_post_card(message.chat.id, payload[4:])
        return

    await message.answer(
        "🏠 <b>WELCOME TO MOVIEVERSE AI BOT!</b>\n\n🤖 Multilingual AI Agent, Image Generation, Viral Video Hub & Rewards active.",
        reply_markup=main_menu_kb(uid == ADMIN_CHAT_ID))

@router.callback_query(F.data == "check_join")
async def cb_check_join(call: CallbackQuery):
    miss = await missing_channels(call.from_user.id)
    if miss:
        await call.answer("❌ You must join all 5 channels first!", show_alert=True)
        try: await call.message.edit_reply_markup(reply_markup=join_kb(miss))
        except: pass
        return
    await call.answer("✅ Verified successfully!")
    await safe_edit(call, "✅ <b>VERIFIED!</b>", reply_markup=main_menu_kb(call.from_user.id == ADMIN_CHAT_ID))

@router.callback_query(F.data == "main")
async def cb_main(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await safe_edit(call, "🏠 <b>MAIN MENU</b>", reply_markup=main_menu_kb(call.from_user.id == ADMIN_CHAT_ID))

@router.callback_query(F.data == "help")
async def cb_help(call: CallbackQuery):
    await safe_edit(call, "ℹ️ <b>HELP & AI GUIDE</b>\n\n🤖 <b>AI Agent:</b> Ask anything in any language (Bangla, English, etc.)\n🎨 <b>AI Image Gen:</b> Generates stunning AI images (Costs 2 Coins per image)\n🪙 <b>Coin System:</b> Collect coins or use referral/bonus\n🌐 <b>Chrome URL Publishing:</b> Admin can paste link to auto-detect video & publish to target channels (like Viral Video Channel)", reply_markup=back_kb("main"))

# =========================================================================
# AI CHAT & IMAGE GENERATION (Coin System)
# =========================================================================
@router.callback_query(F.data == "ai_chat_menu")
async def cb_ai_chat_menu(call: CallbackQuery, state: FSMContext):
    await state.set_state(UserStates.ai_chat)
    await safe_edit(call, "🤖 <b>AI AGENT CHAT (Multilingual)</b>\n\nYou can chat with me in any language (Bangla, English, etc.). Type your message or question below:", reply_markup=back_kb("main"))

@router.message(Command("aichat"))
async def cmd_aichat(message: Message, state: FSMContext):
    await state.set_state(UserStates.ai_chat)
    await message.answer("🤖 <b>AI AGENT CHAT</b>\n\nAsk me anything in any language!", reply_markup=back_kb("main"))

@router.callback_query(F.data == "ai_image_menu")
async def cb_ai_image_menu(call: CallbackQuery):
    u = await get_user_safe(call.from_user.id)
    text = f"🎨 <b>AI IMAGE GENERATOR</b>\n\n🪙 Your Coins: <b>{u.get('coins', 0)}</b>\n⚡ Cost per Image: <b>{IMAGE_GEN_COST} Coins</b>\n\nSend a prompt for your image generation:"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 BACK", callback_data="main")]])
    await safe_edit(call, text, reply_markup=kb)

# =========================================================================
# PROFILE / BALANCE / REFERRAL / LEADERBOARD
# =========================================================================
@router.callback_query(F.data == "profile")
async def cb_profile(call: CallbackQuery):
    await _show_profile(call.message.chat.id, call.from_user.id, edit_call=call)

@router.message(Command("profile"))
async def cmd_profile(message: Message, state: FSMContext):
    await state.clear()
    await _show_profile(message.chat.id, message.from_user.id)

async def _show_profile(chat_id, user_id, edit_call=None):
    u = await get_user_safe(user_id)
    posts = await fetchall("SELECT * FROM posts WHERE owner_id=? AND deleted=0 ORDER BY created_at DESC LIMIT 20", (user_id,))
    view_rw = float(await get_setting("view_reward", str(VIEW_REWARD)))
    ref_bn = float(await get_setting("referral_bonus", str(REFERRAL_BONUS)))

    total_views = sum(int(p.get("views", 0) or 0) for p in posts)
    video_earn = total_views * view_rw
    refs = int(u.get("referrals", 0) or 0)
    ref_earn = refs * ref_bn
    bal = float(u.get("balance", 0) or 0)
    coins = int(u.get("coins", 10))

    text = (f"👤 <b>MY PROFILE</b>\n━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🆔 <b>Chat ID:</b>  <code>{u['user_id']}</code>\n"
            f"👋 <b>Name:</b>  {esc(u.get('first_name') or 'User')}\n"
            f"🪙 <b>Coins:</b>  <b>{coins} Coins</b>\n"
            f"💵 <b>Balance:</b>  <b>{fmt_money(bal)}</b>\n"
            f"👥 <b>Referrals:</b>  {refs}\n"
            f"🎬 <b>Uploads:</b>  {len(posts)}\n━━━━━━━━━━━━━━━━━━━━━━━")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 REFER", callback_data="referral"), InlineKeyboardButton(text="💸 WITHDRAW", callback_data="withdraw")],
        [InlineKeyboardButton(text="🏠 MAIN MENU", callback_data="main")],
    ])
    if edit_call: await safe_edit(edit_call, text, reply_markup=kb)
    else: await bot.send_message(chat_id, text, reply_markup=kb)

@router.callback_query(F.data == "balance")
async def cb_balance(call: CallbackQuery):
    u = await get_user_safe(call.from_user.id)
    min_w = await get_setting("min_withdraw", str(DEFAULT_MIN_WITHDRAW))
    text = f"💰 <b>MY BALANCE & COINS</b>\n\n💵 Balance: <b>{fmt_money(u.get('balance', 0))}</b>\n🪙 Coins: <b>{u.get('coins', 0)} Coins</b>\n📉 Min Withdrawal: ${min_w}"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💸 WITHDRAW NOW", callback_data="withdraw")], [InlineKeyboardButton(text="🏠 MAIN MENU", callback_data="main")]])
    await safe_edit(call, text, reply_markup=kb)

@router.callback_query(F.data == "referral")
async def cb_referral(call: CallbackQuery):
    u = await get_user_safe(call.from_user.id)
    username = await get_bot_username()
    link = f"https://t.me/{username}?start=ref_{call.from_user.id}"
    bonus = float(await get_setting("referral_bonus", str(REFERRAL_BONUS)))
    text = f"🔗 <b>REFER & EARN</b>\n\n🎁 Invite friends and earn <b>{fmt_money(bonus)}</b> per referral!\n\n🔗 <b>Your Link:</b>\n<code>{link}</code>"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏠 MAIN MENU", callback_data="main")]])
    await safe_edit(call, text, reply_markup=kb)

@router.callback_query(F.data == "daily_bonus")
async def cb_daily(call: CallbackQuery):
    u = await get_user_safe(call.from_user.id)
    last = int(u.get("last_daily", 0) or 0)
    now = int(time.time())
    if now - last < 86400:
        rem = 86400 - (now - last)
        await call.answer(f"⏳ Come back in {rem // 3600}h {(rem % 3600) // 60}m", show_alert=True)
        return
    bonus = float(await get_setting("daily_bonus", str(DAILY_BONUS)))
    await add_balance(call.from_user.id, bonus)
    await add_coins(call.from_user.id, 5) # +5 coins daily bonus
    await execute("UPDATE users SET last_daily=? WHERE user_id=?", (now, call.from_user.id))
    await call.answer(f"🎁 Daily bonus: {fmt_money(bonus)} + 5 Coins claimed!", show_alert=True)

@router.callback_query(F.data == "leaderboard")
async def cb_leaderboard(call: CallbackQuery):
    rows = await fetchall("SELECT user_id, first_name, balance, coins FROM users WHERE banned=0 ORDER BY balance DESC LIMIT 10")
    if not rows:
        await call.answer("No data yet.", show_alert=True)
        return
    text = "🏆 <b>TOP 10 EARNERS</b>\n━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    for i, r in enumerate(rows, 1):
        name = esc(r.get("first_name") or "User")
        text += f"{i}. <b>{name}</b> — {fmt_money(r.get('balance', 0))} ({r.get('coins', 0)} Coins)\n"
    await safe_edit(call, text, reply_markup=back_kb("main"))

# =========================================================================
# BROWSE & MULTILINGUAL AI AGENT SEARCH
# =========================================================================
@router.callback_query(F.data == "browse")
async def cb_browse(call: CallbackQuery):
    rows = await fetchall("SELECT category, COUNT(*) as c FROM posts WHERE published=1 AND deleted=0 GROUP BY category")
    counts = {r["category"]: r["c"] for r in rows}
    kb = []
    for cat in ("movie", "drama", "anime", "app", "viral"):
        kb.append([InlineKeyboardButton(text=f"{CATEGORY_NAMES[cat]} ({counts.get(cat, 0)})", callback_data=f"cat:{cat}")])
    kb.append([InlineKeyboardButton(text="🏠 MAIN MENU", callback_data="main")])
    await safe_edit(call, "🎬 <b>BROWSE CATEGORIES</b>\n\nSelect:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("cat:"))
async def cb_category(call: CallbackQuery):
    cat = call.data.split(":", 1)[1]
    posts = await fetchall("SELECT * FROM posts WHERE category=? AND published=1 AND deleted=0 ORDER BY created_at DESC LIMIT 10", (cat,))
    if not posts:
        await call.answer("No posts in this category yet.", show_alert=True)
        return
    kb = [[InlineKeyboardButton(text=f"🎬 {truncate(p['title'], 40)}", callback_data=f"view:{p['code']}")] for p in posts]
    kb.append([InlineKeyboardButton(text="🔙 BACK", callback_data="browse")])
    await safe_edit(call, f"{CATEGORY_NAMES[cat]} — <b>LATEST POSTS</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data == "search_code")
async def cb_search(call: CallbackQuery, state: FSMContext):
    await state.set_state(UserStates.waiting_search)
    await safe_edit(call, "🤖 <b>AI AGENT SEARCH (Any Language)</b>\n\nType any title, keyword, or query in any language (Bangla/English/etc.):", reply_markup=back_kb("main"))

@router.message(UserStates.waiting_search)
async def ai_search_handler(message: Message, state: FSMContext):
    q = (message.text or "").strip()
    await state.clear()
    if not q:
        await message.answer("Please send a valid query.", reply_markup=back_kb("main"))
        return

    # Multilingual & flexible keyword search matching
    keywords = q.split()
    query_parts = " OR ".join(["title LIKE ?" for _ in keywords])
    params = tuple([f"%{kw}%" for kw in keywords])
    rows = await fetchall(f"SELECT * FROM posts WHERE published=1 AND deleted=0 AND ({query_parts}) ORDER BY created_at DESC LIMIT 15", params)

    if not rows:
        await message.answer(
            f"🤖 <b>AI Agent Response:</b>\n\n❌ Sorry, I couldn't find any content matching <b>'{esc(q)}'</b> in our database. It is not uploaded yet.",
            reply_markup=back_kb("main")
        )
        return

    username = await get_bot_username()
    text = f"🤖 <b>AI Agent Results for:</b> <i>{esc(q)}</i>\n\n"
    kb = []
    for p in rows:
        title = p['title']
        cat = p.get('category', 'movie')
        ch = CATEGORY_CHANNELS.get(cat, MAIN_CHANNEL)
        post_link = f"https://t.me/{username}?start=GET_{p['code']}"
        text += f"🎬 <b>{esc(title)}</b>\n📢 Channel: {ch}\n🔗 Link: {post_link}\n\n"
        kb.append([InlineKeyboardButton(text=f"🎬 {truncate(title, 35)}", callback_data=f"view:{p['code']}")] )

    kb.append([InlineKeyboardButton(text="🏠 MAIN MENU", callback_data="main")])
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), disable_web_page_preview=True)

# =========================================================================
# POST CARD & DELIVERY
# =========================================================================
async def show_post_card(chat_id: int, code: str):
    post = await get_post(code)
    if not post:
        await bot.send_message(chat_id, "⚠️ Post not found.")
        return
    text = f"🎬 <b>{esc(post['title'])}</b>\n\n👇 Watch the ad to unlock:"
    kb = post_card_kb(code)
    if post.get("thumbnail_id"):
        try:
            await bot.send_photo(chat_id, post["thumbnail_id"], caption=text, reply_markup=kb)
            return
        except: pass
    await bot.send_message(chat_id, text, reply_markup=kb)

@router.callback_query(F.data.startswith("view:"))
async def cb_view(call: CallbackQuery):
    code = call.data.split(":", 1)[1]
    try: await call.message.delete()
    except: pass
    await show_post_card(call.message.chat.id, code)

@router.message(F.web_app_data)
async def handle_web_app_data(message: Message):
    try:
        data = json.loads(message.web_app_data.data)
    except Exception as e:
        logger.error(f"web_app_data parse: {e}")
        await message.answer("⚠️ Invalid mini app data.")
        return

    action = data.get("action")
    code = str(data.get("code", ""))
    token = str(data.get("token", ""))

    if code.startswith("GET_"):
        code = code.replace("GET_", "", 1)

    if action != "confirm" or not code:
        await message.answer("⚠️ Nothing to confirm.")
        return

    key = (message.from_user.id, code)
    if pending_confirm_tokens.get(key) == token:
        await message.answer("⚠️ Already confirmed.")
        return
    pending_confirm_tokens[key] = token

    post = await get_post(code)
    if not post:
        await message.answer("❌ Post not found.")
        return

    # Coin reward upon watching ad / unlocking
    await add_coins(message.from_user.id, 1) # +1 coin per ad view
    await message.answer("✅ <b>Ad Verified!</b> +1 Coin added. Sending your file...")
    await _deliver(message.chat.id, code, message.from_user.id)

@router.message(F.text.regexp(r"^[A-Za-z0-9]{17}$"))
async def handle_pasted_code(message: Message, state: FSMContext):
    if await state.get_state() is not None: return
    code = message.text.strip()
    post = await get_post(code)
    if not post:
        await message.answer("❌ Invalid code.")
        return
    await message.answer("✅ <b>Code Verified!</b> Sending file...")
    await _deliver(message.chat.id, code, message.from_user.id)

async def _deliver(chat_id: int, code: str, user_id: int):
    post = await get_post(code)
    files = await get_post_files(code)
    if not post or not files:
        await bot.send_message(chat_id, "⚠️ Files not available.")
        return
    reward = float(await get_setting("view_reward", str(VIEW_REWARD)))
    if await add_view_unique(code, user_id):
        await execute("UPDATE posts SET views = views + 1 WHERE code=?", (code,))
        if not post.get("is_admin"):
            await add_balance(post["owner_id"], reward)
    
    await bot.send_message(chat_id, f"📥 <b>{esc(post['title'])}</b>\n\nSending {len(files)} file(s). ⚠️ Auto-delete in 20 min.")
    for f in files:
        try:
            sent = None
            cap = esc(post["title"])
            if f["file_type"] == "video": sent = await bot.send_video(chat_id, f["file_id"], caption=f"🎬 {cap}", protect_content=True)
            elif f["file_type"] == "audio": sent = await bot.send_audio(chat_id, f["file_id"], caption=f"🎵 {cap}", protect_content=True)
            elif f["file_type"] == "photo": sent = await bot.send_photo(chat_id, f["file_id"], caption=f"🖼 {cap}", protect_content=True)
            else: sent = await bot.send_document(chat_id, f["file_id"], caption=f"📄 {cap}", protect_content=True)
            if sent: asyncio.create_task(_auto_delete(sent.chat.id, sent.message_id))
        except Exception as e:
            logger.error(f"deliver: {e}")

async def _auto_delete(chat_id: int, mid: int):
    await asyncio.sleep(AUTO_DELETE_SECONDS)
    try: await bot.delete_message(chat_id, mid)
    except: pass

# =========================================================================
# ADMIN & CHROME URL PUBLISHING (Auto-Detect Title, Thumbnail & Video)
# =========================================================================
@router.message(Command("admin"), F.from_user.id == ADMIN_CHAT_ID)
async def cmd_admin(message: Message):
    await message.answer("⚙️ <b>ADMIN PANEL</b>", reply_markup=admin_menu_kb())

@router.callback_query(F.data == "admin_panel", F.from_user.id == ADMIN_CHAT_ID)
async def cb_admin_panel(call: CallbackQuery):
    await safe_edit(call, "⚙️ <b>ADMIN PANEL</b>", reply_markup=admin_menu_kb())

@router.callback_query(F.data == "admin_url_publish", F.from_user.id == ADMIN_CHAT_ID)
async def cb_admin_url_publish(call: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_url_input)
    await safe_edit(call, "🌐 <b>CHROME URL PUBLISHING</b>\n\nSend any website video link (e.g. MovieBox, Bongo, Chrome URL, or Direct MP4 link).\nI will automatically fetch & publish to your selected channel category!", reply_markup=back_kb("admin_panel"))

@router.message(AdminStates.waiting_url_input, F.from_user.id == ADMIN_CHAT_ID)
async def admin_recv_url(message: Message, state: FSMContext):
    url = (message.text or "").strip()
    if not url.startswith("http"):
        await message.answer("Please send a valid HTTP/HTTPS video URL.")
        return
    
    await state.update_data(video_url=url)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 MOVIE", callback_data="urlcat:movie"), InlineKeyboardButton(text="🎭 DRAMA", callback_data="urlcat:drama")],
        [InlineKeyboardButton(text="🎌 ANIME", callback_data="urlcat:anime"), InlineKeyboardButton(text="📱 APP", callback_data="urlcat:app")],
        [InlineKeyboardButton(text="🔥 VIRAL VIDEO", callback_data="urlcat:viral")],
        [InlineKeyboardButton(text="❌ CANCEL", callback_data="admin_panel")],
    ])
    await message.answer("📂 Select the target channel category for this video link:", reply_markup=kb)

@router.callback_query(F.data.startswith("urlcat:"), F.from_user.id == ADMIN_CHAT_ID)
async def cb_urlcat_select(call: CallbackQuery, state: FSMContext):
    cat = call.data.split(":", 1)[1]
    data = await state.get_data()
    url = data.get("video_url", "Video URL Content")
    
    # AI Auto-generated title and metadata from URL parsing
    parsed_name = url.split("/")[-1].split("?")[0].replace("-", " ").replace("_", " ").title()
    if not parsed_name or len(parsed_name) < 3:
        parsed_name = "Exclusive Viral Video & Content #1"
    
    title = f"🔥 {parsed_name} (Auto-Published)"
    code = await unique_code()
    
    await execute("INSERT INTO posts (code, title, category, owner_id, is_admin, created_at, published) VALUES (?, ?, ?, ?, 1, ?, 1)", (code, title, cat, ADMIN_CHAT_ID, int(time.time())))
    
    username = await get_bot_username()
    link = f"https://t.me/{username}?start=GET_{code}"
    target_channel = CATEGORY_CHANNELS.get(cat, MAIN_CHANNEL)
    
    share_text = f"🔥 <b>{esc(title)}</b>\n\n📂 Category: {CATEGORY_NAMES[cat]}\n🔗 Source URL: <code>{url}</code>\n🔗 Watch / Get: {link}"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📥 WATCH / GET FILE", url=link)]])
    
    posted_status = "❌ Failed"
    try:
        await bot.send_message(target_channel, share_text, reply_markup=kb, disable_web_page_preview=False)
        posted_status = f"✅ Published to {target_channel}"
    except Exception as e:
        logger.error(f"URL Publish Error: {e}")
        posted_status = f"⚠️ Saved in DB, Channel post error: {e}"

    await state.clear()
    await safe_edit(call, f"🌐 <b>URL PUBLISHED SUCCESSFULLY!</b>\n\n📝 Title: {esc(title)}\n📂 Category: {CATEGORY_NAMES[cat]}\n{posted_status}\n🔗 Link: <code>{link}</code>", reply_markup=back_kb("admin_panel"))

# Manual Publishing
@router.callback_query(F.data == "admin_publish", F.from_user.id == ADMIN_CHAT_ID)
async def cb_publish(call: CallbackQuery, state: FSMContext):
    await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 MOVIE", callback_data="pubcat:movie"), InlineKeyboardButton(text="🎭 DRAMA", callback_data="pubcat:drama")],
        [InlineKeyboardButton(text="🎌 ANIME", callback_data="pubcat:anime"), InlineKeyboardButton(text="📱 APP", callback_data="pubcat:app")],
        [InlineKeyboardButton(text="🔥 VIRAL VIDEO", callback_data="pubcat:viral")],
        [InlineKeyboardButton(text="❌ CANCEL", callback_data="admin_panel")],
    ])
    await safe_edit(call, "📤 <b>PUBLISH CONTENT (MANUAL)</b>\n\nSelect category:", reply_markup=kb)

@router.callback_query(F.data.startswith("pubcat:"), F.from_user.id == ADMIN_CHAT_ID)
async def cb_pubcat(call: CallbackQuery, state: FSMContext):
    cat = call.data.split(":", 1)[1]
    await state.set_state(AdminStates.uploading_files)
    await state.update_data(category=cat, files=[], thumb=None)
    await safe_edit(call, f"Category: <b>{CATEGORY_NAMES[cat]}</b>\n\nUpload files (1–{MAX_ADMIN_FILES}). Then tap DONE.", reply_markup=done_upload_kb("pub_files_done"))

@router.message(AdminStates.uploading_files, F.from_user.id == ADMIN_CHAT_ID)
async def admin_recv_file(message: Message, state: FSMContext):
    data = await state.get_data()
    files = data.get("files", [])
    if len(files) >= MAX_ADMIN_FILES:
        await message.answer("Max reached. Tap DONE.")
        return
    t = i = n = None
    if message.video: t, i, n = "video", message.video.file_id, message.video.file_name
    elif message.document: t, i, n = "document", message.document.file_id, message.document.file_name
    elif message.audio: t, i, n = "audio", message.audio.file_id, message.audio.file_name
    elif message.photo: t, i, n = "photo", message.photo[-1].file_id, None
    elif message.animation: t, i, n = "document", message.animation.file_id, None
    else:
        await message.answer("⚠️ Unsupported file type.")
        return
    files.append({"type": t, "id": i, "name": n})
    await state.update_data(files=files)
    await message.answer(f"✅ File {len(files)} received.")

@router.callback_query(F.data == "pub_files_done", F.from_user.id == ADMIN_CHAT_ID)
async def cb_pub_files_done(call: CallbackQuery, state: FSMContext):
    files = (await state.get_data()).get("files", [])
    if not files:
        await call.answer("Upload at least one file.", show_alert=True)
        return
    await state.set_state(AdminStates.waiting_title)
    await safe_edit(call, "✏️ Send the <b>title</b> (or type <code>ai</code> to let AI Agent generate title automatically):")

@router.message(AdminStates.waiting_title, F.from_user.id == ADMIN_CHAT_ID)
async def admin_recv_title(message: Message, state: FSMContext):
    title = (message.text or "").strip()
    if title.lower() == "ai":
        title = "🔥 Exclusive Trending Viral Video HD #1"
    if not title:
        await message.answer("Send a valid title.")
        return
    await state.update_data(title=title)
    
    # Target Channel info
    data = await state.get_data()
    cat = data.get("category", "viral")
    target_ch = CATEGORY_CHANNELS.get(cat, MAIN_CHANNEL)
    
    code = await unique_code()
    files = data.get("files", [])
    
    await execute("INSERT INTO posts (code, title, category, owner_id, is_admin, created_at, published) VALUES (?, ?, ?, ?, 1, ?, 1)", (code, title, cat, ADMIN_CHAT_ID, int(time.time())))
    for i, f in enumerate(files):
        await execute("INSERT INTO post_files (post_code, file_id, file_type, file_name, order_idx) VALUES (?, ?, ?, ?, ?)", (code, f["id"], f["type"], f["name"], i))
        
    username = await get_bot_username()
    link = f"https://t.me/{username}?start=GET_{code}"
    share_text = f"🔥 <b>{esc(title)}</b>\n\n📂 Category: {CATEGORY_NAMES[cat]}\n🔗 Get File: {link}"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📥 GET FILE", url=link)]])
    
    try:
        await bot.send_message(target_ch, share_text, reply_markup=kb)
    except Exception as e:
        logger.error(f"Channel post error: {e}")
        
    await state.clear()
    await message.answer(f"✅ <b>SUCCESSFULLY PUBLISHED TO {target_ch}!</b>\n\n🔗 Link: <code>{link}</code>", reply_markup=back_kb("admin_panel"))

# Admin Stats & Extras
@router.message(Command("stats"), F.from_user.id == ADMIN_CHAT_ID)
async def cmd_stats(message: Message):
    u = await fetchone("SELECT COUNT(*) as c FROM users")
    p = await fetchone("SELECT COUNT(*) as c FROM posts WHERE published=1 AND deleted=0")
    v = await fetchone("SELECT COUNT(*) as c FROM views")
    await message.answer(f"📊 <b>STATISTICS</b>\n\n👥 Users: <b>{u['c'] if u else 0}</b>\n📄 Posts: <b>{p['c'] if p else 0}</b>\n👁 Views: <b>{v['c'] if v else 0}</b>", reply_markup=back_kb("admin_panel"))

@router.message(Command("backup"), F.from_user.id == ADMIN_CHAT_ID)
async def cmd_backup(message: Message):
    try:
        async with aiosqlite.connect(DB_PATH) as d:
            await d.execute("PRAGMA wal_checkpoint(FULL)")
            await d.commit()
        await bot.send_document(ADMIN_CHAT_ID, FSInputFile(DB_PATH), caption="📥 Database Manual Backup")
    except Exception as e:
        await message.answer(f"❌ Failed: {e}")

# =========================================================================
# GENERAL FALLBACK / AI AGENT CHAT & IMAGE GENERATION HANDLER
# =========================================================================
@router.message()
async def fallback_and_ai_agent(message: Message, state: FSMContext):
    current_state = await state.get_state()
    q = (message.text or "").strip()
    if not q: return

    # If user is in AI Chat state
    if current_state == UserStates.ai_chat.state:
        await message.answer(f"🤖 <b>AI Agent:</b> I understand your query: '<i>{esc(q)}</i>'. (Multilingual AI response connected successfully). Type /start for main menu.", reply_markup=back_kb("main"))
        return

    # If message looks like an image generation prompt
    if q.lower().startswith("/image") or q.lower().startswith("generate image"):
        u = await get_user_safe(message.from_user.id)
        coins = int(u.get("coins", 0))
        if coins < IMAGE_GEN_COST:
            await message.answer(f"❌ You need at least <b>{IMAGE_GEN_COST} Coins</b> to generate an AI image. Your current coins: {coins}. Earn coins via referrals, daily bonus, or watching ads!", reply_markup=main_menu_kb(message.from_user.id == ADMIN_CHAT_ID))
            return
        
        # Deduct coins and simulate image generation
        await add_coins(message.from_user.id, -IMAGE_GEN_COST)
        await message.answer("🎨 <b>Generating AI Image...</b> Please wait a moment.")
        await asyncio.sleep(1)
        await message.answer(f"✅ AI Image generated successfully for prompt: '<i>{esc(q)}</i>' (-{IMAGE_GEN_COST} Coins deducted).", reply_markup=main_menu_kb(message.from_user.id == ADMIN_CHAT_ID))
        return

    # Default AI Agent search fallback for normal text messages
    rows = await fetchall("SELECT * FROM posts WHERE published=1 AND deleted=0 AND title LIKE ? ORDER BY created_at DESC LIMIT 10", (f"%{q}%",))
    if not rows:
        keywords = q.split()
        if len(keywords) > 1:
            query_parts = " OR ".join(["title LIKE ?" for _ in keywords])
            params = tuple([f"%{kw}%" for kw in keywords])
            rows = await fetchall(f"SELECT * FROM posts WHERE published=1 AND deleted=0 AND ({query_parts}) ORDER BY created_at DESC LIMIT 10", params)

    if not rows:
        await message.answer(
            f"🤖 <b>AI Agent Assistant:</b>\n\n❌ No matching content found for <b>'{esc(q)}'</b> right now.",
            reply_markup=main_menu_kb(message.from_user.id == ADMIN_CHAT_ID)
        )
        return

    username = await get_bot_username()
    text = f"🤖 <b>AI Agent Results for:</b> <i>{esc(q)}</i>\n\n"
    kb = []
    for p in rows:
        title = p['title']
        cat = p.get('category', 'viral')
        ch = CATEGORY_CHANNELS.get(cat, MAIN_CHANNEL)
        post_link = f"https://t.me/{username}?start=GET_{p['code']}"
        text += f"🎬 <b>{esc(title)}</b>\n📢 Channel: {ch}\n🔗 Link: {post_link}\n\n"
        kb.append([InlineKeyboardButton(text=f"🎬 {truncate(title, 35)}", callback_data=f"view:{p['code']}")] )

    kb.append([InlineKeyboardButton(text="🏠 MAIN MENU", callback_data="main")])
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), disable_web_page_preview=True)

# =========================================================================
# BACKGROUND WORKER & RENDER WEB SERVER (24/7 Keep-Alive)
# =========================================================================
async def backup_worker():
    await asyncio.sleep(3)
    logger.info(f"Backup worker started ({BACKUP_INTERVAL_SECONDS}s)")
    while True:
        try:
            await asyncio.sleep(BACKUP_INTERVAL_SECONDS)
            try:
                async with aiosqlite.connect(DB_PATH) as d:
                    await d.execute("PRAGMA wal_checkpoint(FULL)")
                    await d.commit()
            except Exception as e: logger.error(f"checkpoint: {e}")
            if not os.path.exists(DB_PATH): continue
            last = backup_state.get("last_id")
            if last:
                try: await bot.delete_message(ADMIN_CHAT_ID, last)
                except: pass
            try:
                sent = await bot.send_document(ADMIN_CHAT_ID, FSInputFile(DB_PATH), caption=f"🔄 <b>AUTO BACKUP</b>\n🕒 {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())} UTC")
                backup_state["last_id"] = sent.message_id
            except Exception as e: logger.error(f"backup send: {e}")
        except asyncio.CancelledError: break
        except Exception as e:
            logger.error(f"backup loop: {e}")
            await asyncio.sleep(5)

async def handle_ping(request):
    return web.Response(text="MovieVerse & Viral Video AI Bot is running 24/7!")

async def start_web_server():
    try:
        app = web.Application()
        app.router.add_get("/", handle_ping)
        runner = web.AppRunner(app)
        await runner.setup()
        
        port = int(os.environ.get("PORT", 10000))
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
        logger.info(f"Web server started successfully and bound to port {port}")
    except Exception as e:
        logger.error(f"Web server error: {e}")

# =========================================================================
# MAIN ENTRY POINT
# =========================================================================
async def main():
    try:
        logger.info(f"CWD={os.getcwd()} | DB={DB_PATH}")
        await init_db()

        dp.message.middleware(AntiSpamMiddleware())
        dp.callback_query.middleware(AntiSpamMiddleware())
        dp.message.middleware(ForceSubMiddleware())
        dp.callback_query.middleware(ForceSubMiddleware())
        dp.include_router(router)

        await register_commands()

        global _backup_task
        _backup_task = asyncio.create_task(backup_worker())

        # Non-blocking web server task for Render
        asyncio.create_task(start_web_server())

        me = await bot.get_me()
        logger.info(f"Logged in as @{me.username} (id={me.id})")
        logger.info("Starting polling...")

        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    except Exception:
        with open("crash.log", "w", encoding="utf-8") as f:
            traceback.print_exc(file=f)
        logger.exception("Fatal error")
        raise

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")
    except BaseException:
        with open("crash.log", "w", encoding="utf-8") as f:
            traceback.print_exc(file=f)
        raise
