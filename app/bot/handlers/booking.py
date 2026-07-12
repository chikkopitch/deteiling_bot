from collections import defaultdict
from datetime import date, datetime, timedelta
from uuid import UUID, uuid4

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.bot.keyboards import contact_keyboard, main_menu, navigation
from app.bot.keyboards.callbacks import AdminCallback, BookingCallback, MenuCallback
from app.bot.states import AppointmentStates, BookingStates
from app.config import Settings
from app.models import BookingStatus, Service, SlotStatus, TimeSlot, User
from app.repositories import BookingRepository, CatalogRepository
from app.schemas import BookingDraft, PhotoDraft
from app.services import AvailabilityService, BookingService
from app.services.errors import InvalidTransitionError, SlotUnavailableError
from app.utils.datetime import format_studio_time, utc_now

router = Router(name="booking")
CLASSES = ("компакт", "седан", "универсал", "кроссовер", "внедорожник", "минивэн", "купе", "другой")
PAGE_SIZE = 8
PHOTO_DOCUMENT_TYPES = {"image/jpeg", "image/png", "image/webp"}


def normalize_vehicle_name(value: str, limit: int) -> str | None:
    normalized = " ".join(value.split())
    if not normalized or len(normalized) > limit:
        return None
    return normalized


async def render_brands(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    page: int = 0,
    query: str | None = None,
) -> None:
    brands = await CatalogRepository(session).brands(query, PAGE_SIZE + 1, page * PAGE_SIZE)
    visible, has_next = brands[:PAGE_SIZE], len(brands) > PAGE_SIZE
    buttons = [
        [
            InlineKeyboardButton(
                text=item.name,
                callback_data=BookingCallback(action="brand", value=str(item.id)).pack(),
            )
        ]
        for item in visible
    ]
    pager: list[InlineKeyboardButton] = []
    if page:
        pager.append(
            InlineKeyboardButton(
                text="←",
                callback_data=BookingCallback(action="brand_page", value=str(page - 1)).pack(),
            )
        )
    if has_next:
        pager.append(
            InlineKeyboardButton(
                text="→",
                callback_data=BookingCallback(action="brand_page", value=str(page + 1)).pack(),
            )
        )
    if pager:
        buttons.append(pager)
    buttons.extend(
        [
            [
                InlineKeyboardButton(
                    text="🔎 Найти марку",
                    callback_data=BookingCallback(action="brand_search").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="Другой бренд", callback_data=BookingCallback(action="brand_other").pack()
                )
            ],
            *navigation(cancel=True),
        ]
    )
    await state.set_state(BookingStates.brand)
    await state.update_data(brand_query=query or "", brand_input_mode=None)
    title = "Выберите марку автомобиля:" if not query else f"Результаты поиска: {query}"
    if callback.message:
        await callback.message.edit_text(
            title, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )


async def render_models(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, page: int = 0
) -> None:
    data = await state.get_data()
    brand_id = data.get("brand_id")
    if not brand_id:
        await render_brands(callback, state, session)
        return
    models = await CatalogRepository(session).models(
        UUID(brand_id), PAGE_SIZE + 1, page * PAGE_SIZE
    )
    visible, has_next = models[:PAGE_SIZE], len(models) > PAGE_SIZE
    buttons = [
        [
            InlineKeyboardButton(
                text=item.name,
                callback_data=BookingCallback(action="model", value=str(item.id)).pack(),
            )
        ]
        for item in visible
    ]
    pager: list[InlineKeyboardButton] = []
    if page:
        pager.append(
            InlineKeyboardButton(
                text="←",
                callback_data=BookingCallback(action="model_page", value=str(page - 1)).pack(),
            )
        )
    if has_next:
        pager.append(
            InlineKeyboardButton(
                text="→",
                callback_data=BookingCallback(action="model_page", value=str(page + 1)).pack(),
            )
        )
    if pager:
        buttons.append(pager)
    buttons.extend(
        [
            [
                InlineKeyboardButton(
                    text="Ввести модель", callback_data=BookingCallback(action="model_other").pack()
                )
            ],
            *navigation(back="brand", cancel=True),
        ]
    )
    await state.set_state(BookingStates.model)
    await state.update_data(model_input_mode=None)
    if callback.message:
        await callback.message.edit_text(
            "Выберите модель:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )


async def render_vehicle_class(callback: CallbackQuery, state: FSMContext) -> None:
    buttons = [
        [
            InlineKeyboardButton(
                text=item.title(), callback_data=BookingCallback(action="class", value=item).pack()
            )
        ]
        for item in CLASSES
    ]
    await state.set_state(BookingStates.vehicle_class)
    if callback.message:
        await callback.message.edit_text(
            "Выберите класс автомобиля:",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=buttons + navigation(back="year", cancel=True)
            ),
        )


