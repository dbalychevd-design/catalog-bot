"""Создание и просмотр приватных товарных объявлений."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from html import escape

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State
from aiogram.types import CallbackQuery, Message

from config import Settings
from database import Database, Listing
from keyboards import (
    cancel_or_home,
    listing_confirm_keyboard,
    listing_delete_confirmation_keyboard,
    listing_details_keyboard,
    listing_photo_keyboard,
    listings_keyboard,
    profile_for_listing_keyboard,
    shipping_template_keyboard,
)
from services.navigation import Navigation
from states import ListingCreation, ListingPhotoEdit, ShippingTemplateCreation
from ui import clear_flow_keep_screen, project_heading, render_screen, try_delete_user_message


def parse_price_to_cents(raw_value: str) -> int | None:
    """Принимает 120, 120.50 или 120,50 и возвращает число центов."""
    normalized = raw_value.strip().replace(" ", "").replace(",", ".")
    try:
        value = Decimal(normalized)
    except InvalidOperation:
        return None
    if not value.is_finite() or value < 0 or value > Decimal("99999999.99"):
        return None
    cents = (value * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(cents)


def _delivery_field(delivery_info: str, field_name: str) -> str:
    prefix = f"{field_name}:"
    for line in delivery_info.splitlines():
        if line.strip().startswith(prefix):
            return line.split(":", 1)[1].strip() or "—"
    return delivery_info.strip() if field_name == "Город" and delivery_info.strip() else "—"


def build_router(database: Database, settings: Settings, navigation: Navigation) -> Router:
    router = Router(name="listings")

    def public_url(listing: Listing) -> str | None:
        if not listing.public_slug:
            return None
        return f"{settings.public_base_url}/p/{listing.public_slug}"

    async def choose_profile(bot: Bot, chat_id: int, state: FSMContext, user_id: int) -> None:
        profiles = database.list_profiles(user_id)
        await state.set_state(ListingCreation.choosing_profile)
        if profiles:
            body = "Выберите Custom Service. Он определит название и стиль будущего лендинга."
        else:
            body = "Сначала создайте первый Custom Service — у карточки должен быть профиль бренда."
        text = f"{project_heading(settings, 'Создание карточки')}\n\n{body}"
        await render_screen(
            bot,
            chat_id,
            state,
            settings,
            text,
            profile_for_listing_keyboard(profiles),
        )

    async def ask_title(bot: Bot, chat_id: int, state: FSMContext, profile_name: str) -> None:
        await state.set_state(ListingCreation.waiting_for_title)
        text = (
            f"{project_heading(settings, 'Создание карточки · 1/4')}\n\n"
            f"<b>Custom Service:</b> {escape(profile_name)}\n\n"
            "Введите название товара или услуги."
        )
        await render_screen(bot, chat_id, state, settings, text, cancel_or_home())

    async def ask_price(bot: Bot, chat_id: int, state: FSMContext) -> None:
        await state.set_state(ListingCreation.waiting_for_price)
        text = (
            f"{project_heading(settings, 'Создание карточки · 2/4')}\n\n"
            f"Введите цену в <b>{escape(settings.default_currency)}</b>.\n\n"
            "<i>Например: 120 или 120.50</i>"
        )
        await render_screen(bot, chat_id, state, settings, text, cancel_or_home())

    async def ask_shipping(bot: Bot, chat_id: int, state: FSMContext, owner_id: int) -> None:
        await state.set_state(ListingCreation.choosing_shipping)
        templates = database.list_shipping_templates(owner_id)
        body = (
            "Выберите сохранённые публичные данные отправки или создайте новый шаблон."
            if templates
            else "Создайте первый шаблон публичных данных отправки для карточки."
        )
        text = f"{project_heading(settings, 'Создание карточки · 3/4')}\n\n{body}"
        await render_screen(
            bot, chat_id, state, settings, text, shipping_template_keyboard(templates)
        )

    async def ask_shipping_label(bot: Bot, chat_id: int, state: FSMContext) -> None:
        await state.set_state(ShippingTemplateCreation.waiting_for_label)
        text = (
            f"{project_heading(settings, 'Новые данные отправки · 1/5')}\n\n"
            "Введите название шаблона.\n"
            "Например: Основной или Магазин · Zürich."
        )
        await render_screen(bot, chat_id, state, settings, text, cancel_or_home())

    async def ask_shipping_field(
        bot: Bot,
        chat_id: int,
        state: FSMContext,
        next_state: State,
        step: str,
        prompt: str,
    ) -> None:
        await state.set_state(next_state)
        text = f"{project_heading(settings, f'Новые данные отправки · {step}/5')}\n\n{prompt}"
        await render_screen(bot, chat_id, state, settings, text, cancel_or_home())

    @router.callback_query(
        F.data.startswith("listing:shipping:"), ListingCreation.choosing_shipping
    )
    async def choose_shipping_template(
        callback: CallbackQuery, state: FSMContext, bot: Bot
    ) -> None:
        await callback.answer()
        if callback.from_user is None or callback.message is None or callback.data is None:
            return
        user = await navigation.ensure_approved(
            bot, callback.message.chat.id, state, callback.from_user.id
        )
        if user is None or not user.can_manage_content:
            return
        try:
            template_id = int(callback.data.rsplit(":", maxsplit=1)[1])
        except ValueError:
            await callback.answer("Некорректный шаблон", show_alert=True)
            return
        template = database.get_shipping_template_for_owner(template_id, user.telegram_id)
        if template is None:
            await callback.answer("Шаблон не найден", show_alert=True)
            return
        await state.update_data(
            shipping_template_id=template.id,
            delivery_info=template.formatted(),
        )
        await ask_photo(bot, callback.message.chat.id, state)

    @router.callback_query(F.data == "shipping:new", ListingCreation.choosing_shipping)
    async def create_shipping_template(
        callback: CallbackQuery, state: FSMContext, bot: Bot
    ) -> None:
        await callback.answer()
        if callback.message is not None:
            await ask_shipping_label(bot, callback.message.chat.id, state)

    @router.message(ShippingTemplateCreation.waiting_for_label, F.text)
    async def receive_shipping_label(message: Message, state: FSMContext, bot: Bot) -> None:
        value = (message.text or "").strip()
        if not 2 <= len(value) <= 60:
            await message.answer("Название шаблона должно содержать от 2 до 60 символов.")
            return
        await state.update_data(shipping_label=value)
        await try_delete_user_message(message)
        await ask_shipping_field(
            bot, message.chat.id, state, ShippingTemplateCreation.waiting_for_city,
            "2", "Введите город отправки. Например: Zürich",
        )

    @router.message(ShippingTemplateCreation.waiting_for_city, F.text)
    async def receive_shipping_city(message: Message, state: FSMContext, bot: Bot) -> None:
        value = (message.text or "").strip()
        if not 2 <= len(value) <= 80:
            await message.answer("Введите город от 2 до 80 символов.")
            return
        await state.update_data(shipping_city=value)
        await try_delete_user_message(message)
        await ask_shipping_field(
            bot, message.chat.id, state, ShippingTemplateCreation.waiting_for_zip_code,
            "3", "Введите ZIP-код.",
        )

    @router.message(ShippingTemplateCreation.waiting_for_zip_code, F.text)
    async def receive_shipping_zip(message: Message, state: FSMContext, bot: Bot) -> None:
        value = (message.text or "").strip()
        if not 2 <= len(value) <= 20:
            await message.answer("Введите корректный ZIP-код.")
            return
        await state.update_data(shipping_zip_code=value)
        await try_delete_user_message(message)
        await ask_shipping_field(
            bot, message.chat.id, state, ShippingTemplateCreation.waiting_for_contact_name,
            "4", "Введите имя и фамилию отправителя или контактного лица.",
        )

    @router.message(ShippingTemplateCreation.waiting_for_contact_name, F.text)
    async def receive_shipping_contact(message: Message, state: FSMContext, bot: Bot) -> None:
        value = (message.text or "").strip()
        if not 2 <= len(value) <= 120:
            await message.answer("Введите имя и фамилию от 2 до 120 символов.")
            return
        await state.update_data(shipping_contact_name=value)
        await try_delete_user_message(message)
        await ask_shipping_field(
            bot, message.chat.id, state, ShippingTemplateCreation.waiting_for_street,
            "5", "Введите улицу и номер дома.",
        )

    @router.message(ShippingTemplateCreation.waiting_for_street, F.text)
    async def receive_shipping_street(message: Message, state: FSMContext, bot: Bot) -> None:
        if message.from_user is None:
            return
        value = (message.text or "").strip()
        if not 2 <= len(value) <= 160:
            await message.answer("Введите улицу и номер дома от 2 до 160 символов.")
            return
        user = await navigation.ensure_approved(bot, message.chat.id, state, message.from_user.id)
        if user is None or not user.can_manage_content:
            return
        data = await state.get_data()
        template = database.create_shipping_template(
            owner_id=user.telegram_id,
            label=data["shipping_label"],
            city=data["shipping_city"],
            zip_code=data["shipping_zip_code"],
            contact_name=data["shipping_contact_name"],
            street=value,
        )
        await state.update_data(
            shipping_template_id=template.id,
            delivery_info=template.formatted(),
        )
        await try_delete_user_message(message)
        await ask_photo(bot, message.chat.id, state)

    async def ask_photo(bot: Bot, chat_id: int, state: FSMContext) -> None:
        await state.set_state(ListingCreation.waiting_for_photo)
        text = (
            f"{project_heading(settings, 'Создание карточки · 4/4')}\n\n"
            "Отправьте фотографию товара.\n\n"
            "Если фото пока нет, можно продолжить без него и добавить позже."
        )
        await render_screen(bot, chat_id, state, settings, text, listing_photo_keyboard())

    async def show_listing_preview(bot: Bot, chat_id: int, state: FSMContext) -> None:
        data = await state.get_data()
        photo = "добавлено" if data.get("listing_photo_file_id") else "не добавлено"
        price_cents = int(data["price_cents"])
        whole, fraction = divmod(price_cents, 100)
        price = f"{whole:,}.{fraction:02d}".replace(",", " ")
        text = (
            f"{project_heading(settings, 'Предпросмотр объявления')}\n\n"
            f"<b>Custom Service:</b> {escape(data['profile_name'])}\n"
            f"<b>Название:</b> {escape(data['listing_title'])}\n"
            f"<b>Цена:</b> {price} {escape(settings.default_currency)}\n"
            f"<b>Доставка:</b> {escape(data['delivery_info'])}\n"
            f"<b>Фото:</b> {photo}\n\n"
            "Сохраните черновик или отметьте карточку готовой к публикации."
        )
        await state.set_state(ListingCreation.confirming)
        await state.update_data(
            requested_media_kind="listing",
            requested_media_file_id=data.get("listing_photo_file_id"),
        )
        await render_screen(bot, chat_id, state, settings, text, listing_confirm_keyboard())

    async def show_listings(bot: Bot, chat_id: int, state: FSMContext, user_id: int, can_manage: bool) -> None:
        await clear_flow_keep_screen(state)
        listings = database.list_listings(user_id)
        if listings:
            body = "Нажмите на объявление, чтобы посмотреть детали."
        else:
            body = "У вас пока нет объявлений. Создайте первое через кнопку выше."
        text = f"{project_heading(settings, 'Мои объявления')}\n\n{body}"
        await render_screen(
            bot,
            chat_id,
            state,
            settings,
            text,
            listings_keyboard(listings, can_manage),
        )

    @router.callback_query(F.data == "listing:start")
    async def start_listing(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
        await callback.answer()
        if callback.from_user is None or callback.message is None:
            return
        user = await navigation.ensure_approved(
            bot, callback.message.chat.id, state, callback.from_user.id
        )
        if user is None:
            return
        if not user.can_manage_content:
            await callback.answer("Ваша роль не позволяет создавать объявления", show_alert=True)
            return
        await choose_profile(bot, callback.message.chat.id, state, user.telegram_id)

    @router.callback_query(F.data.startswith("listing:profile:"))
    async def select_profile(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
        await callback.answer()
        if callback.from_user is None or callback.message is None or callback.data is None:
            return
        user = await navigation.ensure_approved(
            bot, callback.message.chat.id, state, callback.from_user.id
        )
        if user is None or not user.can_manage_content:
            return
        try:
            profile_id = int(callback.data.rsplit(":", maxsplit=1)[1])
        except ValueError:
            await callback.answer("Некорректный профиль", show_alert=True)
            return
        profile = database.get_profile_for_owner(profile_id, user.telegram_id)
        if profile is None or profile.status != "active":
            await callback.answer("Профиль не найден", show_alert=True)
            return
        await state.update_data(selected_profile_id=profile.id, profile_name=profile.display_name)
        await ask_title(bot, callback.message.chat.id, state, profile.display_name)

    @router.message(ListingCreation.waiting_for_title, F.text)
    async def receive_title(message: Message, state: FSMContext, bot: Bot) -> None:
        if message.from_user is None:
            return
        user = await navigation.ensure_approved(bot, message.chat.id, state, message.from_user.id)
        if user is None or not user.can_manage_content:
            return
        title = (message.text or "").strip()
        if not 2 <= len(title) <= 120:
            await message.answer("Название должно содержать от 2 до 120 символов. Попробуйте ещё раз.")
            return
        await state.update_data(listing_title=title)
        await try_delete_user_message(message)
        await ask_price(bot, message.chat.id, state)

    @router.message(ListingCreation.waiting_for_price, F.text)
    async def receive_price(message: Message, state: FSMContext, bot: Bot) -> None:
        price_cents = parse_price_to_cents(message.text or "")
        if price_cents is None:
            await message.answer("Введите цену числом, например <code>120</code> или <code>120.50</code>.", parse_mode="HTML")
            return
        await state.update_data(price_cents=price_cents)
        await try_delete_user_message(message)
        await ask_shipping(bot, message.chat.id, state, message.from_user.id)

    @router.message(ListingCreation.waiting_for_price)
    async def require_price(message: Message) -> None:
        await message.answer("Введите цену текстом, например <code>120</code>.", parse_mode="HTML")

    @router.message(ListingCreation.waiting_for_delivery_info, F.text)
    async def receive_delivery_info(message: Message, state: FSMContext, bot: Bot) -> None:
        delivery_info = (message.text or "").strip()
        if not 2 <= len(delivery_info) <= 500:
            await message.answer("Данные доставки должны содержать от 2 до 500 символов.")
            return
        await state.update_data(delivery_info=delivery_info)
        await try_delete_user_message(message)
        await ask_photo(bot, message.chat.id, state)

    @router.message(ListingCreation.waiting_for_delivery_info)
    async def require_delivery_info(message: Message) -> None:
        await message.answer("Введите условия доставки текстом.")

    @router.message(ListingCreation.waiting_for_photo, F.photo)
    async def receive_listing_photo(message: Message, state: FSMContext, bot: Bot) -> None:
        await state.update_data(listing_photo_file_id=message.photo[-1].file_id)
        await try_delete_user_message(message)
        await show_listing_preview(bot, message.chat.id, state)

    @router.message(ListingCreation.waiting_for_photo)
    async def require_listing_photo_or_action(message: Message) -> None:
        await message.answer("Отправьте фотографию товара или нажмите «Без фото».")

    @router.callback_query(F.data == "listing:photo:skip", ListingCreation.waiting_for_photo)
    async def skip_listing_photo(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
        await callback.answer()
        if callback.message is None:
            return
        await state.update_data(listing_photo_file_id=None)
        await show_listing_preview(bot, callback.message.chat.id, state)

    @router.callback_query(F.data.startswith("listing:save:"), ListingCreation.confirming)
    async def save_listing(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
        await callback.answer()
        if callback.from_user is None or callback.message is None or callback.data is None:
            return
        user = await navigation.ensure_approved(
            bot, callback.message.chat.id, state, callback.from_user.id
        )
        if user is None or not user.can_manage_content:
            return
        status = callback.data.rsplit(":", maxsplit=1)[1]
        if status not in {"draft", "ready"}:
            await callback.answer("Некорректный статус", show_alert=True)
            return
        data = await state.get_data()
        required = {"selected_profile_id", "listing_title", "price_cents", "delivery_info", "profile_name"}
        if not required.issubset(data):
            await callback.answer("Не хватает данных карточки", show_alert=True)
            await choose_profile(bot, callback.message.chat.id, state, user.telegram_id)
            return
        try:
            listing = database.create_listing(
                owner_id=user.telegram_id,
                profile_id=int(data["selected_profile_id"]),
                title=data["listing_title"],
                price_cents=int(data["price_cents"]),
                currency=settings.default_currency,
                delivery_info=data["delivery_info"],
                photo_file_id=data.get("listing_photo_file_id"),
                status=status,
                shipping_template_id=data.get("shipping_template_id"),
            )
        except PermissionError:
            await callback.answer("Профиль больше недоступен", show_alert=True)
            await choose_profile(bot, callback.message.chat.id, state, user.telegram_id)
            return

        screen_message_id = data.get("screen_message_id")
        saved_photo_file_id = listing.photo_file_id
        await state.clear()
        if screen_message_id:
            await state.update_data(
                screen_message_id=screen_message_id,
                requested_media_kind="listing" if saved_photo_file_id else "project",
                requested_media_file_id=saved_photo_file_id,
            )
        label = "Черновик сохранён" if listing.status == "draft" else "Карточка готова"
        link_text = (
            f"<b>🔗 Ссылка:</b> <code>{escape(public_url(listing) or 'появится после публикации')}</code>"
            if listing.public_slug
            else "<b>🔗 Ссылка:</b> <code>появится после нажатия «Готово»</code>"
        )
        text = (
            f"{project_heading(settings, label)}\n\n"
            f"<b>Название:</b> <code>{escape(listing.title)}</code>\n"
            f"<b>Цена:</b> <code>{escape(listing.formatted_price)}</code>\n"
            f"<b>Custom Service:</b> <code>{escape(listing.profile_name or '')}</code>\n\n"
            f"{link_text}"
        )
        await render_screen(
            bot,
            callback.message.chat.id,
            state,
            settings,
            text,
            listing_details_keyboard(listing, is_owner=True, public_url=public_url(listing)),
        )

    @router.callback_query(F.data == "listing:edit", ListingCreation.confirming)
    async def edit_listing(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
        await callback.answer()
        if callback.message is None:
            return
        data = await state.get_data()
        await ask_title(bot, callback.message.chat.id, state, data.get("profile_name", "—"))

    @router.callback_query(F.data == "listing:list")
    async def list_listings(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
        await callback.answer()
        if callback.from_user is None or callback.message is None:
            return
        user = await navigation.ensure_approved(
            bot, callback.message.chat.id, state, callback.from_user.id
        )
        if user is None:
            return
        await show_listings(
            bot, callback.message.chat.id, state, user.telegram_id, user.can_manage_content
        )

    @router.callback_query(F.data.startswith("listing:open:"))
    async def open_listing(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
        await callback.answer()
        if callback.from_user is None or callback.message is None or callback.data is None:
            return
        user = await navigation.ensure_approved(
            bot, callback.message.chat.id, state, callback.from_user.id
        )
        if user is None:
            return
        try:
            listing_id = int(callback.data.rsplit(":", maxsplit=1)[1])
        except ValueError:
            await callback.answer("Некорректное объявление", show_alert=True)
            return
        listing = database.get_listing_for_owner(listing_id, user.telegram_id)
        if listing is None:
            await callback.answer("Объявление не найдено", show_alert=True)
            return
        await render_listing_details(bot, callback.message.chat.id, state, listing, user.can_manage_content)

    async def render_listing_details(
        bot: Bot, chat_id: int, state: FSMContext, listing: Listing, is_owner: bool
    ) -> None:
        status = "Черновик" if listing.status == "draft" else "Готово к публикации"
        link = public_url(listing)
        link_text = escape(link) if link else "появится после нажатия «Готово»"
        text = (
            f"{project_heading(settings, 'Объявление')}\n\n"
            f"<b>Название:</b> <code>{escape(listing.title)}</code>\n"
            f"<b>Цена:</b> <code>{escape(listing.formatted_price)}</code>\n\n"
            f"<b>Custom Service:</b> <code>{escape(listing.profile_name or '—')}</code>\n\n"
            "📦 <b>Данные отправки:</b>\n"
            f"<b>Город:</b> <code>{escape(_delivery_field(listing.delivery_info, 'Город'))}</code>\n"
            f"<b>ZIP-код:</b> <code>{escape(_delivery_field(listing.delivery_info, 'ZIP-код'))}</code>\n"
            f"<b>Имя и фамилия:</b> <code>{escape(_delivery_field(listing.delivery_info, 'Имя и фамилия'))}</code>\n"
            f"<b>Улица:</b> <code>{escape(_delivery_field(listing.delivery_info, 'Улица'))}</code>\n\n"
            f"✅ <b>Статус:</b> <code>{status}</code>\n\n"
            f"🔗 <b>Ссылка:</b> <code>{link_text}</code>\n"
            f"<b>Фото:</b> <code>{'добавлено' if listing.photo_file_id else 'не добавлено'}</code>"
        )
        await state.update_data(
            requested_media_kind="listing" if listing.photo_file_id else "project",
            requested_media_file_id=listing.photo_file_id,
        )
        await render_screen(
            bot, chat_id, state, settings, text,
            listing_details_keyboard(listing, is_owner, link),
        )

    @router.callback_query(F.data.startswith("listing:copy:"))
    async def copy_listing_url(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
        await callback.answer()
        if callback.from_user is None or callback.message is None or callback.data is None:
            return
        user = await navigation.ensure_approved(
            bot, callback.message.chat.id, state, callback.from_user.id
        )
        if user is None:
            return
        listing_id = int(callback.data.rsplit(":", maxsplit=1)[1])
        listing = database.get_listing_for_owner(listing_id, user.telegram_id)
        link = public_url(listing) if listing else None
        if not link:
            await callback.answer("Ссылка появится после публикации", show_alert=True)
            return
        await callback.message.answer(
            f"🔗 <b>Ссылка карточки:</b>\n<code>{escape(link)}</code>",
            parse_mode="HTML",
            disable_web_page_preview=True,
        )

    @router.callback_query(F.data.startswith("listing:photo:replace:"))
    async def replace_listing_photo(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
        await callback.answer()
        if callback.from_user is None or callback.message is None or callback.data is None:
            return
        user = await navigation.ensure_approved(
            bot, callback.message.chat.id, state, callback.from_user.id
        )
        if user is None or not user.can_manage_content:
            return
        listing_id = int(callback.data.rsplit(":", maxsplit=1)[1])
        listing = database.get_listing_for_owner(listing_id, user.telegram_id)
        if listing is None:
            await callback.answer("Объявление не найдено", show_alert=True)
            return
        await state.set_state(ListingPhotoEdit.waiting_for_photo)
        await state.update_data(editing_listing_id=listing.id)
        await render_screen(
            bot,
            callback.message.chat.id,
            state,
            settings,
            f"{project_heading(settings, 'Замена фотографии')}\n\n"
            f"Отправьте новую фотографию для <code>{escape(listing.title)}</code>.",
            cancel_or_home(),
        )

    @router.message(ListingPhotoEdit.waiting_for_photo, F.photo)
    async def receive_replacement_photo(message: Message, state: FSMContext, bot: Bot) -> None:
        if message.from_user is None:
            return
        user = await navigation.ensure_approved(bot, message.chat.id, state, message.from_user.id)
        if user is None or not user.can_manage_content:
            return
        data = await state.get_data()
        listing_id = data.get("editing_listing_id")
        if not listing_id:
            await message.answer("Карточка для замены фото не найдена.")
            return
        listing = database.update_listing_photo(
            int(listing_id), user.telegram_id, message.photo[-1].file_id
        )
        await try_delete_user_message(message)
        await state.clear()
        if data.get("screen_message_id"):
            await state.update_data(
                screen_message_id=data["screen_message_id"],
                requested_media_kind="listing",
                requested_media_file_id=listing.photo_file_id if listing else None,
            )
        if listing is None:
            await message.answer("Карточка не найдена.")
            return
        await render_listing_details(bot, message.chat.id, state, listing, True)

    @router.callback_query(F.data.startswith("listing:photo:delete:"))
    async def delete_listing_photo(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
        await callback.answer()
        if callback.from_user is None or callback.message is None or callback.data is None:
            return
        user = await navigation.ensure_approved(
            bot, callback.message.chat.id, state, callback.from_user.id
        )
        if user is None or not user.can_manage_content:
            return
        listing_id = int(callback.data.rsplit(":", maxsplit=1)[1])
        listing = database.update_listing_photo(listing_id, user.telegram_id, None)
        if listing is None:
            await callback.answer("Объявление не найдено", show_alert=True)
            return
        await render_listing_details(bot, callback.message.chat.id, state, listing, True)

    @router.callback_query(F.data.startswith("listing:delete:ask:"))
    async def ask_delete_listing(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
        await callback.answer()
        if callback.from_user is None or callback.message is None or callback.data is None:
            return
        user = await navigation.ensure_approved(
            bot, callback.message.chat.id, state, callback.from_user.id
        )
        if user is None or not user.can_manage_content:
            return
        listing_id = int(callback.data.rsplit(":", maxsplit=1)[1])
        listing = database.get_listing_for_owner(listing_id, user.telegram_id)
        if listing is None:
            await callback.answer("Объявление не найдено", show_alert=True)
            return
        text = (
            f"{project_heading(settings, 'Удалить объявление?')}\n\n"
            f"<b>{escape(listing.title)}</b> будет удалено без возможности восстановления."
        )
        await render_screen(
            bot,
            callback.message.chat.id,
            state,
            settings,
            text,
            listing_delete_confirmation_keyboard(listing.id),
        )

    @router.callback_query(F.data.startswith("listing:delete:yes:"))
    async def delete_listing(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
        await callback.answer()
        if callback.from_user is None or callback.message is None or callback.data is None:
            return
        user = await navigation.ensure_approved(
            bot, callback.message.chat.id, state, callback.from_user.id
        )
        if user is None or not user.can_manage_content:
            return
        listing_id = int(callback.data.rsplit(":", maxsplit=1)[1])
        if not database.delete_listing(listing_id, user.telegram_id):
            await callback.answer("Объявление уже удалено", show_alert=True)
            return
        await callback.answer("Объявление удалено")
        await show_listings(
            bot, callback.message.chat.id, state, user.telegram_id, user.can_manage_content
        )

    @router.callback_query(F.data == "flow:back", ListingCreation.choosing_shipping)
    async def listing_back_from_shipping(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
        await callback.answer()
        if callback.message is not None:
            await ask_price(bot, callback.message.chat.id, state)

    @router.callback_query(F.data == "flow:back", ShippingTemplateCreation.waiting_for_label)
    async def shipping_back_from_label(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
        await callback.answer()
        if callback.from_user is not None and callback.message is not None:
            await ask_shipping(bot, callback.message.chat.id, state, callback.from_user.id)

    @router.callback_query(F.data == "flow:back", ShippingTemplateCreation.waiting_for_city)
    async def shipping_back_from_city(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
        await callback.answer()
        if callback.message is not None:
            await ask_shipping_label(bot, callback.message.chat.id, state)

    @router.callback_query(F.data == "flow:back", ShippingTemplateCreation.waiting_for_zip_code)
    async def shipping_back_from_zip(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
        await callback.answer()
        if callback.message is not None:
            await ask_shipping_field(
                bot, callback.message.chat.id, state,
                ShippingTemplateCreation.waiting_for_city, "2", "Введите город отправки. Например: Zürich",
            )

    @router.callback_query(F.data == "flow:back", ShippingTemplateCreation.waiting_for_contact_name)
    async def shipping_back_from_contact(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
        await callback.answer()
        if callback.message is not None:
            await ask_shipping_field(
                bot, callback.message.chat.id, state,
                ShippingTemplateCreation.waiting_for_zip_code, "3", "Введите ZIP-код.",
            )

    @router.callback_query(F.data == "flow:back", ShippingTemplateCreation.waiting_for_street)
    async def shipping_back_from_street(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
        await callback.answer()
        if callback.message is not None:
            await ask_shipping_field(
                bot, callback.message.chat.id, state,
                ShippingTemplateCreation.waiting_for_contact_name, "4",
                "Введите имя и фамилию отправителя или контактного лица.",
            )

    @router.callback_query(F.data == "flow:back", ListingCreation.choosing_profile)
    async def listing_back_from_profiles(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
        await callback.answer()
        if callback.from_user is None or callback.message is None:
            return
        user = await navigation.ensure_approved(
            bot, callback.message.chat.id, state, callback.from_user.id
        )
        if user:
            await navigation.show_home(bot, callback.message.chat.id, state, user)

    @router.callback_query(F.data == "flow:back", ListingCreation.waiting_for_title)
    async def listing_back_to_profiles(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
        await callback.answer()
        if callback.from_user is None or callback.message is None:
            return
        await choose_profile(bot, callback.message.chat.id, state, callback.from_user.id)

    @router.callback_query(F.data == "flow:back", ListingCreation.waiting_for_price)
    async def listing_back_to_title(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
        await callback.answer()
        if callback.message is None:
            return
        data = await state.get_data()
        await ask_title(bot, callback.message.chat.id, state, data.get("profile_name", "—"))

    @router.callback_query(F.data == "flow:back", ListingCreation.waiting_for_delivery_info)
    async def listing_back_to_price(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
        await callback.answer()
        if callback.message is not None:
            await ask_price(bot, callback.message.chat.id, state)

    @router.callback_query(F.data == "flow:back", ListingCreation.waiting_for_photo)
    async def listing_back_to_delivery(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
        await callback.answer()
        if callback.message is not None:
            await ask_delivery_info(bot, callback.message.chat.id, state)

    @router.callback_query(F.data == "flow:back", ListingCreation.confirming)
    async def listing_back_to_photo(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
        await callback.answer()
        if callback.message is not None:
            await ask_photo(bot, callback.message.chat.id, state)

    return router
