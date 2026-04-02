import os
import requests
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup
from aiogram.utils import executor
from datetime import datetime

BOT_TOKEN = os.getenv("BOT_TOKEN")
SHEET_WEBHOOK_URL = os.getenv("SHEET_WEBHOOK_URL")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# ================= Клавиатуры =================
main_kb = ReplyKeyboardMarkup(resize_keyboard=True)
main_kb.add("📦 Перенос", "🗑 Списание")
main_kb.add("🧹 Чеклист", "🧹 Ежедневная уборка")

direction_kb = ReplyKeyboardMarkup(resize_keyboard=True)
direction_kb.add("Кухня → Бар", "Бар → Кухня", "⬅ Назад")

back_kb = ReplyKeyboardMarkup(resize_keyboard=True)
back_kb.add("⬅ Назад")

checklist_items = [
    "Лайн чек заготовок", "Фото бара", "Крышки закрыты", "Стоп-лист проверен",
    "Баклахи с водой", "Поверхности протерты", "Посуда в баре",
    "Кофе машина", "Раковины", "Кассовый узел", "Зона алкоголя", "Порядок на складе"
]

user_states = {}

# ================= Отправка в Sheets =================
def send_to_sheet(sheet, data_dict):
    try:
        requests.post(SHEET_WEBHOOK_URL, json={
            "sheet": sheet,
            "text": data_dict
        }, timeout=10)
    except Exception as e:
        print("Ошибка отправки:", e)

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
    await message.answer("Напишите что и сколько переносим:", reply_markup=back_kb)

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "transfer_text")
async def transfer_save(message: types.Message):
    direction = user_states[message.from_user.id]["direction"]
    data = {
        "Дата": datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
        "Сотрудник": message.from_user.full_name,
        "Направление": direction,
        "Позиция": message.text,
        "Вес": ""
    }
    send_to_sheet("Переносы", data)
    await message.answer("✅ Перенос записан", reply_markup=main_kb)
    user_states.pop(message.from_user.id)

# ================= Списание =================
@dp.message_handler(lambda m: m.text == "🗑 Списание")
async def writeoff_start(message: types.Message):
    user_states[message.from_user.id] = {"state": "writeoff"}
    await message.answer("Напишите что списываем:", reply_markup=back_kb)

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "writeoff")
async def writeoff_save(message: types.Message):
    data = {
        "Дата": datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
        "Сотрудник": message.from_user.full_name,
        "Позиция": message.text,
        "Вес": ""
    }
    send_to_sheet("Списания", data)
    await message.answer("✅ Списание записано", reply_markup=main_kb)
    user_states.pop(message.from_user.id)

# ================= Чеклист =================
@dp.message_handler(lambda m: m.text == "🧹 Чеклист")
async def checklist_start(message: types.Message):
    user_states[message.from_user.id] = {"state": "checklist", "checked": set()}
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    for item in checklist_items:
        kb.add(item)
    kb.add("Готово", "⬅ Назад")
    await message.answer("Выберите выполненные пункты:", reply_markup=kb)

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "checklist")
async def checklist_handler(message: types.Message):
    if message.text == "Готово":
        state = user_states.get(message.from_user.id)
        checked = state["checked"]
        data = {
            "Дата": datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
            "Сотрудник": message.from_user.full_name
        }
        for item in checklist_items:
            data[item] = item in checked
        send_to_sheet("Чеклист", data)
        await message.answer("✅ Чеклист отправлен", reply_markup=main_kb)
        user_states.pop(message.from_user.id)
        return

    if message.text == "⬅ Назад":
        user_states.pop(message.from_user.id, None)
        await message.answer("Главное меню:", reply_markup=main_kb)
        return

    # Отмечаем пункт
    user_states[message.from_user.id]["checked"].add(message.text)
    await message.answer(f"✅ Отмечено: {message.text}")

# ================= Назад =================
@dp.message_handler(lambda m: m.text == "⬅ Назад")
async def go_back(message: types.Message):
    user_states.pop(message.from_user.id, None)
    await message.answer("Главное меню:", reply_markup=main_kb)

# ================= Запуск =================
if __name__ == "__main__":
    from aiogram import executor
    executor.start_polling(dp, skip_updates=True)
