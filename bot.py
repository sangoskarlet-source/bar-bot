import os
import requests
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
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

direction_kb = ReplyKeyboardMarkup(resize_keyboard=True)
direction_kb.add("Кухня → Бар", "Бар → Кухня")
direction_kb.add("⬅ Назад")

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
    "Порядок на складе"
]
for item in checklist_items:
    checklist_kb.add(item)
checklist_kb.add("Готово", "⬅ Назад")

floor_kb = ReplyKeyboardMarkup(resize_keyboard=True)
floor_kb.add("1 этаж", "2 этаж", "⬅ Назад")

back_kb = ReplyKeyboardMarkup(resize_keyboard=True)
back_kb.add("⬅ Назад")

user_states = {}

# ================= ОТПРАВКА В SHEETS =================
def send_to_sheet(sheet, user, user_id, data):
    try:
        requests.post(
            SHEET_WEBHOOK_URL,
            json={
                "sheet": sheet,
                "user": user,
                "user_id": user_id,
                "data": data
            },
            timeout=10
        )
    except Exception as e:
        print("Ошибка отправки:", e)

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
    user_states[message.from_user.id] = {"state": "transfer_text", "direction": message.text}
    await message.answer("Напишите что и сколько переносим (пример: Лимон 10):", reply_markup=back_kb)

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "transfer_text")
async def transfer_save(message: types.Message):
    direction = user_states[message.from_user.id]["direction"]
    text = message.text
    # Парсим позицию и вес
    import re
    number = re.search(r"\d+([.,]\d+)?", text)
    weight = number.group(0) if number else ""
    position = re.sub(r"\d+([.,]\d+)?", "", text).strip()

    send_to_sheet(
        "Переносы",
        message.from_user.full_name,
        message.from_user.id,
        {"direction": direction, "position": position, "weight": weight}
    )
    await message.answer("✅ Перенос записан", reply_markup=main_kb)
    user_states.pop(message.from_user.id)

# ================= СПИСАНИЕ =================
@dp.message_handler(lambda m: m.text == "🗑 Списание")
async def writeoff_start(message: types.Message):
    user_states[message.from_user.id] = {"state": "writeoff"}
    await message.answer("Напишите что списываем (пример: Лимон 5):", reply_markup=back_kb)

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "writeoff")
async def writeoff_save(message: types.Message):
    text = message.text
    import re
    number = re.search(r"\d+([.,]\d+)?", text)
    weight = number.group(0) if number else ""
    position = re.sub(r"\d+([.,]\d+)?", "", text).strip()

    send_to_sheet(
        "Списания",
        message.from_user.full_name,
        message.from_user.id,
        {"position": position, "weight": weight}
    )
    await message.answer("✅ Списание записано", reply_markup=main_kb)
    user_states.pop(message.from_user.id)

# ================= ЧЕКЛИСТ =================
@dp.message_handler(lambda m: m.text == "🧹 Чеклист")
async def checklist_start(message: types.Message):
    user_states[message.from_user.id] = {"state": "checklist", "completed": {}}
    await message.answer("Выберите пункт чеклиста:", reply_markup=checklist_kb)

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "checklist")
async def checklist_save(message: types.Message):
    if message.text == "Готово":
        send_to_sheet(
            "Чеклист",
            message.from_user.full_name,
            message.from_user.id,
            user_states[message.from_user.id]["completed"]
        )
        await message.answer("✅ Чеклист сохранен", reply_markup=main_kb)
        user_states.pop(message.from_user.id)
        return
    user_states[message.from_user.id]["completed"][message.text] = "Выполнено"
    await message.answer("Пункт отмечен ✅", reply_markup=checklist_kb)

# ================= ФОТО =================
@dp.message_handler(lambda m: m.text == "📸 Фото уборки")
async def photo_start(message: types.Message):
    user_states[message.from_user.id] = {"state": "photo"}
    await message.answer("Отправьте фото:", reply_markup=back_kb)

@dp.message_handler(content_types=types.ContentType.PHOTO)
async def photo_save(message: types.Message):
    state = user_states.get(message.from_user.id, {}).get("state")
    if state != "photo":
        return
    file_id = message.photo[-1].file_id
    send_to_sheet(
        "Фото",
        message.from_user.full_name,
        message.from_user.id,
        {"file_id": file_id}
    )
    await message.answer("✅ Фото сохранено", reply_markup=main_kb)
    user_states.pop(message.from_user.id)

# ================= ЖУРНАЛ ТЕМПЕРАТУР =================
fridges = {
    "1 этаж": ["Холодильник с водой", "Холодильник с вином", "Морозильник", "Холодильник в баре", "Холодильник с открытым вином"],
    "2 этаж": ["Холодильник с вином", "Холодильник пепси", "Морозильник", "Холодильник для фруктов", "Сережа", "Морозильный ларь"]
}

@dp.message_handler(lambda m: m.text == "🌡 Журнал температур")
async def temp_start(message: types.Message):
    user_states[message.from_user.id] = {"state": "temp_floor"}
    await message.answer("Выберите этаж:", reply_markup=floor_kb)

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "temp_floor")
async def temp_floor(message: types.Message):
    if message.text not in fridges:
        return
    user_states[message.from_user.id] = {"state": "temp_input", "floor": message.text}
    fridge_list = "\n".join(fridges[message.text])
    await message.answer(f"Введите температуру и укажите холодильник:\n{fridge_list}\nПример: 5 Холодильник с водой", reply_markup=back_kb)

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "temp_input")
async def temp_save(message: types.Message):
    floor = user_states[message.from_user.id]["floor"]
    text = message.text
    parts = text.split(" ", 1)
    if len(parts) != 2:
        await message.answer("Ошибка формата. Пример: 5 Холодильник с водой", reply_markup=back_kb)
        return
    temp, fridge = parts
    send_to_sheet(
        f"{floor}",
        message.from_user.full_name,
        message.from_user.id,
        {fridge: temp}
    )
    await message.answer(f"✅ Температура {temp} записана для {fridge}", reply_markup=back_kb)

# ================= НАЗАД =================
@dp.message_handler(lambda m: m.text == "⬅ Назад")
async def go_back(message: types.Message):
    user_states.pop(message.from_user.id, None)
    await message.answer("Главное меню:", reply_markup=main_kb)

# ================= ЗАПУСК БОТА =================
if __name__ == "__main__":
    from aiogram import executor
    executor.start_polling(dp, skip_updates=True)
