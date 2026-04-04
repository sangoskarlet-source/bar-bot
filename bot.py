import os
import requests
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup
from datetime import datetime
import re
from apscheduler.schedulers.asyncio import AsyncIOScheduler

BOT_TOKEN = os.getenv("BOT_TOKEN")
SHEET_WEBHOOK_URL = os.getenv("SHEET_WEBHOOK_URL")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# ================= Клавиатуры =================
main_kb = ReplyKeyboardMarkup(resize_keyboard=True)
main_kb.add("📦 Перенос", "🗑 Списание")
main_kb.add("🧹 Чеклист", "🌡 Журнал температур")

direction_kb = ReplyKeyboardMarkup(resize_keyboard=True)
direction_kb.add("Кухня → Бар", "Бар → Кухня", "⬅ Назад")

back_kb = ReplyKeyboardMarkup(resize_keyboard=True)
back_kb.add("⬅ Назад")

floor_kb = ReplyKeyboardMarkup(resize_keyboard=True)
floor_kb.add("1 этаж", "2 этаж", "⬅ Назад")

# ================= Данные =================
checklist_items = [
    "Лайн чек заготовок", "Фото бара", "Крышки закрыты", "Стоп-лист проверен",
    "Баклахи с водой", "Поверхности протерты", "Посуда в баре",
    "Кофе машина", "Раковины", "Кассовый узел", "Зона алкоголя", "Порядок на складе"
]

floor1_items = [
    "Холодильник с водой",
    "Холодильник с вином",
    "Морозильник",
    "Холодильник в баре",
    "Холодильник с открытым вином"
]

floor2_items = [
    "Холодильник с вином",
    "Холодильник пепси",
    "Морозильник",
    "Холодильник для фруктов",
    "Сережа",
    "Морозильный ларь"
]

user_states = {}

# ================= Работа с таблицей =================
def send_to_sheet(sheet, data):
    try:
        requests.post(SHEET_WEBHOOK_URL, json={
            "sheet": sheet,
            "text": data
        }, timeout=10)
    except Exception as e:
        print("Ошибка:", e)

def get_today_workers():
    try:
        res = requests.get(SHEET_WEBHOOK_URL)
        return res.json()
    except Exception as e:
        print("Ошибка получения графика:", e)
        return []

# ================= НАПОМИНАНИЯ =================
async def send_reminders(mode):
    workers = get_today_workers()

    for w in workers:
        user_id = int(w["id"])
        shift = w["shift"]

        try:
            # Температуры (А)
            if mode == "temp_A" and "А" in shift:
                await bot.send_message(user_id, "🌡 Сними температуры (смена А)")

            # Температуры (Б)
            if mode == "temp_B" and "Б" in shift:
                await bot.send_message(user_id, "🌡 Сними температуры (смена Б)")

            # Чеклист (все)
            if mode == "checklist" and ("А" in shift or "Б" in shift):
                await bot.send_message(user_id, "🧹 Заполни чеклист перед закрытием")

        except Exception as e:
            print(f"Ошибка отправки {user_id}: {e}")

# ================= Планировщик =================
async def on_startup(dp):
    scheduler = AsyncIOScheduler()

    scheduler.add_job(send_reminders, "cron", hour=11, minute=30, args=["temp_A"])
    scheduler.add_job(send_reminders, "cron", hour=18, minute=30, args=["temp_B"])
    scheduler.add_job(send_reminders, "cron", hour=23, minute=30, args=["checklist"])

    scheduler.start()

# ================= Старт =================
@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    await message.answer("Выберите действие:", reply_markup=main_kb)

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
    await message.answer("Напишите что переносим:", reply_markup=back_kb)

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "transfer_text")
async def transfer_save(message: types.Message):
    direction = user_states[message.from_user.id]["direction"]

    for line in message.text.split("\n"):
        line = line.strip()
        if not line:
            continue

        num = re.search(r"\d+([.,]\d+)?", line)
        weight = num.group(0) if num else ""
        position = re.sub(r"\d+([.,]\d+)?", "", line).strip()

        send_to_sheet("Переносы", {
            "Дата": datetime.now().strftime("%d.%m.%Y %H:%M"),
            "Сотрудник": message.from_user.full_name,
            "Направление": direction,
            "Позиция": position,
            "Вес": weight
        })

    await message.answer("✅ Готово", reply_markup=main_kb)
    user_states.pop(message.from_user.id)

# ================= Списание =================
@dp.message_handler(lambda m: m.text == "🗑 Списание")
async def writeoff_start(message: types.Message):
    user_states[message.from_user.id] = {"state": "writeoff"}
    await message.answer("Напишите списание:", reply_markup=back_kb)

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "writeoff")
async def writeoff_save(message: types.Message):
    for line in message.text.split("\n"):
        line = line.strip()
        if not line:
            continue

        num = re.search(r"\d+([.,]\d+)?", line)
        weight = num.group(0) if num else ""
        position = re.sub(r"\d+([.,]\d+)?", "", line).strip()

        send_to_sheet("Списания", {
            "Дата": datetime.now().strftime("%d.%m.%Y %H:%M"),
            "Сотрудник": message.from_user.full_name,
            "Позиция": position,
            "Вес": weight
        })

    await message.answer("✅ Готово", reply_markup=main_kb)
    user_states.pop(message.from_user.id)

# ================= Чеклист =================
@dp.message_handler(lambda m: m.text == "🧹 Чеклист")
async def checklist_start(message: types.Message):
    user_states[message.from_user.id] = {"state": "checklist", "checked": set()}
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for item in checklist_items:
        kb.add(item)
    kb.add("Готово", "⬅ Назад")
    await message.answer("Отметьте выполненное:", reply_markup=kb)

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "checklist")
async def checklist_handler(message: types.Message):
    if message.text == "Готово":
        state = user_states[message.from_user.id]
        checked = state["checked"]

        data = {
            "Дата": datetime.now().strftime("%d.%m.%Y %H:%M"),
            "Сотрудник": message.from_user.full_name
        }

        for item in checklist_items:
            data[item] = "✅" if item in checked else "❌"

        send_to_sheet("Чеклист", data)
        await message.answer("✅ Отправлено", reply_markup=main_kb)
        user_states.pop(message.from_user.id)
        return

    if message.text == "⬅ Назад":
        user_states.pop(message.from_user.id)
        await message.answer("Меню", reply_markup=main_kb)
        return

    user_states[message.from_user.id]["checked"].add(message.text)
    await message.answer(f"✅ {message.text}")

# ================= Запуск =================
if __name__ == "__main__":
    from aiogram import executor
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
