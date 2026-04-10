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

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
SHEET_WEBHOOK_URL = os.getenv("SHEET_WEBHOOK_URL")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)
scheduler = AsyncIOScheduler(timezone="Europe/Moscow")

# Временные хранилища
user_states = {}  
checklist_pending = {} 
temp_pending = {}

# Константы
CLOSING_ITEMS = ["Фото бара", "Крышки закрыты", "Стоп-лист проверен", "Баклахи с водой", "Поверхности протерты", "Посуда в баре", "Кофе машина", "Раковины", "Кассовый узел", "Зона алкоголя", "Порядок на складе"]
fridges = {
    "1 этаж": ["Холодильник с водой", "Холодильник с вином", "Морозильник", "Холодильник в баре", "Холодильник с открытым вином"],
    "2 этаж": ["Холодильник с вином", "Холодильник Пепси", "Морозильник", "Холодильник для фруктов", "Сережа", "Морозильный ларь"]
}
DAILY_CLEANING_TASKS = ["Подоконники, и Сережа", "Холодильник для овощей", "Холодильник для вина", "Полки для специй и чайников, техническая зона кофемашины", "Стелаж с соками, полки для вина и пива на складе", "Бойлер от накипи, и хаус зона со льдом", "Морозильный ларь, и полки для алкоголя в баре"]
DAYS_RU = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]

def get_msk_time():
    return datetime.now(timezone(timedelta(hours=3)))

async def send_to_sheet(payload):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(SHEET_WEBHOOK_URL, json=payload, timeout=20) as resp:
                text_res = await resp.text()
                try:
                    return json.loads(text_res)
                except:
                    return text_res
    except Exception as e:
        logger.error(f"Ошибка связи с таблицей: {e}")
        return None

def get_main_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add("📦 Перенос", "🗑 Списание", "📸 Фото уборки", "🧹 Чеклист", "🌡 Журнал температур", "🧹 Ежедневная уборка")
    return kb

# ================= ИСПРАВЛЕННАЯ ЛОГИКА ПОИСКА (Игнорируем год) =================

async def job_start_shift(shift_type):
    now = get_msk_time()
    # Ищем только ДЕНЬ и МЕСЯЦ (например "10.04")
    search_pattern = now.strftime("%d.%m") 
    logger.info(f"Запуск напоминания для смены {shift_type}. Ищу колонку для {search_pattern}")

    res = await send_to_sheet({"action": "get_schedule"})
    if not isinstance(res, list) or not res: return

    headers = res[0]
    date_idx = -1
    for i, h in enumerate(headers):
        if search_pattern in str(h):
            date_idx = i
            break
    
    if date_idx != -1:
        for row in res[1:]:
            if len(row) > date_idx:
                u_id = str(row[0]).strip()
                val = str(row[date_idx]).upper()
                if u_id.isdigit() and shift_type in val:
                    try:
                        await bot.send_message(int(u_id), "🔔 Хорошей смены и не забудте заполнить температурный режим и ежедневную уборку")
                    except: pass
    else:
        logger.warning(f"Колонка для {search_pattern} не найдена (несмотря на год)")

# ================= ОБРАБОТЧИКИ =================

@dp.message_handler(commands=["test_schedule"])
async def cmd_test(message: types.Message):
    now = get_msk_time()
    search_pattern = now.strftime("%d.%m")
    await message.answer(f"🔍 Тест поиска...\nИщу колонку, где есть текст: <code>{search_pattern}</code>", parse_mode="HTML")
    
    res = await send_to_sheet({"action": "get_schedule"})
    if not isinstance(res, list):
        await message.answer("❌ Ошибка: Таблица не вернула данные.")
        return

    headers = res[0]
    date_idx = -1
    for i, h in enumerate(headers):
        if search_pattern in str(h):
            date_idx = i
            break
            
    if date_idx == -1:
        await message.answer(f"❌ Не нашел колонку для {search_pattern}.\nПервые заголовки: <code>{headers[:5]}</code>")
    else:
        found = False
        for row in res[1:]:
            if str(row[0]).strip() == str(message.from_user.id):
                found = True
                await message.answer(f"✅ Нашел тебя! Смена в колонке {headers[date_idx]}: <b>{row[date_idx]}</b>", parse_mode="HTML")
                break
        if not found:
            await message.answer("❌ Твой ID не найден в первом столбце.")

@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    await message.answer(f"ID: <code>{message.from_user.id}</code>", parse_mode="HTML", reply_markup=get_main_kb())

# Остальные функции (Переносы, Списания, Уборка, Температуры) остаются такими же
# ... (вставьте их из предыдущего рабочего кода) ...

@dp.message_handler(lambda m: m.text == "⬅ Назад")
async def back(message: types.Message):
    user_states.pop(message.from_user.id, None)
    await message.answer("Меню:", reply_markup=get_main_kb())

@dp.message_handler(lambda m: m.text in ["📦 Перенос", "🗑 Списание"])
async def st_p(message: types.Message):
    u_id = message.from_user.id
    user_states[u_id] = {"state": "tr_dir" if "Перенос" in message.text else "wr_val"}
    if "Перенос" in message.text:
        await message.answer("Направление:", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("Кухня → Бар", "Бар → Кухня", "⬅ Назад"))
    else:
        await message.answer("Что списываем? (списком)", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("⬅ Назад"))

