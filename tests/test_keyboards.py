from app.bot.keyboards import main_menu


def test_main_menu_has_all_sections() -> None:
    texts = [button.text for row in main_menu().inline_keyboard for button in row]
    assert texts == [
        "🚗 Записаться на бесплатный осмотр",
        "✨ Услуги и цены",
        "🧮 Рассчитать стоимость",
        "📅 Моя запись",
        "❓ Частые вопросы",
        "💬 Связаться с менеджером",
    ]