async def render_services(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    services = list(
        await session.scalars(
            select(Service)
            .options(selectinload(Service.category))
            .where(Service.is_active, Service.deleted_at.is_(None))
            .order_by(Service.category_id, Service.sort_order)
        )
    )
    data = await state.get_data()
    selected = set(data.get("service_ids", []))
    grouped: dict[str, list[Service]] = defaultdict(list)
    for item in services:
        grouped[item.category.name].append(item)
    lines = ["Выберите одну или несколько услуг:"]
    buttons: list[list[InlineKeyboardButton]] = []
    for category, items in grouped.items():
        lines.append(f"\n<b>{category}</b>")
        for item in items:
            marker = "✅ " if str(item.id) in selected else ""
            lines.append(f"• {item.name} — от {item.price_from:.0f} ₽")
            buttons.append(
                [
                    InlineKeyboardButton(
                        text=f"{marker}{item.name}",
                        callback_data=BookingCallback(action="service", value=str(item.id)).pack(),
                    ),
                    InlineKeyboardButton(
                        text="ℹ️",
                        callback_data=BookingCallback(
                            action="service_info", value=str(item.id)
                        ).pack(),
                    ),
                ]
            )
    buttons.append(
        [
            InlineKeyboardButton(
                text=f"Продолжить ({len(selected)})",
                callback_data=BookingCallback(action="services_done").pack(),
            )
        ]
    )
    buttons.extend(navigation(back="vehicle_class", cancel=True))
    await state.set_state(BookingStates.services)
    if callback.message:
        await callback.message.edit_text(
            "\n".join(lines),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
            parse_mode="HTML",
        )


async def render_summary(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    service_ids = [UUID(value) for value in data.get("service_ids", [])]
    services = list(await session.scalars(select(Service).where(Service.id.in_(service_ids))))
    names = ", ".join(item.name for item in services)
    text = f"Проверьте автомобиль и услуги:\n\nМарка: {data.get('brand')}\nМодель: {data.get('model')}\nГод: {data.get('year')}\nКласс: {data.get('vehicle_class')}\nУслуги: {names}"
    buttons = [
        [
            InlineKeyboardButton(
                text="Всё верно", callback_data=BookingCallback(action="summary_confirm").pack()
            )
        ],
        [
            InlineKeyboardButton(
                text="Изменить автомобиль",
                callback_data=BookingCallback(action="summary_vehicle").pack(),
            )
        ],
        [
            InlineKeyboardButton(
                text="Изменить услуги",
                callback_data=BookingCallback(action="summary_services").pack(),
            )
        ],
        *navigation(cancel=True),
    ]
    await state.set_state(BookingStates.summary)
    if callback.message:
        await callback.message.edit_text(
            text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )


def photo_controls(count: int) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text="Готово", callback_data=BookingCallback(action="photos_done").pack()
            )
        ],
        [
            InlineKeyboardButton(
                text="Пропустить", callback_data=BookingCallback(action="photos_done").pack()
            )
        ],
    ]
    if count:
        rows.append(
            [
                InlineKeyboardButton(
                    text="Удалить последнее фото",
                    callback_data=BookingCallback(action="photo_delete_last").pack(),
                )
            ]
        )
    rows.extend(navigation(back="summary", cancel=True))
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def add_photo(
    message: Message,
    state: FSMContext,
    settings: Settings,
    *,
    file_id: str,
    unique_file_id: str,
    mime_type: str,
    size_bytes: int,
) -> None:
    data = await state.get_data()
    photos = list(data.get("photos", []))
    if size_bytes > settings.MAX_PHOTO_SIZE_MB * 1024 * 1024:
        await message.answer(f"Размер файла не должен превышать {settings.MAX_PHOTO_SIZE_MB} МБ.")
        return
    if any(item["unique_file_id"] == unique_file_id for item in photos):
        await message.answer("Это фото уже добавлено.")
        return
    if len(photos) >= settings.MAX_PHOTOS_PER_BOOKING:
        await message.answer(f"Можно добавить не больше {settings.MAX_PHOTOS_PER_BOOKING} фото.")
        return
    photos.append(
        {
            "file_id": file_id,
            "unique_file_id": unique_file_id,
            "size": size_bytes,
            "mime": mime_type,
        }
    )
    await state.update_data(photos=photos)
    await message.answer(
        f"Добавлено: {len(photos)}. Можно добавить ещё: {settings.MAX_PHOTOS_PER_BOOKING - len(photos)}.",
        reply_markup=photo_controls(len(photos)),
    )


