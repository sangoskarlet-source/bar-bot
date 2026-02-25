import os
import requests
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup
from aiogram.utils import executor

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
SHEET_WEBHOOK_URL = os.getenv("SHEET_WEBHOOK_URL")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# ================= КЛАВИАТУРЫ =================

main_kb = ReplyKeyboardMarkup(resize_keyboard=True)
main_kb.add("📦 Перенос")
main_kb.add("🗑 Списание")
main_kb.add("📸 Фото уборки")
main_kb.add("🧹 Чеклист")
main_kb.add("🧹 Ежедневная уборка")

direction_kb = ReplyKeyboardMarkup(resize_keyboard=True)
direction_kb.add("Кухня → Бар")
direction_kb.add("Бар → Кухня")
direction_kb.add("⬅ Назад")

checklist_kb = ReplyKeyboardMarkup(resize_keyboard=True)
checklist_kb.add("Полы")
checklist_kb.add("Барная стойка")
checklist_kb.add("Холодильники")
checklist_kb.add("Готово")
checklist_kb.add("⬅ Назад")

back_kb = ReplyKeyboardMarkup(resize_keyboard=True)
back_kb.add("⬅ Назад")

user_states = {}

# ================= ОТПРАВКА В SHEETS =================

def send_to_sheet(sheet, user, text, extra=""):
    try:
        requests.post(
            SHEET_WEBHOOK_URL,
            json={
                "sheet": sheet,
                "user": user,
                "text": text,
                "extra": extra
            },
            timeout=10
        )
    except Exception as e:
        print("Ошибка отправки:", e)

# ================= НАЗАД =================

@dp.message_handler(lambda m: m.text == "⬅ Назад")
async def go_back(message: types.Message):
    user_states.pop(message.from_user.id, None)
    await message.answer("Главное меню:", reply_markup=main_kb)

# ================= СТАРТ =================

@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    await message.answer("Выберите действие:", reply_markup=main_kb)

# ================= ПЕРЕНОС =================

@dp.message_handler(lambda m: m.text == "📦 Перенос")
async def transfer_start(message: types.Message):
    user_states[message.from_user.id] = {"state": "transfer_direction"}
    await message.answer("Выберите направление:", reply_markup=direction_kb)

@dp.message_handler(lambda m: m.text in ["Кухня → Бар", "Бар → Кухня"])
async def transfer_direction(message: types.Message):
    user_states[message.from_user.id] = {
        "state": "transfer_text",
        "direction": message.text
    }
    await message.answer("Напишите что и сколько переносим:", reply_markup=back_kb)

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "transfer_text")
async def transfer_save(message: types.Message):
    direction = user_states[message.from_user.id]["direction"]

    send_to_sheet(
        "Переносы",
        str(message.from_user.id),
        message.text,
        direction
    )

    await message.answer("✅ Перенос записан", reply_markup=main_kb)
    user_states.pop(message.from_user.id)

# ================= СПИСАНИЕ =================

@dp.message_handler(lambda m: m.text == "🗑 Списание")
async def writeoff_start(message: types.Message):
    user_states[message.from_user.id] = {"state": "writeoff"}
    await message.answer("Напишите что списываем:", reply_markup=back_kb)

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "writeoff")
async def writeoff_save(message: types.Message):
    send_to_sheet(
        "Списания",
        str(message.from_user.id),
        message.text
    )

    await message.answer("✅ Списание записано", reply_markup=main_kb)
    user_states.pop(message.from_user.id)

# ================= ЕЖЕДНЕВНАЯ УБОРКА =================

@dp.message_handler(lambda m: m.text == "🧹 Ежедневная уборка")
async def daily_cleaning(message: types.Message):
    user_states[message.from_user.id] = {"state": "daily_cleaning"}
    await message.answer("Отправьте фото выполнения уборки:", reply_markup=back_kb)

# ================= СОХРАНЕНИЕ ФОТО =================

@dp.message_handler(content_types=types.ContentType.PHOTO)
async def save_photo(message: types.Message):

    state = user_states.get(message.from_user.id, {}).get("state")
    if not state:
        return

    file_id = message.photo[-1].file_id

    if state == "daily_cleaning":
        sheet_name = "Фото"
    else:
        return

    send_to_sheet(
        sheet_name,
        str(message.from_user.id),
        file_id
    )

    await message.answer("✅ Фото сохранено", reply_markup=main_kb)
    user_states.pop(message.from_user.id)

# ================= WEBHOOK =================

async def on_startup(dp):
    await bot.set_webhook(WEBHOOK_URL)

if __name__ == "__main__":
    executor.start_webhook(
        dispatcher=dp,
        webhook_path="",
        on_startup=on_startup,
        skip_updates=True,
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8080))
    )