@dp.message_handler(lambda m: m.text in ["Кухня → Бар", "Бар → Кухня"])
async def tr_d(message: types.Message):
    user_states[message.from_user.id].update({"state": "tr_val", "direction": message.text})
    await message.answer("Что переносим?", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("⬅ Назад"))

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") in ["tr_val", "wr_val"])
async def pr_r(message: types.Message):
    u_id = message.from_user.id
    st = user_states[u_id]
    lines = message.text.strip().split('\n')
    for line in lines:
        if not line.strip(): continue
        w = re.search(r'(\d+[.,]?\d*)', line); q = w.group(1).replace(',', '.') if w else "?"
        it = re.sub(r'(\d+[.,]?\d*)', '', line).strip() or "???"
        asyncio.create_task(send_to_sheet({"sheet": "Переносы" if st["state"]=="tr_val" else "Списания", "user": message.from_user.full_name, "item": it, "qty": q, "direction": st.get("direction", "")}))
    await message.answer(f"✅ Записано строк: {len(lines)}", reply_markup=get_main_kb())
    user_states.pop(u_id, None)

@dp.message_handler(lambda m: m.text == "🧹 Ежедневная уборка")
async def daily_cl(message: types.Message):
    idx = get_msk_time().weekday()
    user_states[message.from_user.id] = {"state": "d_c", "task": DAILY_CLEANING_TASKS[idx], "day": DAYS_RU[idx]}
    await message.answer(f"Задание: {DAILY_CLEANING_TASKS[idx]}", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("✅ Выполнил(а)", "⬅ Назад"))

@dp.message_handler(lambda m: m.text == "✅ Выполнил(а)" and user_states.get(m.from_user.id, {}).get("state") == "d_c")
async def daily_d(message: types.Message):
    u_id = message.from_user.id; d = user_states[u_id]
    asyncio.create_task(send_to_sheet({"sheet": "Ежедневная уборка", "user": message.from_user.full_name, "task": d["task"], "day": d["day"]}))
    await message.answer("✅ Записано!", reply_markup=get_main_kb()); user_states.pop(u_id, None)

@dp.message_handler(lambda m: m.text == "🌡 Журнал температур")
async def tmp_st(message: types.Message):
    await message.answer("Этаж:", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("1 этаж", "2 этаж", "⬅ Назад"))

@dp.message_handler(lambda m: m.text in ["1 этаж", "2 этаж"])
async def tmp_fl(message: types.Message):
    u_id = message.from_user.id; user_states[u_id] = {"state": "t_m", "floor": message.text, "session": f"T{int(time.time())}"}
    temp_pending[u_id] = fridges[message.text].copy()
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2); [kb.insert(f) for f in temp_pending[u_id]]
    await message.answer("Объект:", reply_markup=kb.add("⬅ Назад"))

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "t_m")
async def tmp_ob(message: types.Message):
    if message.text not in temp_pending.get(message.from_user.id, []): return
    user_states[message.from_user.id].update({"state": "t_v", "obj": message.text})
    await message.answer(f"Температура {message.text}:")

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "t_v")
async def tmp_sv(message: types.Message):
    u_id = message.from_user.id; d = user_states[u_id]
    asyncio.create_task(send_to_sheet({"sheet": d["floor"], "user": message.from_user.full_name, "session_id": d["session"], "fridge": d["obj"], "temp": message.text}))
    temp_pending[u_id].remove(d["obj"])
    if temp_pending[u_id]:
        user_states[u_id]["state"] = "t_m"
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2); [kb.insert(f) for f in temp_pending[u_id]]
        await message.answer("Дальше:", reply_markup=kb.add("⬅ Назад"))
    else:
        user_states.pop(u_id); await message.answer("✅ Готово!", reply_markup=get_main_kb())

@dp.message_handler(lambda m: m.text == "🧹 Чеклист")
async def ch_menu(message: types.Message):
    await message.answer("Выбор:", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("Закрытие смены", "⬅ Назад"))

@dp.message_handler(lambda m: m.text == "Закрытие смены")
async def ch_start(message: types.Message):
    u_id = message.from_user.id; user_states[u_id] = {"state": "cls", "session": f"C{int(time.time())}"}
    checklist_pending[u_id] = CLOSING_ITEMS.copy()
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2); [kb.insert(i) for i in checklist_pending[u_id]]
    await message.answer("Пункты:", reply_markup=kb.add("⬅ Назад"))

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "cls")
async def ch_step(message: types.Message):
    u_id = message.from_user.id; task = message.text
    if task == "⬅ Назад": user_states.pop(u_id, None); await message.answer("Меню:", reply_markup=get_main_kb()); return
    if u_id not in checklist_pending or task not in checklist_pending[u_id]: return
    asyncio.create_task(send_to_sheet({"sheet": "Чеклист", "user": message.from_user.full_name, "session_id": user_states[u_id]["session"], "task": task, "val": "✅"}))
    checklist_pending[u_id].remove(task)
    if checklist_pending[u_id]:
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2); [kb.insert(i) for i in checklist_pending[u_id]]
        await message.answer("Ок:", reply_markup=kb.add("⬅ Назад"))
    else:
        user_states.pop(u_id); await message.answer("🎉 Готово!", reply_markup=get_main_kb())

# ================= ЗАПУСК =================

async def on_startup(_):
    scheduler.add_job(job_start_shift, "cron", hour=12, minute=0, args=["А"])
    scheduler.add_job(job_start_shift, "cron", hour=19, minute=0, args=["Б"])
    scheduler.start()

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
