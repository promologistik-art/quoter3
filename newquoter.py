import os
import asyncio
import logging
from datetime import datetime
import pytz
import random
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

# ===== ЗАГРУЗКА ПЕРЕМЕННЫХ ОКРУЖЕНИЯ =====
load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
YOUR_USERNAME = os.getenv('YOUR_USERNAME')
CHANNEL_ID = os.getenv('CHANNEL_ID')

if not BOT_TOKEN:
    raise ValueError("❌ Не найдена переменная окружения BOT_TOKEN")
if not YOUR_USERNAME:
    raise ValueError("❌ Не найдена переменная окружения YOUR_USERNAME")
if not CHANNEL_ID:
    raise ValueError("❌ Не найдена переменная окружения CHANNEL_ID")
# ==========================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

msk_tz = pytz.timezone('Europe/Moscow')
POST_HOURS = [9, 12, 15, 17, 20]

QUOTES_FILE = "quotes.txt"
STATE_FILE = "last_index.txt"
STATS_FILE = "stats.txt"


class QuoteBot:
    def __init__(self):
        self.quotes = []
        self.current_index = 0
        self.total_quotes = 0
        self.publish_count = 0
        self.warning_sent = False
        self.load_quotes()
        self.load_stats()
        self.load_state()

    def load_quotes(self):
        """Загружает цитаты из файла"""
        try:
            if not os.path.exists(QUOTES_FILE):
                logging.error(f"❌ Файл {QUOTES_FILE} не найден!")
                return False

            with open(QUOTES_FILE, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                # Разделяем по двойному переносу строки (пустая строка между цитатами)
                raw_quotes = content.split('\n\n')

                self.quotes = []
                for quote in raw_quotes:
                    quote = quote.strip()
                    if quote and not quote.startswith('#'):  # Пропускаем комментарии и пустые
                        # Убираем номер, если есть (например "1. " в начале)
                        lines = quote.split('\n')
                        if lines[0].strip() and lines[0][0].isdigit() and '.' in lines[0]:
                            lines[0] = lines[0].split('.', 1)[1].strip()
                        self.quotes.append('\n'.join(lines))

                self.total_quotes = len(self.quotes)
                logging.info(f"📚 Загружено {self.total_quotes} цитат из файла {QUOTES_FILE}")

                if self.total_quotes == 0:
                    logging.error("❌ Файл с цитатами пуст!")
                    return False

                return True
        except Exception as e:
            logging.error(f"❌ Ошибка при чтении файла: {e}")
            return False

    def load_stats(self):
        """Загружает статистику публикаций"""
        try:
            if os.path.exists(STATS_FILE):
                with open(STATS_FILE, 'r') as f:
                    self.publish_count = int(f.read().strip())
                    logging.info(f"📊 Загружена статистика: опубликовано {self.publish_count} цитат")
        except:
            self.publish_count = 0

    def save_stats(self):
        """Сохраняет статистику"""
        try:
            with open(STATS_FILE, 'w') as f:
                f.write(str(self.publish_count))
        except:
            pass

    def load_state(self):
        """Загружает индекс последней опубликованной цитаты"""
        try:
            if os.path.exists(STATE_FILE):
                with open(STATE_FILE, 'r') as f:
                    saved_index = int(f.read().strip())
                    if 0 <= saved_index < self.total_quotes:
                        self.current_index = saved_index
                        logging.info(f"📌 Загружен индекс: {self.current_index}")
                    else:
                        self.current_index = 0
                        logging.info("🔄 Сохраненный индекс некорректен, начинаем с начала")
        except:
            self.current_index = 0

    def save_state(self):
        """Сохраняет текущий индекс"""
        try:
            with open(STATE_FILE, 'w') as f:
                f.write(str(self.current_index))
        except:
            pass

    def get_next_quote(self):
        """Возвращает следующую по очереди цитату"""
        if not self.quotes:
            return None

        quote = self.quotes[self.current_index]

        # Переходим к следующей
        self.current_index += 1
        if self.current_index >= self.total_quotes:
            self.current_index = 0
            logging.info("🔄 Достигнут конец списка, начинаем сначала")

        self.save_state()
        self.publish_count += 1
        self.save_stats()

        return quote

    def get_random_quote(self):
        """Возвращает случайную цитату (для ручного вызова)"""
        if not self.quotes:
            return None
        return random.choice(self.quotes)

    def remaining_before_warning(self):
        """Сколько осталось до предупреждения (каждые 50 постов)"""
        return 50 - (self.publish_count % 50)


quote_bot = QuoteBot()


async def post_quote():
    """Публикует следующую по очереди цитату в канал"""
    quote = quote_bot.get_next_quote()
    if quote:
        try:
            await bot.send_message(CHANNEL_ID, quote)
            logging.info(
                f"📤 Опубликована цитата #{quote_bot.publish_count} (индекс в файле: {quote_bot.current_index})")

            # Проверка на остаток (каждые 50 постов)
            remaining = quote_bot.remaining_before_warning()
            if remaining <= 10 and not quote_bot.warning_sent:
                await bot.send_message(
                    YOUR_USERNAME,
                    f"⚠️ Опубликовано {quote_bot.publish_count} цитат.\n"
                    f"До следующей проверки осталось: {remaining}"
                )
                quote_bot.warning_sent = True

            # Сбрасываем флаг предупреждения после 50
            if quote_bot.publish_count % 50 == 0:
                quote_bot.warning_sent = False

        except Exception as e:
            logging.error(f"❌ Ошибка публикации: {e}")
    else:
        logging.error("❌ Нет цитат для публикации")


async def scheduler():
    """Планировщик публикаций"""
    logging.info("🔄 Планировщик запущен")
    while True:
        try:
            now = datetime.now(msk_tz)
            if now.hour in POST_HOURS and now.minute == 0:
                logging.info(f"⏰ Время публикации {now.hour}:00")
                await post_quote()
                await asyncio.sleep(61)  # Чтобы не опубликовать дважды
            else:
                await asyncio.sleep(30)
        except Exception as e:
            logging.error(f"❌ Ошибка в планировщике: {e}")
            await asyncio.sleep(60)


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "📚 **Бот книжных цитат**\n\n"
        f"Всего цитат в базе: {quote_bot.total_quotes}\n"
        f"Публикации каждый день в 9, 12, 15, 17, 20 по МСК в канал @quoterofday\n\n"
        "**Команды:**\n"
        "/quote — получить случайную цитату сейчас\n"
        "/next — посмотреть следующую по очереди\n"
        "/post_now — опубликовать в канал сейчас\n"
        "/stats — статистика\n"
        "/status — проверка работы"
    )


