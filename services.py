import json
import logging
import threading
import time
from typing import Any
import httpx
from flask import Flask

logger = logging.getLogger(__name__)


class GroqAIService:
    def __init__(self, api_key: str) -> None:
        self.api_key: str = api_key.strip() if api_key else ""
        self.api_url: str = "https://api.groq.com/openai/v1/chat/completions"
        self.model: str = "llama-3.3-70b-versatile"

    async def find_movies_by_prompt(
        self, user_prompt: str, catalog: list[dict]
    ) -> tuple[dict | None, list[dict], str]:
        if not catalog:
            return None, [], "Hozircha bot bazasida kinolar mavjud emas."

        if not self.api_key:
            return None, [], "AI xizmati vaqtincha sozlanmagan (API kalit yo'q)."

        compact_catalog = []
        for movie in catalog:
            compact_catalog.append({
                "id": movie.get("id"),
                "t": movie.get("title", ""),
                "y": movie.get("year", 0),
                "g": movie.get("genre", ""),
                "d": (movie.get("description", "") or "")[:250],
                "c": movie.get("code", "")
            })

        system_instruction = (
            "Sen professional kino tavsiya qiluvchi o'zbek tilidagi AI yordamchisisan. "
            "Senga foydalanuvchi so'rovi va FAQATGINA bizning kino bazamiz JSON ro'yxatida beriladi. "
            "QAT'IY QOIDA: Ro'yxatda mavjud bo'lmagan kinolarni aslo to'qib chiqarma yoki taklif qilma! "
            "Foydalanuvchi tasvirlagan voqea, personaj, janr yoki mavzuni bazadagi kinolar tavsifi bilan solishtir. "
            "Agar 90% dan yuqori aniqlikda bitta aniq mos keladigan kino bo'lsa, 'exact_match_id' maydoniga uning id raqamini yoz. "
            "Agar aniq bitta film bo'lmasa yoki shubhali bo'lsa, 'exact_match_id' null bo'lsin. "
            "'suggested_ids' maydoniga eng yaqin kelishi mumkin bo'lgan maksimum 3 ta film ID raqamini massiv ko'rinishida kirit. "
            "Agar umuman hech qanday aloqador kino topilmasa, 'exact_match_id' null va 'suggested_ids' [] bo'lsin. "
            "'explanation' maydoniga o'zbek tilida (lotin alifbosida) xushmuomala qisqa tushuntirish yoz. "
            "Javobing FAQAT va FAQAT quyidagi JSON formatida bo'lishi shart, boshqa hech qanday so'z qo'shma: "
            '{"exact_match_id": int or null, "suggested_ids": [int, ...], "explanation": "string"}'
        )

        user_content = (
            f"Foydalanuvchi so'rovi: {user_prompt.strip()}\n\n"
            f"Mavjud filmlar katalogi:\n{json.dumps(compact_catalog, ensure_ascii=False)}"
        )

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": user_content}
            ],
            "temperature": 0.2,
            "response_format": {"type": "json_object"}
        }

        movie_map = {m["id"]: m for m in catalog if "id" in m}

        try:
            async with httpx.AsyncClient(timeout=25.0) as client:
                response = await client.post(self.api_url, headers=headers, json=payload)
                if response.status_code != 200:
                    logger.error(f"Groq API xatosi {response.status_code}: {response.text}")
                    return None, [], "AI qidiruv xizmatida vaqtinchalik uzilish yuz berdi."

                result_data = response.json()
                content_str = result_data["choices"][0]["message"]["content"]
                parsed = json.loads(content_str)

                exact_id = parsed.get("exact_match_id")
                suggested_ids = parsed.get("suggested_ids", [])
                explanation = parsed.get(
                    "explanation", "Qidiruv natijalari tayyorlandi."
                )

                exact_movie = movie_map.get(exact_id) if exact_id else None
                suggested_movies = []

                if isinstance(suggested_ids, list):
                    for sid in suggested_ids[:3]:
                        if sid != exact_id and sid in movie_map:
                            suggested_movies.append(movie_map[sid])

                return exact_movie, suggested_movies, explanation

        except httpx.TimeoutException:
            logger.warning("Groq AI API so'rovida timeout yuz berdi.")
            return None, [], "Qidiruv vaqti tugadi. Iltimos, qaytadan urinib ko'ring."
        except Exception as e:
            logger.exception(f"Groq AI xizmati orqali qidirishda kutilmagan xato: {e}")
            return None, [], "Kinoni qidirishda tizim xatosi yuz berdi."


class RateLimiter:
    def __init__(self, cooldown: float = 1.0) -> None:
        self.cooldown: float = cooldown
        self.last_requests: dict[int, float] = {}

    def is_rate_limited(self, user_id: int) -> bool:
        current_time = time.time()
        last_time = self.last_requests.get(user_id, 0.0)
        if current_time - last_time < self.cooldown:
            return True
        self.last_requests[user_id] = current_time
        return False


async def check_channel_subscriptions(
    bot: Any, user_id: int, channels: list[dict]
) -> tuple[bool, list[dict]]:
    if not channels:
        return True, []

    unsubscribed: list[dict] = []
    valid_statuses = ("creator", "administrator", "member", "restricted")

    for channel in channels:
        channel_id = channel.get("channel_id")
        if not channel_id:
            continue

        try:
            target_chat_id: int | str = channel_id
            try:
                target_chat_id = int(channel_id)
            except ValueError:
                target_chat_id = channel_id

            member = await bot.get_chat_member(chat_id=target_chat_id, user_id=user_id)
            if member.status not in valid_statuses:
                unsubscribed.append(channel)
        except Exception as err:
            logger.warning(
                f"Kanal obunasi tekshirilmadi ({channel_id}) user {user_id}: {err}"
            )
            unsubscribed.append(channel)

    is_subscribed = len(unsubscribed) == 0
    return is_subscribed, unsubscribed


def run_keep_alive(port: int = 8080) -> None:
    app = Flask("TelegramCinemaBotKeepAlive")

    @app.route("/")
    def index():
        return "Bot muvaffaqiyatli ishlab turibdi!", 200

    @app.route("/health")
    def health():
        return {"status": "ok", "service": "Telegram Movie Bot"}, 200

    def start_flask() -> None:
        werkzeug_logger = logging.getLogger("werkzeug")
        werkzeug_logger.setLevel(logging.ERROR)
        app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

    server_thread = threading.Thread(target=start_flask, daemon=True)
    server_thread.start()
    logger.info(f"Flask keep-alive serveri {port}-portda ishga tushirildi.")