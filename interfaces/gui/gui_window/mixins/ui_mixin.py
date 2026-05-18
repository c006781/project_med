# interfaces/gui/gui_window/mixins/ui_mixin.py
"""
Миксин для построения пользовательского интерфейса страницы списка.

Предоставляет методы для создания:
    - Верхней панели с кнопками и комбобоксами.
    - Таблицы (FilterTableView).
    - Панели фильтров (FilterBar).
    - Управления видимостью элементов в режиме редактирования.
    - Обработки действий из выпадающих списков (обычный режим и inline-режим).
    - Двойного клика по строке.

Требования к классу-наследнику:
    - Должен содержать атрибут `main_layout` (QVBoxLayout), созданный до вызова `setup_ui()`.
    - Должен содержать атрибут `table_view` (FilterTableView) – будет создан в `_create_table()`.
    - Должен содержать атрибут `filter_bar` (FilterBar) – будет создан в `_create_filter_bar()`.
    - Должен содержать атрибут `edit_mode` (bool) – управляется извне.
    - Должен реализовывать следующие методы (вызываются из UI):
        - `add_row()` – добавление новой строки в режиме редактирования.
        - `delete_selected_rows()` – удаление выбранных строк.
        - `cancel_selected_rows_changes()` – отмена изменений выбранных строк.
        - `save_all_changes()` – сохранение всех изменений.
        - `reload_data()` – перезагрузка данных (по кнопке «Обновить»).
        - `get_current_selected_dto()` – возвращает DTO текущей выделенной строки.
        - `set_global_search(text)` – устанавливает глобальный текстовый фильтр.
        - `toggle_edit_mode(enable)` – переключает режим редактирования (подключается к кнопке).
        - `cancel_parent_changes_only()` – отмена только родительских правок (если используется).
    - Должен содержать сигналы:
        - `add_requested` – испускается при нажатии «Добавить» в обычном режиме.
        - `edit_requested` – испускается при выборе «Редактировать» (передаётся DTO).
        - `delete_requested` – испускается при выборе «Удалить» (передаётся DTO).
        - `action_requested` – испускается при двойном клике или нажатии дополнительной кнопки.

Примечание:
    - Метод `_setup_delegates()` оставлен пустым и должен быть переопределён в наследнике
      для установки делегатов в зависимости от типов столбцов.
"""

from interfaces.gui.gui_window.widgets.filter_column import FilterBar
from interfaces.gui.gui_window.widgets.filter_table_view import FilterTableView

from PySide6.QtWidgets import (
    QHBoxLayout, QVBoxLayout, 
    QPushButton, QLineEdit, 
    QComboBox,
)
# from PySide6.QtCore import Qt, Signal



