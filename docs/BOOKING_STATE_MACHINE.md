# State machine записи

```mermaid
stateDiagram-v2
    [*] --> draft
    draft --> pending: заявка отправлена
    draft --> cancelled_by_client: отмена черновика
    pending --> confirmed: подтверждение администратора
    pending --> reschedule_requested: запрос переноса
    pending --> cancelled_by_client
    pending --> cancelled_by_admin
    confirmed --> reschedule_requested
    confirmed --> cancelled_by_client
    confirmed --> cancelled_by_admin
    confirmed --> completed: визит завершён
    confirmed --> no_show: клиент не пришёл
    reschedule_requested --> pending: выбран новый слот
    reschedule_requested --> confirmed: администратор подтвердил предложение
    reschedule_requested --> cancelled_by_client
    reschedule_requested --> cancelled_by_admin
```

| Статус | Значение | Разрешённые переходы |
| --- | --- | --- |
| `draft` | Неполная запись, ещё не заявка | `pending`, `cancelled_by_client` |
| `pending` | Отправлена, ожидает решения | `confirmed`, `reschedule_requested`, `cancelled_by_client`, `cancelled_by_admin` |
| `confirmed` | Время закреплено | `reschedule_requested`, `cancelled_by_client`, `cancelled_by_admin`, `completed`, `no_show` |
| `reschedule_requested` | Идёт подбор нового времени | `pending`, `confirmed`, `cancelled_by_client`, `cancelled_by_admin` |
| `cancelled_by_client` | Отменил клиент | финальный |
| `cancelled_by_admin` | Отменила студия | финальный |
| `completed` | Услуга оказана | финальный |
| `no_show` | Клиент не пришёл | финальный |

Инварианты: pending/confirmed/reschedule_requested имеют актуальный slot; отмена освобождает слот и отменяет неотправленные уведомления; confirmed создаёт reminders; перенос в одной транзакции освобождает старый слот, бронирует новый и заменяет reminders. Повторная команда, ведущая к текущему состоянию, возвращает существующий результат без побочных действий. Любой иной переход — domain error и аудит отказа.

