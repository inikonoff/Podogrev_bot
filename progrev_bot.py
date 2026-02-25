import os
import sys
import signal
import logging
import asyncio
import time
import psutil
from typing import Dict, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response, Request
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command
from aiogram.types import Message
from groq import Groq

# === НАСТРОЙКА ЛОГГИРОВАНИЯ ===
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

# === ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ ===
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
PORT = int(os.environ.get("PORT", 8080))
HOST = os.environ.get("HOST", "0.0.0.0")

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN не установлен")
if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY не установлен")

# === ИНИЦИАЛИЗАЦИЯ КЛИЕНТОВ ===
groq_client = Groq(api_key=GROQ_API_KEY)
bot = Bot(token=TELEGRAM_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# === ХРАНИЛИЩЕ ИСТОРИИ ДИАЛОГОВ ===
chat_histories: Dict[int, List[Dict[str, str]]] = {}
MAX_HISTORY = 20

def get_history(chat_id: int) -> List[Dict[str, str]]:
    return chat_histories.setdefault(chat_id, [])

def add_to_history(chat_id: int, role: str, content: str) -> None:
    history = get_history(chat_id)
    history.append({"role": role, "content": content})
    if len(history) > MAX_HISTORY:
        chat_histories[chat_id] = history[-MAX_HISTORY:]

def clear_history(chat_id: int) -> None:
    chat_histories[chat_id] = []

# === СИСТЕМНЫЙ ПРОМПТ ===
SYSTEM_PROMPT = """Ты — «Архитектор Прогрева», умный нейропомощник, который создаёт мягкий, но сильный прогрев, ведущий к продажам.

В твоём ядре — синтез трёх маркетинговых систем:
• Alex Hormozi — формула ценности и структура предложения;
• Frank Kern — модель мягких продаж через доверие;
• Система Жени Новой — пять типов контента: обучающий, вдохновляющий, вовлекающий, продающий, социальное доказательство.

Ты думаешь как маркетолог топ-уровня и строишь прогревы с точностью дорогого сценариста.
Ты НЕ обучаешь — ты делаешь за пользователя.

─── Пять типов контента (система Жени Новой) ───
1. ОБУЧАЮЩИЙ — даёт ценность, формирует экспертность, прогревает через пользу.
2. ВДОХНОВЛЯЮЩИЙ — история, трансформация, эмоция. Человек видит себя в результате.
3. ВОВЛЕКАЮЩИЙ — вопросы, опросы, дискуссии. Создаёт связь и диалог.
4. ПРОДАЮЩИЙ — оффер, выгоды, призыв к действию. Снимает возражения.
5. СОЦИАЛЬНОЕ ДОКАЗАТЕЛЬСТВО — отзывы, кейсы, результаты клиентов.

─── Алгоритм работы ───
Когда пользователь обращается впервые или просит создать прогрев — задай ВСЕ шесть вопросов одним сообщением:

1. Что ты продаёшь? (продукт, услуга или программа)
2. Как ты продаёшь — постоянно (evergreen) или через запуски?
3. Где будет публиковаться прогрев: Telegram, Stories или обе площадки?
4. Сколько дней нужен прогрев:
   — 1–3 дня — для постоянных продаж,
   — 5–10 дней — для мини-продукта до 10 000 ₽,
   — 14–30 дней — для запуска или продукта от 10 000 ₽.
5. В каком тоне звучит сценарий — мягкий, экспертный, вдохновляющий или провокационный?
6. Есть ли отзывы, кейсы или результаты клиентов? Если да — коротко опиши.

─── Формат архитектуры прогрева ───
После получения ответов создай структуру по дням:

День N — «[Цепляющий заголовок]»
Тип контента: [один из пяти типов]
Цель: [чего достигаем этим постом]
Что показывать: [конкретные тезисы/идеи]
Как построить: [структура поста: с чего начать, как развить, чем закончить]
Социальное доказательство: [где вставить отзыв/кейс, если есть]

─── Правила ───
• Каждый день прогрева — отдельный блок.
• Первые дни — доверие и боль, середина — трансформация и экспертность, конец — оффер и срочность.
• Не используй шаблонные фразы. Каждый прогрев — уникальная стратегия.
• Адаптируй язык под нишу пользователя.
• Если пользователь просит доработать или переделать — делай это без лишних вопросов.
• Отвечай на русском языке.
• Будь конкретным: не «напишите о своём опыте», а «расскажи историю одного клиента, который пришёл с [проблемой] и получил [результат]».
"""

# === ФУНКЦИЯ ЗАПРОСА К GROQ ===
async def ask_groq(chat_id: int, user_message: str) -> str:
    add_to_history(chat_id, "user", user_message)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + get_history(chat_id)

    try:
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(
            None,
            lambda: groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=messages,
                temperature=0.7,
                max_tokens=4096,
            )
        )
        assistant_reply = response.choices[0].message.content
        add_to_history(chat_id, "assistant", assistant_reply)
        return assistant_reply
    except Exception as e:
        logger.error(f"Groq API error: {e}")
        return "⚠️ Произошла ошибка при обращении к модели. Попробуй ещё раз."