class UIMixin:
    """
    Миксин для построения пользовательского интерфейса страницы списка.

    Создаёт верхнюю панель, таблицу, фильтр-бар и управляет их состоянием.
    """

    def setup_ui(self):
        """
        Главный метод построения интерфейса.

        Выполняет:
            1. Создаёт основной вертикальный layout (self.main_layout).
            2. Вызывает `_create_top_panel()` – создаёт верхнюю панель.
            3. Вызывает `_create_table()` – создаёт таблицу.
            4. Добавляет таблицу в main_layout.
            5. Вызывает `_create_filter_bar()` – создаёт фильтр-бар.
            6. Вставляет фильтр-бар перед таблицей.
            7. Вызывает `_setup_delegates()` – устанавливает делегаты (переопределяется в наследнике).

        Требования:
            - self.main_layout должен существовать (например, создан в `__init__`).
            - self.table_view будет создан в `_create_table()`.
        """

        self.main_layout = QVBoxLayout(self)

        self._create_top_panel()
        self._create_table()
        self.main_layout.addWidget(self.table_view)
        self._create_filter_bar()
        
        # Вставляем фильтр-бар перед таблицей
        idx = self.main_layout.indexOf(self.table_view)
        if idx >= 0:
            self.main_layout.insertWidget(idx, self.filter_bar)

        self._setup_delegates()

    def _create_top_panel(self):
        """
        Создаёт верхнюю панель с элементами управления.

        Создаёт:
            - Кнопку переключения режима редактирования (self.edit_mode_btn).
            - Выпадающий список действий в обычном режиме (self.action_combo).
            - Выпадающий список inline-действий в режиме редактирования (self.inline_action_combo).
            - Кнопку сохранения изменений (self.save_changes_btn).
            - Кнопку дополнительного действия (self.action_btn) – если задан `action_button_text`.
            - Поле поиска (self.search_edit).

        Подключает сигналы:
            - self.edit_mode_btn.toggled -> self.toggle_edit_mode
            - self.action_combo.currentIndexChanged -> self._on_action_selected
            - self.inline_action_combo.currentIndexChanged -> self._on_inline_action_selected
            - self.save_changes_btn.clicked -> self.save_all_changes
            - self.action_btn.clicked (если есть) -> self._on_action_clicked
            - self.search_edit.textChanged -> self.set_global_search

        Требования (атрибуты класса-наследника):
            - self.action_button_text (str, optional) – текст дополнительной кнопки.
            - self.edit_mode (bool) – текущее состояние режима редактирования.
            - self.toggle_edit_mode(enable) – метод переключения режима.
            - self.save_all_changes() – метод сохранения.
            - self.set_global_search(text) – метод установки глобального фильтра.
        """

        # тригеры в def _update_ui_for_edit_mode

        top_layout = QHBoxLayout()

        # Кнопка переключения режима редактирования
        self.edit_mode_btn = QPushButton("Режим редактирования")
        self.edit_mode_btn.setCheckable(True)
        self.edit_mode_btn.toggled.connect(self.toggle_edit_mode)
        top_layout.addWidget(self.edit_mode_btn)

        # Выпадающий список действий (обычный режим)
        self.action_combo = QComboBox()
        self.action_combo.addItems(
            [
                "▼ Действия с записями", 
                "Добавить", 
                "Редактировать", 
                "Удалить", 
                "Обновить",
            ]
        )
        self.action_combo.model().item(0).setEnabled(False)
        self.action_combo.setCurrentIndex(0)
        self.action_combo.currentIndexChanged.connect(self._on_action_selected)
        top_layout.addWidget(self.action_combo)

        # Выпадающий список inline-действий (режим редактирования)
        self.inline_action_combo = QComboBox()
        self.inline_action_combo.addItems(
            [
                "▼ Действия со строками", 
                "Добавить строку", 
                "Удалить строку", 
                "Отменить изменения",
            ]
        )
        self.inline_action_combo.model().item(0).setEnabled(False)
        self.inline_action_combo.setCurrentIndex(0)
        self.inline_action_combo.currentIndexChanged.connect(self._on_inline_action_selected)
        self.inline_action_combo.setVisible(False)
        top_layout.addWidget(self.inline_action_combo)

        # Кнопка сохранения
        self.save_changes_btn = QPushButton("Сохранить изменения")
        self.save_changes_btn.setEnabled(False)
        self.save_changes_btn.setVisible(False)
        self.save_changes_btn.clicked.connect(self.save_all_changes)
        top_layout.addWidget(self.save_changes_btn)

        self.cancel_parent_btn = QPushButton("Отменить правки строки")
        self.cancel_parent_btn.setVisible(False)
        self.cancel_parent_btn.clicked.connect(self.cancel_parent_changes_only)
        top_layout.addWidget(self.cancel_parent_btn)

        # Кнопка дополнительного действия
        if getattr(self, 'action_button_text', None):
            self.action_btn = QPushButton(self.action_button_text)
            self.action_btn.clicked.connect(self._on_action_clicked)
            self.action_btn.setEnabled(False)
            top_layout.addWidget(self.action_btn)

        top_layout.addStretch()

        # Поле поиска
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Поиск...")
        self.search_edit.textChanged.connect(self.set_global_search)
        top_layout.addWidget(self.search_edit)

        self.main_layout.addLayout(top_layout)

    def _create_table(self):
        """
        Создаёт таблицу (FilterTableView) и настраивает её базовые свойства.

        Устанавливает:
            - self.table_view (FilterTableView)
            - Сортировку (setSortingEnabled)
            - Поведение выделения строк (SelectRows)
            - Режим выделения (SingleSelection)
            - Триггеры редактирования (NoEditTriggers – будут включены в режиме редактирования)
            - Подключение двойного клика к self._on_row_double_clicked

        Примечание:
            Модель таблицы и прокси-модель должны быть установлены в наследнике.
        """

        # from interfaces.gui.gui_window.widgets.filter_table_view import FilterTableView
        self.table_view = FilterTableView()
        self.table_view.setSortingEnabled(True)
        self.table_view.setSelectionBehavior(self.table_view.SelectionBehavior.SelectRows)
        self.table_view.setSelectionMode(self.table_view.SelectionMode.SingleSelection)
        self.table_view.setEditTriggers(self.table_view.NoEditTriggers)
        self.table_view.doubleClicked.connect(self._on_row_double_clicked)

        # Подключаем сигнал сортировки, если метод-обработчик определён в классе-наследнике
        # Обоснование: Мы подключаем сигнал sortIndicatorChanged заголовка таблицы к методу _on_sort_indicator_changed, который должен быть предоставлен одним из миксинов (например, FilterMixin). Проверка hasattr делает код устойчивым к отсутствию обработчика.
        if hasattr(self, '_on_sort_indicator_changed'):
            header = self.table_view.horizontalHeader()
            header.sortIndicatorChanged.connect(self._on_sort_indicator_changed)

    def _create_filter_bar(self):
        """
        Создаёт панель активных фильтров (FilterBar).

        Устанавливает:
            - self.filter_bar (FilterBar) – изначально скрыта.
        """

        # from interfaces.gui.gui_window.widgets.filter_column import FilterBar
        self.filter_bar = FilterBar(self)
        self.filter_bar.setVisible(False)

    def _setup_delegates(self):
        """
        Устанавливает делегаты для столбцов таблицы.

        **Должен быть переопределён в наследнике!**
        Базовый метод ничего не делает. В наследнике необходимо:
            - Проанализировать field_configs и типы полей.
            - Создать соответствующие делегаты (ComboBoxDelegate, DatePickerDelegate и т.д.).
            - Установить их для каждого столбца через `self.table_view.setItemDelegateForColumn()`.

        Примечание:
            Этот метод вызывается в конце `setup_ui()`.
        """

        # Будет реализовано позже, аналогично DynamicListPage._setup_delegates
        pass

    def _on_action_selected(self, index):
        """
        Обработчик выбора действия в обычном режиме (self.action_combo).

        Args:
            index (int): Индекс выбранного пункта.
                1 → Добавить (испускает сигнал add_requested)
                2 → Редактировать (испускает edit_requested с текущим DTO)
                3 → Удалить (испускает delete_requested с текущим DTO)
                4 → Обновить (вызывает reload_data())

        После обработки сбрасывает индекс комбобокса на 0 (заглушку).

        Требования:
            - self.get_current_selected_dto() – возвращает DTO выбранной строки.
            - self.add_requested, self.edit_requested, self.delete_requested – сигналы.
            - self.reload_data() – метод перезагрузки данных.
        """

        if index == 1:   # Добавить
            self.add_requested.emit()

        elif index == 2: # Редактировать
            dto = self.get_current_selected_dto()
            if dto:
                self.edit_requested.emit(dto)

        elif index == 3: # Удалить
            dto = self.get_current_selected_dto()
            if dto:
                self.delete_requested.emit(dto)

        elif index == 4: # Обновить
            self.reload_data()

        self.action_combo.setCurrentIndex(0)

    def _on_inline_action_selected(self, index):
        """
        Обработчик выбора действия в режиме редактирования (self.inline_action_combo).

        Args:
            index (int): Индекс выбранного пункта.
                1 → Добавить строку (вызывает add_row())
                2 → Удалить строку (вызывает delete_selected_rows())
                3 → Отменить изменения (вызывает cancel_selected_rows_changes())

        После обработки сбрасывает индекс комбобокса на 0 (заглушку).

        Требования:
            - self.add_row(), self.delete_selected_rows(), self.cancel_selected_rows_changes()
              должны быть реализованы в наследнике.
        """

        if index == 1:   # Добавить строку
            self.add_row()

        elif index == 2: # Удалить строку
            self.delete_selected_rows()

        elif index == 3: # Отменить изменения
            self.cancel_selected_rows_changes()

        self.inline_action_combo.setCurrentIndex(0)

    def _on_action_clicked(self):
        """
        Обработчик нажатия дополнительной кнопки (self.action_btn).

        Испускает сигнал action_requested с текущим DTO.

        Требования:
            - self.get_current_selected_dto() – возвращает DTO выбранной строки.
            - self.action_requested – сигнал.
        """

        dto = self.get_current_selected_dto()
        if dto:
            self.action_requested.emit(dto)

    def _on_row_double_clicked(self, index):
        """
        Обработчик двойного клика по строке таблицы.

        Если режим редактирования выключен, испускает сигнал action_requested
        с DTO строки, по которой был произведён двойной клик.

        Args:
            index (QModelIndex): Индекс ячейки, по которой кликнули.
        """

        if not self.edit_mode:
            dto = self.get_current_selected_dto()
            if dto:
                self.action_requested.emit(dto)

    def _update_ui_for_edit_mode(self, edit_mode: bool):
        """
        Обновляет видимость элементов UI в зависимости от режима редактирования.

        Args:
            edit_mode (bool): True – режим редактирования включён, False – выключен.

        Действия:
            - Скрывает/показывает self.action_combo.
            - Показывает/скрывает self.inline_action_combo.
            - Показывает/скрывает self.save_changes_btn.
            - Устанавливает режим редактирования таблицы (DoubleClicked / NoEditTriggers).
            - Если есть self.action_btn – включает/отключает его (в обычном режиме активна, в режиме редактирования – нет).

        Примечание:
            Этот метод вызывается из `EditModeMixin._set_edit_mode()`.
        """

        # описание в def _create_top_panel
        self.action_combo.setVisible(not edit_mode)
        self.inline_action_combo.setVisible(edit_mode)
        self.save_changes_btn.setVisible(edit_mode)
        self.cancel_parent_btn.setVisible(edit_mode) 

        self.table_view.setEditTriggers(self.table_view.DoubleClicked if edit_mode else self.table_view.NoEditTriggers)

        if hasattr(self, 'action_btn') and self.action_btn:
            self.action_btn.setEnabled(not edit_mode)