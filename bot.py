import telebot
import requests

# ================= Настройки =================
BOT_TOKEN = "8553414858:AAGVIXM8rCDWMpeq-Nu3yHPZazNtJX6w_sQ"
SHEET_WEBHOOK_URL = "https://script.google.com/macros/s/AKfycbxg8ZACys5zkZswAkCMVKaWXAc7dSqblHjtnHMxihG1EUm02tYLTCANQQ3zhBZslxZSRQ/exec"

bot = telebot.TeleBot(BOT_TOKEN)

# состояния пользователей
user_state = {}        # для Переносов и Списаний
user_checklist = {}    # для чек-листа

# ================= Главное меню =================
def main_menu(chat_id):
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("📦 Переносы", "🗑 Списания")
    markup.row("✅ Чек-лист")
    bot.send_message(chat_id, "Выберите действие:", reply_markup=markup)

@bot.message_handler(commands=['start'])
def start(message):
    main_menu(message.chat.id)

# ================= Переносы и Списания =================
@bot.message_handler(func=lambda message: True)
def handle_text(message):
    chat_id = message.chat.id
    state = user_state.get(chat_id)

    if state == "perenos":
        try:
            requests.post(
                SHEET_WEBHOOK_URL,
                json={"sheet": "Переносы", "user": message.from_user.first_name, "text": message.text},
                timeout=5
            )
            bot.send_message(chat_id, "✅ Перенос записан")
        except Exception as e:
            bot.send_message(chat_id, f"Ошибка отправки: {e}")
        user_state[chat_id] = None

    elif state == "spisanie":
        try:
            requests.post(
                SHEET_WEBHOOK_URL,
                json={"sheet": "Списания", "user": message.from_user.first_name, "text": message.text},
                timeout=5
            )
            bot.send_message(chat_id, "✅ Списание записано")
        except Exception as e:
            bot.send_message(chat_id, f"Ошибка отправки: {e}")
        user_state[chat_id] = None

# ================= Меню кнопок =================
@bot.message_handler(func=lambda m: m.text in ["📦 Переносы", "🗑 Списания", "✅ Чек-лист"])
def menu_buttons(message):
    chat_id = message.chat.id
    text = message.text

    if text == "📦 Переносы":
        user_state[chat_id] = "perenos"
        bot.send_message(chat_id, "Введите что переносим, например:\nЛимон 2\nАпельсин 3")

    elif text == "🗑 Списания":
        user_state[chat_id] = "spisanie"
        bot.send_message(chat_id, "Введите что списываем")

    elif text == "✅ Чек-лист":
        user_checklist[chat_id] = {}
        show_checklist(chat_id)

# ================= Чек-лист =================
def show_checklist(chat_id):
    markup = telebot.types.InlineKeyboardMarkup()
    checklist_items = [
        "Лайн чек заготовок","Фото бара отправлено","Крышки закрыты","Стоп-лист проверен",
        "Баклахи с водой","Поверхности протерты","Посуда в баре","Кофе машина",
        "Раковины","Кассовый узел","Зона алкоголя","Порядок на складе"
    ]
    for item in checklist_items:
        markup.add(telebot.types.InlineKeyboardButton(item, callback_data=item))
    markup.add(telebot.types.InlineKeyboardButton("✅ Отправить", callback_data="send_checklist"))
    markup.add(telebot.types.InlineKeyboardButton("⬅ Назад", callback_data="back"))
    bot.send_message(chat_id, "Отметьте выполненные пункты:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    chat_id = call.message.chat.id
    data = call.data

    if data == "back":
        main_menu(chat_id)
        bot.answer_callback_query(call.id)
        return

    if data == "send_checklist":
        send_checklist(chat_id)
        bot.answer_callback_query(call.id, "Чек-лист отправлен ✅")
        main_menu(chat_id)
        return

    # Отмечаем пункт чек-листа
    if chat_id not in user_checklist:
        user_checklist[chat_id] = {}
    user_checklist[chat_id][data] = "Выполнено"
    bot.answer_callback_query(call.id, f"{data} ✅")

def send_checklist(chat_id):
    data = user_checklist.get(chat_id, {})
    if not data:
        bot.send_message(chat_id, "Вы ничего не отметили ❌")
        return
    try:
        requests.post(
            SHEET_WEBHOOK_URL,
            json={"sheet": "Чеклист", "user": str(chat_id), "checklist": data},
            timeout=5
        )
        bot.send_message(chat_id, "Чек-лист сохранён ✅")
    except Exception as e:
        bot.send_message(chat_id, f"Ошибка отправки: {e}")
    user_checklist[chat_id] = {}

# ================= Запуск бота =================
bot.infinity_polling()
