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

checklist_kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
checklist_kb.add("Лайн чек заготовок", "Закрытие смены", "⬅ Назад")

fridges = {
    "1 этаж": ["Холодильник с водой", "Холодильник с вином", "Морозильник", "Холодильник в баре", "Холодильник с открытым вином"],
    "2 этаж": ["Холодильник с вином", "Холодильник Пепси", "Морозильник", "Холодильник для фруктов", "Сережа", "Морозильный ларь"]
}

user_states = {}  
temp_pending = {} 

def send_to_sheet(payload):
    try:
        res = requests.post(SHEET_WEBHOOK_URL, json=payload, timeout=10)
        return res.text
    except Exception as e:
        print(f"Ошибка отправки: {e}")
        return "ERROR"

# ================= ОБРАБОТЧИКИ =================

@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    await message.answer("Система бартендера готова:", reply_markup=main_kb)

@dp.message_handler(lambda m: m.text == "⬅ Назад")
async def go_back(message: types.Message):
    user_states.pop(message.from_user.id, None)
    temp_pending.pop(message.from_user.id, None)
    await message.answer("Главное меню:", reply_markup=main_kb)

# ---------- ЧЕКЛИСТ (ДОБАВЛЕНО) ----------
@dp.message_handler(lambda m: m.text == "🧹 Чеклист")
async def checklist_start(message: types.Message):
    user_states[message.from_user.id] = {"state": "checklist_choice"}
    await message.answer("Выберите чеклист:", reply_markup=checklist_kb)

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "checklist_choice")
async def checklist_process(message: types.Message):
    choice = message.text
    if choice == "⬅ Назад":
        user_states.pop(message.from_user.id)
        await message.answer("Главное меню:", reply_markup=main_kb)
        return

    if choice == "Лайн чек заготовок":
        send_to_sheet({
            "sheet": "Чеклист",
            "user": message.from_user.full_name,
            "task": "Лайн чек заготовок",
            "status": "Выполнено"
        })
        await message.answer("✅ Лайн чек записан", reply_markup=main_kb)
    
    elif choice == "Закрытие смены":
        items = ["Фото бара", "Крышки закрыты", "Стоп-лист", "Раковины", "Кофемашина", "Кассовый узел"]
        # Отправляем одной строкой или циклом (здесь для простоты одной записью)
        send_to_sheet({
            "sheet": "Чеклист",
            "user": message.from_user.full_name,
            "task": "Закрытие смены (все пункты)",
            "status": "Выполнено"
        })
        await message.answer("✅ Закрытие смены записано", reply_markup=main_kb)
    
    user_states.pop(message.from_user.id)

# ---------- ПЕРЕНОС / СПИСАНИЕ ----------
@dp.message_handler(lambda m: m.text in ["📦 Перенос", "🗑 Списание"])
async def process_start(message: types.Message):
    mode = "transfer" if "Перенос" in message.text else "writeoff"
    if mode == "transfer":
        user_states[message.from_user.id] = {"state": "transfer_direction"}
        await message.answer("Направление:", reply_markup=direction_kb)
    else:
        user_states[message.from_user.id] = {"state": "writeoff_text"}
        await message.answer("Что и сколько списываем?", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("⬅ Назад"))

@dp.message_handler(lambda m: m.text in ["Кухня → Бар", "Бар → Кухня"])
async def transfer_dir(message: types.Message):
    user_states[message.from_user.id] = {"state": "transfer_text", "direction": message.text}
    await message.answer("Введите текст (напр: Сироп 2):", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("⬅ Назад"))

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") in ["transfer_text", "writeoff_text"])
async def save_item(message: types.Message):
    u_id = message.from_user.id
    data = user_states[u_id]
    text = message.text.strip()
    
    weight = re.search(r'(\d+[.,]?\d*)', text)
    weight = weight.group(1) if weight else "?"
    item_name = re.sub(r'(\d+[.,]?\d*)', '', text).strip()

    payload = {
        "sheet": "Переносы" if data["state"] == "transfer_text" else "Списания",
        "user": message.from_user.full_name,
        "item": item_name,
        "qty": weight
    }
    if "direction" in data: payload["direction"] = data["direction"]

    send_to_sheet(payload)
    await message.answer(f"✅ Записано в {payload['sheet']}", reply_markup=main_kb)
    user_states.pop(u_id)

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
        await message.answer("Выберите холодильник:", reply_markup=kb)

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
        await message.answer("Следующий:", reply_markup=kb)
    else:
        user_states.pop(u_id); temp_pending.pop(u_id)
        await message.answer("✅ Готово!", reply_markup=main_kb)

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
