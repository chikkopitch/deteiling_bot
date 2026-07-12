import phonenumbers


def normalize_phone(value: str, region: str = "RU") -> str:
    parsed = phonenumbers.parse(value, region)
    if not phonenumbers.is_valid_number(parsed):
        raise ValueError("Введите корректный номер телефона")
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


def mask_phone(value: str) -> str:
    return f"{value[:2]}***{value[-4:]}" if len(value) >= 7 else "***"
