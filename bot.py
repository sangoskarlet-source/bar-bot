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

# ================= НАСТРОЙКИ =================
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
fridges = {"1 этаж": ["Холодильник с водой", "Холодильник с вином", "Морозильник", "Холодильник в баре", "Холодильник с открытым вином"], "2 этаж": ["Холодильник с вином", "Холодильник Пепси", "Морозильник", "Холодильник для фруктов", "Сережа", "Морозильный ларь"]}
DAILY_CLEANING_TASKS = ["Подоконники, и Сережа", "Холодильник для овощей", "Холодильник для вина", "Полки для специй и чайников, техническая зона кофемашины", "Стелаж с соками, полки для вина и пива на складе", "Бойлер от накипи, и хаус зона со льдом", "Морозильный ларь, и полки для алкоголя в баре"]
DAYS_RU = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]

def get_msk_time():
    return datetime.now(timezone(timedelta(hours=3)))

async def send_to_sheet(payload):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(SHEET_WEBHOOK_URL, json=payload, timeout=20) as resp:
                return await resp.json()
    except Exception as e:
        logger.error(f"Ошибка запроса к таблице: {e}")
        return None

def get_main_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add("📦 Перенос", "🗑 Списание", "📸 Фото уборки", "🧹 Чеклист", "🌡 Журнал температур", "🧹 Ежедневная уборка")
    return kb

# ================= ЛОГИКА НАПОМИНАНИЙ =================

async def job_start_shift(shift_type):
    now = get_msk_time()
    today_str = now.strftime("%d.%m.%Y")
    
    logger.info(f"Запуск рассылки для смены {shift_type}. Дата: {today_str}")
    
    schedule = await send_to_sheet({"action": "get_schedule"})
    if not schedule or not isinstance(schedule, list):
        logger.error("Не удалось получить график из таблицы")
        return

    headers = schedule[0]
    date_idx = -1
    
    # Ищем колонку с датой (проверяем разные форматы)
    for i, h in enumerate(headers):
        h_str = str(h)
        if today_str in h_str or now.strftime("%d.%m.%y") in h_str:
            date_idx = i
            break
    
    if date_idx != -1:
        for row in schedule[1:]:
            if len(row) <= date_idx: continue
            u_id = str(row[0]).strip()
            shift_val = str(row[date_idx]).upper()
            
            # Если ID есть и в ячейке есть буква смены (например "АБ" содержит "Б")
            if u_id.isdigit() and shift_type in shift_val:
                msg = "🔔 Хорошей смены и не забудте заполнить температурный режим и ежедневную уборку"
                try:
                    await bot.send_message(int(u_id), msg)
                    logger.info(f"Сообщение отправлено пользователю {u_id}")
                except Exception as e:
                    logger.error(f"Ошибка отправки пользователю {u_id}: {e}")
    else:
        logger.warning(f"Дата {today_str} не найдена в заголовках таблицы")

# ================= КОМАНДА ПРОВЕРКИ (ТЕСТ) =================

@dp.message_handler(commands=["test_schedule"])
async def cmd_test_sched(message: types.Message):
    now = get_msk_time()
    today_str = now.strftime("%d.%m.%Y")
    
    await message.answer(f"<b>Диагностика графика:</b>\n"
                         f"Твой ID: <code>{message.from_user.id}</code>\n"
                         f"Искомая дата: <code>{today_str}</code>", parse_mode="HTML")
    
    data = await send_to_sheet({"action": "get_schedule"})
    if not data:
        await message.answer("❌ Ошибка: Таблица не отвечает.")
        return

    headers = data[0]
    date_idx = -1
    for i, h in enumerate(headers):
        if today_str in str(h) or now.strftime("%d.%m.%y") in str(h):
            date_idx = i
            break
            
    if date_idx == -1:
        await message.answer(f"❌ Дата {today_str} не найдена в шапке.\n\n"
                             f"Вижу такие заголовки:\n<code>{headers[2:10]}...</code>", parse_mode="HTML")
    else:
        found_user = False
        for row in data[1:]:
            if str(row[0]).strip() == str(message.from_user.id):
                found_user = True
                shift = row[date_idx]
                await message.answer(f"✅ Ты найден в списке!\nТвоя смена на сегодня: <b>{shift}</b>\n\n"
                                     f"<i>Если тут 'АБ', то бот напишет и в 12, и в 19.</i>", parse_mode="HTML")
                break
        if not found_user:
            await message.answer("❌ Твой ID не найден в первой колонке листа 'График'.")

# ================= ОБРАБОТЧИКИ МЕНЮ =================

@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    await message.answer(f"Система активна. ID: <code>{message.from_user.id}</code>", 
                         parse_mode="HTML", reply_markup=get_main_kb())

@dp.message_handler(lambda m: m.text == "⬅ Назад")
async def go_back(message: types.Message):
    user_states.pop(message.from_user.id, None)
    await message.answer("Главное меню:", reply_markup=get_main_kb())

@dp.message_handler(lambda m: m.text in ["📦 Перенос", "🗑 Списание"])
async def tr_wr_start(message: types.Message):
    u_id = message.from_user.id
    user_states[u_id] = {"state": "tr_dir" if "Перенос" in message.text else "wr_val"}
    if "Перенос" in message.text:
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True).add("Кухня → Бар", "Бар → Кухня", "⬅ Назад")
        await message.answer("Направление:", reply_markup=kb)
    else:
        await message.answer("Что и сколько списываем? (каждая позиция с новой строки)", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("⬅ Назад"))

