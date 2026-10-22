import html
import logging
from telegram import Update
from telegram.ext import ContextTypes

from config import (
    ADMIN_IDS,
    DB_PATH,
    GROQ_API_KEY,
    PREMIUM_PRICE_30_DAYS,
    REFERRAL_BONUS,
)
from database import Database
from keyboards import (
    channel_subscription_keyboard,
    genres_keyboard,
    main_menu_keyboard,
    movie_card_keyboard,
    movies_list_keyboard,
    premium_plans_keyboard,
    profile_keyboard,
)
from services import GroqAIService, RateLimiter, check_channel_subscriptions

logger = logging.getLogger(__name__)

db = Database(DB_PATH)
ai_service = GroqAIService(GROQ_API_KEY)
rate_limiter = RateLimiter(cooldown=1.0)


def _is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


async def _verify_subscription_flow(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user = update.effective_user
    if not user:
        return False

    is_forced = db.get_setting("is_forced_sub", "0") == "1"
    if not is_forced or _is_admin(user.id):
        return True

    channels = db.get_mandatory_channels()
    if not channels:
        return True

    is_subscribed, missing_channels = await check_channel_subscriptions(context.bot, user.id, channels)
    if not is_subscribed:
        text = (
            "⚠️ <b>Botdan foydalanish uchun quyidagi kanallarga obuna bo'lishingiz shart!</b>\n\n"
            "Obuna bo'lgach, <b>«✅ Obunani tekshirish»</b> tugmasini bosing."
        )
        reply_markup = channel_subscription_keyboard(missing_channels)

        if update.callback_query:
            try:
                await update.callback_query.answer("Iltimos, avval barcha kanallarga a'zo bo'ling!", show_alert=True)
                await update.callback_query.message.edit_text(text, reply_markup=reply_markup, parse_mode="HTML")
            except Exception:
                await update.effective_message.reply_text(text, reply_markup=reply_markup, parse_mode="HTML")
        else:
            await update.effective_message.reply_text(text, reply_markup=reply_markup, parse_mode="HTML")
        return False

    return True


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user:
        return

    if rate_limiter.is_rate_limited(user.id):
        return

    if db.is_user_blocked(user.id):
        await update.effective_message.reply_text("⛔️ Siz bot tomonidan bloklangansiz.")
        return

    referrer_id = None
    if context.args and len(context.args) > 0:
        arg = context.args[0]
        if arg.startswith("ref_") and arg[4:].isdigit():
            possible_ref = int(arg[4:])
            if possible_ref != user.id:
                referrer_id = possible_ref
        elif arg.isdigit():
            movie = db.get_movie_by_code(arg)
            if movie:
                db.get_or_create_user(user.id, user.username, user.full_name)
                db.update_user_activity(user.id)
                db.increment_movie_views(movie["id"])
                bookmarks = [b["id"] for b in db.get_user_bookmarks(user.id)]
                is_bm = movie["id"] in bookmarks
                caption = (
                    f"🎬 <b>{html.escape(movie['title'])}</b> ({movie['year']})\n\n"
                    f"🔢 <b>Kodi:</b> <code>{html.escape(movie['code'])}</code>\n"
                    f"🎭 <b>Janri:</b> {html.escape(movie['genre'])}\n"
                    f"👁 <b>Ko'rishlar:</b> {movie['views'] + 1}\n\n"
                    f"📝 <b>Tavsifi:</b>\n{html.escape(movie['description'])}"
                )
                try:
                    await update.effective_message.reply_video(
                        video=movie["file_id"],
                        caption=caption,
                        parse_mode="HTML",
                        reply_markup=movie_card_keyboard(movie["id"], is_bookmarked=is_bm, is_admin=_is_admin(user.id))
                    )
                    return
                except Exception as e:
                    logger.error(f"Kino yuborishda xatolik: {e}")

    user_info = db.get_or_create_user(
        user_id=user.id,
        username=user.username,
        full_name=user.full_name,
        referrer_id=referrer_id
    )
    db.update_user_activity(user.id)

    if not await _verify_subscription_flow(update, context):
        return

    welcome_text = (
        f"Assalomu alaykum, <b>{html.escape(user.first_name)}</b>! 🍿\n\n"
        f"Kinolar olamiga xush kelibsiz! Botimiz orqali sevimli filmlaringizni osongina topishingiz mumkin:\n\n"
        f"🔢 <b>Kino kodi orqali:</b> Shunchaki film kodini yuboring (masalan, <code>101</code>).\n"
        f"🧠 <b>Aqlli AI qidiruv:</b> Film syujetini o'z so'zlaringiz bilan tasvirlab yozing "
        f"(masalan: <i>«Kema cho'kishi haqidagi sevgi qissasi»</i>).\n\n"
        f"Quyidagi menyu orqali bot imkoniyatlaridan foydalanishingiz mumkin:"
    )

    await update.effective_message.reply_text(
        welcome_text,
        reply_markup=main_menu_keyboard(is_admin=_is_admin(user.id)),
        parse_mode="HTML"
    )


async def check_sub_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    user = query.from_user
    if db.is_user_blocked(user.id):
        await query.edit_message_text("⛔️ Siz bot tomonidan bloklangansiz.")
        return

    channels = db.get_mandatory_channels()
    is_subscribed, missing_channels = await check_channel_subscriptions(context.bot, user.id, channels)

    if is_subscribed:
        await query.message.delete()
        await context.bot.send_message(
            chat_id=user.id,
            text="✅ <b>Obuna muvaffaqiyatli tasdiqlandi!</b>\n\nEndi botdan to'liq foydalanishingiz mumkin.",
            reply_markup=main_menu_keyboard(is_admin=_is_admin(user.id)),
            parse_mode="HTML"
        )
    else:
        text = (
            "⚠️ <b>Hali barcha kanallarga a'zo bo'lmadingiz!</b>\n\n"
            "Iltimos, ro'yxatdagi barcha kanallarga a'zo bo'ling va qaytadan tekshiring:"
        )
        reply_markup = channel_subscription_keyboard(missing_channels)
        try:
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode="HTML")
        except Exception:
            pass


