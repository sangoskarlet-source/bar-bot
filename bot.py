import os
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor

# Переменные окружения
API_TOKEN = os.getenv("8553414858:AAGVIXM8rCDWMpeq-Nu3yHPZazNtJX6w_sQ")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

# Старт и клавиатура
@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add("Бар → Кухня", "Кухня → Бар")
    keyboard.add("Списание", "Фото уборки")
    await message.answer("Привет! Я бот бара 🍹\nВыбирай действие:", reply_markup=keyboard)

# Переносы бар ↔ кухня
@dp.message_handler(lambda m: m.text in ["Бар → Кухня", "Кухня → Бар"])
async def transfer(message: types.Message):
    await bot.send_message(ADMIN_ID, f"{message.from_user.full_name} сделал перенос: {message.text}")
    await message.reply("Перенос отправлен ✅")

# Кнопка списание — бот попросит ввести текст
@dp.message_handler(lambda m: m.text == "Списание")
async def write_off_prompt(message: types.Message):
    await message.reply("Напиши, что списываем (например: Мята 30 порча)")

# Обработка текста после нажатия "Списание" или обычного сообщения
@dp.message_handler()
async def handle_text(message: types.Message):
    # Игнорируем системные кнопки
    if message.text not in ["Бар → Кухня", "Кухня → Бар", "Списание", "Фото уборки"]:
        await bot.send_message(ADMIN_ID, f"Списание от {message.from_user.full_name}: {message.text}")
        await message.reply("Списание отправлено ✅")

# Обработка фото уборки
@dp.message_handler(content_types=['photo'])
async def handle_photo(message: types.Message):
    # Получаем файл фото
    file_id = message.photo[-1].file_id
    await bot.send_message(ADMIN_ID, f"Фото от {message.from_user.full_name}: на проверке")
    await message.reply("Фото отправлено на проверку ✅")

# Запуск бота
if __name__ == '__main__':
    print("Бот запущен")

    executor.start_polling(dp, skip_updates=True)
