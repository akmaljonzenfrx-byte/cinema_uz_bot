import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from config import ADMIN_IDS, DB_PATH
from database import Database
from keyboards import (
    admin_main_keyboard,
    admin_channels_keyboard,
    admin_broadcast_confirm_keyboard,
    cancel_keyboard,
    main_menu_keyboard
)

logger = logging.getLogger(__name__)
db = Database()

# Conversation states
(
    ADD_MOVIE_VIDEO,
    ADD_MOVIE_TITLE,
    ADD_MOVIE_YEAR,
    ADD_MOVIE_GENRE,
    ADD_MOVIE_DESC,
    ADD_MOVIE_CODE,
) = range(6)

ADD_CHANNEL_DATA = 6
BROADCAST_RECEIVE, BROADCAST_CONFIRM = 7, 8
USER_MANAGE_INPUT = 9


def is_admin(user_id: int) -> bool:
    """Foydalanuvchining admin ekanligini tekshirish."""
    return user_id in ADMIN_IDS


async def admin_panel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin boshqaruv panelini chiqarish."""
    user = update.effective_user
    if not user or not is_admin(user.id):
        if update.message:
            await update.message.reply_text("❌ Sizda admin huquqlari mavjud emas.")
        return

    text = (
        "⚙️ **Admin Boshqaruv Paneli**\n\n"
        "Quyidagi bo'limlardan birini tanlang:"
    )

    if update.message:
        await update.message.reply_text(
            text,
            reply_markup=admin_main_keyboard(),
            parse_mode="Markdown"
        )
    elif update.callback_query:
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(
            text,
            reply_markup=admin_main_keyboard(),
            parse_mode="Markdown"
        )


async def admin_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin paneldagi callback tugmalarni qayta ishlash."""
    query = update.callback_query
    if not query:
        return

    user = query.from_user
    if not user or not is_admin(user.id):
        await query.answer("❌ Kirish taqiqlangan!", show_alert=True)
        return

    await query.answer()
    data = query.data

    if data == "adm_back_main":
        await admin_panel_handler(update, context)

    elif data == "adm_stats":
        stats = db.get_statistics()
        text = (
            "📊 **Bot Statistikasi**\n\n"
            f"👤 Jami foydalanuvchilar: **{stats.get('total_users', 0)}**\n"
            f"🆕 Bugun qo'shilganlar: **{stats.get('today_users', 0)}**\n"
            f"💎 Premium a'zolar: **{stats.get('premium_users', 0)}**\n"
            f"🚫 Bloklanganlar: **{stats.get('blocked_users', 0)}**\n\n"
            f"🎬 Jami kinolar: **{stats.get('total_movies', 0)}**\n"
            f"👁 Jami ko'rishlar: **{stats.get('total_views', 0)}**\n"
            f"📢 Majburiy kanallar: **{stats.get('total_channels', 0)}**"
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Orqaga", callback_data="adm_back_main")]
        ])
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")

    elif data == "adm_channels":
        channels = db.get_mandatory_channels()
        is_forced = db.get_setting("forced_sub_enabled", "1") == "1"
        await query.edit_message_text(
            "📢 **Majburiy Obuna Kanallari**\n\n"
            "Kanal qo'shishingiz yoki mavjudlarini o'chirishingiz mumkin:",
            reply_markup=admin_channels_keyboard(channels, is_forced),
            parse_mode="Markdown"
        )

    elif data == "adm_toggle_forced_sub":
        current = db.get_setting("forced_sub_enabled", "1")
        new_val = "0" if current == "1" else "1"
        db.set_setting("forced_sub_enabled", new_val)
        
        channels = db.get_mandatory_channels()
        is_forced = (new_val == "1")
        await query.edit_message_text(
            "📢 **Majburiy Obuna Kanallari**\n\n"
            "Kanal qo'shishingiz yoki mavjudlarini o'chirishingiz mumkin:",
            reply_markup=admin_channels_keyboard(channels, is_forced),
            parse_mode="Markdown"
        )

    elif data.startswith("adm_del_chan_"):
        chan_id = data.replace("adm_del_chan_", "")
        db.delete_channel(chan_id)
        channels = db.get_mandatory_channels()
        is_forced = db.get_setting("forced_sub_enabled", "1") == "1"
        await query.edit_message_text(
            "✅ Kanal majburiy obunadan o'chirildi.\n\n📢 **Majburiy Obuna Kanallari**:",
            reply_markup=admin_channels_keyboard(channels, is_forced),
            parse_mode="Markdown"
        )

    elif data.startswith("adm_del_mov_"):
        movie_id_str = data.replace("adm_del_mov_", "")
        try:
            m_id = int(movie_id_str)
            db.delete_movie(m_id)
            await query.edit_message_text("✅ Kino muvaffaqiyatli o'chirildi.")
        except Exception as e:
            logger.error(f"Kino o'chirishda xatolik: {e}")
            await query.edit_message_text("❌ Kinoni o'chirishda xatolik yuz berdi.")


