from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
import logging
import asyncio
from datetime import datetime, time

# ====== Настройки ======
API_TOKEN = "8553414858:AAGVIXM8rCDWMpeq-Nu3yHPZazNtJX6w_sQ"  # вставь свой токен от BotFather
ADMIN_ID = 5646298852               # твой Telegram ID

logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

# ====== Клавиатуры ======
transfer_kb = ReplyKeyboardMarkup(resize_keyboard=True)
transfer_kb.add(KeyboardButton("Бар → Кухня"))
transfer_kb.add(KeyboardButton("Кухня → Бар"))
transfer_kb.add(KeyboardButton("Списание"))

checklist_buttons = InlineKeyboardMarkup(row_width=2)
checklist_buttons.add(
    InlineKeyboardButton("✅ Сделано", callback_data="check_done"),
    InlineKeyboardButton("❌ Не сделано", callback_data="check_notdone")
)

# ====== Хранение данных в памяти ======
tasks_in_review = {}  # для фото уборки на проверке

# ====== Хендлеры ======
@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    await message.answer(
        "Привет! Я бот бара 🍹\n\n"
        "Выбирай действие:",
        reply_markup=transfer_kb
    )

@dp.message_handler(lambda message: message.text == "Бар → Кухня")
async def bar_to_kitchen(message: types.Message):
    await bot.send_message(ADMIN_ID, f"[Перенос] {message.from_user.full_name} → Бар → Кухня")
    await message.answer("Сообщение отправлено админу ✅")

@dp.message_handler(lambda message: message.text == "Кухня → Бар")
async def kitchen_to_bar(message: types.Message):
    await bot.send_message(ADMIN_ID, f"[Перенос] {message.from_user.full_name} → Кухня → Бар")
    await message.answer("Сообщение отправлено админу ✅")

@dp.message_handler(lambda message: message.text == "Списание")
async def write_transfer(message: types.Message):
    await message.answer("Отправь текст списания, например: Мята 30 порча")

@dp.message_handler(content_types=["text"])
async def handle_text(message: types.Message):
    if message.text.lower().startswith(("мята", "апельсины", "лимон", "сок", "порошок")):
        await bot.send_message(ADMIN_ID, f"[Списание] {message.from_user.full_name}: {message.text}")
        await message.answer("Списание отправлено админу ✅")
    else:
        await message.answer("Не понимаю. Выбери действие через клавиатуру.")

@dp.message_handler(content_types=["photo"])
async def handle_photo(message: types.Message):
    tasks_in_review[message.from_user.id] = message.photo[-1].file_id
    await message.answer("Фото получено. Статус: на проверке 🕒")
    await bot.send_message(ADMIN_ID, f"[Фото уборки] от {message.from_user.full_name}. Используй /check {message.from_user.id} чтобы проверить.")

@dp.callback_query_handler(lambda c: c.data and c.data.startswith("check_"))
async def process_check(call: types.CallbackQuery):
    await call.answer()
    status = call.data.split("_")[1]
    await bot.send_message(ADMIN_ID, f"Фото уборки: {status.upper()}")
    await call.message.edit_text(f"Статус подтверждён: {status.upper()}")

# ====== Напоминания об уборке ======
async def send_reminder(reminder_time: time):
    while True:
        now = datetime.now().time()
        if now.hour == reminder_time.hour and now.minute == reminder_time.minute:
            # Пример: отправляем всем пользователям (для простоты — один раз админу)
            await bot.send_message(ADMIN_ID, f"Напоминание об уборке ({reminder_time.strftime('%H:%M')})")
        await asyncio.sleep(60)

async def scheduler():
    await asyncio.gather(
        send_reminder(time(11, 0)),
        send_reminder(time(16, 0)),
        send_reminder(time(23, 0))
    )

# ====== Запуск бота ======
if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.create_task(scheduler())
    executor.start_polling(dp, skip_updates=True)