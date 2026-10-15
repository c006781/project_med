# app/utils/drafts_qt/page.py

"""
Страница-таблица с черновиками: таблица + панель действий + постраничная загрузка.

Данные — через ``RowSource`` (любой источник: сервис, API, список); сохранение —
через переданную функцию (окно решает, что и с какими вопросами сохранять). Код
приложения не используется (переносимость).

Возможности:
    * правка ячеек — черновики (модель ``DraftTableModel``);
    * «Добавить», «Удалить», «Восстановить», «Отменить» (строку или ветку), «Сохранить»;
    * постраничная загрузка (◀ стр. N из M ▶);
    * контекст родителя (``set_parent``) — таблица детей выбранной строки другой таблицы;
    * выделение сохраняется при перечитывании (и после замены временного id);
    * цель сохранения: текущая строка (``current_node``), выделенные (``selected_nodes``),
      вся страница (``page_nodes``).

Пример:
    >>> page = DraftTablePage(store, 'photo', columns, source=photo_source,
    ...                       save_handler=lambda p: window.save_drafts())
    >>> page.set_parent(12)          # фото приёма 12
"""

from __future__ import annotations

from typing import Any, Callable, Hashable, List, Mapping, Optional, Sequence, Tuple

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QHeaderView, QLabel, QMenu, QPushButton, QStyledItemDelegate,
    QTableView, QToolButton, QVBoxLayout, QWidget,
)

from .model import Column, DraftTableModel

try:
    from ..drafts import MISSING, DraftStore, NodeKey, SaveScope
except ImportError:  # pragma: no cover
    from drafts import MISSING, DraftStore, NodeKey, SaveScope

try:
    from typing import Protocol
except ImportError:  # pragma: no cover
    Protocol = object  # type: ignore


class RowSource(Protocol):
    """
    Источник строк страницы.

    Пример:
        >>> class ListSource:
        ...     def load(self, offset, limit, parent_id):
        ...         rows = [r for r in ALL if parent_id is MISSING or r['appointment_id'] == parent_id]
        ...         return rows[offset:offset + limit], len(rows)
    """

    def load(self, offset: int, limit: int, parent_id: Any) -> Tuple[List[Mapping[str, Any]], int]:
        """
        Страница строк.

        Args:
            offset: Сколько строк пропустить.
            limit: Сколько вернуть.
            parent_id: Родитель (контекст) или ``MISSING`` — без фильтра.

        Returns:
            ``(строки, всего строк)``.

        Пример:
            >>> source.load(0, 50, 12)
            ([{'id': 7, 'appointment_id': 12, 'file_path': 'a.jpg'}], 1)
        """
        ...  # pragma: no cover


