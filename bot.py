import os
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup
from aiogram.utils import executor
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.fsm_storage.memory import MemoryStorage

API_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# =========================
# Состояния
# =========================
class TransferState(StatesGroup):
    waiting_text = State()

# =========================
# Старт
# =========================
@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add("Бар → Кухня", "Кухня → Бар")
    keyboard.add("Списание", "Фото уборки")
    await message.answer("Привет! Я бот бара 🍹\nВыбирай действие:", reply_markup=keyboard)

# =========================
# Начало переноса
# =========================
@dp.message_handler(lambda m: m.text in ["Бар → Кухня", "Кухня → Бар"])
async def start_transfer(message: types.Message, state: FSMContext):
    await state.update_data(direction=message.text)
    await message.answer("Напишите что и сколько переносим\nПример: Лимон 5")
    await TransferState.waiting_text.set()

# =========================
# Получаем текст переноса
# =========================
@dp.message_handler(state=TransferState.waiting_text)
async def process_transfer(message: types.Message, state: FSMContext):
    data = await state.get_data()
    direction = data["direction"]

    text = (
        f"📦 Перенос\n"
        f"{direction}\n"
        f"{message.text}\n\n"
        f"От: {message.from_user.full_name}"
    )

    await bot.send_message(ADMIN_ID, text)
    await message.answer("Перенос отправлен ✅")
    await state.finish()

# =========================
# Запуск
# =========================
if __name__ == "__main__":
    print("Бот запущен")
    executor.start_polling(dp, skip_updates=True)
