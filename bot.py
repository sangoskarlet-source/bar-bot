import os
import re
import requests
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from datetime import datetime

# ================= Настройки =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
SHEET_WEBHOOK_URL = os.getenv("SHEET_WEBHOOK_URL")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# ================= КЛАВИАТУРЫ =================

main_kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
main_kb.add("📦 Перенос", "🗑 Списание")
main_kb.add("📸 Фото уборки", "🧹 Чеклист")
main_kb.add("🌡 Журнал температур", "🧹 Ежедневная уборка")

direction_kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
direction_kb.add("Кухня → Бар", "Бар → Кухня", "⬅ Назад")

# Список холодильников (Проверь, чтобы в таблице было ТАК ЖЕ)
fridges = {
    "1 этаж": [
        "Холодильник с водой", 
        "Холодильник с вином", 
        "Морозильник", 
        "Холодильник в баре", 
        "Холодильник с открытым вином"
    ],
    "2 этаж": [
        "Холодильник с вином", 
        "Холодильник Пепси", 
        "Морозильник", 
        "Холодильник для фруктов", 
        "Сережа", 
        "Морозильный ларь"
    ]
}

user_states = {}  
temp_pending = {} 

def send_to_sheet(payload):
    try:
        res = requests.post(SHEET_WEBHOOK_URL, json=payload, timeout=10)
        return res.text
    except Exception as e:
        print(f"Ошибка: {e}")
        return "ERROR"

# ================= ОБРАБОТЧИКИ =================

@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    await message.answer("Система готова. Выберите действие:", reply_markup=main_kb)

@dp.message_handler(lambda m: m.text == "⬅ Назад")
async def go_back(message: types.Message):
    user_states.pop(message.from_user.id, None)
    temp_pending.pop(message.from_user.id, None)
    await message.answer("Главное меню:", reply_markup=main_kb)

# ---------- ПЕРЕНОС / СПИСАНИЕ ----------
@dp.message_handler(lambda m: m.text in ["📦 Перенос", "🗑 Списание"])
async def process_start(message: types.Message):
    mode = "transfer" if "Перенос" in message.text else "writeoff"
    if mode == "transfer":
        user_states[message.from_user.id] = {"state": "transfer_direction"}
        await message.answer("Выберите направление:", reply_markup=direction_kb)
    else:
        user_states[message.from_user.id] = {"state": "writeoff_text"}
        await message.answer("Что и сколько списываем?", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("⬅ Назад"))

@dp.message_handler(lambda m: m.text in ["Кухня → Бар", "Бар → Кухня"])
async def transfer_dir(message: types.Message):
    user_states[message.from_user.id] = {"state": "transfer_text", "direction": message.text}
    await message.answer("Введите название и количество:", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("⬅ Назад"))

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") in ["transfer_text", "writeoff_text"])
async def save_item(message: types.Message):
    u_id = message.from_user.id
    state_data = user_states[u_id]
    text = message.text.strip()
    
    weight_match = re.search(r'(\d+[.,]?\d*)', text)
    weight = weight_match.group(1) if weight_match else "?"
    item_name = re.sub(r'(\d+[.,]?\d*)', '', text).strip()

    payload = {
        "sheet": "Переносы" if state_data["state"] == "transfer_text" else "Списания",
        "user": message.from_user.full_name,
        "item": item_name,
        "qty": weight
    }
    if "direction" in state_data: payload["direction"] = state_data["direction"]

    send_to_sheet(payload)
    await message.answer(f"✅ Записано: {item_name} ({weight})", reply_markup=main_kb)
    user_states.pop(u_id)

# ---------- ТЕМПЕРАТУРЫ ----------
@dp.message_handler(lambda m: m.text == "🌡 Журнал температур")
async def temp_start(message: types.Message):
    user_states[message.from_user.id] = {"state": "temp_floor"}
    await message.answer("Выберите этаж:", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("1 этаж", "2 этаж", "⬅ Назад"))

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "temp_floor")
async def temp_floor(message: types.Message):
    floor = message.text
    if floor in ["1 этаж", "2 этаж"]:
        user_states[message.from_user.id] = {"state": "temp_fridge", "floor": floor}
        temp_pending[message.from_user.id] = fridges[floor].copy()
        
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        for f in temp_pending[message.from_user.id]: kb.insert(f)
        kb.add("⬅ Назад")
        await message.answer(f"Этаж {floor}. Выберите холодильник:", reply_markup=kb)

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "temp_fridge")
async def temp_fridge_choice(message: types.Message):
    u_id = message.from_user.id
    if message.text not in temp_pending.get(u_id, []):
        return await message.answer("Выберите из списка!")
    
    user_states[u_id]["state"] = "temp_value"
    user_states[u_id]["fridge_choice"] = message.text
    await message.answer(f"Температура для '{message.text}':", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("⬅ Назад"))

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "temp_value")
async def temp_val_save(message: types.Message):
    u_id = message.from_user.id
    data = user_states[u_id]
    
    send_to_sheet({
        "sheet": data["floor"],
        "user": message.from_user.full_name,
        "date": datetime.now().strftime("%d.%m.%Y"),
        "fridge": data["fridge_choice"],
        "temp": message.text
    })

    temp_pending[u_id].remove(data["fridge_choice"])

    if temp_pending[u_id]:
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        for f in temp_pending[u_id]: kb.insert(f)
        kb.add("⬅ Назад")
        user_states[u_id]["state"] = "temp_fridge"
        await message.answer("Записано. Следующий:", reply_markup=kb)
    else:
        user_states.pop(u_id)
        temp_pending.pop(u_id)
        await message.answer("✅ Все температуры внесены!", reply_markup=main_kb)

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
