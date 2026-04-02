import telebot
import requests

# Токен твоего бота
BOT_TOKEN = "8553414858:AAGVIXM8rCDWMpeq-Nu3yHPZazNtJX6w_sQ"

# URL твоего Apps Script
SHEET_WEBHOOK_URL = "https://script.google.com/macros/s/AKfycbz/exec"

bot = telebot.TeleBot(BOT_TOKEN)

# состояния пользователей
user_state = {}

# временное хранение чек-листа
user_checklist = {}


# =============================
# СТАРТ / МЕНЮ
# =============================
def main_menu(chat_id):
    markup = telebot.types.InlineKeyboardMarkup()

    markup.add(
        telebot.types.InlineKeyboardButton("📦 Переносы", callback_data="perenos"),
        telebot.types.InlineKeyboardButton("🗑 Списания", callback_data="spisanie")
    )

    markup.add(
        telebot.types.InlineKeyboardButton("✅ Чек-лист", callback_data="checklist")
    )

    bot.send_message(chat_id, "Выбери действие:", reply_markup=markup)


@bot.message_handler(commands=['start'])
def start(message):
    main_menu(message.chat.id)


# =============================
# CALLBACK КНОПКИ
# =============================
@bot.callback_query_handler(func=lambda call: True)
def callback(call):

    chat_id = call.message.chat.id

    # НАЗАД
    if call.data == "back":
        main_menu(chat_id)

    # ПЕРЕНОСЫ
    elif call.data == "perenos":
        user_state[chat_id] = "perenos"
        bot.send_message(chat_id, "Введи переносы:\nпример:\nЛимон 2\nАпельсин 3")

    # СПИСАНИЯ
    elif call.data == "spisanie":
        user_state[chat_id] = "spisanie"
        bot.send_message(chat_id, "Введи списания:")

    # ЧЕК-ЛИСТ
    elif call.data == "checklist":
        user_checklist[chat_id] = {}
        show_checklist(chat_id)

    # ЧЕК-ЛИСТ ПУНКТЫ
    elif call.data.startswith("cl_"):
        handle_checklist(call)

    # ОТПРАВКА ЧЕК-ЛИСТА
    elif call.data == "send_checklist":
        send_checklist(chat_id)
        bot.answer_callback_query(call.id, "Отправлено ✅")
        main_menu(chat_id)


# =============================
# ЧЕК-ЛИСТ UI
# =============================
def show_checklist(chat_id):

    markup = telebot.types.InlineKeyboardMarkup()

    buttons = [
        ("Лайн чек", "cl_1"),
        ("Фото бара", "cl_2"),
        ("Крышки", "cl_3"),
        ("Стоп-лист", "cl_4"),
        ("Баклахи", "cl_5"),
        ("Поверхности", "cl_6"),
        ("Посуда", "cl_7"),
        ("Кофе машина", "cl_8"),
        ("Раковины", "cl_9"),
        ("Касса", "cl_10"),
        ("Алкоголь", "cl_11"),
        ("Склад", "cl_12")
    ]

    for text, code in buttons:
        markup.add(telebot.types.InlineKeyboardButton(text, callback_data=code))

    markup.add(
        telebot.types.InlineKeyboardButton("✅ Отправить", callback_data="send_checklist")
    )

    markup.add(
        telebot.types.InlineKeyboardButton("⬅️ Назад", callback_data="back")
    )

    bot.send_message(chat_id, "Отметь выполненные пункты:", reply_markup=markup)


# =============================
# ЛОГИКА ЧЕК-ЛИСТА
# =============================
def handle_checklist(call):

    chat_id = call.message.chat.id

    checklist_map = {
        "cl_1": "Лайн чек заготовок",
        "cl_2": "Фото бара отправлено",
        "cl_3": "Крышки закрыты",
        "cl_4": "Стоп-лист проверен",
        "cl_5": "Баклахи с водой",
        "cl_6": "Поверхности протерты",
        "cl_7": "Посуда в баре",
        "cl_8": "Кофе машина",
        "cl_9": "Раковины",
        "cl_10": "Кассовый узел",
        "cl_11": "Зона алкоголя",
        "cl_12": "Порядок на складе"
    }

    item = checklist_map.get(call.data)

    if chat_id not in user_checklist:
        user_checklist[chat_id] = {}

    user_checklist[chat_id][item] = "Выполнено"

    bot.answer_callback_query(call.id, f"{item} ✅")


def send_checklist(chat_id):

    data = user_checklist.get(chat_id, {})

    # если ничего не выбрано
    if not data:
        bot.send_message(chat_id, "Ты ничего не отметил ❗")
        return

    requests.post(
        SHEET_WEBHOOK_URL,
        json={
            "sheet": "Чеклист",
            "user": str(chat_id),
            "checklist": data
        },
        timeout=5
    )

    bot.send_message(chat_id, "Чек-лист сохранён ✅")


# =============================
# ОБРАБОТКА ТЕКСТА
# =============================
@bot.message_handler(func=lambda message: True)
def handle_text(message):

    chat_id = message.chat.id
    state = user_state.get(chat_id)

    if state == "perenos":

        requests.post(
            SHEET_WEBHOOK_URL,
            json={
                "sheet": "Переносы",
                "user": message.from_user.first_name,
                "text": message.text,
                "extra": "Бар"
            },
            timeout=5
        )

        bot.send_message(chat_id, "Перенос записан ✅")
        user_state[chat_id] = None

    elif state == "spisanie":

        requests.post(
            SHEET_WEBHOOK_URL,
            json={
                "sheet": "Списания",
                "user": message.from_user.first_name,
                "text": message.text
            },
            timeout=5
        )

        bot.send_message(chat_id, "Списание записано ✅")
        user_state[chat_id] = None


# =============================
# ЗАПУСК
# =============================
bot.infinity_polling()
