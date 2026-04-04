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

temp_floor_kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
temp_floor_kb.add("1 этаж", "2 этаж", "⬅ Назад")

fridges = {
    "1 этаж": ["Холодильник с водой", "Холодильник с вином", "Морозильник", "Холодильник в баре", "Холодильник с открытым вином"],
    "2 этаж": ["Холодильник с вином", "Холодильник Пепси", "Морозильник", "Холодильник для фруктов", "Сережа", "Морозильный ларь"]
}

user_states = {}  
temp_pending = {} 

# ================= ФУНКЦИЯ ОТПРАВКИ =================

def send_to_sheet(payload):
    try:
        res = requests.post(SHEET_WEBHOOK_URL, json=payload, timeout=10)
        print(f"Ответ Google: {res.text}")
        return True
    except Exception as e:
        print(f"Ошибка отправки: {e}")
        return False

# ================= ОБРАБОТКА КНОПОК =================

@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    await message.answer("Выберите действие:", reply_markup=main_kb)

@dp.message_handler(lambda m: m.text == "⬅ Назад")
async def go_back(message: types.Message):
    user_states.pop(message.from_user.id, None)
    temp_pending.pop(message.from_user.id, None)
    await message.answer("Главное меню:", reply_markup=main_kb)

# ---------- ПЕРЕНОС ----------
@dp.message_handler(lambda m: m.text == "📦 Перенос")
async def transfer_start(message: types.Message):
    user_states[message.from_user.id] = {"state": "transfer_direction"}
    await message.answer("Выберите направление:", reply_markup=direction_kb)

@dp.message_handler(lambda m: m.text in ["Кухня → Бар", "Бар → Кухня"])
async def transfer_direction(message: types.Message):
    user_states[message.from_user.id] = {"state": "transfer_text", "direction": message.text}
    await message.answer("Напишите что и сколько (например: Молоко 5):", 
                         reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("⬅ Назад"))

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "transfer_text")
async def transfer_save(message: types.Message):
    user_id = message.from_user.id
    direction = user_states[user_id]["direction"]
    text = message.text.strip()
    
    # Парсим число (количество) и текст (название)
    weight_match = re.search(r'(\d+[.,]?\d*)', text)
    weight = weight_match.group(1) if weight_match else "?"
    item_name = re.sub(r'(\d+[.,]?\d*)', '', text).strip()

    send_to_sheet({
        "sheet": "Переносы",
        "user": message.from_user.full_name,
        "item": item_name,
        "qty": weight,
        "direction": direction
    })
    
    await message.answer(f"✅ Записано: {item_name} ({weight})", reply_markup=main_kb)
    user_states.pop(user_id)

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
    item_name = re.sub(r'(\d+[.,]?\d*)', '', text).strip()

    send_to_sheet({
        "sheet": "Списания",
        "user": message.from_user.full_name,
        "item": item_name,
        "qty": weight
    })
    await message.answer(f"✅ Списание: {item_name} ({weight})", reply_markup=main_kb)
    user_states.pop(message.from_user.id)

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
        
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        for f in temp_pending[message.from_user.id]:
            kb.insert(f)
        kb.add("⬅ Назад")
        await message.answer("Выберите холодильник:", reply_markup=kb)

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "temp_fridge")
async def temp_input(message: types.Message):
    user_id = message.from_user.id
    fridge_choice = message.text
    if fridge_choice not in temp_pending.get(user_id, []):
        await message.answer("Используйте кнопки для выбора!")
        return
        
    user_states[user_id]["state"] = "temp_value"
    user_states[user_id]["fridge_choice"] = fridge_choice
    await message.answer(f"Температура для {fridge_choice}:", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("⬅ Назад"))

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "temp_value")
async def temp_save(message: types.Message):
    user_id = message.from_user.id
    temp_val = message.text
    floor = user_states[user_id]["floor"]
    fridge = user_states[user_id]["fridge_choice"]

    send_to_sheet({
        "sheet": floor,
        "user": message.from_user.full_name,
        "date": datetime.now().strftime("%d.%m.%Y"),
        "fridge": fridge,
        "temp": temp_val
    })

    temp_pending[user_id].remove(fridge)

    if temp_pending[user_id]:
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        for f in temp_pending[user_id]:
            kb.insert(f)
        kb.add("⬅ Назад")
        user_states[user_id]["state"] = "temp_fridge"
        await message.answer(f"Записано {temp_val}°. Следующий:", reply_markup=kb)
    else:
        user_states.pop(user_id)
        temp_pending.pop(user_id)
        await message.answer("✅ Все данные внесены", reply_markup=main_kb)

# ---------- ЗАПУСК ----------
if __name__ == "__main__":
    if os.getenv("WEBHOOK_URL"):
        executor.start_webhook(
            dispatcher=dp,
            webhook_path="",
            on_startup=lambda d: bot.set_webhook(os.getenv("WEBHOOK_URL")),
            skip_updates=True,
            host="0.0.0.0",
            port=int(os.environ.get("PORT", 8080))
        )
    else:
        executor.start_polling(dp, skip_updates=True)
