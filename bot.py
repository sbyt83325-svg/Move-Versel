#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MovieVerse Bot — Fully Updated Edition
Includes:
 - Dynamic Sliding Page Pagination (Scrollable Number Pagination)
 - Folder Edit (Rename), Sub-folder Add & Remove
 - File Move & Copy between Folders/Sub-folders
 - Multi-language AI Smart Search
 - 60-Second Auto Backup & Web Server
"""

import asyncio
import html
import json
import logging
import os
import re
import time
import secrets
import string
import shutil
import traceback
from typing import Optional, Union, List

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
from aiohttp import web

# =========================================================================
# CONFIG & AI API KEY
# =========================================================================
BOT_TOKEN = os.environ.get(
    "BOT_TOKEN",
    "8999148581:AAExMi5DcfVS06RzED5R0qhRJPWKknczotA",
)
ADMIN_CHAT_ID = int(os.environ.get("ADMIN_CHAT_ID", "8806711354"))
AI_API_KEY = "AQ.Ab8RN6KQBJ1Br-6ih2Wz3CWx3zl--IHUWubd3ErCj6sULshNhQ"

DB_PATH = os.path.join(os.getcwd(), "movieverse.db")

AUTO_DELETE_SECONDS = 1200
BACKUP_INTERVAL_SECONDS = 60
ANTI_SPAM_COOLDOWN = 0.5

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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("MovieVerse")

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
    waiting_confirm = State()
    waiting_ban_id = State()
    waiting_unban_id = State()
    waiting_restore_db = State()
    waiting_setting = State()
    waiting_broadcast = State()
    waiting_folder_name = State()
    waiting_subfolder_name = State()
    waiting_admin_add = State()
    waiting_edit_folder = State()
    waiting_add_sub_dynamic = State()

class UserStates(StatesGroup):
    uploading_files = State()
    waiting_title = State()
    waiting_thumb = State()
    waiting_search = State()

class WithdrawStates(StatesGroup):
    waiting_amount = State()
    waiting_method = State()
    waiting_address = State()

# =========================================================================
# HELPER UTILS
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
# AI MULTI-LANGUAGE SMART SEARCH ENGINE
# =========================================================================
def parse_season_episode(text: str):
    text_lower = text.lower()
    bn_digits = {'০': '0', '১': '1', '২': '2', '৩': '3', '৪': '4', '৫': '5', '৬': '6', '৭': '7', '৮': '8', '৯': '9'}
    for b, e in bn_digits.items():
        text_lower = text_lower.replace(b, e)
        
    season = None
    episode = None
    
    s_match = re.search(r'(?:season|s|সিজন)\s*[:=\-]?\s*(\d+)', text_lower)
    if s_match:
        season = int(s_match.group(1))
        
    e_match = re.search(r'(?:episode|ep|e|পর্ব|এপিসোড)\s*[:=\-]?\s*(\d+)', text_lower)
    if e_match:
        episode = int(e_match.group(1))
        
    if not episode:
        nums = re.findall(r'\b\d+\b', text_lower)
        if nums and not season:
            episode = int(nums[0])
            
    clean_title = re.sub(r'(?:season|s|সিজন|episode|ep|e|পর্ব|এপিসোড)\s*[:=\-]?\s*\d+', '', text_lower)
    clean_title = re.sub(r'\b\d+\b', '', clean_title).strip()
    
    return clean_title, season, episode

async def ai_multi_language_search(user_query: str) -> List[dict]:
    clean_q, req_s, req_e = parse_season_episode(user_query)
    all_posts = await fetchall("SELECT * FROM posts WHERE published=1 AND deleted=0")
    matched_posts = []
    
    for post in all_posts:
        title = post["title"].lower()
        title_clean, post_s, post_e = parse_season_episode(title)
        is_title_match = False
        if clean_q and (clean_q in title or title_clean in clean_q):
            is_title_match = True
        elif not clean_q:
            is_title_match = True
            
        if is_title_match:
            if req_s is not None and post_s is not None and req_s != post_s:
                continue
            if req_e is not None and post_e is not None and req_e != post_e:
                continue
            matched_posts.append(post)
    return matched_posts

# =========================================================================
# DATABASE INITIALIZATION
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
                referrals INTEGER DEFAULT 0, banned INTEGER DEFAULT 0,
                total_uploads INTEGER DEFAULT 0, last_daily INTEGER DEFAULT 0,
                cooldown_until INTEGER DEFAULT 0
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY
            )
        """)
        await db.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (ADMIN_CHAT_ID,))

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

        for col, ddl in [
            ("language", "TEXT DEFAULT ''"),
            ("folder_id", "INTEGER DEFAULT 0"),
            ("subfolder_id", "INTEGER DEFAULT 0"),
        ]:
            if not await _col_exists(db, "posts", col):
                try: await db.execute(f"ALTER TABLE posts ADD COLUMN {col} {ddl}")
                except: pass

        await db.execute("""
            CREATE TABLE IF NOT EXISTS admin_folders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER,
                category TEXT,
                language TEXT,
                name TEXT
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS admin_subfolders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                folder_id INTEGER,
                name TEXT
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
    logger.info("DB initialized & ready.")

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

async def is_admin_user(user_id: int) -> bool:
    if user_id == ADMIN_CHAT_ID:
        return True
    row = await fetchone("SELECT 1 FROM admins WHERE user_id=?", (user_id,))
    return bool(row)

async def get_setting(key: str, default=None):
    row = await fetchone("SELECT value FROM settings WHERE key=?", (key,))
    return row["value"] if row else default

async def set_setting(key: str, value: str) -> None:
    await execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))

async def get_user_safe(user_id: int) -> dict:
    u = await fetchone("SELECT * FROM users WHERE user_id=?", (user_id,))
    if not u:
        return {"user_id": user_id, "username": None, "first_name": None, "joined_at": int(time.time()), "referred_by": None, "balance": 0.0, "referrals": 0, "banned": 0, "total_uploads": 0, "last_daily": 0, "cooldown_until": 0}
    for k, v in [("username", None), ("first_name", None), ("joined_at", int(time.time())), ("referred_by", None), ("balance", 0.0), ("referrals", 0), ("banned", 0), ("total_uploads", 0), ("last_daily", 0), ("cooldown_until", 0)]:
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
        [InlineKeyboardButton(text="🎬 BROWSE", callback_data="browse"), InlineKeyboardButton(text="🔍 AI SEARCH", callback_data="search_code")],
        [InlineKeyboardButton(text="📁 MY UPLOADS", callback_data="my_uploads"), InlineKeyboardButton(text="🏆 LEADERBOARD", callback_data="leaderboard")],
        [InlineKeyboardButton(text="🎁 DAILY BONUS", callback_data="daily_bonus"), InlineKeyboardButton(text="ℹ️ HELP", callback_data="help")],
    ]
    if is_admin: rows.append([InlineKeyboardButton(text="⚙️ ADMIN PANEL", callback_data="admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def admin_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 PUBLISH CONTENT", callback_data="admin_publish")],
        [InlineKeyboardButton(text="📁 MANAGE FOLDERS & EDIT", callback_data="admin_manage_folders")],
        [InlineKeyboardButton(text="👑 MANAGE ADMINS", callback_data="admin_manage_admins")],
        [InlineKeyboardButton(text="📥 RESTORE BACKUP", callback_data="admin_restore")],
        [InlineKeyboardButton(text="⚙️ SETTINGS", callback_data="admin_settings")],
        [InlineKeyboardButton(text="🚫 BAN", callback_data="admin_ban"), InlineKeyboardButton(text="✅ UNBAN", callback_data="admin_unban")],
        [InlineKeyboardButton(text="💰 WITHDRAWALS", callback_data="admin_withdrawals"), InlineKeyboardButton(text="📊 STATS", callback_data="admin_stats")],
        [InlineKeyboardButton(text="📄 ALL POSTS (MOVE/COPY)", callback_data="admin_posts")],
        [InlineKeyboardButton(text="👥 ALL USERS", callback_data="admin_users"), InlineKeyboardButton(text="📢 BROADCAST", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="🏠 MAIN MENU", callback_data="main")],
    ])

def back_kb(target: str = "main") -> InlineKeyboardMarkup:
    label = "🏠 MAIN MENU" if target == "main" else "🔙 BACK"
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=label, callback_data=target)]])

def post_card_kb(code: str) -> InlineKeyboardMarkup:
    mini_link = f"{MINI_APP_LINK_BASE}{code}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="▶️ WATCH & UNLOCK", url=mini_link)],
        [InlineKeyboardButton(text="🔙 BACK", callback_data="main")],
    ])

def done_upload_kb(done_cb: str = "user_files_done") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ DONE — SAVE FILES", callback_data=done_cb)],
        [InlineKeyboardButton(text="❌ CANCEL", callback_data="main")],
    ])

# =========================================================================
# BOT COMMANDS REGISTRATION
# =========================================================================
async def register_commands():
    user_cmds = [
        BotCommand(command="start", description="🏠 Main menu"),
        BotCommand(command="profile", description="👤 My profile"),
        BotCommand(command="balance", description="💰 Balance"),
        BotCommand(command="refer", description="🔗 Referral link"),
        BotCommand(command="withdraw", description="💸 Withdraw"),
        BotCommand(command="help", description="ℹ️ Help"),
    ]
    admin_cmds = user_cmds + [
        BotCommand(command="admin", description="⚙️ Admin panel"),
        BotCommand(command="backup", description="📥 DB backup"),
        BotCommand(command="stats", description="📊 Statistics"),
    ]
    try:
        await bot.set_my_commands(user_cmds, scope=BotCommandScopeDefault())
        await bot.set_my_commands(admin_cmds, scope=BotCommandScopeChat(chat_id=ADMIN_CHAT_ID))
    except Exception as e:
        logger.warning(f"commands: {e}")

# =========================================================================
# START & FORWARD RESTRICTION
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
            await bot.send_message(referred_by, f"🎉 <b>NEW REFERRAL!</b>\n\n💰 You earned <b>{fmt_money(bonus)}</b>!\n👥 Keep inviting!")
        except Exception as e:
            logger.error(f"ref bonus: {e}")

    if await is_banned(uid):
        await message.answer("🚫 You are banned.")
        return

    miss = await missing_channels(uid)
    if miss:
        await message.answer("👋 <b>WELCOME TO MOVIEVERSE!</b>\n\nTo continue, please join <b>ALL</b> our channels:", reply_markup=join_kb(miss))
        return

    if payload and payload.startswith("GET_"):
        code = payload[4:]
        await show_post_card(message.chat.id, code)
        return

    is_adm = await is_admin_user(uid)
    await message.answer(
        "🏠 <b>WELCOME TO MOVIEVERSE!</b>\n\n🎬 Watch content, earn rewards.\n💸 $0.0001 per view, $0.025 per referral.",
        reply_markup=main_menu_kb(is_adm))

@router.message(F.forward_date)
async def handle_forwarded_content(message: Message):
    username = await get_bot_username()
    text = (
        "🚫 <b>Not Available / Restricted!</b>\n\n"
        "বট থেকে অন্য কোনো চ্যানেলে বা ইউজারকে ভিডিও সরাসরি ফরওয়ার্ড করা যাবে না। "
        "ভিডিও দেখতে আমাদের বটের লিংকে প্রবেশ করুন:\n\n"
        f"🤖 Bot Username: @{username}\n"
        f"🔗 স্টার্ট লিংক: https://t.me/{username}"
    )
    await message.answer(text, disable_web_page_preview=True)

@router.callback_query(F.data == "check_join")
async def cb_check_join(call: CallbackQuery):
    miss = await missing_channels(call.from_user.id)
    if miss:
        await call.answer("❌ Join all channels first!", show_alert=True)
        try: await call.message.edit_reply_markup(reply_markup=join_kb(miss))
        except: pass
        return
    await call.answer("✅ Verified!")
    is_adm = await is_admin_user(call.from_user.id)
    await safe_edit(call, "✅ <b>VERIFIED!</b>", reply_markup=main_menu_kb(is_adm))

@router.callback_query(F.data == "main")
async def cb_main(call: CallbackQuery, state: FSMContext):
    await state.clear()
    is_adm = await is_admin_user(call.from_user.id)
    await safe_edit(call, "🏠 <b>MAIN MENU</b>", reply_markup=main_menu_kb(is_adm))

@router.callback_query(F.data == "help")
async def cb_help(call: CallbackQuery):
    await safe_edit(call, "ℹ️ <b>HELP & INFO</b>\n\n🎬 <b>Browse:</b> Find content by category & seasons\n🔍 <b>AI Search:</b> Smart search supporting multi-language queries\n📤 <b>Upload:</b> Upload & generate share links\n💸 <b>Withdraw:</b> Minimum $10 via Binance/USDT", reply_markup=back_kb("main"))

# =========================================================================
# USER PROFILE & EARNINGS
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

    codes_txt = ""
    if posts:
        codes_txt = "\n📄 <b>YOUR CONTENT:</b>\n"
        for p in posts[:10]:
            codes_txt += f"  {esc(truncate(p['title'], 30))} — 👁 {p.get('views', 0)}\n"
    else:
        codes_txt = "\n📄 <b>YOUR CONTENT:</b> None yet.\n"

    text = (f"👤 <b>MY PROFILE</b>\n━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🆔 <b>Chat ID:</b>  <code>{u['user_id']}</code>\n"
            f"👋 <b>Name:</b>  {esc(u.get('first_name') or 'User')}\n"
            f"📛 <b>Username:</b>  {'@' + esc(u['username']) if u.get('username') else '—'}\n"
            f"📅 <b>Joined:</b>  {fmt_date(u.get('joined_at'))}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━\n📊 <b>STATISTICS</b>\n━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🎬 <b>Posts:</b>  {len(posts)}\n👁 <b>Views:</b>  {total_views}\n👥 <b>Referrals:</b>  {refs}\n{codes_txt}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━\n💰 <b>EARNINGS</b>\n━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🎬 <b>Video:</b>  {fmt_money(video_earn)}\n🔗 <b>Referral:</b>  {fmt_money(ref_earn)}\n💵 <b>TOTAL:</b>  <b>{fmt_money(bal)}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 REFER", callback_data="referral"), InlineKeyboardButton(text="💸 WITHDRAW", callback_data="withdraw")],
        [InlineKeyboardButton(text="🏠 MAIN MENU", callback_data="main")],
    ])
    if edit_call: await safe_edit(edit_call, text, reply_markup=kb)
    else: await bot.send_message(chat_id, text, reply_markup=kb)

@router.callback_query(F.data == "balance")
async def cb_balance(call: CallbackQuery):
    await _show_balance(call.message.chat.id, call.from_user.id, edit_call=call)

@router.message(Command("balance"))
async def cmd_balance(message: Message):
    await _show_balance(message.chat.id, message.from_user.id)

async def _show_balance(chat_id, user_id, edit_call=None):
    u = await get_user_safe(user_id)
    min_w = await get_setting("min_withdraw", str(DEFAULT_MIN_WITHDRAW))
    vr = await get_setting("view_reward", str(VIEW_REWARD))
    rb = await get_setting("referral_bonus", str(REFERRAL_BONUS))
    text = (f"💰 <b>MY BALANCE</b>\n━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"💵 <b>Current:</b>  {fmt_money(u.get('balance', 0))}\n📉 <b>Minimum Withdrawal:</b>  ${min_w}\n\n"
            f"💡 <b>How to earn:</b>\n👁 ${vr} per unique view\n🔗 ${rb} per referral")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💸 WITHDRAW NOW", callback_data="withdraw")],
        [InlineKeyboardButton(text="🏠 MAIN MENU", callback_data="main")],
    ])
    if edit_call: await safe_edit(edit_call, text, reply_markup=kb)
    else: await bot.send_message(chat_id, text, reply_markup=kb)

@router.callback_query(F.data == "referral")
async def cb_referral(call: CallbackQuery):
    await _show_referral(call.message.chat.id, call.from_user.id, edit_call=call)

@router.message(Command("refer"))
async def cmd_refer(message: Message):
    await _show_referral(message.chat.id, message.from_user.id)

async def _show_referral(chat_id, user_id, edit_call=None):
    u = await get_user_safe(user_id)
    username = await get_bot_username()
    link = f"https://t.me/{username}?start=ref_{user_id}"
    bonus = float(await get_setting("referral_bonus", str(REFERRAL_BONUS)))
    refs = int(u.get("referrals", 0) or 0)
    earned = refs * bonus

    text = (f"🔗 <b>REFER & EARN</b>\n━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🎁 <b>Invite friends and earn!</b>\n\n💵 <b>Reward per referral:</b>  <b>{fmt_money(bonus)}</b>\n"
            f"⚡ <b>Instant credit</b>\n♾ <b>Unlimited</b> referrals\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━\n📊 <b>YOUR STATS</b>\n━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"👥 <b>Total Referrals:</b>  {refs}\n💰 <b>Earned:</b>  {fmt_money(earned)}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━\n🔗 <b>YOUR LINK:</b>\n<code>{link}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━")
    share = f"🎬 Join MovieVerse & earn!\n{link}"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 SHARE INVITE LINK", url=f"https://t.me/share/url?url={link}&text={share}")],
        [InlineKeyboardButton(text="📋 COPY LINK", callback_data="copy_ref"), InlineKeyboardButton(text="👤 PROFILE", callback_data="profile")],
        [InlineKeyboardButton(text="🏠 MAIN MENU", callback_data="main")],
    ])
    if edit_call: await safe_edit(edit_call, text, reply_markup=kb)
    else: await bot.send_message(chat_id, text, reply_markup=kb)

@router.callback_query(F.data == "copy_ref")
async def cb_copy_ref(call: CallbackQuery):
    username = await get_bot_username()
    link = f"https://t.me/{username}?start=ref_{call.from_user.id}"
    await call.answer(f"Your link:\n{link}", show_alert=True)

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
    await execute("UPDATE users SET last_daily=? WHERE user_id=?", (now, call.from_user.id))
    await call.answer(f"🎁 Daily bonus claimed: {fmt_money(bonus)}", show_alert=True)

@router.callback_query(F.data == "leaderboard")
async def cb_leaderboard(call: CallbackQuery):
    rows = await fetchall("SELECT user_id, first_name, username, balance FROM users WHERE banned=0 ORDER BY balance DESC LIMIT 10")
    if not rows:
        await call.answer("No data yet.", show_alert=True)
        return
    text = "🏆 <b>TOP 10 EARNERS</b>\n━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    for i, r in enumerate(rows, 1):
        name = esc(r.get("first_name") or "User")
        medal = ["🥇", "🥈", "🥉"][i - 1] if i <= 3 else f"{i}."
        text += f"{medal} <b>{name}</b> — {fmt_money(r.get('balance', 0))}\n"
    await safe_edit(call, text, reply_markup=back_kb("main"))

# =========================================================================
# BROWSE & DYNAMIC SLIDING NUMBER PAGINATION
# =========================================================================
@router.callback_query(F.data == "browse")
async def cb_browse(call: CallbackQuery):
    rows = await fetchall("SELECT category, COUNT(*) as c FROM posts WHERE published=1 AND deleted=0 GROUP BY category")
    counts = {r["category"]: r["c"] for r in rows}
    kb = []
    for cat in ("movie", "viral", "anime"):
        kb.append([InlineKeyboardButton(text=f"{CATEGORY_NAMES[cat]} ({counts.get(cat, 0)})", callback_data=f"cat:{cat}")])
    kb.append([InlineKeyboardButton(text="🏠 MAIN MENU", callback_data="main")])
    await safe_edit(call, "🎬 <b>BROWSE CATEGORIES</b>\n\nSelect category:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("cat:"))
async def cb_category(call: CallbackQuery):
    cat = call.data.split(":", 1)[1]
    if cat in ("movie", "anime", "viral"):
        kb = []
        for lang_code, lang_name in LANGUAGES.items():
            kb.append([InlineKeyboardButton(text=lang_name, callback_data=f"browselang:{cat}:{lang_code}")])
        kb.append([InlineKeyboardButton(text="🔙 BACK", callback_data="browse")])
        await safe_edit(call, f"{CATEGORY_NAMES[cat]} — 🌐 <b>Select Language:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    else:
        await show_category_posts(call, cat=cat, lang="", folder_id=0, subfolder_id=0, page=1)

@router.callback_query(F.data.startswith("browselang:"))
async def cb_browse_lang(call: CallbackQuery):
    parts = call.data.split(":")
    cat, lang = parts[1], parts[2]
    
    folders = await fetchall("SELECT * FROM admin_folders WHERE category=? AND language=?", (cat, lang))
    if folders:
        kb = []
        for f in folders:
            kb.append([InlineKeyboardButton(text=f"📁 {f['name']}", callback_data=f"browsefolder:{cat}:{lang}:{f['id']}:1")])
        kb.append([InlineKeyboardButton(text="📄 All Direct Videos", callback_data=f"browsefolder:{cat}:{lang}:0:1")])
        kb.append([InlineKeyboardButton(text="🔙 BACK", callback_data=f"cat:{cat}")])
        await safe_edit(call, f"{CATEGORY_NAMES[cat]} ({LANGUAGES[lang]}) — 📁 <b>Select Folder/Season:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    else:
        await show_category_posts(call, cat=cat, lang=lang, folder_id=0, subfolder_id=0, page=1)

@router.callback_query(F.data.startswith("browsefolder:"))
async def cb_browse_folder(call: CallbackQuery):
    parts = call.data.split(":")
    cat, lang, folder_id, page = parts[1], parts[2], int(parts[3]), int(parts[4])
    
    subfolders = await fetchall("SELECT * FROM admin_subfolders WHERE folder_id=?", (folder_id,))
    if subfolders:
        kb = []
        for sf in subfolders:
            kb.append([InlineKeyboardButton(text=f"📂 {sf['name']}", callback_data=f"browsesub:{cat}:{lang}:{folder_id}:{sf['id']}:1")])
        kb.append([InlineKeyboardButton(text="📄 Folder Main Videos", callback_data=f"browseviewposts:{cat}:{lang}:{folder_id}:0:1")])
        kb.append([InlineKeyboardButton(text="🔙 BACK", callback_data=f"browselang:{cat}:{lang}")])
        await safe_edit(call, f"📁 <b>Select Sub-folder / Part:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    else:
        await show_category_posts(call, cat=cat, lang=lang, folder_id=folder_id, subfolder_id=0, page=page)

@router.callback_query(F.data.startswith("browsesub:"))
@router.callback_query(F.data.startswith("browseviewposts:"))
async def cb_browse_subfolder(call: CallbackQuery):
    parts = call.data.split(":")
    cat, lang, folder_id, subfolder_id, page = parts[1], parts[2], int(parts[3]), int(parts[4]), int(parts[5])
    await show_category_posts(call, cat=cat, lang=lang, folder_id=folder_id, subfolder_id=subfolder_id, page=page)

async def show_category_posts(call: CallbackQuery, cat: str, lang: str, folder_id: int, subfolder_id: int, page: int = 1):
    query = "SELECT * FROM posts WHERE category=? AND published=1 AND deleted=0"
    params = [cat]
    
    if lang:
        query += " AND language=?"
        params.append(lang)
    if folder_id > 0:
        query += " AND folder_id=?"
        params.append(folder_id)
    if subfolder_id > 0:
        query += " AND subfolder_id=?"
        params.append(subfolder_id)
        
    query += " ORDER BY created_at DESC"
    all_posts = await fetchall(query, tuple(params))
    
    if not all_posts:
        await call.answer("No posts found here.", show_alert=True)
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

    # ডাইনামিক স্লাইডিং পেজিনেশন (সর্বোচ্চ ৫টি সংখ্যা দেখাবে, স্ক্রোলিং বা স্লাইডিং এর মতো কাজ করবে)
    max_visible_pages = 5
    start_page = max(1, page - max_visible_pages // 2)
    end_page = min(total_pages, start_page + max_visible_pages - 1)
    if end_page - start_page + 1 < max_visible_pages:
        start_page = max(1, end_page - max_visible_pages + 1)

    num_row = []
    for p_num in range(start_page, end_page + 1):
        if p_num == page:
            num_row.append(InlineKeyboardButton(text=f"[{p_num}]", callback_data="noop"))
        else:
            num_row.append(InlineKeyboardButton(text=str(p_num), callback_data=f"browsefolder:{cat}:{lang}:{folder_id}:{p_num}"))
    if num_row:
        kb.append(num_row)

    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton(text="⬅️ Previous", callback_data=f"browsefolder:{cat}:{lang}:{folder_id}:{page-1}"))
    nav_buttons.append(InlineKeyboardButton(text="🏠 Main Menu", callback_data="main"))
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton(text="Next ➡️", callback_data=f"browsefolder:{cat}:{lang}:{folder_id}:{page+1}"))
    kb.append(nav_buttons)

    text_header = f"<b>{CATEGORY_NAMES[cat]}</b>"
    if lang in LANGUAGES:
        text_header += f" | <b>{LANGUAGES[lang]}</b>"
    text_header += f"\n📌 Page <b>{page}/{total_pages}</b> (Total: {total_items}):"

    await safe_edit(call, text_header, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data == "noop")
async def cb_noop(call: CallbackQuery):
    await call.answer()

# =========================================================================
# AI MULTI-LANGUAGE SEARCH HANDLER
# =========================================================================
@router.callback_query(F.data == "search_code")
async def cb_search(call: CallbackQuery, state: FSMContext):
    await state.set_state(UserStates.waiting_search)
    await safe_edit(call, "🔍 <b>AI SMART SEARCH</b>\n\nযেকোনো ভাষায় মুভি/সিরিজের নাম বা সিজন/পর্বের সংখ্যা লিখে পাঠান (যেমন: নারুতো ১০ পর্ব / Naruto S1 Ep10):", reply_markup=back_kb("main"))

@router.message(UserStates.waiting_search)
async def search_handler(message: Message, state: FSMContext):
    q = (message.text or "").strip()
    await state.clear()
    if not q:
        await message.answer("সঠিক নাম লিখে পাঠান।", reply_markup=back_kb("main"))
        return
    
    matches = await ai_multi_language_search(q)
    
    if not matches:
        await message.answer(
            f"❌ <b>এই নামে আমাদের এখানে কোনো মুভি বা সিরিজ পাওয়া যায়নি।</b>",
            reply_markup=back_kb("main")
        )
        return

    text = f"🔍 <b>AI SEARCH RESULTS FOR:</b> <i>{esc(q)}</i>\n\n"
    kb = []
    for p in matches[:15]:
        kb.append([InlineKeyboardButton(text=f"🎬 {truncate(p['title'], 35)}", callback_data=f"view:{p['code']}")])
    kb.append([InlineKeyboardButton(text="🏠 MAIN MENU", callback_data="main")])
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

# =========================================================================
# POST CARD & FILE DELIVERY
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
    try:
        data = json.loads(message.web_app_data.data)
    except Exception as e:
        logger.error(f"web_app_data parse: {e}")
        await message.answer("⚠️ Invalid data from Mini App.")
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
        await message.answer("⚠️ This confirmation was already used.")
        return
    pending_confirm_tokens[key] = token

    post = await get_post(code)
    if not post:
        await message.answer("❌ Post not found.")
        return

    conf_msg = await message.answer("✅ <b>Confirming...</b>")
    asyncio.create_task(_auto_delete(conf_msg.chat.id, conf_msg.message_id))
    await asyncio.sleep(0.4)
    await _deliver(message.chat.id, code, message.from_user.id)

@router.message(F.text.regexp(r"^[A-Za-z0-9]{17}$"))
async def handle_pasted_code(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is not None:
        return
    code = message.text.strip()
    post = await get_post(code)
    if not post:
        await message.answer("❌ Invalid code or video deleted.")
        return
    v_msg = await message.answer("✅ <b>Code Verified!</b> Sending your file...")
    asyncio.create_task(_auto_delete(v_msg.chat.id, v_msg.message_id))
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
    
    info_msg = await bot.send_message(chat_id, f"📥 <b>{esc(post['title'])}</b>\n\nSending {len(files)} file(s). ⚠️ Auto-delete in 20 min.")
    asyncio.create_task(_auto_delete(info_msg.chat.id, info_msg.message_id))

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
# USER UPLOADS
# =========================================================================
@router.callback_query(F.data == "user_upload")
async def cb_upload(call: CallbackQuery, state: FSMContext):
    await state.set_state(UserStates.uploading_files)
    await state.update_data(files=[], edit_code=None)
    await safe_edit(call, f"📤 <b>UPLOAD CONTENT</b>\n\nSend files one by one (max {MAX_USER_FILES}), then tap DONE.", reply_markup=done_upload_kb("user_files_done"))

@router.callback_query(F.data == "user_files_done", UserStates.uploading_files)
async def cb_files_done(call: CallbackQuery, state: FSMContext):
    files = (await state.get_data()).get("files", [])
    if not files:
        await call.answer("Send at least one file.", show_alert=True)
        return
    await state.set_state(UserStates.waiting_title)
    await safe_edit(call, "✏️ Send a <b>title</b>:")

@router.message(UserStates.uploading_files)
async def recv_user_file(message: Message, state: FSMContext):
    data = await state.get_data()
    files = data.get("files", [])
    if len(files) >= MAX_USER_FILES:
        await message.answer(f"Max {MAX_USER_FILES} files. Tap DONE.")
        return
    t = i = n = None
    if message.video: t, i, n = "video", message.video.file_id, message.video.file_name
    elif message.document: t, i, n = "document", message.document.file_id, message.document.file_name
    elif message.audio: t, i, n = "audio", message.audio.file_id, message.audio.file_name
    elif message.photo: t, i, n = "photo", message.photo[-1].file_id, None
    elif message.animation: t, i, n = "document", message.animation.file_id, None
    else:
        await message.answer("⚠️ Unsupported.")
        return
    files.append({"type": t, "id": i, "name": n})
    await state.update_data(files=files)
    await message.answer(f"✅ File {len(files)} received.")

@router.message(UserStates.waiting_title)
async def recv_user_title(message: Message, state: FSMContext):
    title = (message.text or "").strip()
    if not title:
        await message.answer("Send a valid title.")
        return
    data = await state.get_data()
    edit_code = data.get("edit_code")

    if edit_code:
        await execute("UPDATE posts SET title=? WHERE code=?", (title, edit_code))
        await state.clear()
        await message.answer(f"✅ Title updated: <b>{esc(title)}</b>", reply_markup=back_kb("my_uploads"))
        return

    await state.update_data(title=title)
    await state.set_state(UserStates.waiting_thumb)
    await message.answer("🖼 Send a <b>thumbnail</b> photo, or type <code>skip</code>:")

@router.message(UserStates.waiting_thumb)
async def recv_user_thumb(message: Message, state: FSMContext):
    thumb = None
    if message.photo: thumb = message.photo[-1].file_id
    elif (message.text or "").strip().lower() == "skip": thumb = None
    else:
        await message.answer("Send a photo or type <code>skip</code>.")
        return

    data = await state.get_data()
    files = data.get("files", [])
    title = data.get("title", "Untitled")

    code = await unique_code()
    await execute("INSERT INTO posts (code, title, category, owner_id, is_admin, thumbnail_id, created_at, published) VALUES (?, ?, 'private', ?, 0, ?, ?, 0)", (code, title, message.from_user.id, thumb, int(time.time())))
    for i, f in enumerate(files):
        await execute("INSERT INTO post_files (post_code, file_id, file_type, file_name, order_idx) VALUES (?, ?, ?, ?, ?)", (code, f["id"], f["type"], f["name"], i))
    
    await execute("UPDATE users SET total_uploads = COALESCE(total_uploads,0) + 1 WHERE user_id=?", (message.from_user.id,))
    username = await get_bot_username()
    link = f"https://t.me/{username}?start=GET_{code}"
    await state.clear()
    await message.answer(f"✅ <b>UPLOAD COMPLETE!</b>\n\n📌 Title: <b>{esc(title)}</b>\n🔗 Share: <code>{link}</code>", reply_markup=back_kb("main"))

@router.callback_query(F.data == "my_uploads")
async def cb_my_uploads(call: CallbackQuery):
    rows = await fetchall("SELECT * FROM posts WHERE owner_id=? AND deleted=0 ORDER BY created_at DESC LIMIT 20", (call.from_user.id,))
    if not rows:
        await call.answer("You haven't uploaded anything.", show_alert=True)
        return
    kb = [[InlineKeyboardButton(text=f"🎬 {truncate(p['title'], 35)} (👁 {p['views']})", callback_data=f"myedit:{p['code']}")] for p in rows]
    kb.append([InlineKeyboardButton(text="🏠 MAIN MENU", callback_data="main")])
    await safe_edit(call, f"📁 <b>MY UPLOADS</b> ({len(rows)})\n\nTap to manage:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

# =========================================================================
# WITHDRAW SYSTEM
# =========================================================================
@router.callback_query(F.data == "withdraw")
async def cb_withdraw(call: CallbackQuery, state: FSMContext):
    await _start_withdraw(call.message.chat.id, call.from_user.id, state, edit_call=call)

@router.message(Command("withdraw"))
async def cmd_withdraw(message: Message, state: FSMContext):
    await _start_withdraw(message.chat.id, message.from_user.id, state)

async def _start_withdraw(chat_id, user_id, state, edit_call=None):
    u = await get_user_safe(user_id)
    min_w = float(await get_setting("min_withdraw", str(DEFAULT_MIN_WITHDRAW)))
    if float(u.get("balance", 0)) < min_w:
        msg = f"⚠️ Minimum withdrawal is <b>${min_w}</b>.\nYour balance: <b>{fmt_money(u.get('balance', 0))}</b>"
        if edit_call: await safe_edit(edit_call, msg, reply_markup=back_kb("main"))
        else: await bot.send_message(chat_id, msg, reply_markup=back_kb("main"))
        return
    await state.set_state(WithdrawStates.waiting_amount)
    text = f"💸 <b>WITHDRAW</b>\n\n💰 Balance: <b>{fmt_money(u.get('balance', 0))}</b>\n📉 Minimum: <b>${min_w}</b>\n\nEnter amount:"
    if edit_call: await safe_edit(edit_call, text, reply_markup=back_kb("main"))
    else: await bot.send_message(chat_id, text, reply_markup=back_kb("main"))

@router.message(WithdrawStates.waiting_amount)
async def wd_amount(message: Message, state: FSMContext):
    try: amt = float((message.text or "").strip())
    except ValueError:
        await message.answer("Send a valid number.")
        return
    u = await get_user_safe(message.from_user.id)
    min_w = float(await get_setting("min_withdraw", str(DEFAULT_MIN_WITHDRAW)))
    if amt < min_w:
        await message.answer(f"Minimum is ${min_w}.")
        return
    if amt > float(u.get("balance", 0)):
        await message.answer("Insufficient balance.")
        return
    await state.update_data(amount=amt)
    await state.set_state(WithdrawStates.waiting_method)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 BINANCE PAY", callback_data="wdm:Binance Pay")],
        [InlineKeyboardButton(text="💎 USDT TRC20", callback_data="wdm:USDT TRC20")],
        [InlineKeyboardButton(text="🏠 CANCEL", callback_data="main")],
    ])
    await message.answer("Select payment method:", reply_markup=kb)

@router.callback_query(F.data.startswith("wdm:"), WithdrawStates.waiting_method)
async def wd_method(call: CallbackQuery, state: FSMContext):
    method = call.data.split(":", 1)[1]
    await state.update_data(method=method)
    await state.set_state(WithdrawStates.waiting_address)
    await safe_edit(call, f"Send your <b>{esc(method)}</b> wallet address:")

@router.message(WithdrawStates.waiting_address)
async def wd_address(message: Message, state: FSMContext):
    addr = (message.text or "").strip()
    if len(addr) < 10:
        await message.answer("Invalid address.")
        return
    data = await state.get_data()
    amt, method = data["amount"], data["method"]
    await execute("UPDATE users SET balance = COALESCE(balance,0) - ? WHERE user_id=?", (amt, message.from_user.id))
    wid = await execute("INSERT INTO withdrawals (user_id, amount, method, address, status, created_at) VALUES (?, ?, ?, ?, 'pending', ?)", (message.from_user.id, amt, method, addr, int(time.time())))
    await state.clear()
    await message.answer(f"✅ <b>WITHDRAWAL SUBMITTED</b>\n\n🆔 ID: #{wid}\n💵 Amount: {fmt_money(amt)}\n💳 Method: {esc(method)}\n📮 Address: <code>{esc(addr)}</code>", reply_markup=back_kb("main"))
    try:
        await bot.send_message(ADMIN_CHAT_ID, f"💸 <b>NEW WITHDRAWAL</b>\nUser: <code>{message.from_user.id}</code>\nAmount: {fmt_money(amt)}\nMethod: {esc(method)}\nAddress: <code>{esc(addr)}</code>\nID: #{wid}", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ APPROVE", callback_data=f"wdapprove:{wid}"), InlineKeyboardButton(text="❌ REJECT", callback_data=f"wdreject:{wid}")]]))
    except: pass

# =========================================================================
# ADMIN PANEL: FOLDER EDIT, SUB-FOLDER ADD/REMOVE, MOVE/COPY, DB RESTORE
# =========================================================================
@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if not await is_admin_user(message.from_user.id):
        return
    await message.answer("⚙️ <b>ADMIN PANEL</b>", reply_markup=admin_menu_kb())

@router.callback_query(F.data == "admin_panel")
async def cb_admin_panel(call: CallbackQuery):
    if not await is_admin_user(call.from_user.id):
        return
    await safe_edit(call, "⚙️ <b>ADMIN PANEL</b>", reply_markup=admin_menu_kb())

# -------------------------------------------------------------------------
# FILE MOVE & COPY FEATURE
# -------------------------------------------------------------------------
@router.callback_query(F.data == "admin_posts")
async def cb_all_posts(call: CallbackQuery):
    if not await is_admin_user(call.from_user.id):
        return
    rows = await fetchall("SELECT * FROM posts WHERE deleted=0 ORDER BY created_at DESC LIMIT 30")
    if not rows:
        await call.answer("No posts.", show_alert=True)
        return
    kb = []
    for p in rows:
        kb.append([InlineKeyboardButton(text=f"📦 Select: {truncate(p['title'], 25)}", callback_data=f"adm_postopt:{p['code']}")])
    kb.append([InlineKeyboardButton(text="🔙 BACK", callback_data="admin_panel")])
    await safe_edit(call, "📄 <b>ALL POSTS MANAGEMENT</b>\n\nক্লিক করে ভিডিও **Move (স্থানান্তর)** বা **Copy (কপি)** করুন:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("adm_postopt:"))
async def cb_adm_post_options(call: CallbackQuery):
    code = call.data.split(":", 1)[1]
    post = await get_post(code)
    if not post:
        await call.answer("Post not found.", show_alert=True)
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚚 MOVE To Another Folder", callback_data=f"adm_move_start:{code}")],
        [InlineKeyboardButton(text="📋 COPY To Another Folder", callback_data=f"adm_copy_start:{code}")],
        [InlineKeyboardButton(text="🗑 Delete Post", callback_data=f"adm_delpost:{code}")],
        [InlineKeyboardButton(text="🔙 BACK", callback_data="admin_posts")]
    ])
    await safe_edit(call, f"⚙️ <b>Post Selected:</b> <i>{esc(post['title'])}</i>\n\nকী করতে চান সিলেক্ট করুন:", reply_markup=kb)

@router.callback_query(F.data.startswith("adm_delpost:"))
async def cb_adm_delpost(call: CallbackQuery):
    code = call.data.split(":", 1)[1]
    await execute("UPDATE posts SET deleted=1 WHERE code=?", (code,))
    await call.answer("🗑 Post deleted.", show_alert=True)
    await cb_all_posts(call)

@router.callback_query(F.data.startswith("adm_move_start:"))
async def cb_adm_move_start(call: CallbackQuery):
    code = call.data.split(":", 1)[1]
    post = await get_post(code)
    folders = await fetchall("SELECT * FROM admin_folders WHERE category=? AND language=?", (post["category"], post["language"]))
    
    kb = []
    for f in folders:
        marker = " 📍(Current)" if f["id"] == post["folder_id"] else ""
        kb.append([InlineKeyboardButton(text=f"📁 {f['name']}{marker}", callback_data=f"adm_move_do:{code}:{f['id']}")])
    kb.append([InlineKeyboardButton(text="📂 No Folder (Direct)", callback_data=f"adm_move_do:{code}:0")])
    kb.append([InlineKeyboardButton(text="🔙 BACK", callback_data=f"adm_postopt:{code}")])
    
    await safe_edit(call, f"🚚 <b>MOVE FILE:</b> <i>{esc(post['title'])}</i>\n\nকোন ফোল্ডারে স্থানান্তর করবেন সিলেক্ট করুন:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("adm_move_do:"))
async def cb_adm_move_do(call: CallbackQuery):
    parts = call.data.split(":")
    code, target_fid = parts[1], int(parts[2])
    await execute("UPDATE posts SET folder_id=? WHERE code=?", (target_fid, code))
    await call.answer("✅ সফলভাবে মুভ (Move) করা হয়েছে!", show_alert=True)
    await cb_all_posts(call)

@router.callback_query(F.data.startswith("adm_copy_start:"))
async def cb_adm_copy_start(call: CallbackQuery):
    code = call.data.split(":", 1)[1]
    post = await get_post(code)
    folders = await fetchall("SELECT * FROM admin_folders WHERE category=? AND language=?", (post["category"], post["language"]))
    
    kb = []
    for f in folders:
        kb.append([InlineKeyboardButton(text=f"📁 Copy to {f['name']}", callback_data=f"adm_copy_do:{code}:{f['id']}")])
    kb.append([InlineKeyboardButton(text="🔙 BACK", callback_data=f"adm_postopt:{code}")])
    
    await safe_edit(call, f"📋 <b>COPY FILE:</b> <i>{esc(post['title'])}</i>\n\nকোন ফোল্ডারে কপি করে বসাবেন সিলেক্ট করুন:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("adm_copy_do:"))
async def cb_adm_copy_do(call: CallbackQuery):
    parts = call.data.split(":")
    code, target_fid = parts[1], int(parts[2])
    
    orig = await get_post(code)
    orig_files = await get_post_files(code)
    
    new_code = await unique_code()
    new_title = f"{orig['title']} (Copy)"
    
    await execute("INSERT INTO posts (code, title, category, language, owner_id, is_admin, thumbnail_id, created_at, published, folder_id, subfolder_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)", (new_code, new_title, orig["category"], orig["language"], orig["owner_id"], orig["is_admin"], orig["thumbnail_id"], int(time.time()), target_fid, orig["subfolder_id"]))
    
    for f in orig_files:
        await execute("INSERT INTO post_files (post_code, file_id, file_type, file_name, order_idx) VALUES (?, ?, ?, ?, ?)", (new_code, f["file_id"], f["file_type"], f["file_name"], f["order_idx"]))
        
    await call.answer("✅ সফলভাবে কপি (Copy) করা হয়েছে!", show_alert=True)
    await cb_all_posts(call)

# -------------------------------------------------------------------------
# FOLDER MANAGEMENT: EDIT FOLDER, ADD SUB-FOLDER, REMOVE SUB-FOLDER, DELETE
# -------------------------------------------------------------------------
@router.callback_query(F.data == "admin_manage_folders")
async def cb_manage_folders(call: CallbackQuery):
    if not await is_admin_user(call.from_user.id):
        return
    kb = []
    for cat in ("movie", "viral", "anime"):
        kb.append([InlineKeyboardButton(text=f"📁 {CATEGORY_NAMES[cat]} Folders", callback_data=f"admfoldcat:{cat}")])
    kb.append([InlineKeyboardButton(text="🔙 BACK TO ADMIN", callback_data="admin_panel")])
    await safe_edit(call, "📁 <b>MANAGE FOLDERS & SUB-FOLDERS</b>\n\nSelect category:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

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
            kb.append([InlineKeyboardButton(text=f"📁 {f['name']} (Manage/Edit)", callback_data=f"admfold_manage:{f['id']}")])
    else:
        kb.append([InlineKeyboardButton(text="⚠️ No folders found", callback_data="noop")])
    kb.append([InlineKeyboardButton(text="🔙 BACK", callback_data=f"admfoldcat:{cat}")])
    await safe_edit(call, f"📁 <b>Folders List ({CATEGORY_NAMES[cat]} - {LANGUAGES[lang]}):</b>\n\nফোল্ডার এডিট বা সাব-ফোল্ডার যুক্ত করতে ক্লিক করুন:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@router.callback_query(F.data.startswith("admfold_manage:"))
async def cb_adm_folder_manage(call: CallbackQuery):
    folder_id = int(call.data.split(":", 1)[1])
    folder = await fetchone("SELECT * FROM admin_folders WHERE id=?", (folder_id,))
    if not folder:
        await call.answer("Folder not found.", show_alert=True)
        return
    
    subfolders = await fetchall("SELECT * FROM admin_subfolders WHERE folder_id=?", (folder_id,))
    
    kb = [
        [InlineKeyboardButton(text="✏️ ফোল্ডারের নাম পরিবর্তন করুন (Edit)", callback_data=f"adm_editfolder_start:{folder_id}")],
        [InlineKeyboardButton(text="➕ সাব-ফোল্ডার যুক্ত করুন (Add Sub-folder)", callback_data=f"adm_addsub_start:{folder_id}")],
        [InlineKeyboardButton(text="🗑 ফোল্ডার ডিলিট করুন (Delete Folder)", callback_data=f"admdelefold_confirm:{folder_id}")],
    ]
    
    sub_txt = "\n📂 <b>সাব-ফোল্ডাসমূহ:</b>\n"
    if subfolders:
        for sf in subfolders:
            sub_txt += f" - {sf['name']}\n"
            kb.append([InlineKeyboardButton(text=f"❌ রিমুভ সাব-ফোল্ডার: {sf['name']}", callback_data=f"adm_removesub:{sf['id']}:{folder_id}")])
    else:
        sub_txt += "কোনো সাব-ফোল্ডার নেই।\n"
        
    kb.append([InlineKeyboardButton(text="🔙 ব্যাক", callback_data=f"admfoldlang:{folder['category']}:{folder['language']}")])
    
    await safe_edit(call, f"📁 <b>ফোল্ডার ম্যানেজমেন্ট:</b> <i>{esc(folder['name'])}</i>\n{sub_txt}", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

# ফোল্ডার এডিট (নাম পরিবর্তন)
@router.callback_query(F.data.startswith("adm_editfolder_start:"))
async def cb_edit_folder_start(call: CallbackQuery, state: FSMContext):
    folder_id = int(call.data.split(":", 1)[1])
    await state.update_data(edit_folder_id=folder_id)
    await state.set_state(AdminStates.waiting_edit_folder)
    await safe_edit(call, "✏️ ফোল্ডারের নতুন নামটি লিখে পাঠান:")

@router.message(AdminStates.waiting_edit_folder)
async def save_edited_folder_name(message: Message, state: FSMContext):
    if not await is_admin_user(message.from_user.id):
        return
    new_name = (message.text or "").strip()
    data = await state.get_data()
    fid = data.get("edit_folder_id")
    
    await execute("UPDATE admin_folders SET name=? WHERE id=?", (new_name, fid))
    await state.clear()
    await message.answer(f"✅ ফোল্ডারের নাম পরিবর্তন করে <b>'{new_name}'</b> করা হয়েছে!", reply_markup=back_kb("admin_panel"))

# সাব-ফোল্ডার অ্যাড করা
@router.callback_query(F.data.startswith("adm_addsub_start:"))
async def cb_addsub_start(call: CallbackQuery, state: FSMContext):
    folder_id = int(call.data.split(":", 1)[1])
    await state.update_data(parent_folder_id=folder_id)
    await state.set_state(AdminStates.waiting_add_sub_dynamic)
    await safe_edit(call, "✏️ নতুন সাব-ফোল্ডারের নাম (যেমন: Season Part 1) লিখে পাঠান:")

@router.message(AdminStates.waiting_add_sub_dynamic)
async def save_sub_dynamic(message: Message, state: FSMContext):
    if not await is_admin_user(message.from_user.id):
        return
    sf_name = (message.text or "").strip()
    data = await state.get_data()
    fid = data.get("parent_folder_id")
    
    await execute("INSERT INTO admin_subfolders (folder_id, name) VALUES (?, ?)", (fid, sf_name))
    await state.clear()
    await message.answer(f"✅ সাব-ফোল্ডার <b>'{sf_name}'</b> সফলভাবে যুক্ত করা হয়েছে!", reply_markup=back_kb("admin_panel"))

# সাব-ফোল্ডার রিমুভ করা
@router.callback_query(F.data.startswith("adm_removesub:"))
async def cb_remove_subfolder(call: CallbackQuery):
    parts = call.data.split(":")
    sf_id, folder_id = int(parts[1]), int(parts[2])
    await execute("DELETE FROM admin_subfolders WHERE id=?", (sf_id,))
    await call.answer("✅ সাব-ফোল্ডার রিমুভ করা হয়েছে!", show_alert=True)
    # রিফ্রেশ ম্যানেজ মেনু
    call.data = f"admfold_manage:{folder_id}"
    await cb_adm_folder_manage(call)

# ফোল্ডার ডিলিট কনফার্মেশন (Yes / No)
@router.callback_query(F.data.startswith("admdelefold_confirm:"))
async def cb_adm_delete_folder_confirm(call: CallbackQuery):
    folder_id = int(call.data.split(":", 1)[1])
    folder = await fetchone("SELECT * FROM admin_folders WHERE id=?", (folder_id,))
    if not folder:
        await call.answer("Folder not found.", show_alert=True)
        return
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ হ্যাঁ (Yes, Delete)", callback_data=f"admdelefold_yes:{folder_id}")],
        [InlineKeyboardButton(text="❌ না (No, Cancel)", callback_data="admin_manage_folders")]
    ])
    await safe_edit(call, f"⚠️ আপনি কি ফোল্ডার <b>'{folder['name']}'</b> এবং এর ভেতরের সকল সাব-ফোল্ডার ডিলিট করতে চান?", reply_markup=kb)

@router.callback_query(F.data.startswith("admdelefold_yes:"))
async def cb_adm_delete_folder_yes(call: CallbackQuery):
    folder_id = int(call.data.split(":", 1)[1])
    await execute("UPDATE posts SET folder_id=0 WHERE folder_id=?", (folder_id,))
    await execute("DELETE FROM admin_subfolders WHERE folder_id=?", (folder_id,))
    await execute("DELETE FROM admin_folders WHERE id=?", (folder_id,))
    await call.answer("✅ ফোল্ডার সফলভাবে ডিলিট করা হয়েছে!", show_alert=True)
    await cb_manage_folders(call)

# -------------------------------------------------------------------------
# DATABASE BACKUP & RESTORE HANDLERS
# -------------------------------------------------------------------------
@router.message(Command("backup"))
async def cmd_backup(message: Message):
    if not await is_admin_user(message.from_user.id):
        return
    try:
        async with aiosqlite.connect(DB_PATH) as d:
            await d.execute("PRAGMA wal_checkpoint(FULL)")
            await d.commit()
        await bot.send_document(ADMIN_CHAT_ID, FSInputFile(DB_PATH), caption=f"📥 Manual Database Backup\n🕒 {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())}")
    except Exception as e:
        await message.answer(f"❌ Backup failed: {e}")

@router.callback_query(F.data == "admin_restore")
async def cb_restore(call: CallbackQuery, state: FSMContext):
    if not await is_admin_user(call.from_user.id):
        return
    await state.set_state(AdminStates.waiting_restore_db)
    await safe_edit(call, "📥 <b>RESTORE DATABASE BACKUP</b>\n\n⚠️ আপলোড করলে বর্তমান ডাটাবেজ আপডেট হবে।\n\nআপনার ব্যাকআপ করা <code>.db</code> ফাইলটি এখন সেন্ড করুন:", reply_markup=back_kb("admin_panel"))

@router.message(AdminStates.waiting_restore_db, F.document)
async def restore_handler(message: Message, state: FSMContext):
    if not await is_admin_user(message.from_user.id):
        return
    doc = message.document
    if not doc.file_name or not doc.file_name.lower().endswith(".db"):
        await message.answer("একটি সঠিক .db ব্যাকআপ ফাইল দিন।")
        return
    await message.answer("⏳ Processing & Restoring Database...")
    tmp = f"restore_{int(time.time())}.db"
    try:
        f = await bot.get_file(doc.file_id)
        await bot.download_file(f.file_path, tmp)
        async with aiosqlite.connect(tmp) as t:
            await t.execute("SELECT 1 FROM sqlite_master LIMIT 1")
        for s in ("-wal", "-shm"):
            p = DB_PATH + s
            if os.path.exists(p):
                try: os.remove(p)
                except: pass
        shutil.copy(tmp, DB_PATH)
        os.remove(tmp)
        await init_db()
        await state.clear()
        await message.answer("✅ <b>DATABASE RESTORED SUCCESSFULLY!</b>\n\nসকল ডেটা সফলভাবে রিস্টোর হয়েছে।", reply_markup=back_kb("admin_panel"))
    except Exception as e:
        if os.path.exists(tmp):
            try: os.remove(tmp)
            except: pass
        await message.answer(f"❌ Restore Failed: {e}")

# -------------------------------------------------------------------------
# ADMIN MANAGING & BROADCAST
# -------------------------------------------------------------------------
@router.callback_query(F.data == "admin_manage_admins")
async def cb_manage_admins(call: CallbackQuery):
    if not await is_admin_user(call.from_user.id):
        return
    admins = await fetchall("SELECT * FROM admins")
    text = "👑 <b>CURRENT BOT ADMINS:</b>\n\n"
    for a in admins:
        text += f"🔹 Admin Chat ID: <code>{a['user_id']}</code>\n"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Add New Admin", callback_data="adm_add_admin")],
        [InlineKeyboardButton(text="🔙 BACK", callback_data="admin_panel")]
    ])
    await safe_edit(call, text, reply_markup=kb)

@router.callback_query(F.data == "adm_add_admin")
async def cb_add_admin_prompt(call: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_admin_add)
    await safe_edit(call, "👑 নতুন অ্যাডমিনের <b>Chat ID</b> লিখে পাঠান:", reply_markup=back_kb("admin_panel"))

@router.message(AdminStates.waiting_admin_add)
async def recv_new_admin_id(message: Message, state: FSMContext):
    if not await is_admin_user(message.from_user.id):
        return
    try: new_aid = int((message.text or "").strip())
    except ValueError:
        await message.answer("সঠিক চ্যাট আইডি দিন।")
        return
    await execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (new_aid,))
    await state.clear()
    await message.answer(f"✅ <code>{new_aid}</code> আইডি সফলভাবে অ্যাডমিন হিসেবে যুক্ত করা হয়েছে!", reply_markup=back_kb("admin_panel"))

@router.callback_query(F.data == "admin_broadcast")
async def cb_broadcast(call: CallbackQuery, state: FSMContext):
    if not await is_admin_user(call.from_user.id):
        return
    await state.set_state(AdminStates.waiting_broadcast)
    await safe_edit(call, "📢 <b>BROADCAST MESSAGE</b>\n\nইউজারদের পাঠানোর জন্য মেসেজটি এখানে লিখুন বা ফরওয়ার্ড করুন:", reply_markup=back_kb("admin_panel"))

@router.message(AdminStates.waiting_broadcast)
async def recv_broadcast(message: Message, state: FSMContext):
    if not await is_admin_user(message.from_user.id):
        return
    users = await fetchall("SELECT user_id FROM users WHERE banned=0")
    await state.clear()
    await message.answer(f"📤 Broadcasting to {len(users)} users...")
    ok = fail = 0
    for u in users:
        try:
            await message.copy_to(u["user_id"])
            ok += 1
            await asyncio.sleep(0.04)
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
            try:
                await message.copy_to(u["user_id"])
                ok += 1
            except: fail += 1
        except: fail += 1
    await message.answer(f"✅ Broadcast Complete!\nSuccess: {ok} | Failed: {fail}", reply_markup=back_kb("admin_panel"))

# -------------------------------------------------------------------------
# PUBLISHING CONTENT BY ADMIN
# -------------------------------------------------------------------------
@router.callback_query(F.data == "admin_publish")
async def cb_publish(call: CallbackQuery, state: FSMContext):
    if not await is_admin_user(call.from_user.id):
        return
    await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 MOVIE", callback_data="pubcat:movie")],
        [InlineKeyboardButton(text="🔥 VIRAL VIDEO", callback_data="pubcat:viral")],
        [InlineKeyboardButton(text="🎌 ANIME", callback_data="pubcat:anime")],
        [InlineKeyboardButton(text="❌ CANCEL", callback_data="admin_panel")],
    ])
    await safe_edit(call, "📤 <b>PUBLISH CONTENT</b>\n\nSelect category:", reply_markup=kb)

@router.callback_query(F.data.startswith("pubcat:"))
async def cb_pubcat(call: CallbackQuery, state: FSMContext):
    cat = call.data.split(":", 1)[1]
    await state.set_state(AdminStates.uploading_files)
    await state.update_data(category=cat, files=[], thumb=None, folder_id=0, subfolder_id=0, language="")
    await safe_edit(call, f"Category: <b>{CATEGORY_NAMES[cat]}</b>\n\nUpload files (1–{MAX_ADMIN_FILES}). Then tap DONE.", reply_markup=done_upload_kb("pub_files_done"))

@router.message(AdminStates.uploading_files)
async def admin_recv_file(message: Message, state: FSMContext):
    if not await is_admin_user(message.from_user.id):
        return
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
        await message.answer("⚠️ Unsupported.")
        return
    files.append({"type": t, "id": i, "name": n})
    await state.update_data(files=files)
    await message.answer(f"✅ File {len(files)} received.")

@router.callback_query(F.data == "pub_files_done")
async def cb_pub_files_done(call: CallbackQuery, state: FSMContext):
    files = (await state.get_data()).get("files", [])
    if not files:
        await call.answer("Upload at least one file.", show_alert=True)
        return
    await state.set_state(AdminStates.waiting_title)
    await safe_edit(call, "✏️ Send the <b>title</b>:")

@router.message(AdminStates.waiting_title)
async def admin_recv_title(message: Message, state: FSMContext):
    if not await is_admin_user(message.from_user.id):
        return
    title = (message.text or "").strip()
    if not title:
        await message.answer("Send a valid title.")
        return
    await state.update_data(title=title)
    await state.set_state(AdminStates.waiting_thumb)
    await message.answer("🖼 Send a <b>thumbnail</b> photo, or type <code>skip</code>:")

@router.message(AdminStates.waiting_thumb)
async def admin_recv_thumb(message: Message, state: FSMContext):
    if not await is_admin_user(message.from_user.id):
        return
    thumb = None
    if message.photo: thumb = message.photo[-1].file_id
    elif (message.text or "").strip().lower() == "skip": thumb = None
    else:
        await message.answer("Send a photo or type <code>skip</code>.")
        return
    await state.update_data(thumb=thumb)
    
    data = await state.get_data()
    cat = data.get("category")

    if cat in ("movie", "anime", "viral"):
        kb = []
        for lang_code, lang_name in LANGUAGES.items():
            kb.append([InlineKeyboardButton(text=lang_name, callback_data=f"setpublang:{lang_code}")])
        await message.answer("🌐 Select Language:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    else:
        await show_confirm_preview(message, state)

@router.callback_query(F.data.startswith("setpublang:"))
async def cb_set_pub_lang(call: CallbackQuery, state: FSMContext):
    lang_code = call.data.split(":", 1)[1]
    await state.update_data(language=lang_code)
    data = await state.get_data()
    cat = data.get("category")
    
    folders = await fetchall("SELECT * FROM admin_folders WHERE admin_id=? AND category=? AND language=?", (ADMIN_CHAT_ID, cat, lang_code))
    buttons = []
    for f in folders:
        buttons.append([InlineKeyboardButton(text=f"📁 {f['name']}", callback_data=f"admin_select_folder:{f['id']}")])
    buttons.append([InlineKeyboardButton(text="➕ Create Folder", callback_data="admin_create_folder")])
    buttons.append([InlineKeyboardButton(text="➡️ Direct Upload", callback_data="admin_select_folder:0")])
    await safe_edit(call, "ফোল্ডার সিলেক্ট করুন:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@router.callback_query(F.data == "admin_create_folder")
async def process_admin_create_folder(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_folder_name)
    await callback.message.edit_text("✏️ ফোল্ডারের নাম (যেমন: Season 1) লিখে পাঠান:")
    await callback.answer()

@router.message(AdminStates.waiting_folder_name)
async def save_admin_folder_name(message: Message, state: FSMContext):
    if not await is_admin_user(message.from_user.id):
        return
    folder_name = (message.text or "").strip()
    data = await state.get_data()
    folder_id = await execute("INSERT INTO admin_folders (admin_id, category, language, name) VALUES (?, ?, ?, ?)", (ADMIN_CHAT_ID, data.get("category"), data.get("language"), folder_name))
    await state.update_data(folder_id=folder_id)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ সাব-ফোল্ডার তৈরি করুন", callback_data="admin_create_subfolder")],
        [InlineKeyboardButton(text="✅ এই ফোল্ডারেই আপলোড সম্পন্ন করুন", callback_data="admin_proceed_preview")]
    ])
    await message.answer(f"✅ ফোল্ডার <b>'{folder_name}'</b> যুক্ত হয়েছে।", reply_markup=kb)

@router.callback_query(F.data == "admin_create_subfolder")
async def cb_create_subfolder(call: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_subfolder_name)
    await safe_edit(call, "✏️ সাব-ফোল্ডারের নাম লিখে পাঠান:")

@router.message(AdminStates.waiting_subfolder_name)
async def save_subfolder_name(message: Message, state: FSMContext):
    if not await is_admin_user(message.from_user.id):
        return
    sf_name = (message.text or "").strip()
    data = await state.get_data()
    sf_id = await execute("INSERT INTO admin_subfolders (folder_id, name) VALUES (?, ?)", (data.get("folder_id"), sf_name))
    await state.update_data(subfolder_id=sf_id)
    await message.answer(f"✅ সাব-ফোল্ডার <b>'{sf_name}'</b> যুক্ত হয়েছে!")
    await show_confirm_preview(message, state)

@router.callback_query(F.data == "admin_proceed_preview")
@router.callback_query(F.data.startswith("admin_select_folder:"))
async def process_admin_folder_selection(callback: CallbackQuery, state: FSMContext):
    if callback.data.startswith("admin_select_folder:"):
        folder_id = int(callback.data.split(":")[1])
        await state.update_data(folder_id=folder_id)
    await callback.answer()
    await show_confirm_preview(callback.message, state, is_callback=True)

async def show_confirm_preview(event_msg: Message, state: FSMContext, is_callback: bool = False):
    await state.set_state(AdminStates.waiting_confirm)
    data = await state.get_data()
    thumb = data.get("thumb")
    
    folder_info = "None"
    if data.get("folder_id"):
        f_row = await fetchone("SELECT name FROM admin_folders WHERE id=?", (data["folder_id"],))
        if f_row: folder_info = f_row["name"]

    preview = f"📋 <b>CONFIRM PUBLISH</b>\n\n📂 Category: {CATEGORY_NAMES[data['category']]}\n📁 Folder: {folder_info}\n📄 Files: {len(data['files'])}\n📝 Title: <b>{esc(data['title'])}</b>\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🚀 PUBLISH NOW", callback_data="pub_confirm")], [InlineKeyboardButton(text="❌ CANCEL", callback_data="admin_panel")]])
    
    if thumb:
        try:
            await event_msg.answer_photo(thumb, caption=preview, reply_markup=kb)
            return
        except: pass
    if is_callback:
        await safe_edit(event_msg, preview, reply_markup=kb)
    else:
        await event_msg.answer(preview, reply_markup=kb)

@router.callback_query(F.data == "pub_confirm")
async def cb_pub_confirm(call: CallbackQuery, state: FSMContext):
    if not await is_admin_user(call.from_user.id):
        return
    data = await state.get_data()
    files = data.get("files", [])
    title = data.get("title", "Untitled")
    category = data.get("category", "movie")
    language = data.get("language", "")
    thumb = data.get("thumb")
    folder_id = data.get("folder_id", 0)
    subfolder_id = data.get("subfolder_id", 0)
    
    if not files: return
    code = await unique_code()
    await execute("INSERT INTO posts (code, title, category, language, owner_id, is_admin, thumbnail_id, created_at, published, folder_id, subfolder_id) VALUES (?, ?, ?, ?, ?, 1, ?, ?, 1, ?, ?)", (code, title, category, language, ADMIN_CHAT_ID, thumb, int(time.time()), folder_id, subfolder_id))
    for i, f in enumerate(files):
        await execute("INSERT INTO post_files (post_code, file_id, file_type, file_name, order_idx) VALUES (?, ?, ?, ?, ?)", (code, f["id"], f["type"], f["name"], i))
    
    username = await get_bot_username()
    link = f"https://t.me/{username}?start=GET_{code}"
    share = f"🎬 <b>{esc(title)}</b>\n\n📂 {CATEGORY_NAMES[category]}\n🔗 Link: {link}"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📥 GET FILE", url=link)]])
    
    target_channel = CATEGORY_CHANNELS[category]
    try:
        if thumb: await bot.send_photo(target_channel, thumb, caption=share, reply_markup=kb)
        else: await bot.send_message(target_channel, share, reply_markup=kb)
    except: pass
            
    await state.clear()
    await safe_edit(call, f"✅ <b>PUBLISHED!</b>\n\n🔗 Link: <code>{link}</code>", reply_markup=back_kb("admin_panel"))

# -------------------------------------------------------------------------
# ADMIN BAN / UNBAN / USERS / SETTINGS / STATS
# -------------------------------------------------------------------------
@router.callback_query(F.data == "admin_ban")
async def cb_ban(call: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_ban_id)
    await safe_edit(call, "🚫 Send <b>User ID</b> to ban:", reply_markup=back_kb("admin_panel"))

@router.message(AdminStates.waiting_ban_id)
async def recv_ban(message: Message, state: FSMContext):
    try: uid = int((message.text or "").strip())
    except ValueError:
        await message.answer("Send a valid ID.")
        return
    await execute("UPDATE users SET banned=1 WHERE user_id=?", (uid,))
    await state.clear()
    await message.answer(f"✅ User <code>{uid}</code> banned.", reply_markup=back_kb("admin_panel"))

@router.callback_query(F.data == "admin_unban")
async def cb_unban(call: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_unban_id)
    await safe_edit(call, "✅ Send <b>User ID</b> to unban:", reply_markup=back_kb("admin_panel"))

@router.message(AdminStates.waiting_unban_id)
async def recv_unban(message: Message, state: FSMContext):
    try: uid = int((message.text or "").strip())
    except ValueError:
        await message.answer("Send a valid ID.")
        return
    await execute("UPDATE users SET banned=0 WHERE user_id=?", (uid,))
    await state.clear()
    await message.answer(f"✅ User <code>{uid}</code> unbanned.", reply_markup=back_kb("admin_panel"))

@router.callback_query(F.data == "admin_withdrawals")
async def cb_withdrawals(call: CallbackQuery):
    rows = await fetchall("SELECT * FROM withdrawals WHERE status='pending' ORDER BY id DESC LIMIT 20")
    if not rows:
        await safe_edit(call, "💰 <b>WITHDRAWALS</b>\n\nNo pending withdrawals.", reply_markup=back_kb("admin_panel"))
        return
    text = "💰 <b>PENDING WITHDRAWALS</b>\n\n"
    for r in rows[:10]:
        text += f"#{r['id']} | <code>{r['user_id']}</code> | {fmt_money(r['amount'])} | {esc(r['method'])}\n"
    await safe_edit(call, text, reply_markup=back_kb("admin_panel"))

@router.callback_query(F.data.startswith("wdapprove:"))
async def cb_wd_approve(call: CallbackQuery):
    wid = int(call.data.split(":", 1)[1])
    wd = await fetchone("SELECT * FROM withdrawals WHERE id=?", (wid,))
    if not wd or wd["status"] != "pending":
        await call.answer("Already processed.", show_alert=True)
        return
    await execute("UPDATE withdrawals SET status='approved' WHERE id=?", (wid,))
    try: await bot.send_message(wd["user_id"], f"✅ Withdrawal #{wid} approved!")
    except: pass
    await safe_edit(call, f"✅ Approved #{wid}", reply_markup=back_kb("admin_panel"))

@router.callback_query(F.data.startswith("wdreject:"))
async def cb_wd_reject(call: CallbackQuery):
    wid = int(call.data.split(":", 1)[1])
    wd = await fetchone("SELECT * FROM withdrawals WHERE id=?", (wid,))
    if not wd or wd["status"] != "pending":
        await call.answer("Already processed.", show_alert=True)
        return
    await execute("UPDATE withdrawals SET status='rejected' WHERE id=?", (wid,))
    await add_balance(wd["user_id"], wd["amount"])
    try: await bot.send_message(wd["user_id"], f"❌ Withdrawal #{wid} rejected.")
    except: pass
    await safe_edit(call, f"❌ Rejected #{wid}", reply_markup=back_kb("admin_panel"))

@router.callback_query(F.data == "admin_users")
async def cb_all_users(call: CallbackQuery):
    rows = await fetchall("SELECT * FROM users ORDER BY joined_at DESC LIMIT 30")
    text = "👥 <b>ALL USERS (30)</b>\n\n"
    for u in rows:
        ban = "🚫" if u.get("banned") else "✅"
        text += f"{ban} <code>{u['user_id']}</code> | {esc(truncate(u.get('first_name') or 'User', 20))} | {fmt_money(u.get('balance', 0))}\n"
    await safe_edit(call, text, reply_markup=back_kb("admin_panel"))

@router.callback_query(F.data == "admin_stats")
async def cb_stats(call: CallbackQuery):
    u = await fetchone("SELECT COUNT(*) as c FROM users")
    p = await fetchone("SELECT COUNT(*) as c FROM posts WHERE published=1 AND deleted=0")
    v = await fetchone("SELECT COUNT(*) as c FROM views")
    b = await fetchone("SELECT COALESCE(SUM(balance),0) as s FROM users")
    text = f"📊 <b>BOT STATISTICS</b>\n\n👥 Users: <b>{u['c']}</b>\n📄 Posts: <b>{p['c']}</b>\n👁 Views: <b>{v['c']}</b>\n💰 Total Balances: <b>{fmt_money(b['s'])}</b>"
    await safe_edit(call, text, reply_markup=back_kb("admin_panel"))

@router.callback_query(F.data == "admin_settings")
async def cb_settings(call: CallbackQuery):
    min_w = await get_setting("min_withdraw", str(DEFAULT_MIN_WITHDRAW))
    vr = await get_setting("view_reward", str(VIEW_REWARD))
    rb = await get_setting("referral_bonus", str(REFERRAL_BONUS))
    daily = await get_setting("daily_bonus", str(DAILY_BONUS))
    text = f"⚙️ <b>SETTINGS</b>\n\n💵 Min Withdraw: <b>${min_w}</b>\n👁 View Reward: <b>${vr}</b>\n🔗 Referral: <b>${rb}</b>\n🎁 Daily: <b>${daily}</b>"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💵 MIN WITHDRAW", callback_data="set:min_withdraw")],
        [InlineKeyboardButton(text="👁 VIEW REWARD", callback_data="set:view_reward")],
        [InlineKeyboardButton(text="🔗 REFERRAL BONUS", callback_data="set:referral_bonus")],
        [InlineKeyboardButton(text="🎁 DAILY BONUS", callback_data="set:daily_bonus")],
        [InlineKeyboardButton(text="🔙 BACK", callback_data="admin_panel")],
    ])
    await safe_edit(call, text, reply_markup=kb)

@router.callback_query(F.data.startswith("set:"))
async def cb_set_value(call: CallbackQuery, state: FSMContext):
    key = call.data.split(":", 1)[1]
    await state.update_data(setting_key=key)
    await state.set_state(AdminStates.waiting_setting)
    await safe_edit(call, f"Send new numeric value for <b>{key}</b>:", reply_markup=back_kb("admin_settings"))

@router.message(AdminStates.waiting_setting)
async def recv_setting(message: Message, state: FSMContext):
    try: val = float((message.text or "").strip())
    except ValueError:
        await message.answer("Send a valid number.")
        return
    key = (await state.get_data()).get("setting_key")
    await set_setting(key, str(val))
    await state.clear()
    await message.answer(f"✅ <b>{key}</b> = <b>{val}</b>", reply_markup=back_kb("admin_settings"))

# =========================================================================
# 60-SECOND AUTOMATIC BACKUP WORKER
# =========================================================================
async def backup_worker():
    await asyncio.sleep(5)
    logger.info(f"Automatic Backup worker loop active ({BACKUP_INTERVAL_SECONDS}s)")
    while True:
        try:
            await asyncio.sleep(BACKUP_INTERVAL_SECONDS)
            if not os.path.exists(DB_PATH):
                continue
            
            try:
                async with aiosqlite.connect(DB_PATH) as d:
                    await d.execute("PRAGMA wal_checkpoint(FULL)")
                    await d.commit()
            except Exception as e:
                logger.error(f"checkpoint: {e}")

            last = backup_state.get("last_id")
            if last:
                try: await bot.delete_message(ADMIN_CHAT_ID, last)
                except: pass
            
            try:
                sent = await bot.send_document(
                    ADMIN_CHAT_ID,
                    FSInputFile(DB_PATH),
                    caption=f"🔄 <b>AUTO BACKUP (60s)</b>\n🕒 {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime())} UTC"
                )
                backup_state["last_id"] = sent.message_id
            except Exception as e:
                logger.error(f"backup send failed: {e}")

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"backup loop error: {e}")
            await asyncio.sleep(5)

# =========================================================================
# WEB SERVER FOR 24/7 RUNNING (RENDER PORT BINDING)
# =========================================================================
async def handle_ping(request):
    return web.Response(text="MovieVerse Bot is running 24/7!")

async def start_web_server():
    try:
        app = web.Application()
        app.router.add_get("/", handle_ping)
        runner = web.AppRunner(app)
        await runner.setup()
        port = int(os.environ.get("PORT", 10000))
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
        logger.info(f"Web server active on port {port}")
    except Exception as e:
        logger.error(f"Web server failed: {e}")

@router.message()
async def fallback(message: Message):
    is_adm = await is_admin_user(message.from_user.id)
    await message.answer("ℹ️ Use /start to open main menu.", reply_markup=main_menu_kb(is_adm))

# =========================================================================
# MAIN EXECUTION
# =========================================================================
async def main():
    try:
        await init_db()

        dp.message.middleware(AntiSpamMiddleware())
        dp.callback_query.middleware(AntiSpamMiddleware())
        dp.message.middleware(ForceSubMiddleware())
        dp.callback_query.middleware(ForceSubMiddleware())
        dp.include_router(router)

        await register_commands()

        global _backup_task
        _backup_task = asyncio.create_task(backup_worker())
        asyncio.create_task(start_web_server())

        me = await bot.get_me()
        logger.info(f"Logged in as @{me.username}")
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    except Exception:
        with open("crash.log", "w", encoding="utf-8") as f:
            traceback.print_exc(file=f)
        logger.exception("Fatal Error")
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
