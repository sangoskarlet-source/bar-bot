import os
import re
import asyncio
import aiohttp
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from datetime import datetime

# ================= Настройки =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
SHEET_WEBHOOK_URL = os.getenv("SHEET_WEBHOOK_URL")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# ================= КЛАВИАТУРЫ =================

def get_main_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add("📦 Перенос", "🗑 Списание")
    kb.add("📸 Фото уборки", "🧹 Чеклист")
    kb.add("🌡 Журнал температур", "🧹 Ежедневная уборка")
    return kb

direction_kb = types.ReplyKeyboardMarkup(resize_keyboard=True).add("Кухня → Бар", "Бар → Кухня", "⬅ Назад")

checklist_kb = types.ReplyKeyboardMarkup(resize_keyboard=True).add("Лайн чек заготовок", "Закрытие смены", "⬅ Назад")

temp_floor_kb = types.ReplyKeyboardMarkup(resize_keyboard=True).add("1 этаж", "2 этаж", "⬅ Назад")

fridges = {
    "1 этаж": ["Холодильник с водой", "Холодильник с вином", "Морозильник", "Холодильник в баре", "Холодильник с открытым вином"],
    "2 этаж": ["Холодильник с вином", "Холодильник Пепси", "Морозильник", "Холодильник для фруктов", "Сережа", "Морозильный ларь"]
}

user_states = {}  
temp_pending = {} 

# ================= ФУНКЦИИ ОТПРАВКИ (АСИНХРОННО) =================