@router.callback_query(MenuCallback.filter(F.section == "booking"))
async def begin(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    await state.clear()
    await render_brands(callback, state, session)
    await callback.answer()


@router.callback_query(BookingStates.brand, BookingCallback.filter(F.action == "brand_page"))
async def brand_page(
    callback: CallbackQuery,
    callback_data: BookingCallback,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    data = await state.get_data()
    await render_brands(
        callback, state, session, int(callback_data.value), data.get("brand_query") or None
    )
    await callback.answer()


@router.callback_query(BookingStates.brand, BookingCallback.filter(F.action == "brand_search"))
async def brand_search(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(brand_input_mode="search")
    if callback.message:
        await callback.message.edit_text(
            "Напишите марку для поиска:",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=navigation(back="brand", cancel=True)
            ),
        )
    await callback.answer()


@router.callback_query(BookingStates.brand, BookingCallback.filter(F.action == "brand"))
async def choose_brand(
    callback: CallbackQuery,
    callback_data: BookingCallback,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    from app.models import VehicleBrand

    brand = await session.get(VehicleBrand, UUID(callback_data.value))
    if brand is None or not brand.is_active:
        await callback.answer("Эта кнопка устарела. Выберите марку заново.", show_alert=True)
        return
    await state.update_data(brand=brand.name, brand_id=str(brand.id), brand_input_mode=None)
    await render_models(callback, state, session)
    await callback.answer()


@router.callback_query(BookingStates.model, BookingCallback.filter(F.action == "model_page"))
async def model_page(
    callback: CallbackQuery,
    callback_data: BookingCallback,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    await render_models(callback, state, session, int(callback_data.value))
    await callback.answer()


@router.callback_query(BookingStates.brand, BookingCallback.filter(F.action == "brand_other"))
async def other_brand(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(brand_input_mode="manual")
    if callback.message:
        await callback.message.edit_text(
            "Напишите марку автомобиля:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=navigation(cancel=True)),
        )
    await callback.answer()


@router.message(BookingStates.brand)
async def brand_text(message: Message, state: FSMContext, session: AsyncSession) -> None:
    value = normalize_vehicle_name(message.text or "", 80)
    if value is None:
        await message.answer("Введите название от 1 до 80 символов.")
        return
    data = await state.get_data()
    if data.get("brand_input_mode") == "search":
        brands = await CatalogRepository(session).brands(value, PAGE_SIZE + 1)
        visible, has_next = brands[:PAGE_SIZE], len(brands) > PAGE_SIZE
        buttons = [
            [
                InlineKeyboardButton(
                    text=item.name,
                    callback_data=BookingCallback(action="brand", value=str(item.id)).pack(),
                )
            ]
            for item in visible
        ]
        if has_next:
            buttons.append(
                [
                    InlineKeyboardButton(
                        text="→",
                        callback_data=BookingCallback(action="brand_page", value="1").pack(),
                    )
                ]
            )
        buttons.extend(
            [
                [
                    InlineKeyboardButton(
                        text="Другой бренд",
                        callback_data=BookingCallback(action="brand_other").pack(),
                    )
                ],
                *navigation(back="brand", cancel=True),
            ]
        )
        await state.update_data(brand_query=value, brand_input_mode=None)
        await message.answer(
            f"Результаты поиска: {value}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        )
        return
    await state.update_data(brand=value.title(), brand_id=None, brand_input_mode=None)
    await state.set_state(BookingStates.model)
    await state.update_data(model_input_mode="manual")
    await message.answer(
        "Теперь напишите модель автомобиля:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=navigation(back="brand", cancel=True)),
    )


@router.callback_query(BookingStates.model, BookingCallback.filter(F.action == "model"))
async def choose_model(
    callback: CallbackQuery,
    callback_data: BookingCallback,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    from app.models import VehicleModel

    model = await session.get(VehicleModel, UUID(callback_data.value))
    data = await state.get_data()
    if model is None or not model.is_active or str(model.brand_id) != data.get("brand_id"):
        await callback.answer("Эта кнопка устарела. Выберите модель заново.", show_alert=True)
        return
    await state.update_data(model=model.name, model_input_mode=None)
    await ask_year(callback.message, state)
    await callback.answer()


@router.callback_query(BookingStates.model, BookingCallback.filter(F.action == "model_other"))
async def model_other(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(model_input_mode="manual")
    if callback.message:
        await callback.message.edit_text("Напишите модель автомобиля:")
    await callback.answer()


@router.message(BookingStates.model)
async def model_text(message: Message, state: FSMContext) -> None:
    value = normalize_vehicle_name(message.text or "", 100)
    if value is None:
        await message.answer("Введите модель от 1 до 100 символов.")
        return
    await state.update_data(model=value)
    await ask_year(message, state)


async def ask_year(target: Message | None, state: FSMContext) -> None:
    await state.set_state(BookingStates.year)
    if target:
        await target.answer("Введите год выпуска:")


@router.message(BookingStates.year)
async def year(message: Message, state: FSMContext) -> None:
    current = datetime.now().year
    try:
        value = int(message.text or "")
    except ValueError:
        value = 0
    if value < 1980 or value > current + 1:
        await message.answer(f"Введите год от 1980 до {current + 1}.")
        return
    await state.update_data(year=value)
    await state.set_state(BookingStates.vehicle_class)
    buttons = [
        [
            InlineKeyboardButton(
                text=x.title(), callback_data=BookingCallback(action="class", value=x).pack()
            )
        ]
        for x in CLASSES
    ]
    await message.answer(
        "Выберите класс автомобиля:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons + navigation(cancel=True)),
    )


@router.callback_query(BookingStates.vehicle_class, BookingCallback.filter(F.action == "class"))
async def vehicle_class(
    callback: CallbackQuery,
    callback_data: BookingCallback,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    await state.update_data(vehicle_class=callback_data.value)
    await render_services(callback, state, session)
    await callback.answer()


@router.callback_query(BookingStates.services, BookingCallback.filter(F.action == "service"))
async def toggle_service(
    callback: CallbackQuery,
    callback_data: BookingCallback,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    data = await state.get_data()
    selected = set(data.get("service_ids", []))
    selected.symmetric_difference_update({callback_data.value})
    await state.update_data(service_ids=list(selected))
    await render_services(callback, state, session)
    await callback.answer(f"Выбрано: {len(selected)}")


@router.callback_query(BookingStates.services, BookingCallback.filter(F.action == "service_info"))
async def service_info(
    callback: CallbackQuery, callback_data: BookingCallback, session: AsyncSession
) -> None:
    item = await session.get(Service, UUID(callback_data.value))
    if item is None or not item.is_active:
        await callback.answer("Эта услуга больше недоступна.", show_alert=True)
        return
    await callback.answer(
        f"{item.short_description}\nОриентир: от {item.price_from:.0f} ₽", show_alert=True
    )


@router.callback_query(BookingStates.services, BookingCallback.filter(F.action == "services_done"))
async def services_done(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    if not data.get("service_ids"):
        await callback.answer("Выберите хотя бы одну услугу", show_alert=True)
        return
    await render_summary(callback, state, session)
    await callback.answer()


@router.callback_query(BookingStates.summary, BookingCallback.filter(F.action == "summary_confirm"))
async def summary_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(BookingStates.photos)
    if callback.message:
        await callback.message.edit_text(
            "Пришлите общий вид, проблемные или загрязнённые зоны, салон и отдельные элементы. Фото можно пропустить.",
            reply_markup=photo_controls(0),
        )
    await callback.answer()


@router.callback_query(BookingStates.summary, BookingCallback.filter(F.action == "summary_vehicle"))
async def summary_vehicle(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    await state.update_data(
        brand=None, brand_id=None, model=None, year=None, vehicle_class=None, service_ids=[]
    )
    await render_brands(callback, state, session)
    await callback.answer()


@router.callback_query(
    BookingStates.summary, BookingCallback.filter(F.action == "summary_services")
)
async def summary_services(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession
) -> None:
    await render_services(callback, state, session)
    await callback.answer()


@router.callback_query(BookingCallback.filter(F.action == "back"))
async def back(
    callback: CallbackQuery,
    callback_data: BookingCallback,
    state: FSMContext,
    session: AsyncSession,
    settings: Settings,
) -> None:
    destination = callback_data.value
    if destination == "brand":
        await render_brands(callback, state, session)
    elif destination == "model":
        await render_models(callback, state, session)
    elif destination == "year":
        await state.set_state(BookingStates.year)
        if callback.message:
            await callback.message.edit_text(
                "Введите год выпуска:",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=navigation(back="model", cancel=True)
                ),
            )
    elif destination == "vehicle_class":
        await render_vehicle_class(callback, state)
    elif destination == "services":
        await render_services(callback, state, session)
    elif destination == "summary":
        await render_summary(callback, state, session)
    elif destination == "dates":
        await render_dates(callback, state, session, settings, 0)
    await callback.answer()


@router.message(BookingStates.photos, F.photo)
async def photo(message: Message, state: FSMContext, settings: Settings) -> None:
    if not message.photo:
        return
    item = message.photo[-1]
    await add_photo(
        message,
        state,
        settings,
        file_id=item.file_id,
        unique_file_id=item.file_unique_id,
        mime_type="image/jpeg",
        size_bytes=item.file_size or 0,
    )


@router.message(BookingStates.photos, F.document)
async def photo_document(message: Message, state: FSMContext, settings: Settings) -> None:
    document = message.document
    if document is None:
        return
    if document.mime_type not in PHOTO_DOCUMENT_TYPES:
        await message.answer(
            "Подойдут только изображения JPEG, PNG или WEBP. Видео и архивы не принимаются."
        )
        return
    await add_photo(
        message,
        state,
        settings,
        file_id=document.file_id,
        unique_file_id=document.file_unique_id,
        mime_type=document.mime_type,
        size_bytes=document.file_size or 0,
    )


@router.message(BookingStates.photos, F.video)
async def reject_video(message: Message) -> None:
    await message.answer("Видео не принимаются. Пришлите фото или нажмите «Готово».")


@router.callback_query(
    BookingStates.photos, BookingCallback.filter(F.action == "photo_delete_last")
)
async def delete_last_photo(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    photos = list(data.get("photos", []))
    if not photos:
        await callback.answer("Фото для удаления нет.", show_alert=True)
        return
    photos.pop()
    await state.update_data(photos=photos)
    if callback.message:
        await callback.message.edit_text(
            f"Последнее фото удалено. Сейчас загружено: {len(photos)}.",
            reply_markup=photo_controls(len(photos)),
        )
    await callback.answer()


@router.callback_query(BookingStates.photos, BookingCallback.filter(F.action == "photos_done"))
async def photos_done(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, settings: Settings
) -> None:
    await render_dates(callback, state, session, settings, 0)
    await callback.answer()


async def render_dates(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    settings: Settings,
    week_offset: int,
) -> None:
    availability = AvailabilityService(session, settings.STUDIO_TIMEZONE)
    await availability.release_expired_holds()
    dates = await availability.dates_for_week(week_offset, settings.BOOKING_HORIZON_DAYS)
    buttons = [
        [
            InlineKeyboardButton(
                text=item.strftime("%d.%m.%Y"),
                callback_data=BookingCallback(action="date", value=item.isoformat()).pack(),
            )
        ]
        for item in dates
    ]
    pager: list[InlineKeyboardButton] = []
    if week_offset:
        pager.append(
            InlineKeyboardButton(
                text="← Неделя",
                callback_data=BookingCallback(
                    action="date_week", value=str(week_offset - 1)
                ).pack(),
            )
        )
    if (week_offset + 1) * 7 < settings.BOOKING_HORIZON_DAYS:
        pager.append(
            InlineKeyboardButton(
                text="Следующая неделя →",
                callback_data=BookingCallback(
                    action="date_week", value=str(week_offset + 1)
                ).pack(),
            )
        )
    if pager:
        buttons.append(pager)
    buttons.extend(navigation(back="summary", cancel=True))
    await state.set_state(BookingStates.date)
    if callback.message:
        await callback.message.edit_text(
            "Выберите дату бесплатного осмотра:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        )


@router.callback_query(BookingStates.date, BookingCallback.filter(F.action == "date_week"))
async def date_week(
    callback: CallbackQuery,
    callback_data: BookingCallback,
    state: FSMContext,
    session: AsyncSession,
    settings: Settings,
) -> None:
    await render_dates(callback, state, session, settings, int(callback_data.value))
    await callback.answer()


@router.callback_query(BookingStates.date, BookingCallback.filter(F.action == "date"))
async def select_date(
    callback: CallbackQuery,
    callback_data: BookingCallback,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
    settings: Settings,
) -> None:
    try:
        selected_date = date.fromisoformat(callback_data.value)
    except ValueError:
        await callback.answer("Дата устарела. Выберите её заново.", show_alert=True)
        return
    availability = AvailabilityService(session, settings.STUDIO_TIMEZONE)
    await availability.release_expired_holds()
    slots = await availability.slots_for_date(selected_date, db_user.id)
    buttons = [
        [
            InlineKeyboardButton(
                text=format_studio_time(item.starts_at, settings.STUDIO_TIMEZONE)[-5:],
                callback_data=BookingCallback(action="slot", value=str(item.id)).pack(),
            )
        ]
        for item in slots
    ]
    buttons.extend(navigation(back="dates", cancel=True))
    await state.set_state(BookingStates.slot)
    await state.update_data(selected_date=selected_date.isoformat())
    if callback.message:
        await callback.message.edit_text(
            f"Свободное время на {selected_date.strftime('%d.%m.%Y')}:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        )
    await callback.answer()


@router.callback_query(BookingStates.slot, BookingCallback.filter(F.action == "slot"))
async def select_slot(
    callback: CallbackQuery,
    callback_data: BookingCallback,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
    settings: Settings,
) -> None:
    slot = await session.get(TimeSlot, UUID(callback_data.value))
    if (
        slot is None
        or slot.status in (SlotStatus.BOOKED, SlotStatus.BLOCKED)
        or (
            slot.status == SlotStatus.HELD
            and (
                slot.held_by_user_id != db_user.id
                or not slot.hold_expires_at
                or slot.hold_expires_at <= utc_now()
            )
        )
    ):
        await callback.answer("Это время уже недоступно. Выберите другое.", show_alert=True)
        return
    data = await state.get_data()
    service_ids = [UUID(value) for value in data.get("service_ids", [])]
    services = list(await session.scalars(select(Service).where(Service.id.in_(service_ids))))
    await state.update_data(selected_slot_id=str(slot.id))
    text = (
        f"Проверьте время:\n{format_studio_time(slot.starts_at, settings.STUDIO_TIMEZONE)}\n"
        f"Адрес: {settings.STUDIO_ADDRESS}\n"
        f"Длительность: {(slot.ends_at - slot.starts_at).seconds // 60} мин.\n"
        f"Услуги: {', '.join(item.name for item in services)}"
    )
    if callback.message:
        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="Подтвердить время",
                            callback_data=BookingCallback(action="slot_confirm").pack(),
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="Выбрать другое",
                            callback_data=BookingCallback(action="slot_change").pack(),
                        )
                    ],
                    *navigation(back="dates", cancel=True),
                ]
            ),
        )
    await callback.answer()


@router.callback_query(BookingStates.slot, BookingCallback.filter(F.action == "slot_change"))
async def slot_change(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, settings: Settings
) -> None:
    await render_dates(callback, state, session, settings, 0)
    await callback.answer()


@router.callback_query(BookingStates.slot, BookingCallback.filter(F.action == "slot_confirm"))
async def confirm_slot(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
    settings: Settings,
) -> None:
    data = await state.get_data()
    selected_slot_id = data.get("selected_slot_id")
    if not selected_slot_id:
        await callback.answer("Сначала выберите время.", show_alert=True)
        return
    try:
        await BookingService(session).hold_slot(
            UUID(selected_slot_id), db_user, settings.SLOT_HOLD_MINUTES
        )
        await session.commit()
    except SlotUnavailableError as error:
        await session.rollback()
        await callback.answer(str(error), show_alert=True)
        return
    await state.update_data(slot_id=selected_slot_id)
    await state.set_state(BookingStates.name)
    if callback.message:
        buttons = [
            [
                InlineKeyboardButton(
                    text=f"Использовать имя: {db_user.first_name}",
                    callback_data=BookingCallback(action="name_telegram").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="Ввести другое имя",
                    callback_data=BookingCallback(action="name_manual").pack(),
                )
            ],
            *navigation(back="dates", cancel=True),
        ]
        await callback.message.edit_text(
            "Как к вам обращаться? Можно использовать имя из Telegram или ввести другое.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        )
    await callback.answer()


async def ask_phone(message: Message, state: FSMContext) -> None:
    await state.set_state(BookingStates.phone)
    await message.answer(
        "Поделитесь номером или введите его вручную:", reply_markup=contact_keyboard()
    )


@router.callback_query(BookingStates.name, BookingCallback.filter(F.action == "name_telegram"))
async def use_telegram_name(callback: CallbackQuery, state: FSMContext, db_user: User) -> None:
    await state.update_data(customer_name=" ".join(db_user.first_name.split()))
    await state.set_state(BookingStates.phone)
    if callback.message:
        await callback.message.edit_text(
            "Поделитесь номером или введите его вручную:", reply_markup=contact_keyboard()
        )
    await callback.answer()


@router.callback_query(BookingStates.name, BookingCallback.filter(F.action == "name_manual"))
async def use_manual_name(callback: CallbackQuery) -> None:
    if callback.message:
        await callback.message.edit_text("Напишите имя для заявки (от 2 до 80 символов):")
    await callback.answer()


@router.message(BookingStates.name)
async def name(message: Message, state: FSMContext) -> None:
    value = " ".join((message.text or "").split())
    if not 2 <= len(value) <= 80 or not any(ch.isalpha() for ch in value):
        await message.answer("Введите имя от 2 до 80 символов.")
        return
    await state.update_data(customer_name=value)
    await ask_phone(message, state)


@router.message(BookingStates.phone)
async def phone(message: Message, state: FSMContext) -> None:
    from app.utils.phone import normalize_phone

    raw = message.contact.phone_number if message.contact else message.text or ""
    try:
        value = normalize_phone(raw)
    except ValueError as error:
        await message.answer(str(error))
        return
    await state.update_data(customer_phone=value)
    await state.set_state(BookingStates.consent)
    text = "Мы используем имя и номер только для связи по этой записи. Подтвердите согласие, чтобы отправить заявку."
    await message.answer(
        text,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Согласен на связь по записи",
                        callback_data=BookingCallback(action="consent_yes").pack(),
                    )
                ],
                *navigation(back="contacts", cancel=True),
            ]
        ),
    )


@router.callback_query(BookingStates.consent, BookingCallback.filter(F.action == "consent_yes"))
async def consent_yes(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, settings: Settings
) -> None:
    data = await state.get_data()
    slot = await session.get(TimeSlot, UUID(data["slot_id"]))
    services = list(
        await session.scalars(
            select(Service).where(Service.id.in_([UUID(value) for value in data["service_ids"]]))
        )
    )
    estimate = ""
    if data.get("estimated_min") is not None and data.get("estimated_max") is not None:
        estimate = f"\nПредварительная стоимость: {data['estimated_min']}–{data['estimated_max']} ₽"
    when = (
        format_studio_time(slot.starts_at, settings.STUDIO_TIMEZONE) if slot else "время уточняется"
    )
    text = (
        f"Проверьте заявку:\n\nИмя: {data['customer_name']}\nТелефон: {data['customer_phone']}\n"
        f"Автомобиль: {data['brand']} {data['model']}, {data['year']}\nКласс: {data['vehicle_class']}\n"
        f"Услуги: {', '.join(item.name for item in services)}\nФото: {len(data.get('photos', []))}\n"
        f"Дата и время: {when}\nАдрес: {settings.STUDIO_ADDRESS}{estimate}"
    )
    await state.set_state(BookingStates.final)
    if callback.message:
        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="Отправить заявку",
                            callback_data=BookingCallback(action="submit").pack(),
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="Изменить контакты",
                            callback_data=BookingCallback(action="final_contacts").pack(),
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="Изменить дату",
                            callback_data=BookingCallback(action="final_date").pack(),
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="Изменить услуги",
                            callback_data=BookingCallback(action="final_services").pack(),
                        )
                    ],
                    *navigation(cancel=True),
                ]
            ),
        )
    await callback.answer()


@router.callback_query(BookingStates.final, BookingCallback.filter(F.action == "final_contacts"))
async def final_contacts(callback: CallbackQuery, state: FSMContext, db_user: User) -> None:
    await state.set_state(BookingStates.name)
    if callback.message:
        await callback.message.edit_text(
            "Как к вам обращаться?",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=f"Использовать имя: {db_user.first_name}",
                            callback_data=BookingCallback(action="name_telegram").pack(),
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="Ввести другое имя",
                            callback_data=BookingCallback(action="name_manual").pack(),
                        )
                    ],
                    *navigation(back="dates", cancel=True),
                ]
            ),
        )
    await callback.answer()


