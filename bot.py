import logging
from datetime import datetime

import gspread
from oauth2client.service_account import ServiceAccountCredentials

from aiogram import Bot, Dispatcher, executor, types

# ================= НАСТРОЙКИ =================

API_TOKEN = "ТВОЙ_TELEGRAM_BOT_TOKEN"
SPREADSHEET_ID = "ТВОЙ_SPREADSHEET_ID"
CREDS_FILE = "credentials.json"

# =============================================

logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

# --- Google Sheets подключение ---

scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]

creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_FILE, scope)
client = gspread.authorize(creds)

sheet_graph = client.open_by_key(SPREADSHEET_ID).worksheet("График")
sheet_photo = client.open_by_key(SPREADSHEET_ID).worksheet("Фото")

# ================= КОМАНДЫ =================

@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    await message.answer("Бот работает. Отправь фото ежедневной уборки.")

@dp.message_handler(commands=["id"])
async def get_id(message: types.Message):
    await message.answer(f"Ваш chat_id: {message.from_user.id}")

# ================= СОХРАНЕНИЕ ФОТО =================

@dp.message_handler(content_types=types.ContentType.PHOTO)
async def save_photo(message: types.Message):
    user_id = str(message.from_user.id)
    file_id = message.photo[-1].file_id
    now = datetime.now().strftime("%d.%m.%Y %H:%M:%S")

    # Получаем данные графика
    graph_data = sheet_graph.get_all_values()

    user_name = "Не найден"

    # Ищем имя по chat_id (столбец A)
    for row in graph_data[1:]:  # пропускаем заголовок
        if len(row) > 1 and row[0] == user_id:
            user_name = row[1]  # столбец B = имя
            break

    # Записываем в лист Фото:
    # Дата | Имя | chat_id | file_id
    sheet_photo.append_row([
        now,
        user_name,
        user_id,
        file_id
    ])

    await message.answer("Фото сохранено ✅")

# ================= ЗАПУСК =================

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
