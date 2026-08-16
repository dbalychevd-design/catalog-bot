"""Точка запуска Catalog Studio Telegram Bot."""

from __future__ import annotations

import asyncio
import logging
import threading

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from api import create_app
from config import load_settings
from database import Database
from handlers import admin, common, listings, profiles, static_pages
from services.navigation import Navigation


def start_health_server(database: Database, settings) -> None:
    """Запускает Flask API и health-проверки в фоне рядом с polling."""
    flask_app = create_app(database, settings)

    thread = threading.Thread(
        target=lambda: flask_app.run(host="0.0.0.0", port=settings.port, use_reloader=False),
        name="health-server",
        daemon=True,
    )
    thread.start()


async def main() -> None:
    settings = load_settings()
    database = Database(settings.database_path)
    database.initialize(settings.admin_id)
    navigation = Navigation(database=database, settings=settings)

    start_health_server(database, settings)

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher(storage=MemoryStorage())

    # `/start` подключается первым, поэтому он сбрасывает любой незавершённый сценарий.
    # Обычный текст без активного состояния обработается только последним fallback-обработчиком.
    dispatcher.include_router(common.build_router(database, settings, navigation))
    dispatcher.include_router(admin.build_router(database, settings, navigation))
    dispatcher.include_router(profiles.build_router(database, settings, navigation))
    dispatcher.include_router(listings.build_router(database, settings, navigation))
    dispatcher.include_router(static_pages.build_router(database, settings, navigation))

    logging.info("Bot started. SQLite database: %s", settings.database_path)
    try:
        await dispatcher.start_polling(bot, allowed_updates=dispatcher.resolve_used_update_types())
    finally:
        await bot.session.close()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Bot stopped by user")
