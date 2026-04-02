import os
import requests
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils import executor

# ================= Настройки =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
SHEET_WEBHOOK_URL = os.getenv("SHEET_WEBHOOK_URL")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# ================= Клавиатуры =================
main_kb = ReplyKeyboardMarkup(resize_keyboard=True)
main_kb.add("📦 Переносы", "🗑 Списания")
main_kb.add("✅ Чек-лист")

back_kb = ReplyKeyboardMarkup(resize_keyboard=True)
back_kb.add("⬅ Назад")

# ================= Состояния =================
user_states = {}
user_checklist = {}

# ================= Отправка в Google Sheets =================
def send_to_sheet(sheet, user, text, extra=""):
    try:
        requests.post(
            SHEET_WEBHOOK_URL,
            json={"sheet": sheet, "user": user, "text": text, "extra": extra},
            timeout=10
        )
    except Exception as e:
        print("Ошибка отправки:", e)

# ================= Главная команда =================
@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    await message.answer("Выберите действие:", reply_markup=main_kb)

# ================= Переносы =================
@dp.message_handler(lambda m: m.text == "📦 Переносы")
async def transfer_start(message: types.Message):
    user_states[message.from_user.id] = {"state": "transfer"}
    await message.answer("Введите что переносим:", reply_markup=back_kb)

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "transfer")
async def transfer_save(message: types.Message):
    send_to_sheet("Переносы", message.from_user.full_name, message.text)
    await message.answer("✅ Перенос записан", reply_markup=main_kb)
    user_states.pop(message.from_user.id)

# ================= Списания =================
@dp.message_handler(lambda m: m.text == "🗑 Списания")
async def writeoff_start(message: types.Message):
    user_states[message.from_user.id] = {"state": "writeoff"}
    await message.answer("Введите что списываем:", reply_markup=back_kb)

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "writeoff")
async def writeoff_save(message: types.Message):
    send_to_sheet("Списания", message.from_user.full_name, message.text)
    await message.answer("✅ Списание записано", reply_markup=main_kb)
    user_states.pop(message.from_user.id)

# ================= Чек-лист =================
checklist_items = [
    "Лайн чек заготовок","Фото бара отправлено","Крышки закрыты","Стоп-лист проверен",
    "Баклахи с водой","Поверхности протерты","Посуда в баре","Кофе машина",
    "Раковины","Кассовый узел","Зона алкоголя","Порядок на складе"
]

@dp.message_handler(lambda m: m.text == "✅ Чек-лист")
async def checklist_start(message: types.Message):
    user_checklist[message.from_user.id] = set()
    await show_checklist(message.from_user.id)

async def show_checklist(user_id):
    markup = InlineKeyboardMarkup(row_width=2)
    for item in checklist_items:
        markup.insert(InlineKeyboardButton(text=item, callback_data=item))
    markup.add(InlineKeyboardButton("✅ Отправить", callback_data="send_checklist"))
    markup.add(InlineKeyboardButton("⬅ Назад", callback_data="back"))
    await bot.send_message(user_id, "Отметьте выполненные пункты:", reply_markup=markup)

@dp.callback_query_handler(lambda c: True)
async def checklist_handler(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    data = callback.data

    if data == "back":
        await bot.send_message(user_id, "Главное меню:", reply_markup=main_kb)
        await callback.answer()
        return

    if data == "send_checklist":
        checked = user_checklist.get(user_id, set())
        if checked:
            # Отправляем в Google Sheets, один row = один пользователь, колонки = пункты
            payload = {item: ("Выполнено" if item in checked else "") for item in checklist_items}
            send_to_sheet("Чеклист", str(user_id), str(payload))
            await bot.send_message(user_id, "Чек-лист сохранён ✅", reply_markup=main_kb)
        else:
            await bot.send_message(user_id, "Вы ничего не отметили ❌", reply_markup=main_kb)
        user_checklist[user_id] = set()
        await callback.answer()
        return

    # Отмечаем пункт
    if user_id not in user_checklist:
        user_checklist[user_id] = set()
    if data in user_checklist[user_id]:
        user_checklist[user_id].remove(data)
        await callback.answer(f"{data} ❌")
    else:
        user_checklist[user_id].add(data)
        await callback.answer(f"{data} ✅")

# ================= Кнопка Назад =================
@dp.message_handler(lambda m: m.text == "⬅ Назад")
async def go_back(message: types.Message):
    user_states.pop(message.from_user.id, None)
    user_checklist.pop(message.from_user.id, None)
    await message.answer("Главное меню:", reply_markup=main_kb)

# ================= Запуск бота =================
if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
