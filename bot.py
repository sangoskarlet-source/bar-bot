import os
import re
import asyncio
import aiohttp
import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ================= НАСТРОЙКИ =================
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
SHEET_WEBHOOK_URL = os.getenv("SHEET_WEBHOOK_URL")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)
scheduler = AsyncIOScheduler(timezone="Europe/Moscow") # Используем часовой пояс Москвы

# Состояния и временные данные
user_states = {}  
checklist_pending = {} 
temp_pending = {}

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
    "Подоконники, и Сережа",                                    # Пн
    "Холодильник для овощей",                                  # Вт
    "Холодильник для вина",                                    # Ср
    "Полки для специй и чайников, техническая зона кофемашины", # Чт
    "Стелаж с соками, полки для вина и пива на складе",        # Пт
    "Бойлер от накипи, и хаус зона со льдом",                  # Сб
    "Морозильный ларь, и полки для алкоголя в баре"            # Вс
]

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

def get_msk_time():
    return datetime.now(timezone(timedelta(hours=3)))

async def send_to_sheet(payload):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(SHEET_WEBHOOK_URL, json=payload, timeout=15) as resp:
                return await resp.json() if resp.status == 200 else await resp.text()
    except Exception as e:
        logging.error(f"Ошибка Google Sheets: {e}")

def get_main_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add("📦 Перенос", "🗑 Списание", "📸 Фото уборки", "🧹 Чеклист", "🌡 Журнал температур", "🧹 Ежедневная уборка")
    return kb

# ================= ЛОГИКА НАПОМИНАНИЙ (APScheduler) =================

async def job_start_shift(shift_type):
    """Напоминание о начале смены (12:00 и 19:00)"""
    today_str = get_msk_time().strftime("%d.%m.%Y")
    schedule = await send_to_sheet({"action": "get_schedule"})
    
    if schedule and isinstance(schedule, list):
        headers = schedule[0]
        date_idx = next((i for i, v in enumerate(headers) if today_str in str(v)), -1)
        
        if date_idx != -1:
            for row in schedule[1:]:
                u_id = str(row[0]).strip()
                if u_id.isdigit() and shift_type in str(row[date_idx]).upper():
                    text = f"🔔 Смена {shift_type} началась! Удачной работы."
                    try: await bot.send_message(int(u_id), text)
                    except: pass

async def job_check_reports(shift_to_warn):
    """Проверка отчетов в 17:00 и 22:00"""
    today_str = get_msk_time().strftime("%d.%m.%Y")
    # Проверяем заполнение в таблице
    completion = await send_to_sheet({"action": "check_completion"})
    
    missing = []
    if not completion or not isinstance(completion, dict): return
    if not completion.get("1 этаж") or not completion.get("2 этаж"): missing.append("🌡 Журнал температур")
    if not completion.get("Чеклист") or not completion.get("Ежедневная уборка"): missing.append("🧹 Уборка / Чеклист")

    if missing:
        schedule = await send_to_sheet({"action": "get_schedule"})
        headers = schedule[0]
        date_idx = next((i for i, v in enumerate(headers) if today_str in str(v)), -1)
        
        for row in schedule[1:]:
            u_id = str(row[0]).strip()
            if u_id.isdigit() and shift_to_warn in str(row[date_idx]).upper():
                msg = "⚠️ <b>ВНИМАНИЕ!</b>\nВы забыли заполнить:\n" + "\n".join(missing)
                try: await bot.send_message(int(u_id), msg, parse_mode="HTML")
                except: pass

# ================= ОБРАБОТЧИКИ СООБЩЕНИЙ =================

@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    await message.answer(f"Твой ID: <code>{message.from_user.id}</code>\nДобавь его в график.", 
                         parse_mode="HTML", reply_markup=get_main_kb())

@dp.message_handler(lambda m: m.text == "⬅ Назад")
async def back_to_menu(message: types.Message):
    user_states.pop(message.from_user.id, None)
    await message.answer("Главное меню:", reply_markup=get_main_kb())

# --- ПЕРЕНОС И СПИСАНИЕ (ИСПРАВЛЕНО: МНОГОСТРОЧНО) ---
@dp.message_handler(lambda m: m.text in ["📦 Перенос", "🗑 Списание"])
async def start_transfer_writeoff(message: types.Message):
    u_id = message.from_user.id
    if "Перенос" in message.text:
        user_states[u_id] = {"state": "transfer_dir"}
        await message.answer("Направление:", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("Кухня → Бар", "Бар → Кухня", "⬅ Назад"))
    else:
        user_states[u_id] = {"state": "writeoff_val"}
        await message.answer("Что списываем? Можно несколько строк.\nПример:\nЛайм 1.5\nМята 0.2", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("⬅ Назад"))

@dp.message_handler(lambda m: m.text in ["Кухня → Бар", "Бар → Кухня"])
async def transfer_dir_set(message: types.Message):
    user_states[message.from_user.id] = {"state": "transfer_val", "direction": message.text}
    await message.answer(f"Что переносим ({message.text})?", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("⬅ Назад"))

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") in ["transfer_val", "writeoff_val"])
async def process_multi_lines(message: types.Message):
    u_id = message.from_user.id
    data = user_states[u_id]
    lines = message.text.strip().split('\n')
    
    for line in lines:
        if not line.strip(): continue
        weight_match = re.search(r'(\d+[.,]?\d*)', line)
        weight = weight_match.group(1).replace(',', '.') if weight_match else "?"
        item_name = re.sub(r'(\d+[.,]?\d*)', '', line).strip() or "Не указано"

        payload = {
            "sheet": "Переносы" if data["state"] == "transfer_val" else "Списания",
            "user": message.from_user.full_name,
            "item": item_name, "qty": weight, "direction": data.get("direction", "")
        }
        asyncio.create_task(send_to_sheet(payload))
    
    await message.answer(f"✅ Записано строк: {len(lines)}", reply_markup=get_main_kb())
    user_states.pop(u_id, None)