async def send_to_sheet_async(payload):
    """Асинхронная отправка данных в Google Sheets"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(SHEET_WEBHOOK_URL, json=payload, timeout=15) as resp:
                return await resp.text()
    except Exception as e:
        print(f"Ошибка отправки в таблицу: {e}")

# ================= ОБРАБОТКА КОМАНД =================

@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    await message.answer("Система бартендера готова. Выберите действие:", reply_markup=get_main_kb())

@dp.message_handler(lambda m: m.text == "⬅ Назад")
async def go_back(message: types.Message):
    user_states.pop(message.from_user.id, None)
    temp_pending.pop(message.from_user.id, None)
    await message.answer("Главное меню:", reply_markup=get_main_kb())

# ---------- ПЕРЕНОС ----------
@dp.message_handler(lambda m: m.text == "📦 Перенос")
async def transfer_start(message: types.Message):
    user_states[message.from_user.id] = {"state": "transfer_direction"}
    await message.answer("Выберите направление:", reply_markup=direction_kb)

@dp.message_handler(lambda m: m.text in ["Кухня → Бар", "Бар → Кухня"])
async def transfer_direction(message: types.Message):
    user_states[message.from_user.id] = {"state": "transfer_text", "direction": message.text}
    await message.answer(f"Направление: {message.text}\nНапишите что и сколько (напр: Молоко 5, Сироп 2):", 
                         reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("⬅ Назад"))

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "transfer_text")
async def transfer_save(message: types.Message):
    data = user_states.get(message.from_user.id)
    direction = data["direction"]
    text = message.text.strip()
    
    # Парсим строки
    lines = text.split("\n")
    for line in lines:
        if not line: continue
        weight_match = re.search(r'(\d+[.,]?\d*)', line)
        weight = weight_match.group(1) if weight_match else "?"
        position = re.sub(r'(\d+[.,]?\d*)', '', line).strip()
        
        payload = {
            "sheet": "Переносы",
            "user": message.from_user.full_name,
            "text": position,
            "extra": f"{direction} | Кол-во: {weight}"
        }
        await send_to_sheet_async(payload)

    await message.answer("✅ Перенос успешно записан", reply_markup=get_main_kb())
    user_states.pop(message.from_user.id, None)

# ---------- СПИСАНИЕ ----------
@dp.message_handler(lambda m: m.text == "🗑 Списание")
async def writeoff_start(message: types.Message):
    user_states[message.from_user.id] = {"state": "writeoff"}
    await message.answer("Напишите что и сколько списываем:", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("⬅ Назад"))

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "writeoff")
async def writeoff_save(message: types.Message):
    text = message.text.strip()
    weight_match = re.search(r'(\d+[.,]?\d*)', text)
    weight = weight_match.group(1) if weight_match else "?"
    position = re.sub(r'(\d+[.,]?\d*)', '', text).strip()
    
    await send_to_sheet_async({
        "sheet": "Списания",
        "user": message.from_user.full_name,
        "text": position,
        "extra": weight
    })
    await message.answer("✅ Списание записано", reply_markup=get_main_kb())
    user_states.pop(message.from_user.id, None)

# ---------- ЖУРНАЛ ТЕМПЕРАТУР ----------
@dp.message_handler(lambda m: m.text == "🌡 Журнал температур")
async def temp_start(message: types.Message):
    user_states[message.from_user.id] = {"state": "temp_floor"}
    await message.answer("Выберите этаж:", reply_markup=temp_floor_kb)

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "temp_floor")
async def temp_choose_floor(message: types.Message):
    floor = message.text
    if floor in ["1 этаж", "2 этаж"]:
        user_states[message.from_user.id] = {"state": "temp_fridge", "floor": floor}
        temp_pending[message.from_user.id] = fridges[floor].copy()
        
        # Клавиатура с холодильниками
        fridge_kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        for f in temp_pending[message.from_user.id]:
            fridge_kb.insert(f)
        fridge_kb.add("⬅ Назад")
        await message.answer("Выберите холодильник:", reply_markup=fridge_kb)

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "temp_fridge")
async def temp_input(message: types.Message):
    user_id = message.from_user.id
    fridge_choice = message.text
    
    if fridge_choice not in temp_pending.get(user_id, []):
        await message.answer("Пожалуйста, выберите холодильник из списка на кнопках.")
        return

    user_states[user_id]["state"] = "temp_value"
    user_states[user_id]["fridge_choice"] = fridge_choice
    await message.answer(f"Введите температуру для '{fridge_choice}':", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("⬅ Назад"))

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "temp_value")
async def temp_save(message: types.Message):
    user_id = message.from_user.id
    temp_val = message.text
    data = user_states.get(user_id)
    
    # Отправка
    await send_to_sheet_async({
        "sheet": "Температуры",
        "user": message.from_user.full_name,
        "date": datetime.now().strftime("%d.%m.%Y %H:%M"),
        "fridge": data["fridge_choice"],
        "temp": temp_val
    })

    # Удаляем из списка оставшихся
    if user_id in temp_pending and data["fridge_choice"] in temp_pending[user_id]:
        temp_pending[user_id].remove(data["fridge_choice"])

    if temp_pending.get(user_id):
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        for f in temp_pending[user_id]:
            kb.insert(f)
        kb.add("⬅ Назад")
        user_states[user_id]["state"] = "temp_fridge"
        await message.answer(f"Записано: {temp_val}°C. Следующий холодильник:", reply_markup=kb)
    else:
        user_states.pop(user_id, None)
        temp_pending.pop(user_id, None)
        await message.answer("✅ Все температуры на этаже внесены!", reply_markup=get_main_kb())

# ---------- ФОТО (Заглушка) ----------
@dp.message_handler(content_types=['photo'])
async def handle_photo(message: types.Message):
    # Если нужно отправлять ссылку на фото в таблицу, 
    # фото сначала нужно выгрузить на хостинг или в сам ТГ.
    await message.answer("📸 Фото получено и сохранено в системе (условно).")

# ================= ЗАПУСК =================

async def on_startup(dp):
    webhook_url = os.getenv("WEBHOOK_URL")
    if webhook_url:
        await bot.set_webhook(webhook_url)

if __name__ == "__main__":
    # Если на Railway используете Webhook:
    if os.getenv("WEBHOOK_URL"):
        executor.start_webhook(
            dispatcher=dp,
            webhook_path="",
            on_startup=on_startup,
            skip_updates=True,
            host="0.0.0.0",
            port=int(os.environ.get("PORT", 8080))
        )
    else:
        # Для локальных тестов
        executor.start_polling(dp, skip_updates=True)
