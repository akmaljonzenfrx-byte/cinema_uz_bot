from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton


def main_menu_keyboard(is_admin: bool = False) -> ReplyKeyboardMarkup:
    """Asosiy reply menyu klaviaturasi."""
    keyboard = [
        [KeyboardButton("🔍 Kino qidirish (Kod yoki AI)"), KeyboardButton("🔥 Top kinolar")],
        [KeyboardButton("🎭 Janrlar"), KeyboardButton("⭐ Tanlanganlar")],
        [KeyboardButton("👤 Profilim"), KeyboardButton("💎 Premium")],
        [KeyboardButton("ℹ️ Yordam")]
    ]
    if is_admin:
        keyboard.append([KeyboardButton("⚙️ Admin panel")])

    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def profile_keyboard() -> InlineKeyboardMarkup:
    """Profil boshqaruvi uchun inline klaviatura."""
    keyboard = [
        [
            InlineKeyboardButton("💎 Premium sotib olish", callback_data="buy_premium_menu"),
            InlineKeyboardButton("💰 Hisobni to'ldirish", callback_data="deposit_balance")
        ],
        [
            InlineKeyboardButton("⭐ Saqlangan kinolarim", callback_data="my_bookmarks"),
            InlineKeyboardButton("👥 Do'stlarni taklif qilish", callback_data="referral_info")
        ],
        [
            InlineKeyboardButton("🔄 Yangilash", callback_data="refresh_profile")
        ]
    ]
    return InlineKeyboardMarkup(keyboard=keyboard)


def premium_plans_keyboard() -> InlineKeyboardMarkup:
    """Premium tariflarini tanlash klaviaturasi."""
    keyboard = [
        [InlineKeyboardButton("💎 30 kunlik Premium — 15,000 so'm", callback_data="buy_prem_confirm_30")],
        [InlineKeyboardButton("💎 90 kunlik Premium — 39,000 so'm", callback_data="buy_prem_confirm_90")],
        [InlineKeyboardButton("💎 365 kunlik Premium — 120,000 so'm", callback_data="buy_prem_confirm_365")],
        [InlineKeyboardButton("💳 Balansni to'ldirish", callback_data="deposit_balance")],
        [InlineKeyboardButton("🔙 Orqaga", callback_data="back_to_profile")]
    ]
    return InlineKeyboardMarkup(keyboard=keyboard)


def genres_keyboard(genres: list[str]) -> InlineKeyboardMarkup:
    """Janrlar ro'yxatini chiqaruvchi inline klaviatura."""
    keyboard = []
    row = []
    for index, genre in enumerate(genres, start=1):
        clean_genre = genre.strip()
        if clean_genre:
            btn_text = f"🎬 {clean_genre}"
            row.append(InlineKeyboardButton(text=btn_text, callback_data=f"genre_{clean_genre}"))
            if len(row) == 2:
                keyboard.append(row)
                row = []
    if row:
        keyboard.append(row)

    keyboard.append([InlineKeyboardButton("🔙 Orqaga", callback_data="back_to_main")])
    return InlineKeyboardMarkup(keyboard=keyboard)


def movie_card_keyboard(movie_id: int, is_bookmarked: bool = False, is_admin: bool = False) -> InlineKeyboardMarkup:
    """Alohida kino kartasi ostidagi inline boshqaruv tugmalari."""
    bookmark_text = "❌ Tanlanganlardan o'chirish" if is_bookmarked else "⭐ Sevimlilarga qo'shish"
    keyboard = [
        [
            InlineKeyboardButton(bookmark_text, callback_data=f"bookmark_{movie_id}"),
            InlineKeyboardButton("📤 Ulashish", switch_inline_query=f"movie_{movie_id}")
        ]
    ]

    if is_admin:
        keyboard.append([
            InlineKeyboardButton("✏️ Tahrirlash", callback_data=f"adm_edit_mov_{movie_id}"),
            InlineKeyboardButton("🗑 O'chirish", callback_data=f"adm_del_mov_{movie_id}")
        ])

    return InlineKeyboardMarkup(keyboard=keyboard)


