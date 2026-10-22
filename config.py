import logging
import os
import sys
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "").strip()

admin_ids_raw: str = os.getenv("ADMIN_IDS", "").strip()
ADMIN_IDS: list[int] = []
if admin_ids_raw:
    for item in admin_ids_raw.replace(";", ",").split(","):
        cleaned = item.strip()
        if cleaned.isdigit() or (cleaned.startswith("-") and cleaned[1:].isdigit()):
            ADMIN_IDS.append(int(cleaned))

GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "").strip()
PORT: int = int(os.getenv("PORT", "8080"))
DB_PATH: str = os.getenv("DB_PATH", "cinema_bot.db").strip()

FREE_AI_DAILY_LIMIT: int = int(os.getenv("FREE_AI_DAILY_LIMIT", "5"))
PREMIUM_PRICE_30_DAYS: int = int(os.getenv("PREMIUM_PRICE_30_DAYS", "15000"))
REFERRAL_BONUS: int = int(os.getenv("REFERRAL_BONUS", "1000"))


def setup_logging() -> None:
    logging_level = os.getenv("LOGGING_LEVEL", "INFO").upper()
    level = getattr(logging, logging_level, logging.INFO)

    log_format = "%(asctime)s - [%(levelname)s] - %(name)s - %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    handlers: list[logging.Handler] = [
        logging.StreamHandler(sys.stdout)
    ]

    log_file = os.getenv("LOG_FILE", "").strip()
    if log_file:
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    logging.basicConfig(
        level=level,
        format=log_format,
        datefmt=date_format,
        handlers=handlers,
        force=True
    )

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.INFO)
    logging.getLogger("werkzeug").setLevel(logging.WARNING)