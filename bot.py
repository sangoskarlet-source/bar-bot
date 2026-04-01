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

# ================= STATES =================
user_states = {}
def reset_state(user_id):
    user_states.pop(user_id, None)

# ================= CHECKLIST =================
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

# ================= KEYBOARDS =================
main_kb = ReplyKeyboardMarkup(resize_keyboard=True)
main_kb.add("📦 Перенос", "🗑 Списание")
main_kb.add("📸 Фото уборки", "🧹 Чеклист")
main_kb.add("🧹 Ежедневная уборка")

direction_kb = ReplyKeyboardMarkup(resize_keyboard=True)
direction_kb.add("Кухня → Бар", "Бар → Кухня")

back_kb = ReplyKeyboardMarkup(resize_keyboard=True)
back_kb.add("⬅ Назад")

# ================= SEND TO SHEETS =================
def send_to_sheet(sheet, user, text, extra=""):
    try:
        requests.post(
            SHEET_WEBHOOK_URL,
            json={"sheet": sheet, "user": user, "text": text, "extra": extra},
            timeout=10
        )
    except Exception as e:
        print("Ошибка отправки:", e)

# ================= HANDLERS =================
@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    reset_state(message.from_user.id)
    await message.answer("Выберите действие:", reply_markup=main_kb)

@dp.message_handler(lambda m: m.text == "⬅ Назад")
async def go_back(message: types.Message):
    reset_state(message.from_user.id)
    await message.answer("Главное меню:", reply_markup=main_kb)

# ===== ПЕРЕНОСЫ =====
@dp.message_handler(lambda m: m.text == "📦 Перенос")
async def transfer_start(message: types.Message):
    reset_state(message.from_user.id)
    user_states[message.from_user.id] = {"state": "transfer_direction"}
    await message.answer("Выберите направление:", reply_markup=direction_kb)

@dp.message_handler(lambda m: m.text in ["Кухня → Бар", "Бар → Кухня"]
                   and user_states.get(m.from_user.id, {}).get("state") == "transfer_direction")
async def transfer_direction(message: types.Message):
    user_states[message.from_user.id] = {"state": "transfer_text", "direction": message.text}
    await message.answer("Напишите что и сколько переносим:", reply_markup=back_kb)

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "transfer_text")
async def transfer_save(message: types.Message):
    direction = user_states[message.from_user.id]["direction"]
    send_to_sheet("Переносы", message.from_user.full_name, message.text, direction)
    await message.answer("✅ Перенос записан", reply_markup=main_kb)
    reset_state(message.from_user.id)

# ===== СПИСАНИЯ =====
@dp.message_handler(lambda m: m.text == "🗑 Списание")
async def writeoff_start(message: types.Message):
    reset_state(message.from_user.id)
    user_states[message.from_user.id] = {"state": "writeoff"}
    await message.answer("Напишите что списываем:", reply_markup=back_kb)

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "writeoff")
async def writeoff_save(message: types.Message):
    send_to_sheet("Списания", message.from_user.full_name, message.text)
    await message.answer("✅ Списание записано", reply_markup=main_kb)
    reset_state(message.from_user.id)

# ===== ФОТО =====
@dp.message_handler(content_types=types.ContentType.PHOTO)
async def save_photo(message: types.Message):
    state = user_states.get(message.from_user.id, {}).get("state")
    file_id = message.photo[-1].file_id
    send_to_sheet("Фото", str(message.from_user.id), file_id)

    # Для чек-листа фото автоматически закрывает пункт
    if state == "checklist":
        if "Фото бара отправлено" not in user_states[message.from_user.id]["done"]:
            user_states[message.from_user.id]["done"].append("Фото бара отправлено")
            await show_checklist(message)
        else:
            await message.answer("✅ Фото сохранено", reply_markup=main_kb)
    else:
        await message.answer("✅ Фото сохранено", reply_markup=main_kb)

# ===== ЧЕК-ЛИСТ =====
@dp.message_handler(lambda m: m.text == "🧹 Чеклист")
async def checklist_start(message: types.Message):
    reset_state(message.from_user.id)
    user_states[message.from_user.id] = {"state": "checklist", "done": []}
    await show_checklist(message)

async def show_checklist(message):
    state = user_states.get(message.from_user.id)
    if not state: return
    done = state.get("done", [])
    text = "🧹 Чек-лист смены:\n\n🔹 Лайн чек:\n"
    mark = "✅" if "Лайн чек заготовок" in done else "⬜"
    text += f"{mark} Лайн чек заготовок\n\n🔻 Закрытие смены:\n"
    for item in CHECKLIST_ITEMS[1:]:
        mark = "✅" if item in done else "⬜"
        text += f"{mark} {item}\n"

    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for item in CHECKLIST_ITEMS: kb.add(item)
    kb.add("Готово"); kb.add("⬅ Назад")
    await message.answer(text, reply_markup=kb)

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "checklist"
                   and (m.text in CHECKLIST_ITEMS or m.text == "Готово"))
async def checklist_process(message: types.Message):
    done = user_states[message.from_user.id]["done"]
    if message.text == "Готово":
        if "Лайн чек заготовок" not in done or "Фото бара отправлено" not in done:
            await message.answer("❗ Необходимо выполнить все обязательные пункты!")
            return
        for item in CHECKLIST_ITEMS:
            send_to_sheet("Чеклист", message.from_user.full_name, item, "Выполнено" if item in done else "Не выполнено")
        await message.answer("✅ Чек-лист сохранён", reply_markup=main_kb)
        reset_state(message.from_user.id)
        return

    # Отметка/снятие отметки
    if message.text in done:
        done.remove(message.text)
    else:
        done.append(message.text)
    await show_checklist(message)

# ===== ЕЖЕДНЕВНАЯ УБОРКА =====
@dp.message_handler(lambda m: m.text == "🧹 Ежедневная уборка")
async def daily_cleaning(message: types.Message):
    reset_state(message.from_user.id)
    user_states[message.from_user.id] = {"state": "daily_cleaning"}
    await message.answer("Отправьте фото выполнения уборки:", reply_markup=back_kb)

# ===== WEBHOOK =====
async def on_startup(dp):
    await bot.set_webhook(WEBHOOK_URL)

if __name__ == "__main__":
    executor.start_webhook(dispatcher=dp, webhook_path="", on_startup=on_startup, skip_updates=True,
                           host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