# --- KINO QO'SHISH CONVERSATION ---

async def add_movie_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Kino qo'shish jarayonini boshlash."""
    user = update.effective_user
    if not user or not is_admin(user.id):
        return ConversationHandler.END

    if update.callback_query:
        await update.callback_query.answer()

    context.user_data.clear()

    msg = (
        "🎬 **Yangi kino qo'shish**\n\n"
        "Iltimos, kinoning **video faylini** yuboring:"
    )

    if update.callback_query:
        await update.callback_query.message.reply_text(msg, reply_markup=cancel_keyboard(), parse_mode="Markdown")
    elif update.message:
        await update.message.reply_text(msg, reply_markup=cancel_keyboard(), parse_mode="Markdown")

    return ADD_MOVIE_VIDEO


async def add_movie_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Kino videosini qabul qilish."""
    if not update.message:
        return ADD_MOVIE_VIDEO

    video = update.message.video or update.message.document
    if not video:
        await update.message.reply_text("❌ Iltimos, video fayl yuboring!")
        return ADD_MOVIE_VIDEO

    context.user_data['file_id'] = video.file_id
    await update.message.reply_text("✏️ **Kino nomini kiriting:**", parse_mode="Markdown")
    return ADD_MOVIE_TITLE


async def add_movie_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Kino nomini qabul qilish."""
    if not update.message or not update.message.text:
        await update.message.reply_text("❌ Iltimos, kino nomini matn shaklida kiriting!")
        return ADD_MOVIE_TITLE

    context.user_data['title'] = update.message.text.strip()
    await update.message.reply_text("📅 **Chiqarilgan yilini kiriting (masalan: 2023):**", parse_mode="Markdown")
    return ADD_MOVIE_YEAR


