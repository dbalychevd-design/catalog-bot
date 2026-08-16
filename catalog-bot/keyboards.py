"""Inline-клавиатуры Catalog Studio.

Телеграм не поддерживает цвет фона inline-кнопок, поэтому красный стиль создаётся
через единые подписи, а белые эмодзи используются в основных разделах.
"""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database import BrandProfile, Listing, ShippingTemplate, User


HOME = "nav:home"


def main_menu(user: User) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if user.can_manage_content:
        builder.button(text="👉🏻 Создать карточку 👈🏻", callback_data="listing:start")
    builder.button(text="🕊 Профили", callback_data="profile:list")
    builder.button(text="Мои объявления 🕊", callback_data="listing:list")
    builder.button(text="🕊 Настройки", callback_data="settings:open")
    builder.button(text="Информация 🕊", callback_data="info:open")
    if user.is_admin:
        builder.button(text="🛠 Админ-панель", callback_data="admin:open")
        builder.adjust(1, 2, 2, 1)
    else:
        builder.adjust(1, 2, 2)
    return builder.as_markup()


def home_only() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="← Главное меню", callback_data=HOME)]]
    )


def cancel_or_home() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="← Назад", callback_data="flow:back")],
            [InlineKeyboardButton(text="Отменить", callback_data="flow:cancel")],
            [InlineKeyboardButton(text="⌂ Главное меню", callback_data=HOME)],
        ]
    )