# === ОБРАБОТЧИКИ КОМАНД AIOGRAM ===
@dp.message(Command("start"))
async def cmd_start(message: Message) -> None:
    clear_history(message.chat.id)
    welcome = (
        "👋 Привет! Я — <b>Архитектор Прогрева</b>.\n\n"
        "Я создам для тебя структуру прогрева, которая реально приводит к продажам.\n\n"
        "Расскажи, что хочешь продавать — и я задам несколько вопросов, "
        "чтобы собрать архитектуру прогрева под тебя 🔥"
    )
    await message.answer(welcome)

@dp.message(Command("reset"))
async def cmd_reset(message: Message) -> None:
    clear_history(message.chat.id)
    await message.answer("🔄 История очищена. Начинаем с чистого листа!")

@dp.message()
async def handle_message(message: Message) -> None:
    if not message.text:
        return

    await bot.send_chat_action(chat_id=message.chat.id, action="typing")
    reply = await ask_groq(message.chat.id, message.text)

    # Разбиваем на части если > 4096 символов
    for i in range(0, len(reply), 4096):
        await message.answer(reply[i:i + 4096])
        if i + 4096 < len(reply):
            await asyncio.sleep(0.3)

# === ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ===
start_time = time.time()
stats = {"total_requests": 0, "errors": 0}
is_shutting_down = False
polling_task = None

# === GRACEFUL SHUTDOWN ===
def handle_sigterm(signum, frame):
    global is_shutting_down
    if is_shutting_down:
        return
    logger.info("📡 Получен SIGTERM! Инициирую мягкую остановку...")
    is_shutting_down = True

# === POLLING TASK (с автоперезапуском как в шаблоне) ===
async def run_polling():
    global is_shutting_down
    while not is_shutting_down:
        try:
            logger.info("🚀 Запуск polling...")
            await dp.start_polling(bot)
        except asyncio.CancelledError:
            break
        except Exception as e:
            if is_shutting_down:
                break
            logger.error(f"❌ Polling упал: {e}. Перезапуск через 5с...")
            await asyncio.sleep(5)

# === ЖИЗНЕННЫЙ ЦИКЛ FASTAPI ===
@asynccontextmanager
async def lifespan(app: FastAPI):
    global polling_task
    logger.info("🟢 Приложение запускается...")

    # Регистрация обработчиков сигналов
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, handle_sigterm, sig, None)

    # Сбрасываем возможный старый webhook и запускаем polling
    await bot.delete_webhook(drop_pending_updates=True)
    polling_task = asyncio.create_task(run_polling())

    yield  # Сервер работает

    logger.info("🔴 Приложение останавливается...")
    if polling_task and not polling_task.done():
        polling_task.cancel()
        try:
            await polling_task
        except asyncio.CancelledError:
            pass
    try:
        await bot.session.close()
    except Exception as e:
        logger.error(f"Ошибка при закрытии сессии: {e}")

# === СОЗДАНИЕ FASTAPI ПРИЛОЖЕНИЯ ===
app = FastAPI(
    title="Архитектор Прогрева",
    description="Telegram бот для создания прогревающих сценариев",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None
)

# === MIDDLEWARE ДЛЯ МЕТРИК ===
@app.middleware("http")
async def monitor_requests(request: Request, call_next):
    stats["total_requests"] += 1
    try:
        return await call_next(request)
    except Exception:
        stats["errors"] += 1
        raise

# === ЭНДПОИНТЫ ===
@app.get("/")
async def root():
    return {"status": "running", "service": "Архитектор Прогрева"}

@app.get("/health")
@app.head("/health")
async def health():
    """Для UptimeRobot и Render health check"""
    if is_shutting_down:
        return Response(content="Shutting down", status_code=503)
    return Response(content="OK", status_code=200)

@app.get("/metrics")
async def metrics():
    uptime = int(time.time() - start_time)
    ram_mb = psutil.Process().memory_info().rss / 1024 / 1024
    cpu = psutil.Process().cpu_percent()

    text = f"""# HELP bot_uptime Uptime in seconds
# TYPE bot_uptime gauge
bot_uptime {uptime}
# HELP bot_ram_mb RAM usage MB
bot_ram_mb {ram_mb:.2f}
# HELP bot_cpu CPU usage percent
bot_cpu {cpu}
# HELP bot_requests_total Total HTTP requests
bot_requests_total {stats["total_requests"]}
# HELP bot_errors_total Total errors
bot_errors_total {stats["errors"]}
# HELP bot_history_entries Chat history entries
bot_history_entries {len(chat_histories)}
"""
    return Response(content=text, media_type="text/plain")

# === ТОЧКА ВХОДА ===
if __name__ == "__main__":
    import uvicorn
    logger.info(f"🚀 Запуск сервера на {HOST}:{PORT}")
    uvicorn.run(
        "progrev_bot:app",
        host=HOST,
        port=PORT,
        log_level="info",
        workers=1
    )
