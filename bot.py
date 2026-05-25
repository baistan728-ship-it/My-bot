import sys
import asyncio
import time
import json
from pyrogram import Client
from pyrogram.errors import FloodWait
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# --- НАСТРОЙКИ (ЗАПОЛНИТЕ СВОИ ДАННЫЕ) ---
API_ID = 38705543                # Ваши цифры с my.telegram.org
API_HASH = "4b82da37c766b2db3809af6186607028"       # Ваш хэш с my.telegram.org
BOT_TOKEN = "8876730835:AAHJl7rekKfIsoGp2Hnh1US079csjtFiuJE" # Токен вашего бота из @BotFather
ADMIN_ID = 7378145281            # ВАШ числовой ID в Telegram

GROUPS_FILE = "groups_list.txt"
POST_FILE = "saved_post.txt"
SETTINGS_FILE = "settings.json"

userbot = Client("my_userbot_session", api_id=API_ID, api_hash=API_HASH)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

broadcast_task = None
is_running = False

class SettingsStates(StatesGroup):
    waiting_for_hours = State()
    waiting_for_circle = State()
    waiting_for_msg_delay = State()

def load_settings():
    try:
        with open(SETTINGS_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"hours": 3.0, "circle_min": 20, "msg_sec": 10}

def save_settings(settings):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f)

def get_main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📝 Настроить Пост"), KeyboardButton(text="📁 Список Групп")],
            [KeyboardButton(text="⏱ Настройки Таймера")],
            [KeyboardButton(text="🚀 ЗАПУСК"), KeyboardButton(text="🛑 ОСТАНОВКА")]
        ],
        resize_keyboard=True
    )

@dp.message(Command("start"), F.from_user.id == ADMIN_ID)
async def start_cmd(message: Message):
    await message.answer("👋 Панель управления запущена!", reply_markup=get_main_keyboard())

@dp.message(F.text == "📁 Список Групп", F.from_user.id == ADMIN_ID)
async def view_groups(message: Message):
    try:
        with open(GROUPS_FILE, "r", encoding="utf-8") as f:
            groups = f.read()
        if not groups.strip():
            await message.answer("📁 Список групп пуст. Отправьте ссылки списком.")
        else:
            await message.answer(f"<b>Список чатов:</b>\n\n<code>{groups}</code>", parse_mode="HTML")
    except FileNotFoundError:
        await message.answer("📁 Список групп пуст.")

@dp.message(F.text == "📝 Настроить Пост", F.from_user.id == ADMIN_ID)
async def view_post(message: Message):
    try:
        with open(POST_FILE, "r", encoding="utf-8") as f:
            post = f.read()
        if not post.strip():
            await message.answer("📝 Пост пуст. Отправьте мне текст рекламы.")
        else:
            await message.answer(f"<b>Текущий post:</b>\n\n{post}", parse_mode="HTML")
    except FileNotFoundError:
        await message.answer("📝 Пост пуст.")

@dp.message(F.text == "⏱ Настройки Таймера", F.from_user.id == ADMIN_ID)
async def view_timers(message: Message, state: FSMContext):
    global is_running
    if is_running:
        await message.answer("⚠️ Нельзя менять настройки во время активной рассылки!")
        return
        
    s = load_settings()
    await message.answer(
        f"⏱ <b>Текущие таймеры:</b>\n"
        f"• Время работы: <code>{s['hours']}</code> ч.\n"
        f"• Пауза между кругами: <code>{s['circle_min']}</code> мин.\n"
        f"• Пауза сообщений: <code>{s['msg_sec']}</code> сек.\n\n"
        f"Введите <b>время работы бота (в часах)</b> (или /cancel):",
        parse_mode="HTML"
    )
    await state.set_state(SettingsStates.waiting_for_hours)