async def search_movie_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user:
        return

    if rate_limiter.is_rate_limited(user.id):
        await update.effective_message.reply_text("⏱ Iltimos, so'rovlarni juda tez yubormang.")
        return

    if db.is_user_blocked(user.id):
        await update.effective_message.reply_text("⛔️ Siz bot tomonidan bloklangansiz.")
        return

    if not await _verify_subscription_flow(update, context):
        return

    text = update.effective_message.text.strip()
    if not text:
        return

    db.get_or_create_user(user.id, user.username, user.full_name)
    db.update_user_activity(user.id)

    if text == "🔍 Qidiruv":
        await update.effective_message.reply_text(
            "🔎 <b>Kino qidirish usullari:</b>\n\n"
            "1. <b>Kino kodi:</b> Faqat raqam yuboring (masalan: <code>101</code>)\n"
            "2. <b>AI Aqlli qidiruv:</b> Film sujetini tasvirlang (masalan: <i>«Sehrgar bolakay va uning maktabdagi do'stlari»</i>)",
            parse_mode="HTML"
        )
        return
    elif text == "🎭 Janrlar":
        await genres_handler(update, context)
        return
    elif text == "🔥 Top kinolar":
        await top_movies_handler(update, context)
        return
    elif text == "👤 Profilim":
        await profile_handler(update, context)
        return
    elif text == "⭐️ Premium":
        await buy_premium_callback(update, context)
        return
    elif text == "📌 Saqlanganlar":
        await bookmarks_handler(update, context)
        return
    elif text == "ℹ️ Yordam":
        await help_handler(update, context)
        return

    if text.isdigit():
        movie = db.get_movie_by_code(text)
        if not movie:
            await update.effective_message.reply_text(
                f"❌ <b>{html.escape(text)}</b> kodli kino bazadan topilmadi.\n"
                "Iltimos, kodni to'g'ri kiritganingizni tekshiring yoki tavsif orqali qidiring.",
                parse_mode="HTML"
            )
            return

        db.increment_movie_views(movie["id"])
        bookmarks = [b["id"] for b in db.get_user_bookmarks(user.id)]
        is_bm = movie["id"] in bookmarks
        caption = (
            f"🎬 <b>{html.escape(movie['title'])}</b> ({movie['year']})\n\n"
            f"🔢 <b>Kodi:</b> <code>{html.escape(movie['code'])}</code>\n"
            f"🎭 <b>Janri:</b> {html.escape(movie['genre'])}\n"
            f"👁 <b>Ko'rishlar:</b> {movie['views'] + 1}\n\n"
            f"📝 <b>Tavsifi:</b>\n{html.escape(movie['description'])}"
        )
        try:
            await update.effective_message.reply_video(
                video=movie["file_id"],
                caption=caption,
                parse_mode="HTML",
                reply_markup=movie_card_keyboard(movie["id"], is_bookmarked=is_bm, is_admin=_is_admin(user.id))
            )
        except Exception as e:
            logger.error(f"Kino jo'natish xatosi: {e}")
            await update.effective_message.reply_text(
                f"⚠️ Film videosini yuklashda xatolik yuz berdi:\n\n{caption}",
                parse_mode="HTML",
                reply_markup=movie_card_keyboard(movie["id"], is_bookmarked=is_bm, is_admin=_is_admin(user.id))
            )
        return

    can_use, remaining, is_premium = db.check_and_use_ai_limit(user.id)
    if not can_use:
        await update.effective_message.reply_text(
            "⚠️ <b>Kunlik bepul AI qidiruv limiti tugadi!</b>\n\n"
            "Cheksiz AI qidiruvdan foydalanish uchun <b>⭐️ Premium</b> obunani faollashtiring yoki ertaga qayta urinib ko'ring.",
            reply_markup=profile_keyboard(),
            parse_mode="HTML"
        )
        return

    status_msg = await update.effective_message.reply_text(
        "🧠 <i>AI filmlar bazasini tahlil qilmoqda, iltimos kuting...</i>",
        parse_mode="HTML"
    )

    catalog = db.get_all_movies_for_ai()
    if not catalog:
        await status_msg.edit_text("ℹ️ Filmlar bazasi hozircha bo'sh. Tez orada yangi kinolar qo'shiladi.")
        return

    best_match, alternatives, reason = await ai_service.find_movies_by_prompt(text, catalog)

    limit_info = "Cheksiz (Premium)" if is_premium else f"{remaining} ta qoldi"

    if not best_match and not alternatives:
        await status_msg.edit_text(
            f"🔍 Sizning so'rovingiz: <i>«{html.escape(text)}»</i>\n\n"
            f"❌ Afsuski, bazamizdan bunga mos keladigan kino topilmadi.\n\n"
            f"💡 <i>Qidiruv so'zlarini boshqacharoq tasvirlab ko'ring.</i>\n"
            f"📊 <b>Bugungi AI limit:</b> {limit_info}",
            parse_mode="HTML"
        )
        return

    response_lines = [
        f"🤖 <b>AI Qidiruv natijalari</b>",
        f"🔎 <i>«{html.escape(text)}»</i>\n"
    ]

    if reason:
        response_lines.append(f"💡 <b>Izoh:</b> {html.escape(reason)}\n")

    buttons_list = []
    if best_match:
        response_lines.append(
            f"🎯 <b>Eng mos kelgan film:</b>\n"
            f"🎬 <b>{html.escape(best_match['title'])}</b> ({best_match['year']}) — Kod: <code>{html.escape(best_match['code'])}</code>\n"
        )
        buttons_list.append(best_match)

    if alternatives:
        response_lines.append("📌 <b>O'xshash boshqa variantlar:</b>")
        for idx, alt in enumerate(alternatives, start=1):
            response_lines.append(f"{idx}. {html.escape(alt['title'])} ({alt['year']}) — Kod: <code>{html.escape(alt['code'])}</code>")
            if alt not in buttons_list:
                buttons_list.append(alt)

    response_lines.append(f"\n📊 <b>Bugungi AI limit:</b> {limit_info}")

    await status_msg.edit_text(
        "\n".join(response_lines),
        reply_markup=movies_list_keyboard(buttons_list, prefix="ai_mov"),
        parse_mode="HTML"
    )


