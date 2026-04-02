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

user_states = {}

def reset_state(user_id):
    user_states.pop(user_id, None)

CHECKLIST_ITEMS = [
    "Лайн чек заготовок",
    "Фото бара отправлено",
    "Крышки закрыты",
    "Стоп-лист проверен",
    "Баклахи с водой",
    "Поверхности протерты",
    "Посуда в баре",
    "Кофе машина",
    "Раковины",
    "Кассовый узел",
    "Зона алкоголя",
    "Порядок на складе"
]

# ================= КНОПКИ =================
main_kb = ReplyKeyboardMarkup(resize_keyboard=True)
main_kb.add("📦 Перенос", "🗑 Списание")
main_kb.add("📸 Фото уборки", "🧹 Чеклист")

back_kb = ReplyKeyboardMarkup(resize_keyboard=True)
back_kb.add("⬅ Назад")

# ================= START =================
@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    reset_state(message.from_user.id)
    await message.answer("Выберите действие:", reply_markup=main_kb)

# ================= ЧЕКЛИСТ =================
@dp.message_handler(lambda m: m.text == "🧹 Чеклист")
async def checklist_start(message: types.Message):
    user_states[message.from_user.id] = {
        "state": "checklist",
        "done": []
    }
    await show_checklist(message)

async def show_checklist(message):
    state = user_states.get(message.from_user.id)
    done = state.get("done", [])

    text = "🧹 Чек-лист:\n\n"
    for item in CHECKLIST_ITEMS:
        mark = "✅" if item in done else "⬜"
        text += f"{mark} {item}\n"

    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for item in CHECKLIST_ITEMS:
        kb.add(item)
    kb.add("Готово", "⬅ Назад")

    await message.answer(text, reply_markup=kb)

@dp.message_handler(lambda m: m.text in CHECKLIST_ITEMS)
async def toggle_item(message: types.Message):
    state = user_states.get(message.from_user.id)
    if not state or state.get("state") != "checklist":
        return

    done = state["done"]

    if message.text in done:
        done.remove(message.text)
    else:
        done.append(message.text)

    await show_checklist(message)

@dp.message_handler(lambda m: m.text == "Готово")
async def checklist_finish(message: types.Message):
    state = user_states.get(message.from_user.id)
    if not state:
        return

    done = state["done"]

    # обязательные пункты
    if "Лайн чек заготовок" not in done:
        await message.answer("❗ Сделай лайн-чек")
        return

    if "Фото бара отправлено" not in done:
        await message.answer("❗ Нужно фото бара")
        return

    # отправка ВСЕГО чек-листа одним запросом
    checklist_data = {
        item: ("Выполнено" if item in done else "Не выполнено")
        for item in CHECKLIST_ITEMS
    }

    requests.post(
        SHEET_WEBHOOK_URL,
        json={
            "sheet": "Чеклист",
            "user": message.from_user.full_name,
            "checklist": checklist_data
        }
    )

    await message.answer("✅ Чек-лист сохранён", reply_markup=main_kb)
    reset_state(message.from_user.id)

# ================= ФОТО =================
@dp.message_handler(content_types=types.ContentType.PHOTO)
async def photo_handler(message: types.Message):
    state = user_states.get(message.from_user.id)

    if state and state.get("state") == "checklist":
        if "Фото бара отправлено" not in state["done"]:
            state["done"].append("Фото бара отправлено")
            await show_checklist(message)

    requests.post(
        SHEET_WEBHOOK_URL,
        json={
            "sheet": "Фото",
            "user": message.from_user.full_name,
            "text": message.photo[-1].file_id
        }
    )

    await message.answer("✅ Фото сохранено")

# ================= ЗАПУСК =================
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