@dp.message(Command("cancel"), F.from_user.id == ADMIN_ID)
async def cancel_handler(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Настройка отменена.", reply_markup=get_main_keyboard())

@dp.message(SettingsStates.waiting_for_hours, F.from_user.id == ADMIN_ID)
async def process_hours(message: Message, state: FSMContext):
    try:
        hours = float(message.text.strip())
        await state.update_data(hours=hours)
        await message.answer("⌛️ Теперь введите <b>паузу между кругами (в минутах)</b>:")
        await state.set_state(SettingsStates.waiting_for_circle)
    except ValueError:
        await message.answer("❌ Введите число!")

@dp.message(SettingsStates.waiting_for_circle, F.from_user.id == ADMIN_ID)
async def process_circle(message: Message, state: FSMContext):
    try:
        circle = int(message.text.strip())
        await state.update_data(circle_min=circle)
        await message.answer("⚡️ Введите <b>паузу между сообщениями (в секундах)</b>:")
        await state.set_state(SettingsStates.waiting_for_msg_delay)
    except ValueError:
        await message.answer("❌ Введите целое число!")

@dp.message(SettingsStates.waiting_for_msg_delay, F.from_user.id == ADMIN_ID)
async def process_msg_delay(message: Message, state: FSMContext):
    try:
        msg_sec = int(message.text.strip())
        user_data = await state.get_data()
        new_settings = {"hours": user_data["hours"], "circle_min": user_data["circle_min"], "msg_sec": msg_sec}
        save_settings(new_settings)
        await state.clear()
        await message.answer("✅ Настройки успешно изменены!", reply_markup=get_main_keyboard())
    except ValueError:
        await message.answer("❌ Введите целое число!")

@dp.message(F.text == "🚀 ЗАПУСК", F.from_user.id == ADMIN_ID)
async def start_broadcast(message: Message):
    global broadcast_task, is_running
    if is_running:
        await message.answer("ℹ️ Рассылка уже запущена.")
        return
    is_running = True
    s = load_settings()
    broadcast_task = asyncio.create_task(broadcast_worker(hours=s["hours"], circle_delay_min=s["circle_min"], msg_delay_sec=s["msg_sec"]))
    await message.answer("⏳ Рассылка запускается...")

@dp.message(F.text == "🛑 ОСТАНОВКА", F.from_user.id == ADMIN_ID)
async def stop_broadcast(message: Message):
    global is_running
    if not is_running:
        await message.answer("ℹ️ Рассылка выключена.")
        return
    is_running = False
    await message.answer("🛑 Рассылка остановлена.")

@dp.message(F.text, F.from_user.id == ADMIN_ID)
async def save_data(message: Message):
    global is_running
    system_buttons = ["📝 Настроить Пост", "📁 Список Групп", "⏱ Настройки Таймера", "🚀 ЗАПУСК", "🛑 ОСТАНОВКА"]
    if message.text in system_buttons or message.text.startswith("/"):
        return
    if is_running:
        await message.answer("⚠️ Остановите рассылку для изменения настроек!")
        return

    text = message.text.strip()
    if text.lower() == "очистить группы":
        with open(GROUPS_FILE, "w", encoding="utf-8") as f: f.write("")
        await message.answer("🗑 Список групп очищен!")
    elif "t.me" in text or "@" in text or text.startswith("-"):
        with open(GROUPS_FILE, "a", encoding="utf-8") as f:
            for line in text.split("\n"):
                clean_line = line.strip().replace(",", "")
                if clean_line: f.write(clean_line + "\n")
        await message.answer("✅ Группы добавлены!")
    else:
        with open(POST_FILE, "w", encoding="utf-8") as f: f.write(text)
        await message.answer("✅ Пост сохранен!")

async def broadcast_worker(hours, circle_delay_min, msg_delay_sec):
    global is_running
    end_time = time.time() + (hours * 3600)
    try:
        with open(GROUPS_FILE, "r") as f: targets = [line.strip() for line in f.readlines() if line.strip()]
        with open(POST_FILE, "r", encoding="utf-8") as f: post_text = f.read()
    except Exception:
        await bot.send_message(ADMIN_ID, "❌ Файлы настроек не найдены!")
        is_running = False
        return

    await bot.send_message(ADMIN_ID, f"🚀 Рассылка началась по {len(targets)} чатам.")
    round_num = 0

    while time.time() < end_time and is_running:
        round_num += 1
        success_count = 0
        error_count = 0
        
        for target in targets:
            if not is_running or time.time() >= end_time: break
            
            if target.startswith("-") or target.isdigit(): chat_id = int(target)
            elif "t.me/" in target: chat_id = target.split("t.me/")[-1].replace("@", "").strip()
            else: chat_id = target.replace("@", "").strip()

            try:
                print(f"Отправка в: {chat_id}")
                await userbot.send_message(chat_id=chat_id, text=post_text)
                print(f"✅ Успешно: {chat_id}")
                success_count += 1
                await asyncio.sleep(msg_delay_sec)
            except FloodWait as e:
                print(f"⚠️ Ограничение FloodWait: ждем {e.value} сек.")
                error_count += 1
                await asyncio.sleep(e.value)
            except Exception as e:
                print(f"❌ Ошибка в {target}: {e}")
                error_count += 1

        await bot.send_message(
            chat_id=ADMIN_ID,
            text=f"📊 <b>Отчёт по кругу №{round_num}:</b>\n"
                 f"✅ Успешно отправлено: <code>{success_count}</code>\n"
                 f"❌ Ошибок/пропусков: <code>{error_count}</code>",
            parse_mode="HTML"
        )

        time_left = end_time - time.time()
        if time_left <= 0 or not is_running: break
        await asyncio.sleep(min(circle_delay_min * 60, time_left))

    is_running = False
    await bot.send_message(ADMIN_ID, f"⏱ Работа по таймеру завершена! Всего кругов: {round_num}")

async def main():
    await userbot.start()
    print("Юзербот успешно подключен к Telegram!")
    print("Пульт управления через кнопки включен!")
    try:
        await dp.start_polling(bot)
    finally:
        await userbot.stop()

if __name__ == "__main__":
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(main())
    except (KeyboardInterrupt, SystemExit):
        print("\nВыключено.")
