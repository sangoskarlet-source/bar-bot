import os
import requests
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup
from aiogram.utils import executor
from datetime import datetime

# ================= Настройки =================
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
main_kb.add("🧹 Ежедневная уборка")

direction_kb = ReplyKeyboardMarkup(resize_keyboard=True)
direction_kb.add("Кухня → Бар")
direction_kb.add("Бар → Кухня")
direction_kb.add("⬅ Назад")

checklist_kb = ReplyKeyboardMarkup(resize_keyboard=True)
checklist_kb.add(
    "Лайн чек заготовок",
    "Закрытие смены"
)
checklist_back_kb = ReplyKeyboardMarkup(resize_keyboard=True)
checklist_back_kb.add("⬅ Назад")

temp_floor_kb = ReplyKeyboardMarkup(resize_keyboard=True)
temp_floor_kb.add("1 этаж", "2 этаж", "⬅ Назад")

# Список холодильников
fridges = {
    "1 этаж": ["Холодильник с водой", "Холодильник с вином", "Морозильник", "Холодильник в баре", "Холодильник с открытым вином"],
    "2 этаж": ["Холодильник с вином", "Холодильник Пепси", "Морозильник", "Холодильник для фруктов", "Сережа", "Морозильный ларь"]
}

user_states = {}  # для отслеживания состояния пользователя
temp_pending = {} # для хранения оставшихся холодильников на этаж

# ================= ФУНКЦИИ =================

def send_to_sheet(sheet, user, text, extra=""):
    try:
        requests.post(
            SHEET_WEBHOOK_URL,
            json={"sheet": sheet, "user": user, "text": text, "extra": extra},
            timeout=10
        )
    except Exception as e:
        print("Ошибка отправки:", e)

def send_temperature(user, sheet, fridge, temp):
    today = datetime.now().strftime("%d.%m.%Y")
    try:
        requests.post(
            SHEET_WEBHOOK_URL,
            json={
                "sheet": sheet,
                "user": user,
                "date": today,
                "fridge": fridge,
                "temp": temp
            },
            timeout=10
        )
    except Exception as e:
        print("Ошибка отправки температуры:", e)

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
    await message.answer("Напишите что и сколько переносим:", reply_markup=ReplyKeyboardMarkup(resize_keyboard=True).add("⬅ Назад"))

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "transfer_text")
async def transfer_save(message: types.Message):
    direction = user_states[message.from_user.id]["direction"]
    text = message.text.strip()
    lines = text.split("\n")
    for line in lines:
        if not line: continue
        import re
        weight_match = re.search(r'\d+([.,]\d+)?', line)
        weight = weight_match.group(0) if weight_match else ""
        position = re.sub(r'\d+([.,]\d+)?', '', line).strip()
        send_to_sheet("Переносы", f"{message.from_user.id} - {message.from_user.full_name}", position, direction + " | " + weight)
    await message.answer("✅ Перенос записан", reply_markup=main_kb)
    user_states.pop(message.from_user.id)

# ---------- СПИСАНИЕ ----------
@dp.message_handler(lambda m: m.text == "🗑 Списание")
async def writeoff_start(message: types.Message):
    user_states[message.from_user.id] = {"state": "writeoff"}
    await message.answer("Напишите что списываем:", reply_markup=ReplyKeyboardMarkup(resize_keyboard=True).add("⬅ Назад"))

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "writeoff")
async def writeoff_save(message: types.Message):
    text = message.text.strip()
    import re
    weight_match = re.search(r'\d+([.,]\d+)?', text)
    weight = weight_match.group(0) if weight_match else ""
    position = re.sub(r'\d+([.,]\d+)?', '', text).strip()
    send_to_sheet("Списания", f"{message.from_user.id} - {message.from_user.full_name}", position, weight)
    await message.answer("✅ Списание записано", reply_markup=main_kb)
    user_states.pop(message.from_user.id)

# ---------- ЧЕКЛИСТ ----------
@dp.message_handler(lambda m: m.text == "🧹 Чеклист")
async def checklist_start(message: types.Message):
    user_states[message.from_user.id] = {"state": "checklist"}
    await message.answer("Выберите чеклист:", reply_markup=checklist_kb)

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "checklist")
async def checklist_choice(message: types.Message):
    choice = message.text
    if choice == "Лайн чек заготовок":
        send_to_sheet("Чеклист", message.from_user.full_name, "Лайн чек заготовок", "Выполнено")
    elif choice == "Закрытие смены":
        items = [
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
        for i in items:
            send_to_sheet("Чеклист", message.from_user.full_name, i, "Выполнено")
    await message.answer("✅ Чеклист выполнен", reply_markup=main_kb)
    user_states.pop(message.from_user.id)

# ---------- ЖУРНАЛ ТЕМПЕРАТУР ----------
@dp.message_handler(lambda m: m.text == "🌡 Журнал температур")
async def temp_start(message: types.Message):
    user_states[message.from_user.id] = {"state": "temp_floor"}
    temp_pending[message.from_user.id] = {}
    await message.answer("Выберите этаж:", reply_markup=temp_floor_kb)

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "temp_floor")
async def temp_choose_floor(message: types.Message):
    floor = message.text
    if floor in ["1 этаж", "2 этаж"]:
        user_states[message.from_user.id] = {"state": "temp_fridge", "floor": floor}
        temp_pending[message.from_user.id] = fridges[floor].copy()
        fridge_kb = ReplyKeyboardMarkup(resize_keyboard=True)
        for f in temp_pending[message.from_user.id]:
            fridge_kb.add(f)
        fridge_kb.add("⬅ Назад")
        await message.answer("Выберите холодильник:", reply_markup=fridge_kb)

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "temp_fridge")
async def temp_input(message: types.Message):
    user_id = message.from_user.id
    pending = temp_pending.get(user_id, [])
    fridge_choice = message.text
    if fridge_choice not in pending:
        await message.answer("Выберите холодильник из списка!", reply_markup=main_kb)
        return
    user_states[user_id]["state"] = "temp_value"
    user_states[user_id]["fridge_choice"] = fridge_choice
    await message.answer(f"Введите температуру для {fridge_choice}:", reply_markup=ReplyKeyboardMarkup(resize_keyboard=True).add("⬅ Назад"))

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "temp_value")
async def temp_save(message: types.Message):
    user_id = message.from_user.id
    temp = message.text
    floor = user_states[user_id]["floor"]
    fridge = user_states[user_id]["fridge_choice"]
    send_temperature(f"{message.from_user.id} - {message.from_user.full_name}", floor, fridge, temp)

    # удаляем выбранный холодильник из списка
    temp_pending[user_id].remove(fridge)

    if temp_pending[user_id]:
        kb = ReplyKeyboardMarkup(resize_keyboard=True)
        for f in temp_pending[user_id]:
            kb.add(f)
        kb.add("⬅ Назад")
        user_states[user_id]["state"] = "temp_fridge"
        await message.answer("Выберите следующий холодильник:", reply_markup=kb)
    else:
        user_states.pop(user_id)
        temp_pending.pop(user_id)
        await message.answer("✅ Все температуры внесены", reply_markup=main_kb)

# ================= WEBHOOK =================

async def on_startup(dp):
    await bot.set_webhook(os.getenv("WEBHOOK_URL"))

if __name__ == "__main__":
    executor.start_webhook(
        dispatcher=dp,
        webhook_path="",
        on_startup=on_startup,
        skip_updates=True,
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8080, )))