async def movie_click_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    data = query.data
    movie_id = None
    if data.startswith("ai_mov_"):
        movie_id = int(data.replace("ai_mov_", ""))
    elif data.startswith("gen_mov_"):
        movie_id = int(data.replace("gen_mov_", ""))
    elif data.startswith("top_mov_"):
        movie_id = int(data.replace("top_mov_", ""))
    elif data.startswith("bm_mov_"):
        movie_id = int(data.replace("bm_mov_", ""))
    elif data.startswith("movie_"):
        movie_id = int(data.replace("movie_", ""))

    if not movie_id:
        return

    movie = db.get_movie_by_id(movie_id)
    if not movie:
        await query.message.reply_text("❌ Film ma'lumotlar bazasidan topilmadi yoki o'chirilgan.")
        return

    user = query.from_user
    db.increment_movie_views(movie["id"])
    bookmarks = [b["id"] for b in db.get_user_bookmarks(user.id)]
    is_bm = movie["id"] in bookmarks

    caption = (
        f"🎬 <b>{html.escape(movie['title'])}</b> ({movie['year']})\n\n"
        f"🔢 <b>Kodi:</b> <code>{html.escape(movie['code'])}</code>\n"
        f"🎭 <b>Janri:</b> {html.escape(movie['genre'])}\n"
        f"👁 <b>Ko'rishlar:</b> {movie['views'] + 1}\n\n"
        f"📝 <b>Tavsifi:</b>\n{html.escape(movie['description'])}"
    )

    try:
        await context.bot.send_video(
            chat_id=user.id,
            video=movie["file_id"],
            caption=caption,
            parse_mode="HTML",
            reply_markup=movie_card_keyboard(movie["id"], is_bookmarked=is_bm, is_admin=_is_admin(user.id))
        )
    except Exception as e:
        logger.error(f"Kino yuborishda xatolik: {e}")
        await context.bot.send_message(
            chat_id=user.id,
            text=f"⚠️ Video faylni yuklashda xatolik:\n\n{caption}",
            parse_mode="HTML",
            reply_markup=movie_card_keyboard(movie["id"], is_bookmarked=is_bm, is_admin=_is_admin(user.id))
        )