# --- ЕЖЕДНЕВНАЯ УБОРКА (АВТО-ВЫБОР ЗАДАЧИ) ---
@dp.message_handler(lambda m: m.text == "🧹 Ежедневная уборка")
async def daily_clean(message: types.Message):
    task = DAILY_CLEANING_TASKS[get_msk_time().weekday()]
    user_states[message.from_user.id] = {"state": "confirm_daily", "task": task}
    await message.answer(f"Сегодняшнее задание:\n<b>{task}</b>", parse_mode="HTML",
                         reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("✅ Выполнил(а)", "⬅ Назад"))

@dp.message_handler(lambda m: m.text == "✅ Выполнил(а)" and user_states.get(m.from_user.id, {}).get("state") == "confirm_daily")
async def daily_done(message: types.Message):
    u_id = message.from_user.id
    payload = {"sheet": "Ежедневная уборка", "user": message.from_user.full_name, "task": user_states[u_id]["task"]}
    asyncio.create_task(send_to_sheet(payload))
    await message.answer("✅ Записано!", reply_markup=get_main_kb())
    user_states.pop(u_id, None)

# --- ЖУРНАЛ ТЕМПЕРАТУР ---
@dp.message_handler(lambda m: m.text == "🌡 Журнал температур")
async def temp_start(message: types.Message):
    await message.answer("Этаж:", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("1 этаж", "2 этаж", "⬅ Назад"))

@dp.message_handler(lambda m: m.text in ["1 этаж", "2 этаж"])
async def temp_floor(message: types.Message):
    u_id = message.from_user.id
    user_states[u_id] = {"state": "temp_f", "floor": message.text, "session": f"T{int(time.time())}"}
    temp_pending[u_id] = fridges[message.text].copy()
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    for f in temp_pending[u_id]: kb.insert(f)
    await message.answer("Выберите объект:", reply_markup=kb.add("⬅ Назад"))

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "temp_f")
async def temp_obj(message: types.Message):
    if message.text not in temp_pending.get(message.from_user.id, []): return
    user_states[message.from_user.id].update({"state": "temp_v", "obj": message.text})
    await message.answer(f"Температура для {message.text}:", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("⬅ Назад"))

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "temp_v")
async def temp_save(message: types.Message):
    u_id = message.from_user.id
    d = user_states[u_id]
    asyncio.create_task(send_to_sheet({"sheet": d["floor"], "user": message.from_user.full_name, "session_id": d["session"], "fridge": d["obj"], "temp": message.text}))
    temp_pending[u_id].remove(d["obj"])
    if temp_pending[u_id]:
        user_states[u_id]["state"] = "temp_f"
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        for f in temp_pending[u_id]: kb.insert(f)
        await message.answer("Записано. Дальше:", reply_markup=kb.add("⬅ Назад"))
    else:
        user_states.pop(u_id); await message.answer("✅ Готово!", reply_markup=get_main_kb())

# --- ЧЕКЛИСТ ---
@dp.message_handler(lambda m: m.text == "🧹 Чеклист")
async def check_start(message: types.Message):
    await message.answer("Чеклист:", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("Закрытие смены", "⬅ Назад"))

@dp.message_handler(lambda m: m.text == "Закрытие смены")
async def closing_start(message: types.Message):
    u_id = message.from_user.id
    user_states[u_id] = {"state": "cls", "session": f"C{int(time.time())}"}
    checklist_pending[u_id] = CLOSING_ITEMS.copy()
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    for i in checklist_pending[u_id]: kb.insert(i)
    await message.answer("Пункты закрытия:", reply_markup=kb.add("⬅ Назад"))

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "cls")
async def closing_step(message: types.Message):
    u_id = message.from_user.id
    if message.text not in checklist_pending.get(u_id, []): return
    asyncio.create_task(send_to_sheet({"sheet": "Чеклист", "user": message.from_user.full_name, "session_id": user_states[u_id]["session"], "task": message.text, "val": "✅"}))
    checklist_pending[u_id].remove(message.text)
    if checklist_pending[u_id]:
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        for i in checklist_pending[u_id]: kb.insert(i)
        await message.answer("Ок. Дальше:", reply_markup=kb.add("⬅ Назад"))
    else:
        user_states.pop(u_id); await message.answer("🎉 Смена закрыта!", reply_markup=get_main_kb())

# ================= ЗАПУСК =================

async def on_startup(dp):
    # Напоминания о начале смены
    scheduler.add_job(job_start_shift, "cron", hour=12, minute=0, args=["А"])
    scheduler.add_job(job_start_shift, "cron", hour=19, minute=0, args=["Б"])
    
    # Напоминания о забытых отчетах
    scheduler.add_job(job_check_reports, "cron", hour=17, minute=0, args=["А"])
    scheduler.add_job(job_check_reports, "cron", hour=22, minute=0, args=["Б"])
    
    scheduler.start()

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
