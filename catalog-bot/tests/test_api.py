from __future__ import annotations

import tempfile
from pathlib import Path

from api import create_app
from config import Settings
from database import Database


def main() -> None:
    with tempfile.TemporaryDirectory() as temporary_directory:
        database = Database(Path(temporary_directory) / "catalog.db")
        database.initialize(admin_id=100)
        creator, _ = database.request_access(200, "creator", "Test Creator")
        assert creator.access_status == "pending"
        database.approve_user(200)

        shipping = database.create_shipping_template(
            owner_id=200,
            label="Основной",
            city="Zürich",
            zip_code="8001",
            contact_name="Test Store",
            street="Bahnhofstrasse 45",
        )
        profile = database.create_profile(
            owner_id=200,
            display_name="Test1 Store",
            logo_file_id=None,
            theme_mode="red",
            primary_color=None,
            favicon_file_id=None,
        )
        listing = database.create_listing(
            owner_id=200,
            profile_id=profile.id,
            title="Test Product",
            price_cents=12050,
            currency="CHF",
            delivery_info=shipping.formatted(),
            photo_file_id=None,
            status="ready",
            shipping_template_id=shipping.id,
        )
        draft = database.create_listing(
            owner_id=200,
            profile_id=profile.id,
            title="Draft Product",
            price_cents=1000,
            currency="CHF",
            delivery_info=shipping.formatted(),
            photo_file_id=None,
            status="draft",
            shipping_template_id=shipping.id,
        )

        settings = Settings(
            bot_token="test-token-not-used",
            admin_id=100,
            database_path=Path(temporary_directory) / "catalog.db",
            project_title="Catalog Studio",
            project_description="Test",
            support_username="@support",
            community_url=None,
            project_image_file_id=None,
            default_currency="CHF",
            public_base_url="https://safe-swiss.online",
            port=10000,
        )
        client = create_app(database, settings).test_client()

        response = client.get(f"/api/public/listings/{listing.public_slug}")
        assert response.status_code == 200
        payload = response.get_json()
        assert payload["listing_id"] == listing.public_slug
        assert payload["service"]["name"] == "Test1 Store"
        assert payload["listing"]["title"] == "Test Product"
        assert payload["listing"]["price"] == "120.50"
        assert payload["listing"]["delivery_info"].startswith("Город: Zürich")
        assert "bot-token" not in response.get_data(as_text=True)

        assert client.get(f"/api/public/listings/{draft.public_slug or 'missing'}").status_code == 404
        assert client.get("/api/public/listings/not-found").status_code == 404

    print("Flask public API scenarios passed")


if __name__ == "__main__":
    main()
