from decimal import Decimal
from uuid import UUID
from app.database.models import (
    Admin,
    AdminAuditLog,
    CalculationFactor,
    CalculationFactorValue,
    FAQItem,
    Service,
    ServicePrice,
)
from app.database.repositories import AdminAuditLogRepository

ENTITY_MODELS = {
    "service": Service,
    "price": ServicePrice,
    "faq": FAQItem,
    "factor": CalculationFactor,
    "factor_value": CalculationFactorValue,
}
ALLOWED_FIELDS = {
    "service": {
        "name": str,
        "short_description": str,
        "full_description": str,
        "base_price": Decimal,
        "duration_minutes": int,
        "is_active": bool,
        "sort_order": int,
    },
    "price": {"price": Decimal, "min_price": Decimal, "max_price": Decimal},
    "faq": {
        "question": str,
        "answer": str,
        "keywords": str,
        "category": str,
        "is_active": bool,
        "sort_order": int,
    },
    "factor": {"name": str, "input_type": str, "is_active": bool, "sort_order": int},
    "factor_value": {
        "label": str,
        "coefficient": Decimal,
        "fixed_surcharge": Decimal,
        "is_active": bool,
        "sort_order": int,
    },
}


def _json(value):
    return str(value) if isinstance(value, Decimal) else value


class EntityAdminService:
    def __init__(self, session):
        self.session = session
        self.audit = AdminAuditLogRepository(session)

    async def preview(self, entity, entity_id, updates):
        if entity not in ENTITY_MODELS:
            raise ValueError("Тип сущности недоступен.")
        obj = await self.session.get(ENTITY_MODELS[entity], entity_id)
        if obj is None:
            raise ValueError("Запись не найдена.")
        converted = {}
        for key, value in updates.items():
            converter = ALLOWED_FIELDS[entity].get(key)
            if converter is None:
                raise ValueError(f"Поле {key} недоступно.")
            if value is None and key in {
                "min_price",
                "max_price",
                "keywords",
                "category",
                "short_description",
                "full_description",
            }:
                converted[key] = None
            elif converter is bool:
                if not isinstance(value, bool):
                    raise ValueError(f"Поле {key} должно быть true/false.")
                converted[key] = value
            else:
                converted[key] = converter(value)
        old = {key: _json(getattr(obj, key)) for key in converted}
        new = {key: _json(value) for key, value in converted.items()}
        return obj, converted, old, new

    async def save(
        self,
        admin: Admin,
        entity: str,
        entity_id: UUID,
        updates: dict,
        expected_old: dict,
    ):
        obj, converted, old, new = await self.preview(entity, entity_id, updates)
        if old != expected_old:
            raise ValueError("Запись уже изменена другим администратором.")
        for key, value in converted.items():
            setattr(obj, key, value)
        await self.audit.add(
            AdminAuditLog(
                admin_id=admin.id,
                action=f"{entity}_updated",
                entity_type=entity,
                entity_id=obj.id,
                old_value=old,
                new_value=new,
            )
        )
        await self.session.flush()
        return obj
