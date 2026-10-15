# interfaces/gui/gui_window/pages/draft_pages.py

"""
Экраны приложения на новых черновиках (``app.utils.drafts`` + ``app.utils.drafts_qt``).

Новые классы РЯДОМ со старыми (решение владельца 2026-10-16): старые
``PatientListPage`` / ``AppointmentPhotoFrame`` не тронуты, главное окно переключено на
эти (старое создание — в комментариях). Все экраны работают с ОДНИМ хранилищем
черновиков главного окна — изменения на разных экранах сохраняются вместе.

* ``ServiceRowSource`` — строки страницы через сервис приложения (фильтр по родителю).
* ``columns_from_config`` — колонки из ``field_configs`` (заголовок, скрытые, порядок,
  только чтение, даты).
* ``PatientsDraftPage`` — пациенты; «Приёмы» открывает фрейм приёмов пациента.
* ``AppointmentsPhotosDraftFrame`` — приёмы пациента + фото выбранного приёма.
* ``save_from_page`` — «Сохранить»: вопрос «всё / текущее», затем сохранение главным окном.

Пример:
    >>> page = PatientsDraftPage(store, save_handler=lambda p: save_from_page(window, p))
"""

import datetime
from types import SimpleNamespace
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QSplitter, QVBoxLayout, QWidget

from app.utils.drafts import MISSING, DraftStore, SaveScope
from app.utils.drafts_qt import Column, DraftTablePage
from interfaces.gui.gui_window.pages.base_page import BasePage


# ---------------------------------------------------------------------------
# Источник строк и колонки
# ---------------------------------------------------------------------------

class ServiceRowSource:
    """
    ``RowSource`` через сервис приложения: ``service.get_page(offset, limit, filters)``.

    Сервис берётся функцией при каждой загрузке (после смены БД — актуальный).

    Пример:
        >>> source = ServiceRowSource(get_photo_service, parent_field='appointment_id')
        >>> source.load(0, 50, 12)
        ([{'id': 7, 'appointment_id': 12, ...}], 1)
    """

    def __init__(self, service_provider: Callable[[], Any], parent_field: Optional[str] = None) -> None:
        """
        Args:
            service_provider: Функция, возвращающая сервис.
            parent_field: Поле внешнего ключа для фильтра по родителю.

        Пример:
            >>> ServiceRowSource(get_patient_service)
        """
        self.service_provider = service_provider
        self.parent_field = parent_field

    def load(self, offset: int, limit: int, parent_id: Any) -> Tuple[List[Dict[str, Any]], int]:
        """
        Страница строк (словари ``model_dump`` DTO).

        Args:
            offset: Пропустить строк.
            limit: Вернуть строк.
            parent_id: Родитель или ``MISSING`` (без фильтра).

        Returns:
            ``(строки, всего)``.

        Пример:
            >>> source.load(0, 2, MISSING)
            ([{...}, {...}], 10)
        """
        filters = None
        if self.parent_field and parent_id is not MISSING:
            filters = [{'column': self.parent_field, 'operator': 'eq', 'value': parent_id}]
        items, total = self.service_provider().get_page(offset, limit, filters=filters)
        return [item.model_dump() for item in items], total


def _date_text(value: Any) -> str:
    """
    Дата → ``ДД.ММ.ГГГГ``.

    Args:
        value: ``date``/``datetime``/строка/``None``.

    Returns:
        Текст.

    Пример:
        >>> _date_text(datetime.date(2026, 10, 16))
        '16.10.2026'
    """
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.strftime('%d.%m.%Y')
    return '' if value is None else str(value)


def _date_from_edit(value: Any) -> Any:
    """
    Значение редактора даты → ``datetime.date`` (Qt отдаёт ``QDate``).

    Args:
        value: ``QDate``, ``date`` или строка ``ДД.ММ.ГГГГ``/``ГГГГ-ММ-ДД``.

    Returns:
        Дата (или ``None`` для пустого).

    Raises:
        ValueError: Строка не разбирается как дата.

    Пример:
        >>> _date_from_edit(QDate(2026, 10, 16))
        datetime.date(2026, 10, 16)
    """
    if value in (None, ''):
        return None
    if isinstance(value, QDate):
        return value.toPython()
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    text = str(value).strip()
    for fmt in ('%d.%m.%Y', '%Y-%m-%d'):
        try:
            return datetime.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"не дата: {text!r}")


