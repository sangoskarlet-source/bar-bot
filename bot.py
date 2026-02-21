import os
import requests
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils import executor

BOT_TOKEN = os.getenv("BOT_TOKEN")
SHEET_WEBHOOK_URL = os.getenv("SHEET_WEBHOOK_URL")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# ---------- КЛАВИАТУРА ----------

main_kb = ReplyKeyboardMarkup(resize_keyboard=True)
main_kb.add("📦 Перенос")
main_kb.add("🗑 Списание")
main_kb.add("📸 Фото уборки")
main_kb.add("🧹 Чеклист")

direction_kb = ReplyKeyboardMarkup(resize_keyboard=True)
direction_kb.add("Кухня → Бар")
direction_kb.add("Бар → Кухня")

checklist_kb = ReplyKeyboardMarkup(resize_keyboard=True)
checklist_kb.add("Полы")
checklist_kb.add("Барная стойка")
checklist_kb.add("Холодильники")
checklist_kb.add("Готово")

user_states = {}

# ---------- ФУНКЦИЯ ОТПРАВКИ В ТАБЛИЦУ ----------

def send_to_sheet(sheet, user, text, extra=""):
    try:
        requests.post(SHEET_WEBHOOK_URL, json={
            "sheet": sheet,
            "user": user,
            "text": text,
            "extra": extra
        })
    except:
        pass

# ---------- СТАРТ ----------

@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    await message.answer("Выберите действие:", reply_markup=main_kb)

# ---------- ПЕРЕНОС ----------

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
    await message.answer("Напишите что и сколько переносим:")

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "transfer_text")
async def transfer_save(message: types.Message):
    direction = user_states[message.from_user.id]["direction"]

    send_to_sheet(
        "Переносы",
        message.from_user.full_name,
        message.text,
        direction
    )

    await message.answer("✅ Перенос записан", reply_markup=main_kb)
    user_states.pop(message.from_user.id)

# ---------- СПИСАНИЕ ----------

@dp.message_handler(lambda m: m.text == "🗑 Списание")
async def writeoff_start(message: types.Message):
    user_states[message.from_user.id] = {"state": "writeoff"}
    await message.answer("Напишите что списываем и количество:")

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "writeoff")
async def writeoff_save(message: types.Message):
    send_to_sheet(
        "Списания",
        message.from_user.full_name,
        message.text
    )

    await message.answer("✅ Списание записано", reply_markup=main_kb)
    user_states.pop(message.from_user.id)

# ---------- ФОТО ----------

@dp.message_handler(lambda m: m.text == "📸 Фото уборки")
async def photo_request(message: types.Message):
    user_states[message.from_user.id] = {"state": "photo"}
    await message.answer("Отправьте фото:")

@dp.message_handler(content_types=types.ContentType.PHOTO)
async def save_photo(message: types.Message):
    if user_states.get(message.from_user.id, {}).get("state") == "photo":
        file_id = message.photo[-1].file_id

        send_to_sheet(
            "Фото",
            message.from_user.full_name,
            file_id
        )

        await message.answer("✅ Фото сохранено", reply_markup=main_kb)
        user_states.pop(message.from_user.id)

# ---------- ЧЕКЛИСТ ----------

@dp.message_handler(lambda m: m.text == "🧹 Чеклист")
async def checklist_start(message: types.Message):
    user_states[message.from_user.id] = {
        "state": "checklist",
        "items": []
    }
    await message.answer("Отметьте выполненное:", reply_markup=checklist_kb)

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "checklist")
async def checklist_process(message: types.Message):
    if message.text == "Готово":
        items = user_states[message.from_user.id]["items"]

        send_to_sheet(
            "Чеклист",
            message.from_user.full_name,
            ", ".join(items)
        )

        await message.answer("✅ Чеклист сохранён", reply_markup=main_kb)
        user_states.pop(message.from_user.id)
    else:
        user_states[message.from_user.id]["items"].append(message.text)
        await message.answer(f"Добавлено: {message.text}")

# ---------- ЗАПУСК ----------

if __name__ == "__main__":
    from aiogram import executor
    import os

    WEBHOOK_URL = os.getenv("WEBHOOK_URL")

    async def on_startup(dp):
        await bot.set_webhook(WEBHOOK_URL)

    executor.start_webhook(
        dispatcher=dp,
        webhook_path="",
        on_startup=on_startup,
        skip_updates=True,
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8080))
    )
