import logging
import sqlite3
from datetime import datetime, timedelta
from typing import Any
from config import DB_PATH, FREE_AI_DAILY_LIMIT, REFERRAL_BONUS

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, db_path: str = DB_PATH) -> None:
        self.db_path = db_path
        self.init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    full_name TEXT,
                    balance INTEGER DEFAULT 0,
                    premium_until TEXT,
                    ai_queries_today INTEGER DEFAULT 0,
                    last_query_date TEXT,
                    is_blocked INTEGER DEFAULT 0,
                    referrer_id INTEGER,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    last_active TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS movies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    code TEXT UNIQUE NOT NULL,
                    year INTEGER,
                    genre TEXT,
                    description TEXT,
                    file_id TEXT NOT NULL,
                    views INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS channels (
                    channel_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    invite_url TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS bookmarks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    movie_id INTEGER NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, movie_id)
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)

            cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('mandatory_subscription', '1')")
            conn.commit()

    def get_or_create_user(self, user_id: int, username: str | None, full_name: str, referrer_id: int | None = None) -> dict:
        today_str = datetime.now().strftime("%Y-%m-%d")
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()

            if row:
                cursor.execute("""
                    UPDATE users 
                    SET username = ?, full_name = ?, last_active = ?
                    WHERE user_id = ?
                """, (username, full_name, now_str, user_id))
                conn.commit()
                cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
                return dict(cursor.fetchone())

            valid_referrer = None
            if referrer_id and referrer_id != user_id:
                cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (referrer_id,))
                if cursor.fetchone():
                    valid_referrer = referrer_id

            cursor.execute("""
                INSERT INTO users (user_id, username, full_name, referrer_id, last_query_date, last_active)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (user_id, username, full_name, valid_referrer, today_str, now_str))

            if valid_referrer:
                cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (REFERRAL_BONUS, valid_referrer))

            conn.commit()
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            return dict(cursor.fetchone())

    def update_user_activity(self, user_id: int) -> None:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET last_active = ? WHERE user_id = ?", (now_str, user_id))
            conn.commit()

    def get_user(self, user_id: int) -> dict | None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def update_balance(self, user_id: int, amount: int) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            if not row:
                return 0
            current_balance = row["balance"]
            new_balance = max(0, current_balance + amount)
            cursor.execute("UPDATE users SET balance = ? WHERE user_id = ?", (new_balance, user_id))
            conn.commit()
            return new_balance

    def set_premium(self, user_id: int, days: int) -> str:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT premium_until FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            now = datetime.now()

            current_until = None
            if row and row["premium_until"]:
                try:
                    parsed = datetime.strptime(row["premium_until"], "%Y-%m-%d %H:%M:%S")
                    if parsed > now:
                        current_until = parsed
                except ValueError:
                    current_until = None

            base_time = current_until if current_until else now
            new_expiry = base_time + timedelta(days=days)
            expiry_str = new_expiry.strftime("%Y-%m-%d %H:%M:%S")

            cursor.execute("UPDATE users SET premium_until = ? WHERE user_id = ?", (expiry_str, user_id))
            conn.commit()
            return expiry_str

    def check_and_use_ai_limit(self, user_id: int) -> tuple[bool, int, bool]:
        today_str = datetime.now().strftime("%Y-%m-%d")
        now = datetime.now()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT premium_until, ai_queries_today, last_query_date FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()

            if not row:
                return (False, 0, False)

            is_premium = False
            if row["premium_until"]:
                try:
                    exp_date = datetime.strptime(row["premium_until"], "%Y-%m-%d %H:%M:%S")
                    if exp_date > now:
                        is_premium = True
                except ValueError:
                    is_premium = False

            if is_premium:
                cursor.execute("""
                    UPDATE users 
                    SET ai_queries_today = ai_queries_today + 1, last_query_date = ? 
                    WHERE user_id = ?
                """, (today_str, user_id))
                conn.commit()
                return (True, 999999, True)

            ai_queries = row["ai_queries_today"]
            if row["last_query_date"] != today_str:
                ai_queries = 0

            if ai_queries >= FREE_AI_DAILY_LIMIT:
                return (False, 0, False)

            new_queries = ai_queries + 1
            cursor.execute("""
                UPDATE users 
                SET ai_queries_today = ?, last_query_date = ? 
                WHERE user_id = ?
            """, (new_queries, today_str, user_id))
            conn.commit()

            remaining = max(0, FREE_AI_DAILY_LIMIT - new_queries)
            return (True, remaining, False)

    def is_user_blocked(self, user_id: int) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT is_blocked FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            return bool(row["is_blocked"]) if row else False

    def set_blocked(self, user_id: int, is_blocked: bool) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET is_blocked = ? WHERE user_id = ?", (1 if is_blocked else 0, user_id))
            conn.commit()

    def add_movie(self, title: str, code: str, year: int, genre: str, description: str, file_id: str) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO movies (title, code, year, genre, description, file_id)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (title, code.strip(), year, genre.strip(), description.strip(), file_id))
            conn.commit()
            return cursor.lastrowid

    def get_movie_by_code(self, code: str) -> dict | None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM movies WHERE LOWER(code) = LOWER(?)", (code.strip(),))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_movie_by_id(self, movie_id: int) -> dict | None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM movies WHERE id = ?", (movie_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_all_movies_for_ai(self) -> list[dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, title, code, year, genre, description FROM movies")
            return [dict(row) for row in cursor.fetchall()]

    def increment_movie_views(self, movie_id: int) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE movies SET views = views + 1 WHERE id = ?", (movie_id,))
            conn.commit()

    def get_top_movies(self, limit: int = 10) -> list[dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM movies ORDER BY views DESC, id DESC LIMIT ?", (limit,))
            return [dict(row) for row in cursor.fetchall()]

    def get_all_genres(self) -> list[str]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT genre FROM movies WHERE genre IS NOT NULL AND genre != ''")
            genres_set = set()
            for row in cursor.fetchall():
                parts = [g.strip().capitalize() for g in row["genre"].replace("/", ",").split(",") if g.strip()]
                genres_set.update(parts)
            return sorted(list(genres_set))

    def get_movies_by_genre(self, genre: str, limit: int = 8, offset: int = 0) -> list[dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM movies 
                WHERE LOWER(genre) LIKE LOWER(?) 
                ORDER BY views DESC, id DESC 
                LIMIT ? OFFSET ?
            """, (f"%{genre}%", limit, offset))
            return [dict(row) for row in cursor.fetchall()]

    def delete_movie(self, movie_id: int) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM movies WHERE id = ?", (movie_id,))
            cursor.execute("DELETE FROM bookmarks WHERE movie_id = ?", (movie_id,))
            conn.commit()
            return cursor.rowcount > 0

    def update_movie(self, movie_id: int, title: str, year: int, genre: str, description: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE movies 
                SET title = ?, year = ?, genre = ?, description = ? 
                WHERE id = ?
            """, (title, year, genre, description, movie_id))
            conn.commit()
            return cursor.rowcount > 0

    def get_mandatory_channels(self) -> list[dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM channels ORDER BY created_at ASC")
            return [dict(row) for row in cursor.fetchall()]

    def add_channel(self, channel_id: str, title: str, invite_url: str) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO channels (channel_id, title, invite_url)
                VALUES (?, ?, ?)
            """, (str(channel_id).strip(), title.strip(), invite_url.strip()))
            conn.commit()

    def delete_channel(self, channel_id: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM channels WHERE channel_id = ?", (str(channel_id).strip(),))
            conn.commit()
            return cursor.rowcount > 0

    def get_setting(self, key: str, default: str = "") -> str:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
            conn.commit()

    def get_statistics(self) -> dict:
        today_date = datetime.now().strftime("%Y-%m-%d")
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) AS total_users FROM users")
            total_users = cursor.fetchone()["total_users"]

            cursor.execute("SELECT COUNT(*) AS new_today FROM users WHERE DATE(created_at) = ?", (today_date,))
            new_today = cursor.fetchone()["new_today"]

            cursor.execute("SELECT COUNT(*) AS total_movies FROM movies")
            total_movies = cursor.fetchone()["total_movies"]

            cursor.execute("SELECT COUNT(*) AS active_premiums FROM users WHERE premium_until > ?", (now_str,))
            active_premiums = cursor.fetchone()["active_premiums"]

            cursor.execute("SELECT COUNT(*) AS blocked_users FROM users WHERE is_blocked = 1")
            blocked_users = cursor.fetchone()["blocked_users"]

            cursor.execute("SELECT id, title, code, views FROM movies ORDER BY views DESC LIMIT 5")
            top_viewed = [dict(row) for row in cursor.fetchall()]

            return {
                "total_users": total_users,
                "new_today": new_today,
                "total_movies": total_movies,
                "active_premiums": active_premiums,
                "blocked_users": blocked_users,
                "top_movies": top_viewed
            }

    def get_all_user_ids(self) -> list[int]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT user_id FROM users WHERE is_blocked = 0")
            return [row["user_id"] for row in cursor.fetchall()]

    def toggle_bookmark(self, user_id: int, movie_id: int) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM bookmarks WHERE user_id = ? AND movie_id = ?", (user_id, movie_id))
            row = cursor.fetchone()

            if row:
                cursor.execute("DELETE FROM bookmarks WHERE user_id = ? AND movie_id = ?", (user_id, movie_id))
                conn.commit()
                return False
            else:
                cursor.execute("INSERT INTO bookmarks (user_id, movie_id) VALUES (?, ?)", (user_id, movie_id))
                conn.commit()
                return True

    def get_user_bookmarks(self, user_id: int) -> list[dict]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT m.* FROM movies m
                INNER JOIN bookmarks b ON m.id = b.movie_id
                WHERE b.user_id = ?
                ORDER BY b.id DESC
            """, (user_id,))
            return [dict(row) for row in cursor.fetchall()]