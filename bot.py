import os
import re
import asyncio
import aiohttp
import time
import requests
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from datetime import datetime

# ================= Настройки =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
SHEET_WEBHOOK_URL = os.getenv("SHEET_WEBHOOK_URL")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# СПИСКИ
CLOSING_ITEMS = [
    "Фото бара", "Крышки закрыты", "Стоп-лист проверен", 
    "Баклахи с водой", "Поверхности протерты", "Посуда в баре", 
    "Кофе машина", "Раковины", "Кассовый узел", 
    "Зона алкоголя", "Порядок на складе"
]

fridges = {
    "1 этаж": ["Холодильник с водой", "Холодильник с вином", "Морозильник", "Холодильник в баре", "Холодильник с открытым вином"],
    "2 этаж": ["Холодильник с вином", "Холодильник Пепси", "Морозильник", "Холодильник для фруктов", "Сережа", "Морозильный ларь"]
}

user_states = {}  
temp_pending = {} 
checklist_pending = {} 

# --- Асинхронная отправка ---
async def send_to_sheet_async(payload):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(SHEET_WEBHOOK_URL, json=payload, timeout=15) as resp:
                text = await resp.text()
                print(f"Ответ Google: {text}")
    except Exception as e:
        print(f"Ошибка отправки: {e}")

def get_main_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add("📦 Перенос", "🗑 Списание", "📸 Фото уборки", "🧹 Чеклист", "🌡 Журнал температур", "🧹 Ежедневная уборка")
    return kb

# ================= ОБРАБОТЧИКИ =================

@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    await message.answer("Система бартендера активна:", reply_markup=get_main_kb())

@dp.message_handler(lambda m: m.text == "⬅ Назад")
async def go_back(message: types.Message):
    u_id = message.from_user.id
    user_states.pop(u_id, None)
    await message.answer("Главное меню:", reply_markup=get_main_kb())

# ---------- ПЕРЕНОС И СПИСАНИЕ ----------
@dp.message_handler(lambda m: m.text in ["📦 Перенос", "🗑 Списание"])
async def start_process(message: types.Message):
    u_id = message.from_user.id
    if "Перенос" in message.text:
        user_states[u_id] = {"state": "transfer_direction"}
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True).add("Кухня → Бар", "Бар → Кухня", "⬅ Назад")
        await message.answer("Направление переноса:", reply_markup=kb)
    else:
        user_states[u_id] = {"state": "writeoff_text"}
        await message.answer("Что и сколько списываем? (напр: Лайм 1кг)", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("⬅ Назад"))

@dp.message_handler(lambda m: m.text in ["Кухня → Бар", "Бар → Кухня"])
async def transfer_direction_step(message: types.Message):
    u_id = message.from_user.id
    user_states[u_id] = {"state": "transfer_text", "direction": message.text}
    await message.answer(f"Направление: {message.text}. Что переносим?", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("⬅ Назад"))

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") in ["transfer_text", "writeoff_text"])
async def save_transfer_or_writeoff(message: types.Message):
    u_id = message.from_user.id
    data = user_states[u_id]
    text = message.text.strip()
    
    # Парсим цифры и текст
    weight_match = re.search(r'(\d+[.,]?\d*)', text)
    weight = weight_match.group(1) if weight_match else "?"
    item_name = re.sub(r'(\d+[.,]?\d*)', '', text).strip()

    payload = {
        "sheet": "Переносы" if data["state"] == "transfer_text" else "Списания",
        "user": message.from_user.full_name,
        "item": item_name,
        "qty": weight,
        "direction": data.get("direction", "")
    }
    asyncio.create_task(send_to_sheet_async(payload))
    await message.answer(f"✅ Записано: {item_name} {weight}", reply_markup=get_main_kb())
    user_states.pop(u_id, None)

# ---------- ЧЕКЛИСТ ----------
@dp.message_handler(lambda m: m.text == "🧹 Чеклист")
async def checklist_menu(message: types.Message):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True).add("Лайн чек заготовок", "Закрытие смены", "⬅ Назад")
    await message.answer("Выберите чеклист:", reply_markup=kb)

@dp.message_handler(lambda m: m.text == "Закрытие смены")
async def closing_start(message: types.Message):
    u_id = message.from_user.id
    session_id = f"CLS_{u_id}_{int(time.time())}"
    user_states[u_id] = {"state": "closing_process", "session_id": session_id}
    checklist_pending[u_id] = CLOSING_ITEMS.copy()
    
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    for item in checklist_pending[u_id]: kb.insert(item)
    kb.add("⬅ Назад")
    await message.answer("Пункты закрытия (будут исчезать):", reply_markup=kb)

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "closing_process")
async def closing_process(message: types.Message):
    u_id = message.from_user.id
    task = message.text
    if task not in checklist_pending.get(u_id, []): return

    payload = {"sheet": "Чеклист", "user": message.from_user.full_name, "session_id": user_states[u_id]["session_id"], "task": task, "val": "✅"}
    asyncio.create_task(send_to_sheet_async(payload))

    checklist_pending[u_id].remove(task)
    if checklist_pending[u_id]:
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        for item in checklist_pending[u_id]: kb.insert(item)
        kb.add("⬅ Назад")
        await message.answer(f"Готово: {task}", reply_markup=kb)
    else:
        user_states.pop(u_id, None)
        await message.answer("🎉 Чеклист закрытия выполнен!", reply_markup=get_main_kb())

# ---------- ТЕМПЕРАТУРЫ ----------
@dp.message_handler(lambda m: m.text == "🌡 Журнал температур")
async def temp_menu(message: types.Message):
    await message.answer("Выберите этаж:", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("1 этаж", "2 этаж", "⬅ Назад"))

@dp.message_handler(lambda m: m.text in ["1 этаж", "2 этаж"])
async def temp_floor_sel(message: types.Message):
    u_id = message.from_user.id
    session_id = f"TMP_{u_id}_{int(time.time())}"
    user_states[u_id] = {"state": "temp_fridge", "floor": message.text, "session_id": session_id}
    temp_pending[u_id] = fridges[message.text].copy()
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    for f in temp_pending[u_id]: kb.insert(f)
    kb.add("⬅ Назад")
    await message.answer(f"Этаж {message.text}:", reply_markup=kb)

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "temp_fridge")
async def temp_fridge_choice(message: types.Message):
    u_id = message.from_user.id
    if message.text not in temp_pending.get(u_id, []): return
    user_states[u_id]["state"] = "temp_value"
    user_states[u_id]["fridge_choice"] = message.text
    await message.answer(f"Температура для {message.text}:", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("⬅ Назад"))

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "temp_value")
async def temp_val_save(message: types.Message):
    u_id = message.from_user.id
    data = user_states[u_id]
    payload = {"sheet": data["floor"], "user": message.from_user.full_name, "session_id": data["session_id"], "fridge": data["fridge_choice"], "temp": message.text}
    asyncio.create_task(send_to_sheet_async(payload))

    temp_pending[u_id].remove(data["fridge_choice"])
    if temp_pending[u_id]:
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        for f in temp_pending[u_id]: kb.insert(f)
        kb.add("⬅ Назад")
        user_states[u_id]["state"] = "temp_fridge"
        await message.answer(f"Записано {message.text}°. Следующий:", reply_markup=kb)
    else:
        user_states.pop(u_id); await message.answer("✅ Температуры заполнены!", reply_markup=get_main_kb())

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