@router.callback_query(BookingStates.final, BookingCallback.filter(F.action == "final_date"))
async def final_date(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, settings: Settings
) -> None:
    await render_dates(callback, state, session, settings, 0)
    await callback.answer()


@router.callback_query(BookingStates.final, BookingCallback.filter(F.action == "final_services"))
async def final_services(callback: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    await render_services(callback, state, session)
    await callback.answer()


@router.callback_query(BookingStates.final, BookingCallback.filter(F.action == "submit"))
async def submit(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
    settings: Settings,
) -> None:
    data = await state.get_data()
    draft = BookingDraft(
        brand=data["brand"],
        model=data["model"],
        year=data["year"],
        vehicle_class=data["vehicle_class"],
        service_ids=[UUID(x) for x in data["service_ids"]],
        slot_id=UUID(data["slot_id"]),
        customer_name=data["customer_name"],
        customer_phone=data["customer_phone"],
        photos=[
            PhotoDraft(
                file_id=photo["file_id"],
                unique_file_id=photo["unique_file_id"],
                mime_type=photo["mime"],
                size_bytes=photo["size"],
            )
            for photo in data.get("photos", [])
        ],
        estimated_min=data.get("estimated_min"),
        estimated_max=data.get("estimated_max"),
        idempotency_key=data.setdefault("idempotency_key", str(uuid4())),
    )
    try:
        booking = await BookingService(session).submit(db_user, draft)
    except (SlotUnavailableError, ValueError) as error:
        await callback.answer(str(error), show_alert=True)
        return
    await state.clear()
    if callback.message:
        await callback.message.edit_text(
            f"Заявка #{str(booking.id)[:8]} принята. Администратор подтвердит время.",
            reply_markup=main_menu(),
        )
    slot = await session.get(TimeSlot, booking.slot_id)
    services = list(await session.scalars(select(Service).where(Service.id.in_(draft.service_ids))))
    card = (
        f"Новая заявка #{str(booking.id)[:8]}\n"
        f"Клиент: {booking.customer_name} ({'@' + db_user.username if db_user.username else 'без username'})\n"
        f"Телефон: {booking.customer_phone}\n"
        f"Автомобиль: {data['brand']} {data['model']}, {data['year']}; {data['vehicle_class']}\n"
        f"Услуги: {', '.join(item.name for item in services)}\n"
        f"Дата и время: {format_studio_time(slot.starts_at, settings.STUDIO_TIMEZONE) if slot else 'не выбрано'}\n"
        f"Фото: {len(data.get('photos', []))}\nСоздано: {format_studio_time(booking.created_at, settings.STUDIO_TIMEZONE)}"
    )
    admin_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Подтвердить",
                    callback_data=AdminCallback(action="confirm", entity_id=str(booking.id)).pack(),
                ),
                InlineKeyboardButton(
                    text="Отклонить",
                    callback_data=AdminCallback(action="reject", entity_id=str(booking.id)).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="Предложить другое время",
                    callback_data=AdminCallback(action="propose", entity_id=str(booking.id)).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="История",
                    callback_data=AdminCallback(action="history", entity_id=str(booking.id)).pack(),
                )
            ],
        ]
    )
    for admin_id in settings.ADMIN_IDS:
        await callback.bot.send_message(admin_id, card, reply_markup=admin_keyboard)
        for photo_data in data.get("photos", []):
            await callback.bot.send_photo(admin_id, photo_data["file_id"])
    await callback.answer()