def access_request_keyboard(telegram_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Принять", callback_data=f"admin:approve:{telegram_id}")
    builder.button(text="Отклонить", callback_data=f"admin:decline:{telegram_id}")
    builder.button(text="Профиль", callback_data=f"admin:user:{telegram_id}")
    builder.adjust(2, 1)
    return builder.as_markup()


def profile_list_keyboard(profiles: list[BrandProfile], allow_create: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for profile in profiles:
        label = f"{profile.display_name}{' · основной' if profile.is_default else ''}"
        builder.button(text=label, callback_data=f"profile:open:{profile.id}")
    if allow_create:
        builder.button(text="Создать Custom Service", callback_data="profile:new")
    builder.button(text="← Главное меню", callback_data=HOME)
    builder.adjust(*([1] * len(profiles)), 1, 1)
    return builder.as_markup()


def profile_for_listing_keyboard(profiles: list[BrandProfile]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for profile in profiles:
        suffix = " · основной" if profile.is_default else ""
        builder.button(text=f"{profile.display_name}{suffix}", callback_data=f"listing:profile:{profile.id}")
    builder.button(text="Создать Custom Service", callback_data="profile:new_for_listing")
    builder.button(text="← Главное меню", callback_data=HOME)
    builder.adjust(*([1] * len(profiles)), 1, 1)
    return builder.as_markup()


def profile_details_keyboard(profile: BrandProfile, is_owner: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if is_owner and profile.status == "active":
        builder.button(text="Использовать для карточки", callback_data=f"listing:profile:{profile.id}")
        if not profile.is_default:
            builder.button(text="Сделать основным", callback_data=f"profile:default:{profile.id}")
        builder.button(text="Архивировать", callback_data=f"profile:archive:ask:{profile.id}")
    builder.button(text="← К профилям", callback_data="profile:list")
    builder.button(text="⌂ Главное меню", callback_data=HOME)
    builder.adjust(1, 1, 1, 1)
    return builder.as_markup()


def profile_theme_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Стандартный красный стиль", callback_data="profile:theme:red")
    builder.button(text="Свой HEX-цвет", callback_data="profile:theme:custom")
    builder.button(text="Настроить позже", callback_data="profile:theme:later")
    builder.button(text="← Назад", callback_data="flow:back")
    builder.button(text="Отменить", callback_data="flow:cancel")
    builder.adjust(1, 1, 1, 2)
    return builder.as_markup()


def logo_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Без логотипа", callback_data="profile:logo:skip")
    builder.button(text="← Назад", callback_data="flow:back")
    builder.button(text="Отменить", callback_data="flow:cancel")
    builder.adjust(1, 2)
    return builder.as_markup()


def favicon_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Использовать логотип", callback_data="profile:favicon:logo")
    builder.button(text="Настроить позже", callback_data="profile:favicon:skip")
    builder.button(text="← Назад", callback_data="flow:back")
    builder.button(text="Отменить", callback_data="flow:cancel")
    builder.adjust(1, 1, 2)
    return builder.as_markup()


def profile_confirm_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Сохранить профиль", callback_data="profile:save")
    builder.button(text="Изменить", callback_data="profile:edit")
    builder.button(text="Отменить", callback_data="flow:cancel")
    builder.adjust(1, 1, 1)
    return builder.as_markup()


def archive_confirmation_keyboard(profile_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Да, архивировать", callback_data=f"profile:archive:yes:{profile_id}")
    builder.button(text="Нет, оставить", callback_data=f"profile:open:{profile_id}")
    builder.adjust(1, 1)
    return builder.as_markup()


def shipping_template_keyboard(templates: list[ShippingTemplate]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for template in templates:
        suffix = " · основной" if template.is_default else ""
        builder.button(text=f"{template.label}{suffix}", callback_data=f"listing:shipping:{template.id}")
    builder.button(text="＋ Новые данные отправки", callback_data="shipping:new")
    builder.button(text="← Назад", callback_data="flow:back")
    builder.button(text="Отменить", callback_data="flow:cancel")
    builder.adjust(*([1] * len(templates)), 1, 2)
    return builder.as_markup()


def listing_photo_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Без фото", callback_data="listing:photo:skip")
    builder.button(text="← Назад", callback_data="flow:back")
    builder.button(text="Отменить", callback_data="flow:cancel")
    builder.adjust(1, 2)
    return builder.as_markup()


def listing_confirm_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Сохранить как черновик", callback_data="listing:save:draft")
    builder.button(text="Готово", callback_data="listing:save:ready")
    builder.button(text="Изменить", callback_data="listing:edit")
    builder.button(text="Отменить", callback_data="flow:cancel")
    builder.adjust(1, 2, 1)
    return builder.as_markup()


def listings_keyboard(listings: list[Listing], can_manage: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for listing in listings:
        status = "Черновик" if listing.status == "draft" else "Готово"
        link_mark = " · 🔗" if listing.public_slug else ""
        builder.button(
            text=f"{listing.title} · {status}{link_mark}",
            callback_data=f"listing:open:{listing.id}",
        )
    if can_manage:
        builder.button(text="👉🏻 Создать карточку 👈🏻", callback_data="listing:start")
    builder.button(text="← Главное меню", callback_data=HOME)
    builder.adjust(*([1] * len(listings)), 1, 1)
    return builder.as_markup()


def listing_details_keyboard(
    listing: Listing, is_owner: bool, public_url: str | None = None
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if public_url:
        builder.button(text="🔗 Открыть ссылку", url=public_url)
        builder.button(text="📋 Скопировать ссылку", callback_data=f"listing:copy:{listing.id}")
    if is_owner:
        builder.button(text="Заменить фото", callback_data=f"listing:photo:replace:{listing.id}")
        if listing.photo_file_id:
            builder.button(text="Удалить фото", callback_data=f"listing:photo:delete:{listing.id}")
        builder.button(text="Удалить объявление", callback_data=f"listing:delete:ask:{listing.id}")
    builder.button(text="← К объявлениям", callback_data="listing:list")
    builder.button(text="⌂ Главное меню", callback_data=HOME)
    builder.adjust(1, 1, 2 if is_owner and listing.photo_file_id else 1, 1, 1)
    return builder.as_markup()


def listing_delete_confirmation_keyboard(listing_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Да, удалить", callback_data=f"listing:delete:yes:{listing_id}")
    builder.button(text="Нет, оставить", callback_data=f"listing:open:{listing_id}")
    builder.adjust(1, 1)
    return builder.as_markup()


def settings_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="← Главное меню", callback_data=HOME)
    return builder.as_markup()


def admin_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Новые заявки", callback_data="admin:pending")
    builder.button(text="Пользователи", callback_data="admin:users")
    builder.button(text="Все профили", callback_data="admin:profiles")
    builder.button(text="Все объявления", callback_data="admin:listings")
    builder.button(text="Статистика", callback_data="admin:stats")
    builder.button(text="← Главное меню", callback_data=HOME)
    builder.adjust(2, 2, 1, 1)
    return builder.as_markup()


def users_keyboard(users: list[User], back_callback: str = "admin:open") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for user in users:
        marker = {"owner": "Админ", "creator": "Создатель", "viewer": "Наблюдатель"}[user.role]
        builder.button(text=f"{user.full_name} · {marker}", callback_data=f"admin:user:{user.telegram_id}")
    builder.button(text="← В админ-панель", callback_data=back_callback)
    builder.adjust(*([1] * len(users)), 1)
    return builder.as_markup()


def admin_profiles_keyboard(profiles: list[BrandProfile]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for profile in profiles:
        owner = profile.owner_name or str(profile.owner_id)
        builder.button(
            text=f"{profile.display_name} · {owner}",
            callback_data=f"admin:profile:{profile.id}",
        )
    builder.button(text="← В админ-панель", callback_data="admin:open")
    builder.adjust(*([1] * len(profiles)), 1)
    return builder.as_markup()


def admin_listings_keyboard(listings: list[Listing]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for listing in listings:
        owner = listing.owner_name or str(listing.owner_id)
        builder.button(
            text=f"{listing.title} · {owner}",
            callback_data=f"admin:listing:{listing.id}",
        )
    builder.button(text="← В админ-панель", callback_data="admin:open")
    builder.adjust(*([1] * len(listings)), 1)
    return builder.as_markup()


def admin_profile_details_keyboard(profile_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Архивировать", callback_data=f"admin:profile:archive:ask:{profile_id}")
    builder.button(text="← Ко всем профилям", callback_data="admin:profiles")
    builder.button(text="← В админ-панель", callback_data="admin:open")
    builder.adjust(1, 1, 1)
    return builder.as_markup()


def admin_listing_details_keyboard(listing_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Удалить", callback_data=f"admin:listing:delete:ask:{listing_id}")
    builder.button(text="← Ко всем объявлениям", callback_data="admin:listings")
    builder.button(text="← В админ-панель", callback_data="admin:open")
    builder.adjust(1, 1, 1)
    return builder.as_markup()


def admin_listing_delete_keyboard(listing_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Да, удалить", callback_data=f"admin:listing:delete:yes:{listing_id}")
    builder.button(text="Нет, оставить", callback_data=f"admin:listing:{listing_id}")
    builder.adjust(1, 1)
    return builder.as_markup()


def admin_profile_archive_keyboard(profile_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Да, архивировать", callback_data=f"admin:profile:archive:yes:{profile_id}")
    builder.button(text="Нет, оставить", callback_data=f"admin:profile:{profile_id}")
    builder.adjust(1, 1)
    return builder.as_markup()


def admin_user_keyboard(user: User) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if user.role != "owner":
        builder.button(text="Назначить Создателем", callback_data=f"admin:role:{user.telegram_id}:creator")
        builder.button(text="Назначить Наблюдателем", callback_data=f"admin:role:{user.telegram_id}:viewer")
    builder.button(text="← К пользователям", callback_data="admin:users")
    builder.button(text="← В админ-панель", callback_data="admin:open")
    builder.adjust(1, 1, 1, 1)
    return builder.as_markup()