def movies_list_keyboard(movies: list[dict], prefix: str = 'mov') -> InlineKeyboardMarkup:
    """Kino qidiruv natijalari yoki top kinolar ro'yxati tugmalari."""
    keyboard = []
    for movie in movies:
        m_id = movie.get("id")
        m_code = movie.get("code", "")
        m_title = movie.get("title", "Kino")
        m_year = movie.get("year", "")
        year_str = f" ({m_year})" if m_year else ""
        button_text = f"🎬 [{m_code}] {m_title}{year_str}"
        keyboard.append([InlineKeyboardButton(text=button_text, callback_data=f"{prefix}_{m_id}")])

    return InlineKeyboardMarkup(keyboard=keyboard)


def channel_subscription_keyboard(unsubscribed_channels: list[dict]) -> InlineKeyboardMarkup:
    """Majburiy a'zolik uchun obuna bo'linmagan kanallar va tekshirish tugmasi."""
    keyboard = []
    for index, channel in enumerate(unsubscribed_channels, start=1):
        title = channel.get("title") or f"Kanal #{index}"
        invite_url = channel.get("invite_url", "https://t.me/")
        keyboard.append([
            InlineKeyboardButton(text=f"➕ {title}", url=invite_url)
        ])

    keyboard.append([
        InlineKeyboardButton("✅ Obunani tekshirish", callback_data="check_subscription")
    ])
    return InlineKeyboardMarkup(keyboard=keyboard)


def admin_main_keyboard() -> InlineKeyboardMarkup:
    """Admin boshqaruv panelining bosh menyusi."""
    keyboard = [
        [
            InlineKeyboardButton("🎬 Kino qo'shish", callback_data="adm_add_movie"),
            InlineKeyboardButton("📢 Kanallar boshqaruvi", callback_data="adm_channels")
        ],
        [
            InlineKeyboardButton("📊 To'liq statistika", callback_data="adm_stats"),
            InlineKeyboardButton("📨 Hammaga xabar yuborish", callback_data="adm_broadcast")
        ],
        [
            InlineKeyboardButton("👤 Foydalanuvchini boshqarish", callback_data="adm_user_manage"),
            InlineKeyboardButton("💾 Zaxira nusxa (DB)", callback_data="adm_backup")
        ]
    ]
    return InlineKeyboardMarkup(keyboard=keyboard)


def admin_channels_keyboard(channels: list[dict], is_forced: bool) -> InlineKeyboardMarkup:
    """Majburiy kanallarni sozlash va o'chirish klaviaturasi."""
    keyboard = []
    status_icon = "🟢" if is_forced else "🔴"
    status_text = "Majburiy obuna: YOQILGAN" if is_forced else "Majburiy obuna: O'CHIRILGAN"
    
    keyboard.append([
        InlineKeyboardButton(f"{status_icon} {status_text}", callback_data="adm_toggle_forced_sub")
    ])

    for ch in channels:
        ch_id = ch.get("channel_id")
        ch_title = ch.get("title", "Kanal")
        keyboard.append([
            InlineKeyboardButton(f"❌ {ch_title}", callback_data=f"adm_del_chan_{ch_id}")
        ])

    keyboard.append([
        InlineKeyboardButton("➕ Yangi kanal qo'shish", callback_data="adm_add_chan")
    ])
    keyboard.append([
        InlineKeyboardButton("🔙 Admin panelga qaytish", callback_data="adm_back_main")
    ])
    return InlineKeyboardMarkup(keyboard=keyboard)


def admin_broadcast_confirm_keyboard() -> InlineKeyboardMarkup:
    """Xabar tarqatishni tasdiqlash klaviaturasi."""
    keyboard = [
        [
            InlineKeyboardButton("✅ Ha, yuborilsin", callback_data="adm_broadcast_confirm_yes"),
            InlineKeyboardButton("❌ Bekor qilish", callback_data="adm_broadcast_confirm_no")
        ]
    ]
    return InlineKeyboardMarkup(keyboard=keyboard)


def cancel_keyboard() -> ReplyKeyboardMarkup:
    """Har qanday ko'p bosqichli amallarni to'xtatish tugmasi."""
    keyboard = [
        [KeyboardButton("❌ Bekor qilish")]
    ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)