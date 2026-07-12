from aiogram.fsm.state import State, StatesGroup


class BookingStates(StatesGroup):
    brand = State()
    model = State()
    year = State()
    vehicle_class = State()
    services = State()
    summary = State()
    photos = State()
    date = State()
    slot = State()
    name = State()
    phone = State()
    consent = State()
    final = State()


class ManagerStates(StatesGroup):
    question = State()
    photos = State()
    phone = State()
    preview = State()


class CalculatorStates(StatesGroup):
    service = State()
    vehicle_class = State()
    condition = State()
    options = State()


class AdminStates(StatesGroup):
    rejection_reason = State()
    reply = State()
    content = State()
    reschedule_slot = State()


class AppointmentStates(StatesGroup):
    reschedule_date = State()
    reschedule_slot = State()
    reschedule_confirm = State()
    cancel_confirm = State()
    cancel_reason = State()


class FAQStates(StatesGroup):
    search = State()