async def genres_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user:
        return

    if not await _verify_subscription_flow(update, context):
        return

    genres = db.get_all_genres()
    if not genres:
        await update.effective_message.reply_text("ℹ️ Hozircha janrlar ro'yxati shakllanmagan.")
        return

    text = "🎭 <b>O'zingizga qiziq bo'lgan kino janrini tanlang:</b>"
    await update.effective_message.reply_text(text, reply_markup=genres_keyboard(genres), parse_mode="HTML")


async def genre_select_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    data = query.data
    if data == "back_to_genres":
        genres = db.get_all_genres()
        await query.edit_message_text(
            "🎭 <b>Kino janrini tanlang:</b>",
            reply_markup=genres_keyboard(genres),
            parse_mode="HTML"
        )
        return

    if not data.startswith("genre_"):
        return

    genre_name = data.replace("genre_", "")
    movies = db.get_movies_by_genre(genre_name, limit=10)

    if not movies:
        await query.edit_message_text(
            f"ℹ️ <b>{html.escape(genre_name)}</b> janrida hali kinolar mavjud emas.",
            reply_markup=genres_keyboard(db.get_all_genres()),
            parse_mode="HTML"
        )
        return

    text = f"🎭 <b>{html.escape(genre_name)}</b> janridagi filmlar:\n\nTomosha qilish uchun kinoni tanlang:"
    await query.edit_message_text(
        text,
        reply_markup=movies_list_keyboard(movies, prefix="gen_mov"),
        parse_mode="HTML"
    )


