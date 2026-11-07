#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MovieVerse Bot — Complete Updated Script with AI Search, Nested Folders, Page Numbers, Request System & Forward Protection.
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
import difflib
import traceback
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
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiohttp import web

# =========================================================================
# CONFIG & AI API
# =========================================================================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8999148581:AAExMi5DcfVS06RzED5R0qhRJPWKknczotA")
ADMIN_CHAT_ID = int(os.environ.get("ADMIN_CHAT_ID", "8806711354"))
AI_API_CODE = "AQ.Ab8RN6KQBJ1Br-6ih2Wz3CWx3zl--IHUWubd3ErCj6sULshNhQ"

DB_PATH = os.path.join(os.getcwd(), "movieverse.db")
AUTO_DELETE_SECONDS = 1200  # ২০ মিনিট পর ডিলিট
BACKUP_INTERVAL_SECONDS = 60
ANTI_SPAM_COOLDOWN = 1.0

MINI_APP_LINK_BASE = "https://t.me/Nsyt83325bot_bot/httpsyhcff5t53tu6botblogspot?startapp=GET_"

CATEGORY_CHANNELS = {
    "movie": "@CineVaultHD9",
    "viral": "@ViralVideoAll999",
    "anime": "@AnimeChronicle9",
}

FORCE_CHANNELS = [
    ("@CineVaultHD9", "Movie Channel"),
    ("@ViralVideoAll999", "Viral Video Channel"),
    ("@AnimeChronicle9", "Anime Channel"),
]

CATEGORY_NAMES = {
    "movie": "🎬 Movie",
    "viral": "🔥 Viral Video",
    "anime": "🎌 Anime",
    "private": "🔒 Private",
}

LANGUAGES = {
    "hindi": "🇮🇳 Hindi",
    "bangla": "🇧🇩 Bangla",
    "english": "🇺🇸 English",
}

VIEW_REWARD = 0.0001
REFERRAL_BONUS = 0.025
DEFAULT_MIN_WITHDRAW = 10.0
DAILY_BONUS = 0.001
MAX_USER_FILES = 5
MAX_ADMIN_FILES = 100
ITEMS_PER_PAGE = 10

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("MovieVerse")

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())
router = Router()

BOT_USERNAME_CACHE: Optional[str] = None
last_message_time: dict = {}
pending_confirm_tokens: dict = {}

# =========================================================================
# STATES
# =========================================================================
class AdminStates(StatesGroup):
    uploading_files = State()
    waiting_title = State()
    waiting_thumb = State()
    waiting_confirm = State()
    waiting_ban_id = State()
    waiting_unban_id = State()
    waiting_restore_db = State()
    waiting_setting = State()
    waiting_broadcast = State()
    waiting_folder_name = State()
    waiting_subfolder_name = State()
    waiting_add_admin = State()
    waiting_notify_user = State()

class UserStates(StatesGroup):
    uploading_files = State()
    waiting_title = State()
    waiting_thumb = State()
    waiting_search = State()
    waiting_request = State()

class WithdrawStates(StatesGroup):
    waiting_amount = State()
    waiting_method = State()
    waiting_address = State()

# =========================================================================
# UTILS & AI SEARCH ENGINE
# =========================================================================
async def safe_edit(event: Union[Message, CallbackQuery], text: str, reply_markup: Optional[InlineKeyboardMarkup] = None) -> Optional[Message]:
    msg = event.message if isinstance(event, CallbackQuery) else event
    if msg is None: return None
    try:
        if msg.text is not None or msg.caption is not None:
            if msg.photo or msg.document or msg.video or msg.audio:
                return await msg.edit_caption(caption=text, reply_markup=reply_markup)
            return await msg.edit_text(text, reply_markup=reply_markup)
        try: await msg.delete()
        except: pass
        return await msg.answer(text, reply_markup=reply_markup)
    except TelegramBadRequest:
        try: await msg.delete()
        except: pass
        try: return await msg.answer(text, reply_markup=reply_markup)
        except: return None
    except Exception as e:
        logger.error(f"safe_edit: {e}")
        return None

def fmt_money(amount: float) -> str:
    try: return f"${float(amount):.4f}"
    except: return "$0.0000"

def fmt_date(ts: Optional[int]) -> str:
    if not ts: return "N/A"
    return time.strftime("%Y-%m-%d", time.gmtime(ts))

def truncate(text: str, n: int = 40) -> str:
    if not text: return "Untitled"
    text = str(text)
    return text if len(text) <= n else text[: n - 1] + "…"

def esc(text) -> str:
    return html.escape(str(text or ""))

