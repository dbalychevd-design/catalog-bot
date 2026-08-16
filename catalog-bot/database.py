"""SQLite-хранилище для Catalog Studio.

База создаётся автоматически при первом запуске. Все методы открывают короткое
соединение с SQLite, поэтому данные не зависят от памяти процесса бота.
"""

from __future__ import annotations

import secrets
import sqlite3
import string
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

UserRole = Literal["owner", "creator", "viewer"]
AccessStatus = Literal["pending", "approved", "declined"]
ProfileStatus = Literal["active", "archived"]
ListingStatus = Literal["draft", "ready"]


@dataclass(slots=True, frozen=True)
class User:
    telegram_id: int
    username: str | None
    full_name: str
    role: UserRole
    access_status: AccessStatus
    requested_at: str
    approved_at: str | None

    @property
    def can_manage_content(self) -> bool:
        return self.access_status == "approved" and self.role in {"owner", "creator"}

    @property
    def is_admin(self) -> bool:
        return self.access_status == "approved" and self.role == "owner"


@dataclass(slots=True, frozen=True)
class BrandProfile:
    id: int
    owner_id: int
    display_name: str
    logo_file_id: str | None
    theme_mode: str
    primary_color: str | None
    favicon_file_id: str | None
    status: ProfileStatus
    is_default: bool
    created_at: str
    owner_name: str | None = None


@dataclass(slots=True, frozen=True)
class ShippingTemplate:
    id: int
    owner_id: int
    label: str
    city: str
    zip_code: str
    contact_name: str
    street: str
    is_default: bool
    created_at: str

    def formatted(self) -> str:
        return (
            f"Город: {self.city}\n"
            f"ZIP-код: {self.zip_code}\n"
            f"Имя и фамилия: {self.contact_name}\n"
            f"Улица: {self.street}"
        )


@dataclass(slots=True, frozen=True)
class Listing:
    id: int
    owner_id: int
    profile_id: int
    title: str
    price_cents: int
    currency: str
    delivery_info: str
    photo_file_id: str | None
    status: ListingStatus
    created_at: str
    updated_at: str
    profile_name: str | None = None
    owner_name: str | None = None
    shipping_template_id: int | None = None
    public_slug: str | None = None

    @property
    def formatted_price(self) -> str:
        whole, fraction = divmod(self.price_cents, 100)
        return f"{whole:,}.{fraction:02d}".replace(",", " ") + f" {self.currency}"