def columns_from_config(
    config: Mapping[str, Mapping[str, Any]],
    exclude: Iterable[str] = (),
) -> List[Column]:
    """
    Колонки таблицы из ``field_configs`` приложения.

    Правила: ``hidden`` и ``widget_type='photo_uploader'`` (составной компонент) — не
    показываются; виртуальные поля без ``is_note`` и с ``sql_compute`` — только чтение
    (вычисляются в БД); ``widget_type='date'`` — формат ``ДД.ММ.ГГГГ`` и разбор даты;
    ``sql_compute.formatter`` — текст ячейки; ``width.fixed`` — ширина; порядок — ``order``
    (без ``order`` — в конце, как в конфиге).

    Args:
        config: ``PATIENT_CONFIG`` и т. п.
        exclude: Поля, которые не показывать.

    Returns:
        Колонки.

    Пример:
        >>> [c.field for c in columns_from_config(PHOTO_CONFIG)]
        ['file_path', 'description']
    """
    excluded = set(exclude)
    items = []
    for position, (field, cfg) in enumerate(config.items()):
        if field in excluded or cfg.get('hidden') or cfg.get('widget_type') == 'photo_uploader':
            continue
        computed = bool(cfg.get('sql_compute')) or (cfg.get('virtual') and not cfg.get('is_note'))
        editable = bool(cfg.get('editable', True)) and not computed
        to_text = from_edit = None
        if cfg.get('widget_type') == 'date':
            to_text, from_edit = _date_text, _date_from_edit
        formatter = (cfg.get('sql_compute') or {}).get('formatter')
        if callable(formatter):
            to_text = formatter
        width = cfg.get('width', {}).get('fixed') if isinstance(cfg.get('width'), dict) else None
        column = Column(field, cfg.get('title', field), editable=editable, to_text=to_text,
                        from_edit=from_edit, width=width)
        items.append((cfg.get('order', 10_000 + position), position, column))
    return [column for _, _, column in sorted(items, key=lambda x: (x[0], x[1]))]


# ---------------------------------------------------------------------------
# Сохранение
# ---------------------------------------------------------------------------

def save_from_page(window: Any, page: DraftTablePage, scope: SaveScope = SaveScope.BRANCH,
                   frame_nodes: Optional[Callable[[], Sequence]] = None) -> bool:
    """
    «Сохранить» на экране: вопрос «всё / текущее» (треб. 5), затем
    ``window.save_drafts(targets, scope)`` (вопросы про новых родителей и удаление).

    «Текущее» — выделенные строки страницы (или вся выборка фрейма ``frame_nodes``, если
    ничего не выделено) с направлениями ``scope`` (по умолчанию строка и вложенные).

    Args:
        window: Главное окно (``save_drafts``).
        page: Страница, где нажали «Сохранить».
        scope: Направления для «текущего».
        frame_nodes: Цель «выборка фрейма» при пустом выделении.

    Returns:
        ``True`` — сохранено.

    Пример:
        >>> save_from_page(window, appointments_page)
        True
    """
    from interfaces.gui.gui_window.drafts_qt import ask_save_target
    targets = page.selected_nodes() or (list(frame_nodes()) if frame_nodes else [])
    choice = ask_save_target(page, has_current=bool(targets))
    if choice is None:
        return False
    if choice == 'all':
        return window.save_drafts(None, scope)
    return window.save_drafts(targets, scope)


# ---------------------------------------------------------------------------
# Экраны
# ---------------------------------------------------------------------------