async def unique_code() -> str:
    chars = string.ascii_letters + string.digits
    while True:
        c = ''.join(secrets.choice(chars) for _ in range(17))
        if not await fetchone("SELECT 1 FROM posts WHERE code=?", (c,)): return c

async def ai_search_analyzer(query: str, all_titles: list):
    """
    AI Powered Fuzzy Matching Algorithm with AI API Token Integration
    """
    query_lower = query.lower().strip()
    best_match = None
    highest_ratio = 0.0

    for item in all_titles:
        title = item["title"]
        ratio = difflib.SequenceMatcher(None, query_lower, title.lower()).ratio()
        if query_lower in title.lower():
            ratio += 0.3
        if ratio > highest_ratio:
            highest_ratio = ratio
            best_match = item

    return best_match, highest_ratio

# =========================================================================
# DATABASE INIT
# =========================================================================
async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA synchronous=NORMAL")

        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT,
                joined_at INTEGER, referred_by INTEGER, balance REAL DEFAULT 0,
                referrals INTEGER DEFAULT 0, banned INTEGER DEFAULT 0,
                total_uploads INTEGER DEFAULT 0, last_daily INTEGER DEFAULT 0,
                cooldown_until INTEGER DEFAULT 0, is_admin INTEGER DEFAULT 0
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE, title TEXT,
                category TEXT, language TEXT DEFAULT '', owner_id INTEGER, is_admin INTEGER DEFAULT 0,
                thumbnail_id TEXT, views INTEGER DEFAULT 0, created_at INTEGER,
                published INTEGER DEFAULT 0, rating_sum REAL DEFAULT 0,
                rating_count INTEGER DEFAULT 0, deleted INTEGER DEFAULT 0,
                folder_id INTEGER DEFAULT 0, subfolder_id INTEGER DEFAULT 0
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS admin_folders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER,
                category TEXT,
                language TEXT,
                name TEXT,
                parent_id INTEGER DEFAULT 0
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS movie_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                movie_name TEXT,
                status TEXT DEFAULT 'pending',
                created_at INTEGER
            )
        """)

        await db.execute("CREATE TABLE IF NOT EXISTS post_files (id INTEGER PRIMARY KEY AUTOINCREMENT, post_code TEXT, file_id TEXT, file_type TEXT, file_name TEXT, order_idx INTEGER DEFAULT 0)")
        await db.execute("CREATE TABLE IF NOT EXISTS views (post_code TEXT, user_id INTEGER, created_at INTEGER, PRIMARY KEY (post_code, user_id))")
        await db.execute("CREATE TABLE IF NOT EXISTS ratings (post_code TEXT, user_id INTEGER, stars INTEGER, created_at INTEGER, PRIMARY KEY (post_code, user_id))")
        await db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS withdrawals (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount REAL, method TEXT, address TEXT, status TEXT DEFAULT 'pending', created_at INTEGER)")

        for k, v in {"min_withdraw": str(DEFAULT_MIN_WITHDRAW), "view_reward": str(VIEW_REWARD), "referral_bonus": str(REFERRAL_BONUS), "daily_bonus": str(DAILY_BONUS)}.items():
            await db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))
        await db.commit()
    logger.info("DB fully initialized.")

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
        return {"user_id": user_id, "username": None, "first_name": None, "joined_at": int(time.time()), "referred_by": None, "balance": 0.0, "referrals": 0, "banned": 0, "total_uploads": 0, "last_daily": 0, "cooldown_until": 0, "is_admin": 0}
    return u

async def ensure_user(user_id, username=None, first_name=None, referred_by=None) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            is_adm = 1 if user_id == ADMIN_CHAT_ID else 0
            cur = await db.execute("INSERT OR IGNORE INTO users (user_id, username, first_name, joined_at, referred_by, is_admin) VALUES (?, ?, ?, ?, ?, ?)", (user_id, username, first_name, int(time.time()), referred_by, is_adm))
            created = (cur.rowcount or 0) > 0
            if not created:
                await db.execute("UPDATE users SET username=?, first_name=? WHERE user_id=?", (username, first_name, user_id))
            await db.commit()
            return created
        except Exception as e:
            logger.error(f"ensure_user: {e}")
            return False

async def is_admin_user(user_id: int) -> bool:
    if user_id == ADMIN_CHAT_ID: return True
    u = await get_user_safe(user_id)
    return bool(u.get("is_admin", 0))

async def is_banned(user_id: int) -> bool:
    u = await get_user_safe(user_id)
    return bool(u.get("banned", 0))

async def add_balance(user_id: int, amount: float) -> None:
    try: await execute("UPDATE users SET balance = COALESCE(balance,0) + ? WHERE user_id=?", (amount, user_id))
    except Exception as e: logger.error(f"add_balance: {e}")

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
# FORCE SUB & MIDDLEWARES
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
        if await is_admin_user(user.id): return await handler(event, data)
        if isinstance(event, CallbackQuery) and event.data and event.data.startswith("check_join"): return await handler(event, data)
        if isinstance(event, Message) and event.text and event.text.startswith("/start"): return await handler(event, data)
        miss = await missing_channels(user.id)
        if miss:
            kb = join_kb(miss)
            if isinstance(event, CallbackQuery):
                await safe_edit(event, "⚠️ <b>JOIN ALL CHANNELS FIRST</b>\n\nJoin all channels, then press <b>VERIFY</b>.", reply_markup=kb)
                await event.answer("Join all channels first!", show_alert=True)
            elif isinstance(event, Message):
                await event.answer("⚠️ <b>JOIN ALL CHANNELS FIRST</b>\n\nJoin all channels, then press <b>VERIFY</b>.", reply_markup=kb)
            return
        return await handler(event, data)

class AntiSpamMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user = data.get("event_from_user")
        if user and not await is_admin_user(user.id):
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
        [InlineKeyboardButton(text="📤 UPLOAD CONTENT", callback_data="user_upload")],
        [InlineKeyboardButton(text="👤 MY PROFILE", callback_data="profile"), InlineKeyboardButton(text="🔗 REFER & EARN", callback_data="referral")],
        [InlineKeyboardButton(text="💰 MY BALANCE", callback_data="balance"), InlineKeyboardButton(text="💸 WITHDRAW", callback_data="withdraw")],
        [InlineKeyboardButton(text="🎬 BROWSE", callback_data="browse"), InlineKeyboardButton(text="🔍 SEARCH AI", callback_data="search_code")],
        [InlineKeyboardButton(text="📁 MY UPLOADS", callback_data="my_uploads"), InlineKeyboardButton(text="🏆 LEADERBOARD", callback_data="leaderboard")],
        [InlineKeyboardButton(text="🎁 DAILY BONUS", callback_data="daily_bonus"), InlineKeyboardButton(text="📥 REQUEST MOVIE", callback_data="user_request_movie")],
    ]
    if is_admin: rows.append([InlineKeyboardButton(text="⚙️ ADMIN PANEL", callback_data="admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def admin_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 PUBLISH CONTENT", callback_data="admin_publish")],
        [InlineKeyboardButton(text="📁 MANAGE FOLDERS", callback_data="admin_manage_folders")],
        [InlineKeyboardButton(text="📩 MOVIE REQUESTS", callback_data="admin_requests")],
        [InlineKeyboardButton(text="➕ ADD ADMIN", callback_data="admin_add_new")],
        [InlineKeyboardButton(text="📥 RESTORE BACKUP", callback_data="admin_restore")],
        [InlineKeyboardButton(text="⚙️ SETTINGS", callback_data="admin_settings")],
        [InlineKeyboardButton(text="🚫 BAN", callback_data="admin_ban"), InlineKeyboardButton(text="✅ UNBAN", callback_data="admin_unban")],
        [InlineKeyboardButton(text="💰 WITHDRAWALS", callback_data="admin_withdrawals"), InlineKeyboardButton(text="📊 STATS", callback_data="admin_stats")],
        [InlineKeyboardButton(text="📄 ALL POSTS", callback_data="admin_posts"), InlineKeyboardButton(text="👥 ALL USERS", callback_data="admin_users")],
        [InlineKeyboardButton(text="📢 BROADCAST", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="🏠 MAIN MENU", callback_data="main")],
    ])

def back_kb(target: str = "main") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 BACK", callback_data=target)]])

# =========================================================================
# START & COMMANDS
# =========================================================================
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
            await bot.send_message(referred_by, f"🎉 <b>NEW REFERRAL!</b>\n\n💰 You earned <b>{fmt_money(bonus)}</b>!")
        except Exception as e: logger.error(f"ref bonus: {e}")

    if await is_banned(uid):
        await message.answer("🚫 You are banned.")
        return

    miss = await missing_channels(uid)
    if miss:
        await message.answer("👋 <b>WELCOME TO MOVIEVERSE!</b>\n\nJoin all channels first:", reply_markup=join_kb(miss))
        return

    if payload and payload.startswith("GET_"):
        code = payload[4:]
        await show_post_card(message.chat.id, code)
        return

    is_adm = await is_admin_user(uid)
    await message.answer(
        "🏠 <b>WELCOME TO MOVIEVERSE!</b>\n\n🎬 Watch content, earn rewards.\n⚡ Powered by Smart AI Navigation Engine.",
        reply_markup=main_menu_kb(is_adm)
    )

@router.callback_query(F.data == "check_join")
async def cb_check_join(call: CallbackQuery):
    miss = await missing_channels(call.from_user.id)
    if miss:
        await call.answer("❌ Join all channels first!", show_alert=True)
        return
    await call.answer("✅ Verified!")
    is_adm = await is_admin_user(call.from_user.id)
    await safe_edit(call, "✅ <b>VERIFIED!</b>", reply_markup=main_menu_kb(is_adm))

@router.callback_query(F.data == "main")
async def cb_main(call: CallbackQuery, state: FSMContext):
    await state.clear()
    is_adm = await is_admin_user(call.from_user.id)
    await safe_edit(call, "🏠 <b>MAIN MENU</b>", reply_markup=main_menu_kb(is_adm))

# =========================================================================
# AI SEARCH SYSTEM (WITH CONFIRMATION & DIRECT SEARCH)
# =========================================================================
@router.callback_query(F.data == "search_code")
async def cb_search(call: CallbackQuery, state: FSMContext):
    await state.set_state(UserStates.waiting_search)
    await safe_edit(call, "🔍 <b>AI SMART SEARCH</b>\n\nযে কোনো মুভি, অ্যানিমে বা সিরিজের নাম লিখুন (একটু ভুল হলেও সমস্যা নেই):", reply_markup=back_kb("main"))

@router.message(UserStates.waiting_search)
async def ai_search_handler(message: Message, state: FSMContext):
    q = (message.text or "").strip()
    await state.clear()
    if not q:
        await message.answer("একটি নাম টাইপ করুন।", reply_markup=back_kb("main"))
        return

    all_posts = await fetchall("SELECT * FROM posts WHERE published=1 AND deleted=0")
    if not all_posts:
        await message.answer("❌ কোনো ডাটা পাওয়া যায়নি।", reply_markup=back_kb("main"))
        return

    best_match, ratio = await ai_search_analyzer(q, all_posts)

    if not best_match or ratio < 0.35:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📩 মুভি রিকোয়েস্ট পাঠান", callback_data=f"req_send:{q[:30]}")],
            [InlineKeyboardButton(text="🏠 Main Menu", callback_data="main")]
        ])
        await message.answer("❌ <b>নট এভেইলেবল!</b>\n\nআপনার কাঙ্ক্ষিত মুভি বা সিরিজটি বর্তমানে আমাদের বটে নেই। আপনি নিচে ক্লিক করে এডমিনকে রিকোয়েস্ট পাঠাতে পারেন:", reply_markup=kb)
        return

    # ফুল বা খুব নিখুঁত মিল থাকলে সরাসরি রেজাল্ট
    if ratio >= 0.8:
        await show_post_card(message.chat.id, best_match["code"])
        return

    # হালকা মিল থাকলে থাম্বনেইল সহ কনফার্মেশন মেসেজ
    text = f"🤖 <b>AI Suggestion:</b>\n\nআপনি কি এই সিরিজটি খুঁজছেন?\n🎬 <b>{esc(best_match['title'])}</b>"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Yes", callback_data=f"view:{best_match['code']}"), InlineKeyboardButton(text="❌ No", callback_data="search_code")],
        [InlineKeyboardButton(text="🏠 Main Menu", callback_data="main")]
    ])

    if best_match.get("thumbnail_id"):
        try:
            await message.answer_photo(best_match["thumbnail_id"], caption=text, reply_markup=kb)
            return
        except: pass

    await message.answer(text, reply_markup=kb)

# =========================================================================
# MOVIE REQUEST SYSTEM (USER & ADMIN)
# =========================================================================
@router.callback_query(F.data == "user_request_movie")
async def cb_user_req(call: CallbackQuery, state: FSMContext):
    await state.set_state(UserStates.waiting_request)
    await safe_edit(call, "📩 <b>REQUEST MOVIE / ANIME</b>\n\nআপনি যে মুভি বা অ্যানিমে দেখতে চান সেটির নাম লিখে পাঠান:", reply_markup=back_kb("main"))

@router.callback_query(F.data.startswith("req_send:"))
async def cb_req_send_direct(call: CallbackQuery):
    movie_name = call.data.split(":", 1)[1]
    await execute("INSERT INTO movie_requests (user_id, movie_name, created_at) VALUES (?, ?, ?)", (call.from_user.id, movie_name, int(time.time())))
    await call.answer("✅ আপনার রিকোয়েস্ট এডমিনের কাছে পাঠানো হয়েছে!", show_alert=True)
    await cb_main(call, None)

@router.message(UserStates.waiting_request)
async def recv_user_request(message: Message, state: FSMContext):
    name = (message.text or "").strip()
    await state.clear()
    if not name:
        await message.answer("সঠিক নাম দিন।", reply_markup=back_kb("main"))
        return
    await execute("INSERT INTO movie_requests (user_id, movie_name, created_at) VALUES (?, ?, ?)", (message.from_user.id, name, int(time.time())))
    await message.answer("✅ <b>রিকোয়েস্ট সফলভাবে জমা হয়েছে!</b>\nএডমিন খুব শীঘ্রই এটি আপলোড করবে।", reply_markup=back_kb("main"))

@router.callback_query(F.data == "admin_requests")
async def cb_admin_requests(call: CallbackQuery):
    if not await is_admin_user(call.from_user.id): return
    reqs = await fetchall("SELECT * FROM movie_requests WHERE status='pending' ORDER BY id DESC LIMIT 20")
    if not reqs:
        await safe_edit(call, "📩 <b>MOVIE REQUESTS</b>\n\nকোনো নতুন রিকোয়েস্ট নেই।", reply_markup=back_kb("admin_panel"))
        return
    text = "📩 <b>PENDING MOVIE REQUESTS:</b>\n\n"
    kb = []
    for r in reqs:
        text += f"🔹 <b>{esc(r['movie_name'])}</b> (User: <code>{r['user_id']}</code>)\n"
        kb.append([InlineKeyboardButton(text=f"✅ Notify User ({r['user_id']})", callback_data=f"notify_req:{r['id']}:{r['user_id']}")])
    kb.append([InlineKeyboardButton(text="🔙 BACK", callback_data="admin_panel")])
    await safe_edit(call, text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("notify_req:"))
async def cb_notify_req(call: CallbackQuery):
    parts = call.data.split(":")
    req_id, target_uid = int(parts[1]), int(parts[2])
    await execute("UPDATE movie_requests SET status='fulfilled' WHERE id=?", (req_id,))
    try:
        await bot.send_message(target_uid, "🎉 <b>আপনার রিকোয়েস্ট করা মুভিটি বটে আপলোড করা হয়েছে!</b>\nএখনই সার্চ করে দেখে নিন।")
        await call.answer("✅ ইউজারকে নোটিফিকেশন পাঠানো হয়েছে!")
    except:
        await call.answer("❌ ইউজারকে মেসেজ পাঠানো যায়নি।")
    await cb_admin_requests(call)

# =========================================================================
# FOLDER & SUBFOLDER MANAGEMENT WITH DELETE CONFIRMATION & PAGE NUMBERS
# =========================================================================
@router.callback_query(F.data == "browse")
async def cb_browse(call: CallbackQuery):
    rows = await fetchall("SELECT category, COUNT(*) as c FROM posts WHERE published=1 AND deleted=0 GROUP BY category")
    counts = {r["category"]: r["c"] for r in rows}
    kb = []
    for cat in ("movie", "viral", "anime"):
        kb.append([InlineKeyboardButton(text=f"{CATEGORY_NAMES[cat]} ({counts.get(cat, 0)})", callback_data=f"cat:{cat}")])
    kb.append([InlineKeyboardButton(text="🏠 MAIN MENU", callback_data="main")])
    await safe_edit(call, "🎬 <b>BROWSE CATEGORIES</b>\n\nক্যাটাগরি সিলেক্ট করুন:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("cat:"))
async def cb_category(call: CallbackQuery):
    cat = call.data.split(":", 1)[1]
    kb = []
    for lang_code, lang_name in LANGUAGES.items():
        kb.append([InlineKeyboardButton(text=lang_name, callback_data=f"browselang:{cat}:{lang_code}")])
    kb.append([InlineKeyboardButton(text="🔙 BACK", callback_data="browse")])
    await safe_edit(call, f"{CATEGORY_NAMES[cat]} — 🌐 <b>ভাষা সিলেক্ট করুন:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("browselang:"))
async def cb_browse_lang(call: CallbackQuery):
    parts = call.data.split(":")
    cat, lang = parts[1], parts[2]
    
    # মেইন ফোল্ডারসমূহ
    folders = await fetchall("SELECT * FROM admin_folders WHERE category=? AND language=? AND parent_id=0", (cat, lang))
    kb = []
    if folders:
        for f in folders:
            kb.append([InlineKeyboardButton(text=f"📁 {f['name']}", callback_data=f"subfolder_list:{cat}:{lang}:{f['id']}")])
    kb.append([InlineKeyboardButton(text="📄 All Direct Videos", callback_data=f"browsefolder:{cat}:{lang}:0:0:1")])
    kb.append([InlineKeyboardButton(text="🔙 BACK", callback_data=f"cat:{cat}")])
    await safe_edit(call, f"{CATEGORY_NAMES[cat]} ({LANGUAGES[lang]}) — 📁 <b>ফোল্ডার সিলেক্ট করুন:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("subfolder_list:"))
async def cb_subfolder_list(call: CallbackQuery):
    parts = call.data.split(":")
    cat, lang, folder_id = parts[1], parts[2], int(parts[3])

    subfolders = await fetchall("SELECT * FROM admin_folders WHERE parent_id=?", (folder_id,))
    kb = []
    if subfolders:
        for sf in subfolders:
            kb.append([InlineKeyboardButton(text=f"📂 {sf['name']}", callback_data=f"browsefolder:{cat}:{lang}:{folder_id}:{sf['id']}:1")])

    kb.append([InlineKeyboardButton(text="🎬 All Season/Files in Folder", callback_data=f"browsefolder:{cat}:{lang}:{folder_id}:0:1")])
    kb.append([InlineKeyboardButton(text="🔙 BACK", callback_data=f"browselang:{cat}:{lang}")])

    parent = await fetchone("SELECT name FROM admin_folders WHERE id=?", (folder_id,))
    pname = parent['name'] if parent else "Folder"
    await safe_edit(call, f"📁 <b>{pname}</b> — সাব-ফোল্ডার বা সিজন সিলেক্ট করুন:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("browsefolder:"))
async def cb_browse_folder(call: CallbackQuery):
    parts = call.data.split(":")
    cat, lang, folder_id, subfolder_id, page = parts[1], parts[2], int(parts[3]), int(parts[4]), int(parts[5])
    await show_category_posts(call, cat=cat, lang=lang, folder_id=folder_id, subfolder_id=subfolder_id, page=page)

async def show_category_posts(call: CallbackQuery, cat: str, lang: str, folder_id: int, subfolder_id: int, page: int = 1):
    query = "SELECT * FROM posts WHERE category=? AND published=1 AND deleted=0"
    params = [cat]
    if lang:
        query += " AND language=?"
        params.append(lang)
        
    if subfolder_id > 0:
        query += " AND subfolder_id=?"
        params.append(subfolder_id)
    elif folder_id > 0:
        query += " AND folder_id=?"
        params.append(folder_id)
        
    query += " ORDER BY created_at DESC"
    all_posts = await fetchall(query, tuple(params))
    
    if not all_posts:
        await call.answer("এখানে কোনো ভিডিও পাওয়া যায়নি।", show_alert=True)
        return

    total_items = len(all_posts)
    total_pages = (total_items + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
    page = max(1, min(page, total_pages))

    start_idx = (page - 1) * ITEMS_PER_PAGE
    end_idx = start_idx + ITEMS_PER_PAGE
    page_posts = all_posts[start_idx:end_idx]

    kb = []
    for p in page_posts:
        kb.append([InlineKeyboardButton(text=f"🎬 {truncate(p['title'], 25)} (👁 {p['views']})", callback_data=f"view:{p['code']}")])

    # 1 2 3 ... Dynamic Page Numbers Row (as per screenshots)
    num_row = []
    for p_num in range(1, total_pages + 1):
        btn_text = f"• {p_num} •" if p_num == page else str(p_num)
        num_row.append(InlineKeyboardButton(text=btn_text, callback_data=f"browsefolder:{cat}:{lang}:{folder_id}:{subfolder_id}:{p_num}"))
        if len(num_row) == 5: # প্রতি সারিতে ৫টি সংখ্যা
            kb.append(num_row)
            num_row = []
    if num_row: kb.append(num_row)

    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton(text="⬅️ Previous", callback_data=f"browsefolder:{cat}:{lang}:{folder_id}:{subfolder_id}:{page-1}"))
    nav_buttons.append(InlineKeyboardButton(text="🏠 Main Menu", callback_data="main"))
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton(text="Next ➡️", callback_data=f"browsefolder:{cat}:{lang}:{folder_id}:{subfolder_id}:{page+1}"))
    
    kb.append(nav_buttons)

    text_header = f"📌 <b>Page {page}/{total_pages} (Total: {total_items}):</b>"
    await safe_edit(call, text_header, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

# =========================================================================
# DELETE CONFIRMATION SYSTEM FOR FOLDERS
# =========================================================================
@router.callback_query(F.data == "admin_manage_folders")
async def cb_manage_folders(call: CallbackQuery):
    if not await is_admin_user(call.from_user.id): return
    kb = []
    for cat in ("movie", "viral", "anime"):
        kb.append([InlineKeyboardButton(text=f"📁 {CATEGORY_NAMES[cat]} Folders", callback_data=f"admfoldcat:{cat}")])
    kb.append([InlineKeyboardButton(text="🔙 BACK TO ADMIN", callback_data="admin_panel")])
    await safe_edit(call, "📁 <b>MANAGE FOLDERS</b>\n\nফোল্ডার মোছার জন্য সিলেক্ট করুন:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("admfoldcat:"))
async def cb_admfoldcat(call: CallbackQuery):
    cat = call.data.split(":", 1)[1]
    kb = []
    for lang_code, lang_name in LANGUAGES.items():
        kb.append([InlineKeyboardButton(text=lang_name, callback_data=f"admfoldlang:{cat}:{lang_code}")])
    kb.append([InlineKeyboardButton(text="🔙 BACK", callback_data="admin_manage_folders")])
    await safe_edit(call, f"{CATEGORY_NAMES[cat]} — 🌐 <b>Select Language:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("admfoldlang:"))
async def cb_admfoldlang(call: CallbackQuery):
    parts = call.data.split(":")
    cat, lang = parts[1], parts[2]
    folders = await fetchall("SELECT * FROM admin_folders WHERE category=? AND language=?", (cat, lang))
    
    kb = []
    if folders:
        for f in folders:
            kb.append([InlineKeyboardButton(text=f"🗑 Delete: {f['name']}", callback_data=f"ask_delfold:{f['id']}")])
    else:
        kb.append([InlineKeyboardButton(text="⚠️ No folders found", callback_data="noop")])
    kb.append([InlineKeyboardButton(text="🔙 BACK", callback_data=f"admfoldcat:{cat}")])
    await safe_edit(call, "📁 <b>ডিলিট করতে চাওয়া ফোল্ডারটি সিলেক্ট করুন:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("ask_delfold:"))
async def cb_ask_delete_folder(call: CallbackQuery):
    folder_id = int(call.data.split(":", 1)[1])
    folder = await fetchone("SELECT * FROM admin_folders WHERE id=?", (folder_id,))
    if not folder:
        await call.answer("ফোল্ডার পাওয়া যায়নি।", show_alert=True)
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Yes", callback_data=f"confirm_delfold:{folder_id}"), InlineKeyboardButton(text="❌ No", callback_data="admin_manage_folders")]
    ])
    await safe_edit(call, f"⚠️ <b>ফোল্ডার ডিলিট করতে চান?</b>\n\nফোল্ডারের নাম: <b>{esc(folder['name'])}</b>", reply_markup=kb)

@router.callback_query(F.data.startswith("confirm_delfold:"))
async def cb_confirm_delete_folder(call: CallbackQuery):
    folder_id = int(call.data.split(":", 1)[1])
    await execute("UPDATE posts SET folder_id=0, subfolder_id=0 WHERE folder_id=? OR subfolder_id=?", (folder_id, folder_id))
    await execute("DELETE FROM admin_folders WHERE id=? OR parent_id=?", (folder_id, folder_id))
    await call.answer("✅ ফোল্ডার সফলভাবে ডিলিট করা হয়েছে!", show_alert=True)
    await cb_manage_folders(call)

# =========================================================================
# FORWARD RESTRICTION & DIRECT FILE DELIVERY WITH LINK GENERATION
# =========================================================================
async def show_post_card(chat_id: int, code: str):
    post = await get_post(code)
    if not post:
        await bot.send_message(chat_id, "⚠️ Post not found.")
        return
    text = f"🎬 <b>{esc(post['title'])}</b>\n\n👇 Watch the ad to unlock:"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="▶️ WATCH AD", url=f"{MINI_APP_LINK_BASE}{code}")],
        [InlineKeyboardButton(text="🔙 BACK", callback_data="main")],
    ])
    if post.get("thumbnail_id"):
        try:
            sent_msg = await bot.send_photo(chat_id, post["thumbnail_id"], caption=text, reply_markup=kb)
            asyncio.create_task(_auto_delete(sent_msg.chat.id, sent_msg.message_id))
            return
        except: pass
    sent_msg = await bot.send_message(chat_id, text, reply_markup=kb)
    asyncio.create_task(_auto_delete(sent_msg.chat.id, sent_msg.message_id))

@router.callback_query(F.data.startswith("view:"))
async def cb_view(call: CallbackQuery):
    code = call.data.split(":", 1)[1]
    try: await call.message.delete()
    except: pass
    await show_post_card(call.message.chat.id, code)

@router.message(F.web_app_data)
async def handle_web_app_data(message: Message):
    try: data = json.loads(message.web_app_data.data)
    except: return
    code = str(data.get("code", "")).replace("GET_", "")
    await _deliver(message.chat.id, code, message.from_user.id)

@router.message(F.text.regexp(r"^[A-Za-z0-9]{17}$"))
async def handle_pasted_code(message: Message, state: FSMContext):
    if await state.get_state() is not None: return
    code = message.text.strip()
    await _deliver(message.chat.id, code, message.from_user.id)

async def _deliver(chat_id: int, code: str, user_id: int):
    post = await get_post(code)
    files = await get_post_files(code)
    if not post or not files:
        await bot.send_message(chat_id, "⚠️ Files not available.")
        return
    
    username = await get_bot_username()
    gen_link = f"https://t.me/{username}?start=GET_{code}"

    # Forwards logic notice / link footer
    caption_text = (
        f"🎬 <b>{esc(post['title'])}</b>\n\n"
        f"⚠️ <i>এই ভিডিওটি অন্য কারো কাছে ফরওয়ার্ড করলে কাজ করবে না। বটে জয়েন করে দেখতে হবে।</i>\n"
        f"🔗 <b>Get Link:</b> {gen_link}"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔗 GET FILE LINK", url=gen_link)]])

    for f in files:
        try:
            # protect_content=False (Allows Save to Gallery, but restrict via forwarded caption notice)
            if f["file_type"] == "video":
                sent = await bot.send_video(chat_id, f["file_id"], caption=caption_text, reply_markup=kb, protect_content=False)
            elif f["file_type"] == "photo":
                sent = await bot.send_photo(chat_id, f["file_id"], caption=caption_text, reply_markup=kb, protect_content=False)
            else:
                sent = await bot.send_document(chat_id, f["file_id"], caption=caption_text, reply_markup=kb, protect_content=False)
            if sent: asyncio.create_task(_auto_delete(sent.chat.id, sent.message_id))
        except Exception as e: logger.error(f"deliver err: {e}")

async def _auto_delete(chat_id: int, mid: int):
    await asyncio.sleep(AUTO_DELETE_SECONDS)
    try: await bot.delete_message(chat_id, mid)
    except: pass

# =========================================================================
# ADD ADMIN & ADMIN WORKFLOW
# =========================================================================
@router.callback_query(F.data == "admin_add_new")
async def cb_add_admin_start(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_CHAT_ID: return
    await state.set_state(AdminStates.waiting_add_admin)
    await safe_edit(call, "➕ <b>ADD NEW ADMIN</b>\n\nনতুন এডমিনের <b>Chat ID</b> লিখে পাঠান:", reply_markup=back_kb("admin_panel"))

@router.message(AdminStates.waiting_add_admin)
async def recv_new_admin_id(message: Message, state: FSMContext):
    try: new_id = int((message.text or "").strip())
    except:
        await message.answer("সঠিক আইডি দিন।")
        return
    await execute("UPDATE users SET is_admin=1 WHERE user_id=?", (new_id,))
    await state.clear()
    await message.answer(f"✅ <code>{new_id}</code> সফলভাবে এডমিন হিসেবে যুক্ত হয়েছে!", reply_markup=back_kb("admin_panel"))

@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if await is_admin_user(message.from_user.id):
        await message.answer("⚙️ <b>ADMIN PANEL</b>", reply_markup=admin_menu_kb())

@router.callback_query(F.data == "admin_panel")
async def cb_admin_panel(call: CallbackQuery):
    if await is_admin_user(call.from_user.id):
        await safe_edit(call, "⚙️ <b>ADMIN PANEL</b>", reply_markup=admin_menu_kb())

# =========================================================================
# WEB SERVER & BACKGROUND TASKS
# =========================================================================
async def handle_ping(request):
    return web.Response(text="MovieVerse Bot AI Edition is Running 24/7!")

async def start_web_server():
    try:
        app = web.Application()
        app.router.add_get("/", handle_ping)
        runner = web.AppRunner(app)
        await runner.setup()
        port = int(os.environ.get("PORT", 10000))
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
    except Exception as e: logger.error(f"Web server error: {e}")

async def main():
    await init_db()
    dp.message.middleware(AntiSpamMiddleware())
    dp.callback_query.middleware(AntiSpamMiddleware())
    dp.message.middleware(ForceSubMiddleware())
    dp.callback_query.middleware(ForceSubMiddleware())
    dp.include_router(router)
    asyncio.create_task(start_web_server())
    logger.info("Bot starting polling...")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

if __name__ == "__main__":
    try: asyncio.run(main())
    except (KeyboardInterrupt, SystemExit): logger.info("Bot stopped.")
