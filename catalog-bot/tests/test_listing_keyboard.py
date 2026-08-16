from __future__ import annotations

from database import Listing
from keyboards import listing_details_keyboard


def main() -> None:
    listing = Listing(
        id=1,
        owner_id=2,
        profile_id=3,
        title="Test Product",
        price_cents=12050,
        currency="CHF",
        delivery_info="Город: Zürich",
        photo_file_id="photo-id",
        status="ready",
        created_at="now",
        updated_at="now",
        profile_name="Test Service",
        public_slug="aB7xK2mQ",
    )
    keyboard = listing_details_keyboard(listing, is_owner=True, public_url="https://example.com/p/aB7xK2mQ")
    buttons = [button for row in keyboard.inline_keyboard for button in row]
    assert any(button.url == "https://example.com/p/aB7xK2mQ" for button in buttons)
    assert any(button.callback_data == "listing:photo:replace:1" for button in buttons)
    assert any(button.callback_data == "listing:photo:delete:1" for button in buttons)
    print("Listing keyboard passed")


if __name__ == "__main__":
    main()
