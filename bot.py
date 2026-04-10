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
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
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

# ================= ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =================

def get_msk_time():
    """Текущее время по Москве"""
    return datetime.now(timezone(timedelta(hours=3)))

async def send_to_sheet(payload):
    """Отправка в Google Таблицу"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(SHEET_WEBHOOK_URL, json=payload, timeout=20) as resp:
                res = await resp.text()
                logger.info(f"Google Response: {res}")
                return res
    except Exception as e:
        logger.error(f"Ошибка отправки в Google: {e}")
        return None

def get_main_kb():
    """Главное меню"""
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add("📦 Перенос", "🗑 Списание")
    kb.add("📸 Фото уборки", "🧹 Чеклист")
    kb.add("🌡 Журнал температур", "🧹 Ежедневная уборка")
    return kb

# ================= ПЛАНИРОВЩИК (НАПОМИНАНИЯ) =================

async def job_start_shift(shift_type):
    logger.info(f"Запуск рассылки о начале смены {shift_type}")
    today_str = get_msk_time().strftime("%d.%m.%Y")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(SHEET_WEBHOOK_URL, json={"action": "get_schedule"}) as resp:
                schedule = await resp.json()
        
        if schedule and len(schedule) > 0:
            headers = schedule[0]
            date_idx = next((i for i, v in enumerate(headers) if today_str in str(v)), -1)
            if date_idx != -1:
                for row in schedule[1:]:
                    u_id = str(row[0]).strip()
                    if u_id.isdigit() and shift_type in str(row[date_idx]).upper():
                        await bot.send_message(int(u_id), f"🔔 Смена {shift_type} началась (МСК)!")
    except Exception as e:
        logger.error(f"Ошибка в job_start_shift: {e}")

async def job_check_reports(shift_to_warn):
    logger.info(f"Проверка отчетов для смены {shift_to_warn}")
    today_str = get_msk_time().strftime("%d.%m.%Y")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(SHEET_WEBHOOK_URL, json={"action": "check_completion"}) as resp:
                status = await resp.json()
        
        missing = []
        if not status.get("1 этаж") or not status.get("2 этаж"): missing.append("🌡 Температуры")
        if not status.get("Чеклист") or not status.get("Ежедневная уборка"): missing.append("🧹 Уборки/Чеклисты")

        if missing:
            async with aiohttp.ClientSession() as session:
                async with session.post(SHEET_WEBHOOK_URL, json={"action": "get_schedule"}) as resp:
                    schedule = await resp.json()
            
            headers = schedule[0]
            date_idx = next((i for i, v in enumerate(headers) if today_str in str(v)), -1)
            for row in schedule[1:]:
                u_id = str(row[0]).strip()
                if u_id.isdigit() and shift_to_warn in str(row[date_idx]).upper():
                    await bot.send_message(int(u_id), "⚠️ <b>ВНИМАНИЕ!</b>\nЗабыли заполнить:\n" + "\n".join(missing), parse_mode="HTML")
    except Exception as e:
        logger.error(f"Ошибка в job_check_reports: {e}")

# ================= ОБРАБОТЧИКИ СООБЩЕНИЙ =================

@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    logger.info(f"User {message.from_user.id} started bot")
    await message.answer(f"Твой ID: <code>{message.from_user.id}</code>\nДобавь его в график.", 
                         parse_mode="HTML", reply_markup=get_main_kb())

@dp.message_handler(lambda m: m.text == "⬅ Назад")
async def back_to_menu(message: types.Message):
    u_id = message.from_user.id
    user_states.pop(u_id, None)
    checklist_pending.pop(u_id, None)
    await message.answer("Главное меню:", reply_markup=get_main_kb())

# --- ПЕРЕНОС И СПИСАНИЕ ---
@dp.message_handler(lambda m: m.text in ["📦 Перенос", "🗑 Списание"])
async def start_transfer_writeoff(message: types.Message):
    u_id = message.from_user.id
    if "Перенос" in message.text:
        user_states[u_id] = {"state": "transfer_dir"}
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True).add("Кухня → Бар", "Бар → Кухня", "⬅ Назад")
        await message.answer("Направление переноса:", reply_markup=kb)
    else:
        user_states[u_id] = {"state": "writeoff_val"}
        await message.answer("Что списываем? (каждая позиция с новой строки)\nПример:\nЛайм 1.5\nМята 0.2", 
                             reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("⬅ Назад"))

@dp.message_handler(lambda m: m.text in ["Кухня → Бар", "Бар → Кухня"])
async def transfer_dir_set(message: types.Message):
    user_states[message.from_user.id] = {"state": "transfer_val", "direction": message.text}
    await message.answer(f"Что переносим ({message.text})?", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("⬅ Назад"))

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") in ["transfer_val", "writeoff_val"])
async def process_multi_lines(message: types.Message):
    u_id = message.from_user.id
    state_data = user_states[u_id]
    lines = message.text.strip().split('\n')
    
    for line in lines:
        if not line.strip(): continue
        weight_match = re.search(r'(\d+[.,]?\d*)', line)
        weight = weight_match.group(1).replace(',', '.') if weight_match else "?"
        item_name = re.sub(r'(\d+[.,]?\d*)', '', line).strip() or "???"

        payload = {
            "sheet": "Переносы" if state_data["state"] == "transfer_val" else "Списания",
            "user": message.from_user.full_name,
            "item": item_name, "qty": weight, "direction": state_data.get("direction", "")
        }
        asyncio.create_task(send_to_sheet(payload))
    
    await message.answer(f"✅ Записано строк: {len(lines)}", reply_markup=get_main_kb())
    user_states.pop(u_id, None)

# --- ЧЕКЛИСТ (ИСПРАВЛЕННЫЙ) ---
@dp.message_handler(lambda m: m.text == "🧹 Чеклист")
async def check_menu_top(message: types.Message):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True).add("Закрытие смены", "⬅ Назад")
    await message.answer("Выберите чеклист:", reply_markup=kb)

@dp.message_handler(lambda m: m.text == "Закрытие смены")
async def closing_start_session(message: types.Message):
    u_id = message.from_user.id
    logger.info(f"User {u_id} started Closing Checklist")
    
    user_states[u_id] = {"state": "checklist_active", "session": f"C{int(time.time())}"}
    checklist_pending[u_id] = CLOSING_ITEMS.copy()
    
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    for item in checklist_pending[u_id]:
        kb.insert(item)
    kb.add("⬅ Назад")
    
    await message.answer("Пункты закрытия смены (нажмите для отметки):", reply_markup=kb)

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "checklist_active")
async def closing_process_item(message: types.Message):
    u_id = message.from_user.id
    task = message.text
    
    if task == "⬅ Назад":
        user_states.pop(u_id, None)
        await message.answer("Отменено.", reply_markup=get_main_kb())
        return

    if u_id not in checklist_pending or task not in checklist_pending[u_id]:
        return

    # Отправка
    payload = {
        "sheet": "Чеклист", 
        "user": message.from_user.full_name, 
        "session_id": user_states[u_id]["session"], 
        "task": task, "val": "✅"
    }
    asyncio.create_task(send_to_sheet(payload))

    # Удаление
    checklist_pending[u_id].remove(task)

    if checklist_pending[u_id]:
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        for i in checklist_pending[u_id]: kb.insert(i)
        kb.add("⬅ Назад")
        await message.answer(f"Готово: {task}", reply_markup=kb)
    else:
        user_states.pop(u_id, None)
        await message.answer("🎉 Все пункты выполнены! Смена закрыта.", reply_markup=get_main_kb())

# --- ТЕМПЕРАТУРЫ ---
@dp.message_handler(lambda m: m.text == "🌡 Журнал температур")
async def temps_start(message: types.Message):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True).add("1 этаж", "2 этаж", "⬅ Назад")
    await message.answer("Выберите этаж:", reply_markup=kb)

@dp.message_handler(lambda m: m.text in ["1 этаж", "2 этаж"])
async def temps_floor_select(message: types.Message):
    u_id = message.from_user.id
    user_states[u_id] = {"state": "temp_mode", "floor": message.text, "session": f"T{int(time.time())}"}
    temp_pending[u_id] = fridges[message.text].copy()
    
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    for f in temp_pending[u_id]: kb.insert(f)
    kb.add("⬅ Назад")
    await message.answer(f"Объекты ({message.text}):", reply_markup=kb)

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "temp_mode")
async def temps_fridge_choice(message: types.Message):
    u_id = message.from_user.id
    if message.text not in temp_pending.get(u_id, []): return
    user_states[u_id].update({"state": "temp_val_input", "fridge": message.text})
    await message.answer(f"Температура для {message.text}:", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("⬅ Назад"))

@dp.message_handler(lambda m: user_states.get(m.from_user.id, {}).get("state") == "temp_val_input")
async def temps_save_val(message: types.Message):
    u_id = message.from_user.id
    data = user_states[u_id]
    
    payload = {"sheet": data["floor"], "user": message.from_user.full_name, "session_id": data["session"], "fridge": data["fridge"], "temp": message.text}
    asyncio.create_task(send_to_sheet(payload))
    
    temp_pending[u_id].remove(data["fridge"])
    if temp_pending[u_id]:
        user_states[u_id]["state"] = "temp_mode"
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        for f in temp_pending[u_id]: kb.insert(f)
        kb.add("⬅ Назад")
        await message.answer(f"Записано {message.text}°. Выберите следующий:", reply_markup=kb)
    else:
        user_states.pop(u_id, None)
        await message.answer("✅ Журнал температур заполнен!", reply_markup=get_main_kb())

# --- ЕЖЕДНЕВНАЯ УБОРКА ---
@dp.message_handler(lambda m: m.text == "🧹 Ежедневная уборка")
async def daily_task_start(message: types.Message):
    task = DAILY_CLEANING_TASKS[get_msk_time().weekday()]
    user_states[message.from_user.id] = {"state": "daily_confirm", "task": task}
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True).add("✅ Выполнил(а)", "⬅ Назад")
    await message.answer(f"Задание на сегодня:\n<b>{task}</b>", parse_mode="HTML", reply_markup=kb)

@dp.message_handler(lambda m: m.text == "✅ Выполнил(а)" and user_states.get(m.from_user.id, {}).get("state") == "daily_confirm")
async def daily_task_done(message: types.Message):
    u_id = message.from_user.id
    payload = {"sheet": "Ежедневная уборка", "user": message.from_user.full_name, "task": user_states[u_id]["task"]}
    asyncio.create_task(send_to_sheet(payload))
    await message.answer("✅ Уборка отмечена!", reply_markup=get_main_kb())
    user_states.pop(u_id, None)

# ================= ЗАПУСК =================

async def on_startup(dp):
    logger.info("Бот запускается...")
    # Напоминания
    scheduler.add_job(job_start_shift, "cron", hour=12, minute=0, args=["А"])
    scheduler.add_job(job_start_shift, "cron", hour=19, minute=0, args=["Б"])
    scheduler.add_job(job_check_reports, "cron", hour=17, minute=0, args=["А"])
    scheduler.add_job(job_check_reports, "cron", hour=22, minute=0, args=["Б"])
    scheduler.start()
    logger.info("Планировщик запущен (MSK)")

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