async def top_movies_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user:
        return

    if not await _verify_subscription_flow(update, context):
        return

    top_movies = db.get_top_movies(limit=10)
    if not top_movies:
        await update.effective_message.reply_text("ℹ️ Hozircha filmlar mavjud emas.")
        return

    text = "🔥 <b>Eng ko'p ko'rilgan TOP 10 film:</b>\n\nBirini tanlang va tomosha qiling:"
    await update.effective_message.reply_text(
        text,
        reply_markup=movies_list_keyboard(top_movies, prefix="top_mov"),
        parse_mode="HTML"
    )


async def profile_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user:
        return

    if not await _verify_subscription_flow(update, context):
        return

    user_data = db.get_or_create_user(user.id, user.username, user.full_name)
    bot_info = await context.bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref_{user.id}"

    is_premium = bool(user_data.get("is_premium", 0))
    premium_status = "Yo'q"
    if is_premium:
        prem_until = user_data.get("premium_until", "")
        premium_status = f"⭐️ Faol (Muddati: {prem_until})"

    text = (
        f"👤 <b>Foydalanuvchi Profili</b>\n\n"
        f"🆔 <b>ID:</b> <code>{user.id}</code>\n"
        f"👤 <b>Ism:</b> {html.escape(user.full_name)}\n"
        f"💰 <b>Balans:</b> {user_data['balance']:,} so'm\n"
        f"⭐️ <b>Premium:</b> {premium_status}\n"
        f"👥 <b>Taklif qilgan do'stlaringiz:</b> {user_data['referral_count']} ta\n\n"
        f"🔗 <b>Sizning taklif havolangiz:</b>\n<code>{ref_link}</code>\n\n"
        f"<i>Do'stlaringizga ulashing va har bir taklif qilingan faol do'stingiz uchun {REFERRAL_BONUS:,} so'm bonusga ega bo'ling!</i>"
    )

    if update.callback_query:
        try:
            await update.callback_query.message.edit_text(text, reply_markup=profile_keyboard(), parse_mode="HTML")
        except Exception:
            await update.effective_message.reply_text(text, reply_markup=profile_keyboard(), parse_mode="HTML")
    else:
        await update.effective_message.reply_text(text, reply_markup=profile_keyboard(), parse_mode="HTML")


async def buy_premium_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user:
        return

    user_data = db.get_or_create_user(user.id, user.username, user.full_name)

    text = (
        f"⭐️ <b>PREMIUM OBUNA AFZALLIKLARI</b>\n\n"
        f"🚀 <b>Cheksiz AI qidiruv:</b> Istalgancha syujet orqali filmlarni qidiring!\n"
        f"⚡️ <b>Tezkor server:</b> Filmlarni yuqori tezlikda yuklab olish imkoniyati.\n"
        f"🚫 <b>Reklamasiz interfeys:</b> Xalaqit beruvchi reklamalarsiz toza bot tajribasi.\n\n"
        f"💰 <b>Narxi:</b> 30 kunlik — <b>{PREMIUM_PRICE_30_DAYS:,} so'm</b>\n"
        f"💳 <b>Sizning balansingiz:</b> {user_data['balance']:,} so'm\n\n"
        f"Balansingizni to'ldirish uchun do'stlaringizni taklif qiling yoki adminga murojaat qiling."
    )

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.edit_text(
            text,
            reply_markup=premium_plans_keyboard(),
            parse_mode="HTML"
        )
    else:
        await update.effective_message.reply_text(
            text,
            reply_markup=premium_plans_keyboard(),
            parse_mode="HTML"
        )


