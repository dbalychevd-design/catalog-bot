"""Проверка, что все обработчики и клавиатуры собираются без ошибки импорта."""

from __future__ import annotations

import tempfile
from pathlib import Path

from config import Settings
from database import Database
from handlers import admin, common, listings, profiles, static_pages
from handlers.listings import parse_price_to_cents
from services.navigation import Navigation


def main() -> None:
    with tempfile.TemporaryDirectory() as temporary_directory:
        settings = Settings(
            bot_token="123456:TEST_TOKEN_FOR_IMPORT_CHECK_ONLY",
            admin_id=100,
            database_path=Path(temporary_directory) / "catalog.db",
            project_title="Catalog Studio",
            project_description="Test",
            support_username=None,
            community_url=None,
            project_image_file_id=None,
            default_currency="CHF",
            public_base_url="https://example.com",
            port=10000,
        )
        database = Database(settings.database_path)
        database.initialize(settings.admin_id)
        navigation = Navigation(database=database, settings=settings)
        routers = [
            admin.build_router(database, settings, navigation),
            profiles.build_router(database, settings, navigation),
            listings.build_router(database, settings, navigation),
            static_pages.build_router(database, settings, navigation),
            common.build_router(database, settings, navigation),
        ]
        assert len(routers) == 5
        assert all(router.name for router in routers)
        assert parse_price_to_cents("120") == 12000
        assert parse_price_to_cents("120,50") == 12050
        assert parse_price_to_cents("not a price") is None

    print("Application structure passed")


if __name__ == "__main__":
    main()
