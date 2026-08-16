"""Публичный Flask API для динамических карточек лендинга.

API отдаёт только готовые объявления по непрозрачному slug. Секреты Telegram
не попадают в JSON и не выдаются браузеру.
"""

from __future__ import annotations

import asyncio
import io
from typing import Any

from aiogram import Bot
from flask import Flask, Response, jsonify, request

from config import Settings
from database import Database, Listing


def _public_listing_config(
    listing: Listing,
    database: Database,
    settings: Settings,
    request_base_url: str,
) -> dict[str, Any]:
    profile = database.get_profile_any(listing.profile_id)
    if profile is None:
        raise LookupError("Профиль карточки не найден")

    shipping = None
    if listing.shipping_template_id is not None:
        shipping = database.get_shipping_template_for_owner(
            listing.shipping_template_id,
            listing.owner_id,
        )

    service_media_base = f"{request_base_url}/api/public/listings/{listing.public_slug}/media"
    image_url = (
        f"{service_media_base}/listing"
        if listing.photo_file_id
        else None
    )
    logo_url = (
        f"{service_media_base}/logo"
        if profile.logo_file_id
        else None
    )
    favicon_url = (
        f"{service_media_base}/favicon"
        if profile.favicon_file_id
        else logo_url
    )

    shipping_info = shipping.formatted() if shipping else listing.delivery_info
    return {
        "listing_id": listing.public_slug,
        "service": {
            "name": profile.display_name,
            "logo_url": logo_url,
            "favicon_url": favicon_url,
            "theme": {
                "mode": profile.theme_mode,
                "primary": profile.primary_color or "#D52B1E",
                "accent": "#FFFFFF",
            },
        },
        "listing": {
            "title": listing.title,
            "description": "",
            "image_url": image_url,
            "price": f"{listing.price_cents / 100:.2f}",
            "currency": listing.currency,
            "delivery_info": shipping_info,
            "seller_contact": settings.support_username,
        },
        "meta": {
            "status": listing.status,
            "public_url": f"{settings.public_base_url}/p/{listing.public_slug}",
            "api_url": f"{request_base_url}/api/public/listings/{listing.public_slug}",
        },
    }


def _find_asset(listing: Listing, profile: Any, asset: str) -> str | None:
    if asset == "listing":
        return listing.photo_file_id
    if asset == "logo":
        return profile.logo_file_id
    if asset == "favicon":
        return profile.favicon_file_id or profile.logo_file_id
    return None


def _download_telegram_file(token: str, file_id: str) -> tuple[bytes, str]:
    async def download() -> tuple[bytes, str]:
        bot = Bot(token=token)
        try:
            telegram_file = await bot.get_file(file_id)
            if not telegram_file.file_path:
                raise FileNotFoundError("Telegram file path is empty")
            buffer = io.BytesIO()
            await bot.download_file(telegram_file.file_path, destination=buffer)
            return buffer.getvalue(), telegram_file.file_path
        finally:
            await bot.session.close()

    return asyncio.run(download())


def create_app(database: Database, settings: Settings) -> Flask:
    app = Flask(__name__)

    @app.after_request
    def add_cors_headers(response: Response) -> Response:
        if request.path.startswith("/api/"):
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        return response

    @app.get("/")
    def health() -> tuple[dict[str, str], int]:
        return {"status": "ok", "service": "catalog-studio-api"}, 200

    @app.get("/health")
    def health_check() -> tuple[dict[str, str], int]:
        return {"status": "ok"}, 200

    @app.get("/api/public/listings/<slug>")
    def public_listing(slug: str):
        listing = database.get_listing_by_slug(slug)
        if listing is None or listing.status != "ready":
            return jsonify({"error": "listing_not_found"}), 404
        base_url = request.url_root.rstrip("/")
        return jsonify(_public_listing_config(listing, database, settings, base_url))

    @app.get("/api/public/listings/<slug>/media/<asset>")
    def public_media(slug: str, asset: str):
        listing = database.get_listing_by_slug(slug)
        if listing is None or listing.status != "ready":
            return jsonify({"error": "listing_not_found"}), 404
        profile = database.get_profile_any(listing.profile_id)
        if profile is None:
            return jsonify({"error": "profile_not_found"}), 404
        file_id = _find_asset(listing, profile, asset)
        if not file_id:
            return jsonify({"error": "media_not_found"}), 404
        try:
            content, file_path = _download_telegram_file(settings.bot_token, file_id)
        except Exception:
            return jsonify({"error": "media_unavailable"}), 502
        extension = file_path.rsplit(".", 1)[-1].lower() if "." in file_path else "jpg"
        mimetype = {
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "png": "image/png",
            "webp": "image/webp",
        }.get(extension, "application/octet-stream")
        return Response(content, mimetype=mimetype, max_age=300)

    return app


def start_api_server(database: Database, settings: Settings) -> None:
    app = create_app(database, settings)
    app.run(host="0.0.0.0", port=settings.port, use_reloader=False)