async def add_movie_year(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Kino yilini qabul qilish."""
    if not update.message or not update.message.text:
        await update.message.reply_text("❌ Iltimos, yilni kiriting!")
        return ADD_MOVIE_YEAR

    text = update.message.text.strip()
    if not text.isdigit() or len(text) != 4:
        await update.message.reply_text("❌ Iltimos, 4 xonali to'g'ri yil kiriting (masalan: 2023):")
        return ADD_MOVIE_YEAR

    context.user_data['year'] = int(text)
    await update.message.reply_text("🎭 **Kino janrini kiriting (masalan: Fantastika, Boevik, Drama):**", parse_mode="Markdown")
    return ADD_MOVIE_GENRE


async def add_movie_genre(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Kino janrini qabul qilish."""
    if not update.message or not update.message.text:
        await update.message.reply_text("❌ Iltimos, janrni kiriting!")
        return ADD_MOVIE_GENRE

    context.user_data['genre'] = update.message.text.strip()
    await update.message.reply_text("📝 **Kino tavsifini (syujetini) kiriting:**", parse_mode="Markdown")
    return ADD_MOVIE_DESC


async def add_movie_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Kino tavsifini qabul qilish."""
    if not update.message or not update.message.text:
        await update.message.reply_text("❌ Iltimos, tavsifni matn shaklida kiriting!")
        return ADD_MOVIE_DESC

    context.user_data['description'] = update.message.text.strip()
    await update.message.reply_text("🔢 **Kino uchun unikal kod kiriting (masalan: 101):**", parse_mode="Markdown")
    return ADD_MOVIE_CODE


async def add_movie_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Kino kodini qabul qilish va bazaga saqlash."""
    if not update.message or not update.message.text:
        await update.message.reply_text("❌ Iltimos, kodni kiriting!")
        return ADD_MOVIE_CODE

    code = update.message.text.strip()
    existing = db.get_movie_by_code(code)
    if existing:
        await update.message.reply_text(f"❌ Bu kod ({code}) allaqachon mavjud! Boshqa kod kiriting:")
        return ADD_MOVIE_CODE

    title = context.user_data.get('title', '')
    year = context.user_data.get('year', 2024)
    genre = context.user_data.get('genre', 'Noma\'lum')
    description = context.user_data.get('description', '')
    file_id = context.user_data.get('file_id', '')

    movie_id = db.add_movie(
        title=title,
        code=code,
        year=year,
        genre=genre,
        description=description,
        file_id=file_id
    )

    await update.message.reply_text(
        f"✅ **Kino muvaffaqiyatli saqlandi!**\n\n"
        f"🆔 ID: {movie_id}\n"
        f"🎬 Nomi: {title}\n"
        f"🔢 Kodi: `{code}`\n"
        f"📅 Yili: {year}\n"
        f"🎭 Janri: {genre}",
        reply_markup=main_menu_keyboard(is_admin=True),
        parse_mode="Markdown"
    )

    context.user_data.clear()
    return ConversationHandler.END


# --- KANAL QO'SHISH CONVERSATION ---

async def add_channel_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Majburiy kanal qo'shishni boshlash."""
    user = update.effective_user
    if not user or not is_admin(user.id):
        return ConversationHandler.END

    if update.callback_query:
        await update.callback_query.answer()

    text = (
        "➕ **Yangi majburiy kanal qo'shish**\n\n"
        "Format: `kanal_id | kanal_nomi | taklif_linki`\n\n"
        "Misol:\n"
        "`-1001234567890 | Bizning Kanal | https://t.me/+AbCdEfGhIj`\n\n"
        "⚠️ Bot ushbu kanalda **administrator** bo'lishi shart!"
    )

    if update.callback_query:
        await update.callback_query.message.reply_text(text, reply_markup=cancel_keyboard(), parse_mode="Markdown")
    elif update.message:
        await update.message.reply_text(text, reply_markup=cancel_keyboard(), parse_mode="Markdown")

    return ADD_CHANNEL_DATA


async def add_channel_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Kanal ma'lumotlarini qabul qilish va saqlash."""
    if not update.message or not update.message.text:
        await update.message.reply_text("❌ Noto'g'ri format. Iltimos, ko'rsatilgan formatda yuboring.")
        return ADD_CHANNEL_DATA

    parts = [p.strip() for p in update.message.text.split("|")]
    if len(parts) < 3:
        await update.message.reply_text("❌ Noto'g'ri format! `kanal_id | kanal_nomi | taklif_linki` ko'rinishida yuboring.")
        return ADD_CHANNEL_DATA

    channel_id, title, invite_url = parts[0], parts[1], parts[2]
    db.add_channel(channel_id, title, invite_url)

    await update.message.reply_text(
        f"✅ Kanal muvaffaqiyatli qo'shildi:\n\n"
        f"📢 Nomi: **{title}**\n"
        f"🆔 ID: `{channel_id}`\n"
        f"🔗 Link: {invite_url}",
        reply_markup=main_menu_keyboard(is_admin=True),
        parse_mode="Markdown"
    )
    return ConversationHandler.END


# --- HAMMAGA XABAR YUBORISH (BROADCAST) CONVERSATION ---

async def broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """E'lon tarqatishni boshlash."""
    user = update.effective_user
    if not user or not is_admin(user.id):
        return ConversationHandler.END

    if update.callback_query:
        await update.callback_query.answer()

    text = (
        "📢 **Hammaga xabar yuborish**\n\n"
        "Barcha foydalanuvchilarga yubormoqchi bo'lgan xabaringizni yuboring (matn, rasm, video yoki audio):"
    )

    if update.callback_query:
        await update.callback_query.message.reply_text(text, reply_markup=cancel_keyboard(), parse_mode="Markdown")
    elif update.message:
        await update.message.reply_text(text, reply_markup=cancel_keyboard(), parse_mode="Markdown")

    return BROADCAST_RECEIVE


async def broadcast_receive(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Broadcast uchun xabarni qabul qilish."""
    if not update.message:
        return BROADCAST_RECEIVE

    context.user_data['broadcast_msg_id'] = update.message.message_id
    context.user_data['broadcast_chat_id'] = update.message.chat_id

    await update.message.reply_text(
        "❓ **Ushbu xabarni barcha foydalanuvchilarga yuborishni tasdiqlaysizmi?**",
        reply_markup=admin_broadcast_confirm_keyboard(),
        parse_mode="Markdown"
    )
    return BROADCAST_CONFIRM


async def broadcast_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Broadcastni tasdiqlash va yuborish."""
    query = update.callback_query
    if not query:
        return BROADCAST_CONFIRM

    await query.answer()

    if query.data == "adm_broadcast_confirm_no":
        await query.edit_message_text("❌ Xabar yuborish bekor qilindi.")
        context.user_data.clear()
        return ConversationHandler.END

    if query.data == "adm_broadcast_confirm_yes":
        msg_id = context.user_data.get('broadcast_msg_id')
        from_chat_id = context.user_data.get('broadcast_chat_id')

        if not msg_id or not from_chat_id:
            await query.edit_message_text("❌ Xato: Xabar topilmadi.")
            return ConversationHandler.END

        await query.edit_message_text("🚀 Xabar yuborish boshlandi, iltimos kuting...")

        user_ids = db.get_all_user_ids()
        success = 0
        failed = 0

        for u_id in user_ids:
            try:
                await context.bot.copy_message(
                    chat_id=u_id,
                    from_chat_id=from_chat_id,
                    message_id=msg_id
                )
                success += 1
            except Exception as e:
                failed += 1
                logger.debug(f"User {u_id} ga xabar yuborishda xato: {e}")

        await context.bot.send_message(
            chat_id=from_chat_id,
            text=(
                f"✅ **Xabar tarqatish yakunlandi!**\n\n"
                f"🟢 Muvaffaqiyatli: **{success}**\n"
                f"🔴 Yetib bormadi (bloklangan/xato): **{failed}**\n"
                f"📊 Jami: **{len(user_ids)}**"
            ),
            reply_markup=main_menu_keyboard(is_admin=True),
            parse_mode="Markdown"
        )

        context.user_data.clear()
        return ConversationHandler.END

    return BROADCAST_CONFIRM


# --- FOYDALANUVCHINI BOSHQARISH ---

async def user_management_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Foydalanuvchilarni boshqarish bo'yicha amallar va sorovlar."""
    query = update.callback_query
    if not query:
        return

    user = query.from_user
    if not user or not is_admin(user.id):
        await query.answer("❌ Taqiqlangan!", show_alert=True)
        return

    await query.answer()
    data = query.data

    if data == "adm_user_manage":
        await query.edit_message_text(
            "👤 **Foydalanuvchini boshqarish**\n\n"
            "Foydalanuvchini ID raqami bo'yicha qidirish va boshqarish uchun buyruqdan foydalaning:\n"
            "`/user <user_id>` (masalan: `/user 123456789`)",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Orqaga", callback_data="adm_back_main")]])
        )

    elif data.startswith("adm_usr_block_"):
        u_id = int(data.replace("adm_usr_block_", ""))
        db.set_blocked(u_id, True)
        await query.answer("🚫 Foydalanuvchi bloklandi!", show_alert=True)
        await show_user_info_msg(query, u_id)

    elif data.startswith("adm_usr_unblock_"):
        u_id = int(data.replace("adm_usr_unblock_", ""))
        db.set_blocked(u_id, False)
        await query.answer("✅ Foydalanuvchi blokdan chiqarildi!", show_alert=True)
        await show_user_info_msg(query, u_id)

    elif data.startswith("adm_usr_addbal_"):
        u_id = int(data.replace("adm_usr_addbal_", ""))
        db.update_balance(u_id, 10000)
        await query.answer("💰 +10,000 so'm balansga qo'shildi!", show_alert=True)
        await show_user_info_msg(query, u_id)

    elif data.startswith("adm_usr_addprem_"):
        u_id = int(data.replace("adm_usr_addprem_", ""))
        db.set_premium(u_id, 30)
        await query.answer("💎 30 kunlik Premium berildi!", show_alert=True)
        await show_user_info_msg(query, u_id)


async def show_user_info_msg(query, user_id: int) -> None:
    """Foydalanuvchi haqida ma'lumotni tahrirlab ko'rsatish."""
    target_user = db.get_user(user_id)
    if not target_user:
        await query.edit_message_text("❌ Foydalanuvchi topilmadi.")
        return

    is_blocked = db.is_user_blocked(user_id)
    block_btn = (
        InlineKeyboardButton("✅ Blokdan chiqarish", callback_data=f"adm_usr_unblock_{user_id}")
        if is_blocked
        else InlineKeyboardButton("🚫 Bloklash", callback_data=f"adm_usr_block_{user_id}")
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💰 +10,000 Balans", callback_data=f"adm_usr_addbal_{user_id}"),
            InlineKeyboardButton("💎 +30 Kun Premium", callback_data=f"adm_usr_addprem_{user_id}")
        ],
        [block_btn],
        [InlineKeyboardButton("🔙 Orqaga", callback_data="adm_back_main")]
    ])

    text = (
        f"👤 **Foydalanuvchi ma'lumoti:**\n\n"
        f"🆔 ID: `{target_user.get('user_id')}`\n"
        f"👤 Nomi: {target_user.get('full_name', '')}\n"
        f"🏷 Username: @{target_user.get('username', 'Yo\'q')}\n"
        f"💰 Balans: **{target_user.get('balance', 0):,} so'm**\n"
        f"💎 Premium gacha: **{target_user.get('premium_until', 'Yo\'q')}**\n"
        f"🚫 Holati: **{'Bloklangan' if is_blocked else 'Faol'}**"
    )

    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")


