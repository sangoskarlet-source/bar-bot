import os
import re
import asyncio
import aiohttp
import time
from datetime import datetime, timedelta, timezone
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor

# ================= Настройки =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
SHEET_WEBHOOK_URL = os.getenv("SHEET_WEBHOOK_URL")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# Константы
CLOSING_ITEMS = [
    "Фото бара", "Крышки закрыты", "Стоп-лист проверен", 
    "Баклахи с водой", "Поверхности протерты", "Посуда в баре", 
    "Кофе машина", "Раковины", "Кассовый узел", 
    "Зона алкоголя", "Порядок на складе"
]

fridges = {
    "1 этаж": ["Холодильник с водой", "Холодильник с вином", "Морозильник", "Холодильник в баре", "Холодильник с открытым вином"],
    "2 этаж": ["Холодильник с вином", "Холодильник Пепси", "Морозильник", "Холодильник для фруктов", "Сережа", "Морозильный ларь"]
}

DAILY_CLEANING_TASKS = [
    "Подоконники, и Сережа",                                    # Пн (0)
    "Холодильник для овощей",                                  # Вт (1)
    "Холодильник для вина",                                    # Ср (2)
    "Полки для специй и чайников, техническая зона кофемашины", # Чт (3)
    "Стелаж с соками, полки для вина и пива на складе",        # Пт (4)
    "Бойлер от накипи, и хаус зона со льдом",                  # Сб (5)
    "Морозильный ларь, и полки для алкоголя в баре"            # Вс (6)
]

user_states = {}  
checklist_pending = {} 
temp_pending = {}

# --- Вспомогательные функции ---

def get_msk_time():
    """Получение текущего времени по Москве"""
    return datetime.now(timezone(timedelta(hours=3)))

async def send_to_sheet_async(payload):
    """Отправка данных в Google Apps Script"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(SHEET_WEBHOOK_URL, json=payload, timeout=15) as resp:
                return await resp.text()
    except Exception as e:
        print(f"Ошибка связи с Google: {e}")

def get_main_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add("📦 Перенос", "🗑 Списание", "📸 Фото уборки", "🧹 Чеклист", "🌡 Журнал температур", "🧹 Ежедневная уборка")
    return kb

# ---------- ЛОГИКА НАПОМИНАНИЙ (ФОНОВАЯ ЗАДАЧА) ----------

async def check_reminders_task():
    last_hour = -1
    while True:
        try:
            now = get_msk_time()
            # Проверка срабатывает один раз в начале часа
            if now.minute == 0 and now.hour != last_hour:
                h = now.hour
                today_str = now.strftime("%d.%m.%Y")
                
                # 1. Запрашиваем график
                async with aiohttp.ClientSession() as session:
                    async with session.post(SHEET_WEBHOOK_URL, json={"action": "get_schedule"}) as resp:
                        schedule = await resp.json()

                if schedule:
                    headers = schedule[0]
                    date_idx = next((i for i, v in enumerate(headers) if today_str in str(v)), -1)
                    
                    if date_idx != -1:
                        # Списки ID сотрудников на сегодня
                        shift_a_ids = [row[0] for row in schedule[1:] if "А" in str(row[date_idx]).upper() and str(row[0]).isdigit()]
                        shift_b_ids = [row[0] for row in schedule[1:] if "Б" in str(row[date_idx]).upper() and str(row[0]).isdigit()]

                        # --- 12:00 и 19:00: Напоминание о начале ---
                        if h == 12:
                            for uid in shift_a_ids:
                                await bot.send_message(uid, "🌞 12:00! Смена А началась. Удачного рабочего дня!")
                        
                        if h == 19:
                            for uid in shift_b_ids:
                                await bot.send_message(uid, "🌙 19:00! Смена Б началась. Продуктивного вечера!")

                        # --- 17:00 и 22:00: Проверка заполнения ---
                        if h == 17 or h == 22:
                            async with aiohttp.ClientSession() as session:
                                async with session.post(SHEET_WEBHOOK_URL, json={"action": "check_completion"}) as resp:
                                    status = await resp.json()
                            
                            missing = []
                            if not status.get("1 этаж") or not status.get("2 этаж"): missing.append("🌡 Журнал температур")
                            if not status.get("Чеклист") or not status.get("Ежедневная уборка"): missing.append("🧹 Уборка / Чеклисты")
                            
                            if missing:
                                reminder_text = "⚠️ <b>ВНИМАНИЕ!</b>\nВы забыли заполнить за сегодня:\n\n" + "\n".join(missing)
                                targets = shift_a_ids if h == 17 else shift_b_ids
                                for uid in targets:
                                    await bot.send_message(uid, reminder_text, parse_mode="HTML")

                last_hour = h
            await asyncio.sleep(30)
        except Exception as e:
            print(f"Ошибка в цикле напоминаний: {e}")
            await asyncio.sleep(60)

# ================= ОБРАБОТЧИКИ ТЕЛЕГРАМ =================

@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    u_id = message.from_user.id
    await message.answer(f"Система бармена активна.\nВаш ID: <code>{u_id}</code>\n(Передайте его менеджеру для графика)", 
                         parse_mode="HTML", reply_markup=get_main_kb())

@dp.message_handler(lambda m: m.text == "⬅ Назад")
async def go_back(message: types.Message):
    user_states.pop(message.from_user.id, None)
    await message.answer("Главное меню:", reply_markup=get_main_kb())

# ---------- ПЕРЕНОС И СПИСАНИЕ (МНОГОСТРОЧНОЕ) ----------

@dp.message_handler(lambda m: m.text in ["📦 Перенос", "🗑 Списание"])
async def start_process(message: types.Message):
    u