@dp.message_handler(lambda m: m.text in ["Кухня → Бар", "Бар → Кухня"])
async def tr_dir_step(message: types.Message):
    user_states[message.from_user.id] = {"state": "tr_val", "direction": message.text}
    await message.answer(f"Что переносим ({message.text})?", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("⬅ Назад"))

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") in ["tr_val", "wr_val"])
async def process_multiline(message: types.Message):
    u_id = message.from_user.id
    st = user_states[u_id]
    lines = message.text.strip().split('\n')
    for line in lines:
        if not line.strip(): continue
        w = re.search(r'(\d+[.,]?\d*)', line)
        qty = w.group(1).replace(',', '.') if w else "?"
        item = re.sub(r'(\d+[.,]?\d*)', '', line).strip() or "???"
        
        payload = {"sheet": "Переносы" if st["state"]=="tr_val" else "Списания", "user": message.from_user.full_name, "item": item, "qty": qty, "direction": st.get("direction", "")}
        asyncio.create_task(send_to_sheet(payload))
    
    await message.answer(f"✅ Записано строк: {len(lines)}", reply_markup=get_main_kb())
    user_states.pop(u_id, None)

@dp.message_handler(lambda m: m.text == "🧹 Ежедневная уборка")
async def daily_task(message: types.Message):
    day_idx = get_msk_time().weekday()
    task = DAILY_CLEANING_TASKS[day_idx]
    day_name = DAYS_RU[day_idx]
    user_states[message.from_user.id] = {"state": "d_c_c", "task": task, "day": day_name}
    await message.answer(f"Сегодня {day_name}.\nЗадание:\n<b>{task}</b>", parse_mode="HTML", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("✅ Выполнил(а)", "⬅ Назад"))

@dp.message_handler(lambda m: m.text == "✅ Выполнил(а)" and user_states.get(m.from_user.id, {}).get("state") == "d_c_c")
async def daily_done(message: types.Message):
    u_id = message.from_user.id
    d = user_states[u_id]
    asyncio.create_task(send_to_sheet({"sheet": "Ежедневная уборка", "user": message.from_user.full_name, "task": d["task"], "day": d["day"]}))
    await message.answer("✅ Уборка записана!", reply_markup=get_main_kb())
    user_states.pop(u_id, None)

@dp.message_handler(lambda m: m.text == "🌡 Журнал температур")
async def tmp_menu(message: types.Message):
    await message.answer("Этаж:", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("1 этаж", "2 этаж", "⬅ Назад"))

@dp.message_handler(lambda m: m.text in ["1 этаж", "2 этаж"])
async def tmp_floor(message: types.Message):
    u_id = message.from_user.id
    user_states[u_id] = {"state": "t_f", "floor": message.text, "session": f"T{int(time.time())}"}
    temp_pending[u_id] = fridges[message.text].copy()
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    for f in temp_pending[u_id]: kb.insert(f)
    await message.answer("Объект:", reply_markup=kb.add("⬅ Назад"))

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "t_f")
async def tmp_val(message: types.Message):
    if message.text not in temp_pending.get(message.from_user.id, []): return
    user_states[message.from_user.id].update({"state": "t_v", "obj": message.text})
    await message.answer(f"Температура {message.text}:")

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "t_v")
async def tmp_save(message: types.Message):
    u_id = message.from_user.id
    d = user_states[u_id]
    asyncio.create_task(send_to_sheet({"sheet": d["floor"], "user": message.from_user.full_name, "session_id": d["session"], "fridge": d["obj"], "temp": message.text}))
    temp_pending[u_id].remove(d["obj"])
    if temp_pending[u_id]:
        user_states[u_id]["state"] = "t_f"
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2); [kb.insert(f) for f in temp_pending[u_id]]
        await message.answer("Дальше:", reply_markup=kb.add("⬅ Назад"))
    else:
        user_states.pop(u_id); await message.answer("✅ Готово!", reply_markup=get_main_kb())

@dp.message_handler(lambda m: m.text == "🧹 Чеклист")
async def ch_m(message: types.Message):
    await message.answer("Чеклист:", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("Закрытие смены", "⬅ Назад"))

@dp.message_handler(lambda m: m.text == "Закрытие смены")
async def ch_s(message: types.Message):
    u_id = message.from_user.id
    user_states[u_id] = {"state": "cls", "session": f"C{int(time.time())}"}
    checklist_pending[u_id] = CLOSING_ITEMS.copy()
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2); [kb.insert(i) for i in checklist_pending[u_id]]
    await message.answer("Пункты:", reply_markup=kb.add("⬅ Назад"))

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
        await message.answer("Ок:", reply_markup=kb.add("⬅ Назад"))
    else:
        user_states.pop(u_id); await message.answer("🎉 Смена закрыта!", reply_markup=get_main_kb())

# ================= ЗАПУСК =================

async def job_reports_check():
    """Проверка заполнения отчетов"""
    await job_start_shift("CHECK") # Внутри job_start_shift добавлена логика

async def on_startup(_):
    # Приветствие
    scheduler.add_job(job_start_shift, "cron", hour=12, minute=0, args=["А"])
    scheduler.add_job(job_start_shift, "cron", hour=19, minute=0, args=["Б"])
    
    # Контрольная проверка (можно добавить вызов job_check_reports сюда)
    scheduler.start()

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
