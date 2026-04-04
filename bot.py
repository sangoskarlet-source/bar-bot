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

# ПУНКТЫ ЧЕКЛИСТА
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

# ================= АСИНХРОННАЯ ОТПРАВКА (МГНОВЕННАЯ) =================
async def send_to_sheet_async(payload):
    """Отправляет данные в фоне, не заставляя бармена ждать"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(SHEET_WEBHOOK_URL, json=payload, timeout=15) as resp:
                res_text = await resp.text()
                print(f"Фоновая отправка: {res_text}")
    except Exception as e:
        print(f"Ошибка фоновой отправки: {e}")

# ================= КЛАВИАТУРЫ =================
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
    temp_pending.pop(u_id, None)
    checklist_pending.pop(u_id, None)
    await message.answer("Главное меню:", reply_markup=get_main_kb())

# ---------- ЧЕКЛИСТ ----------
@dp.message_handler(lambda m: m.text == "🧹 Чеклист")
async def checklist_start(message: types.Message):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True).add("Лайн чек заготовок", "Закрытие смены", "⬅ Назад")
    await message.answer("Выберите чеклист:", reply_markup=kb)

@dp.message_handler(lambda m: m.text in ["Лайн чек заготовок", "Закрытие смены"])
async def checklist_choice(message: types.Message):
    u_id = message.from_user.id
    if message.text == "Лайн чек заготовок":
        payload = {"sheet": "Чеклист", "user": message.from_user.full_name, "date": datetime.now().strftime("%d.%m.%Y"), "task": "Лайн чек заготовок", "val": "✅"}
        asyncio.create_task(send_to_sheet_async(payload))
        await message.answer("✅ Лайн чек выполнен!", reply_markup=get_main_kb())
    else:
        user_states[u_id] = {"state": "closing_process"}
        checklist_pending[u_id] = CLOSING_ITEMS.copy()
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        for item in checklist_pending[u_id]: kb.insert(item)
        kb.add("⬅ Назад")
        await message.answer("Закрытие смены. Нажимайте готовое:", reply_markup=kb)

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "closing_process")
async def closing_process(message: types.Message):
    u_id = message.from_user.id
    task = message.text
    if task not in checklist_pending.get(u_id, []): return

    # 1. СРАЗУ отправляем задачу в фон
    payload = {"sheet": "Чеклист", "user": message.from_user.full_name, "date": datetime.now().strftime("%d.%m.%Y"), "task": task, "val": "✅"}
    asyncio.create_task(send_to_sheet_async(payload))

    # 2. МГНОВЕННО обновляем интерфейс
    checklist_pending[u_id].remove(task)
    if checklist_pending[u_id]:
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        for item in checklist_pending[u_id]: kb.insert(item)
        kb.add("⬅ Назад")
        await message.answer(f"Готово: {task}", reply_markup=kb)
    else:
        user_states.pop(u_id, None)
        await message.answer("🎉 Все задачи выполнены!", reply_markup=get_main_kb())

# ---------- ТЕМПЕРАТУРЫ ----------
@dp.message_handler(lambda m: m.text == "🌡 Журнал температур")
async def temp_start(message: types.Message):
    user_states[message.from_user.id] = {"state": "temp_floor"}
    await message.answer("Выберите этаж:", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("1 этаж", "2 этаж", "⬅ Назад"))

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "temp_floor")
async def temp_floor_sel(message: types.Message):
    floor = message.text
    if floor in ["1 этаж", "2 этаж"]:
        user_states[message.from_user.id] = {"state": "temp_fridge", "floor": floor}
        temp_pending[message.from_user.id] = fridges[floor].copy()
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        for f in temp_pending[message.from_user.id]: kb.insert(f)
        kb.add("⬅ Назад")
        await message.answer(f"Этаж {floor}:", reply_markup=kb)

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
    payload = {"sheet": data["floor"], "user": message.from_user.full_name, "date": datetime.now().strftime("%d.%m.%Y"), "fridge": data["fridge_choice"], "temp": message.text}
    asyncio.create_task(send_to_sheet_async(payload))

    temp_pending[u_id].remove(data["fridge_choice"])
    if temp_pending[u_id]:
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        for f in temp_pending[u_id]: kb.insert(f)
        kb.add("⬅ Назад")
        user_states[u_id]["state"] = "temp_fridge"
        await message.answer("Принято. Следующий:", reply_markup=kb)
    else:
        user_states.pop(u_id); await message.answer("✅ Готово!", reply_markup=get_main_kb())

# ---------- ПЕРЕНОС / СПИСАНИЕ ----------
@dp.message_handler(lambda m: m.text in ["📦 Перенос", "🗑 Списание"])
async def transfer_start(message: types.Message):
    mode = "transfer" if "Перенос" in message.text else "writeoff"
    user_states[message.from_user.id] = {"state": f"{mode}_direction" if mode == "transfer" else "writeoff_text"}
    if mode == "transfer":
        await message.answer("Направление:", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("Кухня → Бар", "Бар → Кухня", "⬅ Назад"))
    else:
        await message.answer("Что и сколько списываем?", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("⬅ Назад"))

@dp.message_handler(lambda m: m.text in ["Кухня → Бар", "Бар → Кухня"])
async def transfer_dir(message: types.Message):
    user_states[message.from_user.id] = {"state": "transfer_text", "direction": message.text}
    await message.answer("Текст (напр: Лайм 1кг):", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("⬅ Назад"))

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") in ["transfer_text", "writeoff_text"])
async def save_item(message: types.Message):
    u_id = message.from_user.id
    data = user_states[u_id]
    text = message.text.strip()
    weight = re.search(r'(\d+[.,]?\d*)', text)
    weight = weight.group(1) if weight else "?"
    item_name = re.sub(r'(\d+[.,]?\d*)', '', text).strip()

    payload = {"sheet": "Переносы" if data["state"] == "transfer_text" else "Списания", "user": message.from_user.full_name, "item": item_name, "qty": weight, "direction": data.get("direction", "")}
    asyncio.create_task(send_to_sheet_async(payload))
    await message.answer("✅ Записано", reply_markup=get_main_kb())
    user_states.pop(u_id)

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
