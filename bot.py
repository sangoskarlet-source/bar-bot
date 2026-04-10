import os
import re
import asyncio
import aiohttp
import logging
import time
from datetime import datetime, timedelta, timezone

from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ================= НАСТРОЙКИ ЛОГИРОВАНИЯ =================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ================= ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
SHEET_WEBHOOK_URL = os.getenv("SHEET_WEBHOOK_URL")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)
scheduler = AsyncIOScheduler(timezone="Europe/Moscow")

# ================= ДАННЫЕ И СПИСКИ =================
user_states = {}  
checklist_pending = {} 
temp_pending = {}

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
    "Подоконники, и Сережа",                                    # Пн
    "Холодильник для овощей",                                  # Вт
    "Холодильник для вина",                                    # Ср
    "Полки для специй и чайников, техническая зона кофемашины", # Чт
    "Стелаж с соками, полки для вина и пива на складе",        # Пт
    "Бойлер от накипи, и хаус зона со льдом",                  # Сб
    "Морозильный ларь, и полки для алкоголя в баре"            # Вс
]

DAYS_RU = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]

# ================= ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =================

def get_msk_time():
    return datetime.now(timezone(timedelta(hours=3)))

async def send_to_sheet(payload):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(SHEET_WEBHOOK_URL, json=payload, timeout=20) as resp:
                res = await resp.text()
                return res
    except Exception as e:
        logger.error(f"Ошибка Google Sheets: {e}")

def get_main_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add("📦 Перенос", "🗑 Списание", "📸 Фото уборки", "🧹 Чеклист", "🌡 Журнал температур", "🧹 Ежедневная уборка")
    return kb

# ================= ЛОГИКА НАПОМИНАНИЙ (ПО МОСКВЕ) =================

async def job_start_shift(shift_type):
    """Приветствие в 12:00 и 19:00"""
    today_str = get_msk_time().strftime("%d.%m.%Y")
    
    # Получаем график через Google Script
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(SHEET_WEBHOOK_URL, json={"action": "get_schedule"}) as resp:
                schedule = await resp.json()
        
        if schedule and isinstance(schedule, list):
            headers = schedule[0]
            date_idx = next((i for i, v in enumerate(headers) if today_str in str(v)), -1)
            
            if date_idx != -1:
                for row in schedule[1:]:
                    u_id = str(row[0]).strip()
                    # Если ID число и в графике стоит буква смены (А или Б)
                    if u_id.isdigit() and shift_type in str(row[date_idx]).upper():
                        msg = "🔔 Хорошей смены и не забудте заполнить температурный режим и ежедневную уборку"
                        try: await bot.send_message(int(u_id), msg)
                        except: pass
    except Exception as e:
        logger.error(f"Ошибка напоминания начала смены: {e}")

async def job_check_reports():
    """Проверка отчетов в 17:00 и 22:00"""
    now = get_msk_time()
    today_str = now.strftime("%d.%m.%Y")
    
    # Проверяем заполнение
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(SHEET_WEBHOOK_URL, json={"action": "check_completion"}) as resp:
                status = await resp.json()
        
        missing = []
        if not status.get("1 этаж") or not status.get("2 этаж"): missing.append("🌡 Журнал температур")
        if not status.get("Чеклист") or not status.get("Ежедневная уборка"): missing.append("🧹 Уборка / Чеклист")

        if missing:
            # Определяем, какую смену ругать (до 18:00 - А, после - Б)
            target_shift = "А" if now.hour < 18 else "Б"
            
            async with aiohttp.ClientSession() as session:
                async with session.post(SHEET_WEBHOOK_URL, json={"action": "get_schedule"}) as resp:
                    schedule = await resp.json()
            
            headers = schedule[0]
            date_idx = next((i for i, v in enumerate(headers) if today_str in str(v)), -1)
            
            for row in schedule[1:]:
                u_id = str(row[0]).strip()
                if u_id.isdigit() and target_shift in str(row[date_idx]).upper():
                    msg = "⚠️ <b>ВНИМАНИЕ!</b>\nВы забыли заполнить:\n" + "\n".join(missing)
                    try: await bot.send_message(int(u_id), msg, parse_mode="HTML")
                    except: pass
    except Exception as e:
        logger.error(f"Ошибка проверки отчетов: {e}")

