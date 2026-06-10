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

from app.utils.logger.logger import AppLogger

from interfaces.gui.gui_window.widgets.filter_column import FilterBar
from interfaces.gui.gui_window.widgets.filter_table_view import FilterTableView

from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QVBoxLayout, 
    QPushButton, QLineEdit, 
    QComboBox,
)

from PySide6.QtCore import (
    Qt, 
    # Signal
)

class ToolbarComboMixin:
    """
    Миксин для добавления значений в выпадающий списк
    """

    @AppLogger.get_instance(
        name='ToolbarComboMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time( level=AppLogger._parse_log_level('DEBUG') )
    def _rebuild_combo(self, combo, actions_dict:dict):
        """
        Заполняет combo  на основе словаря действий.
        Порядок пунктов определяется порядком ключей в словаре (Python 3.7+ сохраняет порядок вставки).
        """

        combo.blockSignals(True)
        combo.clear()

        any_enabled= False
        index = -1
        for k, v in actions_dict.items():
            index +=1

            actions_dict[k]["index"] = index
            
            text = v.get("text", None)
            separator = v.get("separator", False) # Разделитель

            func = v.get("func", None)
            args = v.get("args", None)
            kwargs = v.get("kwargs", None)

            visible = v.get("visible", True)
            enabled = v.get("enabled", True) and (func is not None)

            userData = {
                "name_sysem": k,
                "func": func,
                "args": args,
                "kwargs": kwargs
            }

            # Пропускаем, если явно указано visible=False
            if visible is False:
                continue

                  
            # Разделитель
            if separator:
                combo.insertSeparator(combo.count())
                continue  
            
            if text is None:
                continue

            combo.addItem(text , userData)

            combo.model().item(index).setEnabled(enabled)

            any_enabled = any_enabled or enabled

        combo.setCurrentIndex(0)
        combo.blockSignals(False)

        combo.setVisible(any_enabled)  # если ни один пункт не активен, скрываем комбобокс

    @AppLogger.get_instance(
        name='ToolbarComboMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time( level=AppLogger._parse_log_level('DEBUG') )
    def _run_selected_combo_action(self,combo):
        # Получить данные функции из текущего выбранного пункта и выполнить функцию
        cfg = combo.currentData()
        return self._run_func_dict(cfg)
  
    @AppLogger.get_instance(
        name='ToolbarComboMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time( level=AppLogger._parse_log_level('DEBUG') )
    def _set_combo_key_by_index(self,actions_dict:dict, index):
        # Получить ключ по внутренему индексу
        key = None
        for k, v in actions_dict.items:
            index_actions_dict = v.get("index", None)   
            if index_actions_dict == index:
                key = k  
                break
        return key
    
    @AppLogger.get_instance(
        name='ToolbarComboMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time( level=AppLogger._parse_log_level('DEBUG') )
    def _set_combo_config_by_key(self,actions_dict:dict, key):
        # Получить данные функции по ключу и выполнить функцию
        if not key:
            return False , None 
        cfg = actions_dict[key]
        return self._run_func_dict(cfg)

    @AppLogger.get_instance(
        name='ToolbarComboMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time( level=AppLogger._parse_log_level('DEBUG') )
    def _run_func_dict(self,cfg_func:dict):
        # выполнить функцию по данным
        func = cfg_func.get("func", None)
        if func is not None:
            return True, func(
                *cfg_func.get("args", ()), 
                **cfg_func.get("kwargs", {})
            )
        return False, None
    
class UIMixin(ToolbarComboMixin):
    """
    Миксин для построения пользовательского интерфейса страницы списка.

    Создаёт:
        - Верхнюю панель с кнопками и выпадающими списками (`_setup_top_panel`).
        - Таблицу (`FilterTableView`) с поддержкой фильтрации и сортировки (`_create_table`).
        - Панель активных фильтров (`FilterBar`) (`_create_filter_bar`).
        - Делегаты для столбцов (`_setup_delegates`).

    Требования к классу-наследнику:
        - Должен иметь атрибут `main_layout` (QVBoxLayout), созданный до вызова `setup_ui()`.
        - Должен реализовывать метод `toggle_edit_mode(enable: bool)` – вызывается при переключении режима.
        - Должен реализовывать методы `add_row()`, `delete_selected_rows()`, `cancel_selected_rows_changes()`,
          `save_all_changes()`, `reload_data()`, `get_current_selected_dto()`, `set_global_search(text)`.
        - Должен иметь сигналы `add_requested`, `edit_requested`, `delete_requested`, `action_requested`.

    Атрибуты, создаваемые миксином (при условии, что их имена присутствуют в `self._show_controls`):
        edit_mode_btn (QPushButton): Кнопка переключения режима редактирования.
        action_combo (QComboBox): Выпадающий список действий (обычный режим).
        inline_action_combo (QComboBox): Выпадающий список inline-действий (режим редактирования).
        save_changes_btn (QPushButton): Кнопка сохранения всех изменений.
        search_edit (QLineEdit): Поле глобального поиска.
        table_view (FilterTableView): Таблица.
        filter_bar (FilterBar): Панель активных фильтров.

        **Важно:** Если соответствующий элемент не запрошен через `show_controls`, соответствующий
        атрибут может отсутствовать. Перед доступом к нему следует проверять `hasattr`.
    """

    # ------------------------------------------------------------------
    # Ленивая инициализация атрибутов (без __init__)
    # ------------------------------------------------------------------

    @property
    def logger(self) -> AppLogger:
        try:
            return self._logger
        except AttributeError as e:
            self._logger = AppLogger.get_instance(
                name='gui.UIMixin',
                enable_file_logging = 'user',
                use_name_in_filename = False, # 'system'
            )

        return self._logger

    @logger.setter
    def logger(self, value):
        self._logger = value


    @property
    def _normal_actions(self) -> dict:
        try:
            return self.__normal_actions
        except AttributeError as e:
            self._create_normal_actions()

        return self.__normal_actions

    @_normal_actions.setter
    def _normal_actions(self, value:dict):
        self.__normal_actions = value

    @AppLogger.get_instance(
        name='UIMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def _create_normal_actions(self):
        # Действия для обычного режима (action_combo)
        self.__normal_actions =  {
            "item_0": {"text": "▼ Действия", "enabled": False},
            # "add": {"text": "Добавить", "func": lambda: self.add_requested.emit, "args": (), "kwargs": {}},
            "add": {"text": "Добавить", "func": self.add_row, "args": (), "kwargs": {}},
            "edit": {"text": "Редактировать", "func": self._on_edit_clicked, "args": (), "kwargs": {}},
            # "delete": {"text": "Удалить", "func": self.delete_selected_rows, "args": (), "kwargs": {}},
            "delete": {"text": "Удалить", "func": self.delete_selected_rows, "args": (), "kwargs": {}},
            "separator_1": {"separator": True},
            "refresh": {"text": "Обновить", "func": self.reload_data, "args": (), "kwargs": {}}
        }

    @property
    def _inline_actions(self) -> dict:
        try:
            return self.__inline_actions
        except AttributeError as e:
            self._create_inline_actions()

        return self.__inline_actions

    @_inline_actions.setter
    def _inline_actionss(self, value:dict):
        self.__inline_actions = value

    @AppLogger.get_instance(
        name='UIMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def _create_inline_actions(self):
        # Действия для режима редактирования (inline_action_combo)
        self.__inline_actions = {
            "item_0": {"text": "▼ Действия со строками", "enabled": False},
            "add_row": {"text": "Добавить строку", "func": self.add_row, "args": (), "kwargs": {}},
            "delete_row": {"text": "Удалить строку", "func": self.delete_selected_rows, "args": (), "kwargs": {}},
            # "delete_row": {"text": "Удалить строку", "func": self.delete_selected_rows, "args": (), "kwargs": {}},
            "cancel_row": {"text": "Отменить изменения строки", "func": self.cancel_selected_rows_changes, "args": (), "kwargs": {}},
            "separator_1": {"text": None, "separator": True},
            "cancel_all": {
                "text": "Отменить все изменения", 
                "func": self._discard_all_changes , 
                "args": (), 
                "kwargs": {},
            }
        }

    @AppLogger.get_instance(
        name='UIMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def setup_ui(self):
        """
        Главный метод построения интерфейса.

        Выполняет:
            1. Создаёт основной вертикальный layout (self.main_layout).
            2. Вызывает `_setup_top_panel()` – создаёт верхнюю панель.
            3. Вызывает `_create_table()` – создаёт таблицу.
            4. Добавляет таблицу в main_layout.
            5. Вызывает `_create_filter_bar()` – создаёт фильтр-бар.
            6. Вставляет фильтр-бар перед таблицей.
            7. Вызывает `_setup_delegates()` – устанавливает делегаты (переопределяется в наследнике).

        Примечания:
            - Предполагается, что self.main_layout (QVBoxLayout) уже создан.
            - После вызова метода таблица и панель фильтров готовы к использованию.
        Returns:
            None        
        """

        self.main_layout = QVBoxLayout(self)

        # self._create_top_panel()  # ← старый метод, создающий все элементы безусловно
        self._setup_top_panel()  # ← условное создание элементов

        self._create_table()
        self.main_layout.addWidget(self.table_view)
        self._create_filter_bar()

        self._create_model()  # создаёт self.source_model (PaginatedTableModel)
        
        # Вставляем фильтр-бар перед таблицей
        idx = self.main_layout.indexOf(self.table_view)
        if idx >= 0:
            self.main_layout.insertWidget(idx, self.filter_bar)

        self._setup_delegates()

    @AppLogger.get_instance(
        name='UIMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _setup_top_panel(self):
        """
        Создаёт верхнюю панель с элементами управления.

        **Условное создание элементов:**
            Элементы отображаются только если их имена присутствуют в списке `self._show_controls`.
            Допустимые имена:
                'edit_mode_btn'       – кнопка переключения режима редактирования,
                'action_combo'        – выпадающий список действий в обычном режиме,
                'inline_action_combo' – выпадающий список inline-действий в режиме редактирования,
                'save_btn'            – кнопка сохранения изменений,
                'cancel_parent_btn'   – кнопка отмены правок строки,
                'action_btn'          – дополнительная кнопка действия,
                'search'              – поле глобального поиска.

        Если `self._show_controls` не задан или пуст, панель будет содержать только растяжку
        (то есть фактически не будет создана). Если `self._show_controls` содержит элементы,
        отсутствующие в списке, они игнорируются.

        **Примечание:** Этот метод заменил старый `_create_top_panel`, который создавал все элементы
        безусловно. Старый метод оставлен закомментированным для обратной совместимости.
        """

        show = set(getattr(self, '_show_controls', []))
        if show == set():
            return
        
        top_layout = QHBoxLayout()

        # ---- Кнопка переключения режима редактирования ----
        if 'edit_mode_btn' in show:
            self.edit_mode_btn = QPushButton("Режим редактирования")
            self.edit_mode_btn.setCheckable(True)
            self.edit_mode_btn.toggled.connect(self._on_edit_mode_toggled)
            top_layout.addWidget(self.edit_mode_btn)

        # ---- Выпадающий список действий (обычный режим) ----
        if 'action_combo' in show:
            self.action_combo = QComboBox()
            self._rebuild_combo_on_action_selected()
            self.action_combo.currentIndexChanged.connect(self._on_action_selected)
            top_layout.addWidget(self.action_combo)

        # ---- Выпадающий список inline-действий (режим редактирования) ----
        if 'inline_action_combo' in show:
            self.inline_action_combo = QComboBox()
            self._rebuild_combo_on_inline_action_selected()
            self.inline_action_combo.currentIndexChanged.connect(self._on_inline_action_selected)
            self.inline_action_combo.setVisible(False)
            top_layout.addWidget(self.inline_action_combo)

        # ---- Кнопка сохранения ----
        if 'save_btn' in show:
            self.save_changes_btn = QPushButton("Сохранить изменения")
            self.save_changes_btn.setEnabled(False)
            self.save_changes_btn.setVisible(False)
            self.save_changes_btn.clicked.connect(self.save_all_changes)
            top_layout.addWidget(self.save_changes_btn)

        # ---- Кнопка отмены правок строки ----
        if 'cancel_parent_btn' in show:
            self.cancel_parent_btn = QPushButton("Отменить правки строки")
            self.cancel_parent_btn.setVisible(False)
            self.cancel_parent_btn.clicked.connect(self.cancel_parent_changes_only)
            top_layout.addWidget(self.cancel_parent_btn)

        # ---- Дополнительная кнопка действия ----
        if 'action_btn' in show and getattr(self, 'action_button_text', None):
            self.action_btn = QPushButton(self.action_button_text)
            self.action_btn.clicked.connect(self._on_action_clicked)
            self.action_btn.setEnabled(False)
            top_layout.addWidget(self.action_btn)

        top_layout.addStretch()

        # ---- Поле поиска ----
        if 'search' in show:
            self.search_edit = QLineEdit()
            self.search_edit.setPlaceholderText("Поиск...")
            self.search_edit.textChanged.connect(self.set_global_search)
            top_layout.addWidget(self.search_edit)

        self.main_layout.addLayout(top_layout)

    @AppLogger.get_instance(
        name='UIMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
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

        Примечания:
            - Модель таблицы должна быть установлена отдельно (например, в наследнике).
            - Если в классе-наследнике есть метод `_on_sort_indicator_changed`,
            подключает сигнал sortIndicatorChanged заголовка к этому методу.

        Returns:
            Noneе.
        """

        # from interfaces.gui.gui_window.widgets.filter_table_view import FilterTableView
        self.table_view = FilterTableView()
        self.table_view.setSortingEnabled(True)
        self.table_view.setSelectionBehavior(self.table_view.SelectionBehavior.SelectRows)
        self.table_view.setSelectionMode(self.table_view.SelectionMode.SingleSelection)
        # self.table_view.setEditTriggers(self.table_view.NoEditTriggers)
        self.table_view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table_view.doubleClicked.connect(self._on_row_double_clicked)

        # # Подключаем сигнал сортировки, если метод-обработчик определён в классе-наследнике
        # # Обоснование: Мы подключаем сигнал sortIndicatorChanged заголовка таблицы к методу _on_sort_indicator_changed, который должен быть предоставлен одним из миксинов (например, FilterMixin). Проверка hasattr делает код устойчивым к отсутствию обработчика.
        # if hasattr(self, '_on_sort_indicator_changed'): # перенесли в FilterMixin
        #     header = self.table_view.horizontalHeader()
        #     header.sortIndicatorChanged.connect(self._on_sort_indicator_changed)

    @AppLogger.get_instance(
        name='UIMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _create_filter_bar(self):
        """
        Создаёт панель активных фильтров (FilterBar).

        Устанавливает:
            - self.filter_bar (FilterBar)
            - Панель изначально скрыта (setVisible(False))

        Вставка производится в self.main_layout перед self.table_view.
        Если self.table_view не найден, панель добавляется в конец.

        Returns:
            None
        """

        # from interfaces.gui.gui_window.widgets.filter_column import FilterBar
        self.filter_bar = FilterBar(self)
        self.filter_bar.setVisible(False)

    @AppLogger.get_instance(
        name='UIMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
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

        Returns:
            None
        """

        # Будет реализовано позже, аналогично DynamicListPage._setup_delegates
        pass



    @AppLogger.get_instance(
        name='UIMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def _rebuild_combo_on_action_selected(self):
        self._rebuild_combo(self.action_combo, self._normal_actions)
        
    @AppLogger.get_instance(
        name='UIMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _on_action_selected(self, index):
        """
        Обработчик выбора действия в обычном режиме (self.action_combo).

        Args:
            index (int): Индекс выбранного пункта.
                0 – заглушка
                1 → Добавить (испускает сигнал add_requested)
                2 → Редактировать (испускает edit_requested с текущим DTO)
                3 → Удалить (испускает delete_requested с текущим DTO)
                4 → Обновить (вызывает reload_data())

        После обработки сбрасывает индекс комбобокса на 0 (заглушку).

        Действия:
            1 -> испускает сигнал self.add_requested.emit()
            2 -> испускает self.edit_requested.emit(dto) с текущим выбранным DTO
            3 -> испускает self.delete_requested.emit(dto) с текущим выбранным DTO
            4 -> вызывает self.reload_data()

        Требования:
            - self.get_current_selected_dto() – возвращает DTO выбранной строки.
            - self.add_requested, self.edit_requested, self.delete_requested – сигналы.
            - self.reload_data() – метод перезагрузки данных.
        """

        self._run_selected_combo_action(self.action_combo)

        self.action_combo.blockSignals(True)
        self.action_combo.setCurrentIndex(0)
        self.action_combo.blockSignals(False)

        # if index == 1:   # Добавить
        #     self.add_requested.emit()

        # elif index == 2: # Редактировать
        #     dto = self.get_current_selected_dto()
        #     if dto:
        #         self.edit_requested.emit(dto)

        # elif index == 3: # Удалить
        #     dto = self.get_current_selected_dto()
        #     if dto:
        #         self.delete_requested.emit(dto)

        # elif index == 4: # Обновить
        #     self.reload_data()

        # self.action_combo.setCurrentIndex(0)

    def _on_edit_clicked(self):
        dto = self.get_current_selected_dto()
        if dto:
            self.edit_requested.emit(dto)
            
    # def _on_delete_clicked(self):
    #     if self.edit_mode:
    #         self.delete_selected_rows()
    #     else:
    #         dto = self.get_current_selected_dto()
    #         if dto:
    #             self.delete_requested.emit(dto)


    @AppLogger.get_instance(
        name='UIMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def _rebuild_combo_on_inline_action_selected(self):
        self._rebuild_combo(self.inline_action_combo, self._inline_actions)
           

    @AppLogger.get_instance(
        name='UIMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _on_inline_action_selected(self, index):
        """
        Обработчик выбора действия в режиме редактирования (self.inline_action_combo).

        Args:
            index (int): Индекс выбранного пункта.
                0 – заглушка
                1 → Добавить строку (вызывает add_row())
                2 → Удалить строку (вызывает delete_selected_rows())
                3 → Отменить изменения (вызывает cancel_selected_rows_changes())

        После обработки сбрасывает индекс комбобокса на 0 (заглушку).

        Действия:
            1 -> вызывает self.add_row()
            2 -> вызывает self.delete_selected_rows()
            3 -> вызывает self.cancel_selected_rows_changes()

        Требования:
            - self.add_row(), self.delete_selected_rows(), self.cancel_selected_rows_changes()
              должны быть реализованы в наследнике.
        """

        self._run_selected_combo_action(self.inline_action_combo)
        self.inline_action_combo.setCurrentIndex(0)

        # if index == 1:   # Добавить строку
        #     self.add_row()

        # elif index == 2: # Удалить строку
        #     self.delete_selected_rows()

        # elif index == 3: # Отменить изменения
        #     self.cancel_selected_rows_changes()

        # elif index == 4: # Отменить все изменения
        #     if hasattr(self, '_discard_all_changes'):
        #         self._discard_all_changes()
        #     else:
        #         self.logger.warning("Метод _discard_all_changes не реализован в классе-владельце")

        # self.inline_action_combo.setCurrentIndex(0)

    @AppLogger.get_instance(
        name='UIMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _on_action_clicked(self):
        """
        Обработчик нажатия дополнительной кнопки (self.action_btn).

        Испускает сигнал self.action_requested.emit(dto) с текущим DTO.

        Требования:
            - self.get_current_selected_dto() – возвращает DTO выбранной строки.
            - self.action_requested – сигнал.
        """

        dto = self.get_current_selected_dto()
        if dto:
            self.action_requested.emit(dto)

    @AppLogger.get_instance(
        name='UIMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _on_row_double_clicked(self, index):
        """
        Обработчик двойного клика по строке таблицы.

        Если режим редактирования выключен, испускает сигнал action_requested
        с DTO строки, по которой был произведён двойной клик.

        Args:
            index (QModelIndex): Индекс ячейки, по которой кликнули.

        Returns:
            None
        """

        self.logger.debug(
            f"_on_row_double_clicked: "
            f"index={index} "
            f"self.edit_mode={self.edit_mode} "
        )
        if not self.edit_mode:
            dto = self.get_current_selected_dto()
            if dto:

                self.logger.debug(
                    f"_on_row_double_clicked: "
                    f"dto is None={dto is None} "
                )
                self.action_requested.emit(dto)
    
    @AppLogger.get_instance(
        name='UIMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _update_ui_for_edit_mode(self, edit_mode: bool):
        """
        Обновляет видимость элементов UI в зависимости от режима редактирования.

        Действия:
            - Скрывает/показывает self.action_combo.
            - Показывает/скрывает self.inline_action_combo.
            - Показывает/скрывает self.save_changes_btn.
            - Показывает/скрывает self.cancel_parent_btn.
            - Устанавливает режим редактирования таблицы (DoubleClicked / NoEditTriggers).
            - Если есть self.action_btn – включает/отключает его (в обычном режиме активна, в режиме редактирования – нет).

        Примечание:
            - Этот метод вызывается из `EditModeMixin._set_edit_mode()`.
            - В наследниках может быть переопределён для дополнительной кастомизации.

        Args:
            edit_mode (bool): True – режим редактирования включён, False – выключен.
        """
        # self.table_view.setUpdatesEnabled(False)
        # try:
        
        # описание в def _create_top_panel
        
        if hasattr(self, 'action_combo') and self.action_combo:
            self.action_combo.setVisible(not edit_mode)

        if hasattr(self, 'inline_action_combo') and self.inline_action_combo:
            self.inline_action_combo.setVisible(edit_mode)

        if hasattr(self, 'save_changes_btn') and self.save_changes_btn:
            self.save_changes_btn.setVisible(edit_mode)

        if hasattr(self, 'cancel_parent_btn') and self.cancel_parent_btn:
            self.cancel_parent_btn.setVisible(edit_mode) 

        if hasattr(self, 'action_btn') and self.action_btn:
            self.action_btn.setEnabled(not edit_mode)

        # self.table_view.setEditTriggers(self.table_view.DoubleClicked if edit_mode else self.table_view.NoEditTriggers)
        self.table_view.setEditTriggers(
            QAbstractItemView.DoubleClicked if edit_mode else QAbstractItemView.NoEditTriggers
        )
        # finally:
        # self.table_view.setUpdatesEnabled(True)