@dp.message(Command("quote"))
async def cmd_quote(message: types.Message):
    """Случайная цитата в личку"""
    if message.from_user.username == YOUR_USERNAME.replace('@', ''):
        quote = quote_bot.get_random_quote()
        if quote:
            await message.answer(quote)
        else:
            await message.answer("❌ Нет цитат в базе")
    else:
        await message.answer("Нет прав")


@dp.message(Command("next"))
async def cmd_next(message: types.Message):
    """Показать следующую по очереди цитату (без публикации)"""
    if message.from_user.username == YOUR_USERNAME.replace('@', ''):
        if quote_bot.quotes:
            next_quote = quote_bot.quotes[quote_bot.current_index]
            await message.answer(
                f"📌 **Следующая цитата:**\n\n{next_quote}\n\n"
                f"Индекс: {quote_bot.current_index + 1}/{quote_bot.total_quotes}"
            )
        else:
            await message.answer("❌ Нет цитат в базе")
    else:
        await message.answer("Нет прав")


@dp.message(Command("post_now"))
async def cmd_post_now(message: types.Message):
    """Принудительная публикация в канал"""
    if message.from_user.username == YOUR_USERNAME.replace('@', ''):
        await message.answer("⏳ Публикую в канал...")
        await post_quote()
        await message.answer("✅ Опубликовано!")
    else:
        await message.answer("Нет прав")


@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    """Статистика"""
    if message.from_user.username == YOUR_USERNAME.replace('@', ''):
        remaining = quote_bot.remaining_before_warning()
        await message.answer(
            f"📊 **Статистика:**\n"
            f"Всего цитат в базе: {quote_bot.total_quotes}\n"
            f"Опубликовано всего: {quote_bot.publish_count}\n"
            f"Текущий индекс: {quote_bot.current_index + 1}\n"
            f"До предупреждения: {remaining}\n"
            f"Файл: {QUOTES_FILE}"
        )
    else:
        await message.answer("Нет прав")


@dp.message(Command("status"))
async def cmd_status(message: types.Message):
    """Проверка работы"""
    await message.answer(
        "✅ **Бот работает**\n"
        "🔄 Планировщик активен\n"
        f"📚 Цитат в базе: {quote_bot.total_quotes}\n"
        f"📊 Опубликовано: {quote_bot.publish_count}"
    )


async def main():
    logging.info("🚀 Запуск бота...")

    if not quote_bot.quotes:
        logging.error("❌ Не удалось загрузить цитаты!")
        return

    asyncio.create_task(scheduler())
    logging.info("🔄 Планировщик запущен")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())