"""Создание и управление профилями Custom Service."""

from __future__ import annotations

import re
import sqlite3
from html import escape

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from config import Settings
from database import BrandProfile, Database
from keyboards import (
    HOME,
    archive_confirmation_keyboard,
    cancel_or_home,
    favicon_keyboard,
    logo_keyboard,
    profile_confirm_keyboard,
    profile_details_keyboard,
    profile_list_keyboard,
    profile_theme_keyboard,
)
from services.navigation import Navigation
from states import ListingCreation, ProfileCreation
from ui import clear_flow_keep_screen, project_heading, render_screen, try_delete_user_message

HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


def build_router(database: Database, settings: Settings, navigation: Navigation) -> Router:
    router = Router(name="profiles")

    async def show_profiles(
        bot: Bot, chat_id: int, state: FSMContext, telegram_id: int, allow_create: bool
    ) -> None:
        await clear_flow_keep_screen(state)
        profiles = database.list_profiles(telegram_id)
        if profiles:
            body = "Выберите сохранённый профиль или создайте новый."
        elif allow_create:
            body = "У вас пока нет профилей. Создайте первый Custom Service для карточек."
        else:
            body = "У вас пока нет доступных профилей."
        text = f"{project_heading(settings, 'Профили Custom Service')}\n\n{body}"
        await render_screen(
            bot,
            chat_id,
            state,
            settings,
            text,
            profile_list_keyboard(profiles, allow_create),
        )

    async def ask_profile_name(
        bot: Bot, chat_id: int, state: FSMContext, return_to_listing: bool
    ) -> None:
        await state.set_state(ProfileCreation.waiting_for_name)
        await state.update_data(return_to_listing=return_to_listing)
        text = (
            f"{project_heading(settings, 'Создание Custom Service · 1/4')}\n\n"
            "Введите название сервиса для отображения на лендинге.\n\n"
            "<i>Например: Test1 Store</i>"
        )
        await render_screen(bot, chat_id, state, settings, text, cancel_or_home())

    async def ask_logo(bot: Bot, chat_id: int, state: FSMContext) -> None:
        await state.set_state(ProfileCreation.waiting_for_logo)
        text = (
            f"{project_heading(settings, 'Создание Custom Service · 2/4')}\n\n"
            "Отправьте логотип сервиса изображением.\n\n"
            "Логотип можно добавить позднее — тогда нажмите «Без логотипа»."
        )
        await render_screen(bot, chat_id, state, settings, text, logo_keyboard())

    async def ask_theme(bot: Bot, chat_id: int, state: FSMContext) -> None:
        await state.set_state(ProfileCreation.waiting_for_theme)
        text = (
            f"{project_heading(settings, 'Создание Custom Service · 3/4')}\n\n"
            "Выберите оформление будущего лендинга.\n\n"
            "Стандартный вариант — красный стиль проекта."
        )
        await render_screen(bot, chat_id, state, settings, text, profile_theme_keyboard())

    async def ask_favicon(bot: Bot, chat_id: int, state: FSMContext) -> None:
        await state.set_state(ProfileCreation.waiting_for_favicon)
        text = (
            f"{project_heading(settings, 'Создание Custom Service · 4/4')}\n\n"
            "Отправьте favicon изображением или выберите один из быстрых вариантов.\n\n"
            "<i>Favicon — маленькая иконка, которая отображается на вкладке сайта.</i>"
        )
        await render_screen(bot, chat_id, state, settings, text, favicon_keyboard())

    async def show_profile_preview(bot: Bot, chat_id: int, state: FSMContext) -> None:
        data = await state.get_data()
        theme_titles = {
            "red": "Стандартный красный",
            "custom": f"Свой цвет {escape(data.get('primary_color') or '')}",
            "later": "Настроить позже",
        }
        logo = "загружен" if data.get("logo_file_id") else "не добавлен"
        favicon = "загружен" if data.get("favicon_file_id") else "не добавлен"
        text = (
            f"{project_heading(settings, 'Предпросмотр Custom Service')}\n\n"
            f"<b>Название:</b> {escape(data.get('profile_name', '—'))}\n"
            f"<b>Логотип:</b> {logo}\n"
            f"<b>Стиль:</b> {theme_titles.get(data.get('theme_mode'), '—')}\n"
            f"<b>Favicon:</b> {favicon}\n\n"
            "Проверьте данные перед сохранением."
        )
        await state.set_state(ProfileCreation.confirming)
        await render_screen(bot, chat_id, state, settings, text, profile_confirm_keyboard())

    async def start_listing_from_profile(
        bot: Bot, chat_id: int, state: FSMContext, profile: BrandProfile
    ) -> None:
        await state.set_state(ListingCreation.waiting_for_title)
        await state.update_data(
            selected_profile_id=profile.id,
            profile_name=profile.display_name,
        )
        text = (
            f"{project_heading(settings, 'Создание карточки · 1/4')}\n\n"
            f"<b>Custom Service:</b> {escape(profile.display_name)}\n\n"
            "Введите название товара или услуги."
        )
        await render_screen(bot, chat_id, state, settings, text, cancel_or_home())

    @router.callback_query(F.data == "profile:list")
    async def list_profiles(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
        await callback.answer()
        if callback.from_user is None or callback.message is None:
            return
        user = await navigation.ensure_approved(
            bot, callback.message.chat.id, state, callback.from_user.id
        )
        if user is None:
            return
        await show_profiles(
            bot,
            callback.message.chat.id,
            state,
            user.telegram_id,
            allow_create=user.can_manage_content,
        )

    @router.callback_query(F.data.in_({"profile:new", "profile:new_for_listing"}))
    async def create_profile(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
        await callback.answer()
        if callback.from_user is None or callback.message is None or callback.data is None:
            return
        user = await navigation.ensure_approved(
            bot, callback.message.chat.id, state, callback.from_user.id
        )
        if user is None:
            return
        if not user.can_manage_content:
            await callback.answer("Ваша роль не позволяет создавать профили", show_alert=True)
            return
        await ask_profile_name(
            bot,
            callback.message.chat.id,
            state,
            return_to_listing=callback.data == "profile:new_for_listing",
        )

    @router.message(ProfileCreation.waiting_for_name, F.text)
    async def receive_profile_name(message: Message, state: FSMContext, bot: Bot) -> None:
        if message.from_user is None:
            return
        user = await navigation.ensure_approved(bot, message.chat.id, state, message.from_user.id)
        if user is None:
            return
        name = (message.text or "").strip()
        if not 2 <= len(name) <= 80:
            await message.answer("Название должно содержать от 2 до 80 символов. Попробуйте ещё раз.")
            return
        await state.update_data(profile_name=name)
        await try_delete_user_message(message)
        await ask_logo(bot, message.chat.id, state)

    @router.message(ProfileCreation.waiting_for_logo, F.photo)
    async def receive_logo(message: Message, state: FSMContext, bot: Bot) -> None:
        await state.update_data(logo_file_id=message.photo[-1].file_id)
        await try_delete_user_message(message)
        await ask_theme(bot, message.chat.id, state)

    @router.message(ProfileCreation.waiting_for_logo)
    async def require_logo_or_action(message: Message) -> None:
        await message.answer("Отправьте изображение логотипа или нажмите «Без логотипа».")

    @router.callback_query(F.data == "profile:logo:skip", ProfileCreation.waiting_for_logo)
    async def skip_logo(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
        await callback.answer()
        if callback.message is None:
            return
        await state.update_data(logo_file_id=None)
        await ask_theme(bot, callback.message.chat.id, state)

    @router.callback_query(F.data == "profile:theme:red", ProfileCreation.waiting_for_theme)
    async def choose_red_theme(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
        await callback.answer()
        if callback.message is None:
            return
        await state.update_data(theme_mode="red", primary_color=None)
        await ask_favicon(bot, callback.message.chat.id, state)

    @router.callback_query(F.data == "profile:theme:later", ProfileCreation.waiting_for_theme)
    async def choose_later_theme(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
        await callback.answer()
        if callback.message is None:
            return
        await state.update_data(theme_mode="later", primary_color=None)
        await ask_favicon(bot, callback.message.chat.id, state)

    @router.callback_query(F.data == "profile:theme:custom", ProfileCreation.waiting_for_theme)
    async def choose_custom_theme(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
        await callback.answer()
        if callback.message is None:
            return
        await state.set_state(ProfileCreation.waiting_for_custom_color)
        text = (
            f"{project_heading(settings, 'Создание Custom Service · 3/4')}\n\n"
            "Введите основной HEX-цвет в формате <code>#C1121F</code>.\n\n"
            "Он будет использоваться на будущем лендинге."
        )
        await render_screen(bot, callback.message.chat.id, state, settings, text, cancel_or_home())

    @router.message(ProfileCreation.waiting_for_custom_color, F.text)
    async def receive_custom_color(message: Message, state: FSMContext, bot: Bot) -> None:
        color = (message.text or "").strip().upper()
        if not HEX_COLOR_RE.fullmatch(color):
            await message.answer("Введите цвет ровно в формате <code>#C1121F</code>.", parse_mode="HTML")
            return
        await state.update_data(theme_mode="custom", primary_color=color)
        await try_delete_user_message(message)
        await ask_favicon(bot, message.chat.id, state)

    @router.message(ProfileCreation.waiting_for_custom_color)
    async def require_custom_color(message: Message) -> None:
        await message.answer("Введите HEX-цвет текстом, например <code>#C1121F</code>.", parse_mode="HTML")

    @router.message(ProfileCreation.waiting_for_favicon, F.photo)
    async def receive_favicon(message: Message, state: FSMContext, bot: Bot) -> None:
        await state.update_data(favicon_file_id=message.photo[-1].file_id)
        await try_delete_user_message(message)
        await show_profile_preview(bot, message.chat.id, state)

    @router.message(ProfileCreation.waiting_for_favicon)
    async def require_favicon_or_action(message: Message) -> None:
        await message.answer("Отправьте изображение favicon или выберите действие на панели.")

    @router.callback_query(F.data == "profile:favicon:logo", ProfileCreation.waiting_for_favicon)
    async def use_logo_as_favicon(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
        await callback.answer()
        if callback.message is None:
            return
        data = await state.get_data()
        await state.update_data(favicon_file_id=data.get("logo_file_id"))
        await show_profile_preview(bot, callback.message.chat.id, state)

    @router.callback_query(F.data == "profile:favicon:skip", ProfileCreation.waiting_for_favicon)
    async def skip_favicon(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
        await callback.answer()
        if callback.message is None:
            return
        await state.update_data(favicon_file_id=None)
        await show_profile_preview(bot, callback.message.chat.id, state)

    @router.callback_query(F.data == "profile:save", ProfileCreation.confirming)
    async def save_profile(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
        await callback.answer()
        if callback.from_user is None or callback.message is None:
            return
        user = await navigation.ensure_approved(
            bot, callback.message.chat.id, state, callback.from_user.id
        )
        if user is None or not user.can_manage_content:
            return
        data = await state.get_data()
        try:
            profile = database.create_profile(
                owner_id=user.telegram_id,
                display_name=data["profile_name"],
                logo_file_id=data.get("logo_file_id"),
                theme_mode=data["theme_mode"],
                primary_color=data.get("primary_color"),
                favicon_file_id=data.get("favicon_file_id"),
            )
        except sqlite3.IntegrityError:
            await callback.answer("Профиль с таким названием уже есть", show_alert=True)
            return

        return_to_listing = bool(data.get("return_to_listing"))
        screen_message_id = data.get("screen_message_id")
        await state.clear()
        if screen_message_id:
            await state.update_data(screen_message_id=screen_message_id)

        if return_to_listing:
            await start_listing_from_profile(bot, callback.message.chat.id, state, profile)
            return

        text = (
            f"{project_heading(settings, 'Custom Service сохранён')}\n\n"
            f"<b>{escape(profile.display_name)}</b> готов к использованию в карточках."
        )
        await render_screen(
            bot,
            callback.message.chat.id,
            state,
            settings,
            text,
            profile_details_keyboard(profile, is_owner=True),
        )

    @router.callback_query(F.data == "profile:edit", ProfileCreation.confirming)
    async def edit_new_profile(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
        await callback.answer()
        if callback.message is None:
            return
        data = await state.get_data()
        await ask_profile_name(
            bot,
            callback.message.chat.id,
            state,
            return_to_listing=bool(data.get("return_to_listing")),
        )

    @router.callback_query(F.data.startswith("profile:open:"))
    async def open_profile(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
        await callback.answer()
        if callback.from_user is None or callback.message is None or callback.data is None:
            return
        user = await navigation.ensure_approved(
            bot, callback.message.chat.id, state, callback.from_user.id
        )
        if user is None:
            return
        try:
            profile_id = int(callback.data.rsplit(":", maxsplit=1)[1])
        except ValueError:
            await callback.answer("Некорректный профиль", show_alert=True)
            return
        profile = database.get_profile_for_owner(profile_id, user.telegram_id)
        if profile is None:
            await callback.answer("Профиль не найден", show_alert=True)
            return
        style = {
            "red": "Стандартный красный",
            "custom": profile.primary_color or "Свой цвет",
            "later": "Настроить позже",
        }[profile.theme_mode]
        text = (
            f"{project_heading(settings, 'Custom Service')}\n\n"
            f"<b>Название:</b> {escape(profile.display_name)}\n"
            f"<b>Стиль:</b> {escape(style)}\n"
            f"<b>Логотип:</b> {'добавлен' if profile.logo_file_id else 'не добавлен'}\n"
            f"<b>Favicon:</b> {'добавлен' if profile.favicon_file_id else 'не добавлен'}\n"
            f"<b>Статус:</b> {'основной' if profile.is_default else 'активный'}"
        )
        await render_screen(
            bot,
            callback.message.chat.id,
            state,
            settings,
            text,
            profile_details_keyboard(profile, is_owner=user.can_manage_content),
        )

    @router.callback_query(F.data.startswith("profile:default:"))
    async def make_default(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
        await callback.answer()
        if callback.from_user is None or callback.message is None or callback.data is None:
            return
        user = await navigation.ensure_approved(
            bot, callback.message.chat.id, state, callback.from_user.id
        )
        if user is None or not user.can_manage_content:
            return
        profile_id = int(callback.data.rsplit(":", maxsplit=1)[1])
        if not database.set_default_profile(profile_id, user.telegram_id):
            await callback.answer("Не удалось обновить профиль", show_alert=True)
            return
        await callback.answer("Основной профиль обновлён")
        await show_profiles(bot, callback.message.chat.id, state, user.telegram_id, True)

    @router.callback_query(F.data.startswith("profile:archive:ask:"))
    async def ask_archive_profile(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
        await callback.answer()
        if callback.from_user is None or callback.message is None or callback.data is None:
            return
        user = await navigation.ensure_approved(
            bot, callback.message.chat.id, state, callback.from_user.id
        )
        if user is None or not user.can_manage_content:
            return
        profile_id = int(callback.data.rsplit(":", maxsplit=1)[1])
        profile = database.get_profile_for_owner(profile_id, user.telegram_id)
        if profile is None:
            await callback.answer("Профиль не найден", show_alert=True)
            return
        text = (
            f"{project_heading(settings, 'Архивировать профиль?')}\n\n"
            f"Профиль <b>{escape(profile.display_name)}</b> исчезнет из выбора для новых карточек. "
            "Уже созданные объявления останутся в истории."
        )
        await render_screen(
            bot,
            callback.message.chat.id,
            state,
            settings,
            text,
            archive_confirmation_keyboard(profile.id),
        )

    @router.callback_query(F.data.startswith("profile:archive:yes:"))
    async def archive_profile(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
        await callback.answer()
        if callback.from_user is None or callback.message is None or callback.data is None:
            return
        user = await navigation.ensure_approved(
            bot, callback.message.chat.id, state, callback.from_user.id
        )
        if user is None or not user.can_manage_content:
            return
        profile_id = int(callback.data.rsplit(":", maxsplit=1)[1])
        if not database.archive_profile(profile_id, user.telegram_id):
            await callback.answer("Профиль уже недоступен", show_alert=True)
            return
        await callback.answer("Профиль архивирован")
        await show_profiles(bot, callback.message.chat.id, state, user.telegram_id, True)

    @router.callback_query(F.data == "flow:back", ProfileCreation.waiting_for_name)
    async def profile_back_from_name(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
        await callback.answer()
        if callback.from_user is None or callback.message is None:
            return
        user = await navigation.ensure_approved(
            bot, callback.message.chat.id, state, callback.from_user.id
        )
        if user:
            await show_profiles(bot, callback.message.chat.id, state, user.telegram_id, user.can_manage_content)

    @router.callback_query(F.data == "flow:back", ProfileCreation.waiting_for_logo)
    async def profile_back_to_name(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
        await callback.answer()
        if callback.message is None:
            return
        data = await state.get_data()
        await ask_profile_name(bot, callback.message.chat.id, state, bool(data.get("return_to_listing")))

    @router.callback_query(F.data == "flow:back", ProfileCreation.waiting_for_theme)
    async def profile_back_to_logo(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
        await callback.answer()
        if callback.message is not None:
            await ask_logo(bot, callback.message.chat.id, state)

    @router.callback_query(F.data == "flow:back", ProfileCreation.waiting_for_custom_color)
    async def profile_back_to_theme(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
        await callback.answer()
        if callback.message is not None:
            await ask_theme(bot, callback.message.chat.id, state)

    @router.callback_query(F.data == "flow:back", ProfileCreation.waiting_for_favicon)
    async def profile_back_to_theme_from_favicon(
        callback: CallbackQuery, state: FSMContext, bot: Bot
    ) -> None:
        await callback.answer()
        if callback.message is not None:
            await ask_theme(bot, callback.message.chat.id, state)

    @router.callback_query(F.data == "flow:back", ProfileCreation.confirming)
    async def profile_back_to_favicon(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
        await callback.answer()
        if callback.message is not None:
            await ask_favicon(bot, callback.message.chat.id, state)

    return router