# ================= ОБРАБОТЧИКИ =================

@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    await message.answer(f"Твой ID для графика: <code>{message.from_user.id}</code>", 
                         parse_mode="HTML", reply_markup=get_main_kb())

@dp.message_handler(lambda m: m.text == "⬅ Назад")
async def back_to_menu(message: types.Message):
    user_states.pop(message.from_user.id, None)
    await message.answer("Главное меню:", reply_markup=get_main_kb())

# --- МНОГОСТРОЧНОЕ СПИСАНИЕ/ПЕРЕНОС ---
@dp.message_handler(lambda m: m.text in ["📦 Перенос", "🗑 Списание"])
async def start_tr_wr(message: types.Message):
    u_id = message.from_user.id
    if "Перенос" in message.text:
        user_states[u_id] = {"state": "tr_dir"}
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True).add("Кухня → Бар", "Бар → Кухня", "⬅ Назад")
        await message.answer("Направление:", reply_markup=kb)
    else:
        user_states[u_id] = {"state": "wr_val"}
        await message.answer("Что списываем? (каждая позиция с новой строки)", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("⬅ Назад"))

@dp.message_handler(lambda m: m.text in ["Кухня → Бар", "Бар → Кухня"])
async def tr_dir_set(message: types.Message):
    user_states[message.from_user.id] = {"state": "tr_val", "direction": message.text}
    await message.answer(f"Что переносим ({message.text})?", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("⬅ Назад"))

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") in ["tr_val", "wr_val"])
async def process_lines(message: types.Message):
    u_id = message.from_user.id
    st = user_states[u_id]
    lines = message.text.strip().split('\n')
    for line in lines:
        if not line.strip(): continue
        weight = re.search(r'(\d+[.,]?\d*)', line)
        qty = weight.group(1).replace(',', '.') if weight else "?"
        item = re.sub(r'(\d+[.,]?\d*)', '', line).strip() or "???"
        
        payload = {
            "sheet": "Переносы" if st["state"]=="tr_val" else "Списания", 
            "user": message.from_user.full_name, 
            "item": item, "qty": qty, "direction": st.get("direction", "")
        }
        asyncio.create_task(send_to_sheet(payload))
    await message.answer(f"✅ Обработано строк: {len(lines)}", reply_markup=get_main_kb())
    user_states.pop(u_id, None)

# --- ЕЖЕДНЕВНАЯ УБОРКА ---
@dp.message_handler(lambda m: m.text == "🧹 Ежедневная уборка")
async def daily_start(message: types.Message):
    now = get_msk_time()
    day_idx = now.weekday()
    task = DAILY_CLEANING_TASKS[day_idx]
    day_name = DAYS_RU[day_idx]
    user_states[message.from_user.id] = {"state": "d_c", "task": task, "day": day_name}
    await message.answer(f"Задание на сегодня (<b>{day_name}</b>):\n{task}", 
                         parse_mode="HTML", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("✅ Выполнил(а)", "⬅ Назад"))

@dp.message_handler(lambda m: m.text == "✅ Выполнил(а)" and user_states.get(m.from_user.id, {}).get("state") == "d_c")
async def daily_done(message: types.Message):
    u_id = message.from_user.id
    d = user_states[u_id]
    payload = {"sheet": "Ежедневная уборка", "user": message.from_user.full_name, "task": d["task"], "day": d["day"]}
    asyncio.create_task(send_to_sheet(payload))
    await message.answer(f"✅ Записано!", reply_markup=get_main_kb())
    user_states.pop(u_id, None)

