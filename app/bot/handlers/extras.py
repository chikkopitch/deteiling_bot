from uuid import UUID

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards import contact_keyboard, main_menu
from app.bot.keyboards.callbacks import (
    AdminCallback,
    BookingCallback,
    CatalogCallback,
    MenuCallback,
)
from app.bot.states import CalculatorStates, ManagerStates
from app.config import Settings
from app.models import AuditLog, ManagerRequest, User
from app.repositories import CatalogRepository
from app.services import PricingService
from app.utils.phone import normalize_phone

router = Router(name="extras")


async def show_calc_classes(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(CalculatorStates.vehicle_class)
    buttons = [
        [
            InlineKeyboardButton(
                text=item.title(),
                callback_data=BookingCallback(action="calc_class", value=item).pack(),
            )
        ]
        for item in ("компакт", "седан", "кроссовер", "внедорожник")
    ]
    if callback.message:
        await callback.message.edit_text(
            "Выберите класс автомобиля:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )


@router.callback_query(MenuCallback.filter(F.section == "calculator"))
async def calculator(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    items = await CatalogRepository(session).services()
    buttons = [
        [
            InlineKeyboardButton(
                text=x.name,
                callback_data=BookingCallback(action="calc_service", value=str(x.id)).pack(),
            )
        ]
        for x in items
    ]
    await state.set_state(CalculatorStates.service)
    if callback.message:
        await callback.message.edit_text(
            "Какую услугу рассчитать?", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
    await callback.answer()


@router.callback_query(CalculatorStates.service, BookingCallback.filter(F.action == "calc_service"))
async def calc_service(
    callback: CallbackQuery, callback_data: BookingCallback, state: FSMContext
) -> None:
    await state.update_data(calc_service_id=callback_data.value)
    await show_calc_classes(callback, state)
    await callback.answer()


@router.callback_query(CatalogCallback.filter(F.action == "calculate_service"))
async def calculate_service_from_catalog(
    callback: CallbackQuery, callback_data: CatalogCallback, state: FSMContext
) -> None:
    await state.update_data(calc_service_id=callback_data.value)
    await show_calc_classes(callback, state)
    await callback.answer()


@router.callback_query(
    CalculatorStates.vehicle_class, BookingCallback.filter(F.action == "calc_class")
)
async def calc_class(
    callback: CallbackQuery, callback_data: BookingCallback, state: FSMContext
) -> None:
    await state.update_data(calc_class=callback_data.value)
    await state.set_state(CalculatorStates.condition)
    buttons = [
        [
            InlineKeyboardButton(
                text=x.title(),
                callback_data=BookingCallback(action="calc_condition", value=x).pack(),
            )
        ]
        for x in ("лёгкое", "среднее", "сильное", "осмотр")
    ]
    if callback.message:
        await callback.message.edit_text(
            "Оцените состояние:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
    await callback.answer()


@router.callback_query(
    CalculatorStates.condition, BookingCallback.filter(F.action == "calc_condition")
)
async def calc_condition(
    callback: CallbackQuery,
    callback_data: BookingCallback,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    data = await state.get_data()
    await state.update_data(calc_condition=callback_data.value, calc_options=[])
    rule = await CatalogRepository(session).price_rule(
        UUID(data["calc_service_id"]), data["calc_class"]
    )
    if rule is None:
        if callback.message:
            await callback.message.edit_text(
                "Для выбранных параметров нужен бесплатный осмотр.", reply_markup=main_menu()
            )
        await state.clear()
        await callback.answer()
        return
    buttons = [
        [
            InlineKeyboardButton(
                text=option,
                callback_data=BookingCallback(action="calc_option", value=option).pack(),
            )
        ]
        for option in rule.options
    ]
    buttons.append(
        [
            InlineKeyboardButton(
                text="Рассчитать", callback_data=BookingCallback(action="calc_done").pack()
            )
        ]
    )
    await state.set_state(CalculatorStates.options)
    if callback.message:
        await callback.message.edit_text(
            "Выберите дополнительные опции (можно несколько) или сразу рассчитайте стоимость:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        )
    await callback.answer()


@router.callback_query(CalculatorStates.options, BookingCallback.filter(F.action == "calc_option"))
async def calc_option(
    callback: CallbackQuery, callback_data: BookingCallback, state: FSMContext
) -> None:
    data = await state.get_data()
    selected = set(data.get("calc_options", []))
    selected.symmetric_difference_update({callback_data.value})
    await state.update_data(calc_options=list(selected))
    await callback.answer(f"Выбрано опций: {len(selected)}")


@router.callback_query(CalculatorStates.options, BookingCallback.filter(F.action == "calc_done"))
async def calc_result(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    try:
        result = await PricingService(session).calculate(
            UUID(data["calc_service_id"]),
            data["calc_class"],
            data["calc_condition"],
            data.get("calc_options", []),
        )
    except LookupError as error:
        text = str(error)
    else:
        text = f"Ориентировочная цена: от {result.minimum:.0f} до {result.maximum:.0f} ₽.\nФакторы: {', '.join(result.factors)}\n\nТочную стоимость назовём после бесплатного осмотра."
    await state.clear()
    if callback.message:
        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="Записаться на бесплатный осмотр",
                            callback_data=MenuCallback(section="booking").pack(),
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="Главное меню", callback_data=MenuCallback(section="main").pack()
                        )
                    ],
                ]
            ),
        )
    await callback.answer()


@router.callback_query(MenuCallback.filter(F.section == "manager"))
async def manager(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(ManagerStates.question)
    if callback.message:
        await callback.message.edit_text("Напишите вопрос менеджеру.")
    await callback.answer()


@router.message(ManagerStates.question)
async def manager_question(message: Message, state: FSMContext, db_user: User) -> None:
    text = (message.text or "").strip()
    if not 3 <= len(text) <= 2000:
        await message.answer("Напишите вопрос длиной от 3 до 2000 символов.")
        return
    await state.update_data(manager_text=text, manager_photos=[], manager_phone=db_user.phone)
    await state.set_state(ManagerStates.photos)
    await message.answer(
        "При желании приложите до 3 фото. Затем нажмите «Готово».",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Готово",
                        callback_data=BookingCallback(action="manager_photos_done").pack(),
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="Пропустить",
                        callback_data=BookingCallback(action="manager_photos_done").pack(),
                    )
                ],
            ]
        ),
    )


