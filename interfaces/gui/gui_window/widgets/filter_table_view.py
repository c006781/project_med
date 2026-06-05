# interfaces/gui/gui_window/widgets/filter_table_view.py
"""
Заголовок таблицы с контекстным меню для фильтрации, сортировки и мульти-сортировки.

При клике правой кнопкой мыши на секцию заголовка отображается меню, позволяющее:
    - Сортировать столбец по возрастанию или убыванию (пункты отключаются при активном fuzzy-фильтре).
    - Настроить мульти-сортировку (диалог выбора нескольких столбцов).
    - Сбросить текущую сортировку.
    - Открыть диалог расширенной фильтрации (поддержка AND/OR, нескольких условий,
      операторов eq, like, between, in, is_null и др.).
    - Сбросить фильтр для столбца.

Для чекбокс-столбца (индекс 0) при включённом режиме редактирования
отображается отдельное меню с пунктами «Выбрать все» / «Снять все».

**Сигналы:**
    - `filter_requested(column: int, logic: str, conditions: list)` – испускается при настройке фильтра.
    - `filter_clear_requested(column: int)` – испускается при сбросе фильтра для столбца.

**Важно:** При активном fuzzy-фильтре (определяемом через `parent().has_active_fuzzy_filter()`)
пункты меню, связанные с сортировкой, отключаются (`setEnabled(False)`).

**Методы:**
    - `set_multi_sorting(specs)` – перенаправляет запрос мульти-сортировки на родительскую страницу
      (ищет вверх по иерархии виджет с методом `set_multi_sorting`).
    - `_show_multi_sort_dialog()` – открывает диалог выбора столбцов для мульти-сортировки.

Модуль предоставляет два основных класса:

1. FilterHeaderView – переопределённый QHeaderView, который при клике правой
   кнопкой мыши показывает контекстное меню с опциями:
   - Сортировка по одному столбцу (по возрастанию/убыванию)
   - Мульти-сортировка (выбор нескольких столбцов через диалог)
   - Сброс сортировки
   - Настройка фильтра (диалог с поддержкой множественных условий, операторов
     eq, like, between, in, is_null и т.д.)
   - Сброс фильтра для столбца

   Заголовок также поддерживает:
   - Отображение чекбокс-столбца с отдельным меню ("Выбрать все"/"Снять все")
   - Получение уникальных значений для столбца через callback `set_get_unique_values_func`
   - Отключение пунктов сортировки при активном fuzzy-фильтре (проверка через
     родительский виджет, имеющий метод `has_active_fuzzy_filter`)

2. FilterTableView – QTableView, использующий FilterHeaderView в качестве
   горизонтального заголовка. Предоставляет метод `on_filter_requested`,
   который должен быть переопределён в наследнике или связан с моделью/контроллером
   для фактической фильтрации данных.

Использование:
    Таблица автоматически подключает сигналы заголовка к методам фильтрации.
    Для полноценной работы требуется установка модели (например, PaginatedTableModel)
    и реализация обработки сигнала `filter_requested` на уровне страницы.

Пример:
    >>> table = FilterTableView()
    >>> header = table.horizontalHeader()  # это уже FilterHeaderView
    >>> header.set_get_unique_values_func(lambda col: get_unique_values(col))
    >>> header.filter_requested.connect(on_filter_requested)
"""

from typing import Optional

from app.utils.logger.logger import AppLogger

from interfaces.gui.gui_window.widgets.filter_column import FilterColumnDialog

from PySide6.QtWidgets import (
    QComboBox, QTableView, 
    QHeaderView, QMenu, 
    QDialog, QListWidget, 
    QVBoxLayout, QHBoxLayout, 
    QPushButton,
    # QInputDialog, QListWidgetItem,
)

from PySide6.QtCore import (
    QModelIndex, Qt, 
    Signal, Slot
) 
from PySide6.QtGui import QAction