class PatientsDraftPage(BasePage):
    """
    Пациенты (таблица с черновиками).

    Сигналы совместимы со старой ``PatientListPage`` (подключения главного окна не
    меняются): ``action_requested(obj с .id)`` — «Приёмы» выбранного пациента; остальные
    (``add_requested``, ``edit_requested``, ``delete_requested``) объявлены для
    совместимости — добавление/удаление теперь в самой таблице (черновиками).

    Пример:
        >>> page = PatientsDraftPage(store, save_handler=handler)
        >>> page.action_requested.connect(open_appointments)
    """

    add_requested = Signal()
    edit_requested = Signal(object)
    delete_requested = Signal(object)
    action_requested = Signal(object)

    def __init__(self, store: DraftStore, save_handler: Optional[Callable[[DraftTablePage], Any]] = None,
                 parent: Optional[QWidget] = None) -> None:
        """
        Args:
            store: Хранилище черновиков главного окна.
            save_handler: Обработчик «Сохранить».
            parent: Родитель.

        Пример:
            >>> PatientsDraftPage(store)
        """
        super().__init__(parent)
        from app.dependencies import get_patient_service
        from app.dto.field_configs import PATIENT_CONFIG
        self.page_title = "Пациенты"
        self.table = DraftTablePage(
            store, 'patient', columns_from_config(PATIENT_CONFIG),
            ServiceRowSource(get_patient_service), save_handler=save_handler, title="Пациенты",
        )
        self.appointments_btn = QPushButton("Приёмы", self)
        self.appointments_btn.clicked.connect(self._open_appointments)
        self.table.current_changed.connect(lambda _id: self.appointments_btn.setEnabled(_id is not None))
        self.appointments_btn.setEnabled(False)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.table)
        buttons = QHBoxLayout()
        buttons.addWidget(self.appointments_btn)
        buttons.addStretch(1)
        layout.addLayout(buttons)

    def _open_appointments(self) -> None:
        """
        «Приёмы» → ``action_requested`` с текущим пациентом (в т.ч. новым, ещё не
        сохранённым: его приёмы тоже будут черновиками).

        Returns:
            None

        Пример:
            >>> page._open_appointments()
        """
        patient_id = self.table.current_id()
        if patient_id is not None:
            self.action_requested.emit(SimpleNamespace(id=patient_id))

    def on_enter(self, extra_data: Optional[Mapping[str, Any]] = None) -> None:
        """
        Вход на экран: перечитать страницу (черновики сохраняются).

        Args:
            extra_data: Не используется.

        Returns:
            None

        Пример:
            >>> page.on_enter()
        """
        self.table.reload()

    def _load_data(self) -> None:
        """
        Совместимость со старой страницей: перечитать.

        Returns:
            None

        Пример:
            >>> page._load_data()
        """
        self.table.reload()

    def refresh_data(self) -> None:
        """
        Совместимость со старой страницей: перечитать.

        Returns:
            None

        Пример:
            >>> page.refresh_data()
        """
        self.table.reload()


class AppointmentsPhotosDraftFrame(BasePage):
    """
    Приёмы пациента (сверху) и фото выбранного приёма (снизу) на одном хранилище.

    ``on_enter({'patient_id': id})`` — приёмы этого пациента; без пациента — все приёмы.
    Переходы между строками и экранами черновики не теряют.

    Пример:
        >>> frame = AppointmentsPhotosDraftFrame(store, save_handler=handler)
        >>> frame.on_enter({'patient_id': 1})
    """

    def __init__(self, store: DraftStore,
                 save_handler: Optional[Callable[[DraftTablePage], Any]] = None,
                 parent: Optional[QWidget] = None) -> None:
        """
        Args:
            store: Хранилище черновиков главного окна.
            save_handler: Обработчик «Сохранить» (получает страницу).
            parent: Родитель.

        Пример:
            >>> AppointmentsPhotosDraftFrame(store)
        """
        super().__init__(parent)
        from app.dependencies import get_appointment_service, get_photo_service
        from app.dto.field_configs import APPOINTMENT_CONFIG, PHOTO_CONFIG
        self.page_title = "Приёмы и фото"
        self._patient_id: Any = MISSING
        self.appointments = DraftTablePage(
            store, 'appointment', columns_from_config(APPOINTMENT_CONFIG, exclude=('patient_id',)),
            ServiceRowSource(get_appointment_service, 'patient_id'), save_handler=save_handler,
            title="Приёмы", default_row=lambda: {'date': datetime.date.today()},
        )
        self.photos = DraftTablePage(
            store, 'photo', columns_from_config(PHOTO_CONFIG),
            ServiceRowSource(get_photo_service, 'appointment_id'), save_handler=save_handler,
            title="Фото", requires_parent=True,
        )
        self.appointments.current_changed.connect(self.photos.set_parent)
        splitter = QSplitter(Qt.Vertical, self)
        splitter.addWidget(self.appointments)
        splitter.addWidget(self.photos)
        splitter.setSizes([300, 400])
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)

    @property
    def patient_id(self) -> Any:
        """
        Пациент экрана или ``MISSING`` (все приёмы).

        Returns:
            Id.

        Пример:
            >>> frame.patient_id
            1
        """
        return self._patient_id

    def frame_nodes(self) -> list:
        """
        Цель «выборка фрейма»: все приёмы на странице (несколько веток).

        Returns:
            Ключи узлов.

        Пример:
            >>> frame.frame_nodes()
            [('appointment', 12), ('appointment', 13)]
        """
        return self.appointments.page_nodes()

    def on_enter(self, extra_data: Optional[Mapping[str, Any]] = None) -> None:
        """
        Вход: приёмы пациента из ``extra_data['patient_id']`` (или все), фото — после
        выбора приёма.

        Args:
            extra_data: ``{'patient_id': id}`` или ``None``.

        Returns:
            None

        Пример:
            >>> frame.on_enter({'patient_id': 1})
        """
        patient_id = (extra_data or {}).get('patient_id', MISSING)
        self._patient_id = patient_id
        self.appointments.set_parent(patient_id)
        if self.appointments.current_id() is None:
            self.photos.set_parent(None)
