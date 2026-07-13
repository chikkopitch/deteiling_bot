from app.bot.keyboards.admin import ADMIN_SECTIONS, admin_menu_keyboard


def test_admin_menu_only_contains_implemented_sections() -> None:
    assert tuple(section for section, _ in ADMIN_SECTIONS) == (
        "schedule",
        "free_slots",
        "services",
        "prices",
        "calculator",
        "faq",
        "requests",
        "settings",
    )

    keyboard = admin_menu_keyboard()
    assert len(keyboard.inline_keyboard) == 4