class DraftTablePage(QWidget):
    """
    Таблица записей одного типа с черновиками.

    Сигналы:
        current_changed(object): id текущей строки (``None`` — нет).
        save_requested(): нажата «Сохранить» (если не задан ``save_handler``).

    Пример:
        >>> page = DraftTablePage(store, 'patient', [Column('last_name', 'Фамилия')], source)
        >>> page.reload()
    """

    current_changed = Signal(object)
    save_requested = Signal()

    def __init__(
        self,
        store: DraftStore,
        entity: str,
        columns: Sequence[Column],
        source: RowSource,
        save_handler: Optional[Callable[['DraftTablePage'], Any]] = None,
        page_size: int = 50,
        title: Optional[str] = None,
        default_row: Optional[Callable[[], Mapping[str, Any]]] = None,
        requires_parent: bool = False,
        parent: Optional[QWidget] = None,
    ) -> None:
        """
        Args:
            store: Хранилище черновиков (общее для приложения).
            entity: Тип записей.
            columns: Колонки.
            source: Источник строк.
            save_handler: Что делать по «Сохранить» (получает страницу); нет —
                испускается ``save_requested``.
            page_size: Строк на странице.
            title: Заголовок над таблицей.
            default_row: Поля новой строки по «Добавить».
            requires_parent: Таблица детей: без родителя (``set_parent``) пустая, «Добавить»
                недоступно.
            parent: Родительский виджет.

        Пример:
            >>> DraftTablePage(store, 'photo', cols, source, requires_parent=True)
        """
        super().__init__(parent)
        self.store = store
        self.entity = entity
        self.source = source
        self.save_handler = save_handler
        self.page_size = max(1, page_size)
        self.default_row = default_row
        self.requires_parent = requires_parent
        self._page = 0
        self._total = 0
        self._parent_id: Any = MISSING

        self.model = DraftTableModel(store, entity, columns, parent=self)
        self.model.reload_requested.connect(self.reload)
        self.model.row_id_changed.connect(self._on_row_id_changed)

        self.view = QTableView(self)
        self.view.setModel(self.model)
        self.view.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.view.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed
                                  | QAbstractItemView.AnyKeyPressed)
        self.view.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.view.horizontalHeader().setStretchLastSection(True)
        for i, column in enumerate(columns):
            if column.width:
                self.view.setColumnWidth(i, column.width)
        self.view.selectionModel().currentRowChanged.connect(self._on_current_row_changed)
        self.view.selectionModel().selectionChanged.connect(lambda *_: self._update_buttons())

        self._build_toolbar(title)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self._toolbar)
        layout.addWidget(self.view)
        self._update_buttons()

    # ------------------------------------------------------------------
    # Интерфейс
    # ------------------------------------------------------------------

    def _build_toolbar(self, title: Optional[str]) -> None:
        """
        Панель: заголовок, действия, листание.

        Args:
            title: Заголовок.

        Returns:
            None

        Пример:
            >>> page._build_toolbar('Фото')
        """
        bar = QHBoxLayout()
        self.title_label = QLabel(title or '', self)
        self.title_label.setVisible(bool(title))
        bar.addWidget(self.title_label)

        self.add_btn = QPushButton("Добавить", self)
        self.add_btn.clicked.connect(self.add_row)
        self.delete_btn = QPushButton("Удалить", self)
        self.delete_btn.clicked.connect(self.delete_selected)
        self.undelete_btn = QPushButton("Восстановить", self)
        self.undelete_btn.clicked.connect(self.undelete_selected)

        self.discard_btn = QToolButton(self)
        self.discard_btn.setText("Отменить")
        self.discard_btn.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(self.discard_btn)
        menu.addAction("Изменения строки", lambda: self.discard_selected(SaveScope.SELF))
        menu.addAction("Изменения строки и вложенных", lambda: self.discard_selected(SaveScope.BRANCH))
        self.discard_btn.setMenu(menu)

        self.save_btn = QPushButton("Сохранить", self)
        self.save_btn.clicked.connect(self._on_save_clicked)

        for widget in (self.add_btn, self.delete_btn, self.undelete_btn, self.discard_btn, self.save_btn):
            bar.addWidget(widget)
        bar.addStretch(1)

        self.prev_btn = QToolButton(self)
        self.prev_btn.setText("◀")
        self.prev_btn.clicked.connect(lambda: self.go_to_page(self._page - 1))
        self.page_label = QLabel(self)
        self.next_btn = QToolButton(self)
        self.next_btn.setText("▶")
        self.next_btn.clicked.connect(lambda: self.go_to_page(self._page + 1))
        for widget in (self.prev_btn, self.page_label, self.next_btn):
            bar.addWidget(widget)
        self._toolbar = bar

    def set_column_delegate(self, field: str, delegate: QStyledItemDelegate) -> None:
        """
        Свой делегат (редактор/отрисовка) для колонки.

        Args:
            field: Поле колонки.
            delegate: Делегат.

        Returns:
            None

        Пример:
            >>> page.set_column_delegate('file_path', ImageDelegate(page.view))
        """
        for i, column in enumerate(self.model.columns):
            if column.field == field:
                self.view.setItemDelegateForColumn(i, delegate)
                return
        raise KeyError(f"нет колонки '{field}'")

    def _update_buttons(self) -> None:
        """
        Доступность кнопок по выделению, контексту и состоянию строк.

        Returns:
            None

        Пример:
            >>> page._update_buttons()
        """
        rows = self.selected_rows()
        statuses = [self.model.row_status(r) for r in rows]
        has_context = not (self.requires_parent and self._parent_id is MISSING)
        self.add_btn.setEnabled(has_context)
        self.delete_btn.setEnabled(any(s != 'deleted' for s in statuses))
        self.undelete_btn.setEnabled(any(s == 'deleted' for s in statuses))
        self.discard_btn.setEnabled(any(s is not None for s in statuses))
        pages = max(1, -(-self._total // self.page_size))
        self.page_label.setText(f"стр. {self._page + 1} из {pages}")
        self.prev_btn.setEnabled(self._page > 0)
        self.next_btn.setEnabled(self._page + 1 < pages)

    # ------------------------------------------------------------------
    # Данные
    # ------------------------------------------------------------------

    @property
    def parent_id(self) -> Any:
        """
        Текущий родитель (контекст) или ``MISSING``.

        Returns:
            Id родителя.

        Пример:
            >>> page.parent_id
            12
        """
        return self._parent_id

    def set_parent(self, parent_id: Any) -> None:
        """
        Показать детей записи ``parent_id`` (``None``/``MISSING`` — пусто у таблицы,
        которой нужен родитель). Переход на первую страницу.

        Args:
            parent_id: Id родителя.

        Returns:
            None

        Пример:
            >>> page.set_parent(12)
        """
        self._parent_id = MISSING if parent_id is None else parent_id
        self._page = 0
        self.reload()

    def go_to_page(self, page: int) -> None:
        """
        Перейти на страницу (с ограничением диапазона).

        Args:
            page: Номер страницы с 0.

        Returns:
            None

        Пример:
            >>> page.go_to_page(1)
        """
        pages = max(1, -(-self._total // self.page_size))
        self._page = min(max(0, page), pages - 1)
        self.reload()

    def reload(self) -> None:
        """
        Перечитать текущую страницу из источника; черновики показываются поверх,
        выделенная строка сохраняется.

        Returns:
            None

        Пример:
            >>> page.reload()
        """
        current = self.current_id()
        if self.requires_parent and self._parent_id is MISSING:
            self.model.clear()
            self._total = 0
        else:
            rows, self._total = self.source.load(self._page * self.page_size, self.page_size,
                                                 self._parent_id)
            self.model.set_rows(rows, parent_id=self._parent_id)
        if current is not None:
            self.select_id(current)
        self._update_buttons()
        if self.current_id() != current:
            self.current_changed.emit(self.current_id())

    # ------------------------------------------------------------------
    # Выделение и цели сохранения
    # ------------------------------------------------------------------

    def selected_rows(self) -> List[int]:
        """
        Номера выделенных строк по возрастанию.

        Returns:
            Список.

        Пример:
            >>> page.selected_rows()
            [0, 2]
        """
        return sorted({index.row() for index in self.view.selectionModel().selectedRows()})

    def current_id(self) -> Optional[Hashable]:
        """
        Id текущей строки.

        Returns:
            Id или ``None``.

        Пример:
            >>> page.current_id()
            7
        """
        index = self.view.currentIndex()
        if not index.isValid() or index.row() >= self.model.rowCount():
            return None
        return self.model.row_id(index.row())

    def select_id(self, entity_id: Hashable) -> bool:
        """
        Сделать строку текущей и выделенной.

        Args:
            entity_id: Id записи.

        Returns:
            ``True``, если строка есть на странице.

        Пример:
            >>> page.select_id(7)
            True
        """
        row = self.model.row_of(entity_id)
        if row < 0:
            return False
        self.view.selectRow(row)
        self.view.setCurrentIndex(self.model.index(row, 0))
        return True

    def current_node(self) -> Optional[NodeKey]:
        """
        Цель «текущая строка» (узел ветки).

        Returns:
            Ключ узла или ``None``.

        Пример:
            >>> page.current_node()
            ('photo', 7)
        """
        entity_id = self.current_id()
        return None if entity_id is None else (self.entity, entity_id)

    def selected_nodes(self) -> List[NodeKey]:
        """
        Цель «выделенные строки».

        Returns:
            Ключи узлов.

        Пример:
            >>> page.selected_nodes()
            [('photo', 7), ('photo', -1)]
        """
        return [self.model.node(r) for r in self.selected_rows()]

    def page_nodes(self) -> List[NodeKey]:
        """
        Цель «вся выборка страницы» (несколько веток).

        Returns:
            Ключи узлов всех строк страницы.

        Пример:
            >>> page.page_nodes()
            [('appointment', 12), ('appointment', 13)]
        """
        return [self.model.node(r) for r in range(self.model.rowCount())]

    # ------------------------------------------------------------------
    # Действия
    # ------------------------------------------------------------------

    def add_row(self) -> Optional[Hashable]:
        """
        Новая строка под текущим родителем; становится текущей.

        Returns:
            Временный id или ``None`` (нет контекста).

        Пример:
            >>> page.add_row()
            -1
        """
        if self.requires_parent and self._parent_id is MISSING:
            return None
        new_id = self.model.add_row(dict(self.default_row() if self.default_row else {}))
        self.select_id(new_id)
        self._update_buttons()
        return new_id

    def delete_selected(self) -> None:
        """
        Пометить выделенные строки на удаление.

        Returns:
            None

        Пример:
            >>> page.delete_selected()
        """
        self.model.delete_rows(self.selected_rows())
        self._update_buttons()

    def undelete_selected(self) -> None:
        """
        Снять пометку удаления с выделенных строк.

        Returns:
            None

        Пример:
            >>> page.undelete_selected()
        """
        self.model.undelete_rows(self.selected_rows())
        self._update_buttons()

    def discard_selected(self, scope: SaveScope = SaveScope.SELF) -> None:
        """
        Отменить изменения выделенных строк (``BRANCH`` — и вложенных).

        Args:
            scope: Направления.

        Returns:
            None

        Пример:
            >>> page.discard_selected(SaveScope.BRANCH)
        """
        self.model.discard_rows(self.selected_rows(), scope)
        self._update_buttons()

    def _on_save_clicked(self) -> None:
        """
        «Сохранить»: ``save_handler(self)`` или сигнал ``save_requested``.

        Returns:
            None

        Пример:
            >>> page._on_save_clicked()
        """
        if self.save_handler is not None:
            self.save_handler(self)
        else:
            self.save_requested.emit()

    def _on_current_row_changed(self, current: Any, previous: Any) -> None:
        """
        Текущая строка сменилась → ``current_changed``.

        Args:
            current: Новый индекс.
            previous: Прежний индекс.

        Returns:
            None

        Пример:
            >>> page._on_current_row_changed(index, QModelIndex())
        """
        self._update_buttons()
        self.current_changed.emit(self.current_id())

    def _on_row_id_changed(self, old_id: Hashable, new_id: Hashable) -> None:
        """
        Новая запись сохранена: временный id → настоящий; текущая строка сохраняется.

        Args:
            old_id: Временный id.
            new_id: Настоящий id.

        Returns:
            None

        Пример:
            >>> page._on_row_id_changed(-1, 55)
        """
        if self.current_id() == new_id:
            self.current_changed.emit(new_id)
