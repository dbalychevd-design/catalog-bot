"""Состояния диалогов aiogram."""

from aiogram.fsm.state import State, StatesGroup


class ProfileCreation(StatesGroup):
    waiting_for_name = State()
    waiting_for_logo = State()
    waiting_for_theme = State()
    waiting_for_custom_color = State()
    waiting_for_favicon = State()
    confirming = State()


class ShippingTemplateCreation(StatesGroup):
    waiting_for_label = State()
    waiting_for_city = State()
    waiting_for_zip_code = State()
    waiting_for_contact_name = State()
    waiting_for_street = State()


class ListingPhotoEdit(StatesGroup):
    waiting_for_photo = State()


class ListingCreation(StatesGroup):
    choosing_profile = State()
    choosing_shipping = State()
    waiting_for_title = State()
    waiting_for_price = State()
    waiting_for_delivery_info = State()
    waiting_for_photo = State()
    confirming = State()
