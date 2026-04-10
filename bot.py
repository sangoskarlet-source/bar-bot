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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
SHEET_WEBHOOK_URL = os.getenv("SHEET_WEBHOOK_URL")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)
scheduler = AsyncIOScheduler(timezone="Europe/Moscow")

user_states = {}  
checklist_pending = {} 
temp_pending = {}

CLOSING_ITEMS = ["Фото бара", "Крышки закрыты", "Стоп-лист проверен", "Баклахи с водой", "Поверхности протерты", "Посуда в баре", "Кофе машина", "Раковины", "Кассовый узел", "Зона алкоголя", "Порядок на складе"]
fridges = {
    "1 этаж": ["Холодильник с водой", "Холодильник с вином", "Морозильник", "Холодильник в баре", "Холодильник с открытым вином"],
    "2 этаж": ["Холодильник с вином", "Холодильник Пепси", "Морозильник", "Холодильник для фруктов", "Сережа", "Морозильный ларь"]
}
# Список заданий
DAILY_CLEANING_TASKS = [
    "Подоконники, и Сережа", "Холодильник для овощей", "Холодильник для вина", 
    "Полки для специй и чайников, техническая зона кофемашины", 
    "Стелаж с соками, полки для вина и пива на складе", 
    "Бойлер от накипи, и хаус зона со льдом", 
    "Морозильный ларь, и полки для алкоголя в баре"
]
# Список дней для поиска в таблице
DAYS_RU = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]

def get_msk_time():
    return datetime.now(timezone(timedelta(hours=3)))

async def send_to_sheet(payload):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(SHEET_WEBHOOK_URL, json=payload, timeout=20) as resp:
                res = await resp.text()
                logger.info(f"Google Response: {res}")
                return res
    except Exception as e:
        logger.error(f"Error: {e}")

def get_main_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add("📦 Перенос", "🗑 Списание", "📸 Фото уборки", "🧹 Чеклист", "🌡 Журнал температур", "🧹 Ежедневная уборка")
    return kb

# --- ЕЖЕДНЕВНАЯ УБОРКА (ИСПРАВЛЕНО) ---
@dp.message_handler(lambda m: m.text == "🧹 Ежедневная уборка")
async def daily_task_start(message: types.Message):
    now = get_msk_time()
    day_idx = now.weekday() # 0 = Пн
    task = DAILY_CLEANING_TASKS[day_idx]
    day_name = DAYS_RU[day_idx]
    
    user_states[message.from_user.id] = {"state": "daily_confirm", "task": task, "day": day_name}
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True).add("✅ Выполнил(а)", "⬅ Назад")
    await message.answer(f"Сегодня <b>{day_name}</b>.\nЗадание:\n<b>{task}</b>", parse_mode="HTML", reply_markup=kb)

@dp.message_handler(lambda m: m.text == "✅ Выполнил(а)" and user_states.get(m.from_user.id, {}).get("state") == "daily_confirm")
async def daily_task_done(message: types.Message):
    u_id = message.from_user.id
    data = user_states[u_id]
    
    # Отправляем название дня, чтобы скрипт нашел столбец
    payload = {
        "sheet": "Ежедневная уборка", 
        "user": message.from_user.full_name, 
        "task": data["task"],
        "day": data["day"] 
    }
    
    asyncio.create_task(send_to_sheet(payload))
    await message.answer(f"✅ Уборка за {data['day']} записана!", reply_markup=get_main_kb())
    user_states.pop(u_id, None)

# --- Остальные обработчики (Перенос, Чеклист, Температуры) ---

@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    await message.answer(f"ID: <code>{message.from_user.id}</code>", parse_mode="HTML", reply_markup=get_main_kb())

@dp.message_handler(lambda m: m.text == "⬅ Назад")
async def back_to_menu(message: types.Message):
    user_states.pop(message.from_user.id, None)
    await message.answer("Меню:", reply_markup=get_main_kb())

@dp.message_handler(lambda m: m.text in ["📦 Перенос", "🗑 Списание"])
async def start_tr_wr(message: types.Message):
    u_id = message.from_user.id
    if "Перенос" in message.text:
        user_states[u_id] = {"state": "tr_dir"}
        await message.answer("Направление:", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("Кухня → Бар", "Бар → Кухня", "⬅ Назад"))
    else:
        user_states[u_id] = {"state": "wr_val"}
        await message.answer("Что списываем?", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("⬅ Назад"))

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
        asyncio.create_task(send_to_sheet({"sheet": "Переносы" if st["state"]=="tr_val" else "Списания", "user": message.from_user.full_name, "item": item, "qty": qty, "direction": st.get("direction", "")}))
    await message.answer(f"✅ Записано: {len(lines)}", reply_markup=get_main_kb())
    user_states.pop(u_id, None)

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
    await message.answer("Пункты:", reply_markup=kb.add("⬅ Назад"))

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "cls")
async def ch_proc(message: types.Message):
    u_id = message.from_user.id
    if message.text not in checklist_pending.get(u_id, []): return
    asyncio.create_task(send_to_sheet({"sheet": "Чеклист", "user": message.from_user.full_name, "session_id": user_states[u_id]["session"], "task": message.text, "val": "✅"}))
    checklist_pending[u_id].remove(message.text)
    if checklist_pending[u_id]:
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2); [kb.insert(i) for i in checklist_pending[u_id]]
        await message.answer("Ок:", reply_markup=kb.add("⬅ Назад"))
    else:
        user_states.pop(u_id); await message.answer("🎉 Смена закрыта!", reply_markup=get_main_kb())

# --- Планировщик ---

async def job_start_shift(sh):
    today = get_msk_time().strftime("%d.%m.%Y")
    res = await send_to_sheet({"action": "get_schedule"})
    if res and isinstance(res, list):
        idx = next((i for i, v in enumerate(res[0]) if today in str(v)), -1)
        if idx != -1:
            for r in res[1:]:
                if str(r[0]).isdigit() and sh in str(r[idx]).upper():
                    try: await bot.send_message(int(r[0]), f"🔔 Смена {sh} началась!")
                    except: pass

async def job_check():
    today = get_msk_time().strftime("%d.%m.%Y")
    status = await send_to_sheet({"action": "check_completion"})
    missing = []
    if not status.get("1 этаж") or not status.get("2 этаж"): missing.append("🌡 Температуры")
    if not status.get("Чеклист") or not status.get("Ежедневная уборка"): missing.append("🧹 Уборки")
    if missing:
        res = await send_to_sheet({"action": "get_schedule"})
        idx = next((i for i, v in enumerate(res[0]) if today in str(v)), -1)
        sh = "А" if get_msk_time().hour < 18 else "Б"
        for r in res[1:]:
            if str(r[0]).isdigit() and sh in str(r[idx]).upper():
                try: await bot.send_message(int(r[0]), "⚠️ Забыли:\n"+"\n".join(missing))
                except: pass

async def on_startup(_):
    scheduler.add_job(job_start_shift, "cron", hour=12, minute=0, args=["А"])
    scheduler.add_job(job_start_shift, "cron", hour=19, minute=0, args=["Б"])
    scheduler.add_job(job_check, "cron", hour=17, minute=0)
    scheduler.add_job(job_check, "cron", hour=22, minute=0)
    scheduler.start()

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