@router.callback_query(MenuCallback.filter(F.section == "my_booking"))
async def my_booking(
    callback: CallbackQuery, session: AsyncSession, db_user: User, settings: Settings
) -> None:
    item = await BookingRepository(session).active_for_user(db_user.id)
    if item and item.slot:
        services = ", ".join(service.name for service in item.services) or "—"
        estimate = "—"
        if item.estimated_min is not None and item.estimated_max is not None:
            estimate = f"{item.estimated_min:.0f}–{item.estimated_max:.0f} ₽"
        text = (
            f"Статус: {item.status.value}\nАвтомобиль: {item.vehicle.brand_name} {item.vehicle.model_name}, {item.vehicle.year}\n"
            f"Услуги: {services}\nДата и время: {format_studio_time(item.slot.starts_at, settings.STUDIO_TIMEZONE)}\n"
            f"Адрес: {settings.STUDIO_ADDRESS}\nТелефон: {settings.SUPPORT_PHONE}\n"
            f"Комментарий: {item.comment or '—'}\nПредварительная стоимость: {estimate}"
        )
        buttons = [
            [
                InlineKeyboardButton(
                    text="Перенести", callback_data=BookingCallback(action="reschedule").pack()
                ),
                InlineKeyboardButton(
                    text="Отменить", callback_data=BookingCallback(action="cancel_booking").pack()
                ),
            ],
            *navigation(),
        ]
    else:
        text = "Активной записи нет."
        buttons = [
            [
                InlineKeyboardButton(
                    text="Записаться", callback_data=MenuCallback(section="booking").pack()
                )
            ],
            *navigation(),
        ]
    if callback.message:
        await callback.message.edit_text(
            text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
        )
    await callback.answer()


