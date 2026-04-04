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

# ================= СПИСКИ И КЛАВИАТУРЫ =================

# Пункты чеклиста (Должны СОВПАДАТЬ с заголовками в таблице начиная с колонки C)
CLOSING_ITEMS = [
    "Фото бара", "Крышки закрыты", "Стоп-лист проверен", 
    "Баклахи с водой", "Поверхности протерты", "Посуда в баре", 
    "Кофе машина", "Раковины", "Кассовый узел", 
    "Зона алкоголя", "Порядок на складе"
]

main_kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
main_kb.add("📦 Перенос", "🗑 Списание")
main_kb.add("📸 Фото уборки", "🧹 Чеклист")
main_kb.add("🌡 Журнал температур", "🧹 Ежедневная уборка")

checklist_main_kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
checklist_main_kb.add("Лайн чек заготовок", "Закрытие смены", "⬅ Назад")

fridges = {
    "1 этаж": ["Холодильник с водой", "Холодильник с вином", "Морозильник", "Холодильник в баре", "Холодильник с открытым вином"],
    "2 этаж": ["Холодильник с вином", "Холодильник Пепси", "Морозильник", "Холодильник для фруктов", "Сережа", "Морозильный ларь"]
}

user_states = {}  
temp_pending = {} 
checklist_pending = {} 

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
    u_id = message.from_user.id
    user_states.pop(u_id, None)
    temp_pending.pop(u_id, None)
    checklist_pending.pop(u_id, None)
    await message.answer("Главное меню:", reply_markup=main_kb)

# ---------- ЧЕКЛИСТ ----------
@dp.message_handler(lambda m: m.text == "🧹 Чеклист")
async def checklist_start(message: types.Message):
    user_states[message.from_user.id] = {"state": "checklist_main"}
    await message.answer("Выберите чеклист:", reply_markup=checklist_main_kb)

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "checklist_main")
async def checklist_main_choice(message: types.Message):
    u_id = message.from_user.id
    choice = message.text

    if choice == "Лайн чек заготовок":
        send_to_sheet({
            "sheet": "Чеклист",
            "user": message.from_user.full_name,
            "date": datetime.now().strftime("%d.%m.%Y"),
            "task": "Лайн чек заготовок",
            "val": "✅"
        })
        await message.answer("✅ Лайн чек выполнен!", reply_markup=main_kb)
        user_states.pop(u_id, None)
    
    elif choice == "Закрытие смены":
        user_states[u_id]["state"] = "closing_process"
        checklist_pending[u_id] = CLOSING_ITEMS.copy()
        
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        for item in checklist_pending[u_id]: kb.insert(item)
        kb.add("⬅ Назад")
        await message.answer("Отмечайте выполненные пункты закрытия:", reply_markup=kb)

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "closing_process")
async def closing_item_click(message: types.Message):
    u_id = message.from_user.id
    task = message.text
    if task not in checklist_pending.get(u_id, []): return

    send_to_sheet({
        "sheet": "Чеклист",
        "user": message.from_user.full_name,
        "date": datetime.now().strftime("%d.%m.%Y"),
        "task": task,
        "val": "✅"
    })

    checklist_pending[u_id].remove(task)

    if checklist_pending[u_id]:
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        for item in checklist_pending[u_id]: kb.insert(item)
        kb.add("⬅ Назад")
        await message.answer(f"Принято: {task}. Что еще сделано?", reply_markup=kb)
    else:
        user_states.pop(u_id, None)
        checklist_pending.pop(u_id, None)
        await message.answer("🎉 Все задачи закрытия выполнены!", reply_markup=main_kb)

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
        await message.answer(f"Этаж {floor}. Какой холодильник?", reply_markup=kb)

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
        await message.answer("Записано. Дальше:", reply_markup=kb)
    else:
        user_states.pop(u_id); temp_pending.pop(u_id)
        await message.answer("✅ Температуры заполнены!", reply_markup=main_kb)

# ---------- ПЕРЕНОС / СПИСАНИЕ ----------
@dp.message_handler(lambda m: m.text in ["📦 Перенос", "🗑 Списание"])
async def process_start(message: types.Message):
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

    send_to_sheet({
        "sheet": "Переносы" if data["state"] == "transfer_text" else "Списания",
        "user": message.from_user.full_name,
        "item": item_name, "qty": weight,
        "direction": data.get("direction", "")
    })
    await message.answer(f"✅ Готово", reply_markup=main_kb)
    user_states.pop(u_id)

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