# --- ТЕМПЕРАТУРЫ ---
@dp.message_handler(lambda m: m.text == "🌡 Журнал температур")
async def tmp_start(message: types.Message):
    await message.answer("Этаж:", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("1 этаж", "2 этаж", "⬅ Назад"))

@dp.message_handler(lambda m: m.text in ["1 этаж", "2 этаж"])
async def tmp_floor(message: types.Message):
    u_id = message.from_user.id
    user_states[u_id] = {"state": "t_m", "floor": message.text, "session": f"T{int(time.time())}"}
    temp_pending[u_id] = fridges[message.text].copy()
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    for f in temp_pending[u_id]: kb.insert(f)
    await message.answer("Объект:", reply_markup=kb.add("⬅ Назад"))

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "t_m")
async def tmp_obj(message: types.Message):
    if message.text not in temp_pending.get(message.from_user.id, []): return
    user_states[message.from_user.id].update({"state": "t_v", "obj": message.text})
    await message.answer(f"Температура {message.text}:", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("⬅ Назад"))

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "t_v")
async def tmp_save(message: types.Message):
    u_id = message.from_user.id
    d = user_states[u_id]
    asyncio.create_task(send_to_sheet({"sheet": d["floor"], "user": message.from_user.full_name, "session_id": d["session"], "fridge": d["obj"], "temp": message.text}))
    temp_pending[u_id].remove(d["obj"])
    if temp_pending[u_id]:
        user_states[u_id]["state"] = "t_m"
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        for f in temp_pending[u_id]: kb.insert(f)
        await message.answer("Дальше:", reply_markup=kb.add("⬅ Назад"))
    else:
        user_states.pop(u_id); await message.answer("✅ Готово!", reply_markup=get_main_kb())

# --- ЧЕКЛИСТ ---
@dp.message_handler(lambda m: m.text == "🧹 Чеклист")
async def ch_menu(message: types.Message):
    await message.answer("Чеклист:", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("Закрытие смены", "⬅ Назад"))

@dp.message_handler(lambda m: m.text == "Закрытие смены")
async def ch_start(message: types.Message):
    u_id = message.from_user.id
    user_states[u_id] = {"state": "cls", "session": f"C{int(time.time())}"}
    checklist_pending[u_id] = CLOSING_ITEMS.copy()
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    for i in checklist_pending[u_id]: kb.insert(i)
    await message.answer("Пункт закрытия:", reply_markup=kb.add("⬅ Назад"))

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "cls")
async def ch_proc(message: types.Message):
    u_id = message.from_user.id
    task = message.text
    if task == "⬅ Назад":
        user_states.pop(u_id, None); await message.answer("Меню:", reply_markup=get_main_kb()); return
    if u_id not in checklist_pending or task not in checklist_pending[u_id]: return
    asyncio.create_task(send_to_sheet({"sheet": "Чеклист", "user": message.from_user.full_name, "session_id": user_states[u_id]["session"], "task": task, "val": "✅"}))
    checklist_pending[u_id].remove(task)
    if checklist_pending[u_id]:
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        for i in checklist_pending[u_id]: kb.insert(i)
        await message.answer("Ок. Дальше:", reply_markup=kb.add("⬅ Назад"))
    else:
        user_states.pop(u_id); await message.answer("🎉 Все выполнено!", reply_markup=get_main_kb())

# ================= ЗАПУСК =================

async def on_startup(dp):
    # Утреннее/Вечернее напоминание
    scheduler.add_job(job_start_shift, "cron", hour=12, minute=0, args=["А"])
    scheduler.add_job(job_start_shift, "cron", hour=19, minute=0, args=["Б"])
    
    # Проверка отчетов
    scheduler.add_job(job_check_reports, "cron", hour=17, minute=0)
    scheduler.add_job(job_check_reports, "cron", hour=22, minute=0)
    
    scheduler.start()

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
