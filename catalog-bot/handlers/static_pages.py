"""Информационные экраны, не требующие пошаговой анкеты."""

from __future__ import annotations

from datetime import datetime
from html import escape

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from config import Settings
from database import Database
from keyboards import settings_keyboard
from services.navigation import Navigation
from ui import project_heading, render_screen


def _format_date(iso_value: str) -> str:
    try:
        return datetime.fromisoformat(iso_value).strftime("%d.%m.%Y")
    except ValueError:
        return "—"


def build_router(database: Database, settings: Settings, navigation: Navigation) -> Router:
    router = Router(name="static_pages")

    @router.callback_query(F.data == "info:open")
    async def show_info(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
        await callback.answer()
        if callback.from_user is None or callback.message is None:
            return
        user = await navigation.ensure_approved(
            bot, callback.message.chat.id, state, callback.from_user.id
        )
        if user is None:
            return
        stats = database.get_stats()
        lines = [
            project_heading(settings, "Информация о проекте"),
            "",
            escape(settings.project_description),
            "",
            f"<b>Запущен:</b> {_format_date(database.get_project_started_at())}",
            f"<b>Пользователей:</b> {stats.approved_users}",
            f"<b>Создано профилей:</b> {stats.profile_count}",
            f"<b>Создано объявлений:</b> {stats.listing_count}",
        ]
        if settings.support_username:
            lines.append(f"<b>Администратор:</b> {escape(settings.support_username)}")
        if settings.community_url:
            safe_url = escape(settings.community_url, quote=True)
            lines.append(f'<b>Общий чат:</b> <a href="{safe_url}">открыть</a>')
        lines.extend(
            [
                "",
                "Все профили и объявления изолированы: Создатель видит только свои данные, "
                "а Владелец управляет проектом целиком.",
            ]
        )
        await render_screen(
            bot,
            callback.message.chat.id,
            state,
            settings,
            "\n".join(lines),
            settings_keyboard(),
        )

    @router.callback_query(F.data == "settings:open")
    async def show_settings(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
        await callback.answer()
        if callback.from_user is None or callback.message is None:
            return
        user = await navigation.ensure_approved(
            bot, callback.message.chat.id, state, callback.from_user.id
        )
        if user is None:
            return
        role_title = {"owner": "Владелец / админ", "creator": "Создатель", "viewer": "Наблюдатель"}[user.role]
        text = (
            f"{project_heading(settings, 'Настройки')}\n\n"
            f"<b>Ваша роль:</b> {role_title}\n"
            f"<b>Валюта по умолчанию:</b> {escape(settings.default_currency)}\n\n"
            "В следующей версии здесь появятся персональные настройки уведомлений и языка."
        )
        await render_screen(
            bot,
            callback.message.chat.id,
            state,
            settings,
            text,
            settings_keyboard(),
        )

    return router