@router.message(ManagerStates.photos, F.photo)
async def manager_photo(message: Message, state: FSMContext) -> None:
    if not message.photo:
        return
    data = await state.get_data()
    photos = list(data.get("manager_photos", []))
    item = message.photo[-1]
    if item.file_unique_id in {photo["unique_id"] for photo in photos}:
        await message.answer("Это фото уже добавлено.")
        return
    if len(photos) >= 3:
        await message.answer("Можно приложить не более 3 фото.")
        return
    photos.append({"file_id": item.file_id, "unique_id": item.file_unique_id})
    await state.update_data(manager_photos=photos)
    await message.answer(f"Добавлено фото: {len(photos)} из 3.")


@router.callback_query(
    ManagerStates.photos, BookingCallback.filter(F.action == "manager_photos_done")
)
async def manager_photos_done(
    callback: CallbackQuery,
    state: FSMContext,
    db_user: User,
    session: AsyncSession,
    settings: Settings,
) -> None:
    data = await state.get_data()
    if data.get("manager_phone"):
        if callback.message:
            await callback.message.edit_text("Обращение отправлено менеджеру.")
        await create_request(
            callback.message,
            state,
            db_user,
            session,
            data["manager_text"],
            data["manager_phone"],
            settings,
        )
    else:
        await state.set_state(ManagerStates.phone)
        if callback.message:
            await callback.message.edit_text(
                "Оставьте телефон для ответа:", reply_markup=contact_keyboard()
            )
    await callback.answer()


@router.message(ManagerStates.phone)
async def manager_phone(
    message: Message, state: FSMContext, db_user: User, session: AsyncSession, settings: Settings
) -> None:
    raw = message.contact.phone_number if message.contact else message.text or ""
    try:
        phone = normalize_phone(raw)
    except ValueError as error:
        await message.answer(str(error))
        return
    data = await state.get_data()
    await create_request(message, state, db_user, session, data["manager_text"], phone, settings)


async def create_request(
    message: Message | None,
    state: FSMContext,
    user: User,
    session: AsyncSession,
    text: str,
    phone: str,
    settings: Settings,
) -> None:
    data = await state.get_data()
    photos = list(data.get("manager_photos", []))
    request = ManagerRequest(
        user_id=user.id,
        text=text,
        phone=phone,
        photo_file_ids=[photo["file_id"] for photo in photos],
    )
    session.add(request)
    await session.flush()
    session.add(
        AuditLog(
            actor_user_id=user.id,
            action="manager_request.created",
            entity_type="manager_request",
            entity_id=request.id,
            details={},
        )
    )
    await session.commit()
    await state.clear()
    card = f"Новое обращение #{str(request.id)[:8]}\nКлиент: {user.first_name}\nТелефон: {phone}\nВопрос: {text}"
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Ответить",
                    callback_data=AdminCallback(
                        action="manager_reply", entity_id=str(request.id)
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text="Закрыть",
                    callback_data=AdminCallback(
                        action="manager_close", entity_id=str(request.id)
                    ).pack(),
                ),
            ],
            [
                InlineKeyboardButton(text="Позвонить", url=f"tel:{phone}"),
                InlineKeyboardButton(
                    text="Открыть профиль", url=f"tg://user?id={user.telegram_id}"
                ),
            ],
        ]
    )
    for staff_id in settings.MANAGER_IDS or settings.ADMIN_IDS:
        await message.bot.send_message(staff_id, card, reply_markup=keyboard) if message else None
        for photo in photos:
            await message.bot.send_photo(staff_id, photo["file_id"]) if message else None
    if message:
        await message.answer(
            "Обращение принято. Менеджер свяжется с вами.", reply_markup=main_menu()
        )
