"""Отрисовка единого интерфейсного сообщения бота."""

from __future__ import annotations

from html import escape

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InputMediaPhoto, Message

from config import Settings

SCREEN_MESSAGE_ID = "screen_message_id"


async def clear_flow_keep_screen(state: FSMContext) -> None:
    """Очищает временные данные анкеты, сохраняя ссылку на интерфейсное сообщение."""
    screen_message_id = (await state.get_data()).get(SCREEN_MESSAGE_ID)
    await state.clear()
    if screen_message_id:
        await state.update_data(**{SCREEN_MESSAGE_ID: screen_message_id})


async def try_delete_user_message(message: Message) -> None:
    """Удаляет обработанный ввод, не ломая сценарий при отказе Telegram."""
    try:
        await message.delete()
    except (TelegramBadRequest, TelegramForbiddenError):
        # В некоторых чатах Telegram может запретить удаление входящего сообщения.
        pass


async def render_screen(
    bot: Bot,
    chat_id: int,
    state: FSMContext,
    settings: Settings,
    text: str,
    keyboard: InlineKeyboardMarkup,
) -> Message | None:
    """Редактирует одну «панель управления» или создаёт её при первом открытии.

    Если в PROJECT_IMAGE_FILE_ID задан баннер, он остаётся прикреплённым на каждом
    экране, меняется только подпись и inline-кнопки.
    """
    data = await state.get_data()
    screen_message_id = data.get(SCREEN_MESSAGE_ID)
    screen_media_kind = data.get("screen_media_kind", "text")
    requested_media_kind = data.get("requested_media_kind", "project")
    requested_media_file_id = data.get("requested_media_file_id")

    if screen_message_id and requested_media_kind == "listing" and requested_media_file_id:
        try:
            await bot.edit_message_media(
                chat_id=chat_id,
                message_id=screen_message_id,
                media=InputMediaPhoto(
                    media=requested_media_file_id,
                    caption=text,
                    parse_mode="HTML",
                ),
                reply_markup=keyboard,
            )
            await state.update_data(
                screen_media_kind="listing",
                requested_media_kind=None,
                requested_media_file_id=None,
            )
            return None
        except TelegramBadRequest as exc:
            if "message is not modified" in str(exc).lower():
                return None
            try:
                await bot.delete_message(chat_id=chat_id, message_id=screen_message_id)
            except (TelegramBadRequest, TelegramForbiddenError):
                pass
            await state.update_data(screen_message_id=None, screen_media_kind="text")
            screen_message_id = None

    if screen_message_id and (requested_media_kind != "listing" or not requested_media_file_id) and screen_media_kind == "listing":
        if settings.project_image_file_id:
            try:
                await bot.edit_message_media(
                    chat_id=chat_id,
                    message_id=screen_message_id,
                    media=InputMediaPhoto(
                        media=settings.project_image_file_id,
                        caption=text,
                        parse_mode="HTML",
                    ),
                    reply_markup=keyboard,
                )
                await state.update_data(screen_media_kind="project")
                return None
            except TelegramBadRequest:
                pass
        else:
            try:
                await bot.delete_message(chat_id=chat_id, message_id=screen_message_id)
            except (TelegramBadRequest, TelegramForbiddenError):
                pass
            await state.update_data(screen_message_id=None, screen_media_kind="text")
            screen_message_id = None

    if screen_message_id:
        try:
            if settings.project_image_file_id and screen_media_kind == "project":
                await bot.edit_message_caption(
                    chat_id=chat_id,
                    message_id=screen_message_id,
                    caption=text,
                    reply_markup=keyboard,
                    parse_mode="HTML",
                )
            elif screen_media_kind == "text":
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=screen_message_id,
                    text=text,
                    reply_markup=keyboard,
                    parse_mode="HTML",
                    disable_web_page_preview=True,
                )
            return None
        except TelegramBadRequest as exc:
            # "message is not modified" — нормальный результат повторного нажатия.
            if "message is not modified" in str(exc).lower():
                return None
        except TelegramForbiddenError:
            return None

    if requested_media_kind == "listing" and requested_media_file_id:
        sent = await bot.send_photo(
            chat_id=chat_id,
            photo=requested_media_file_id,
            caption=text,
            reply_markup=keyboard,
            parse_mode="HTML",
        )
        await state.update_data(
            **{SCREEN_MESSAGE_ID: sent.message_id, "screen_media_kind": "listing"}
        )
        return sent

    if settings.project_image_file_id:
        sent = await bot.send_photo(
            chat_id=chat_id,
            photo=settings.project_image_file_id,
            caption=text,
            reply_markup=keyboard,
            parse_mode="HTML",
        )
    else:
        sent = await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=keyboard,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    await state.update_data(
        **{SCREEN_MESSAGE_ID: sent.message_id, "screen_media_kind": "project" if settings.project_image_file_id else "text"}
    )
    return sent


def project_heading(settings: Settings, subtitle: str | None = None) -> str:
    """Строит единый HTML-заголовок для экранов интерфейса."""
    heading = f"<b>🔴 {escape(settings.project_title)}</b>"
    if subtitle:
        heading += f"\n<blockquote>{escape(subtitle)}</blockquote>"
    return heading


def user_label(username: str | None, full_name: str, telegram_id: int) -> str:
    handle = f"@{username}" if username else "без username"
    return f"{escape(full_name)}\n{escape(handle)} · <code>{telegram_id}</code>"
