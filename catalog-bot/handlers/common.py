"""Старт, приватный доступ и базовая навигация."""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from config import Settings
from database import Database
from keyboards import HOME, access_request_keyboard
from services.navigation import Navigation
from ui import user_label


def build_router(database: Database, settings: Settings, navigation: Navigation) -> Router:
    router = Router(name="common")

    @router.message(CommandStart())
    async def command_start(message: Message, state: FSMContext, bot: Bot) -> None:
        if message.from_user is None:
            return
        telegram_user = message.from_user
        user, is_new_request = database.request_access(
            telegram_id=telegram_user.id,
            username=telegram_user.username,
            full_name=telegram_user.full_name,
        )

        if user.access_status == "approved":
            await navigation.show_home(bot, message.chat.id, state, user)
            return

        await navigation.show_not_approved(bot, message.chat.id, state, user.access_status)
        if not is_new_request:
            return

        admin_text = (
            "<b>Новая заявка на доступ</b>\n\n"
            f"{user_label(telegram_user.username, telegram_user.full_name, telegram_user.id)}\n\n"
            "Роль после одобрения: <b>Создатель</b>"
        )
        try:
            await bot.send_message(
                chat_id=settings.admin_id,
                text=admin_text,
                reply_markup=access_request_keyboard(telegram_user.id),
                parse_mode="HTML",
            )
        except Exception:
            # Заявка уже сохранена в SQLite; недоступность Telegram не должна удалять её.
            pass

    @router.callback_query(F.data == HOME)
    async def go_home(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
        await callback.answer()
        if callback.from_user is None or callback.message is None:
            return
        user = await navigation.ensure_approved(
            bot, callback.message.chat.id, state, callback.from_user.id
        )
        if user:
            await navigation.show_home(bot, callback.message.chat.id, state, user)

    @router.callback_query(F.data == "flow:cancel")
    async def cancel_flow(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
        await callback.answer("Создание отменено")
        if callback.from_user is None or callback.message is None:
            return
        user = await navigation.ensure_approved(
            bot, callback.message.chat.id, state, callback.from_user.id
        )
        if user:
            await navigation.show_home(bot, callback.message.chat.id, state, user)

    return router



