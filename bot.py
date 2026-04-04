import os
import re
import asyncio
import aiohttp
import time
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from datetime import datetime

# ================= Настройки =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
SHEET_WEBHOOK_URL = os.getenv("SHEET_WEBHOOK_URL")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

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

async def send_to_sheet_async(payload):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(SHEET_WEBHOOK_URL, json=payload, timeout=15) as resp:
                return await resp.text()
    except Exception as e:
        print(f"Ошибка: {e}")

def get_main_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add("📦 Перенос", "🗑 Списание", "📸 Фото уборки", "🧹 Чеклист", "🌡 Журнал температур", "🧹 Ежедневная уборка")
    return kb

# ================= ОБРАБОТЧИКИ =================

@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    await message.answer("Система готова:", reply_markup=get_main_kb())

@dp.message_handler(lambda m: m.text == "⬅ Назад")
async def go_back(message: types.Message):
    u_id = message.from_user.id
    user_states.pop(u_id, None)
    await message.answer("Главное меню:", reply_markup=get_main_kb())

# ---------- ЧЕКЛИСТ ----------
@dp.message_handler(lambda m: m.text == "🧹 Чеклист")
async def checklist_start(message: types.Message):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True).add("Лайн чек заготовок", "Закрытие смены", "⬅ Назад")
    await message.answer("Выберите чеклист:", reply_markup=kb)

@dp.message_handler(lambda m: m.text == "Закрытие смены")
async def closing_start(message: types.Message):
    u_id = message.from_user.id
    # ГЕНЕРИРУЕМ ID СЕССИИ (Уникальный код для этой конкретной смены)
    session_id = f"CLS_{u_id}_{int(time.time())}"
    user_states[u_id] = {"state": "closing_process", "session_id": session_id}
    checklist_pending[u_id] = CLOSING_ITEMS.copy()
    
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    for item in checklist_pending[u_id]: kb.insert(item)
    kb.add("⬅ Назад")
    await message.answer("Отмечайте выполненное:", reply_markup=kb)

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "closing_process")
async def closing_process(message: types.Message):
    u_id = message.from_user.id
    task = message.text
    if task not in checklist_pending.get(u_id, []): return

    payload = {
        "sheet": "Чеклист", 
        "user": message.from_user.full_name, 
        "session_id": user_states[u_id]["session_id"], # Передаем ID
        "task": task, 
        "val": "✅"
    }
    asyncio.create_task(send_to_sheet_async(payload))

    checklist_pending[u_id].remove(task)
    if checklist_pending[u_id]:
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        for item in checklist_pending[u_id]: kb.insert(item)
        kb.add("⬅ Назад")
        await message.answer(f"Готово: {task}", reply_markup=kb)
    else:
        user_states.pop(u_id, None)
        await message.answer("🎉 Чеклист завершен!", reply_markup=get_main_kb())

# ---------- ТЕМПЕРАТУРЫ ----------
@dp.message_handler(lambda m: m.text == "🌡 Журнал температур")
async def temp_start(message: types.Message):
    await message.answer("Выберите этаж:", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("1 этаж", "2 этаж", "⬅ Назад"))

@dp.message_handler(lambda m: m.text in ["1 этаж", "2 этаж"])
async def temp_floor_sel(message: types.Message):
    u_id = message.from_user.id
    floor = message.text
    # ГЕНЕРИРУЕМ ID СЕССИИ для замера температур
    session_id = f"TMP_{u_id}_{int(time.time())}"
    user_states[u_id] = {"state": "temp_fridge", "floor": floor, "session_id": session_id}
    temp_pending[u_id] = fridges[floor].copy()
    
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    for f in temp_pending[u_id]: kb.insert(f)
    kb.add("⬅ Назад")
    await message.answer(f"Этаж {floor}. Выберите холодильник:", reply_markup=kb)

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "temp_fridge")
async def temp_fridge_choice(message: types.Message):
    u_id = message.from_user.id
    if message.text not in temp_pending.get(u_id, []): return
    user_states[u_id]["state"] = "temp_value"
    user_states[u_id]["fridge_choice"] = message.text
    await message.answer(f"Градусы для {message.text}:", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("⬅ Назад"))

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "temp_value")
async def temp_val_save(message: types.Message):
    u_id = message.from_user.id
    data = user_states[u_id]
    payload = {
        "sheet": data["floor"], 
        "user": message.from_user.full_name, 
        "session_id": data["session_id"], # Передаем ID
        "fridge": data["fridge_choice"], 
        "temp": message.text
    }
    asyncio.create_task(send_to_sheet_async(payload))

    temp_pending[u_id].remove(data["fridge_choice"])
    if temp_pending[u_id]:
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        for f in temp_pending[u_id]: kb.insert(f)
        kb.add("⬅ Назад")
        user_states[u_id]["state"] = "temp_fridge"
        await message.answer(f"Записано {message.text}°. Следующий:", reply_markup=kb)
    else:
        user_states.pop(u_id)
        await message.answer("✅ Температуры заполнены!", reply_markup=get_main_kb())

# (Переносы и списания остаются без изменений, там сессии не нужны)

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
