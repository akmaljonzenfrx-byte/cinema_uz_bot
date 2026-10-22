import html
import json
import logging
import traceback
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from config import ADMIN_IDS, BOT_TOKEN, PORT, setup_logging
from database import Database
from handlers_admin import (
    add_channel_data,
    add_channel_start,
    add_movie_code,
    add_movie_description,
    add_movie_genre,
    add_movie_start,
    add_movie_title,
    add_movie_video,
    add_movie_year,
    admin_backup_handler,
    admin_callback_handler,
    admin_panel_handler,
    broadcast_confirm,
    broadcast_receive,
    broadcast_start,
    cancel_conversation,
    user_management_callback,
)
from handlers_user import (
    bookmarks_handler,
    buy_premium_callback,
    check_sub_callback,
    confirm_buy_premium_callback,
    genre_select_callback,
    genres_handler,
    help_handler,
    movie_click_callback,
    profile_handler,
    search_movie_handler,
    start_handler,
    toggle_bookmark_callback,
    top_movies_handler,
)
from services import run_keep_alive

logger = logging.getLogger(__name__)

# Suhbat holatlari konstantalari
ADD_MOVIE_VIDEO, ADD_MOVIE_TITLE, ADD_MOVIE_YEAR, ADD_MOVIE_GENRE, ADD_MOVIE_DESC, ADD_MOVIE_CODE = range(6)
ADD_CHANNEL_DATA = 10
BROADCAST_RECEIVE, BROADCAST_CONFIRM = 20, 21


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Tizimda yuzaga kelgan xatoliklarni ushlaydi va adminga bildiradi."""
    logger.error("So'rovni bajarishda kutilmagan xatolik:", exc_info=context.error)

    tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
    tb_string = "".join(tb_list)

    update_str = update.to_dict() if isinstance(update, Update) else str(update)
    message = (
        f"⚠️ <b>Botda kutilmagan xatolik yuz berdi!</b>\n\n"
        f"<b>Update:</b>\n<code>{html.escape(json.dumps(update_str, indent=2, ensure_ascii=False)[:1000])}</code>\n\n"
        f"<b>Xatolik matni:</b>\n<code>{html.escape(str(context.error)[:1000])}</code>\n\n"
        f"<b>Traceback:</b>\n<code>{html.escape(tb_string[-2000:])}</code>"
    )

    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=message,
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logger.error(f"Xatolik haqidagi xabarni adminga ({admin_id}) yuborib bo'lmadi: {e}")


def main() -> None:
    """Botni ishga tushiruvchi asosiy funksiya."""
    setup_logging()
    logger.info("Bot tizimi ishga tushirilmoqda...")

    if not BOT_TOKEN:
        logger.critical("BOT_TOKEN muhit o'zgaruvchisi topilmadi! Dastur to'xtatildi.")
        return

    # Ma'lumotlar bazasini tekshirish va jadvallarni initsializatsiya qilish
    db = Database()
    db.init_db()

    # Render platformasida faollikni ta'minlash uchun Flask serverini alohida thread'da yoqish
    run_keep_alive(port=PORT)

    application = Application.builder().token(BOT_TOKEN).build()

    # 1. Kino qo'shish ConversationHandler
    add_movie_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(add_movie_start, pattern=r"^adm_add_movie$")
        ],
        states={
            ADD_MOVIE_VIDEO: [
                MessageHandler(filters.VIDEO, add_movie_video)
            ],
            ADD_MOVIE_TITLE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_movie_title)
            ],
            ADD_MOVIE_YEAR: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_movie_year)
            ],
            ADD_MOVIE_GENRE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_movie_genre)
            ],
            ADD_MOVIE_DESC: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_movie_description)
            ],
            ADD_MOVIE_CODE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_movie_code)
            ],
        },
        fallbacks=[
            MessageHandler(filters.Regex(r"^(❌ Bekor qilish|bekor)$"), cancel_conversation),
            CommandHandler("cancel", cancel_conversation),
            CallbackQueryHandler(cancel_conversation, pattern=r"^adm_home$")
        ],
        allow_reentry=True
    )

    # 2. Kanal qo'shish ConversationHandler
    add_channel_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(add_channel_start, pattern=r"^adm_add_(chan|channel)$")
        ],
        states={
            ADD_CHANNEL_DATA: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_channel_data)
            ]
        },
        fallbacks=[
            MessageHandler(filters.Regex(r"^(❌ Bekor qilish|bekor)$"), cancel_conversation),
            CommandHandler("cancel", cancel_conversation),
            CallbackQueryHandler(cancel_conversation, pattern=r"^adm_home$")
        ],
        allow_reentry=True
    )

    # 3. Hammaga xabar tarqatish (Broadcast) ConversationHandler
    broadcast_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(broadcast_start, pattern=r"^adm_broadcast$")
        ],
        states={
            BROADCAST_RECEIVE: [
                MessageHandler(filters.ALL & ~filters.COMMAND, broadcast_receive)
            ],
            BROADCAST_CONFIRM: [
                CallbackQueryHandler(broadcast_confirm, pattern=r"^adm_broadcast_confirm_.*$"),
                CallbackQueryHandler(broadcast_confirm, pattern=r"^adm_confirm_broadcast$"),
                CallbackQueryHandler(cancel_conversation, pattern=r"^adm_cancel_broadcast$")
            ]
        },
        fallbacks=[
            MessageHandler(filters.Regex(r"^(❌ Bekor qilish|bekor)$"), cancel_conversation),
            CommandHandler("cancel", cancel_conversation),
            CallbackQueryHandler(cancel_conversation, pattern=r"^adm_home$")
        ],
        allow_reentry=True
    )

    # ConversationHandlerlarni ro'yxatdan o'tkazish
    application.add_handler(add_movie_conv)
    application.add_handler(add_channel_conv)
    application.add_handler(broadcast_conv)

    # Boshlang'ich va asosiy komandalar
    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(CommandHandler("admin", admin_panel_handler))
    application.add_handler(CommandHandler("help", help_handler))
    application.add_handler(CommandHandler("profile", profile_handler))
    application.add_handler(CommandHandler("genres", genres_handler))
    application.add_handler(CommandHandler("top", top_movies_handler))
    application.add_handler(CommandHandler("bookmarks", bookmarks_handler))

    # Reply menyu tugmalari uchun handlerlar
    application.add_handler(
        MessageHandler(
            filters.Regex(r"^(⚙️ Admin panel|⚙️ Admin Panel)$"),
            admin_panel_handler
        )
    )
    application.add_handler(
        MessageHandler(
            filters.Regex(r"^(🔥 Top kinolar)$"),
            top_movies_handler
        )
    )
    application.add_handler(
        MessageHandler(
            filters.Regex(r"^(🎭 Janrlar)$"),
            genres_handler
        )
    )
    application.add_handler(
        MessageHandler(
            filters.Regex(r"^(⭐ Tanlanganlar|⭐ Saqlanganlar)$"),
            bookmarks_handler
        )
    )
    application.add_handler(
        MessageHandler(
            filters.Regex(r"^(👤 Profilim)$"),
            profile_handler
        )
    )
    application.add_handler(
        MessageHandler(
            filters.Regex(r"^(💎 Premium|💎 Premium olish)$"),
            buy_premium_callback
        )
    )
    application.add_handler(
        MessageHandler(
            filters.Regex(r"^(ℹ️ Yordam)$"),
            help_handler
        )
    )

    # CallbackQuery handlerlari (Foydalanuvchi)
    application.add_handler(CallbackQueryHandler(check_sub_callback, pattern=r"^check_subscription$"))
    application.add_handler(CallbackQueryHandler(movie_click_callback, pattern=r"^(mov|movie)_-?\d+$"))
    application.add_handler(CallbackQueryHandler(genre_select_callback, pattern=r"^genre_.*$"))
    application.add_handler(CallbackQueryHandler(bookmarks_handler, pattern=r"^(my_bookmarks|view_bookmarks)$"))
    application.add_handler(CallbackQueryHandler(toggle_bookmark_callback, pattern=r"^(bookmark_|bm_)-?\d+$"))
    application.add_handler(CallbackQueryHandler(buy_premium_callback, pattern=r"^(buy_premium_menu|open_premium_plans)$"))
    application.add_handler(CallbackQueryHandler(confirm_buy_premium_callback, pattern=r"^(buy_prem_confirm_|confirm_buy_premium_).*$"))
    application.add_handler(CallbackQueryHandler(profile_handler, pattern=r"^(refresh_profile|back_to_profile)$"))

    # CallbackQuery handlerlari (Administrator)
    application.add_handler(CallbackQueryHandler(admin_backup_handler, pattern=r"^adm_backup$"))
    application.add_handler(CallbackQueryHandler(user_management_callback, pattern=r"^(adm_user_manage|adm_users|adm_u_).*$"))
    application.add_handler(CallbackQueryHandler(admin_callback_handler, pattern=r"^adm_.*$"))

    # Qidiruv handleri: Barcha boshqa yozilgan matnlar kod yoki AI orqali qidiruvga yo'naltiriladi
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search_movie_handler))

    # Xatoliklarni ushlovchi global funksiya
    application.add_error_handler(error_handler)

    logger.info("Bot muvaffaqiyatli ishga tushdi va xabarlarni qabul qilishga tayyor!")
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()