"""Административные сценарии: заявки, роли и статистика."""

from __future__ import annotations

from html import escape

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from config import Settings
from database import Database, User
from keyboards import (
    access_request_keyboard,
    admin_listing_delete_keyboard,
    admin_listing_details_keyboard,
    admin_listings_keyboard,
    admin_menu_keyboard,
    admin_profile_archive_keyboard,
    admin_profile_details_keyboard,
    admin_profiles_keyboard,
    admin_user_keyboard,
    users_keyboard,
)
from services.navigation import Navigation
from ui import project_heading, render_screen, user_label


def build_router(database: Database, settings: Settings, navigation: Navigation) -> Router:
    router = Router(name="admin")

    async def require_admin(callback: CallbackQuery, state: FSMContext, bot: Bot) -> User | None:
        if callback.from_user is None or callback.message is None:
            return None
        user = await navigation.ensure_approved(
            bot, callback.message.chat.id, state, callback.from_user.id
        )
        if user is None:
            return None
        if not user.is_admin:
            await callback.answer("Недостаточно прав", show_alert=True)
            return None
        return user

    @router.callback_query(F.data == "admin:open")
    async def open_admin(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
        await callback.answer()
        user = await require_admin(callback, state, bot)
        if user is None or callback.message is None:
            return
        stats = database.get_stats()
        text = (
            f"{project_heading(settings, 'Административная панель')}\n\n"
            f"<b>Пользователи:</b> {stats.approved_users}\n"
            f"<b>Новые заявки:</b> {stats.pending_users}\n"
            f"<b>Профили:</b> {stats.profile_count}\n"
            f"<b>Объявления:</b> {stats.listing_count}\n\n"
            "Выберите раздел управления."
        )
        await render_screen(
            bot, callback.message.chat.id, state, settings, text, admin_menu_keyboard()
        )

    @router.callback_query(F.data == "admin:pending")
    async def pending_users(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
        await callback.answer()
        user = await require_admin(callback, state, bot)
        if user is None or callback.message is None:
            return
        pending = database.list_pending_users()
        if pending:
            body = "Выберите заявку, чтобы принять или отклонить пользователя."
        else:
            body = "Новых заявок нет."
        text = f"{project_heading(settings, 'Новые заявки')}\n\n{body}"
        await render_screen(
            bot,
            callback.message.chat.id,
            state,
            settings,
            text,
            users_keyboard(pending),
        )

    @router.callback_query(F.data == "admin:users")
    async def users_list(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
        await callback.answer()
        user = await require_admin(callback, state, bot)
        if user is None or callback.message is None:
            return
        users = database.list_approved_users()
        text = (
            f"{project_heading(settings, 'Пользователи')}\n\n"
            "Нажмите на пользователя, чтобы посмотреть роль или изменить доступ."
        )
        await render_screen(
            bot,
            callback.message.chat.id,
            state,
            settings,
            text,
            users_keyboard(users),
        )

    @router.callback_query(F.data == "admin:stats")
    async def project_stats(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
        await callback.answer()
        user = await require_admin(callback, state, bot)
        if user is None or callback.message is None:
            return
        stats = database.get_stats()
        text = (
            f"{project_heading(settings, 'Статистика проекта')}\n\n"
            f"<b>Одобренных пользователей:</b> {stats.approved_users}\n"
            f"<b>Заявок ожидают решения:</b> {stats.pending_users}\n"
            f"<b>Активных профилей:</b> {stats.profile_count}\n"
            f"<b>Всего объявлений:</b> {stats.listing_count}\n\n"
            "Статистика обновляется из базы данных."
        )
        await render_screen(
            bot, callback.message.chat.id, state, settings, text, admin_menu_keyboard()
        )

    @router.callback_query(F.data.startswith("admin:user:"))
    async def user_details(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
        await callback.answer()
        admin = await require_admin(callback, state, bot)
        if admin is None or callback.message is None or callback.data is None:
            return
        try:
            target_id = int(callback.data.rsplit(":", maxsplit=1)[1])
        except ValueError:
            await callback.answer("Некорректный пользователь", show_alert=True)
            return
        target = database.get_user(target_id)
        if target is None:
            await callback.answer("Пользователь не найден", show_alert=True)
            return

        role_titles = {"owner": "Владелец / админ", "creator": "Создатель", "viewer": "Наблюдатель"}
        status_titles = {"pending": "Ожидает решения", "approved": "Одобрен", "declined": "Отклонён"}
        text = (
            f"{project_heading(settings, 'Профиль пользователя')}\n\n"
            f"{user_label(target.username, target.full_name, target.telegram_id)}\n\n"
            f"<b>Роль:</b> {role_titles[target.role]}\n"
            f"<b>Статус:</b> {status_titles[target.access_status]}"
        )
        keyboard = (
            access_request_keyboard(target.telegram_id)
            if target.access_status == "pending"
            else admin_user_keyboard(target)
        )
        await render_screen(bot, callback.message.chat.id, state, settings, text, keyboard)

    @router.callback_query(F.data.startswith("admin:approve:"))
    async def approve_user(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
        await callback.answer()
        admin = await require_admin(callback, state, bot)
        if admin is None or callback.data is None:
            return
        try:
            target_id = int(callback.data.rsplit(":", maxsplit=1)[1])
        except ValueError:
            await callback.answer("Некорректная заявка", show_alert=True)
            return
        target = database.approve_user(target_id)
        if target is None:
            await callback.answer("Заявка не найдена", show_alert=True)
            return

        try:
            await bot.send_message(
                target_id,
                "<b>Доступ одобрен.</b>\n\nВведите /start, чтобы открыть главное меню проекта.",
                parse_mode="HTML",
            )
        except Exception:
            pass

        if callback.message:
            try:
                await callback.message.edit_text(
                    f"<b>Заявка одобрена</b>\n\n{user_label(target.username, target.full_name, target.telegram_id)}\n\n"
                    "Роль: <b>Создатель</b>",
                    parse_mode="HTML",
                )
            except Exception:
                pass

    @router.callback_query(F.data.startswith("admin:decline:"))
    async def decline_user(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
        await callback.answer()
        admin = await require_admin(callback, state, bot)
        if admin is None or callback.data is None:
            return
        try:
            target_id = int(callback.data.rsplit(":", maxsplit=1)[1])
        except ValueError:
            await callback.answer("Некорректная заявка", show_alert=True)
            return
        target = database.decline_user(target_id)
        if target is None:
            await callback.answer("Заявка не найдена", show_alert=True)
            return

        try:
            await bot.send_message(target_id, "Доступ к проекту пока не выдан.")
        except Exception:
            pass

        if callback.message:
            try:
                await callback.message.edit_text(
                    f"<b>Заявка отклонена</b>\n\n{user_label(target.username, target.full_name, target.telegram_id)}",
                    parse_mode="HTML",
                )
            except Exception:
                pass

    @router.callback_query(F.data.startswith("admin:role:"))
    async def change_role(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
        await callback.answer()
        admin = await require_admin(callback, state, bot)
        if admin is None or callback.message is None or callback.data is None:
            return
        parts = callback.data.split(":")
        if len(parts) != 4:
            await callback.answer("Некорректная роль", show_alert=True)
            return
        _, _, raw_target_id, role = parts
        try:
            target_id = int(raw_target_id)
        except ValueError:
            await callback.answer("Некорректный пользователь", show_alert=True)
            return
        if target_id == settings.admin_id:
            await callback.answer("Нельзя изменить роль владельца", show_alert=True)
            return
        if role not in {"creator", "viewer"}:
            await callback.answer("Некорректная роль", show_alert=True)
            return
        target = database.set_user_role(target_id, role)  # type: ignore[arg-type]
        if target is None:
            await callback.answer("Пользователь не найден", show_alert=True)
            return
        title = "Создатель" if role == "creator" else "Наблюдатель"
        await callback.answer(f"Роль: {title}")
        text = (
            f"{project_heading(settings, 'Профиль пользователя')}\n\n"
            f"{user_label(target.username, target.full_name, target.telegram_id)}\n\n"
            f"<b>Роль:</b> {title}\n<b>Статус:</b> Одобрен"
        )
        await render_screen(
            bot,
            callback.message.chat.id,
            state,
            settings,
            text,
            admin_user_keyboard(target),
        )

    @router.callback_query(F.data == "admin:profiles")
    async def all_profiles(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
        await callback.answer()
        admin = await require_admin(callback, state, bot)
        if admin is None or callback.message is None:
            return
        profiles = database.list_all_profiles()
        body = "Выберите профиль для просмотра или архивирования." if profiles else "Активных профилей пока нет."
        text = f"{project_heading(settings, 'Все профили')}\n\n{body}"
        await render_screen(
            bot, callback.message.chat.id, state, settings, text, admin_profiles_keyboard(profiles)
        )

    @router.callback_query(F.data == "admin:listings")
    async def all_listings(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
        await callback.answer()
        admin = await require_admin(callback, state, bot)
        if admin is None or callback.message is None:
            return
        listings = database.list_all_listings()
        body = "Выберите объявление для просмотра или удаления." if listings else "Объявлений пока нет."
        text = f"{project_heading(settings, 'Все объявления')}\n\n{body}"
        await render_screen(
            bot, callback.message.chat.id, state, settings, text, admin_listings_keyboard(listings)
        )

    @router.callback_query(F.data.regexp(r"^admin:profile:\d+$"))
    async def admin_profile_details(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
        await callback.answer()
        admin = await require_admin(callback, state, bot)
        if admin is None or callback.message is None or callback.data is None:
            return
        parts = callback.data.split(":")
        if len(parts) != 3 or parts[1] != "profile":
            return
        try:
            profile_id = int(parts[2])
        except ValueError:
            await callback.answer("Некорректный профиль", show_alert=True)
            return
        profile = database.get_profile_any(profile_id)
        if profile is None:
            await callback.answer("Профиль не найден", show_alert=True)
            return
        style = {"red": "Стандартный красный", "custom": profile.primary_color or "Свой цвет", "later": "Позже"}[profile.theme_mode]
        text = (
            f"{project_heading(settings, 'Профиль пользователя')}\n\n"
            f"<b>Название:</b> {escape(profile.display_name)}\n"
            f"<b>Владелец:</b> {escape(profile.owner_name or str(profile.owner_id))}\n"
            f"<b>Стиль:</b> {escape(style)}\n"
            f"<b>Логотип:</b> {'добавлен' if profile.logo_file_id else 'не добавлен'}\n"
            f"<b>Favicon:</b> {'добавлен' if profile.favicon_file_id else 'не добавлен'}"
        )
        await render_screen(
            bot,
            callback.message.chat.id,
            state,
            settings,
            text,
            admin_profile_details_keyboard(profile.id),
        )

    @router.callback_query(F.data.startswith("admin:profile:archive:ask:"))
    async def admin_ask_archive_profile(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
        await callback.answer()
        admin = await require_admin(callback, state, bot)
        if admin is None or callback.message is None or callback.data is None:
            return
        try:
            profile_id = int(callback.data.rsplit(":", maxsplit=1)[1])
        except ValueError:
            return
        profile = database.get_profile_any(profile_id)
        if profile is None:
            await callback.answer("Профиль не найден", show_alert=True)
            return
        text = (
            f"{project_heading(settings, 'Архивировать профиль?')}\n\n"
            f"Профиль <b>{escape(profile.display_name)}</b> пользователя "
            f"<b>{escape(profile.owner_name or str(profile.owner_id))}</b> исчезнет из новых карточек."
        )
        await render_screen(
            bot,
            callback.message.chat.id,
            state,
            settings,
            text,
            admin_profile_archive_keyboard(profile.id),
        )

    @router.callback_query(F.data.startswith("admin:profile:archive:yes:"))
    async def admin_archive_profile(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
        await callback.answer()
        admin = await require_admin(callback, state, bot)
        if admin is None or callback.message is None or callback.data is None:
            return
        try:
            profile_id = int(callback.data.rsplit(":", maxsplit=1)[1])
        except ValueError:
            return
        if not database.archive_profile_as_admin(profile_id):
            await callback.answer("Профиль уже недоступен", show_alert=True)
            return
        await callback.answer("Профиль архивирован")
        profiles = database.list_all_profiles()
        text = f"{project_heading(settings, 'Все профили')}\n\nВыберите профиль для просмотра или архивирования."
        await render_screen(
            bot, callback.message.chat.id, state, settings, text, admin_profiles_keyboard(profiles)
        )

    @router.callback_query(F.data.regexp(r"^admin:listing:\d+$"))
    async def admin_listing_details(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
        await callback.answer()
        admin = await require_admin(callback, state, bot)
        if admin is None or callback.message is None or callback.data is None:
            return
        parts = callback.data.split(":")
        if len(parts) != 3 or parts[1] != "listing":
            return
        try:
            listing_id = int(parts[2])
        except ValueError:
            await callback.answer("Некорректное объявление", show_alert=True)
            return
        listing = database.get_listing_any(listing_id)
        if listing is None:
            await callback.answer("Объявление не найдено", show_alert=True)
            return
        status = "Черновик" if listing.status == "draft" else "Готово к публикации"
        text = (
            f"{project_heading(settings, 'Объявление пользователя')}\n\n"
            f"<b>{escape(listing.title)}</b>\n"
            f"<b>Владелец:</b> {escape(listing.owner_name or str(listing.owner_id))}\n"
            f"<b>Профиль:</b> {escape(listing.profile_name or '—')}\n"
            f"<b>Цена:</b> {escape(listing.formatted_price)}\n"
            f"<b>Доставка:</b> {escape(listing.delivery_info)}\n"
            f"<b>Статус:</b> {status}"
        )
        await render_screen(
            bot,
            callback.message.chat.id,
            state,
            settings,
            text,
            admin_listing_details_keyboard(listing.id),
        )

    @router.callback_query(F.data.startswith("admin:listing:delete:ask:"))
    async def admin_ask_delete_listing(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
        await callback.answer()
        admin = await require_admin(callback, state, bot)
        if admin is None or callback.message is None or callback.data is None:
            return
        try:
            listing_id = int(callback.data.rsplit(":", maxsplit=1)[1])
        except ValueError:
            return
        listing = database.get_listing_any(listing_id)
        if listing is None:
            await callback.answer("Объявление не найдено", show_alert=True)
            return
        text = (
            f"{project_heading(settings, 'Удалить объявление?')}\n\n"
            f"<b>{escape(listing.title)}</b> пользователя "
            f"<b>{escape(listing.owner_name or str(listing.owner_id))}</b> будет удалено без восстановления."
        )
        await render_screen(
            bot,
            callback.message.chat.id,
            state,
            settings,
            text,
            admin_listing_delete_keyboard(listing.id),
        )

    @router.callback_query(F.data.startswith("admin:listing:delete:yes:"))
    async def admin_delete_listing(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
        await callback.answer()
        admin = await require_admin(callback, state, bot)
        if admin is None or callback.message is None or callback.data is None:
            return
        try:
            listing_id = int(callback.data.rsplit(":", maxsplit=1)[1])
        except ValueError:
            return
        if not database.delete_listing_as_admin(listing_id):
            await callback.answer("Объявление уже удалено", show_alert=True)
            return
        await callback.answer("Объявление удалено")
        listings = database.list_all_listings()
        text = f"{project_heading(settings, 'Все объявления')}\n\nВыберите объявление для просмотра или удаления."
        await render_screen(
            bot, callback.message.chat.id, state, settings, text, admin_listings_keyboard(listings)
        )

    return router
