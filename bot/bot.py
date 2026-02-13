import os
import asyncio
from typing import Dict, Any, List, Optional

import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage

# ====== Конфигурация ======
API_TOKEN = os.getenv("TG_BOT_TOKEN")
RAG_SERVER_URL = os.getenv("RAG_SERVER_URL", "http://rag-server-local:8000")

if not API_TOKEN:
    print("❌ ОШИБКА: TG_BOT_TOKEN не найден в переменных окружения!")
    print("Создайте файл .env с токеном")
    exit(1)

bot = Bot(token=API_TOKEN, parse_mode="HTML")
dp = Dispatcher(storage=MemoryStorage())


# ====== FSM Состояния ======
class ChatState(StatesGroup):
    choosing_level = State()
    choosing_mode = State()
    chatting = State()
    writing_story = State()
    story_outcome = State()


# ====== Клавиатуры ======
def level_keyboard() -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton(text="🟢 Новичок", callback_data="level:новичок")],
        [InlineKeyboardButton(text="🟡 Продвинутый", callback_data="level:средний")],
        [InlineKeyboardButton(text="🔴 Мастер", callback_data="level:мастер")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)


def mode_keyboard() -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton(text="🎯 Поля (живые ситуации)", callback_data="mode:field")],
        [InlineKeyboardButton(text="💬 Онлайн-переписка", callback_data="mode:online")],
        [InlineKeyboardButton(text="💪 Прокачка себя", callback_data="mode:self")],
        [InlineKeyboardButton(text="🆘 SOS / Срочно", callback_data="mode:sos")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)


def story_outcome_keyboard() -> InlineKeyboardMarkup:
    kb = [
        [InlineKeyboardButton(text="✅ Успех", callback_data="outcome:успех")],
        [InlineKeyboardButton(text="⚪ Нейтрально", callback_data="outcome:нейтрально")],
        [InlineKeyboardButton(text="❌ Провал", callback_data="outcome:провал")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)


# ====== Helpers ======
async def call_rag_chat(user_message: str, level: str, mode: str, history: List[Dict[str, str]]) -> str:
    filters = {"level": level, "stage": None, "channel": None, "goal": None}
    
    if mode == "field":
        filters["stage"] = ["Знакомство_холодное", "Первое_свидание", "Сближение"]
    elif mode == "online":
        filters["channel"] = ["Соцсети", "Мессенджеры/СМС"]
    elif mode == "self":
        filters["goal"] = ["саморазвитие"]
    elif mode == "sos":
        filters["stage"] = ["SOS"]

    payload = {
        "user_message": user_message,
        "convo_history": history,
        "filters": filters,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{RAG_SERVER_URL}/chat", json=payload, timeout=30) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    return f"⚠️ Сервер вернул ошибку {resp.status}: {text[:200]}"
                data = await resp.json()
                return data["answer"]
    except aiohttp.ClientError as e:
        return f"⚠️ Не могу подключиться к серверу. Убедитесь, что сервер запущен (docker-compose up)\nОшибка: {str(e)}"
    except Exception as e:
        return f"⚠️ Ошибка: {str(e)}"


async def send_story_to_server(user_id: int, level: str, mode: str, text: str, outcome: str):
    stage = None
    goal = None
    if mode == "field":
        stage = ["Свидание"]
    elif mode == "online":
        goal = ["вызвать_ответ"]
    elif mode == "self":
        goal = ["саморазвитие"]
    elif mode == "sos":
        stage = ["SOS"]

    payload = {
        "telegram_user_id": user_id,
        "level": level,
        "stage": stage,
        "channel": None,
        "goal": goal,
        "text": text,
        "outcome": outcome,
    }

    try:
        async with aiohttp.ClientSession() as session:
            await session.post(f"{RAG_SERVER_URL}/student_story", json=payload)
    except:
        pass  # Игнорируем ошибки при сохранении истории


# ====== Хендлеры ======
@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.update_data(history=[])
    await message.answer(
        "👋 Привет! Я ваш AI-наставник по социальным взаимодействиям.\n\n"
        "У меня есть база из 60+ проверенных техник.\n"
        "Выбери свой уровень:",
        reply_markup=level_keyboard()
    )
    await state.set_state(ChatState.choosing_level)


@dp.callback_query(F.data.startswith("level:"))
async def on_level_chosen(callback: CallbackQuery, state: FSMContext):
    level = callback.data.split(":", 1)[1]
    await state.update_data(level=level)
    await callback.message.edit_text(
        f"✅ Уровень: <b>{level}</b>\n\nВыбери режим работы:",
        reply_markup=mode_keyboard()
    )
    await state.set_state(ChatState.choosing_mode)


@dp.callback_query(F.data.startswith("mode:"))
async def on_mode_chosen(callback: CallbackQuery, state: FSMContext):
    mode = callback.data.split(":", 1)[1]
    await state.update_data(mode=mode)
    await callback.message.edit_text(
        "📝 Опиши свою ситуацию или задай вопрос.\n\n"
        "Я проанализирую и предложу лучшие техники из базы!"
    )
    await state.set_state(ChatState.chatting)


@dp.message(ChatState.chatting)
async def on_chat_message(message: Message, state: FSMContext):
    data = await state.get_data()
    level = data.get("level", "новичок")
    mode = data.get("mode", "field")
    history = data.get("history", [])

    history.append({"role": "user", "content": message.text})
    await state.update_data(history=history)

    wait_msg = await message.answer("🤔 Думаю над ответом...")

    answer = await call_rag_chat(
        user_message=message.text,
        level=level,
        mode=mode,
        history=history,
    )

    await wait_msg.delete()
    await message.answer(answer)

    history.append({"role": "assistant", "content": answer})
    await state.update_data(history=history)

    await message.answer(
        "Хочешь записать реальный кейс в базу опыта?",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📓 Записать кейс", callback_data="story:start")]
            ]
        )
    )