async def render_appointment_dates(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
    settings: Settings,
) -> None:
    availability = AvailabilityService(session, settings.STUDIO_TIMEZONE)
    await availability.release_expired_holds()
    dates = await availability.dates_for_week(0, settings.BOOKING_HORIZON_DAYS, db_user.id)
    buttons = [
        [
            InlineKeyboardButton(
                text=item.strftime("%d.%m.%Y"),
                callback_data=BookingCallback(
                    action="appointment_date", value=item.isoformat()
                ).pack(),
            )
        ]
        for item in dates
    ]
    buttons.extend(navigation(cancel=True))
    await state.set_state(AppointmentStates.reschedule_date)
    if callback.message:
        await callback.message.edit_text(
            "Выберите новую дату. Перенос доступен не менее чем за установленный интервал до визита.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        )


@router.callback_query(BookingCallback.filter(F.action == "reschedule"))
async def begin_reschedule(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
    settings: Settings,
) -> None:
    booking = await BookingRepository(session).active_for_user(db_user.id)
    if (
        booking is None
        or booking.slot is None
        or booking.status not in (BookingStatus.PENDING, BookingStatus.CONFIRMED)
    ):
        await callback.answer("Эту запись нельзя перенести.", show_alert=True)
        return
    if booking.slot.starts_at <= utc_now() + timedelta(hours=settings.MIN_RESCHEDULE_HOURS):
        await callback.answer(
            "Перенос уже недоступен: время визита слишком близко.", show_alert=True
        )
        return
    await state.update_data(appointment_booking_id=str(booking.id))
    await render_appointment_dates(callback, state, session, db_user, settings)
    await callback.answer()


@router.callback_query(
    AppointmentStates.reschedule_date, BookingCallback.filter(F.action == "appointment_date")
)
async def appointment_date(
    callback: CallbackQuery,
    callback_data: BookingCallback,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
    settings: Settings,
) -> None:
    try:
        selected = date.fromisoformat(callback_data.value)
    except ValueError:
        await callback.answer("Дата устарела.", show_alert=True)
        return
    slots = await AvailabilityService(session, settings.STUDIO_TIMEZONE).slots_for_date(
        selected, db_user.id
    )
    cutoff = utc_now() + timedelta(hours=settings.MIN_RESCHEDULE_HOURS)
    slots = [slot for slot in slots if slot.starts_at > cutoff]
    buttons = [
        [
            InlineKeyboardButton(
                text=format_studio_time(slot.starts_at, settings.STUDIO_TIMEZONE)[-5:],
                callback_data=BookingCallback(action="appointment_slot", value=str(slot.id)).pack(),
            )
        ]
        for slot in slots
    ]
    buttons.extend(navigation(cancel=True))
    await state.set_state(AppointmentStates.reschedule_slot)
    if callback.message:
        await callback.message.edit_text(
            f"Свободное время на {selected.strftime('%d.%m.%Y')}:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        )
    await callback.answer()


@router.callback_query(
    AppointmentStates.reschedule_slot, BookingCallback.filter(F.action == "appointment_slot")
)
async def appointment_slot(
    callback: CallbackQuery,
    callback_data: BookingCallback,
    state: FSMContext,
    session: AsyncSession,
    settings: Settings,
) -> None:
    slot = await session.get(TimeSlot, UUID(callback_data.value))
    if slot is None or slot.status != SlotStatus.AVAILABLE:
        await callback.answer("Это время уже недоступно.", show_alert=True)
        return
    await state.update_data(appointment_slot_id=str(slot.id))
    await state.set_state(AppointmentStates.reschedule_confirm)
    if callback.message:
        await callback.message.edit_text(
            f"Перенести запись на {format_studio_time(slot.starts_at, settings.STUDIO_TIMEZONE)}?",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="Подтвердить перенос",
                            callback_data=BookingCallback(action="appointment_confirm").pack(),
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="Выбрать другое",
                            callback_data=BookingCallback(action="reschedule").pack(),
                        )
                    ],
                    *navigation(cancel=True),
                ]
            ),
        )
    await callback.answer()


