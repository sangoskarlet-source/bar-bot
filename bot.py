import os
import requests
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup
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
direction_kb.add("Кухня → Бар", "Бар → Кухня")
direction_kb.add("⬅ Назад")

checklist_main_kb = ReplyKeyboardMarkup(resize_keyboard=True)
checklist_main_kb.add("Лайн чек заготовок", "Закрытие смены")
checklist_main_kb.add("⬅ Назад")

back_kb = ReplyKeyboardMarkup(resize_keyboard=True)
back_kb.add("⬅ Назад")

temperature_floor_kb = ReplyKeyboardMarkup(resize_keyboard=True)
temperature_floor_kb.add("1 этаж", "2 этаж")
temperature_floor_kb.add("⬅ Назад")

# ================= Хранилище состояний =================
user_states = {}
temperature_temp = {}  # временное хранение температуры для конкретного холодильника

# ================= Функция отправки данных в Sheets =================
def send_to_sheet(sheet, user_id, user_name, extra_data):
    payload = {
        "sheet": sheet,
        "ID": user_id,
        "Дата": datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
        "Сотрудник": user_name
    }
    payload.update(extra_data)
    try:
        r = requests.post(SHEET_WEBHOOK_URL, json=payload, timeout=10)
        print("Отправлено:", r.status_code, r.text)
    except Exception as e:
        print("Ошибка отправки:", e)

# ================= Главный старт =================
@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    await message.answer("Выберите действие:", reply_markup=main_kb)

# ================= Назад =================
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
    text = message.text

    # Разделяем текст и числа
    import re
    number_match = re.findall(r'\d+([.,]\d+)?', text)
    weight = number_match[0] if number_match else ""
    position = re.sub(r'\d+([.,]\d+)?', '', text).strip()

    send_to_sheet("Переносы", message.from_user.id, message.from_user.full_name,
                  {"Направление": direction, "Позиция": position, "Вес": weight})

    await message.answer("✅ Перенос записан", reply_markup=main_kb)
    user_states.pop(message.from_user.id)

# ================= Списание =================
@dp.message_handler(lambda m: m.text == "🗑 Списание")
async def writeoff_start(message: types.Message):
    user_states[message.from_user.id] = {"state": "writeoff"}
    await message.answer("Напишите что списываем:", reply_markup=back_kb)

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "writeoff")
async def writeoff_save(message: types.Message):
    # Разделяем текст и числа
    import re
    number_match = re.findall(r'\d+([.,]\d+)?', message.text)
    weight = number_match[0] if number_match else ""
    position = re.sub(r'\d+([.,]\d+)?', '', message.text).strip()

    send_to_sheet("Списания", message.from_user.id, message.from_user.full_name,
                  {"Позиция": position, "Вес": weight})

    await message.answer("✅ Списание записано", reply_markup=main_kb)
    user_states.pop(message.from_user.id)

# ================= Фото уборки =================
@dp.message_handler(lambda m: m.text == "📸 Фото уборки")
async def photo_start(message: types.Message):
    user_states[message.from_user.id] = {"state": "photo"}
    await message.answer("Отправьте фото:", reply_markup=back_kb)

@dp.message_handler(content_types=types.ContentType.PHOTO)
async def save_photo(message: types.Message):
    state = user_states.get(message.from_user.id, {}).get("state")
    if state != "photo":
        return
    file_id = message.photo[-1].file_id
    send_to_sheet("Фото", message.from_user.id, message.from_user.full_name, {"Файл": file_id})
    await message.answer("✅ Фото сохранено", reply_markup=main_kb)
    user_states.pop(message.from_user.id)

# ================= Чеклист =================
checklist_items = {
    "Лайн чек заготовок": ["Выполнено"],
    "Закрытие смены": [
        "Фото бара отправлено",
        "Все крышки закрыты",
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
}

@dp.message_handler(lambda m: m.text == "🧹 Чеклист")
async def checklist_start(message: types.Message):
    user_states[message.from_user.id] = {"state": "checklist"}
    await message.answer("Выберите пункт чеклиста:", reply_markup=checklist_main_kb)

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "checklist")
async def checklist_handler(message: types.Message):
    text = message.text
    if text in checklist_items:
        for item in checklist_items[text]:
            send_to_sheet("Чеклист", message.from_user.id, message.from_user.full_name,
                          {item: "✅"})
        await message.answer("✅ Чеклист заполнен", reply_markup=main_kb)
    elif text == "⬅ Назад":
        await go_back(message)

# ================= Журнал температур =================
floor_items = {
    "1 этаж": ["Холодильник с водой", "Холодильник с вином", "Морозильник", "Холодильник колодец", "Холодильник с открытым вином"],
    "2 этаж": ["Холодильник с вином", "Холодильник Пепси", "Морозильник", "Холодильник для фруктов", "Сережа", "Морозильный ларь"]
}

@dp.message_handler(lambda m: m.text == "🌡 Журнал температур")
async def temperature_start(message: types.Message):
    user_states[message.from_user.id] = {"state": "temperature_floor"}
    await message.answer("Выберите этаж:", reply_markup=temperature_floor_kb)

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "temperature_floor")
async def temperature_floor(message: types.Message):
    floor = message.text
    if floor in floor_items:
        user_states[message.from_user.id] = {"state": "temperature_select", "floor": floor, "items": floor_items[floor].copy()}
        items_text = "\n".join([f"{i+1}. {name}" for i, name in enumerate(floor_items[floor])])
        await message.answer(f"Выберите холодильник и напишите температуру:\n{items_text}", reply_markup=back_kb)

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "temperature_select")
async def temperature_input(message: types.Message):
    state = user_states[message.from_user.id]
    floor = state["floor"]
    items = state["items"]

    # Парсим температуру и выбираем первый холодильник
    try:
        temp = float(message.text)
    except:
        await message.answer("Введите корректное число температуры!")
        return

    fridge_name = items.pop(0)  # берем первый из списка
    send_to_sheet(floor, message.from_user.id, message.from_user.full_name, {fridge_name: temp})

    if items:
        state["items"] = items
        items_text = "\n".join([f"{i+1}. {name}" for i, name in enumerate(items)])
        await message.answer(f"Выберите следующий холодильник:\n{items_text}", reply_markup=back_kb)
    else:
        await message.answer("✅ Все температуры внесены", reply_markup=main_kb)
        user_states.pop(message.from_user.id)

# ================= Запуск =================
if __name__ == "__main__":
    from aiogram import executor
    executor.start_polling(dp, skip_updates=True)
