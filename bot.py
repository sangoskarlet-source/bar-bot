import os
import requests
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils import executor
from datetime import datetime

# ================= Настройки =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
SHEET_WEBHOOK_URL = os.getenv("SHEET_WEBHOOK_URL")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# ================= КЛАВИАТУРЫ =================
main_kb = ReplyKeyboardMarkup(resize_keyboard=True)
main_kb.add("📦 Перенос")
main_kb.add("🗑 Списание")
main_kb.add("📸 Фото уборки")
main_kb.add("🧹 Чеклист")
main_kb.add("🌡 Журнал температур")
main_kb.add("🧹 Ежедневная уборка")

direction_kb = ReplyKeyboardMarkup(resize_keyboard=True)
direction_kb.add("Кухня → Бар", "Бар → Кухня")
direction_kb.add("⬅ Назад")

back_kb = ReplyKeyboardMarkup(resize_keyboard=True)
back_kb.add("⬅ Назад")

checklist_main_kb = ReplyKeyboardMarkup(resize_keyboard=True)
checklist_main_kb.add("Лайн чек заготовок", "Закрытие смены", "⬅ Назад")

checklist_close_kb = ReplyKeyboardMarkup(resize_keyboard=True)
checklist_close_kb.add(
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
    "Порядок на складе",
    "Готово",
    "⬅ Назад"
)

temperature_main_kb = ReplyKeyboardMarkup(resize_keyboard=True)
temperature_main_kb.add("1 этаж", "2 этаж", "⬅ Назад")

floor1_kb = ReplyKeyboardMarkup(resize_keyboard=True)
floor1_kb.add(
    "Холодильник с водой",
    "Холодильник с вином",
    "Морозильник",
    "Холодильник в баре",
    "Холодильник с открытым вином",
    "⬅ Назад"
)

floor2_kb = ReplyKeyboardMarkup(resize_keyboard=True)
floor2_kb.add(
    "Холодильник с вином",
    "Холодильник Пепси",
    "Морозильник",
    "Холодильник для фруктов",
    "Сережа",
    "Морозильный ларь",
    "⬅ Назад"
)

user_states = {}
temp_cache = {}  # Для временного хранения ввода температуры

# ================= ОТПРАВКА В SHEETS =================
def send_to_sheet(sheet, data: dict):
    try:
        requests.post(SHEET_WEBHOOK_URL, json={**data, "sheet": sheet}, timeout=10)
    except Exception as e:
        print("Ошибка отправки:", e)

# ================= НАЧАЛО =================
@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    await message.answer("Выберите действие:", reply_markup=main_kb)

# ================= НАЗАД =================
@dp.message_handler(lambda m: m.text == "⬅ Назад")
async def go_back(message: types.Message):
    user_states.pop(message.from_user.id, None)
    temp_cache.pop(message.from_user.id, None)
    await message.answer("Главное меню:", reply_markup=main_kb)

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
    lines = (message.text or "").split("\n")
    for line in lines:
        line = line.strip()
        if not line:
            continue
        number_match = line.replace(",", ".").split()
        weight = ""
        position = line
        for word in number_match:
            if word.replace(".", "").isdigit():
                weight = word
                position = position.replace(word, "").strip()
        send_to_sheet("Переносы", {
            "ID": message.from_user.id,
            "Дата": datetime.now().strftime("%d.%m.%Y %H:%M"),
            "Сотрудник": message.from_user.full_name,
            "Направление": direction,
            "Позиция": position,
            "Вес": weight
        })
    await message.answer("✅ Перенос записан", reply_markup=main_kb)
    user_states.pop(message.from_user.id)

# ================= СПИСАНИЕ =================
@dp.message_handler(lambda m: m.text == "🗑 Списание")
async def writeoff_start(message: types.Message):
    user_states[message.from_user.id] = {"state": "writeoff"}
    await message.answer("Напишите что списываем:", reply_markup=back_kb)

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "writeoff")
async def writeoff_save(message: types.Message):
    lines = (message.text or "").split("\n")
    for line in lines:
        line = line.strip()
        if not line:
            continue
        number_match = line.replace(",", ".").split()
        weight = ""
        position = line
        for word in number_match:
            if word.replace(".", "").isdigit():
                weight = word
                position = position.replace(word, "").strip()
        send_to_sheet("Списания", {
            "ID": message.from_user.id,
            "Дата": datetime.now().strftime("%d.%m.%Y %H:%M"),
            "Сотрудник": message.from_user.full_name,
            "Позиция": position,
            "Вес": weight
        })
    await message.answer("✅ Списание записано", reply_markup=main_kb)
    user_states.pop(message.from_user.id)

