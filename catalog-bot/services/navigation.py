"""Общие переходы и проверка прав пользователя."""

from __future__ import annotations

from dataclasses import dataclass

from aiogram import Bot
from aiogram.fsm.context import FSMContext

from config import Settings
from database import Database, User
from keyboards import home_only, main_menu
from ui import clear_flow_keep_screen, project_heading, render_screen


@dataclass(slots=True)
class Navigation:
    database: Database
    settings: Settings

    async def show_home(self, bot: Bot, chat_id: int, state: FSMContext, user: User) -> None:
        await clear_flow_keep_screen(state)
        text = (
            f"{project_heading(self.settings, 'Приватная панель создания товарных объявлений')}\n\n"
            "Выберите действие. Ваши профили и объявления доступны только вам и администратору."
        )
        await render_screen(bot, chat_id, state, self.settings, text, main_menu(user))

    async def show_not_approved(
        self, bot: Bot, chat_id: int, state: FSMContext, status: str
    ) -> None:
        await clear_flow_keep_screen(state)
        if status == "pending":
            body = (
                "Это приватный проект. Ваша заявка уже отправлена администрации.\n\n"
                "Статус: <b>ожидает подтверждения</b>."
            )
        else:
            body = "Доступ к проекту пока не выдан. Если это ошибка, свяжитесь с администратором."
        text = f"{project_heading(self.settings, 'Доступ к проекту')}\n\n{body}"
        await render_screen(bot, chat_id, state, self.settings, text, home_only())

    async def ensure_approved(
        self, bot: Bot, chat_id: int, state: FSMContext, telegram_id: int
    ) -> User | None:
        user = self.database.get_user(telegram_id)
        if user is None or user.access_status != "approved":
            await self.show_not_approved(
                bot, chat_id, state, user.access_status if user else "pending"
            )
            return None
        return user