@router.callback_query(
    AppointmentStates.reschedule_confirm, BookingCallback.filter(F.action == "appointment_confirm")
)
async def confirm_reschedule(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
    settings: Settings,
) -> None:
    data = await state.get_data()
    try:
        booking = await BookingService(session).reschedule_by_client(
            UUID(data["appointment_booking_id"]),
            db_user.id,
            UUID(data["appointment_slot_id"]),
            settings.REMINDER_HOURS_BEFORE,
            settings.MIN_RESCHEDULE_HOURS,
        )
    except (KeyError, LookupError, SlotUnavailableError, InvalidTransitionError) as error:
        await callback.answer(str(error) if str(error) else "Перенос не выполнен.", show_alert=True)
        return
    await state.clear()
    slot = await session.get(TimeSlot, booking.slot_id)
    if callback.message:
        await callback.message.edit_text(
            f"Запись перенесена на {format_studio_time(slot.starts_at, settings.STUDIO_TIMEZONE) if slot else 'новое время'}. Администратор уведомлён.",
            reply_markup=main_menu(),
        )
    for admin_id in settings.ADMIN_IDS:
        await callback.bot.send_message(admin_id, f"Клиент перенёс запись #{str(booking.id)[:8]}.")
    await callback.answer()


@router.callback_query(BookingCallback.filter(F.action == "cancel_booking"))
async def begin_cancel(
    callback: CallbackQuery, state: FSMContext, session: AsyncSession, db_user: User
) -> None:
    booking = await BookingRepository(session).active_for_user(db_user.id)
    if booking is None:
        await callback.answer("Активной записи нет.", show_alert=True)
        return
    await state.update_data(appointment_booking_id=str(booking.id))
    await state.set_state(AppointmentStates.cancel_confirm)
    if callback.message:
        await callback.message.edit_text(
            "Отмена освободит время записи. Продолжить?",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="Да, отменить",
                            callback_data=BookingCallback(action="cancel_confirm").pack(),
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="Оставить запись",
                            callback_data=MenuCallback(section="my_booking").pack(),
                        )
                    ],
                    *navigation(cancel=True),
                ]
            ),
        )
    await callback.answer()


