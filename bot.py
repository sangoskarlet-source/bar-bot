import os
import requests
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, ReplyKeyboardRemove
from aiogram.utils import executor

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

checklist_points = [
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

checklist_kb = ReplyKeyboardMarkup(resize_keyboard=True)
for p in checklist_points:
    checklist_kb.add(p)
checklist_kb.add("Готово", "⬅ Назад")

back_kb = ReplyKeyboardMarkup(resize_keyboard=True)
back_kb.add("⬅ Назад")

# ================= Журнал температур =================
fridges_by_floor = {
    "1 этаж": ["Холодильник с водой", "Холодильник с вином", "Морозильник", "Холодильник в баре", "Холодильник с открытым вином"],
    "2 этаж": ["Холодильник с вином", "Холодильник пепси", "Морозильник", "Холодильник для фруктов", "Сережа", "Морозильный ларь"]
}

# ================= СОСТОЯНИЯ ПОЛЬЗОВАТЕЛЕЙ =================
user_states = {}

# ================= ОТПРАВКА В SHEETS =================
def send_to_sheet(sheet, user, text, extra=""):
    try:
        requests.post(
            SHEET_WEBHOOK_URL,
            json={"sheet": sheet, "user": user, "text": text, "extra": extra},
            timeout=10
        )
    except Exception as e:
        print("Ошибка отправки:", e)

# ================= СТАРТ =================
@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    await message.answer("Выберите действие:", reply_markup=main_kb)

# ================= НАЗАД =================
@dp.message_handler(lambda m: m.text == "⬅ Назад")
async def go_back(message: types.Message):
    user_states.pop(message.from_user.id, None)
    await message.answer("Главное меню:", reply_markup=main_kb)

# ================= ПЕРЕНОС =================
@dp.message_handler(lambda m: m.text == "📦 Перенос")
async def transfer_start(message: types.Message):
    user_states[message.from_user.id] = {"state": "transfer_direction"}
    await message.answer("Выберите направление:", reply_markup=direction_kb)

@dp.message_handler(lambda m: m.text in ["Кухня → Бар", "Бар → Кухня"])
async def transfer_direction(message: types.Message):
    user_states[message.from_user.id] = {"state": "transfer_text", "direction": message.text}
    await message.answer("Напишите что и сколько переносим:", reply_markup=back_kb)

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "transfer_text")
async def transfer_save(message: types.Message):
    direction = user_states[message.from_user.id]["direction"]
    send_to_sheet("Переносы", message.from_user.full_name, message.text, direction)
    await message.answer("✅ Перенос записан", reply_markup=main_kb)
    user_states.pop(message.from_user.id)

# ================= СПИСАНИЕ =================
@dp.message_handler(lambda m: m.text == "🗑 Списание")
async def writeoff_start(message: types.Message):
    user_states[message.from_user.id] = {"state": "writeoff"}
    await message.answer("Напишите что списываем:", reply_markup=back_kb)

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "writeoff")
async def writeoff_save(message: types.Message):
    send_to_sheet("Списания", message.from_user.full_name, message.text)
    await message.answer("✅ Списание записано", reply_markup=main_kb)
    user_states.pop(message.from_user.id)

# ================= ЧЕКЛИСТ =================
@dp.message_handler(lambda m: m.text == "🧹 Чеклист")
async def checklist_start(message: types.Message):
    user_states[message.from_user.id] = {"state": "checklist", "results": {}}
    await message.answer("Выберите пункт чеклиста:", reply_markup=checklist_kb)

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "checklist")
async def checklist_handler(message: types.Message):
    state = user_states[message.from_user.id]
    if message.text == "Готово":
        send_to_sheet("Чеклист", message.from_user.full_name, state["results"])
        await message.answer("✅ Чеклист сохранён", reply_markup=main_kb)
        user_states.pop(message.from_user.id)
    elif message.text in checklist_points:
        state["results"][message.text] = "Выполнено"
        await message.answer(f"{message.text} отмечено ✅", reply_markup=checklist_kb)

# ================= ЖУРНАЛ ТЕМПЕРАТУР =================
@dp.message_handler(lambda m: m.text == "🌡 Журнал температур")
async def temp_start(message: types.Message):
    floor_kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for f in fridges_by_floor.keys():
        floor_kb.add(f)
    floor_kb.add("⬅ Назад")
    user_states[message.from_user.id] = {"state": "choose_floor"}
    await message.answer("Выберите этаж:", reply_markup=floor_kb)

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "choose_floor")
async def choose_floor(message: types.Message):
    floor = message.text
    if floor not in fridges_by_floor:
        await message.answer("Выберите этаж из списка", reply_markup=back_kb)
        return
    user_states[message.from_user.id] = {
        "state": "enter_temperature",
        "floor": floor,
        "available_fridges": fridges_by_floor[floor].copy()
    }
    await show_fridge_menu(message, message.from_user.id)

async def show_fridge_menu(message, user_id):
    user_data = user_states[user_id]
    available = user_data["available_fridges"]
    if not available:
        await message.answer("Все холодильники заполнены ✅", reply_markup=main_kb)
        user_states.pop(user_id)
        return
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for fridge in available:
        kb.add(fridge)
    kb.add("⬅ Назад")
    await message.answer("Выберите холодильник:", reply_markup=kb)

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "enter_temperature")
async def enter_temperature(message: types.Message):
    user_data = user_states[message.from_user.id]
    fridge = message.text
    if fridge not in user_data["available_fridges"]:
        await message.answer("Выберите холодильник из списка", reply_markup=back_kb)
        return
    await message.answer(f"Введите температуру для {fridge}:", reply_markup=ReplyKeyboardRemove())
    user_data["current_fridge"] = fridge
    user_data["state"] = "waiting_temperature"

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "waiting_temperature")
async def save_temperature(message: types.Message):
    user_data = user_states[message.from_user.id]
    temp = message.text
    fridge = user_data["current_fridge"]
    floor = user_data["floor"]

    # Отправка в Google Sheets
    send_to_sheet(floor, message.from_user.full_name, f"{fridge}: {temp}")

    # Удаляем холодильник из доступных
    user_data["available_fridges"].remove(fridge)
    user_data["state"] = "enter_temperature"
    await message.answer(f"✅ Температура {fridge} сохранена", reply_markup=main_kb)
    # Показываем обновлённое меню, если остались
    if user_data["available_fridges"]:
        await show_fridge_menu(message, message.from_user.id)
    else:
        user_states.pop(message.from_user.id)

# ================= ЕЖЕДНЕВНАЯ УБОРКА =================
@dp.message_handler(lambda m: m.text == "🧹 Ежедневная уборка")
async def daily_cleaning(message: types.Message):
    user_states[message.from_user.id] = {"state": "daily_cleaning"}
    await message.answer("Отправьте фото выполнения уборки:", reply_markup=back_kb)

@dp.message_handler(content_types=types.ContentType.PHOTO)
async def save_photo(message: types.Message):
    state = user_states.get(message.from_user.id, {}).get("state")
    if not state:
        return
    file_id = message.photo[-1].file_id
    send_to_sheet("Фото", str(message.from_user.id), file_id)
    await message.answer("✅ Фото сохранено", reply_markup=main_kb)
    user_states.pop(message.from_user.id)

# ================= WEBHOOK =================
async def on_startup(dp):
    # Если нужен вебхук
    pass

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
