import os
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
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
class Form(StatesGroup):
    transfer = State()
    writeoff = State()
    cleaning_photo = State()
    checklist = State()

# =========================
# Старт
# =========================
@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add("Бар → Кухня", "Кухня → Бар")
    keyboard.add("Списание", "Фото уборки", "Чек-лист уборки")
    await message.answer("Привет! Я бот бара 🍹\nВыбирай действие:", reply_markup=keyboard)

# =========================
# Перенос
# =========================
@dp.message_handler(lambda m: m.text in ["Бар → Кухня", "Кухня → Бар"])
async def start_transfer(message: types.Message, state: FSMContext):
    await state.update_data(direction=message.text)
    await message.answer("Напишите что и сколько переносим\nПример: Лимон 5")
    await Form.transfer.set()

@dp.message_handler(state=Form.transfer)
async def process_transfer(message: types.Message, state: FSMContext):
    data = await state.get_data()
    direction = data["direction"]
    text = (
        f"📦 Перенос\n{direction}\n{message.text}\nОт: {message.from_user.full_name}"
    )
    await bot.send_message(ADMIN_ID, text)
    await message.answer("Перенос отправлен ✅")
    await state.finish()

# =========================
# Списание
# =========================
@dp.message_handler(lambda m: m.text == "Списание")
async def start_writeoff(message: types.Message):
    await message.answer("Напишите что и сколько списываем\nПример: Мята 3 порча")
    await Form.writeoff.set()

@dp.message_handler(state=Form.writeoff)
async def process_writeoff(message: types.Message, state: FSMContext):
    text = f"🗑 Списание\n{message.text}\nОт: {message.from_user.full_name}"
    await bot.send_message(ADMIN_ID, text)
    await message.answer("Списание отправлено ✅")
    await state.finish()

# =========================
# Фото уборки
# =========================
@dp.message_handler(lambda m: m.text == "Фото уборки")
async def ask_cleaning_photo(message: types.Message):
    await message.answer("Отправьте фото бара после смены")
    await Form.cleaning_photo.set()

@dp.message_handler(content_types=['photo'], state=Form.cleaning_photo)
async def handle_cleaning_photo(message: types.Message, state: FSMContext):
    text = f"📸 Фото уборки на проверке от {message.from_user.full_name}"
    await bot.send_photo(ADMIN_ID, message.photo[-1].file_id, caption=text)
    await message.answer("Фото отправлено на проверку ✅")
    await state.finish()

# =========================
# Чек-лист уборки
# =========================
CHECKLIST_ITEMS = [
    "Протереть барную стойку",
    "Вымыть раковину",
    "Вымыть пол",
    "Протереть оборудование",
    "Вынести мусор",
]

@dp.message_handler(lambda m: m.text == "Чек-лист уборки")
async def start_checklist(message: types.Message, state: FSMContext):
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    for item in CHECKLIST_ITEMS:
        keyboard.add(KeyboardButton(item))
    keyboard.add(KeyboardButton("Готово"))
    await message.answer(
        "Отметьте выполненные пункты, нажимая на кнопки. Когда закончите, нажмите 'Готово'.",
        reply_markup=keyboard
    )
    await state.update_data(done_items=[])
    await Form.checklist.set()

@dp.message_handler(state=Form.checklist)
async def process_checklist(message: types.Message, state: FSMContext):
    data = await state.get_data()
    done_items = data.get("done_items", [])

    if message.text == "Готово":
        text = "🧹 Чек-лист уборки\n"
        text += "\n".join([f"✅ {i}" for i in done_items])
        text += f"\nОт: {message.from_user.full_name}"
        await bot.send_message(ADMIN_ID, text)
        await message.answer("Чек-лист отправлен ✅")
        await state.finish()
    elif message.text in CHECKLIST_ITEMS:
        if message.text not in done_items:
            done_items.append(message.text)
        await state.update_data(done_items=done_items)
        await message.answer(f"Отметил ✅ {message.text}")

# =========================
# Запуск
# =========================
if __name__ == "__main__":
    print("Бот запущен")
    executor.start_polling(dp, skip_updates=True)
