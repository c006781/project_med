# interfaces/gui/gui_window/pages/dataset_pilot_page.py

"""
Пилотный экран на наборах данных (в духе RAD Studio): пациенты → приёмы → фото.

Стоит РЯДОМ со старыми экранами (как в своё время экраны черновиков) и ничего в них не
меняет. Собран из готовых частей, своей логики работы с данными у экрана нет:

* наборы и связи — ``app.dataset_app.create_clinic_datasets`` (сменили пациента —
  приёмы перечитались; сменили приём — фото);
* таблицы — ``DataSetTableModel`` + ``bind_table_view`` (аналог ``TDBGrid``);
* формы — ``bind(виджет, источник, поле)`` (``TDBEdit``, ``TDBMemo``, ``TDBImage``);
* кнопки — ``DataNavigator`` (``TDBNavigator``) + свои: отмена/повтор черновиков;
* запись — через общие черновики окна (правки копятся, «Сохранить» — разом, с теми же
  вопросами, что у экранов черновиков); без черновиков — сразу в БД;
* загрузка — порциями при прокрутке или всё сразу, размер порции — на панели.

Пример:
    >>> page = DataSetPilotPage(drafts=window.drafts, save_handler=window.save_drafts)
    >>> page.clinic.patients.locate(5)
    True
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (
    QComboBox, QDateEdit, QFileDialog, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPlainTextEdit, QPushButton, QSpinBox, QSplitter, QTableView, QToolButton, QVBoxLayout, QWidget,
)

from app.dataset_app import create_clinic_datasets
from app.utils.dataset import Condition, DataSource, FetchMode, Op
from app.utils.dataset import Action, ActionSet
from app.utils.dataset_qt import ActionsMenu, DataNavigator, DataSetTableModel, bind_table_view, build_form
from interfaces.gui.gui_window.pages.base_page import BasePage

# # Колонки таблиц и поля форм: (поле, виджет)
# COLUMNS: Dict[str, Tuple[str, ...]] = {
#     'patients': ('last_name', 'first_name', 'middle_name', 'birth_date', 'phone'),
#     'appointments': ('date', 'reason_text', 'date_next', 'has_photos'),
#     'photos': ('file_path', 'description'),
# }
# FORMS: Dict[str, Tuple[Tuple[str, str], ...]] = {
#     'patients': (('last_name', 'line'), ('first_name', 'line'), ('middle_name', 'line'),
#                  ('birth_date', 'date'), ('phone', 'line'), ('description_text', 'text'),
#                  ('comment_text', 'text')),
#     'appointments': (('date', 'date'), ('date_next', 'date'), ('reason_text', 'text'),
#                      ('procedure_text', 'text'), ('recommendations_text', 'text'),
#                      ('note_text', 'text'), ('cost_procedure_text', 'text')),
#     'photos': (('image', 'image'), ('description', 'text')),
# }
# TITLES = {'patients': 'Пациенты', 'appointments': 'Приёмы', 'photos': 'Фото'}
# ↑ до 2026-10-18: колонки, формы и заголовки экрана — словарями здесь, ровно на три
#   таблицы. Теперь — из описаний таблиц (app/tables: columns, form, title), форма —
#   build_form по описанию полей; экран показывает цепочку таблиц реестра.


def _make_widget(kind: str) -> QWidget:
    """
    (не используется с 2026-10-18: форма — ``build_form`` по описанию полей; оставлена по
    правилу проекта)

    Виджет поля формы по виду.

    Args:
        kind: ``'line'``, ``'date'``, ``'text'``, ``'image'``.

    Returns:
        Виджет.

    Пример:
        >>> isinstance(_make_widget('date'), QDateEdit)
        True
    """
    if kind == 'date':
        widget = QDateEdit()
        widget.setCalendarPopup(True)
        widget.setMinimumDate(QDate(1900, 1, 1))       # минимальная — «пусто» (bind)
        widget.setDisplayFormat('dd.MM.yyyy')
        return widget
    if kind == 'text':
        widget = QPlainTextEdit()
        widget.setMaximumHeight(60)
        return widget
    if kind == 'image':
        widget = QLabel()
        widget.setMinimumSize(160, 120)
        widget.setAlignment(Qt.AlignCenter)
        widget.setFrameShape(QLabel.StyledPanel)
        return widget
    return QLineEdit()


class DataSetPilotPage(BasePage):
    """
    Экран «пациенты → приёмы → фото» на наборах данных.

    Attributes:
        clinic: Наборы клиники (``ClinicDataSets``).
        models: Модели таблиц по именам наборов.
        navigators: Навигаторы по именам наборов.
        bindings: Привязки виджетов форм.

    Пример:
        >>> page = DataSetPilotPage()
        >>> page.models['patients'].columns[:2]
        ['last_name', 'first_name']
    """

    def __init__(self, drafts: Any = None, save_handler: Optional[Callable[..., bool]] = None,
                 parent: Optional[QWidget] = None, *,
                 services: Optional[Mapping[str, Callable[[], Any]]] = None,
                 fetch_size: int = 50, ask_delete: Optional[Callable[[], bool]] = None) -> None:
        """
        Args:
            drafts: Черновики окна (``AppDrafts``); ``None`` — запись сразу в БД.
            save_handler: Сохранение черновиков с вопросами (``MainWindow.save_drafts``:
                ``(targets, scope) -> bool``); ``None`` — ``clinic.save()`` без вопросов.
            parent: Родитель Qt.
            services: Поставщики сервисов (тесты; по умолчанию — ``app.dependencies``).
            fetch_size: Размер порции загрузки.
            ask_delete: Вопрос перед удалением (по умолчанию — окно навигатора).

        Пример:
            >>> DataSetPilotPage(drafts=None).clinic.drafts is None
            True
        """
        super().__init__(parent)
        self.drafts = drafts
        self._save_handler = save_handler
        # наборы, связи, свои столбцы (отметки, итоги) — по описаниям таблиц (app.tables)
        self.clinic = create_clinic_datasets(drafts=drafts, services=services, fetch_size=fetch_size)
        self.models: Dict[str, DataSetTableModel] = {}
        self.navigators: Dict[str, DataNavigator] = {}
        self.tables: Dict[str, QTableView] = {}
        self.forms: Dict[str, Any] = {}
        self.actions: Dict[str, ActionSet] = {}
        self.action_menus: Dict[str, ActionsMenu] = {}
        self.bindings = []
        self._opened = False
        self._ask_delete = ask_delete
        self._build_ui(fetch_size)

    # ------------------------------------------------------------------ интерфейс

    def _build_ui(self, fetch_size: int) -> None:
        """
        Панель, три колонки (таблица + навигатор + форма), строка состояния.

        Args:
            fetch_size: Начальный размер порции.

        Returns:
            None

        Пример:
            >>> page._build_ui(50)
        """
        layout = QVBoxLayout(self)
        self.status = QLabel('')             # раньше колонок: ошибки при построении — сюда
        self.status.setWordWrap(True)
        layout.addLayout(self._build_toolbar(fetch_size))
        splitter = QSplitter(Qt.Horizontal)
        # for name in ('patients', 'appointments', 'photos'):
        # ↑ до 2026-10-18: три таблицы вручную; теперь — цепочка таблиц из описаний
        for name in self.clinic.registry.chain():
            splitter.addWidget(self._build_column(name))
        layout.addWidget(splitter, 1)
        layout.addWidget(self.status)

    def _build_toolbar(self, fetch_size: int) -> QHBoxLayout:
        """
        Панель: режим записи, поиск, загрузка, сохранение.

        Args:
            fetch_size: Начальный размер порции.

        Returns:
            Раскладка панели.

        Пример:
            >>> page._build_toolbar(50)
        """
        bar = QHBoxLayout()
        mode = ('Правки копятся в черновиках — «Сохранить» запишет их разом'
                if self.drafts is not None else 'Правки сразу записываются в базу')
        self.mode_label = QLabel(mode)
        bar.addWidget(self.mode_label)
        bar.addStretch(1)
        self.search = QLineEdit()
        self.search.setPlaceholderText('Поиск по фамилии…')
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._on_search)
        bar.addWidget(self.search)
        self.fetch_mode = QComboBox()
        self.fetch_mode.addItem('Порциями', FetchMode.ON_DEMAND)
        self.fetch_mode.addItem('Всё сразу', FetchMode.ALL)
        self.fetch_mode.currentIndexChanged.connect(self._on_fetch_settings)
        bar.addWidget(self.fetch_mode)
        self.fetch_size = QSpinBox()
        self.fetch_size.setRange(1, 10_000)
        self.fetch_size.setValue(fetch_size)
        self.fetch_size.setPrefix('по ')
        self.fetch_size.editingFinished.connect(self._on_fetch_settings)
        bar.addWidget(self.fetch_size)
        if self.drafts is not None:
            self.save_current_btn = QPushButton('Сохранить пациента')
            self.save_current_btn.setToolTip('Сохранить изменения текущего пациента (вся ветка)')
            self.save_current_btn.clicked.connect(lambda: self.save(current=True))
            bar.addWidget(self.save_current_btn)
            self.save_all_btn = QPushButton('Сохранить всё')
            self.save_all_btn.clicked.connect(lambda: self.save(current=False))
            bar.addWidget(self.save_all_btn)
        return bar

    def _build_column(self, name: str) -> QGroupBox:
        """
        Колонка набора: навигатор, таблица, форма.

        Args:
            name: Имя набора.

        Returns:
            Рамка колонки.

        Пример:
            >>> page._build_column('photos')
        """
        source: DataSource = self.clinic.sources[name]
        spec = self.clinic.registry.get(name)
        box = QGroupBox(spec.title)
        column = QVBoxLayout(box)
        navigator = DataNavigator(source, confirm_delete=self._ask_delete, show_errors=False)
        navigator.error_occurred.connect(self.show_error)
        if self.drafts is not None:
            store = self.drafts.store
            # can_undo/can_redo — свойства хранилища: условие — функция, читающая их
            navigator.add_action('undo', '↶', 'Отменить последнее изменение черновиков',
                                 store.undo, enabled=lambda: store.can_undo)
            navigator.add_action('redo', '↷', 'Повторить изменение черновиков',
                                 store.redo, enabled=lambda: store.can_redo)
            writer = self.clinic.writers[name]
            dataset_of = self.clinic.sources[name]
            navigator.add_action(
                'undelete', '⎌', 'Вернуть строку, помеченную на удаление',
                lambda w=writer, s=dataset_of: w.undelete(s.dataset),
                enabled=lambda s=dataset_of: s.dataset.active and s.dataset.row_status() == 'deleted')
        if name == 'photos':
            navigator.add_action('add_file', '🖼', 'Добавить фото из файла…', self.add_photo_file,
                                 enabled=lambda: self.clinic.photos.can_modify)
        # массовые действия над отмеченными («чеки»): меню «Отмеченные ▾» по набору действий
        actions = ActionSet(batch=self.drafts.store.batch if self.drafts is not None else None)
        if self.drafts is not None:
            actions.add(Action('save_marked', 'Сохранить отмеченные',
                               lambda ds, keys, params, e=spec.entity: self._save_targets(
                                   [(e, k) for k in keys]),
                               group='save'))
        menu = ActionsMenu(source, actions, self, confirm=self._ask_confirm)
        menu.error_occurred.connect(self.show_error)
        marked_button = QToolButton()
        marked_button.setText('Отмеченные')
        marked_button.setMenu(menu)
        marked_button.setPopupMode(QToolButton.InstantPopup)
        marked_button.setVisible('mark' in source.dataset.fields)
        top = QHBoxLayout()
        top.addWidget(navigator, 1)
        top.addWidget(marked_button)
        column.addLayout(top)
        self.actions[name], self.action_menus[name] = actions, menu
        self.navigators[name] = navigator
        model = DataSetTableModel(source, columns=list(spec.columns) or None, parent=self)
        model.error_occurred.connect(self.show_error)
        table = QTableView()
        table.setSelectionBehavior(QTableView.SelectRows)
        table.setSelectionMode(QTableView.SingleSelection)
        table.horizontalHeader().setStretchLastSection(True)
        bind_table_view(table, model)
        # щелчок по заголовку; что считает программа — когда загружено всё. Указатель
        # сортировки — снят ДО включения: иначе Qt сразу сортирует по столбцу 0 и подменяет
        # сортировку из описания таблицы
        table.horizontalHeader().setSortIndicator(-1, Qt.AscendingOrder)
        table.setSortingEnabled(True)
        column.addWidget(table, 1)
        self.models[name], self.tables[name] = model, table
        # form = QFormLayout()
        # dataset = self.clinic.sources[name].dataset
        # for field, kind in FORMS[name]:
        #     widget = _make_widget(kind)
        #     definition = dataset.fields.get(field)
        #     label = definition.label if definition is not None else field
        #     self.bindings.append(bind(widget, source, field, image=kind == 'image',
        #                               on_error=self.show_error))
        #     form.addRow(label, widget)
        # column.addLayout(form)
        # ↑ до 2026-10-18: виджеты подбирались здесь вручную; теперь — форма по описанию полей
        form = build_form(source, list(spec.form) or None, on_error=self.show_error)
        self.forms[name] = form
        self.bindings.extend(form.bindings)
        column.addLayout(form.layout)
        return box

    # ------------------------------------------------------------------ данные

    def open_data(self) -> None:
        """
        Открывает наборы (первое появление экрана; повторно — перечитывает).

        Returns:
            None

        Пример:
            >>> page.open_data()
        """
        try:
            if not self._opened:
                self.clinic.open()
                self._opened = True
            elif self.clinic.patients.state.value == 'browse':
                self.clinic.patients.refresh()
            self.show_status('')
        except Exception as exc:
            self.show_error(f"Данные не загружены: {exc}")

    def showEvent(self, event: QShowEvent) -> None:
        """
        Экран показан — данные открываются (не при создании окна: старт программы не ждёт БД).

        Args:
            event: Событие Qt.

        Returns:
            None

        Пример:
            >>> page.show()
        """
        super().showEvent(event)
        self.open_data()

    def _on_search(self, text: str) -> None:
        """
        Поиск по фамилии (без учёта регистра, подстрока).

        Args:
            text: Текст поиска.

        Returns:
            None

        Пример:
            >>> page._on_search('иван')
        """
        conditions = (Condition('last_name', Op.CONTAINS, text.strip()),) if text.strip() else ()
        try:
            self.clinic.patients.set_filter(*conditions)
        except Exception as exc:
            self.show_error(str(exc))

    def _on_fetch_settings(self, *_: Any) -> None:
        """
        Режим и размер порции → всем наборам; открытые — перечитываются.

        Returns:
            None

        Пример:
            >>> page.fetch_mode.setCurrentIndex(1)     # всё сразу
        """
        mode = self.fetch_mode.currentData()
        size = self.fetch_size.value()
        try:
            for dataset in self.clinic.datasets:
                dataset.fetch_mode, dataset.fetch_size = FetchMode(mode), size
            if self._opened:
                self.clinic.patients.refresh()
        except Exception as exc:
            self.show_error(str(exc))

    def add_photo_file(self, path: Optional[str] = None) -> bool:
        """
        Новое фото текущего приёма из файла.

        Args:
            path: Путь (``None`` — спросить окном выбора файла).

        Returns:
            ``True`` — фото добавлено (в черновики или в БД).

        Пример:
            >>> page.add_photo_file('C:/scan/1.jpg')
            True
        """
        if path is None:
            path, _ = QFileDialog.getOpenFileName(self, 'Фото к приёму', '',
                                                  'Изображения (*.png *.jpg *.jpeg *.bmp)')
        if not path:
            return False
        photos = self.clinic.photos
        try:
            photos.append({'file_path': path})
            photos.post()
        except Exception as exc:
            if photos.state.editing:
                photos.cancel()
            self.show_error(f"Фото не добавлено: {exc}")
            return False
        return True

    def finish_pending_edits(self) -> Optional[str]:
        """
        Завершает незавершённые правки всех наборов (F7: перед закрытием окна — иначе
        правка, ещё не попавшая в черновики/БД, пропала бы молча).

        Returns:
            ``None`` — всё завершено; иначе — текст ошибки (правка не прошла проверку).

        Пример:
            >>> page.finish_pending_edits() is None
            True
        """
        try:
            self.clinic.post_all()
        except Exception as exc:
            self.show_error(str(exc))
            return str(exc)
        return None

    def _ask_confirm(self, parent: Optional[QWidget], text: str) -> bool:
        """
        Вопрос «да/нет» для массовых действий (удаление отмеченных — тем же вопросом, что
        у навигатора).

        Args:
            parent: Родитель.
            text: Вопрос.

        Returns:
            ``True`` — да.

        Пример:
            >>> page._ask_confirm(page, 'Удалить 3?')
            True
        """
        if self._ask_delete is not None:
            return bool(self._ask_delete())
        return QMessageBox.question(parent or self, 'Отмеченные', text) == QMessageBox.Yes

    def _save_targets(self, targets: List[Tuple[str, Any]]) -> bool:
        """
        Сохраняет черновики заданных записей (отмеченных) — с вопросами окна.

        Args:
            targets: Узлы ``(тип, id)``.

        Returns:
            ``True`` — сохранено.

        Пример:
            >>> page._save_targets([('patient', 3)])
            True
        """
        self.clinic.post_all()
        if self._save_handler is not None:
            ok = bool(self._save_handler(list(targets), None))
        else:
            ok = self.clinic.drafts.save(list(targets)) is not None
        self.show_status('Сохранено' if ok else 'Сохранение отменено')
        return ok

    def save(self, current: bool = False) -> bool:
        """
        Сохраняет черновики: всё или ветку текущего пациента.

        Args:
            current: Только текущий пациент (с приёмами и фото).

        Returns:
            ``True`` — сохранено.

        Пример:
            >>> page.save(current=True)
            True
        """
        if self.drafts is None:
            return True
        try:
            self.clinic.post_all()
        except Exception as exc:
            self.show_error(str(exc))
            return False
        targets = None
        if current:
            key = self.clinic.patients.current_key
            if key is None:
                self.show_status('Нет текущего пациента')
                return False
            targets = [('patient', key)]
        try:
            if self._save_handler is not None:
                ok = bool(self._save_handler(targets, None))
            else:
                ok = self.clinic.drafts.save(targets) is not None
        except Exception as exc:
            self.show_error(f"Не сохранено: {exc}")
            return False
        self.show_status('Сохранено' if ok else 'Сохранение отменено')
        return ok

    # ------------------------------------------------------------------ сообщения

    def show_error(self, message: str) -> None:
        """
        Ошибка — в строку состояния (красным).

        Args:
            message: Текст.

        Returns:
            None

        Пример:
            >>> page.show_error('поле «Фамилия» обязательно')
        """
        self.status.setStyleSheet('color: #b00020;')
        self.status.setText(message)

    def show_status(self, message: str) -> None:
        """
        Сообщение — в строку состояния.

        Args:
            message: Текст.

        Returns:
            None

        Пример:
            >>> page.show_status('Сохранено')
        """
        self.status.setStyleSheet('')
        self.status.setText(message)
