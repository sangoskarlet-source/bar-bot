import os
import re
import asyncio
import aiohttp
import logging
import time
import json
from datetime import datetime, timedelta, timezone

from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ================= НАСТРОЙКИ ЛОГИРОВАНИЯ =================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ================= ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
SHEET_WEBHOOK_URL = os.getenv("SHEET_WEBHOOK_URL")
ADMIN_IDS = [5646298852] # Добавьте сюда ID менеджеров через запятую

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
    """Текущее время по Москве"""
    return datetime.now(timezone(timedelta(hours=3)))

async def send_to_sheet(payload):
    """Связь с Google Таблицей"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(SHEET_WEBHOOK_URL, json=payload, timeout=25) as resp:
                text = await resp.text()
                try:
                    return json.loads(text)
                except:
                    return text
    except Exception as e:
        logger.error(f"Ошибка связи с таблицей: {e}")
        return None

def get_main_kb():
    """Главная клавиатура"""
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add("📦 Перенос", "🗑 Списание", "📸 Фото уборки", "🧹 Чеклист", "🌡 Журнал температур", "🧹 Ежедневная уборка")
    return kb

# ================= АВТО-НАПОМИНАНИЯ (ПО ГРАФИКУ) =================

async def job_start_shift(shift_type):
    """Рассылка в 12:00 и 19:00"""
    now = get_msk_time()
    search_pattern = now.strftime("%d.%m") # Ищем "10.04"
    
    schedule = await send_to_sheet({"action": "get_schedule"})
    if not isinstance(schedule, list): return

    headers = schedule[0]
    date_idx = -1
    for i, h in enumerate(headers):
        if search_pattern in str(h):
            date_idx = i
            break
    
    if date_idx != -1:
        for row in schedule[1:]:
            if len(row) > date_idx:
                u_id = str(row[0]).strip()
                val = str(row[date_idx]).upper()
                if u_id.isdigit() and shift_type in val:
                    try:
                        await bot.send_message(int(u_id), "🔔 Хорошей смены и не забудте заполнить температурный режим и ежедневную уборку")
                    except: pass

async def job_check_reports():
    """Проверка отчетов в 17:00 и 22:00"""
    now = get_msk_time()
    today_pattern = now.strftime("%d.%m")
    
    status = await send_to_sheet({"action": "check_completion"})
    missing = []
    if not status or not isinstance(status, dict): return
    if not status.get("1 этаж") or not status.get("2 этаж"): missing.append("🌡 Журнал температур")
    if not status.get("Чеклист") or not status.get("Ежедневная уборка"): missing.append("🧹 Уборки / Чеклисты")

    if missing:
        target_shift = "А" if now.hour < 18 else "Б"
        schedule = await send_to_sheet({"action": "get_schedule"})
        headers = schedule[0]
        date_idx = next((i for i, h in enumerate(headers) if today_pattern in str(h)), -1)
        
        for row in schedule[1:]:
            u_id = str(row[0]).strip()
            if u_id.isdigit() and target_shift in str(row[date_idx]).upper():
                try:
                    await bot.send_message(int(u_id), f"⚠️ <b>ВНИМАНИЕ!</b>\nВы забыли заполнить:\n" + "\n".join(missing), parse_mode="HTML")
                except: pass

# ================= КОМАНДЫ МЕНЕДЖЕРА =================

@dp.message_handler(commands=["push"])
async def manual_push(message: types.Message):
    """Ручная рассылка по текущей смене"""
    if message.from_user.id not in ADMIN_IDS:
        return await message.answer("❌ Нет прав.")

    args = message.get_args()
    push_text = args if args else "Напоминание: заполни чеклист и журналы! 🧹🌡"
    
    now = get_msk_time()
    today_pattern = now.strftime("%d.%m")
    
    data = await send_to_sheet({"action": "get_schedule"})
    if not isinstance(data, list): return await message.answer("Ошибка связи с таблицей.")

    headers = data[0]
    date_idx = next((i for i, h in enumerate(headers) if today_pattern in str(h)), -1)
    
    if date_idx == -1: return await message.answer(f"Дата {today_pattern} не найдена.")

    count = 0
    for row in data[1:]:
        u_id = str(row[0]).strip()
        shift_val = str(row[date_idx]).upper()
        if u_id.isdigit() and any(x in shift_val for x in ["А", "Б"]):
            try:
                await bot.send_message(int(u_id), f"⚠️ <b>ОТ МЕНЕДЖЕРА:</b>\n\n{push_text}", parse_mode="HTML")
                count += 1
            except: pass
    await message.answer(f"✅ Отправлено: {count} чел.")

@dp.message_handler(commands=["test_schedule"])
async def test_sched(message: types.Message):
    """Диагностика графика"""
    now = get_msk_time()
    today_pattern = now.strftime("%d.%m")
    res = await send_to_sheet({"action": "get_schedule"})
    if not isinstance(res, list): return await message.answer("Ошибка таблицы.")
    
    headers = res[0]
    date_idx = next((i for i, h in enumerate(headers) if today_pattern in str(h)), -1)
    
    if date_idx == -1:
        await message.answer(f"❌ Колонки {today_pattern} нет. Вижу: {headers[2:6]}")
    else:
        user_row = next((r for r in res[1:] if str(r[0]).strip() == str(message.from_user.id)), None)
        if user_row:
            await message.answer(f"✅ Нашел! Твоя смена в '{headers[date_idx]}': <b>{user_row[date_idx]}</b>", parse_mode="HTML")
        else:
            await message.answer("❌ Твоего ID нет в колонке A.")

# ================= ОБРАБОТЧИКИ МЕНЮ =================

@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    await message.answer(f"ID: <code>{message.from_user.id}</code>", parse_mode="HTML", reply_markup=get_main_kb())

@dp.message_handler(lambda m: m.text == "⬅ Назад")
async def go_back(message: types.Message):
    user_states.pop(message.from_user.id, None)
    await message.answer("Главное меню:", reply_markup=get_main_kb())

@dp.message_handler(lambda m: m.text in ["📦 Перенос", "🗑 Списание"])
async def process_start(message: types.Message):
    u_id = message.from_user.id
    user_states[u_id] = {"state": "tr_dir" if "Перенос" in message.text else "wr_val"}
    if "Перенос" in message.text:
        await message.answer("Направление:", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("Кухня → Бар", "Бар → Кухня", "⬅ Назад"))
    else:
        await message.answer("Что списываем? (каждая позиция с новой строки)", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("⬅ Назад"))

@dp.message_handler(lambda m: m.text in ["Кухня → Бар", "Бар → Кухня"])
async def tr_dir(message: types.Message):
    user_states[message.from_user.id].update({"state": "tr_val", "direction": message.text})
    await message.answer(f"Что переносим ({message.text})?", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("⬅ Назад"))

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") in ["tr_val", "wr_val"])
async def save_items(message: types.Message):
    u_id = message.from_user.id
    st = user_states[u_id]
    lines = message.text.strip().split('\n')
    for line in lines:
        if not line.strip(): continue
        w = re.search(r'(\d+[.,]?\d*)', line)
        q = w.group(1).replace(',', '.') if w else "?"
        it = re.sub(r'(\d+[.,]?\d*)', '', line).strip() or "???"
        payload = {"sheet": "Переносы" if st["state"]=="tr_val" else "Списания", "user": message.from_user.full_name, "item": it, "qty": q, "direction": st.get("direction", "")}
        asyncio.create_task(send_to_sheet(payload))
    await message.answer(f"✅ Записано строк: {len(lines)}", reply_markup=get_main_kb())
    user_states.pop(u_id, None)

@dp.message_handler(lambda m: m.text == "🧹 Ежедневная уборка")
async def daily_task(message: types.Message):
    now = get_msk_time()
    task = DAILY_CLEANING_TASKS[now.weekday()]
    day_name = DAYS_RU[now.weekday()]
    user_states[message.from_user.id] = {"state": "d_c", "task": task, "day": day_name}
    await message.answer(f"Сегодня {day_name}.\nЗадание:\n<b>{task}</b>", parse_mode="HTML",
                         reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("✅ Выполнил(а)", "⬅ Назад"))

@dp.message_handler(lambda m: m.text == "✅ Выполнил(а)" and user_states.get(m.from_user.id, {}).get("state") == "d_c")
async def daily_done(message: types.Message):
    u_id = message.from_user.id
    d = user_states[u_id]
    asyncio.create_task(send_to_sheet({"sheet": "Ежедневная уборка", "user": message.from_user.full_name, "task": d["task"], "day": d["day"]}))
    await message.answer("✅ Отметка в таблице поставлена!", reply_markup=get_main_kb())
    user_states.pop(u_id, None)

@dp.message_handler(lambda m: m.text == "🌡 Журнал температур")
async def temp_start(message: types.Message):
    await message.answer("Этаж:", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("1 этаж", "2 этаж", "⬅ Назад"))

@dp.message_handler(lambda m: m.text in ["1 этаж", "2 этаж"])
async def temp_floor(message: types.Message):
    u_id = message.from_user.id
    user_states[u_id] = {"state": "t_f", "floor": message.text, "session": f"T{int(time.time())}"}
    temp_pending[u_id] = fridges[message.text].copy()
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2); [kb.insert(f) for f in temp_pending[u_id]]
    await message.answer("Объект:", reply_markup=kb.add("⬅ Назад"))

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "t_f")
async def temp_val(message: types.Message):
    if message.text not in temp_pending.get(message.from_user.id, []): return
    user_states[message.from_user.id].update({"state": "t_v", "obj": message.text})
    await message.answer(f"Введите температуру для {message.text}:")

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "t_v")
async def temp_save(message: types.Message):
    u_id = message.from_user.id
    d = user_states[u_id]
    asyncio.create_task(send_to_sheet({"sheet": d["floor"], "user": message.from_user.full_name, "session_id": d["session"], "fridge": d["obj"], "temp": message.text}))
    temp_pending[u_id].remove(d["obj"])
    if temp_pending[u_id]:
        user_states[u_id]["state"] = "t_f"
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2); [kb.insert(f) for f in temp_pending[u_id]]
        await message.answer("Записано. Дальше:", reply_markup=kb.add("⬅ Назад"))
    else:
        user_states.pop(u_id); await message.answer("✅ Готово!", reply_markup=get_main_kb())

@dp.message_handler(lambda m: m.text == "🧹 Чеклист")
async def ch_m(message: types.Message):
    await message.answer("Выберите:", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("Закрытие смены", "⬅ Назад"))

@dp.message_handler(lambda m: m.text == "Закрытие смены")
async def ch_s(message: types.Message):
    u_id = message.from_user.id
    user_states[u_id] = {"state": "cls", "session": f"C{int(time.time())}"}
    checklist_pending[u_id] = CLOSING_ITEMS.copy()
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2); [kb.insert(i) for i in checklist_pending[u_id]]
    await message.answer("Нажимайте выполненные пункты:", reply_markup=kb.add("⬅ Назад"))

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "cls")
async def ch_p(message: types.Message):
    u_id = message.from_user.id
    task = message.text
    if task == "⬅ Назад":
        user_states.pop(u_id, None); await message.answer("Меню:", reply_markup=get_main_kb()); return
    if u_id not in checklist_pending or task not in checklist_pending[u_id]: return
    asyncio.create_task(send_to_sheet({"sheet": "Чеклист", "user": message.from_user.full_name, "session_id": user_states[u_id]["session"], "task": task, "val": "✅"}))
    checklist_pending[u_id].remove(task)
    if checklist_pending[u_id]:
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2); [kb.insert(i) for i in checklist_pending[u_id]]
        await message.answer("Ок. Что еще?", reply_markup=kb.add("⬅ Назад"))
    else:
        user_states.pop(u_id); await message.answer("🎉 Смена закрыта!", reply_markup=get_main_kb())

# ================= ЗАПУСК =================

async def on_startup(_):
    # Утреннее (12:00) и Вечернее (19:00) напоминание
    scheduler.add_job(job_start_shift, "cron", hour=12, minute=0, args=["А"])
    scheduler.add_job(job_start_shift, "cron", hour=19, minute=0, args=["Б"])
    
    # Проверка отчетов в 17:00 и 22:00
    scheduler.add_job(job_check_reports, "cron", hour=17, minute=0)
    scheduler.add_job(job_check_reports, "cron", hour=22, minute=0)
    
    scheduler.start()

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