@dataclass(slots=True, frozen=True)
class ProjectStats:
    approved_users: int
    pending_users: int
    profile_count: int
    listing_count: int


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class Database:
    """Небольшой слой работы с SQLite без SQL внутри обработчиков Telegram."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    def _connect(self) -> sqlite3.Connection:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def initialize(self, admin_id: int) -> None:
        """Создаёт таблицы и гарантирует, что первый администратор существует."""
        now = utc_now()
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS project_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS users (
                    telegram_id INTEGER PRIMARY KEY,
                    username TEXT,
                    full_name TEXT NOT NULL,
                    role TEXT NOT NULL CHECK (role IN ('owner', 'creator', 'viewer')),
                    access_status TEXT NOT NULL CHECK (access_status IN ('pending', 'approved', 'declined')),
                    requested_at TEXT NOT NULL,
                    approved_at TEXT
                );

                CREATE TABLE IF NOT EXISTS brand_profiles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    owner_id INTEGER NOT NULL,
                    display_name TEXT NOT NULL COLLATE NOCASE,
                    logo_file_id TEXT,
                    theme_mode TEXT NOT NULL DEFAULT 'red' CHECK (theme_mode IN ('red', 'custom', 'later')),
                    primary_color TEXT,
                    favicon_file_id TEXT,
                    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived')),
                    is_default INTEGER NOT NULL DEFAULT 0 CHECK (is_default IN (0, 1)),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(owner_id, display_name),
                    FOREIGN KEY(owner_id) REFERENCES users(telegram_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS shipping_templates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    owner_id INTEGER NOT NULL,
                    label TEXT NOT NULL,
                    city TEXT NOT NULL,
                    zip_code TEXT NOT NULL,
                    contact_name TEXT NOT NULL,
                    street TEXT NOT NULL,
                    is_default INTEGER NOT NULL DEFAULT 0 CHECK (is_default IN (0, 1)),
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(owner_id) REFERENCES users(telegram_id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS listings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    owner_id INTEGER NOT NULL,
                    profile_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    price_cents INTEGER NOT NULL CHECK (price_cents >= 0),
                    currency TEXT NOT NULL,
                    delivery_info TEXT NOT NULL,
                    shipping_template_id INTEGER,
                    public_slug TEXT UNIQUE,
                    photo_file_id TEXT,
                    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'ready')),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(owner_id) REFERENCES users(telegram_id) ON DELETE CASCADE,
                    FOREIGN KEY(profile_id) REFERENCES brand_profiles(id) ON DELETE RESTRICT
                );

                CREATE INDEX IF NOT EXISTS idx_profiles_owner ON brand_profiles(owner_id, status);
                CREATE INDEX IF NOT EXISTS idx_shipping_owner ON shipping_templates(owner_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_listings_owner ON listings(owner_id, status);
                CREATE INDEX IF NOT EXISTS idx_users_access ON users(access_status, role);
                """
            )
            columns = {row[1] for row in connection.execute("PRAGMA table_info(listings)").fetchall()}
            if "shipping_template_id" not in columns:
                connection.execute("ALTER TABLE listings ADD COLUMN shipping_template_id INTEGER")
            if "public_slug" not in columns:
                connection.execute("ALTER TABLE listings ADD COLUMN public_slug TEXT")

            connection.execute(
                "INSERT OR IGNORE INTO project_meta (key, value) VALUES ('started_at', ?)",
                (now,),
            )
            connection.execute(
                """
                INSERT INTO users (
                    telegram_id, username, full_name, role, access_status, requested_at, approved_at
                ) VALUES (?, NULL, 'Владелец проекта', 'owner', 'approved', ?, ?)
                ON CONFLICT(telegram_id) DO UPDATE SET
                    role = 'owner',
                    access_status = 'approved',
                    approved_at = COALESCE(users.approved_at, excluded.approved_at)
                """,
                (admin_id, now, now),
            )

    @staticmethod
    def _to_user(row: sqlite3.Row | None) -> User | None:
        if row is None:
            return None
        return User(
            telegram_id=row["telegram_id"],
            username=row["username"],
            full_name=row["full_name"],
            role=row["role"],
            access_status=row["access_status"],
            requested_at=row["requested_at"],
            approved_at=row["approved_at"],
        )

    @staticmethod
    def _to_profile(row: sqlite3.Row | None) -> BrandProfile | None:
        if row is None:
            return None
        return BrandProfile(
            id=row["id"],
            owner_id=row["owner_id"],
            display_name=row["display_name"],
            logo_file_id=row["logo_file_id"],
            theme_mode=row["theme_mode"],
            primary_color=row["primary_color"],
            favicon_file_id=row["favicon_file_id"],
            status=row["status"],
            is_default=bool(row["is_default"]),
            created_at=row["created_at"],
            owner_name=row["owner_name"] if "owner_name" in row.keys() else None,
        )

    @staticmethod
    def _to_listing(row: sqlite3.Row | None) -> Listing | None:
        if row is None:
            return None
        return Listing(
            id=row["id"],
            owner_id=row["owner_id"],
            profile_id=row["profile_id"],
            title=row["title"],
            price_cents=row["price_cents"],
            currency=row["currency"],
            delivery_info=row["delivery_info"],
            photo_file_id=row["photo_file_id"],
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            profile_name=row["profile_name"] if "profile_name" in row.keys() else None,
            owner_name=row["owner_name"] if "owner_name" in row.keys() else None,
            shipping_template_id=(
                row["shipping_template_id"] if "shipping_template_id" in row.keys() else None
            ),
            public_slug=row["public_slug"] if "public_slug" in row.keys() else None,
        )

    @staticmethod
    def _to_shipping_template(row: sqlite3.Row | None) -> ShippingTemplate | None:
        if row is None:
            return None
        return ShippingTemplate(
            id=row["id"],
            owner_id=row["owner_id"],
            label=row["label"],
            city=row["city"],
            zip_code=row["zip_code"],
            contact_name=row["contact_name"],
            street=row["street"],
            is_default=bool(row["is_default"]),
            created_at=row["created_at"],
        )

    def list_shipping_templates(self, owner_id: int) -> list[ShippingTemplate]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM shipping_templates
                WHERE owner_id = ?
                ORDER BY is_default DESC, created_at DESC
                """,
                (owner_id,),
            ).fetchall()
        return [self._to_shipping_template(row) for row in rows if self._to_shipping_template(row)]

    def get_shipping_template_for_owner(
        self, template_id: int, owner_id: int
    ) -> ShippingTemplate | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM shipping_templates
                WHERE id = ? AND owner_id = ?
                """,
                (template_id, owner_id),
            ).fetchone()
        return self._to_shipping_template(row)

    def create_shipping_template(
        self,
        owner_id: int,
        label: str,
        city: str,
        zip_code: str,
        contact_name: str,
        street: str,
    ) -> ShippingTemplate:
        now = utc_now()
        with self._connect() as connection:
            has_templates = connection.execute(
                "SELECT 1 FROM shipping_templates WHERE owner_id = ? LIMIT 1",
                (owner_id,),
            ).fetchone()
            cursor = connection.execute(
                """
                INSERT INTO shipping_templates
                    (owner_id, label, city, zip_code, contact_name, street, is_default, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    owner_id,
                    label.strip(),
                    city.strip(),
                    zip_code.strip(),
                    contact_name.strip(),
                    street.strip(),
                    0 if has_templates else 1,
                    now,
                ),
            )
            row = connection.execute(
                "SELECT * FROM shipping_templates WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
        template = self._to_shipping_template(row)
        assert template is not None
        return template

    def get_default_shipping_template(self, owner_id: int) -> ShippingTemplate | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM shipping_templates
                WHERE owner_id = ?
                ORDER BY is_default DESC, created_at DESC
                LIMIT 1
                """,
                (owner_id,),
            ).fetchone()
        return self._to_shipping_template(row)

    def set_default_shipping_template(self, template_id: int, owner_id: int) -> bool:
        with self._connect() as connection:
            exists = connection.execute(
                "SELECT id FROM shipping_templates WHERE id = ? AND owner_id = ?",
                (template_id, owner_id),
            ).fetchone()
            if exists is None:
                return False
            connection.execute(
                "UPDATE shipping_templates SET is_default = 0 WHERE owner_id = ?",
                (owner_id,),
            )
            connection.execute(
                "UPDATE shipping_templates SET is_default = 1 WHERE id = ?",
                (template_id,),
            )
        return True

    def get_user(self, telegram_id: int) -> User | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
            ).fetchone()
        return self._to_user(row)

    def request_access(self, telegram_id: int, username: str | None, full_name: str) -> tuple[User, bool]:
        """Создаёт заявку один раз; возвращает пользователя и признак новой заявки."""
        now = utc_now()
        with self._connect() as connection:
            current = connection.execute(
                "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
            ).fetchone()
            if current is not None:
                connection.execute(
                    "UPDATE users SET username = ?, full_name = ? WHERE telegram_id = ?",
                    (username, full_name, telegram_id),
                )
                updated = connection.execute(
                    "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
                ).fetchone()
                user = self._to_user(updated)
                assert user is not None
                return user, False

            connection.execute(
                """
                INSERT INTO users (
                    telegram_id, username, full_name, role, access_status, requested_at, approved_at
                ) VALUES (?, ?, ?, 'creator', 'pending', ?, NULL)
                """,
                (telegram_id, username, full_name, now),
            )
            row = connection.execute(
                "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
            ).fetchone()
        user = self._to_user(row)
        assert user is not None
        return user, True

    def approve_user(self, telegram_id: int) -> User | None:
        now = utc_now()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE users
                SET access_status = 'approved',
                    role = CASE WHEN role = 'owner' THEN 'owner' ELSE 'creator' END,
                    approved_at = ?
                WHERE telegram_id = ?
                """,
                (now, telegram_id),
            )
            if cursor.rowcount == 0:
                return None
            row = connection.execute(
                "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
            ).fetchone()
        return self._to_user(row)

    def decline_user(self, telegram_id: int) -> User | None:
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE users SET access_status = 'declined' WHERE telegram_id = ?",
                (telegram_id,),
            )
            if cursor.rowcount == 0:
                return None
            row = connection.execute(
                "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
            ).fetchone()
        return self._to_user(row)

    def set_user_role(self, telegram_id: int, role: UserRole) -> User | None:
        if role not in {"owner", "creator", "viewer"}:
            raise ValueError("Неизвестная роль.")
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE users SET role = ? WHERE telegram_id = ? AND access_status = 'approved'",
                (role, telegram_id),
            )
            if cursor.rowcount == 0:
                return None
            row = connection.execute(
                "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
            ).fetchone()
        return self._to_user(row)

    def list_pending_users(self) -> list[User]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM users WHERE access_status = 'pending' ORDER BY requested_at ASC"
            ).fetchall()
        return [self._to_user(row) for row in rows if self._to_user(row) is not None]

    def list_approved_users(self) -> list[User]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM users
                WHERE access_status = 'approved'
                ORDER BY CASE role WHEN 'owner' THEN 0 WHEN 'creator' THEN 1 ELSE 2 END, full_name COLLATE NOCASE
                """
            ).fetchall()
        return [self._to_user(row) for row in rows if self._to_user(row) is not None]

    def create_profile(
        self,
        owner_id: int,
        display_name: str,
        logo_file_id: str | None,
        theme_mode: str,
        primary_color: str | None,
        favicon_file_id: str | None,
    ) -> BrandProfile:
        if theme_mode not in {"red", "custom", "later"}:
            raise ValueError("Неизвестный стиль профиля.")
        now = utc_now()
        with self._connect() as connection:
            has_profiles = connection.execute(
                "SELECT 1 FROM brand_profiles WHERE owner_id = ? AND status = 'active' LIMIT 1",
                (owner_id,),
            ).fetchone()
            cursor = connection.execute(
                """
                INSERT INTO brand_profiles (
                    owner_id, display_name, logo_file_id, theme_mode, primary_color,
                    favicon_file_id, status, is_default, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)
                """,
                (
                    owner_id,
                    display_name.strip(),
                    logo_file_id,
                    theme_mode,
                    primary_color,
                    favicon_file_id,
                    0 if has_profiles else 1,
                    now,
                    now,
                ),
            )
            row = connection.execute(
                "SELECT * FROM brand_profiles WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
        profile = self._to_profile(row)
        assert profile is not None
        return profile

    def list_profiles(self, owner_id: int, include_archived: bool = False) -> list[BrandProfile]:
        query = "SELECT * FROM brand_profiles WHERE owner_id = ?"
        if not include_archived:
            query += " AND status = 'active'"
        query += " ORDER BY is_default DESC, created_at DESC"
        with self._connect() as connection:
            rows = connection.execute(query, (owner_id,)).fetchall()
        return [self._to_profile(row) for row in rows if self._to_profile(row) is not None]

    def get_profile_for_owner(self, profile_id: int, owner_id: int) -> BrandProfile | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM brand_profiles WHERE id = ? AND owner_id = ?",
                (profile_id, owner_id),
            ).fetchone()
        return self._to_profile(row)

    def list_all_profiles(self) -> list[BrandProfile]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT brand_profiles.*, users.full_name AS owner_name
                FROM brand_profiles
                JOIN users ON users.telegram_id = brand_profiles.owner_id
                WHERE brand_profiles.status = 'active'
                ORDER BY brand_profiles.created_at DESC
                """
            ).fetchall()
        return [self._to_profile(row) for row in rows if self._to_profile(row) is not None]

    def get_profile_any(self, profile_id: int) -> BrandProfile | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT brand_profiles.*, users.full_name AS owner_name
                FROM brand_profiles
                JOIN users ON users.telegram_id = brand_profiles.owner_id
                WHERE brand_profiles.id = ?
                """,
                (profile_id,),
            ).fetchone()
        return self._to_profile(row)

    def set_default_profile(self, profile_id: int, owner_id: int) -> bool:
        with self._connect() as connection:
            profile = connection.execute(
                """
                SELECT id FROM brand_profiles
                WHERE id = ? AND owner_id = ? AND status = 'active'
                """,
                (profile_id, owner_id),
            ).fetchone()
            if profile is None:
                return False
            connection.execute("UPDATE brand_profiles SET is_default = 0 WHERE owner_id = ?", (owner_id,))
            connection.execute(
                "UPDATE brand_profiles SET is_default = 1, updated_at = ? WHERE id = ?",
                (utc_now(), profile_id),
            )
        return True

    def archive_profile(self, profile_id: int, owner_id: int) -> bool:
        """Архивирует только профиль владельца; карточки остаются в истории."""
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE brand_profiles
                SET status = 'archived', is_default = 0, updated_at = ?
                WHERE id = ? AND owner_id = ? AND status = 'active'
                """,
                (utc_now(), profile_id, owner_id),
            )
            return cursor.rowcount > 0

    def archive_profile_as_admin(self, profile_id: int) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE brand_profiles
                SET status = 'archived', is_default = 0, updated_at = ?
                WHERE id = ? AND status = 'active'
                """,
                (utc_now(), profile_id),
            )
            return cursor.rowcount > 0

    def create_listing(
        self,
        owner_id: int,
        profile_id: int,
        title: str,
        price_cents: int,
        currency: str,
        delivery_info: str,
        photo_file_id: str | None,
        status: ListingStatus = "ready",
        shipping_template_id: int | None = None,
    ) -> Listing:
        if status not in {"draft", "ready"}:
            raise ValueError("Неизвестный статус объявления.")
        if self.get_profile_for_owner(profile_id, owner_id) is None:
            raise PermissionError("Нельзя создать объявление в чужом или удалённом профиле.")
        if shipping_template_id is not None and self.get_shipping_template_for_owner(
            shipping_template_id, owner_id
        ) is None:
            raise PermissionError("Нельзя использовать чужой шаблон данных отправки.")
        now = utc_now()
        alphabet = string.ascii_letters + string.digits
        with self._connect() as connection:
            public_slug = None
            if status == "ready":
                for _ in range(20):
                    candidate = "".join(secrets.choice(alphabet) for _ in range(8))
                    if connection.execute(
                        "SELECT 1 FROM listings WHERE public_slug = ?", (candidate,)
                    ).fetchone() is None:
                        public_slug = candidate
                        break
                if public_slug is None:
                    raise RuntimeError("Не удалось создать уникальную ссылку карточки.")

            cursor = connection.execute(
                """
                INSERT INTO listings (
                    owner_id, profile_id, title, price_cents, currency, delivery_info,
                    shipping_template_id, public_slug, photo_file_id, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    owner_id,
                    profile_id,
                    title.strip(),
                    price_cents,
                    currency.strip().upper(),
                    delivery_info.strip(),
                    shipping_template_id,
                    public_slug,
                    photo_file_id,
                    status,
                    now,
                    now,
                ),
            )
            row = connection.execute(
                """
                SELECT listings.*, brand_profiles.display_name AS profile_name
                FROM listings JOIN brand_profiles ON brand_profiles.id = listings.profile_id
                WHERE listings.id = ?
                """,
                (cursor.lastrowid,),
            ).fetchone()
        listing = self._to_listing(row)
        assert listing is not None
        return listing

    def list_listings(self, owner_id: int) -> list[Listing]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT listings.*, brand_profiles.display_name AS profile_name
                FROM listings
                JOIN brand_profiles ON brand_profiles.id = listings.profile_id
                WHERE listings.owner_id = ?
                ORDER BY listings.created_at DESC
                """,
                (owner_id,),
            ).fetchall()
        return [self._to_listing(row) for row in rows if self._to_listing(row) is not None]

    def list_all_listings(self) -> list[Listing]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT listings.*, brand_profiles.display_name AS profile_name,
                       users.full_name AS owner_name
                FROM listings
                JOIN brand_profiles ON brand_profiles.id = listings.profile_id
                JOIN users ON users.telegram_id = listings.owner_id
                ORDER BY listings.created_at DESC
                """
            ).fetchall()
        return [self._to_listing(row) for row in rows if self._to_listing(row) is not None]

    def get_listing_for_owner(self, listing_id: int, owner_id: int) -> Listing | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT listings.*, brand_profiles.display_name AS profile_name
                FROM listings
                JOIN brand_profiles ON brand_profiles.id = listings.profile_id
                WHERE listings.id = ? AND listings.owner_id = ?
                """,
                (listing_id, owner_id),
            ).fetchone()
        return self._to_listing(row)

    def update_listing_photo(
        self, listing_id: int, owner_id: int, photo_file_id: str | None
    ) -> Listing | None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE listings
                SET photo_file_id = ?, updated_at = ?
                WHERE id = ? AND owner_id = ?
                """,
                (photo_file_id, utc_now(), listing_id, owner_id),
            )
            row = connection.execute(
                """
                SELECT listings.*, brand_profiles.display_name AS profile_name
                FROM listings JOIN brand_profiles ON brand_profiles.id = listings.profile_id
                WHERE listings.id = ? AND listings.owner_id = ?
                """,
                (listing_id, owner_id),
            ).fetchone()
        return self._to_listing(row)

    def get_listing_by_slug(self, public_slug: str) -> Listing | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT listings.*, brand_profiles.display_name AS profile_name
                FROM listings
                JOIN brand_profiles ON brand_profiles.id = listings.profile_id
                WHERE listings.public_slug = ?
                """,
                (public_slug.strip(),),
            ).fetchone()
        return self._to_listing(row)

    def get_listing_any(self, listing_id: int) -> Listing | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT listings.*, brand_profiles.display_name AS profile_name,
                       users.full_name AS owner_name
                FROM listings
                JOIN brand_profiles ON brand_profiles.id = listings.profile_id
                JOIN users ON users.telegram_id = listings.owner_id
                WHERE listings.id = ?
                """,
                (listing_id,),
            ).fetchone()
        return self._to_listing(row)

    def delete_listing(self, listing_id: int, owner_id: int) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM listings WHERE id = ? AND owner_id = ?", (listing_id, owner_id)
            )
            return cursor.rowcount > 0

    def delete_listing_as_admin(self, listing_id: int) -> bool:
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM listings WHERE id = ?", (listing_id,))
            return cursor.rowcount > 0

    def get_project_started_at(self) -> str:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT value FROM project_meta WHERE key = 'started_at'"
            ).fetchone()
        return row["value"] if row else utc_now()

    def get_stats(self) -> ProjectStats:
        with self._connect() as connection:
            approved_users = connection.execute(
                "SELECT COUNT(*) FROM users WHERE access_status = 'approved'"
            ).fetchone()[0]
            pending_users = connection.execute(
                "SELECT COUNT(*) FROM users WHERE access_status = 'pending'"
            ).fetchone()[0]
            profile_count = connection.execute(
                "SELECT COUNT(*) FROM brand_profiles WHERE status = 'active'"
            ).fetchone()[0]
            listing_count = connection.execute("SELECT COUNT(*) FROM listings").fetchone()[0]
        return ProjectStats(
            approved_users=approved_users,
            pending_users=pending_users,
            profile_count=profile_count,
            listing_count=listing_count,
        )
