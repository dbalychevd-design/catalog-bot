"""Небольшой автономный тест ключевых сценариев SQLite."""

from __future__ import annotations

import tempfile
from pathlib import Path

from database import Database


def main() -> None:
    with tempfile.TemporaryDirectory() as temporary_directory:
        db = Database(Path(temporary_directory) / "catalog.db")
        db.initialize(admin_id=100)

        owner = db.get_user(100)
        assert owner is not None and owner.is_admin

        creator, created = db.request_access(200, "creator", "Test Creator")
        assert created and creator.access_status == "pending"
        assert len(db.list_pending_users()) == 1

        creator = db.approve_user(200)
        assert creator is not None and creator.role == "creator" and creator.can_manage_content

        second, created = db.request_access(300, "second", "Second Creator")
        assert created and second.access_status == "pending"
        second = db.approve_user(300)
        assert second is not None and second.can_manage_content

        first_shipping = db.create_shipping_template(
            owner_id=200,
            label="Основной",
            city="Zürich",
            zip_code="8001",
            contact_name="Test Store",
            street="Bahnhofstrasse 45",
        )
        second_shipping = db.create_shipping_template(
            owner_id=200,
            label="Магазин · Bern",
            city="Bern",
            zip_code="3000",
            contact_name="Test Store Bern",
            street="Marktgasse 10",
        )
        assert first_shipping.is_default
        assert not second_shipping.is_default
        assert len(db.list_shipping_templates(200)) == 2
        assert db.get_shipping_template_for_owner(first_shipping.id, 300) is None
        assert "ZIP-код: 8001" in first_shipping.formatted()
        assert db.set_default_shipping_template(second_shipping.id, 200)
        assert db.get_default_shipping_template(200).id == second_shipping.id

        profile = db.create_profile(
            owner_id=200,
            display_name="Test1 Store",
            logo_file_id="logo-file-id",
            theme_mode="red",
            primary_color=None,
            favicon_file_id="logo-file-id",
        )
        assert profile.is_default
        assert db.get_profile_for_owner(profile.id, 200) is not None
        assert db.get_profile_for_owner(profile.id, 300) is None
        admin_profile = db.get_profile_any(profile.id)
        assert admin_profile is not None and admin_profile.owner_name == "Test Creator"
        assert len(db.list_all_profiles()) == 1

        listing = db.create_listing(
            owner_id=200,
            profile_id=profile.id,
            title="Test Product",
            price_cents=12050,
            currency="CHF",
            delivery_info=first_shipping.formatted(),
            photo_file_id="photo-file-id",
            status="ready",
            shipping_template_id=first_shipping.id,
        )
        assert listing.formatted_price == "120.50 CHF"
        assert listing.shipping_template_id == first_shipping.id
        assert listing.public_slug is not None and len(listing.public_slug) == 8
        assert listing.public_slug.isalnum()
        updated_listing = db.update_listing_photo(listing.id, 200, "replacement-photo-id")
        assert updated_listing is not None and updated_listing.photo_file_id == "replacement-photo-id"
        cleared_listing = db.update_listing_photo(listing.id, 200, None)
        assert cleared_listing is not None and cleared_listing.photo_file_id is None
        assert len(db.list_listings(200)) == 1
        assert db.get_listing_for_owner(listing.id, 300) is None
        admin_listing = db.get_listing_any(listing.id)
        assert admin_listing is not None and admin_listing.owner_name == "Test Creator"
        assert len(db.list_all_listings()) == 1
        assert not db.delete_listing(listing.id, 300)
        assert db.delete_listing_as_admin(listing.id)

        draft = db.create_listing(
            owner_id=200,
            profile_id=profile.id,
            title="Draft Product",
            price_cents=9900,
            currency="CHF",
            delivery_info=first_shipping.formatted(),
            photo_file_id=None,
            status="draft",
            shipping_template_id=first_shipping.id,
        )
        assert draft.public_slug is None

        assert db.set_user_role(300, "viewer") is not None
        viewer = db.get_user(300)
        assert viewer is not None and not viewer.can_manage_content

        stats = db.get_stats()
        assert stats.approved_users == 3
        assert stats.profile_count == 1
        assert stats.listing_count == 1

    print("SQLite scenarios passed")


if __name__ == "__main__":
    main()