@router.callback_query(
    AppointmentStates.cancel_confirm, BookingCallback.filter(F.action == "cancel_confirm")
)
async def cancel_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    reasons = [
        ("Изменились планы", "plans"),
        ("Выбрал другую студию", "other_studio"),
        ("Неудобное время", "time"),
        ("Услуга больше не нужна", "not_needed"),
        ("Другая причина", "other"),
    ]
    buttons = [
        [
            InlineKeyboardButton(
                text=text, callback_data=BookingCallback(action="cancel_reason", value=value).pack()
            )
        ]
        for text, value in reasons
    ]
    await state.set_state(AppointmentStates.cancel_reason)
    if callback.message:
        await callback.message.edit_text(
            "Выберите причину отмены:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons + navigation(cancel=True)),
        )
    await callback.answer()


async def complete_client_cancellation(
    callback: CallbackQuery | Message,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
    settings: Settings,
    reason: str,
) -> None:
    data = await state.get_data()
    booking = await BookingService(session).change_status(
        UUID(data["appointment_booking_id"]), BookingStatus.CANCELLED_BY_CLIENT, db_user.id, reason
    )
    await state.clear()
    text = "Запись отменена. Время освобождено, администратор уведомлён."
    if isinstance(callback, CallbackQuery):
        if callback.message:
            await callback.message.edit_text(text, reply_markup=main_menu())
        for admin_id in settings.ADMIN_IDS:
            await callback.bot.send_message(
                admin_id, f"Клиент отменил запись #{str(booking.id)[:8]}. Причина: {reason}"
            )
    else:
        await callback.answer(text, reply_markup=main_menu())
        for admin_id in settings.ADMIN_IDS:
            await callback.bot.send_message(
                admin_id, f"Клиент отменил запись #{str(booking.id)[:8]}. Причина: {reason}"
            )


@router.callback_query(
    AppointmentStates.cancel_reason, BookingCallback.filter(F.action == "cancel_reason")
)
async def cancel_reason(
    callback: CallbackQuery,
    callback_data: BookingCallback,
    state: FSMContext,
    session: AsyncSession,
    db_user: User,
    settings: Settings,
) -> None:
    if callback_data.value == "other":
        if callback.message:
            await callback.message.edit_text("Напишите причину отмены:")
        await callback.answer()
        return
    labels = {
        "plans": "изменились планы",
        "other_studio": "выбрана другая студия",
        "time": "неудобное время",
        "not_needed": "услуга больше не нужна",
    }
    await complete_client_cancellation(
        callback, state, session, db_user, settings, labels[callback_data.value]
    )
    await callback.answer()


@router.message(AppointmentStates.cancel_reason)
async def cancel_other_reason(
    message: Message, state: FSMContext, session: AsyncSession, db_user: User, settings: Settings
) -> None:
    reason = " ".join((message.text or "").split())
    if not reason or len(reason) > 500:
        await message.answer("Укажите причину до 500 символов.")
        return
    await complete_client_cancellation(message, state, session, db_user, settings, reason)


@router.callback_query(BookingCallback.filter(F.action == "offer_accept"))
async def accept_offered_time(
    callback: CallbackQuery,
    callback_data: BookingCallback,
    session: AsyncSession,
    db_user: User,
    settings: Settings,
) -> None:
    try:
        booking = await BookingService(session).accept_reschedule(
            UUID(callback_data.value), db_user.id
        )
    except (LookupError, SlotUnavailableError, InvalidTransitionError) as error:
        await callback.answer(str(error), show_alert=True)
        return
    await BookingService(session).refresh_reminders(booking.id, settings.REMINDER_HOURS_BEFORE)
    slot = await session.get(TimeSlot, booking.slot_id)
    if callback.message:
        await callback.message.edit_text(
            f"Новое время принято: {format_studio_time(slot.starts_at, settings.STUDIO_TIMEZONE) if slot else 'уточняется'}. Администратор подтвердит запись.",
            reply_markup=main_menu(),
        )
    for admin_id in settings.ADMIN_IDS:
        await callback.bot.send_message(
            admin_id, f"Клиент принял перенос записи #{str(booking.id)[:8]}."
        )
    await callback.answer()


@router.callback_query(BookingCallback.filter(F.action == "offer_decline"))
async def decline_offered_time(
    callback: CallbackQuery, callback_data: BookingCallback, session: AsyncSession, db_user: User
) -> None:
    try:
        await BookingService(session).decline_reschedule(UUID(callback_data.value), db_user.id)
    except (LookupError, InvalidTransitionError) as error:
        await callback.answer(str(error), show_alert=True)
        return
    if callback.message:
        await callback.message.edit_text(
            "Предложенное время отклонено. Администратор свяжется с вами, чтобы подобрать другой вариант.",
            reply_markup=main_menu(),
        )
    await callback.answer()
