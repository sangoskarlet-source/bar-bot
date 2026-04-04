import os
import re
import requests
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils import executor

# ================= Настройки =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
SHEET_WEBHOOK_URL = os.getenv("SHEET_WEBHOOK_URL")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# ================= Клавиатуры =================
main_kb = ReplyKeyboardMarkup(resize_keyboard=True)
main_kb.add("📦 Перенос", "🗑 Списание")
main_kb.add("📸 Фото уборки", "🧹 Чеклист")
main_kb.add("🧹 Ежедневная уборка", "🌡 Журнал температур")

direction_kb = ReplyKeyboardMarkup(resize_keyboard=True)
direction_kb.add("Кухня → Бар", "Бар → Кухня", "⬅ Назад")

back_kb = ReplyKeyboardMarkup(resize_keyboard=True)
back_kb.add("⬅ Назад")

checklist_kb = ReplyKeyboardMarkup(resize_keyboard=True)
checklist_items = [
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
    "Порядок на складе",
    "Готово"
]
for item in checklist_items:
    checklist_kb.add(item)
checklist_kb.add("⬅ Назад")

temperature_kb = ReplyKeyboardMarkup(resize_keyboard=True)
temperature_kb.add("1 этаж", "2 этаж", "⬅ Назад")

floor1_kb = ReplyKeyboardMarkup(resize_keyboard=True)
floor1_items = [
    "Холодильник с водой",
    "Холодильник с вином",
    "Морозильник",
    "Холодильник в баре",
    "Холодильник с открытым вином"
]
for item in floor1_items:
    floor1_kb.add(item)
floor1_kb.add("⬅ Назад")

floor2_kb = ReplyKeyboardMarkup(resize_keyboard=True)
floor2_items = [
    "Холодильник с вином",
    "Холодильник пепси",
    "Морозильник",
    "Холодильник для фруктов",
    "Сережа",
    "Морозильный ларь"
]
for item in floor2_items:
    floor2_kb.add(item)
floor2_kb.add("⬅ Назад")

# ================= Состояния пользователей =================
user_states = {}

# ================= Отправка в Google Sheets =================
def send_to_sheet(sheet, user_id, user_name, data):
    try:
        requests.post(
            SHEET_WEBHOOK_URL,
            json={
                "sheet": sheet,
                "user_id": user_id,
                "user": user_name,
                "data": data
            },
            timeout=10
        )
    except Exception as e:
        print("Ошибка отправки:", e)

# ================= Команды =================
@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    await message.answer("Выберите действие:", reply_markup=main_kb)

@dp.message_handler(lambda m: m.text == "⬅ Назад")
async def go_back(message: types.Message):
    user_states.pop(message.from_user.id, None)
    await message.answer("Главное меню:", reply_markup=main_kb)

# ================= Перенос =================
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
    text = message.text.strip()

    number_match = re.search(r'\d+([.,]\d+)?', text)
    weight = number_match.group(0).replace(',', '.') if number_match else ""
    position = re.sub(r'\d+([.,]\d+)?', '', text).strip()

    send_to_sheet(
        "Переносы",
        message.from_user.id,
        message.from_user.full_name,
        {"Направление": direction, "Позиция": position, "Вес": weight}
    )

    await message.answer("✅ Перенос записан", reply_markup=main_kb)
    user_states.pop(message.from_user.id)

# ================= Списание =================
@dp.message_handler(lambda m: m.text == "🗑 Списание")
async def writeoff_start(message: types.Message):
    user_states[message.from_user.id] = {"state": "writeoff"}
    await message.answer("Напишите что списываем:", reply_markup=back_kb)

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "writeoff")
async def writeoff_save(message: types.Message):
    text = message.text.strip()
    number_match = re.search(r'\d+([.,]\d+)?', text)
    weight = number_match.group(0).replace(',', '.') if number_match else ""
    position = re.sub(r'\d+([.,]\d+)?', '', text).strip()

    send_to_sheet(
        "Списания",
        message.from_user.id,
        message.from_user.full_name,
        {"Позиция": position, "Вес": weight}
    )

    await message.answer("✅ Списание записано", reply_markup=main_kb)
    user_states.pop(message.from_user.id)

# ================= Чеклист =================
@dp.message_handler(lambda m: m.text == "🧹 Чеклист")
async def checklist_start(message: types.Message):
    user_states[message.from_user.id] = {"state": "checklist"}
    await message.answer("Выберите выполненный пункт:", reply_markup=checklist_kb)

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "checklist")
async def checklist_save(message: types.Message):
    item = message.text
    if item == "Готово":
        await message.answer("✅ Чеклист завершён", reply_markup=main_kb)
        user_states.pop(message.from_user.id)
        return
    if item not in checklist_items:
        return

    send_to_sheet(
        "Чеклист",
        message.from_user.id,
        message.from_user.full_name,
        {item: "Выполнено"}
    )
    await message.answer(f"✅ {item} отмечен", reply_markup=checklist_kb)

# ================= Фото уборки =================
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
    send_to_sheet(
        "Фото",
        message.from_user.id,
        message.from_user.full_name,
        {"file_id": file_id}
    )
    await message.answer("✅ Фото сохранено", reply_markup=main_kb)
    user_states.pop(message.from_user.id)

# ================= Журнал температур =================
@dp.message_handler(lambda m: m.text == "🌡 Журнал температур")
async def temperature_start(message: types.Message):
    user_states[message.from_user.id] = {"state": "floor_select"}
    await message.answer("Выберите этаж:", reply_markup=temperature_kb)

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "floor_select")
async def floor_select(message: types.Message):
    if message.text == "1 этаж":
        user_states[message.from_user.id] = {"state": "temperature", "floor": "1", "items": floor1_items.copy()}
        await message.answer("Выберите холодильник и введите температуру (например: 5):\n" + "\n".join(floor1_items), reply_markup=back_kb)
    elif message.text == "2 этаж":
        user_states[message.from_user.id] = {"state": "temperature", "floor": "2", "items": floor2_items.copy()}
        await message.answer("Выберите холодильник и введите температуру (например: 5):\n" + "\n".join(floor2_items), reply_markup=back_kb)

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "temperature")
async def temperature_save(message: types.Message):
    state = user_states[message.from_user.id]
    items = state["items"]
    text = message.text.strip()
    # Ожидаем формат "температура холодильник"
    match = re.match(r'(\d+)\s*(.*)', text)
    if not match:
        await message.answer("Неверный формат. Пример: 5 Холодильник с водой")
        return
    temp, fridge = match.groups()
    fridge = fridge.strip()
    if fridge not in items:
        await message.answer("Холодильник не найден или уже заполнен.")
        return

    sheet_name = f"Этаж {state['floor']}"
    send_to_sheet(
        sheet_name,
        message.from_user.id,
        message.from_user.full_name,
        {fridge: temp}
    )
    items.remove(fridge)
    state["items"] = items
    if items:
        await message.answer("Записано ✅\nВыберите следующий холодильник:\n" + "\n".join(items))
    else:
        await message.answer("✅ Все температуры внесены", reply_markup=main_kb)
        user_states.pop(message.from_user.id)

# ================= Запуск =================
if __name__ == "__main__":
    from aiogram import executor
    executor.start_polling(dp, skip_updates=True)