# ================= ФОТО =================
@dp.message_handler(lambda m: m.text == "📸 Фото уборки")
async def daily_cleaning_photo(message: types.Message):
    user_states[message.from_user.id] = {"state": "photo"}
    await message.answer("Отправьте фото:", reply_markup=back_kb)

@dp.message_handler(content_types=types.ContentType.PHOTO)
async def save_photo(message: types.Message):
    state = user_states.get(message.from_user.id, {}).get("state")
    if state not in ["photo", "daily_cleaning"]:
        return
    file_id = message.photo[-1].file_id
    send_to_sheet("Фото", {
        "ID": message.from_user.id,
        "Дата": datetime.now().strftime("%d.%m.%Y %H:%M"),
        "Сотрудник": message.from_user.full_name,
        "Файл": file_id
    })
    await message.answer("✅ Фото сохранено", reply_markup=main_kb)
    user_states.pop(message.from_user.id)

# ================= ЧЕКЛИСТ =================
@dp.message_handler(lambda m: m.text == "🧹 Чеклист")
async def checklist_start(message: types.Message):
    user_states[message.from_user.id] = {"state": "checklist"}
    await message.answer("Выберите:", reply_markup=checklist_main_kb)

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "checklist")
async def checklist_handler(message: types.Message):
    text = message.text
    if text == "Лайн чек заготовок":
        send_to_sheet("Чеклист", {
            "Дата": datetime.now().strftime("%d.%m.%Y %H:%M"),
            "Сотрудник": message.from_user.full_name,
            "Лайн чек заготовок": "Выполнено"
        })
        await message.answer("✅ Лайн чек заготовок отмечен", reply_markup=checklist_main_kb)
    elif text == "Закрытие смены":
        user_states[message.from_user.id]["state"] = "checklist_close"
        await message.answer("Выберите пункт:", reply_markup=checklist_close_kb)
    elif text == "⬅ Назад":
        await go_back(message)

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "checklist_close")
async def checklist_close(message: types.Message):
    text = message.text
    if text == "Готово":
        await message.answer("✅ Закрытие смены завершено", reply_markup=main_kb)
        user_states.pop(message.from_user.id)
        return
    if text in checklist_close_kb.keyboard[0]:
        send_to_sheet("Чеклист", {
            "Дата": datetime.now().strftime("%d.%m.%Y %H:%M"),
            "Сотрудник": message.from_user.full_name,
            text: "Выполнено"
        })
        await message.answer(f"✅ {text} отмечено", reply_markup=checklist_close_kb)

# ================= ЖУРНАЛ ТЕМПЕРАТУР =================
@dp.message_handler(lambda m: m.text == "🌡 Журнал температур")
async def temp_main(message: types.Message):
    user_states[message.from_user.id] = {"state": "temp_main"}
    await message.answer("Выберите этаж:", reply_markup=temperature_main_kb)

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "temp_main")
async def temp_floor(message: types.Message):
    if message.text == "1 этаж":
        user_states[message.from_user.id]["state"] = "temp_floor1"
        await message.answer("Выберите холодильник:", reply_markup=floor1_kb)
    elif message.text == "2 этаж":
        user_states[message.from_user.id]["state"] = "temp_floor2"
        await message.answer("Выберите холодильник:", reply_markup=floor2_kb)
    elif message.text == "⬅ Назад":
        await go_back(message)

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") in ["temp_floor1", "temp_floor2"])
async def temp_select(message: types.Message):
    user_states[message.from_user.id]["selected_fridge"] = message.text
    await message.answer("Введите температуру:")

    user_states[message.from_user.id]["state"] = "temp_input"

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "temp_input")
async def temp_input(message: types.Message):
    fridge = user_states[message.from_user.id]["selected_fridge"]
    temp = message.text
    floor = "1 этаж" if user_states[message.from_user.id]["state"] == "temp_input" else "2 этаж"
    send_to_sheet(floor, {
        "Дата": datetime.now().strftime("%d.%m.%Y %H:%M"),
        "Сотрудник": message.from_user.full_name,
        fridge: temp
    })
    await message.answer(f"✅ {fridge}: {temp}", reply_markup=main_kb)
    user_states.pop(message.from_user.id)

# ================= WEBHOOK =================
async def on_startup(dp):
    pass  # Если нужен вебхук, вставь код настройки здесь

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