@dp.callback_query(F.data == "story:start")
async def story_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "📝 Опиши реальную историю:\n"
        "• Что сделал\n"
        "• Что ответила девушка\n"
        "• Какой был итог"
    )
    await state.set_state(ChatState.writing_story)


@dp.message(ChatState.writing_story)
async def on_story_text(message: Message, state: FSMContext):
    await state.update_data(story_text=message.text)
    await message.answer(
        "Как оценишь результат?",
        reply_markup=story_outcome_keyboard()
    )
    await state.set_state(ChatState.story_outcome)


@dp.callback_query(ChatState.story_outcome, F.data.startswith("outcome:"))
async def on_story_outcome(callback: CallbackQuery, state: FSMContext):
    outcome = callback.data.split(":", 1)[1]
    data = await state.get_data()
    story_text = data.get("story_text")
    level = data.get("level", "новичок")
    mode = data.get("mode", "field")

    await send_story_to_server(
        user_id=callback.from_user.id,
        level=level,
        mode=mode,
        text=story_text,
        outcome=outcome,
    )

    await callback.message.edit_text("✅ Кейс записан анонимно! Спасибо!")
    await state.set_state(ChatState.chatting)


@dp.message(Command("reset"))
async def cmd_reset(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "🔄 Контекст сброшен. Начнём заново!",
        reply_markup=level_keyboard()
    )
    await state.set_state(ChatState.choosing_level)


@dp.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "📚 <b>Команды бота:</b>\n\n"
        "/start — Начать новый диалог\n"
        "/reset — Сбросить контекст\n"
        "/help — Показать помощь\n\n"
        
        "<b>Как пользоваться:</b>\n"
        "1. Выбери уровень (Новичок/Продвинутый/Мастер)\n"
        "2. Выбери режим (Поля/Онлайн/Прокачка/SOS)\n"
        "3. Опиши свою ситуацию\n"
        "4. Получи рекомендации на основе 60+ техник!"
    )


async def main():
    print("🤖 Бот запущен!")
    print(f"🔗 Подключение к серверу: {RAG_SERVER_URL}")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())