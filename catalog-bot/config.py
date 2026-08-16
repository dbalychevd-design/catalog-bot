"""Безопасная конфигурация приложения.

Настройки берутся из переменных окружения или локального файла .env.
Файл .env не добавляется в GitHub.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_DIR = Path(__file__).resolve().parent
load_dotenv(PROJECT_DIR / ".env")


@dataclass(frozen=True, slots=True)
class Settings:
    """Проверенные настройки приложения."""

    bot_token: str
    admin_id: int
    database_path: Path
    project_title: str
    project_description: str
    support_username: str | None
    community_url: str | None
    project_image_file_id: str | None
    default_currency: str
    public_base_url: str
    port: int


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(
            f"Не задана обязательная переменная окружения {name}. "
            "Скопируйте .env.example в .env и заполните значение."
        )
    return value


def load_settings() -> Settings:
    """Загружает и валидирует переменные окружения."""

    raw_database_path = os.getenv("DATABASE_PATH", "data/catalog.db").strip()
    database_path = Path(raw_database_path)
    if not database_path.is_absolute():
        database_path = PROJECT_DIR / database_path

    try:
        admin_id = int(_required("ADMIN_ID"))
    except ValueError as exc:
        raise RuntimeError("ADMIN_ID должен состоять только из цифр.") from exc

    return Settings(
        bot_token=_required("BOT_TOKEN"),
        admin_id=admin_id,
        database_path=database_path,
        project_title=os.getenv("PROJECT_TITLE", "Catalog Studio").strip() or "Catalog Studio",
        project_description=(
            os.getenv(
                "PROJECT_DESCRIPTION",
                "Приватная панель создания товарных объявлений.",
            ).strip()
            or "Приватная панель создания товарных объявлений."
        ),
        support_username=os.getenv("SUPPORT_USERNAME", "").strip() or None,
        community_url=os.getenv("COMMUNITY_URL", "").strip() or None,
        project_image_file_id=os.getenv("PROJECT_IMAGE_FILE_ID", "").strip() or None,
        default_currency=os.getenv("DEFAULT_CURRENCY", "CHF").strip().upper() or "CHF",
        public_base_url=(
            os.getenv("PUBLIC_BASE_URL", "https://example.com").strip().rstrip("/")
            or "https://example.com"
        ),
        port=int(os.getenv("PORT", "10000")),
    )