# --- ZAXIRA NUSXA (BACKUP) ---

async def admin_backup_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ma'lumotlar bazasining zaxira nusxasini adminga yuborish."""
    user = update.effective_user
    if not user or not is_admin(user.id):
        return

    if not os.path.exists(DB_PATH):
        if update.message:
            await update.message.reply_text("❌ Ma'lumotlar bazasi fayli topilmadi.")
        elif update.callback_query:
            await update.callback_query.answer("❌ DB topilmadi", show_alert=True)
        return

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text("📤 Ma'lumotlar bazasi zaxira nusxasi tayyorlanmoqda...")
        with open(DB_PATH, 'rb') as db_file:
            await context.bot.send_document(
                chat_id=user.id,
                document=db_file,
                filename="cinema_bot_backup.db",
                caption="💾 **Baza zaxira nusxasi (Backup)**",
                parse_mode="Markdown"
            )
    elif update.message:
        with open(DB_PATH, 'rb') as db_file:
            await update.message.reply_document(
                document=db_file,
                filename="cinema_bot_backup.db",
                caption="💾 **Baza zaxira nusxasi (Backup)**",
                parse_mode="Markdown"
            )


# --- AMALNI BEKOR QILISH ---

async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Har qanday ko'p bosqichli muloqotni bekor qilish."""
    user = update.effective_user
    is_adm = is_admin(user.id) if user else False

    context.user_data.clear()

    if update.message:
        await update.message.reply_text(
            "❌ Jarayon bekor qilindi.",
            reply_markup=main_menu_keyboard(is_admin=is_adm)
        )
    elif update.callback_query:
        await update.callback_query.answer("❌ Bekor qilindi.")
        await update.callback_query.message.reply_text(
            "❌ Jarayon bekor qilindi.",
            reply_markup=main_menu_keyboard(is_admin=is_adm)
        )

    return ConversationHandler.END