async def confirm_buy_premium_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    user = query.from_user
    user_data = db.get_or_create_user(user.id, user.username, user.full_name)

    balance = user_data.get("balance", 0)

    if balance < PREMIUM_PRICE_30_DAYS:
        await query.answer(
            f"Mablag' yetarli emas! Sizning balansingiz: {balance:,} so'm. Kerakli summa: {PREMIUM_PRICE_30_DAYS:,} so'm.",
            show_alert=True
        )
        return

    db.update_balance(user.id, -PREMIUM_PRICE_30_DAYS)
    new_until = db.set_premium(user.id, 30)

    success_text = (
        f"🎉 <b>Tabriklaymiz! Siz muvaffaqiyatli Premium foydalanuvchiga aylandingiz!</b>\n\n"
        f"⭐️ <b>Premium muddati:</b> {new_until} gacha\n"
        f"💰 <b>Qolgan balansingiz:</b> {balance - PREMIUM_PRICE_30_DAYS:,} so'm\n\n"
        f"Endi barcha imkoniyatlar siz uchun cheklovlarsiz ishlaydi!"
    )

    await query.edit_message_text(
        success_text,
        reply_markup=profile_keyboard(),
        parse_mode="HTML"
    )


async def bookmarks_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user:
        return

    if not await _verify_subscription_flow(update, context):
        return

    bookmarks = db.get_user_bookmarks(user.id)
    if not bookmarks:
        text = "📌 <b>Siz hali hech qanday kinoni saqlamadingiz.</b>\n\nKino ko'rish paytida «📌 Saqlash» tugmasini bosib shu yerga qo'shishingiz mumkin."
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.message.edit_text(text, reply_markup=profile_keyboard(), parse_mode="HTML")
        else:
            await update.effective_message.reply_text(text, parse_mode="HTML")
        return

    text = "📌 <b>Siz saqlagan kinolar ro'yxati:</b>\n\nTomosha qilish uchun kinoni tanlang:"
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.edit_text(
            text,
            reply_markup=movies_list_keyboard(bookmarks, prefix="bm_mov"),
            parse_mode="HTML"
        )
    else:
        await update.effective_message.reply_text(
            text,
            reply_markup=movies_list_keyboard(bookmarks, prefix="bm_mov"),
            parse_mode="HTML"
        )


async def toggle_bookmark_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = query.from_user
    data = query.data

    if not data.startswith("bm_toggle_"):
        await query.answer()
        return

    movie_id = int(data.replace("bm_toggle_", ""))
    is_now_bookmarked = db.toggle_bookmark(user.id, movie_id)

    if is_now_bookmarked:
        await query.answer("📌 Film saqlanganlarga qo'shildi!", show_alert=False)
    else:
        await query.answer("🗑 Film saqlanganlardan olib tashlandi!", show_alert=False)

    try:
        await query.edit_message_reply_markup(
            reply_markup=movie_card_keyboard(movie_id, is_bookmarked=is_now_bookmarked, is_admin=_is_admin(user.id))
        )
    except Exception:
        pass


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user:
        return

    if not await _verify_subscription_flow(update, context):
        return

    text = (
        "ℹ️ <b>Kino Botidan foydalanish bo'yicha qo'llanma:</b>\n\n"
        "1. <b>Kino kodini yuborish:</b> Agar kino kodini bilsangiz, to'g'ridan-to'g'ri kodni yuboring (masalan: <code>105</code>).\n"
        "2. <b>Aqlli AI qidiruv:</b> Kino nomini eslolmasangiz, esingizda qolgan voqealarni yozing. Sun'iy intellekt uni bazamizdan darhol topib beradi.\n"
        "3. <b>Janrlar:</b> Menyu orqali o'zingiz yoqtirgan janrdagi kinolarni ko'rishingiz mumkin.\n"
        "4. <b>Saqlanganlar:</b> Qiziq filmlarni keyinroq ko'rish uchun saqlab qo'ying.\n"
        "5. <b>⭐️ Premium obuna:</b> Bepul foydalanuvchilar kuniga 5 marta AI qidiruvdan foydalana oladi. Cheksiz qidiruv uchun Premium sotib oling!\n\n"
        "Savol va takliflar bo'lsa, administratorlarga murojaat qilishingiz mumkin."
    )

    await update.effective_message.reply_text(
        text,
        reply_markup=main_menu_keyboard(is_admin=_is_admin(user.id)),
        parse_mode="HTML"
    )