class FilterHeaderView(QHeaderView):
    """
    Заголовок таблицы с контекстным меню для фильтрации и сортировки.

    При клике правой кнопкой мыши на секцию заголовка отображается меню,
    позволяющее:
        - Сортировать столбец по возрастанию или убыванию.
        - Настроить мульти-сортировку (диалог выбора нескольких столбцов).
        - Сбросить текущую сортировку.
        - Открыть диалог расширенной фильтрации (поддержка AND/OR, нескольких условий,
          операторов eq, like, between, in, is_null и др.).
        - Сбросить фильтр для столбца.

    Для чекбокс-столбца (индекс 0) при включённом режиме редактирования
    отображается отдельное меню с пунктами «Выбрать все» / «Снять все».

    Сигналы:
        filter_requested(column: int, logic: str, conditions: list)
            Испускается, когда пользователь настроил фильтр. Передаётся логика
            объединения условий ('AND' или 'OR') и список условий.
        filter_clear_requested(column: int)
            Испускается при сбросе фильтра для столбца.

    Для корректной работы необходимо установить:
        - Функцию получения уникальных значений (через `set_get_unique_values_func`),
          используемую в диалоге фильтрации.
        - Callback для чекбокс-столбца (через `set_checkbox_header_menu`).

    Параметры:
        orientation (Qt.Orientation): Горизонтальная или вертикальная ориентация.
        parent (QWidget, optional): Родительский виджет.

    Пример:
        >>> header = FilterHeaderView(Qt.Horizontal, parent)
        >>> header.set_get_unique_values_func(my_get_unique_values)
        >>> header.set_checkbox_header_visible(True)
        >>> header.set_checkbox_header_menu(toggle_all_checkboxes)
        >>> header.filter_requested.connect(on_filter_requested)
    """

    # filter_requested = Signal(int, str, object)  # индекс колонки, оператор, значение
    filter_requested = Signal(int, str, object)  # column, logic, conditions
    filter_clear_requested = Signal(int)         # сброс фильтра для колонки
    
    @AppLogger.get_instance( 
        name = 'FilterHeaderView',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def __init__(self, orientation, parent=None):
        """
        Инициализирует заголовок таблицы.

        :param orientation: ориентация заголовка (Qt.Orientation.Horizontal или Qt.Orientation.Vertical)
        :type orientation: Qt.Orientation
        :param parent: родительский объект (необязательный)
        :type parent: QObject
        """

        super().__init__(orientation, parent)
        self.setSectionsClickable(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        self._get_unique_values_func = None   # функция для получения уникальных значений 

        self._checkbox_column_visible = False   # по умолчанию скрыт

    @AppLogger.get_instance( 
        name = 'FilterHeaderView',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def set_checkbox_column_visible(self, visible: bool):
        """Устанавливает, виден ли столбец чекбоксов."""
        self._checkbox_column_visible = visible

    @AppLogger.get_instance( 
        name = 'FilterHeaderView',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def set_checkbox_header_menu(self, toggle_callback):
        """Устанавливает callback для управления всеми чекбоксами."""
        self._checkbox_toggle_callback = toggle_callback



 
    @AppLogger.get_instance( 
        name = 'FilterHeaderView',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _create_checkbox_menu_item( 
        self, 
        name:str, 
        thec:bool
    ):   
        """
        Создает пункт меню для чекбокса со значением thec.

        :param name: имя пункта меню
        :type name: str
        :param thec: значение чекбокса
        :type thec: bool
        :return: пункт меню
        :rtype: QAction
        """
        select_ = QAction(name, self)
        select_.triggered.connect(
            lambda: self._checkbox_toggle_callback(thec)
        )

        return select_
    
    @AppLogger.get_instance( 
        name = 'FilterHeaderView',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def set_get_unique_values_func(self, func):
        """
        Устанавливает функцию, которая будет использоваться для получения списка уникальных значений
        для столбца. Функция должна возвращать список уникальных значений в виде строкового представления.
        """
        self._get_unique_values_func = func

    @AppLogger.get_instance( 
        name = 'FilterHeaderView',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _show_context_menu(self, pos):
        """Показывает контекстное меню для секции заголовка."""

        logical_index = self.logicalIndexAt(pos)

        if logical_index == -1:
            return

        # ----- Если это столбец чекбоксов (индекс 0) и callback задан -----
        if (
            logical_index == 0
        ) and (
            hasattr(self, '_checkbox_toggle_callback') # callback задан
        ) and (
            self._checkbox_column_visible # столбец виден
        ):
            menu = QMenu(self)

            for name, thec in [ # True - выбрать, False - снять
                ("Выбрать все", True), 
                ("Снять все", False),
            ]:
                menu.addAction(
                    self._create_checkbox_menu_item ( 
                        name, 
                        thec 
                    )    
                )

            menu.exec(
                self.viewport().mapToGlobal(pos)
            )

            return
        
        def _create_sort_action(self, name, index, order, enabled: Optional[bool] = None):
            sort_asc = QAction(name, self)
            sort_asc.triggered.connect(lambda: self.parent().sortByColumn(index, order))    
            if enabled is not None:
                sort_asc.setEnabled(enabled)

            return sort_asc
        
        # ----- Обычное меню для остальных столбцов -----
        menu = QMenu(self)

        # Определяем, активен ли fuzzy-фильтр
        fuzzy_active = False 
        if hasattr(self.parent(), 'has_active_fuzzy_filter'):
            fuzzy_active = self.parent().has_active_fuzzy_filter()


        # Сортировка 
        menu.addAction(_create_sort_action(self, "Сортировать по возрастанию", logical_index, Qt.AscendingOrder,   not fuzzy_active))
        menu.addAction(_create_sort_action(self, "Сортировать по убыванию",    logical_index, Qt.DescendingOrder,  not fuzzy_active))
        menu.addSeparator()

        multi_sort = QAction("Мульти-сортировка...", self)
        multi_sort.triggered.connect(lambda: self._show_multi_sort_dialog())
        multi_sort.setEnabled(not fuzzy_active)
        menu.addAction(multi_sort)

        # Сброс сортировки
        menu.addAction(_create_sort_action(self, "Сбросить сортировку", -1, Qt.AscendingOrder))
        menu.addSeparator()

        # Пункт настройки фильтра
        filter_action = QAction("Настроить фильтр...", self)
        filter_action.triggered.connect(lambda: self._request_advanced_filter(logical_index))
        menu.addAction(filter_action)

        # Сброс фильтра для колонки
        clear_filter = QAction("Сбросить фильтр", self)
        clear_filter.triggered.connect(lambda: self.filter_clear_requested.emit(logical_index))
        menu.addAction(clear_filter)

        menu.exec(self.viewport().mapToGlobal(pos))

    def set_multi_sorting(self, specs):
        """
        Перенаправляет запрос мульти-сортировки на страницу (родительский виджет).

        Ищет в иерархии родительский виджет, у которого есть метод `set_multi_sorting`,
        начиная с непосредственного родителя (`self.parent()`) и поднимаясь вверх.
        Если такой виджет найден, вызывает у него `set_multi_sorting(specs)`.
        Если не найден, ничего не делает.

        Args:
            specs (List[Tuple[int, Qt.SortOrder]]): Список пар (видимый_индекс_столбца, порядок).

        Returns:
            None

        Примечание:
            Этот метод используется в диалоге мульти-сортировки для передачи выбранных
            спецификаций в главную страницу (обычно `PaginatedListPage`), где и происходит
            реальная перезагрузка данных с новым порядком сортировки.
        """

        parent = self.parent()
        while parent and not hasattr(parent, 'set_multi_sorting'):
            parent = parent.parent()

        if parent and hasattr(parent, 'set_multi_sorting'):
            parent.set_multi_sorting(specs)

    def _show_multi_sort_dialog(self):
        """
        Открывает диалог для выбора нескольких столбцов и направлений мульти-сортировки.

        В диалоге пользователь может:
            - Выбрать столбец из выпадающего списка (только видимые DATA-столбцы).
            - Выбрать направление (по возрастанию / по убыванию).
            - Добавить выбранную пару (столбец, направление) в список сортировки.
            - Удалить или изменить порядок можно только через интерфейс списка (перетаскивание не реализовано).

        После нажатия OK формируется список кортежей `(column_index, order)` и вызывается
        метод `set_multi_sorting` у родительской страницы (через `self.set_multi_sorting(specs)`).

        Примечания:
            - Если в диалоге не добавлено ни одной пары, сортировка не применяется.
            - Добавленные столбцы удаляются из выпадающего списка, чтобы нельзя было добавить
              один и тот же столбец дважды (простая защита).
            - Отмена диалога не приводит к изменению сортировки.

        Returns:
            None
        """

        # from PySide6.QtWidgets import QDialog, QVBoxLayout, QListWidget, QPushButton, QHBoxLayout, QComboBox
        
        dialog = QDialog(self)
        dialog.setWindowTitle("Мульти-сортировка")
        dialog.setMinimumWidth(400)
        layout = QVBoxLayout(dialog)
        
        list_widget = QListWidget()
        list_widget.setSelectionMode(QListWidget.SingleSelection)
        layout.addWidget(list_widget)
        
        # Панель для добавления столбца
        add_layout = QHBoxLayout()
        col_combo = QComboBox()

        # Заполняем названиями видимых столбцов
        model = self.parent().model()
        for col in range(model.columnCount()):
            title = model.headerData(col, Qt.Horizontal, Qt.DisplayRole)
            if title:
                col_combo.addItem(title, col)

        add_layout.addWidget(col_combo)
        
        order_combo = QComboBox()
        order_combo.addItem("По возрастанию", Qt.AscendingOrder)
        order_combo.addItem("По убыванию", Qt.DescendingOrder)
        add_layout.addWidget(order_combo)
        
        add_btn = QPushButton("Добавить")
        add_layout.addWidget(add_btn)
        layout.addLayout(add_layout)
        
        # Кнопки OK/Cancel
        btn_layout = QHBoxLayout()
        ok_btn = QPushButton("OK")
        cancel_btn = QPushButton("Отмена")
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)
        
        specs = []  # список кортежей (column_index, order)
        
        def add_spec():
            col_idx = col_combo.currentData()
            order = order_combo.currentData()
            specs.append((col_idx, order))
            col_title = col_combo.currentText()
            order_text = "▲" if order == Qt.AscendingOrder else "▼"
            list_widget.addItem(f"{col_title} {order_text}")
            col_combo.removeItem(col_combo.currentIndex())
            if col_combo.count() == 0:
                add_btn.setEnabled(False)
        
        add_btn.clicked.connect(add_spec)
        
        def accept():
            if specs:
                # # Вызываем метод мульти-сортировки у таблицы (или у страницы)
                # if hasattr(self.parent(), 'set_multi_sorting'):
                #     self.parent().set_multi_sorting(specs)
                # Вызываем метод мульти-сортировки у таблицы (или у страницы)
                # if hasattr(self, 'set_multi_sorting'):
                #     self.set_multi_sorting(specs)
                parent = self.parent()
                while parent and not hasattr(parent, 'set_multi_sorting'):
                    parent = parent.parent()
                if parent and hasattr(parent, 'set_multi_sorting'):
                    parent.set_multi_sorting(specs)

            dialog.accept()
        
        ok_btn.clicked.connect(accept)
        cancel_btn.clicked.connect(dialog.reject)
        
        dialog.exec()

    @AppLogger.get_instance( 
        name = 'FilterHeaderView',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _request_advanced_filter(self, logical_index: int):
        """
        Открывает диалог расширенной фильтрации для столбца с поддержкой множественных условий.

        Диалог поддерживает:
            - несколько условий (AND/OR внутри столбца),
            - различные операторы (eq, like, between, in, is_null и т.д.),
            - выбор значений из списка уникальных (для оператора 'in').

        После подтверждения диалога испускается сигнал `filter_requested(logical_index, logic, conditions)`,
        где `conditions` – список словарей с ключами 'operator', 'value', 'value2'.

        **Алгоритм:**
            1. Получает уникальные значения для столбца (для оператора `in`) через callback
            `_get_unique_values_func`.
            2. Получает заголовок столбца из модели.
            3. **Ищет родительский виджет (страницу) с атрибутом `_column_filters`** и извлекает
            текущие условия фильтра для этого столбца (`logic` и `conditions`), чтобы
            предзаполнить диалог.
            4. Определяет тип данных столбца (через модель или по первой строке).
            5. Создаёт диалог `FilterColumnDialog` с переданными параметрами.
            6. При подтверждении испускает сигнал `filter_requested(logical_index, logic, conditions)`.


        Args:
            logical_index (int): Индекс столбца (видимый) в таблице.

        Returns:
            None
        """
        
        # Получаем уникальные значения для столбца (для оператора 'in')
        if self._get_unique_values_func:
            values = self._get_unique_values_func(logical_index)
        else:
            values = []

        # Получаем заголовок столбца для отображения в диалоге
        column_title = self.model().headerData(logical_index, Qt.Horizontal, Qt.DisplayRole)
        if not column_title:
            column_title = f"Столбец {logical_index}"

        # # Получаем текущий фильтр для этого столбца (если есть)
        # model = self.parent().model()
        # current_logic = None
        # current_conditions = []

        # if (
        #     hasattr(self.parent(), 'model')
        #     and hasattr(model, '_column_filters')
        #     and logical_index in model._column_filters
        # ):
        #     current_filter = model._column_filters[logical_index]
        #     current_logic = current_filter.get('logic')
        #     current_conditions = current_filter.get('conditions', [])

        # Получаем текущий фильтр для этого столбца (если есть)
        # В текущей архитектуре фильтры хранятся в FilterMixin страницы, а не в модели.
        # Чтобы не ломать функциональность, пока оставляем пустые значения.
        current_logic = None
        current_conditions = []

        parent = self.parent()

        while parent:
            if hasattr(parent, '_column_filters'):
                col_filters = getattr(parent, '_column_filters', {})
                if logical_index in col_filters:
                    filter_def = col_filters[logical_index]
                    current_logic = filter_def.get('logic')
                    current_conditions = filter_def.get('conditions', [])
                break
            parent = parent.parent()

        # Определяем тип данных столбца
        column_type = str
        if hasattr(self.model(), 'column_type'):
            column_type = self.model().column_type(logical_index)

        elif self.model().rowCount() > 0:
            idx = self.model().index(0, logical_index)
            data = self.model().data(idx, Qt.EditRole)
            if data is not None:
                column_type = type(data)

        # Создаём диалог фильтрации (новый, с поддержкой множественных условий)
        # from .filter_column import FilterColumnDialog
        dialog = FilterColumnDialog(
            column_title=column_title,
            column_type=column_type,
            current_logic=current_logic,
            current_conditions=current_conditions,
            unique_values=values,
            parent=self
        )

        if dialog.exec() == QDialog.Accepted:
            logic, conditions = dialog.get_filter()
            # Испускаем сигнал с логикой и списком условий
            self.filter_requested.emit(logical_index, logic, conditions)

    # @AppLogger.get_instance( 
    #     name = 'FilterHeaderView',
    #     enable_file_logging = 'system',
    #    use_name_in_filename = False, # 'system',
    # ).log_execution_time(
    #     level = AppLogger._parse_log_level('DEBUG')
    # )
    # def _show_values_dialog(self, logical_index):
    #     """
    #     Открывает диалог выбора значений для фильтрации в таблице.

    #     :param logical_index: индекс столбца, для которого необходимо отобразить фильтр
    #     :type logical_index: int
    #     """
    #     if not self._get_unique_values_func:
    #         return
        
    #     values = self._get_unique_values_func(logical_index)

    #     dialog = QDialog(self)
    #     dialog.setWindowTitle("Выбор значений")

    #     layout = QVBoxLayout(dialog)

    #     list_widget = QListWidget()
    #     list_widget.setSelectionMode(QListWidget.SelectionMode.MultiSelection)

    #     for val in values:
    #         item = QListWidgetItem(str(val))
    #         item.setData(Qt.UserRole, val)
    #         list_widget.addItem(item)
            
    #     layout.addWidget(list_widget)

    #     btn_layout = QHBoxLayout()

    #     ok_btn = QPushButton("OK")
    #     ok_btn.clicked.connect(dialog.accept)
    #     btn_layout.addWidget(ok_btn)

    #     cancel_btn = QPushButton("Отмена")
    #     cancel_btn.clicked.connect(dialog.reject)
    #     btn_layout.addWidget(cancel_btn)
       
        
    #     layout.addLayout(btn_layout)

    #     if dialog.exec() == QDialog.Accepted:
    #         selected = []
    #         for item in list_widget.selectedItems():
    #             selected.append(item.data(Qt.UserRole))
                
    #         self.filter_requested.emit(logical_index, 'in', selected, None)

    # def _populate_values_menu(self, values_menu, logical_index):
    #     """Заполняет подменю уникальными значениями с чекбоксами."""
    #     values_menu.clear()
    #     if not self._get_unique_values_func:
    #         return
    #     values = self._get_unique_values_func(logical_index)
    #     # Создаём QAction для каждого значения
    #     for val in values:
    #         action = QAction(str(val), values_menu)
    #         action.setCheckable(True)
    #         # Сохраняем значение как data
    #         action.setData(val)
    #         values_menu.addAction(action)
    #     # Добавляем кнопки OK/Cancel или применяем при закрытии
    #     # Проще: при выборе элемента применяем фильтр сразу, но это неудобно для множественного выбора.
    #     # Лучше добавить кнопку "Применить" и собирать выбранные значения.
    #     # Для простоты пока сделаем, что выбор элемента сразу отправляет фильтр с этим одним значением.
    #     # Позже можно заменить на диалог.
    #     # Но для полноты реализуем диалог.
    #     # Вместо подменю лучше открыть диалог.
    #     # Переделаем: вместо подменю будем открывать диалог.
    #     # Пока просто вызовем диалог.

    # def _request_filter_values(self, logical_index):
    #     """Открывает диалог выбора значений."""
    #     if not self._get_unique_values_func:
    #         return
    #     values = self._get_unique_values_func(logical_index)
    #     dialog = FilterValuesDialog(self, values)
    #     if dialog.exec() == QDialog.Accepted:
    #         selected = dialog.get_selected_values()
    #         self.filter_requested.emit(logical_index, 'in', selected)

    # @AppLogger.get_instance( 
    #     name = 'FilterHeaderView',
    #     enable_file_logging = 'system',
    #    use_name_in_filename = False, # 'system',
    # ).log_execution_time(
    #     level = AppLogger._parse_log_level('DEBUG')
    # )
    # def _request_filter(self, logical_index):
    #     """Запрашивает ввод значения фильтра."""
    #     # Здесь можно открыть диалог, но для простоты используем input dialog
    #     value, ok = QInputDialog.getText(self, "Фильтр", f"Введите значение для фильтрации (столбец {logical_index}):")
    #     if ok and value:
    #         self.filter_requested.emit(logical_index, 'contains', value)

    # def _clear_filter(self, logical_index):
    #     """Сброс фильтра для колонки."""
    #     self.filter_requested.emit(logical_index, 'clear', None)


class FilterTableView(QTableView):
    """
    Таблица, использующая FilterHeaderView в качестве горизонтального заголовка.

    Автоматически создаёт и устанавливает FilterHeaderView при инициализации.
    Подключает сигнал `filter_requested` заголовка к методу `on_filter_requested`
    (который может быть переопределён в наследнике или связан с моделью/контроллером).

    Таблица поддерживает:
        - Сортировку (setSortingEnabled(True) устанавливается автоматически).
        - Фильтрацию через контекстное меню заголовка.

    Для работы фильтрации необходимо:
        1. Установить модель данных (например, PaginatedTableModel).
        2. Переопределить `on_filter_requested` или подключиться к сигналу заголовка
           напрямую через `self.horizontalHeader().filter_requested.connect(...)`.

    Методы:
        on_filter_requested(column, operator, value, value2=None)
            Обработчик сигнала фильтрации – по умолчанию ничего не делает.
            Должен быть переопределён в наследнике.

        has_active_fuzzy_filter() -> bool
            Проверяет, есть ли активный fuzzy-фильтр у родительской страницы
            (идёт вверх по иерархии виджетов, ищет метод has_active_fuzzy_filter).

    Параметры:
        parent (QWidget, optional): Родительский виджет. По умолчанию None.

    Пример:
        >>> table = FilterTableView()
        >>> model = PaginatedTableModel(columns)
        >>> table.setModel(model)
        >>> table.on_filter_requested = my_filter_handler
    """

    @AppLogger.get_instance( 
        name = 'FilterTableView',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setSortingEnabled(True)

        header = FilterHeaderView(Qt.Orientation.Horizontal, self)

        self.setHorizontalHeader(header)

        header.filter_requested.connect(self.on_filter_requested)

        # self.horizontalHeader().setVisible(True)

    # @AppLogger.get_instance( 
    #     name = 'FilterTableView',
    #     enable_file_logging = 'system',
    #    use_name_in_filename = False, # 'system',
    # ).log_execution_time(
    #     level = AppLogger._parse_log_level('DEBUG')
    # )
    # def showEvent(self, event):
    #     """При каждом отображении таблицы принудительно показываем заголовок."""
    #     super().showEvent(event)
    #     self.horizontalHeader().setVisible(True)

    @AppLogger.get_instance( 
        name = 'FilterTableView',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def on_filter_requested(self, column, operator, value, value2=None):
        """
        Обрабатывает сигнал фильтрации.
        Должен быть переопределён или связан с моделью.
        """
        # В базовом классе просто передаём сигнал дальше
        pass

    @AppLogger.get_instance( 
        name = 'FilterTableView',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def has_active_fuzzy_filter(self) -> bool:
        """Проверяет, есть ли активный fuzzy-фильтр у страницы (родительского виджета)."""
        parent = self.parent()
        while parent:
            if hasattr(parent, 'has_active_fuzzy_filter'):
                return parent.has_active_fuzzy_filter()
            parent = parent.parent()
        return False

    # ------------------------------------------------------------------
    # Новые методы для точечного обновления (вызываются из делегатов)
    # ------------------------------------------------------------------

    @Slot(QModelIndex, QModelIndex)
    def update_range(self, top_left: QModelIndex, bottom_right: QModelIndex) -> None:
        """
        Обновляет прямоугольную область ячеек от top_left до bottom_right.

        **Назначение:**
            Позволяет перерисовать только необходимые ячейки после асинхронной загрузки,
            не затрагивая всю таблицу. Эффективно при обновлении миниатюр в фото-столбце.

        Args:
            top_left (QModelIndex): Индекс верхней левой ячейки диапазона.
            bottom_right (QModelIndex): Индекс нижней правой ячейки диапазона.

        Returns:
            None

        Note:
            Если любой из индексов невалиден, метод ничего не делает.
            Вычисляет объединённый прямоугольник видимых ячеек и обновляет viewport.

        **Примечание:**
            Если индексы невалидны, метод ничего не делает.
            Вычисляет объединённый прямоугольник видимых ячеек и обновляет viewport.
        """
        if not top_left.isValid() or not bottom_right.isValid():
            return

        # Получаем прямоугольники обеих ячеек в координатах viewport
        rect_top = self.visualRect(top_left)
        rect_bottom = self.visualRect(bottom_right)

        # Объединяем в один прямоугольник, покрывающий весь диапазон
        update_rect = rect_top.united(rect_bottom)

        # Обновляем только эту область
        self.viewport().update(update_rect)

    @Slot(int)
    def update_row(self, row: int) -> None:
        """
        Обновляет всю строку таблицы по её индексу.

        **Назначение:**
            Удобная обёртка над `update_range` для обновления целой строки.
            Используется в `ImageThumbnailDelegate` после загрузки миниатюры,
            чтобы перерисовать строку с новым размером и изображением.

        Args:
            row (int): Индекс строки (в модели, установленной в таблице).

        Returns:
            None

        Note:
            Если строка с таким индексом отсутствует, метод ничего не делает.

        **Примечание:**
            Если строка с таким индексом отсутствует, метод ничего не делает.
        """
        
        model = self.model()
        if model is None:
            return

        # Проверяем, что строка существует
        if row < 0 or row >= model.rowCount():
            return

        top_left = model.index(row, 0)
        bottom_right = model.index(row, model.columnCount() - 1)
        self.update_range(top_left, bottom_right)

    @Slot(int)
    def refreshRow(self, row: int) -> None:
        """
        Пересчитывает высоту указанной строки и перерисовывает её.

        **Назначение:**
            Удобный метод для вызова из делегатов после асинхронной загрузки
            миниатюр. Объединяет resizeRowToContents и update_row.

        **Параметры:**
            row (int): Индекс строки.

        **Возвращает:**
            None
        """
        self.resizeRowToContents(row)
        self.update_row(row)

    @Slot(int)
    def refreshRow(self, row: int) -> None:
        """
        Пересчитывает высоту указанной строки и перерисовывает её.

        **Назначение:**
            Удобный метод для вызова из делегатов после асинхронной загрузки
            миниатюр. Объединяет resizeRowToContents и update_row.

        **Параметры:**
            row (int): Индекс строки.

        **Возвращает:**
            None
        """
        self.resizeRowToContents(row)
        self.update_row(row)