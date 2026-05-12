# interfaces/gui/gui_window/pages/dynamic_list_page.py
"""
Модуль универсальной страницы списка (DynamicListPage).

Предоставляет компонент для отображения табличных данных с поддержкой:
    - Обычного режима (только просмотр, с переходом по двойному клику).
    - Режима редактирования (inline-редактирование, чекбоксы, массовые операции).
    - Фильтрации через заголовки столбцов (AdvancedFilterMixin).
    - Программного управления через интерфейс IDynamicListController.

Экспортируемые классы:
    - DynamicListPage: Основная страница списка.
    - Вспомогательные миксины (не предназначены для прямого использования).
"""

from functools import wraps

from typing import (
    List,
    Optional, 
    Callable, 
    Any, 
    Set, 
    Dict,
    Union,
    get_args,
    get_origin
)

import datetime 
from copy import deepcopy

from app.utils.logger.logger import AppLogger

from interfaces.gui.gui_window.controllers.list_controller import IDynamicListController
from interfaces.gui.gui_window.pages.base_page import BasePage

from interfaces.gui.gui_window.utils.gui_helpers import add_copy_paste_to_table

from interfaces.gui.gui_window.widgets.dynamic_table_model import DynamicTableModel
from interfaces.gui.gui_window.widgets.filter_column import FilterBar
from interfaces.gui.gui_window.widgets.filter_table_view import FilterTableView
from interfaces.gui.gui_window.widgets.advanced_filter_proxy_model import AdvancedFilterProxyModel

from interfaces.gui.gui_window.widgets.delegate.type_delegate import (
    CompleterStringDelegate,
    DatePickerDelegate,
    # DateStringDelegate,
    StringDelegate,
    # DateDelegate,
    TextPopupDelegate,
    # TimeDelegate,
    BoolDelegate,
    ComboBoxDelegate,
    TimePickerDelegate,
    # TimeStringDelegate,
)

# from interfaces.gui.gui_window.widgets.delegate.str_delegate import StringDelegate
# from interfaces.gui.gui_window.widgets.delegate.date_delegate import DateDelegate
# from interfaces.gui.gui_window.widgets.delegate.time_delegate import TimeDelegate
# from interfaces.gui.gui_window.widgets.delegate.bool_delegate import BoolDelegate
# from interfaces.gui.gui_window.widgets.delegate.combo_box_delegate import ComboBoxDelegate

from PySide6.QtWidgets import (
    # QWidget, 
    QComboBox, QVBoxLayout, 
    QHBoxLayout,  QPushButton, 
    QLineEdit, QHeaderView, 
    QMessageBox, QAbstractItemView,
    # QTableView, 
)
from PySide6.QtCore import (
    Qt, Signal, Slot, 
    # QModelIndex, QTimer
)
from PySide6.QtGui import QColor


# def preserve_selection(func):
#     """
#     Декоратор для методов, которые могут изменить данные или режим редактирования.
#     Сохраняет текущую строку перед выполнением и восстанавливает её после. 
#     (работает от DynamicListPage)
#     """
#     @wraps(func)
#     def wrapper(self, *args, **kwargs):
#         self._store_current_row()
#         try:
#             result = func(self, *args, **kwargs)
#         except Exception as e:
#             self.logger.exception(f"Ошибка в {func.__name__}: {e}")
#             raise 
#         finally:
#             self._restore_current_row()
#         return result
    
#     return wrapper


class _PreserveSelectionStorage:
    """
    Хранилище сохранённых строк для декоратора `preserve_selection`.

    Использует слабосвязанный словарь: ключ – строка, значение – индекс строки.
    Позволяет сохранять выделение до и после выполнения методов, которые могут перестроить модель.

    Атрибуты класса:
        _data (dict): Словарь {key: row}.
    """

    _data = {}

    @classmethod
    def make_key(
        cls, 
        obj, 
        func_name: str, 
        label: Optional[str] = None
    ) -> str:
        """
        Формирует ключ для хранения.

        Параметры:
            obj (object): Экземпляр, для которого сохраняется строка.
            func_name (str): Имя метода, обёрнутого декоратором.
            label (Optional[str]): Произвольная метка, используемая как ключ (приоритет).

        Возвращает:
            str: Ключ для словаря.
        """

        if label:
            return label
        
        class_name = obj.__class__.__name__
        
        return f"{class_name}.{func_name}"
    
    @classmethod
    def save(cls, key: str, row: int) -> bool:
        """
        Сохраняет строку, если для данного ключа ещё нет значения.

        Параметры:
            key (str): Ключ.
            row (int): Индекс строки.

        Возвращает:
            bool: True, если сохранение выполнено (значения не было), иначе False.
        """
        
        if key not in cls._data:
            cls._data[key] = row

            return True
        
        return False

    @classmethod
    def get(cls, key: str) -> int:
        """Возвращает сохранённый индекс строки или -1."""

        return cls._data.get(key, -1)

    @classmethod
    def clear(cls, key: str):
        """Удаляет ключ из хранилища."""

        cls._data.pop(key, None)

    # @classmethod
    # def save(cls, obj, func_name, row):
    #     key = (id(obj), func_name)
    #     cls._data[key] = row

    # @classmethod
    # def get(cls, obj, func_name):
    #     key = (id(obj), func_name)
    #     return cls._data.get(key, -1)

    # @classmethod
    # def clear(cls, obj, func_name):
    #     key = (id(obj), func_name)
    #     cls._data.pop(key, None)


def preserve_selection(
    store_method_name='_store_current_row', 
    restore_method_name='_restore_current_row',
    label: Optional[str] = None
) -> Callable:
    """
    Декоратор для сохранения и восстановления текущей строки в таблице.

    Используется для методов, которые могут перестроить модель (например, `_load_data`, `_on_edit_mode_toggled`).
    Декоратор сохраняет текущую строку (`store_method_name`), выполняет декорируемый метод,
    затем восстанавливает строку (`restore_method_name`). Если методы не найдены, декоратор не влияет на работу.

    Args:
        store_method_name (str): Имя метода, возвращающего индекс текущей строки
            в прокси-модели (по умолчанию '_store_current_row').
        restore_method_name (str): Имя метода, принимающего индекс строки
            (в прокси-модели) и восстанавливающего выделение.
        label (Optional[str]): Если указана, используется как ключ в хранилище
            вместо автоматического "ClassName.method_name".

    Returns:
        Callable: Декоратор функции.

    Пример:
        >>> @preserve_selection()
        ... def _load_data(self):
        ...     # перестраивает модель
    """

    def decorator(func):
        """
        Декоратор для сохранения и восстановления текущей строки в таблице.

        :param store_method_name: имя метода, возвращающего индекс строки (по умолчанию '_store_current_row')
        :param restore_method_name: имя метода, принимающего индекс строки и восстанавливающего выделение
        :param label: произвольная строка – если указана, используется как ключ в хранилище вместо автоматического "ClassName.method_name"

        Декоратор сохраняет текущую строку перед выполнением функции, а затем восстанавливает её после выполнения.
        Если методы не найдены, декоратор просто выполняет функцию без сохранения.
        """

        @wraps(func)
        def wrapper(self, *args, **kwargs):
            """
            Декоратор для сохранения и восстановления текущей строки в таблице.

            :param func: функция, для которой сохраняется и восстанавливается строка
            :return: результат выполнения функции func
            :rtype: Any

            Декоратор сохраняет текущую строку перед выполнением функции, а затем восстанавливает её после выполнения.
            Если методы не найдены, декоратор просто выполняет функцию без сохранения.
            """

            store = getattr(self, store_method_name, None)
            restore = getattr(self, restore_method_name, None)

            if store is None or restore is None:
                # Если методы не найдены, просто выполняем функцию без сохранения
                return func(self, *args, **kwargs)

            # Формируем ключ
            key = _PreserveSelectionStorage.make_key(self, func.__name__, label)

            # Сохраняем строку только если ещё не сохранена для этого ключа
            saved_row = store()
            is_new = _PreserveSelectionStorage.save(key, saved_row)

            try:
                result = func(self, *args, **kwargs)
            finally:
                # Восстанавливаем строку только если мы её сохранили (is_new)
                if is_new:
                    row_to_restore = _PreserveSelectionStorage.get(key)

                    if row_to_restore != -1:
                        restore(row_to_restore)
                        
                    _PreserveSelectionStorage.clear(key)
            return result
            
        return wrapper
    
    return decorator



class AdvancedFilterMixin:
    """
    Миксин для добавления строки активных фильтров (чипов) и связи с прокси-моделью.

    Требует наличия в классе-наследнике:
        - self.proxy_model (AdvancedFilterProxyModel)
        - self.main_layout (QVBoxLayout)
        - self.table_view (QTableView)

    Предоставляет методы для обновления полосы фильтров и обработки сигналов от фильтров.
    """

    @AppLogger.get_instance(
        name = 'AdvancedFilterMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _on_filter_condition_removed(self, column: int, condition_index: int):
        """
        Обработчик удаления конкретного условия из составного фильтра.

        Параметры:
            column (int): Номер столбца.
            condition_index (int): Индекс условия в списке условий.
        """
        
        self.proxy_model.remove_condition(column, condition_index)

    @AppLogger.get_instance(
        name = 'AdvancedFilterMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _setup_filter_bar(self):
        """
        Создаёт и размещает FilterBar между топ-панелью и таблицей.

        Подключает сигналы прокси-модели (filtersChanged) и сигналы самой панели
        (filter_removed, all_filters_cleared, filter_edit_requested, filter_condition_removed).
        """

        if not hasattr(self, 'filter_bar'):
            self.filter_bar = FilterBar(self)
            # Вставляем после топ-панели, но перед таблицей
            # Находим индекс таблицы в main_layout
            idx = self.main_layout.indexOf(self.table_view)
            if idx >= 0:
                self.main_layout.insertWidget(idx, self.filter_bar)
            else:
                self.main_layout.addWidget(self.filter_bar)

            # Подключаем сигналы прокси-модели
            self.proxy_model.filtersChanged.connect(self._refresh_filter_bar)

            # Сигналы от строки фильтров
            self.filter_bar.filter_removed.connect(self._on_filter_removed)
            self.filter_bar.all_filters_cleared.connect(self._on_all_filters_cleared)
            self.filter_bar.filter_edit_requested.connect(self._on_filter_edit_requested)

            # Для множественных условий (если реализовано)
            if hasattr(self.filter_bar, 'filter_condition_removed'):
                self.filter_bar.filter_condition_removed.connect(self._on_filter_condition_removed)

    @AppLogger.get_instance(
        name = 'AdvancedFilterMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _refresh_filter_bar(self):
        """Обновляет строку фильтров на основе текущих фильтров в прокси-модели."""
        
        if not hasattr(self, 'filter_bar'):
            return
        
        filters = self.proxy_model.get_active_filters()
        
        # Получаем заголовки столбцов
        column_titles = {}
        for col in filters.keys():
            title = self.proxy_model.headerData(col, Qt.Horizontal, Qt.DisplayRole)
            column_titles[col] = title
        
        self.filter_bar.update_filters(filters, column_titles)

    @AppLogger.get_instance(
        name = 'AdvancedFilterMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _on_filter_removed(self, column: int):
        """Обработчик удаления фильтра через чип – очищает фильтр для столбца."""

        self.proxy_model.clear_column_filter(column)

    @AppLogger.get_instance(
        name = 'AdvancedFilterMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _on_all_filters_cleared(self):
        """Обработчик кнопки «Очистить все» – сбрасывает все фильтры в прокси-модели."""

        self.proxy_model.clear_all_filters()

    @AppLogger.get_instance(
        name = 'AdvancedFilterMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _on_filter_edit_requested(self, column: int):
        """
        Обработчик двойного клика по чипу – открывает диалог редактирования фильтра для столбца.

        Эмулирует клик по заголовку таблицы, вызывая `_request_advanced_filter` у заголовка.
        """
        
        # Эмулируем клик по заголовку для вызова диалога
        header = self.table_view.horizontalHeader()
        if hasattr(header, '_request_advanced_filter'):
            header._request_advanced_filter(column)

    @AppLogger.get_instance(
        name = 'AdvancedFilterMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    # Переопределяем on_filter_requested (из ListFilterMixin) для поддержки новых операторов
    def on_filter_requested(self, column, logic, conditions) -> None:
        """
        Применяет сложный фильтр к прокси-модели.

        Args:
            column (int): Номер столбца.
            logic (str): 'AND' или 'OR' – логика объединения условий.
            conditions (list): Список словарей с условиями
                (operator, value, value2).

        Returns:
            None
        """

        self.proxy_model.set_column_filter(column, logic, conditions)

class SelectionDialogMixin:
    """
    Миксин для отображения диалога выбора области действия над строками таблицы.

    Поддерживает:
        - только текущую строку
        - только строки, отмеченные чекбоксами
        - текущую + отмеченные
        - все видимые строки

    Возвращает структуру `SelectionChoice` с типом действия и списком ID.
    """

    class SelectionChoice:
        """Объект, возвращаемый диалогом выбора."""

        __slots__ = ('action_type', 'ids', 'all_visible')

        @AppLogger.get_instance(
            name = 'SelectionChoice',
            # share_file_with = 'system',
            enable_file_logging = 'system',
            use_name_in_filename = False, # 'system',
        ).log_execution_time(
            level = AppLogger._parse_log_level('DEBUG')
        )
        def __init__(
            self, 
            action_type: str, 
            ids: set = None, 
            all_visible: bool = False
        ):
            self.action_type = action_type   # 'none', 'selected', 'current', 'checkbox', 'both', 'all'
            self.ids = ids or set()
            self.all_visible = all_visible

    # @AppLogger.get_instance(
    #     name = 'SelectionDialogMixin',
    #     # share_file_with = 'system',
    #     enable_file_logging = 'system',
    #     use_name_in_filename = False, # 'system',
    # ).log_execution_time(
    #     level = AppLogger._parse_log_level('DEBUG')
    # )
    # def _show_selection_dialog(self, action_name: str = "удаление") -> 'SelectionChoice':
    #     """
    #     Показывает диалог выбора области для действия action_name.

    #     Параметры:
    #         action_name (str): Название действия (отображается в диалоге).

    #     Возвращает:
    #         SelectionChoice: Объект с выбранной областью.
    #     """

    #     current_dto = self._get_current_selected_dto()      # DTO текущей выделенной строки
    #     checkbox_ids = self._get_selected_checkbox_ids()    # ID сущностей, выбранных через чекбоксы
        
    #     has_checkbox = bool(checkbox_ids)       # Есть ли выбранные чекбоксы
    #     has_current = current_dto is not None   # Есть ли текущая строка

    #     total_visible = self.proxy_model.rowCount() if self.proxy_model else 0 # Всего видимых строк

    #     if not has_checkbox and not has_current:
    #         QMessageBox.warning(self, "Нет выбора", "Нет строк для выполнения действия.")
    #         return self.SelectionChoice('none')

    #     # # Если нет чекбоксов – сразу возвращаем текущую строку
    #     # if not has_checkbox and has_current:
    #     #     return self.SelectionChoice('current', ids={current_dto.id})


    #     # Если нет выбранных чекбоксов – удаляем только текущую строку без вопросов
    #     if (
    #         has_current and not has_checkbox # Есть текущая строка, но нет выбранных чекбоксов
    #     ) or (
    #         has_current and (current_dto.id in checkbox_ids) and len(checkbox_ids) == 1 # Есть текущая строка и только она выбрана через чекбокс
    #     ):
    #         # self._perform_deletion({current_dto.id}, current_dto)
    #         return self.SelectionChoice('current', ids={current_dto.id})

    #     # Если нет текущей строки, но есть чекбоксы – предлагаем только чекбоксы
    #     if not has_current and has_checkbox:
    #         reply = QMessageBox.question(
    #             self, f"Подтверждение {action_name}",
    #             f"Выполнить {action_name} для {len(checkbox_ids)} отмеченных записей?",
    #             QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
    #         )

    #         if reply == QMessageBox.StandardButton.Yes:
    #             return self.SelectionChoice('checkbox', ids=checkbox_ids)
            
    #         return self.SelectionChoice('none')

    #     # Есть и текущая строка, и чекбоксы – показываем расширенный диалог
    #     msg = QMessageBox(self)
    #     msg.setWindowTitle(f"Выбор области {action_name}")
    #     msg.setText("Выберите, к каким записям применить действие:")

    #     btn_current = msg.addButton("Только текущую", QMessageBox.ActionRole)
    #     btn_checkbox = msg.addButton("Только выбранные (чекбоксы)", QMessageBox.ActionRole)
    #     btn_both = msg.addButton("Текущую + выбранные", QMessageBox.ActionRole)
    #     btn_all = msg.addButton("Все строки", QMessageBox.ActionRole)
    #     btn_cancel = msg.addButton("Отмена", QMessageBox.RejectRole)

    #     # Устанавливаем доступность кнопок 
    #     btn_current.setEnabled(has_current) # Только текущая
    #     btn_checkbox.setEnabled(has_checkbox) # Только чекбоксы
    #     btn_both.setEnabled(has_current and has_checkbox) # Текущая + чекбоксы
    #     btn_all.setEnabled(total_visible > 0) # Все

    #     msg.setDefaultButton(btn_cancel)

    #     msg.exec()
    #     clicked = msg.clickedButton()

    #     if clicked == btn_current: # Только текущая
    #         return self.SelectionChoice('current', ids={current_dto.id})
        
    #     elif clicked == btn_checkbox: # Только чекбоксы
    #         return self.SelectionChoice('checkbox', ids=checkbox_ids)
        
    #     elif clicked == btn_both: # Текущая + чекбоксы
    #         ids = set(checkbox_ids)
    #         ids.add(current_dto.id)
    #         return self.SelectionChoice('both', ids=ids)
        
    #     elif clicked == btn_all: # Все
    #         # Дополнительное подтверждение для массовой операции
    #         reply = QMessageBox.question(
    #             self, "Подтверждение массового действия",
    #             f"Вы действительно хотите применить действие ко всем {total_visible} отображаемым записям?",
    #             QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
    #         )
    #         if reply == QMessageBox.StandardButton.Yes: # 
    #             return self.SelectionChoice('all', all_visible=True)
            
    #         else:
    #             return self.SelectionChoice('none')
            
    #     else:
    #         return self.SelectionChoice('none')

    @AppLogger.get_instance(
        name = 'SelectionDialogMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _show_selection_dialog_no(self, selected_ids: set, checkbox_ids: set, action_name: str = "удаление"):
        # Если нет ни выделенных, ни чекбоксов – сообщаем
        if not selected_ids and not checkbox_ids:
            QMessageBox.warning(self, "Нет выбора", "Нет строк для выполнения действия {action_name}.")
            return self.SelectionChoice('none')

        return None    
    
    @AppLogger.get_instance(
        name = 'SelectionDialogMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _show_selection_dialog_one(self, selected_ids: set, checkbox_ids: set, action_name: str = "удаление"):

        if_selected = selected_ids and not checkbox_ids     # Простой случай: только выделенные (нет чекбоксов)
        if_checkbox = checkbox_ids and not selected_ids     # Простой случай: только чекбоксы (нет выделенных)

        if if_selected or if_checkbox:
            reply = QMessageBox.question(
                self, f"Подтверждение {action_name}",
                f"Выполнить {action_name} для {len(selected_ids if if_selected else checkbox_ids)} выделенных записей?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                return self.SelectionChoice(
                    action_type=    'selected' if if_selected else 'checkbox', 
                    ids=            selected_ids if if_selected else checkbox_ids 
                )
            
            else:
                return self.SelectionChoice('none')

        return None  

    @AppLogger.get_instance(
        name = 'SelectionDialogMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _show_selection_dialog_multi(self, selected_ids: set, checkbox_ids: set, action_name: str = "удаление"):

        total_visible = self.proxy_model.rowCount() if self.proxy_model else 0
        
        # Сложный случай: есть и выделенные, и чекбоксы (возможно пересечение)
        # Показываем расширенный диалог
        msg = QMessageBox(self)
        msg.setWindowTitle(f"Выбор области {action_name}")
        msg.setText("Выберите, к каким записям применить действие:")

        btn_selected = msg.addButton("Только выделенные (обычное выделение)", QMessageBox.ActionRole)
        btn_checkbox = msg.addButton("Только отмеченные (чекбоксы)", QMessageBox.ActionRole)
        btn_both = msg.addButton("Выделенные + отмеченные", QMessageBox.ActionRole)
        btn_all = msg.addButton("Все видимые строки", QMessageBox.ActionRole)
        btn_cancel = msg.addButton("Отмена", QMessageBox.RejectRole)

        msg.setDefaultButton(btn_cancel)
        msg.exec()
        clicked = msg.clickedButton()

        if clicked == btn_selected:
            return self.SelectionChoice('selected', ids=selected_ids)
        
        elif clicked == btn_checkbox:
            return self.SelectionChoice('checkbox', ids=checkbox_ids)
        
        elif clicked == btn_both:
            # Объединение множеств (удаляем возможные дубликаты)
            both_ids = selected_ids.union(checkbox_ids)
            return self.SelectionChoice('both', ids=both_ids)
        
        elif clicked == btn_all:
            # Дополнительное подтверждение для массовой операции
            reply = QMessageBox.question(
                self, "Подтверждение массового действия",
                f"Вы действительно хотите применить действие ко всем {total_visible} отображаемым записям?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )

            if reply == QMessageBox.StandardButton.Yes:
                return self.SelectionChoice('all', all_visible=True)
            else:
                return self.SelectionChoice('none')
            
        else:
            return self.SelectionChoice('none')

    @AppLogger.get_instance(
        name = 'SelectionDialogMixin',
        enable_file_logging = 'system',
        use_name_in_filename = False,
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _show_selection_dialog(self, action_name: str = "удаление") -> 'SelectionChoice':
        """
        Показывает диалог выбора области для массового действия.

        Args:
            action_name (str): Название действия (отображается в диалоге).

        Returns:
            SelectionChoice: Объект с выбранным типом и множеством ID.
        """

        selected_ids = self._get_selected_ids_from_view()          # обычное выделение
        checkbox_ids = self._get_selected_checkbox_ids()           # чекбоксы

        for i in [
            self._show_selection_dialog_no,     # Если нет ни выделенных, ни чекбоксов – сообщаем
            self._show_selection_dialog_one,    # Простой случай: только выделенные (нет чекбоксов)
            self._show_selection_dialog_multi,  # Сложный случай: есть и выделенные, и чекбоксы (возможно пересечение)
        ]:
            choice = i(selected_ids, checkbox_ids, action_name)

            if choice:
                return choice

    @AppLogger.get_instance(
        name = 'SelectionDialogMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _get_all_visible_ids(self) -> set:
        """
        Возвращает множество ID всех видимых строк (после фильтрации).

        Возвращает:
            set[int]: Идентификаторы сущностей.
        """

        ids = set()

        if not self.proxy_model:
            return ids
        
        for row in range(self.proxy_model.rowCount()):
            proxy_index = self.proxy_model.index(row, 0)

            if proxy_index.isValid():
                source_index = self.proxy_model.mapToSource(proxy_index)
                dto = self.source_model.get_item_at_row(source_index.row())

                if dto and dto.id is not None:
                    ids.add(dto.id)

        return ids

class CheckboxSelectionMixin:
    """
    Миксин для добавления столбца с чекбоксами в таблицу.

    Предоставляет методы для управления выбором строк через чекбоксы,
    получения выбранных ID, очистки чекбоксов.
    """

    @AppLogger.get_instance(
        name = 'CheckboxSelectionMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _ensure_checkbox_header_menu(self):
        """
        Переустанавливает callback для заголовка чекбокс-столбца при каждом показе страницы.

        Обеспечивает появление пунктов «Выбрать все» / «Снять все» в контекстном меню заголовка.
        """

        if not self.edit_mode:
            return
        
        if hasattr(self.table_view, 'horizontalHeader'):
            header = self.table_view.horizontalHeader()  # заголовок таблицы
            if hasattr(header, 'set_checkbox_header_menu'):
                header.set_checkbox_header_menu(self._toggle_all_checkboxes) # устанавливаем callback
                 
    @AppLogger.get_instance(
        name = 'CheckboxSelectionMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _setup_checkbox_column(self) -> None:
        """
        Включает столбец чекбоксов в модели и настраивает заголовок.

        Вызывается при переключении режима редактирования.
        """

        if not hasattr(self, 'source_model'):
            return
        
        self.source_model.set_checkbox_column_visible(self.edit_mode)
        # Добавляем пункты в контекстное меню заголовка чекбокс-столбца
        self._ensure_checkbox_header_menu()   # вызываем общий метод 

    @AppLogger.get_instance(
        name = 'CheckboxSelectionMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _toggle_all_checkboxes(self, checked: bool) -> None:
        """
        Устанавливает или снимает все чекбоксы.

        Параметры:
            checked (bool): True – выбрать все, False – снять все.
        """

        if not self.edit_mode:
            return
        
        for row in range(self.source_model.rowCount()):
            self.source_model.set_checkbox_state(row, checked)

        # self._update_save_button_state()
        self.table_view.viewport().update()

    @AppLogger.get_instance(
        name = 'CheckboxSelectionMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _get_selected_checkbox_ids(self) -> Set[int]:
        """
        Возвращает множество ID сущностей, у которых установлен чекбокс.

        Возвращает:
            set[int]: ID отмеченных строк.
        """

        ids = set()
        for row in range(self.source_model.rowCount()):
            index = self.source_model.index(row, 0)
            if self.source_model.data(index, Qt.CheckStateRole) == Qt.Checked:
                dto = self.source_model.get_item_at_row(row)
                if dto and dto.id is not None:
                    ids.add(dto.id)

        return ids

    @AppLogger.get_instance(
        name = 'CheckboxSelectionMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _clear_checkboxes(self) -> None:
        """Снимает все чекбоксы (без изменения deleted_ids)."""

        for row in range(self.source_model.rowCount()):
            self.source_model.set_checkbox_state(row, False)

    @AppLogger.get_instance(
        name = 'CheckboxSelectionMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _get_current_selected_dto(self):
        """
        Возвращает DTO текущей выделенной строки (обычное выделение, не чекбокс).

        Возвращает:
            Optional[Any]: DTO или None, если выделения нет.
        """

        selection_model = self.table_view.selectionModel()
        if not selection_model or not selection_model.hasSelection():
            return None
        
        indexes = selection_model.selectedIndexes()
        if not indexes:
            return None
        
        proxy_index = indexes[0]
        source_index = self.proxy_model.mapToSource(proxy_index)
        if not source_index.isValid():
            return None
        
        return self.source_model.get_item_at_row(source_index.row())

    @AppLogger.get_instance(
        name = 'CheckboxSelectionMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _delete_with_selection_prompt(self) -> None:
        """
        Вызывает диалог выбора области удаления и выполняет удаление.

        Используется вместо прямого `_mark_selected_for_deletion`.
        """

        if not self.edit_mode:
            return

        choice = self._show_selection_dialog("удаление")

        if choice.action_type == 'none':
            return

        if choice.action_type == 'all':
            ids_to_delete = self._get_all_visible_ids()
        else:
            ids_to_delete = choice.ids

        if not ids_to_delete:
            return

        current_dto = None
        # Если текущая строка входит в список, очистим правую панель
        if self.selected_dto and self.selected_dto.id in ids_to_delete:
            current_dto = self.selected_dto

        # Удаляем строки
        # if not current_dto:
        self._perform_deletion(ids_to_delete, current_dto)

    @AppLogger.get_instance(
        name = 'CheckboxSelectionMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _cancel_with_selection_prompt(self) -> None:
        """
        Вызывает диалог выбора области отмены изменений и отменяет изменения для выбранных записей.
        """
        
        if not self.edit_mode:
            return

        choice = self._show_selection_dialog("отмены изменений")
        if choice.action_type == 'none':
            return

        if choice.action_type == 'all':
            ids_to_cancel = self._get_all_visible_ids()
        else:
            ids_to_cancel = choice.ids

        if not ids_to_cancel:
            return

        # Дополнительное подтверждение перед массовой отменой
        if choice.action_type == 'all' or len(ids_to_cancel) > 5:
            reply = QMessageBox.question(
                self, "Подтверждение отмены",
                f"Отменить изменения для {len(ids_to_cancel)} записей?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )

            if reply != QMessageBox.StandardButton.Yes:
                return


        ids_to_cancel = list(ids_to_cancel)

        self._cancel_rows(ids_to_cancel) # Отменить изменения для строк
        self._update_save_button_state() # Обновить состояние кнопки сохранения (она должна стать неактивной)
        self._update_selection_state() # Обновить состояние кнопки «Отменить текущую» (выделения нет → кнопка неактивна)

        # Обновляем правую панель, если есть выбранная строка
        if self.selected_dto:
            try:
                fresh_dto = self.service.get_by_id(self.selected_dto.id)
                if hasattr(self, 'update_details'):
                    self.update_details(fresh_dto)

            except Exception as e:
                self.logger.exception(f"Ошибка обновления правой панели после отмены: {e}")

        self.logger.debug(f"Изменения для строки id={ids_to_cancel} отменены, данные восстановлены из БД")

    @AppLogger.get_instance(
        name = 'CheckboxSelectionMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    # def _perform_deletion(
    #     self,
    #     ids_to_delete: Set[int],
    #     current_dto_to_clear: Optional[Any]= None
    # ) -> None:
    #     """
    #     Помечает записи на удаление, удаляет из модели новые строки, сбрасывает чекбоксы.

    #     Параметры:
    #         ids_to_delete (set): Множество ID для удаления.
    #         current_dto_to_clear (Optional[Any]): Если передан и его ID входит в `ids_to_delete`,
    #             правая панель очищается.
    #     """

    #     if not ids_to_delete:
    #         return

    #     for entity_id in list(ids_to_delete):
    #         source_row = self._find_source_row_by_id(entity_id)
    #         if source_row == -1:
    #             continue

    #         dto = self.source_model.get_item_at_row(source_row)
    #         if dto is None:
    #             continue

    #         if dto.id is None or dto.id < 0:  # новая строка
    #             self.source_model.remove_row(source_row)
    #             self.new_rows.discard(source_row)
    #             self.deleted_ids.discard(entity_id)

    #         else:
    #             self.deleted_ids.add(entity_id)
                
    #             # Снимаем модификацию, если была
    #             if entity_id in self.modified_ids:
    #                 # self.modified_ids.discard(entity_id)
    #                 self._modified_ids(entity_id, False)

    #             # Обновляем цвет строки
    #             self._set_row_color_by_source_row(source_row)

    #     # Сбрасываем чекбоксы для всех удалённых ID
    #     self._clear_checkboxes()
    #     # Если текущий DTO был удалён, очищаем правую панель
    #     if current_dto_to_clear is not None and current_dto_to_clear.id in ids_to_delete:
    #         self.selected_dto = None
    #         if hasattr(self, '_clear_right_panel'):
    #             self._clear_right_panel()

    #     self._update_save_button_state()
    #     self.table_view.viewport().update()

    @AppLogger.get_instance(
        name = 'CheckboxSelectionMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _get_entity_id(self, dto) -> int:
        """Возвращает ID сущности из DTO (учитывая временные отрицательные ID)."""
        
        if dto is None:
            return None
        
        return dto.id

class ListSelectionMixin:
    """
    Миксин для управления выделением строк в таблице.

    Предоставляет методы сохранения, восстановления и получения текущей строки,
    а также поиск строки по ID сущности.
    """

    @AppLogger.get_instance(
        name = 'ListSelectionMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _clear_selection(self):
        """
        Сбрасывает все отслеживаемые изменения (modified_ids, deleted_ids, new_rows).
        """

        # Сбрасываем все отслеживаемые изменения
        # self.modified_rows.clear()
        # self.deleted_rows.clear()
        # self.new_rows.clear()

        self.modified_ids.clear()
        self.deleted_ids.clear()
        self.new_rows.clear()

        # # Очистка черновиков
        # self._clear_drafts()

    @AppLogger.get_instance(
        name = 'ListSelectionMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _select_by_id(self, entity_id: int) -> bool:
        """
        Выделяет строку по ID сущности.

        Параметры:
            entity_id (int): ID записи.

        Возвращает:
            bool: True, если строка найдена и выделена, иначе False.
        """
        
        row = self._find_row_by_dto_id(entity_id)
        if row >= 0:
            self._set_current_row(row)
            return True
        
        return False

    @AppLogger.get_instance(
        name = 'ListSelectionMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _get_current_row(self) -> int:
        """
        Возвращает индекс текущей строки в прокси-модели.

        Возвращает:
            int: Индекс строки или -1.
        """

        current = self.table_view.currentIndex()

        return current.row() if current.isValid() else -1

    @AppLogger.get_instance(
        name = 'ListSelectionMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _set_current_row(self, row: int) -> None:
        """
        Выделяет строку с указанным индексом (в прокси-модели).
        Если строка не существует, ничего не делает.

        Параметры:
            row (int): Индекс строки.
        """

        if row < 0 or row >= self.proxy_model.rowCount():
            return
        
        proxy_index = self.proxy_model.index(row, 0) # 
        self.table_view.setCurrentIndex(proxy_index) # 
        self.table_view.scrollTo(proxy_index) # 

    @AppLogger.get_instance(
        name = 'ListSelectionMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _store_current_row(self) -> None:
        """
        Запоминает текущую строку в прокси-модели (возвращает её индекс). Используется декоратором `preserve_selection`.
        """

        row = self._get_current_row()
        self._saved_row = row
        
        return row

    @AppLogger.get_instance(
        name = 'ListSelectionMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _restore_current_row(self, row: int = None ) -> None:
        """
        Восстанавливает сохранённую строку. Если сохранённой нет, выбирает первую строку.

        Параметры:
            row (int, optional): Индекс строки для восстановления (если не указан, берётся из self._saved_row).
        """

        # if hasattr(self, '_saved_row') and self._saved_row != -1:
        #     if self._saved_row < self.proxy_model.rowCount():
        #         self._set_current_row(self._saved_row)
        #     else:
        #         self._select_first_row()
        # else:
        #     self._select_first_row()

        if row is None:
            row = getattr(self, '_saved_row', -1)

        if row != -1 and row < self.proxy_model.rowCount():
            self._set_current_row(row)
        else:
            self._select_first_row()

        self._saved_row = -1

        # Обновляем состояние кнопок на основе текущего выделения
        self._update_selection_state()
        
    @AppLogger.get_instance(
        name = 'ListSelectionMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _select_first_row(self) -> None:
        """
        Выбирает первую строку в таблице.
        Если таблица не содержит строк, ничего не делает.
        """
        
        if self.proxy_model.rowCount() > 0:
            self._set_current_row(0)
            
    @AppLogger.get_instance(
        name = 'ListSelectionMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _find_row_by_dto_id(self, dto_id: int) -> int:
        """
        Возвращает индекс строки в прокси-модели для DTO с указанным ID.

        Параметры:
            dto_id (int): ID записи.

        Возвращает:
            int: Индекс в прокси-модели или -1.
        """

        for row in range(self.source_model.rowCount()):
            dto = self.source_model.get_item_at_row(row)
            if dto and getattr(dto, 'id', None) == dto_id:
                source_index = self.source_model.index(row, 0)
                proxy_index = self.proxy_model.mapFromSource(source_index)
                if proxy_index.isValid():
                    return proxy_index.row()
                
        return -1
    
    @AppLogger.get_instance(
        name = 'ListSelectionMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _find_source_row_by_id(self, entity_id: int) -> int:
        """
        Возвращает индекс строки в исходной модели (source_model) по ID сущности.

        Параметры:
            entity_id (int): ID записи.

        Возвращает:
            int: Индекс строки или -1.
        """

        for row in range(self.source_model.rowCount()):
            dto = self.source_model.get_item_at_row(row)
            if dto and getattr(dto, 'id', None) == entity_id:
                return row
        
        return -1

    @AppLogger.get_instance(
        name = 'ListSelectionMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _get_selected_ids_from_view(self) -> Set[int]:
        """
        Возвращает множество ID сущностей, выбранных в таблице.
        Учитывает:
            - обычное выделение (клик + Shift/Ctrl)
            - чекбоксы, если они активны в режиме редактирования
        
        Возвращает:
            set[int]: ID выбранных записей.
        """

        entity_ids = set()
        selection_model = self.table_view.selectionModel()
        if selection_model:
            # Явно берём первую колонку (0), так как `selectedRows()` без аргумента может вернуть все колонки.
            for proxy_index in selection_model.selectedRows(0):
                if not proxy_index.isValid():
                    continue

                source_index = self.proxy_model.mapToSource(proxy_index)
                if not source_index.isValid():
                    continue

                if source_index.row() < 0 or source_index.row() >= self.source_model.rowCount():
                    continue

                dto = self.source_model.get_item_at_row(source_index.row())
                if dto and dto.id is not None:
                    entity_ids.add(dto.id)

        return entity_ids

class ListDataMixin:
    """
    Миксин для загрузки данных в таблицу.

    Требует наличия атрибутов:
        - self.loader_func (callable) – функция, возвращающая список DTO.
        - self.current_extra (Any) – дополнительные параметры для загрузчика.
        - self.source_model (DynamicTableModel)
        - self.original_data (dict) – копия исходных данных для отслеживания изменений.
    """

    @AppLogger.get_instance(
        name = 'ListDataMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _load_data(self) -> None:
        """
        Загружает данные из `loader_func`, обновляет модель, сбрасывает цвета строк,
        выделение и сохраняет копию исходных данных в `self.original_data`.

        Сохраняет копию исходных данных в `self.original_data`.
        Устанавливает флаг `self._data_loaded = True`.
        Вызывает `_clear_selection()` и `_update_save_button_state()`.
            
        Returns:
            None
        """

        # Сохраняем ID выбранного DTO (если есть)
        # selected_id = None
        # if self.selected_dto and hasattr(self.selected_dto, 'id'):
        #     selected_id = self.selected_dto.id

        # Запоминаем ID текущего выделенного приёма (если есть)
        selected_id = self.selected_dto.id if self.selected_dto else None
            
        try:
            self.current_data = self.loader_func(self.current_extra) # Загружаем данные
            self.source_model.update_data(self.current_data) # Обновляем модель
            self.original_data = {i: deepcopy(dto) for i, dto in enumerate(self.current_data)}

            self.source_model.clear_row_colors() # Очищаем все установленные цвета

            # Сбрасываем все отслеживаемые изменения

            self._clear_selection() # сбрасываем выделение в таблице (если оно есть)
            
            self._update_save_button_state() # Обновить состояние кнопки сохранения (она должна стать неактивной)

            self._data_loaded = True # Устанавливаем флаг, что данные загружены

        except Exception as e:
            self.logger.exception(f"Ошибка загрузки данных: {e}")
            QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить данные: {e}")


        self._suppress_draft_save = True
        try:
            # Восстанавливаем выделение по ID
            if selected_id is not None:
                # row = self._find_row_by_dto_id(selected_id)
                row = self._find_source_row_by_id(selected_id)
                if row >= 0:
                    self._set_current_row(row)
                else:
                    self._select_first_row()
            else:
                self._select_first_row()

        except Exception as e:
            self.logger.exception(f"Ошибка восстановления выделения: {e}")
            QMessageBox.critical(self, "Ошибка", f"Не удалось восстановить выделение: {e}")
        finally:
            self._suppress_draft_save = False
        
        # Обновляем состояние кнопок на основе текущего выделения
        self._update_selection_state()
        
        self._data_loaded = True # Устанавливаем флаг, что данные загружены

        self.logger.debug(f"Загружено {len(self.current_data)} записей")
        # except Exception as e:
        #     self.logger.exception(f"Ошибка загрузки данных: {e}")
        #     QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить данные: {e}")

    @AppLogger.get_instance(
        name = 'ListDataMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def set_needs_refresh(self, value=True):
        """
        Устанавливает флаг необходимости перезагрузки данных при следующем входе на страницу.

        Параметры:
            value (bool): True – данные будут перезагружены, False – нет.
        """

        self._needs_refresh = value

    @AppLogger.get_instance(
        name = 'ListDataMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def on_enter(self, extra_data=None) -> None:
        """
        Вызывается при переходе на страницу. Если `extra_data` отличается от текущего,
        перезагружает данные. Поддерживает выделение строки по `select_id`.

        Args:
            extra_data (Any, optional): Дополнительные данные, например `{'patient_id': 123}`
                для фильтрации списка. Если `extra_data` отличается от сохранённого,
                данные перезагружаются.
                Поддерживаются ключи:
                    - 'select_id' (int): ID записи для выделения после загрузки.
                    - 'return_to_page' (str): Страница для возврата.
                    - 'return_field' (str): Поле для установки значения при возврате.
                    - Любые другие ключи сохраняются в self._context_params.

        Returns:
                None

        Примечание:
            Если в `extra_data` передан ключ `select_id`, то после загрузки данных
            строка с соответствующим ID будет выделена.
        """

        reload_needed = self._needs_refresh
        select_id = None
        return_to_page = None
        return_field = None

        # Сохраняем контекстные параметры (все, кроме служебных)
        self._context_params = {}
        if extra_data:
            for key, value in extra_data.items():
                if key == 'select_id':
                    select_id = value
                elif key == 'return_to_page':
                    return_to_page = value
                elif key == 'return_field':
                    return_field = value
                else:
                    self._context_params[key] = value

        # Обновляем current_extra для обратной совместимости (например, для loader_func)
        new_extra = self._context_params.copy() if self._context_params else None
        if new_extra != self.current_extra:
            self.current_extra = new_extra
            reload_needed = True
        
        # Если передан select_id (и не было изменения extra_data), всё равно нужно выделить
        # Но перезагрузка данных не требуется, если reload_needed = False
        if not reload_needed and select_id is not None:
            # Просто выделяем строку без перезагрузки
            self._select_by_id(select_id)
            return


        # if extra_data is not None:
        #     # Запоминаем ID для выделения
        #     select_id = extra_data.get('select_id')
        #     # Если extra_data отличается от текущего, обновляем и помечаем необходимость перезагрузки
        #     if extra_data != self.current_extra:
        #         self.current_extra = extra_data
        #         reload_needed = True

        # Загружаем данные, если:
        # - требуется перезагрузка (reload_needed)
        # - или данные ещё не загружены (self._data_loaded == False)     
        if reload_needed or not self._data_loaded: 
            self._load_data()
            self._needs_refresh = False
            self._data_loaded = True # Устанавливаем флаг, что данные загружены
            # После загрузки выделяем строку, если указан select_id
            if select_id is not None:
                self._select_by_id(select_id)

        elif select_id is not None:
            # Если перезагрузка не требуется, но нужно выделить строку (например, при возврате без обновления)
            self._select_by_id(select_id)

        
        # if extra_data is not None and extra_data != self.current_extra:
        #     self.current_extra = extra_data
        #     reload_needed = True
        # if reload_needed:
        #     self._load_data()
        #     self._needs_refresh = False 
    
    @AppLogger.get_instance(
        name = 'ListDataMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )       
    def _apply_draft_to_new_dto(self, dto):
        """Переопределяется в наследниках для применения черновиков к новому DTO перед созданием."""

        pass

class ListChangesMixin:
    """
    Миксин для обработки изменений в таблице: отслеживание modified/delete/new строк,
    обновление цветов, управление кнопкой сохранения.
    """
    
    # @AppLogger.get_instance(
    #     name = 'ListChangesMixin',
    #     enable_file_logging = 'system',
    #    use_name_in_filename = False, # 'system',
    # ).log_execution_time(
    #     level = AppLogger._parse_log_level('DEBUG')
    # )
    # def _update_row_color(self, row: int):
    #     """
    #     Обновляет цвет строки в таблице в зависимости от статуса строки (новая, изменена, удалена).
    #     :param row: индекс строки в таблице
    #     :type row: int
    #     """
    #     proxy_index = self.proxy_model.index(row, 0)
    #     if not proxy_index.isValid():
    #         return
        
    #     source_row = self.proxy_model.mapToSource(proxy_index).row()
    #     if source_row == -1:
    #         return

    #     if row in self.deleted_rows:
    #         color = QColor(255, 200, 200)   # красный
    #     elif row in self.new_rows:
    #         color = QColor(200, 255, 200)   # зелёный
    #     elif row in self.modified_rows:
    #         color = QColor(255, 255, 180)   # жёлтый
    #     else:
    #         color = QColor(255, 255, 255)   # белый

    #     self.logger.debug(f"Обновление цвета строки {row} - {color.name()}")
    #     self.source_model.set_row_color(source_row, color)

    # @AppLogger.get_instance(
    #     name = 'ListChangesMixin',
    #     # share_file_with = 'system',
    #     enable_file_logging = 'system',
    #     use_name_in_filename = False, # 'system',
    # ).log_execution_time(
    #     level = AppLogger._parse_log_level('DEBUG')
    # )
    # def _set_row_color_by_source_row(self, source_row: int):
    #     """Устанавливает цвет строки в исходной модели по её индексу."""

    #     self.logger.debug(
    #         f"_set_row_color_by_source_row: "
    #         f"source_row={source_row}, "
    #         f"modified_rows={self.modified_rows}, "
    #         f"new_rows={self.new_rows}, "
    #         f"deleted_rows={self.deleted_rows}"
    #     )
    #     if source_row < 0 or source_row >= self.source_model.rowCount():
    #         self.logger.warning(
    #             f"source_row {source_row} "
    #         f"вне диапазона (0-{self.source_model.rowCount()-1})"
    #         )
            
    #     if source_row in self.deleted_rows:
    #         color = QColor(255, 200, 200)   # красный
    #     elif source_row in self.new_rows:
    #         color = QColor(200, 255, 200)   # зелёный
    #     elif source_row in self.modified_rows:
    #         color = QColor(255, 255, 180)   # жёлтый
    #     else:
    #         color = QColor(255, 255, 255)   # белый


    #     self.logger.debug(f"Обновление цвета строки {source_row} - {color.name()}")
    #     self.source_model.set_row_color(source_row, color)
    #     self.table_view.viewport().update()   # перерисовка видимой области
    #     # self.table_view.update()              # перерисовка всей таблицы

    @AppLogger.get_instance(
        name = 'ListChangesMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _set_row_color_by_source_row(self, source_row: int):

        dto = self.source_model.get_item_at_row(source_row)
        if dto is None:
            return
        
        if dto.id is None or dto.id < 0:
            # Новая строка
            if source_row in self.new_rows:
                color = QColor(200, 255, 200)   # зелёный
            else:
                color = QColor(255, 255, 255)   # белый
        
        else:
            if dto.id in self.deleted_ids:
                color = QColor(255, 200, 200)   # красный
            elif dto.id in self.modified_ids:
                color = QColor(255, 255, 180)   # жёлтый
            else:
                color = QColor(255, 255, 255)   # белый
        
        self.source_model.set_row_color(source_row, color)
        self.table_view.viewport().update() # перерисовка видимой области

    @AppLogger.get_instance(
        name = 'ListChangesMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _update_save_button_state(self):
        """
        Обновляет состояние кнопки сохранения изменений.
        Кнопка будет активна, если есть какие-либо изменения (новые, измененные, удаленные строки).
        """

        # has_changes = bool(self.modified_rows or self.deleted_rows or self.new_rows)
        has_changes = self._has_unsaved_changes() # возвращает True, если есть какие-либо изменения

        self.save_changes_btn.setEnabled(has_changes) # сохранять можно, если есть изменения
        # self.cancel_all_btn.setEnabled(has_changes) # отменять можно, если есть изменения
        # self.cancel_current_btn.setEnabled(has_changes) # отменять можно, если есть изменения

    @AppLogger.get_instance(
        name='ListChangesMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _modified_ids(self, appointment_id, if_add :bool):
        if if_add:
            self.modified_ids.add(appointment_id)
        else:
            self.modified_ids.discard(appointment_id)

    @AppLogger.get_instance(
        name='ListChangesMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _modified_ids_control(self, entity_id, if_add :bool):

        """
        Добавляет или удаляет ID из множества изменённых, обновляет цвет строки и кнопку сохранения.\
        
        Если if_add=True, то добавляет source_row в множество измененных строк.
        Если if_add=False, то удаляет source_row из множества измененных строк.
        Затем вызывает _set_row_color_by_source_row для обновления цвета строки source_row,
        а также _update_save_button_state для обновления состояния кнопки сохранения изменений.

        Параметры:
            entity_id (int): ID записи.
            if_add (bool): True – добавить в modified_ids, False – удалить.
        """
        
        source_row = self._find_source_row_by_id(entity_id)

        self._modified_ids(entity_id, if_add) 

        if source_row != -1: # Если строка была найдена
            self._set_row_color_by_source_row(source_row) # обновляем цвет строки

        self._update_save_button_state() # активируем кнопку сохранения

    @AppLogger.get_instance(
        name = 'ListChangesMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    @Slot(int)
    def _on_row_modified(self, row: int):
        """
        Обработчик сигнала `row_modified` от модели. Помечает строку как изменённую,
        если данные отличаются от оригинала.
        
        Если строка была удалена, то ничего не делает.
        Иначе, добавляет строку в список измененных строк и обновляет цвет строки в таблице, а также состояние кнопки сохранения изменений.
        
        Параметры:
            row (int): Индекс строки в source_model.
        """

        self.logger.debug(
            f"_on_row_modified вызван для row={row}, "
        )
        # self.logger.debug(f"Строка {row} изменена")

        # Пропускаем, если строка уже помечена на удаление
        # if row in self.deleted_rows:

        dto = self.source_model.get_item_at_row(row)
        # Если это новая строка (отрицательный ID или None) — не добавляем в modified_rows

        if dto is None:
            return

        # Пропускаем, если строка помечена на удаление (по id)
        if dto.id is not None and dto.id in self.deleted_ids:
            return

        # Если это новая строка (временный id), не добавляем в modified_ids
        if dto.id is None or dto.id < 0:
            self.logger.debug(
                f"Строка {row} — новая, пропускаем добавление в modified_ids"
            )
            return 
         
            
        # if row in self.deleted_ids:
        #     return

        # dto = self.source_model.get_item_at_row(row)
        # # Если это новая строка (отрицательный ID или None) — не добавляем в modified_rows
        # if dto and (dto.id is None or (hasattr(dto, 'id') and dto.id < 0)):
        #     self.logger.debug(f"Строка {row} — новая, пропускаем добавление в modified_rows")
        #     return
        

        # Проверяем, не вернулось ли значение к исходному
        original = self.original_data.get(row)

        self.logger.debug(f"if original is not None : {original is not None}")
        if original is not None:
            # Сравниваем сериализованные данные (исключаем поля, которые могут меняться)
            current_dict = dto.model_dump()
            original_dict = original.model_dump()

            self.logger.debug(f"if current_dict == original_dict : {current_dict == original_dict}")
            if current_dict == original_dict:

                self.logger.debug(f"if dto.id in self.modified_ids : {dto.id in self.modified_ids}")
                if dto.id in self.modified_ids:
                    self._modified_ids_control( dto.id, False )

                self._update_selection_state() # обновляем состояние выбора
                return


        self.logger.debug(
            f"if dto.id not in self.modified_ids : {dto.id not in self.modified_ids}"
        )
        
        if dto.id not in self.modified_ids:
            self._modified_ids_control(dto.id, True) 
            self._update_selection_state()

class ListEditModeMixin:
    """
    Миксин для включения/выключения режима редактирования.

    Управляет видимостью элементов интерфейса (кнопка сохранения, inline‑комбобокс),
    переключением сигналов двойного клика и режима редактирования таблицы.
    """

    @AppLogger.get_instance(
        name = 'ListEditModeMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _set_visible_edit_mode_elements(self, edit_mode):
        """
        Показывает/скрывает элементы, относящиеся к режиму редактирования.

        Параметры:
            edit_mode (bool): True – режим редактирования включён.
        """
                
        self.action_combo.setVisible(not edit_mode)
        self.inline_action_combo.setVisible(edit_mode)
        self.save_changes_btn.setVisible(edit_mode)

        # self.cancel_all_btn.setVisible(edit_mode)
        # self.cancel_current_btn.setVisible(edit_mode)


        if hasattr(self, 'action_btn') and self.action_btn:
            self.action_btn.setVisible(not edit_mode)

        self.table_view.setEditTriggers( # устанавливаем режим редактирования таблицы 
            QAbstractItemView.DoubleClicked if edit_mode else QAbstractItemView.NoEditTriggers
        )

        if edit_mode:   
            self.table_view.doubleClicked.disconnect(self._on_row_double_clicked) 
            self.table_view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)     # Включаем множественное выделение (Shift/Ctrl)
        else:
            self.table_view.doubleClicked.connect(self._on_row_double_clicked )
            self.table_view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)         # В обычном режиме – только одна строка
        
    @AppLogger.get_instance(
        name = 'ListEditModeMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    @preserve_selection(
        store_method_name='_store_current_row', 
        restore_method_name='_restore_current_row',
    )
    @Slot(bool)
    def _on_edit_mode_toggled(self, checked: bool):
        """
        Вызывается при переключении кнопки «Режим редактирования».

        Если выключение и есть несохранённые изменения, предлагает сохранить или отменить.
        При включении и пустой таблице автоматически добавляет новую строку.

        Параметры:
            checked (bool): Новое состояние кнопки (включён ли режим).
        """

        has_changes = self._has_unsaved_changes() # возвращает True, если есть какие-либо изменения

        if not checked and has_changes:
            reply = QMessageBox.question(
                self, "Несохранённые изменения",
                "Есть несохранённые изменения. Сохранить перед выходом из режима редактирования?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel
            )
            if reply == QMessageBox.StandardButton.Yes:
                # Пытаемся сохранить
                success = self._save_changes( # сохраняем изменения
                    if_question=False
                )
                if not success:
                    # Сохранение не удалось – НЕ выключаем режим
                    # Возвращаем кнопку в исходное положение (включено)
                    self.edit_mode_btn.blockSignals(True)
                    self.edit_mode_btn.setChecked(True)
                    self.edit_mode_btn.blockSignals(False)
                    self.edit_mode = True
                    
                    return   # остаёмся в режиме редактирования
                self.edit_mode = False

            elif reply == QMessageBox.StandardButton.No:
                self._load_data() # обновляем данные

                self._clear_selection() # сбрасываем выделение в таблице (если оно есть)
                self._clear_drafts() # Очистка черновиков (если они есть)

                self._update_save_button_state() # обновляем состояние кнопки сохранения
                self.edit_mode = False

            else:
                return
            
        else:
            # При включении режима редактирования, если таблица пуста, создаём новую строку
            if checked and self.source_model.rowCount() == 0:
                self._add_inline_row() # добавляем новую строку
                
            self.edit_mode = checked

        # Управление видимостью кнопок
        self._set_visible_edit_mode_elements(self.edit_mode) # устанавливаем видимость кнопок

        self.table_view.clearSelection() # сбрасываем выделение в таблице
        self.selected_dto = None

        # Управление столбцом чекбоксов
        self.source_model.set_checkbox_column_visible(self.edit_mode)
        header = self.table_view.horizontalHeader()

        if hasattr(self, 'action_btn'): # если есть дополнительная кнопка
            self.action_btn.setEnabled(False) # отключаем ее

        # Переустанавливаем делегаты и обновляем read-only режим для текстовых попапов
        self._reapply_delegates()
        self._update_text_popup_delegates_readonly()

        # Дополнительная очистка при выходе из режима
        if not self.edit_mode:
            self._clear_checkboxes()
            self.deleted_ids.clear()
            self._update_save_button_state()

        # Настройка заголовка таблицы (растяжение последнего столбца, видимость)
        if header:
            self._setup_header_settings_table(header=header)
            self._setup_header_visible_table(header=header)        

        self.logger.debug(f"Режим редактирования: {'включён' if self.edit_mode else 'выключен'}")

class ListSaveMixin: 
    """
    Миксин для сохранения изменений в базу данных.

    Реализует сохранение новых строк, обновление изменённых и удаление помеченных записей.
    """

    @AppLogger.get_instance(
        name = 'ListSaveMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _validate_required_fields(self, dto) -> None:
        """
        Проверяет, заполнены ли все обязательные поля в DTO.
        :param dto: DTO для проверки
        :raises ValueError: если какое-то обязательное поле не заполнено, с сообщением о пропущенных полях
        """
        missing_fields = []
        for field_name, config in self.field_configs.items():
            if config.get('required', False):
                value = getattr(dto, field_name, None)
                if value is None or (isinstance(value, str) and not value.strip()):
                    # Берём человекочитаемый заголовок из конфига, если есть, иначе имя поля
                    title = config.get('title', field_name.replace('_', ' ').title())
                    missing_fields.append(title)
        if missing_fields:
            raise ValueError(f"Обязательные поля не заполнены: {', '.join(missing_fields)}")

    @AppLogger.get_instance(
        name = 'ListSaveMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _save_deleted(self):
        """
        Удаляет записи, ID которых находятся в множестве `self.deleted_ids`.

        Обновляет изменённые записи (ID из `self.modified_ids`) через сервис.
        После обновления обновляет DTO в модели и сбрасывает пометку modified.

        После успешного удаления очищает `self.deleted_ids`.

        Returns:
            None
        """
        
        for entity_id in list(self.deleted_ids):
            try:
                self.service.delete(entity_id)
                self.logger.info(f"Удалена запись ID={entity_id}")

            except Exception as e:
                self.logger.exception(f"Ошибка удаления ID={entity_id}: {e}")
        
        self.deleted_ids.clear()

    @AppLogger.get_instance(
        name = 'ListSaveMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _save_modified(self):
        # Проходим по копии, так как в процессе можем изменять множество
        for entity_id in list(self.modified_ids):
            # Находим DTO по id (может быть несколько строк с одним id? нет, id уникален)
            dto = None
            row = -1
            for r in range(self.source_model.rowCount()):
                candidate = self.source_model.get_item_at_row(r)
                if candidate and getattr(candidate, 'id', None) == entity_id:
                    dto = candidate
                    row = r
                    break

            if dto is None:
                # self.modified_ids.discard(entity_id)
                self._modified_ids(entity_id, False)
                continue

            # Проверяем обязательные поля перед обновлением
            try:
                self._validate_required_fields(dto)
            except ValueError as e:
                self.logger.warning(f"Обновление ID={entity_id} отменено: {e}")
                # Можно также показать пользователю предупреждение, но исключение прервёт сохранение
                raise  # Прерываем весь процесс сохранения

            original = self.original_data.get(row)
            if original and dto.model_dump() == original.model_dump():
                # self.modified_ids.discard(entity_id)
                self._modified_ids(entity_id, False)
                continue

            updated = self.service.update(dto)
            self.source_model.update_row(row, updated)

            self._modified_ids(entity_id, False)

            if row != -1:
                self._set_row_color_by_source_row(row)
                
            self.logger.info(f"Обновлена запись ID={updated.id}")

        self.modified_ids.clear()

    @AppLogger.get_instance(
        name = 'ListSaveMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _save_new(self) -> None:
        """
        Сохраняет в базу данных все новые строки, добавленные в режиме редактирования.

        Метод перебирает все строки, индекс которых сохранён в множестве `self.new_rows`.
        Для каждой такой строки:
            1. Извлекает DTO из модели.
            2. Проверяет обязательные поля через `_validate_required_fields`.
            3. Применяет черновики (если они есть) через `_apply_draft_to_new_dto`.
            4. Вызывает `self.service.create(dto)` для сохранения в БД.
            5. Обновляет DTO в модели только что созданной записью (с присвоенным ID).
            6. Логирует успешное создание.

        После обработки всех новых строк множество `self.new_rows` очищается.

        Returns:
            None

        Raises:
            ValueError: Если при проверке обязательных полей обнаруживается,
                что какое-либо поле, помеченное в `field_configs` как `required=True`,
                отсутствует в DTO или содержит пустую строку.
            Любое другое исключение, возникшее при вызове `service.create(dto)`,
                пробрасывается наверх (например, ошибка целостности БД,
                нарушение внешнего ключа и т.п.).

        Note:
            Перед созданием записи метод вызывает `_validate_required_fields(dto)`,
            который может выбросить `ValueError` с перечнем незаполненных
            обязательных полей. Это предотвращает сохранение неполных данных.

            После успешного создания новой записи в БД метод обновляет
            соответствующий DTO в модели, чтобы у строки появился реальный
            (положительный) ID и исходные данные для last_changes.

            Метод не выполняет автоматический commit – транзакция управляется
            вышестоящим методом `_save_changes`.
        """
        
        for row in list(self.new_rows):
            dto = self.source_model.get_item_at_row(row)
            if dto:
                self._validate_required_fields(dto)# Проверяем обязательные поля

                self._apply_draft_to_new_dto(dto) # если есть черновики
                created = self.service.create(dto)
                self.source_model.update_row(row, created)
                self.logger.info(f"Создана новая запись ID={created.id}")

        self.new_rows.clear()

    @AppLogger.get_instance(
        name = 'ListSaveMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    @preserve_selection()
    @Slot()
    def _save_changes(self , if_question:bool = True) -> bool:
        """
        Главный метод сохранения: последовательно вызывает `_save_new`, `_save_modified`, `_save_deleted`, 
        затем перезагружает данные (`_load_data`) и выходит из режима редактирования.

        1. Удаление удаленных строк
        2. Обновление измененных строк
        3. Создание новых строк

        Параметры:
            if_question (bool): Показывать ли диалог подтверждения перед сохранением.
        
        """
        self.logger.info("=== _save_changes ВЫЗВАН ИЗ ListSaveMixin ===")

        has_changes = self._has_unsaved_changes()
        if not has_changes:
            return True

        if if_question:
            reply = QMessageBox.question(
                self, "Подтверждение",
                "Сохранить все изменения? Будут обновлены, добавлены и удалены записи в БД.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return False

        self.table_view.setEnabled(False)
        self.save_changes_btn.setEnabled(False)

        success = True
        try:
            # Новые строки
            self._save_new()

            # Обновление
            self._save_modified()

            # Удаление
            self._save_deleted()

            self._load_data() # загружаем обновленные данные

            self.changes_saved.emit()
            QMessageBox.information(self, "Успех", "Изменения сохранены.")

            # Выходим из режима редактирования, если он был включён
            self._exit_edit_mode()

            self._clear_checkboxes() # снимаем все чекбоксы

        except Exception as e:
            self.logger.exception(f"Ошибка при сохранении изменений: {e}")
            QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить изменения: {e}")
            success = False
        finally:
            self.table_view.setEnabled(True)
            self._update_save_button_state()

        return success

    @AppLogger.get_instance(
        name = 'ListSaveMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _exit_edit_mode(self):
        """
        Выходит из режима редактирования, если он активен.
        Снимает флаг режима редактирования с кнопки `edit_mode_btn`.
        """
        
        if self.edit_mode:
            # self.edit_mode_btn.setChecked(False) # снимаем флаг режима редактирования
            self.edit_mode_btn.blockSignals(True)
            self.edit_mode_btn.setChecked(False)    # снимаем флаг режима редактирования
            self.edit_mode_btn.blockSignals(False)

class ListUIMixin:
    """
    Миксин для построения пользовательского интерфейса страницы списка.

    Создаёт верхнюю панель (кнопки, комбобоксы, поиск), таблицу, подключает модель,
    прокси-модель, настраивает заголовки и делегаты.
    """
    
    @AppLogger.get_instance(
        name = 'ListUIMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _get_real_type(self, field_type):
        """Извлекает реальный тип из Optional/Union (например, Optional[str] -> str)."""

        origin = get_origin(field_type)
        if origin is Union:
            args = get_args(field_type)

            for arg in args:
                if arg is not type(None):
                    return arg
                
        return field_type

    @AppLogger.get_instance(
        name = 'ListUIMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _setup_ui(self):
        """
        Главный метод построения UI – вызывает `_setup_top_panel`, `_setup_table`, `_setup_delegates`.

        1. Установка верхней панели
        2. Установка таблицы
        3. Добавление таблицы в основной верстке
        4. Установка делегатов
        """

        # Основной макет
        self._setup_top_panel() # Верхняя панель
        self._setup_table() # Добавляем основной макет

        # Добавляем таблицу в основной layout
        self.main_layout.addWidget(self.table_view)
        self._setup_delegates() # Устанавливаем делегаты для колонок с выпадающими списками

    @AppLogger.get_instance(
        name = 'ListUIMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _setup_top_panel(self):
        """
        Создаёт верхнюю панель с кнопкой «Режим редактирования», комбобоксами действий,
        кнопкой сохранения, полем поиска.
        """
        # Верхняя панель
        top_layout = QHBoxLayout()
        
        # Кнопка переключения режима редактирования (переключатель) (переключатель)     
        self.edit_mode_btn = QPushButton("Режим редактирования")
        self.edit_mode_btn.setCheckable(True)
        self.edit_mode_btn.toggled.connect(self._on_edit_mode_toggled)
        top_layout.addWidget(self.edit_mode_btn)
        

        def setup_action_combo(
            action_combo, 
            btns:list, 
            fun_connect:Callable
        ):
            """
            Настройка комбо-бокса действий с заданными кнопками и функцией подключения.

            Аргументы:
                action_combo (QComboBox): Комбо-бокс, который нужно настроить.
                btns (list): Список кнопок, которые нужно добавить в комбо-бокс.
                fun_connect (Callable): Функция, которая будет подключена к сигналу currentIndexChanged комбо-бокса.

            Возвращает:
                None
            """

            for btn in btns:
                action_combo.addItem(btn)

            action_combo.setEditable(False)
            action_combo.setMaximumWidth(170)

            # Делаем первый пункт невыбираемым
            action_combo.model().item(0).setEnabled(False)
            action_combo.setCurrentIndex(0)
            action_combo.currentIndexChanged.connect(fun_connect)

            # Принудительное открытие вниз
            # action_combo.setPopupPolicy(QComboBox.PopupPolicy.InstantPopup)

        # Выпадающий список для действий в обычном режиме
        self.action_combo = QComboBox()
        setup_action_combo(
            action_combo=self.action_combo,
            btns=["▼ Действия с записями", "Добавить", "Редактировать", "Удалить", "Обновить"],
            fun_connect=self._on_action_selected
        )
        
        top_layout.addWidget(self.action_combo)

        # Выпадающий список для inline-действий (скрыт по умолчанию)
        self.inline_action_combo = QComboBox()
        setup_action_combo(
            action_combo=self.inline_action_combo,
            btns=["▼ Действия со строками", "Добавить строку", "Удалить строку", "Отменить изменения"],
            fun_connect=self._on_inline_action_selected
        )

        self.inline_action_combo.setVisible(False)
        top_layout.addWidget(self.inline_action_combo)

        def setup_button(name, fun_connect, set_flags=False):
            """
            Создает и настраивает кнопку QPushButton с указанным именем и подключает ее к функции.

            Аргументы:
                name (str): Текст, который будет отображаться на кнопке.
                fun_connect (Callable): Функция, которая будет вызываться при нажатии кнопки.
                set_flags (bool, optional): Флаг, указывающий, нужно ли устанавливать флаги включения и видимости кнопки в значение False. По умолчанию False.

            Возвращает:
                QPushButton: Настроенная кнопка QPushButton.
            """

            btn = QPushButton(name)
            btn.setEnabled(set_flags)
            btn.setVisible(set_flags)
            btn.clicked.connect(fun_connect)

            return btn

        # Кнопка сохранения (отдельная, показывается в режиме редактирования)
        self.save_changes_btn = setup_button(
            name="Сохранить изменения", 
            # fun_connect=self._save_changes, 
            fun_connect=self.save_all_changes, 
            set_flags=False
        )
        # self.save_changes_btn = QPushButton("Сохранить изменения")
        # self.save_changes_btn.clicked.connect(self._save_changes)
        # self.save_changes_btn.setEnabled(False)
        # self.save_changes_btn.setVisible(False)
        top_layout.addWidget(self.save_changes_btn)

        # self.cancel_all_btn = QPushButton("Отменить все")
        # self.cancel_all_btn.clicked.connect(self._cancel_all_changes)
        # self.cancel_all_btn.setVisible(False)          
        # self.cancel_all_btn.setEnabled(False)
        # self.cancel_all_btn = setup_button(
        #     name="Отменить все", 
        #     fun_connect=self._cancel_all_changes, 
        #     set_flags=False
        # )
        # top_layout.addWidget(self.cancel_all_btn)

        # # self.cancel_current_btn = QPushButton("Отменить текущую")
        # # self.cancel_current_btn.clicked.connect(self._cancel_current_row_changes)
        # # self.cancel_current_btn.setVisible(False)      
        # # self.cancel_current_btn.setEnabled(False)
        # self.cancel_current_btn = setup_button(
        #     name="Отменить текущую", 
        #     fun_connect=self._cancel_current_row_changes, 
        #     set_flags=False
        # )
        # top_layout.addWidget(self.cancel_current_btn)

        # Кнопка "Действие" (если она была указана) (например, "Приёмы")
        if self.action_button_text:
            self.action_btn = QPushButton(self.action_button_text)
            self.action_btn.clicked.connect(self._on_action_clicked)
            self.action_btn.setEnabled(False)
            top_layout.addWidget(self.action_btn)

        # Заполнение пустого пространства
        top_layout.addStretch()

        # Поле поиска
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Поиск...")
        self.search_edit.textChanged.connect(self._on_search_text_changed)
        top_layout.addWidget(self.search_edit)

        self.main_layout.addLayout(top_layout)

    @AppLogger.get_instance(
        name = 'ListUIMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _setup_table(self):
        """
        Установка таблицы для страницы со списком записей.

        Создает экземпляр класса FilterTableView, который является таблицей с возможностью сортировки.
        Устанавливает настройки для таблицы: сортировку по любому из столбцов, выбор строк в таблице,
        отключает редактирование ячеек и двойной клик на строке.

        Создает экземпляр класса DynamicTableModel, который является моделью данных для таблицы.
        Модель данных содержит список self.current_data, который является текущим списком данных, отображаемым
        в таблице. Затем создается экземпляр класса AdvancedFilterProxyModel, который является проксирующим моделью данных.
        Он получает модель данных self.source_model и позволяет фильтровать данные по любому из столбцов.

        Наконец, для таблицы self.table_view устанавливаются моделью данных self.proxy_model и настройки
        заголовка столбцов.
        """
        # Добавляем основной макет

        # Таблица
        self.table_view = FilterTableView()
        self.table_view.setSortingEnabled(True)
        self.table_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection) # В режиме просмотра (по умолчанию) – только одиночное выделение
        # self.table_view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        
        self.table_view.setMouseTracking(True)
        
        self.table_view.setEditTriggers(QAbstractItemView.NoEditTriggers) # Изначально двойной клик не редактирует ячейки (режим не редактирования)
        add_copy_paste_to_table(self.table_view) # Добавляем возможность копирования и вставки

        self.table_view.doubleClicked.connect(self._on_row_double_clicked)

        self.column_masks = {}
        for col_idx, col_info in enumerate(self.columns):
            field_name = col_info['name']
            config = self.field_configs.get(field_name, {})
            mask = config.get('input_mask')
            if mask:
                self.column_masks[col_idx] = mask

        # Модель таблицы
        self.source_model = DynamicTableModel(
            self.current_data, 
            self.columns,
            get_unique_values_func=self.get_unique_values_for_column,
            column_masks=self.column_masks,
        )

        self.source_model.row_modified.connect(self._on_row_modified) # Подключаем сигнал изменения строки для отслеживания изменений строк

        # self.source_model.checkbox_toggled.connect(self._on_checkbox_toggled) # Подключаем сигнал изменения строки для отслеживания изменений чекбоксов

        # Прокси-модель
        self.proxy_model = AdvancedFilterProxyModel()
        self.proxy_model.setSourceModel(self.source_model)
        self.table_view.setModel(self.proxy_model)

        # Настройка заголовка таблицы
        header = self.table_view.horizontalHeader()

        # Устанавливаем начальное состояние видимости чекбокс-столбца (скрыт)
        if hasattr(header, 'set_checkbox_column_visible'):
            header.set_checkbox_column_visible(False)

        if hasattr(header, 'set_get_unique_values_func'):
            header.set_get_unique_values_func(self.get_unique_values_for_column) # Подключаем сигнал изменения строки для отслеживания изменений чекбоксов
            header.filter_requested.connect(self.on_filter_requested) # Подключаем сигнал изменения строки для отслеживания изменений чекбоксов
            header.filter_clear_requested.connect(self.on_filter_clear) # Подключаем сигнал изменения строки для отслеживания изменений чекбоксов

        # tt = self.table_view.horizontalHeader().Visible
        self._setup_header_settings_table(header=header) # Настройка заголовка таблицы

        self._setup_header_visible_table(header=header) 
        
    @AppLogger.get_instance(
        name = 'ListUIMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _setup_header_visible_table(self, header):
        """
        Принудительно показывает заголовок и устанавливает минимальную высоту.

        Параметры:
            header (QHeaderView): Заголовок таблицы.
        """
        
        # Сохраняем нормальную высоту заголовка (если она не 0)
        if header.height() > 0:
            self._header_height = header.height()
        else:
            # Запасной вариант: высота по умолчанию
            self._header_height = 20    

        # Принудительно показываем заголовок
        # header.show()
        header.setMinimumHeight(self._header_height)
        # header.resizeSections(QHeaderView.ResizeToContents)   
        header.setVisible(True) # Показываем заголовок

    @AppLogger.get_instance(
        name = 'ListUIMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _setup_header_settings_table(self, header: QHeaderView) -> None:
        """
        Настраивает поведение заголовка: разрешает изменение размера столбцов,
        делает последний столбец растягивающимся.

        Args:
            header (QHeaderView): Заголовок таблицы.

        Returns:
            None
        """
        
        # header.setStretchLastSection(True) # Растянуть последний столбец
        # header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents) # Размеры столбцов под контент

        # Разрешаем пользователю изменять размеры столбцов
        header.setSectionsMovable(False)      # запрещаем перетаскивание столбцов (опционально)
        header.setSectionsClickable(True)     # кликабельность для сортировки

        # Устанавливаем режим для каждого столбца
        for col in range(header.count()):
            if col == header.count() - 1:
                # Последний столбец – растягиваемый
                header.setSectionResizeMode(col, QHeaderView.Stretch)
            else:
                # Остальные – изменяемые пользователем
                header.setSectionResizeMode(col, QHeaderView.Interactive)

        # Растяжение последнего столбца (дополнительная гарантия)
        header.setStretchLastSection(True)

        # self.table_view.horizontalHeader().setVisible(True) # показываем заголовок

    @AppLogger.get_instance(
        name = 'ListUIMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _setup_delegates(self):
        """
        Устанавливает делегаты для колонок на основе типов полей и field_configs.
        Приоритет: choices > widget_type (autocomplete, textarea, date, time) > тип поля
        """
        #  УТОЧНЕНИЕ! ОБЯЗАТЕЛЬНО прощитывать столбец по факту. в ином случае при добавлении системных столбцов - будет ошибка положения!
        # Словарь: тип -> класс делегата (и, возможно, дополнительные параметры)
        
        invert_tip = {
            'date': datetime.date,
            'time': datetime.time,
            # 'textarea': StringDelegate,
        }

        type_delegate_map = {
            # datetime.date: DateDelegate,
            # datetime.time: TimeDelegate,
            # datetime.date: DateStringDelegate,
            # datetime.time: TimeStringDelegate,
            datetime.date: DatePickerDelegate,
            datetime.time: TimePickerDelegate,
            bool: BoolDelegate,
            str: StringDelegate,
        }

        for col_idx, col_info in enumerate(self.columns):
            field_name = col_info['name']
            config = self.field_configs.get(field_name, {})

            # Определяем индекс колонки в модели (с учётом чекбокса)
            model_col = self.source_model.get_model_column_index(field_name)
            if model_col == -1:
                continue

            # Выпадающий список (choices) – наивысший приоритет
            choices = config.get('choices')
            if choices:
                delegate = ComboBoxDelegate(self.table_view, choices)
                self.table_view.setItemDelegateForColumn(model_col, delegate)
                continue 


            # Определяем тип поля и его реальный тип (для делегата) автоматически по параметрам
            widget_type = config.get('widget_type') # Специальные типы виджетов из field_configs

            if (widget_type is not None) and (widget_type  == 'textarea'):
                # field_type = invert_tip.get(widget_type) # определяем по типу поля  
                # Определяем режим только для чтения (если таблица не в режиме редактирования)
                # readonly = not self.edit_mode
                delegate = TextPopupDelegate(self.table_view, readonly=not self.edit_mode)
                self.table_view.setItemDelegateForColumn(model_col, delegate)   
                continue
            
            if widget_type:
                field_type = invert_tip.get(widget_type)            
            else:
                field_type = col_info.get('type')   # Определяем по реальному типу поля

            real_type = self._get_real_type( # определяем реальный тип
                field_type
            )

            # Автодополнение для строковых полей (если включено в конфигурации)
            if real_type == str and config.get('autocomplete', False):
                delegate = CompleterStringDelegate( # определяем делегата по реальному типу поля
                    self.table_view,
                    get_unique_values_func=self.get_unique_values_for_column,
                    column=col_idx
                )
                self.table_view.setItemDelegateForColumn(model_col, delegate)
                continue

            # # Стандартные делегаты по типу
            # delegate_class = type_delegate_map.get(# определяем класс делегата по реальному типу поля
            #     real_type
            # ) 
            # if delegate_class:
            #     delegate = delegate_class(self.table_view)
            #     self.table_view.setItemDelegateForColumn(model_col, delegate) # устанавливаем делегата
            #     continue

            # Стандартные делегаты по типу
            delegate_class = type_delegate_map.get(real_type)
            if delegate_class:
                # Для DatePickerDelegate и TimePickerDelegate передаём config
                if delegate_class in (DatePickerDelegate, TimePickerDelegate):
                    delegate = delegate_class(self.table_view, config=config)
                else:
                    delegate = delegate_class(self.table_view)
                self.table_view.setItemDelegateForColumn(model_col, delegate)
                continue

            if real_type == str:
                # Для строковых полей используем делегат с поддержкой масок
                mask = config.get('input_mask')
                column_masks = {model_col: mask} if mask else None
                delegate = StringDelegate(self.table_view, column_masks=column_masks)
                self.table_view.setItemDelegateForColumn(model_col, delegate)
                continue
            else:
                delegate_class = type_delegate_map.get(real_type)
                if delegate_class:
                    delegate = delegate_class(self.table_view)
                    self.table_view.setItemDelegateForColumn(model_col, delegate)
                    continue    

                # Для всех остальных типов (int, float и т.д.) оставляем делегат по умолчанию
            # Если тип не найден в словаре – оставляем стандартный делегат (например, для int, float)

    @AppLogger.get_instance(
        name = 'ListUIMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _update_text_popup_delegates_readonly(self):
        """Обновляет состояние readonly для всех TextPopupDelegate при смене режима редактирования."""
        if not hasattr(self, 'table_view'):
            return
        
        for col in range(self.table_view.model().columnCount()):
            delegate = self.table_view.itemDelegateForColumn(col)
            if delegate and isinstance(delegate, TextPopupDelegate):
                delegate.set_readonly(not self.edit_mode)

class ListFilterMixin:
    """
    Миксин для фильтрации данных через прокси-модель.

    Предоставляет методы для получения уникальных значений столбца
    и обработки текстового поиска.
    """

    # @AppLogger.get_instance(
    #     name = 'ListFilterMixin',
    #     # share_file_with = 'system',
    #     enable_file_logging = 'system',
    #     use_name_in_filename = False, # 'system',
    # ).log_execution_time(
    #     level = AppLogger._parse_log_level('DEBUG')
    # )
    # def on_filter_requested(self, column: int, operator: str, value, value2=None):
    #     """
    #     Обработка сигнала фильтрации от заголовка.

    #     :param column: номер столбца, для которого нужно установить фильтр
    #     :param operator: оператор фильтрации (eq, like, fuzzy, in)
    #     :param value: значение для сравнения (зависит от оператора)
    #     """
    #     # if operator == 'in':
    #     #     self.proxy_model.set_column_filter(column, selected_values=value)
    #     # elif operator == 'contains':
    #     #     self.proxy_model.set_column_filter(column, filter_text=value)
    #     # elif operator == 'clear':
    #     #     self.proxy_model.clear_column_filter(column)
    #     self.proxy_model.set_column_filter(column, operator, value, value2)

    @AppLogger.get_instance(
        name = 'ListFilterMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def on_filter_clear(self, column: int):
        """
        Очищает фильтр для столбца.

        Параметры:
            column (int): Номер столбца.
        """

        self.proxy_model.clear_column_filter(column)

    @AppLogger.get_instance(
        name = 'ListFilterMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def get_unique_values_for_column(self, column: int) -> List[str]:
        """
        Возвращает список уникальных значений для указанного столбца (через сервис).

        Параметры:
            column (int): Номер столбца в модели (с учётом чекбокс-столбца).

        Возвращает:
            list[str]: Уникальные значения в виде строк.
        """

        if self.service is None:
            return []
        
        col_name = self.columns[column]['name']
        values = self.service.get_unique_values(col_name)

        # Преобразуем в строки (могут быть даты, числа)
        return [str(v) for v in values]

    @AppLogger.get_instance(
        name = 'ListFilterMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _on_search_text_changed(self, text):
        """
        Обработчик изменения текста в поле поиска – устанавливает глобальный текстовый фильтр в прокси-модели.

        Параметры:
            text (str): Текст для поиска.
        """

        self.proxy_model.set_global_text_filter(text)
    
class ListInlineOpsMixin:
    """
    Миксин для inline-операций: добавление строки, пометка на удаление.

    Используется в режиме редактирования.
    """
    
    @AppLogger.get_instance(
        name = 'ListFilterMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    @Slot()
    def _add_inline_row(self):
        """
        Добавляет новую пустую строку в таблицу.

        Создаёт DTO со значениями по умолчанию:
        - для обязательных полей (required=True) – стандартные значения (текущая дата, 0, пустая строка и т.д.)
        - для необязательных полей – None
        - для контекстных параметров (например, patient_id) – значения из _context_params

        Временный ID генерируется отрицательным числом.

        Returns: 
            None
        """

        defaults = {}
        for col_info in self.columns:
            field_name = col_info['name']
            config = self.field_configs.get(field_name, {})

            # Пропускаем виртуальные и скрытые поля
            if config.get('virtual', False) or config.get('hidden', False):
                continue

            field_info = self.dto_class.model_fields.get(field_name)
            if field_info is None:
                continue

            field_type = self._get_real_type(field_info.annotation)
            default_value = None

            # Обязательное поле – заполняем значением по умолчанию
            if config.get('required', False):
                if field_type == datetime.date:
                    default_value = datetime.date.today()
                elif field_type == datetime.time:
                    default_value = datetime.time(0, 0)
                elif field_type == str:
                    default_value = ""
                elif field_type == int:
                    default_value = 0
                elif field_type == bool:
                    default_value = False
                # иные типы – None

            defaults[field_name] = default_value

        # Применяем контекстные параметры (например, patient_id)
        if hasattr(self, '_context_params') and self._context_params:
            for key, value in self._context_params.items():
                if key in self.dto_class.model_fields and (key not in defaults or defaults[key] is None):
                    defaults[key] = value

        # Для обратной совместимости с current_extra
        if self.current_extra:
            for key, value in self.current_extra.items():
                if key in self.dto_class.model_fields and key not in defaults:
                    defaults[key] = value

        try:
            new_dto = self.dto_class(**defaults)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось создать новую строку: {e}")
            self.logger.exception(f"Ошибка создания пустого DTO: {e}")
            return

        new_dto.id = self._next_temp_id
        self._next_temp_id -= 1

        row = self.source_model.add_row(new_dto)
        self.new_rows.add(row)
        self._set_row_color_by_source_row(row)
        self._update_save_button_state()

        proxy_index = self.proxy_model.mapFromSource(self.source_model.index(row, 0))
        if proxy_index.isValid():
            self.table_view.setCurrentIndex(proxy_index)
            self.table_view.scrollTo(proxy_index)

        self._update_selection_state()
        self.logger.info(f"Добавлена новая строка (индекс {row}, временный ID={new_dto.id})")


    # def _add_inline_row(self):
    #     """
    #     Добавляет новую пустую строку в таблицу.

    #     Создаёт DTO со значениями по умолчанию (пустые строки, сегодняшняя дата и т.п.),
    #     присваивает временный отрицательный ID, добавляет в модель и помечает как новую.
    #     """

    #     defaults = {}
    #     for col_info in self.columns:
    #         field_name = col_info['name']

    #         config = self.field_configs.get(field_name, {})
    #         # Пропускаем виртуальные и скрытые поля
    #         if config.get('virtual', False) or config.get('hidden', False):
    #             continue
            
    #         field_info = self.dto_class.model_fields.get(field_name)
    #         if field_info is None:
    #             continue

    #         # field_type = field_info.annotation
    #         field_type = self._get_real_type(field_info.annotation)

    #         origin = get_origin(field_type)
    #         if origin is Union:
    #             args = get_args(field_type)
    #             field_type = next((arg for arg in args if arg is not type(None)), None)

    #         if field_type is None:
    #             defaults[field_name] = None

    #         elif field_type == str:
    #             defaults[field_name] = ""

    #         elif field_type == int:
    #             defaults[field_name] = 0

    #         elif field_type == datetime.date:
    #             defaults[field_name] = datetime.date.today()

    #         elif field_type == datetime.time:
    #             defaults[field_name] = datetime.time(0, 0)

    #         elif field_type == bool:
    #             defaults[field_name] = False

    #         else:
    #             defaults[field_name] = None

    #     # Применяем контекстные параметры (сохранённые при входе на страницу)
    #     if hasattr(self, '_context_params') and self._context_params:
    #         for key, value in self._context_params.items():
    #             if key in self.dto_class.model_fields and (key not in defaults or defaults[key] is None):
    #                 defaults[key] = value
    #     # Для обратной совместимости (если current_extra всё ещё используется)
    #     if self.current_extra:
    #         for key, value in self.current_extra.items():
    #             if key in self.dto_class.model_fields and key not in defaults:
    #                 defaults[key] = value

    #     try:
    #         new_dto = self.dto_class(**defaults)
    #     except Exception as e:
    #         QMessageBox.critical(self, "Ошибка", f"Не удалось создать новую строку: {e}")
    #         self.logger.exception(f"Ошибка создания пустого DTO: {e}")
    #         return
        
    #     new_dto.id = self._next_temp_id
    #     self._next_temp_id -= 1

    #     row = self.source_model.add_row(new_dto)
    #     self.new_rows.add(row)
    #     # self._update_row_color(row)
    #     self._set_row_color_by_source_row(row)
    #     self._update_save_button_state()

    #     proxy_index = self.proxy_model.mapFromSource(self.source_model.index(row, 0))
    #     if proxy_index.isValid():
    #         self.table_view.setCurrentIndex(proxy_index)
    #         self.table_view.scrollTo(proxy_index)

    #     self._update_selection_state() # Обновляем состояние выделения

    #     self.logger.info(f"Добавлена новая строка (индекс {row})")

    @AppLogger.get_instance(
        name = 'ListFilterMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    @Slot()
    def _mark_selected_for_deletion(self):
        """
        Помечает выбранную строку на удаление.

        Для новых строк (временный ID) – удаляет из модели сразу.
        Для существующих – добавляет ID в `self.deleted_ids` и убирает из modified_ids.
        """

        if not self.selected_dto:
            return
        
        dto = self.selected_dto

        # Находим исходный индекс строки (нужен для цвета)
        source_row = self._find_source_row_by_id(dto.id)
        if source_row == -1:
            return
        
        if dto.id is not None and dto.id < 0:
            # Новая строка – удаляем из модели и из new_rows
            self.source_model.remove_row(source_row)
            self.new_rows.discard(source_row)
            self._update_save_button_state()

            # Очищаем правую панель, если она есть
            if hasattr(self, '_clear_right_panel'):
                self._clear_right_panel()

            return

        # Помечаем строку на удаление (для любых строк – и новых, и существующих)
        # self.deleted_rows.add(row)
        self.deleted_ids.add(dto.id)

        self._modified_ids_control(dto.id, False)  # # Если строка новая, убираем из соответствующих множеств
        

        self._update_selection_state() # Обновить состояние кнопки «Отменить текущую» (выделения нет → кнопка неактивна)

        # self.logger.info(f"Строка {row} помечена на удаление")
        self.logger.info(f"Строка с id {source_row} помечена на удаление")

class RowOperationsMixin:
    """
    Миксин для операций над строками: отмена изменений и удаление с учётом выделения.
    Требует наличия в классе-наследнике:
        - self.source_model (DynamicTableModel)
        - self.new_rows (set)
        - self.deleted_ids (set)
        - self.modified_ids (set)
        - self.original_data (dict)
        - self.selected_dto (Any)
        - self.service (сервис с методами get_by_id, delete)
        - self.logger (AppLogger)
        - self._clear_drafts(entity_id) (метод для очистки черновиков)
        - self._modified_ids(entity_id, if_add) (метод для изменения modified_ids)
        - self._set_row_color_by_source_row(source_row) (метод обновления цвета)
        - self._update_save_button_state() (метод обновления состояния кнопки сохранения)
        - self._update_selection_state() (метод обновления выделения)
        - self._clear_right_panel() (опционально, для страниц с правой панелью)
        - self.update_details(dto) (опционально, для страниц с деталями)
    """

    @AppLogger.get_instance(
        name='RowOperationsMixin',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def _cancel_rows(self, entity_ids: list) -> None:
        """
        Отменяет изменения для списка указанных идентификаторов сущностей.

        Args:
            entity_ids (list): Список ID сущностей (могут быть отрицательными для новых строк).
        """
        if not entity_ids:
            return

        if len(entity_ids) == 0:
            return

        current_id = self.selected_dto.id if self.selected_dto else None

        # Сначала отменяем все, кроме текущего (если он в списке)
        for eid in entity_ids:
            if eid == current_id:
                continue
            self._cancel_row(eid, update_right_panel=False)

        # Затем отменяем текущий (если есть) с обновлением правой панели
        if current_id is not None and current_id in entity_ids:
            self._cancel_row(current_id, update_right_panel=True)
        # Если текущий не был отменён, но после отмены других строк он мог измениться,
        # перезагружаем его данные в правую панель
        elif self.selected_dto is not None:
            try:
                fresh_dto = self.service.get_by_id(self.selected_dto.id)
                if hasattr(self, 'update_details'):
                    self.update_details(fresh_dto)
            except Exception as e:
                self.logger.exception(f"Ошибка обновления правой панели после отмены: {e}")

    @AppLogger.get_instance(
        name='RowOperationsMixin',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def _cancel_row(self, entity_id: int, update_right_panel: bool = True) -> None:
        """
        Отменяет изменения для одной строки по ID.

        Args:
            entity_id (int): ID сущности.
            update_right_panel (bool): Нужно ли обновить правую панель после отмены.
        """
        # Найти исходный индекс строки (в source_model)
        source_row = self._find_source_row_by_id(entity_id)
        if source_row == -1:
            self.logger.warning(f"Строка с id={entity_id} не найдена в модели")
            return

        # Если это новая строка (временный ID)
        if entity_id is not None and entity_id < 0:
            self.source_model.remove_row(source_row)
            self.new_rows.discard(source_row)
            self._clear_drafts(entity_id)

            self.table_view.clearSelection()
            self.selected_dto = None
            if hasattr(self, '_clear_right_panel'):
                self._clear_right_panel()
                 
            self._update_selection_state() 
            self._update_save_button_state()
            self.logger.debug(f"Новая строка с id={entity_id} удалена")
            return

        # Существующая строка (id > 0)
        self._clear_drafts(entity_id)

        try:
            fresh_dto = self.service.get_by_id(entity_id)
        except Exception as e:
            self.logger.exception(f"Ошибка загрузки свежих данных для id={entity_id}: {e}")
            QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить данные: {e}")
            return

        self.source_model.update_row(source_row, fresh_dto)
        self.original_data[source_row] = fresh_dto

        if entity_id in self.modified_ids:
            self._modified_ids(entity_id, False)

        if entity_id in self.deleted_ids:
            self.deleted_ids.discard(entity_id)

        self._set_row_color_by_source_row(source_row)

        if update_right_panel and hasattr(self, 'update_details'):
            self.update_details(fresh_dto)

        self._update_save_button_state()
        self._update_selection_state()
        self.source_model.set_checkbox_state(source_row, False)

    @AppLogger.get_instance(
        name='RowOperationsMixin',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def _perform_deletion(
        self,
        ids_to_delete: Set[int],
        current_dto_to_clear: Optional[Any] = None
    ) -> None:
        """
        Помечает записи на удаление, удаляет из модели новые строки, сбрасывает чекбоксы.

        Args:
            ids_to_delete (set): Множество ID для удаления.
            current_dto_to_clear (Optional[Any]): Если передан и его ID входит в ids_to_delete,
                правая панель очищается.
        """
        if not ids_to_delete:
            return

        for entity_id in list(ids_to_delete):
            source_row = self._find_source_row_by_id(entity_id)
            if source_row == -1:
                continue

            dto = self.source_model.get_item_at_row(source_row)
            if dto is None:
                continue

            if dto.id is None or dto.id < 0:  # новая строка
                self.source_model.remove_row(source_row)
                self.new_rows.discard(source_row)
                self.deleted_ids.discard(entity_id)
            else:
                self.deleted_ids.add(entity_id)
                self._clear_drafts(entity_id)# Очищаем черновики для этого временного ID
                if entity_id in self.modified_ids:
                    self._modified_ids(entity_id, False)
                self._set_row_color_by_source_row(source_row)

        self._clear_checkboxes()
        if current_dto_to_clear is not None and current_dto_to_clear.id in ids_to_delete:
            self.selected_dto = None
            if hasattr(self, '_clear_right_panel'):
                self._clear_right_panel()

        self._update_save_button_state()
        self.table_view.viewport().update()

class DynamicListPage(
    CheckboxSelectionMixin,
    SelectionDialogMixin,
    ListSelectionMixin,
    ListDataMixin,
    ListChangesMixin,
    RowOperationsMixin, # Миксин для операций над строками: отмена изменений и удаление с учётом выделения
    ListEditModeMixin,
    ListSaveMixin,
    ListUIMixin,
    ListFilterMixin,
    AdvancedFilterMixin,
    ListInlineOpsMixin,
    BasePage,
    IDynamicListController, # Интерфейс для управления динамическим списком записей
): 
    """
    Универсальная страница списка с поддержкой inline-редактирования, фильтрации,
    сортировки и массовых операций.
    Добавлена возможность отложенного сохранения изменений через кнопку «Сохранить изменения».

    Страница имеет два режима:
        - Обычный режим: строки нельзя редактировать прямо в таблице. Двойной клик по строке
          испускает сигнал `action_requested` (обычно для перехода к детальной странице).
          Добавление/редактирование/удаление выполняется через отдельные формы (сигналы
          `add_requested`, `edit_requested`, `delete_requested`).
        - Режим редактирования: включается кнопкой «Режим редактирования». В этом режиме
          появляется столбец чекбоксов, строки можно редактировать прямо в таблице,
          добавлять/удалять строки и сохранять изменения через кнопку «Сохранить изменения».

    Сигналы:
        add_requested (Signal): Вызывается при нажатии «Добавить» в обычном режиме.
        edit_requested (Signal(object)): Вызывается при выборе «Редактировать» (передаётся DTO).
        delete_requested (Signal(object)): Вызывается при удалении (передаётся DTO).
        action_requested (Signal(object)): Вызывается при двойном клике в обычном режиме.

    Параметры инициализации:
        service: Сервис для работы с сущностью (должен реализовывать методы `get_all`,
                 `create`, `update`, `delete`, `get_unique_values` и пр.).
        loader_func (callable): Функция, возвращающая список DTO для отображения.
        dto_class (Type[BaseModel]): Класс DTO.
        field_configs (Dict[str, Dict]): Конфигурация полей.
        page_title (str): Заголовок страницы (отображается в breadcrumbs).
        add_action_text (str): Текст кнопки «Добавить» в обычном режиме.
        action_button_text (Optional[str]): Текст дополнительной кнопки (например, «Приёмы»).
        parent (Optional[QWidget]): Родительский виджет.
        exclude_columns (Optional[List[str]]): Список имён полей, которые не должны отображаться.

    Пример создания страницы списка пациентов:
        >>> page = DynamicListPage(
        ...     service=get_patient_service(),
        ...     loader_func=lambda extra: get_patient_service().get_all_patients(),
        ...     dto_class=PatientDTO,
        ...     field_configs=PATIENT_CONFIG,
        ...     page_title="Пациенты",
        ...     add_action_text="Добавить пациента",
        ...     action_button_text="Приёмы",
        ... )
        >>> page.add_requested.connect(lambda: self.page_manager.switch_to('patient_edit'))
        >>> page.edit_requested.connect(lambda dto: self.page_manager.switch_to('patient_edit', extra_data={'id': dto.id}))
    """
 
    add_requested = Signal() # сигнал для добавления (можно не использовать, если добавляем строку напрямую)
    edit_requested = Signal(object) # сигнал для открытия формы редактирования
    delete_requested = Signal(object) # сигнал для удаления (с подтверждением)
    action_requested = Signal(object)  # дополнительное действие
    changes_saved = Signal()  # сигнал для сохранения изменений

    # detail_requested = Signal(object) # сигнал для перехода к детальной странице (двойной клик
        
    @AppLogger.get_instance(
        name = 'DynamicListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def __init__(
        self,
        service,  # сервис, используемый для редактирования записи
        loader_func,  # функция, которая возвращает список данных
        dto_class,  # класс DTO, используемый для создания записи
        field_configs,  # внешняя конфигурация
        page_title="Список",  # заголовок страницы
        add_action_text="Добавить",  # текст кнопки добавления
        action_button_text=None,  # текст дополнительной кнопки (если задана)
        # edit_on_double_click=True,  # True, если редактирование должно быть доступно при двойном нажатии на строке
        parent=None,  # родительский виджет
        exclude_columns=None,
    ):
        """
        Инициализирует страницу списка.

        Параметры:
            service: Сервис с методами get_all, create, update, delete, get_unique_values.
            loader_func (callable): Функция, возвращающая список DTO.
            dto_class (Type[BaseModel]): Класс DTO.
            field_configs (Dict[str, Dict]): Конфигурация полей.
            page_title (str): Заголовок страницы.
            add_action_text (str): Текст кнопки «Добавить».
            action_button_text (Optional[str]): Текст дополнительной кнопки (если None – не создаётся).
            parent (Optional[QWidget]): Родительский виджет.
            exclude_columns (Optional[List[str]]): Имена полей, которые не отображать.
        """

        super().__init__(parent)

        self.logger = AppLogger.get_instance(
            name = f"gui.{self.__class__.__name__}",
            # share_file_with = 'user',
            enable_file_logging = 'user',
            use_name_in_filename = False, # 'user',
        )

        self._checkbox_setup_done = False

        self._delegates_setup_done = False

        self.service = service
        self.loader_func = loader_func
        # self.columns = columns
        self.dto_class = dto_class
        self.field_configs = field_configs
        self.page_title = page_title
        self.add_action_text = add_action_text
        self.action_button_text = action_button_text
        # self.edit_on_double_click = edit_on_double_click

        self.exclude_columns = exclude_columns or []

        self._saved_row = -1  # сохранённый индекс строки

        self._next_temp_id = -1 # генерация временных ID для новых строк

        self._header_height = 20  # значение по умолчанию

        # Словарь для отслеживания изменённых строк:
        # modified_rows: set of row indices, которые были изменены пользователем (но ещё не сохранены)
        # self.modified_rows: Set[int] = set()
        self.modified_ids: Set[int] = set()    # id записей, изменённых пользователем
        # deleted_rows: set of row indices, помеченные на удаление (соответствующие DTO будут удалены при сохранении)
        # self.deleted_rows: Set[int] = set()
        self.deleted_ids: Set[int] = set()     # id записей, помеченных на удаление
        # new_rows: set of row indices, которые были добавлены через inline-добавление (пока не реализовано)
        self.new_rows: Set[int] = set()
        # Сопоставление индекса строки с исходным DTO для восстановления при отмене (опционально)
        self.original_data: Dict[int, Any] = {}
        # Режим редактирования (по умолчанию выключен)
        self.edit_mode: bool = False #

        # сохраним основной layout как атрибут
        self.main_layout = QVBoxLayout(self) 
        # строим список колонок
        self.columns = self._build_columns()   
        self.current_data = []  # список данных, которые сейчас отображаются на странице  # список DTO
        self.selected_dto = None  # выбранный DTO (объект с атрибутами, соответствующими колонкам)
        self._selection_connected = False  # флаг, который указывает, является ли соединение между сигналами selectionChanged и слотом _on_selection_changed установленным
        self.current_extra = None  # запоминаем последние переданные параметры
        self._context_params = {}

        # настройка интерфейса страницы
        self._needs_refresh = False  # флаг, который указывает, нужно ли перезагружать данные при следующем входе на страницу

        self._data_loaded = False   # флаг, что данные ещё не загружены
        self._setup_ui()
        
        # self._load_data() # загрузка данных на страницу

    @AppLogger.get_instance(
        name='DynamicListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _reapply_delegates(self):
        """Очищает все делегаты и переустанавливает их заново с учётом текущего маппинга колонок."""
        # Очищаем все существующие делегаты
        for col in range(self.table_view.model().columnCount()):
            self.table_view.setItemDelegateForColumn(col, None)
        # Устанавливаем заново
        self._setup_delegates()

    @AppLogger.get_instance(
        name='DynamicListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _setup_ui(self):
        super()._setup_ui()

        self._setup_filter_bar()   # добавляем строку фильтров

        if not self._checkbox_setup_done:
            self._setup_checkbox_column()
            self._checkbox_setup_done = True
        
        if not self._delegates_setup_done:
            self._setup_delegates()
            self._delegates_setup_done = True

    @AppLogger.get_instance(
        name='DynamicListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    @preserve_selection()
    def _on_edit_mode_toggled(self, checked: bool):

           
        self._store_current_row() # Сохраняем текущее выделение (для возможного восстановления)

        # Вызываем родительский (он переключит edit_mode)
        super()._on_edit_mode_toggled(checked)

        # Сбрасываем выделение, чтобы избежать артефактов
        self.table_view.clearSelection()
        self._update_selection_state()

        # 0==0

        # Включаем/отключаем видимость чекбокс-столбца
        self.source_model.set_checkbox_column_visible(self.edit_mode)

        # Синхронизируем состояние в заголовке
        header = self.table_view.horizontalHeader()  # получаем заголовок

        if hasattr(header, 'set_checkbox_column_visible'):
            header.set_checkbox_column_visible(self.edit_mode)

        self._ensure_checkbox_header_menu() # добавляем пункты в контекстное меню

        self._reapply_delegates() # переустанавливаем делегаты (Автоопределение типа столбца при появлении доп столбцов)
        
        self._update_text_popup_delegates_readonly() # Обновляем readonly у всех TextPopupDelegate

        if not self.edit_mode:
            self._clear_checkboxes() # снимаем все чекбоксы
            self.deleted_ids.clear() # очищаем список удалённых
            self._update_save_button_state() # обновляем состояние кнопки сохранения

        self._setup_header_settings_table(header=header) # Принудительно восстанавливаем растяжение последнего столбца
        
        self._setup_header_visible_table(header=header)

        # Обновляем геометрию таблицы
        # self.table_view.resizeColumnsToContents() # обновляем размеры столбцов

        # self.table_view.updateGeometry() # обновляем геометрию

    @AppLogger.get_instance(
        name='DynamicListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _has_current_row_changes(self) -> bool:
        """
        Проверяет, есть ли несохранённые изменения у текущей выбранной строки.
        Учитывает:
        - новые строки (id < 0)
        - modified_ids и deleted_ids
        - черновики заметки/фото (если есть метод _has_draft_changes_for_appointment)
        """
        if not self.selected_dto:
            return False
        
        entity_id = self.selected_dto.id
        if entity_id is None:
            return False
        
        # Новая строка (временный ID) – всегда есть изменения
        if entity_id < 0:
            return True
        
        # Проверяем наличие в множествах изменённых/удалённых
        if entity_id in self.modified_ids or entity_id in self.deleted_ids:
            return True
        
        # Если есть метод проверки черновиков (для AppointmentListPage), используем его
        if hasattr(self, '_has_draft_changes_for_appointment'):
            return self._has_draft_changes_for_appointment(entity_id)
        
        return False

    @AppLogger.get_instance(
        name='DynamicListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    @preserve_selection()
    def _cancel_all_changes(self):
        """
        Отменить все несохранённые изменения:
        - очистить modified_ids, deleted_ids, new_rows
        - очистить черновики (через _clear_drafts)
        - перезагрузить данные из БД
        - сбросить правую панель, если есть
        """
        self.logger.info("Отмена всех изменений")

        # 1. Очистить все множества

        self._clear_selection() # очистить выделение (в базовом классе это заглушка, в AppointmentListPage реализован)

        # 2. Очистить черновики (если есть переопределённый метод в наследнике)
        self._clear_drafts()  # очистить черновики  (в базовом классе это заглушка, в AppointmentListPage реализован)

        # 3. Перезагрузить данные из БД
        self._load_data()

        # 5. Обновить состояние кнопки сохранения (она должна стать неактивной)
        self._update_save_button_state()

        # Обновить состояние кнопки «Отменить текущую» (выделения нет → кнопка неактивна)
        self._update_selection_state()

        # 6. Если мы в режиме редактирования, остаёмся в нём, но все изменения отменены
        self.logger.debug("Все изменения отменены")



    # @AppLogger.get_instance(
    #     name='DynamicListPage',
    #     # share_file_with = 'system',
    #     enable_file_logging = 'system',
    #     use_name_in_filename = False, # 'system',
    # ).log_execution_time(
    #     level=AppLogger._parse_log_level('DEBUG')
    # )
    # def _cancel_rows(self, entity_ids:list) -> None:
    #     """
    #     Отменяет изменения для списка указанных идентификаторов сущностей.

    #     Метод последовательно обрабатывает каждый ID из переданного списка:
    #         1. Сначала отменяет изменения для всех ID, кроме текущего выбранного
    #         (если он есть в списке). Для этих вызовов правые панели не обновляются.
    #         2. Затем, если текущий выбранный ID присутствует в списке, отменяет
    #         изменения для него с принудительным обновлением правой панели.
    #         3. Если текущий выбранный ID не был отменён, но после отмены других
    #         строк его DTO мог измениться, перезагружает его данные из БД
    #         и обновляет правую панель (если она существует).

    #     Args:
    #         entity_ids (list): Список идентификаторов сущностей (ID записей),
    #                         для которых необходимо отменить изменения.
    #                         Может содержать как положительные (существующие),
    #                         так и отрицательные (временные, новые) ID.

    #     Returns:
    #         None

    #     Note:
    #         Для существующих записей (id > 0) метод выполняет:
    #             - очистку черновиков,
    #             - перезагрузку свежего DTO из БД,
    #             - обновление модели и original_data,
    #             - удаление ID из множеств modified_ids и deleted_ids,
    #             - обновление цвета строки,
    #             - (опционально) обновление правой панели через update_details.

    #         Для новых записей (id < 0) метод удаляет строку из модели,
    #         очищает черновики и сбрасывает выделение.

    #         Если у класса есть метод update_details (как у AppointmentListPage),
    #         он будет вызван; в базовом классе DynamicListPage проверка hasattr
    #         предотвращает ошибку.
    #     """

    #     if not entity_ids:
    #         return
        
    #     if len(entity_ids) == 0 :
    #         return

    #     current_id = self.selected_dto.id if self.selected_dto else None
    
    #     # Сначала отменяем все, кроме текущего (если он в списке)
    #     for eid in entity_ids:
    #         if eid == current_id:
    #             continue
    #         self._cancel_row(eid, update_right_panel=False)
        
    #     # Затем отменяем текущий (если есть) с обновлением правой панели
    #     if current_id is not None and current_id in entity_ids:
    #         self._cancel_row(current_id, update_right_panel=True)
    #     # Если текущий не был отменён, но после отмены других строк он мог измениться,
    #     # перезагружаем его данные в правую панель
    #     elif self.selected_dto is not None:
    #         try:
    #             fresh_dto = self.service.get_by_id(self.selected_dto.id)
    #             if hasattr(self, 'update_details'):
    #                 self.update_details(fresh_dto)
    #         except Exception as e:
    #             self.logger.exception(f"Ошибка обновления правой панели после отмены: {e}")

    # @AppLogger.get_instance(
    #     name='DynamicListPage',
    #     # share_file_with = 'system',
    #     enable_file_logging = 'system',
    #     use_name_in_filename = False, # 'system',
    # ).log_execution_time(
    #     level=AppLogger._parse_log_level('DEBUG')
    # )
    # def _cancel_row(
    #     self, 
    #     entity_id,
    #     update_right_panel:bool=True,
    # ):

    #     # Найти исходный индекс строки (в source_model)
    #     source_row = self._find_source_row_by_id(entity_id)

    #     if source_row == -1:
    #         self.logger.warning(f"Строка с id={entity_id} не найдена в модели")
    #         return
        
    #     # Если это новая строка (временный ID)
    #     if entity_id is not None and entity_id < 0:

    #         # Удаляем строку из модели
    #         self.source_model.remove_row(source_row)
    #         self.new_rows.discard(source_row)

    #         # Очищаем черновики для этого временного ID
    #         self._clear_drafts(entity_id)
            
    #         # Снимаем выделение
    #         self.table_view.clearSelection()
    #         self.selected_dto = None
    #         if hasattr(self, '_clear_right_panel'):
    #             self._clear_right_panel()

    #         # Обновляем состояние кнопки сохранения
    #         self._update_save_button_state()
            
    #         self.logger.debug(f"Новая строка с id={entity_id} удалена")
    #         return

    #     # Существующая строка (id > 0)
    #     # 1. Очистить черновики для этого приёма (если есть)
    #     self._clear_drafts(entity_id)

    #     # 2. Перезагрузить DTO из БД
    #     try:
    #         fresh_dto = self.service.get_by_id(entity_id)
    #     except Exception as e:
    #         self.logger.exception(f"Ошибка загрузки свежих данных для id={entity_id}: {e}")
    #         QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить данные: {e}")
    #         return

    #     # 3. Обновить модель (заменить DTO)
    #     self.source_model.update_row(source_row, fresh_dto)
    #     # Обновить original_data
    #     self.original_data[source_row] = fresh_dto

    #     # 4. Убрать из modified_ids, если был
    #     if entity_id in self.modified_ids:
    #         # self.modified_ids.discard(entity_id)
    #         self._modified_ids(entity_id, False)

    #     # убираем из deleted_ids, если был помечен на удаление
    #     if entity_id in self.deleted_ids:
    #         self.deleted_ids.discard(entity_id)

    #     # 5. Обновить цвет строки
    #     self._set_row_color_by_source_row(source_row)

    #     # 6. Если есть правая панель, обновить её
    #     if update_right_panel and hasattr(self, 'update_details'):
    #         self.update_details(fresh_dto)

    #     # 7. Обновить состояние кнопки сохранения
    #     self._update_save_button_state()

    #      # 8. Обновить состояние кнопки «Отменить текущую» и другие элементы UI
    #     self._update_selection_state()

    #     self.source_model.set_checkbox_state(source_row, False)

    #     # # 8. Обновить состояние кнопки «Отменить текущую»
    #     # if hasattr(self, 'cancel_current_btn'):
    #     #     self.cancel_current_btn.setEnabled(self._has_current_row_changes())


    @AppLogger.get_instance(
        name='DynamicListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _cancel_current_row_changes(self):
        """
        Отменить изменения только для текущей выбранной строки.
        - Если строка новая (id < 0) → удалить строку.
        - Если строка существующая → перезагрузить из БД, очистить черновики,
        убрать из modified_ids, обновить модель.
        """

        self._cancel_with_selection_prompt() 
        


    @AppLogger.get_instance(
        name='DynamicListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _clear_drafts(self, appointment_id=None):
        """
        Заглушка для страниц без черновиков.
        Переопределяется в AppointmentListPage.
        """
        pass

    @AppLogger.get_instance(
        name='DynamicListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _has_unsaved_changes(self) -> bool:
        """
        Возвращает True, если есть несохранённые изменения:
        - изменённые/удалённые/новые строки в таблице приёмов
        - черновики заметки или фото для текущего приёма

        :return: True, если есть несохранённые изменения, False - иначе
        :rtype: bool
        """
        
        # Определяем, есть ли изменения
        
        # if self.modified_rows or self.deleted_rows or self.new_rows:
        if bool(self.modified_ids or self.deleted_ids or self.new_rows):
            return True
        
        # Добавляем проверку черновиков для текущего выбранного приёма
        # if self.selected_dto:
        #     appointment_id = self.selected_dto.id

        #     # Заметка изменена?
        #     if appointment_id in self._draft_note_current:
        #         if self._draft_note_current[appointment_id] != self._draft_note_original[appointment_id]:
        #             return True

        #     # Или фото изменены?
        #     if appointment_id in self._draft_photos:
        #         # Если есть ожидающие фото, то изменение есть
        #         if len(self._draft_photos[appointment_id].get('pending_photos', []))>0:
        #             return True
                
        #         # Если есть удалённые фото, то изменение есть
        #         if len(self._draft_photos[appointment_id].get('deleted_photo_ids', []))>0:
        #             return True
                
        #         # Если есть изменённые фото, то изменение есть
        #         if len(self._draft_photos[appointment_id].get('modified_photo_ids', []))>0:
        #             return True
                
        return False



    @AppLogger.get_instance(
        name = 'DynamicListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def on_leave(self):
        """
        Вызывается при уходе со страницы.
        Дополнительные действия, такие как очистка черновиков, если нужно.
        """
        super().on_leave()
        
        # Выход из режима редактирования
        if self.edit_mode:
            self._exit_edit_mode() # выход из режима редактирования

        # Дополнительные действия, например, очистка черновиков, если нужно
        # self._clear_drafts()  # если требуется    

    @AppLogger.get_instance(
        name = 'DynamicListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _build_columns(self):
        """
        Создаёт список колонок из field_configs и dto_class.

        Возвращает список словарей, где каждый словарь содержит информацию о колонке:
        - name: имя поля в DTO
        - title: заголовок поля (если не задан, то берется из имени поля)

        Field_configs - это список словарей, где каждый словарь содержит информацию о поле:
        - name: имя поля в DTO
        - title: заголовок поля (если не задан, то берется из имени поля)
        - choices: список значений, которые доступны для поля (если не задан)
        - editable: флаг, который указывает, является ли поле доступным для редактирования (если не задан)

        Dto_class - это класс DTO, который содержит информацию о полях и их значения.
        """
        
        cols = []
        # Сортировка по order (если order не задан, ставим в конец)
        # sorted_fields = sorted(self.field_configs.items(), key=lambda x: x[1].get('order', 999))
        # for field_name, config in sorted_fields:
        for field_name, config in self.field_configs.items():
            if config.get('hidden', False):  # по умолчанию False # нужно ли скрывать объект
                continue

            if field_name in self.exclude_columns:
                continue

            # Получаем тип поля из DTO (по умолчанию str, если поля нет)
            field_info = self.dto_class.model_fields.get(field_name)
            field_type = field_info.annotation if field_info else str

            # field_type = self.dto_class.model_fields[field_name].annotation
            cols.append({
                'name': field_name,
                'title': config.get('title', field_name.replace('_', ' ').title()),
                'type': field_type,
                'editable': config.get('editable', False),
                'choices': config.get('choices'),
            })
        # Сортировка по order
        return sorted(
            cols, 
            key=lambda c: self.field_configs.get(
                c['name'], {}
            ).get(
                'order',
                len(self.field_configs)
                # 0
            )
        )


    # ----------------------- Действия с выделенной строкой (формы) -----------------------

    @AppLogger.get_instance(
        name = 'DynamicListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    @Slot()
    def _on_edit_clicked(self):
        """Открывает форму редактирования для выбранной строки."""
        if self.selected_dto:
            self.edit_requested.emit(self.selected_dto)

    @AppLogger.get_instance(
        name = 'DynamicListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    @Slot()
    def _on_delete_clicked(self):
        """
        Удаление через форму (с подтверждением). Используется, когда режим редактирования выключен.
        """

        if self.selected_dto:   
            reply = QMessageBox.question(
                self, "Подтверждение",
                "Удалить выбранную запись?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )

            if reply == QMessageBox.StandardButton.Yes:
                self.delete_requested.emit(self.selected_dto)
      
    @AppLogger.get_instance(
        name = 'DynamicListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )      
    @Slot()
    def _on_action_clicked(self):
        """Дополнительное действие (например, переход к списку приёмов)."""

        if self.selected_dto:
            self.action_requested.emit(self.selected_dto)

    # ----------------------- Загрузка данных и обработка выделения -----------------------

    @AppLogger.get_instance(
        name = 'DynamicListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _update_selection_state(self):
        """Обновляет состояние выбранного DTO и кнопок на основе текущего выделения в таблице."""

        selection_model = self.table_view.selectionModel()
        if selection_model:

            indexes = selection_model.selectedIndexes()
            if indexes:
                proxy_index = indexes[0]
                source_index = self.proxy_model.mapToSource(proxy_index)
                self.selected_dto = self.source_model.get_item_at_row(source_index.row())
            else:
                self.selected_dto = None
        else:
            self.selected_dto = None

        # Обновляем состояние дополнительной кнопки, если она есть
        if hasattr(self, 'action_btn') and self.action_btn:
            self.action_btn.setEnabled(self.selected_dto is not None)
        
        # # Управляем кнопкой «Отменить текущую»
        # if hasattr(self, 'cancel_current_btn'):
        #     self.cancel_current_btn.setEnabled(self._has_current_row_changes())
    
    # @AppLogger.get_instance(
    #     name = 'DynamicListPage',
    #     enable_file_logging = 'system',
    #    use_name_in_filename = False, # 'system',
    # ).log_execution_time(
    #     level = AppLogger._parse_log_level('DEBUG')
    # )
    def _on_selection_changed(
        self, 
        selected, 
        deselected
    ):
        """
        Обработка события изменения выбора в таблице.

        Если была выбрана строка, то извлекается DTO, соответствующий выбранной строке,
        иначе, если не была выбрана ни одна строка, то извлекается None.

        Также изменяет доступность кнопки удаления и дополнительной кнопки (если задана).

        :param selected: список выбранных индексов
        :type selected: QItemSelection
        :param deselected: список индексов, которые были сняты с выбора
        :type deselected: QItemSelection
        """
        self._update_selection_state()

    @AppLogger.get_instance(
        name = 'DynamicListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _on_row_double_clicked(self, index):
        """
        Обработка двойного клика в обычном режиме (не редактирование).
        Вызывает action_requested для перехода на следующий фрейм.
        """

        if not self.edit_mode and index.isValid(): # если индекс валиден
            source_index = self.proxy_model.mapToSource(index) # получаем индекс в исходном модели
            dto = self.source_model.get_item_at_row(source_index.row()) # 
            if dto:
                self.action_requested.emit(dto) # вызываем сигнал
                
    
    @AppLogger.get_instance(
        name = 'DynamicListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def showEvent(self, event):
        """
        Обработка события отображения страницы.

        Подключает функцию super().showEvent(), а также подключает сигнал selectionChanged к слоту _on_selection_changed,
        если он не был подключен ранее. Это необходимо, чтобы слушатель _on_selection_changed срабатывал,
        когда пользователь выбирает строку в таблице.
        """
        super().showEvent(event)

        # Подключаем сигнал selectionChanged к слоту _on_selection_changed

        self.logger.debug(f'not self._selection_connected : {not self._selection_connected}')

        if not self._selection_connected:
            selection_model = self.table_view.selectionModel()
            
            self.logger.debug(f'if selection_model is not None : {selection_model is not None}')

            if selection_model is not None:
                # Подключаем сигнал selectionChanged к слоту _on_selection_changed
                selection_model.selectionChanged.connect(self._on_selection_changed)
                self._selection_connected = True

        self._ensure_checkbox_header_menu() # обновляем контекстное меню с чекбоксами

    # ----------------------- Вспомогательные методы для inline-добавления (опционально) -----------------------

    # @AppLogger.get_instance(
    #     name = 'DynamicListPage',
    #     # share_file_with = 'system',
    #     enable_file_logging = 'system',
    #     use_name_in_filename = False, # 'system',
    # ).log_execution_time(
    #     level = AppLogger._parse_log_level('DEBUG')
    # )
    # def add_new_row(self, dto: Any = None):
    #     """
    #     Добавляет новую пустую строку в таблицу (для inline-создания).
    #     Если dto не передан, создаётся пустой DTO через конструктор.
    #     """

    #     if not self.edit_mode:
    #         self.logger.warning("add_new_row вызван вне режима редактирования")
    #         return

    #     # Игнорируем переданный dto, так как он может быть неполным.
    #     # Вместо этого используем корректную логику _add_inline_row.
    #     self._add_inline_row()
        
    #     # if dto is None:
    #     #     # Создаём пустой DTO (все поля None, кроме обязательных)
    #     #     dto = self.dto_class()

    #     # row = self.source_model.add_row(dto)
    #     # self.new_rows.add(row)
    #     # # self._update_row_color(row)
    #     # self._set_row_color_by_source_row(row)
    #     # self._update_save_button_state()

    #     # # Прокручиваем к новой строке
    #     # proxy_index = self.proxy_model.mapFromSource(self.source_model.index(row, 0))

    #     # self.logger.debug(
    #     #     f'if proxy_index.isValid() : {proxy_index.isValid()}'
    #     # )
    #     # if proxy_index.isValid():
    #     #     self.table_view.scrollTo(proxy_index)


    # ----------------------- слоты для обработки выбора действий -----------------------

    @AppLogger.get_instance(
        name = 'DynamicListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    @Slot(int)
    def _on_action_selected(self, index):
        """Обрабатывает выбор действия в обычном режиме."""
        if index == 1:  # Добавить
            self.add_requested.emit()
        elif index == 2:  # Редактировать
            if self.selected_dto:
                self.edit_requested.emit(self.selected_dto)
            else:
                QMessageBox.warning(self, "Внимание", "Выберите строку для редактирования.")

        elif index == 3:  # Удалить
            if self.selected_dto:
                self.delete_requested.emit(self.selected_dto)
            else:
                QMessageBox.warning(self, "Внимание", "Выберите строку для удаления.")
        elif index == 4:  # Обновить
            # self._data_loaded = True
            self._load_data()


        # Сбрасываем индекс на заглушку (0), но блокируем сигнал, чтобы не вызывать снова
        self.action_combo.blockSignals(True)
        self.action_combo.setCurrentIndex(0)
        self.action_combo.blockSignals(False)

    @AppLogger.get_instance(
        name = 'DynamicListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    @Slot(int)
    def _on_inline_action_selected(self, index):
        """Обрабатывает выбор действия в режиме редактирования."""
        if index == 1:  # Добавить строку
            # self._add_inline_row()
            self.add_row()
        elif index == 2:  # Удалить строку
            # if self.selected_dto:
            # self._delete_with_selection_prompt()
            self.delete_selected_rows()
                # self._mark_selected_for_deletion()
            # else:
            #     QMessageBox.warning(self, "Внимание", "Выберите строку для удаления.")
        
        elif index == 3:  # Отменить изменения
            # self._cancel_with_selection_prompt()
            self.cancel_selected_rows_changes()

        # Сбрасываем индекс на заглушку (0), но блокируем сигнал, чтобы не вызывать снова
        self.inline_action_combo.blockSignals(True)
        self.inline_action_combo.setCurrentIndex(0)
        self.inline_action_combo.blockSignals(False)

    # ----------------------------------------------------------------------
    # Реализация методов IDynamicListController
    # ----------------------------------------------------------------------

    @AppLogger.get_instance(
        name = 'DynamicListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def add_row(self) -> None:
        """
        Добавляет новую пустую строку в таблицу (делегирует _add_inline_row).

        Returns:
            None
        """

        if not self.edit_mode:
            self.logger.warning("add_row вызван вне режима редактирования")
            return   
             
        self._add_inline_row()

    @AppLogger.get_instance(
        name = 'DynamicListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def delete_selected_rows(self) -> None:
        """Удаляет выбранные строки (делегирует _delete_with_selection_prompt)."""

        if not self.edit_mode:
            self.logger.warning("delete_selected_rows вызван вне режима редактирования")
            return
        
        self._delete_with_selection_prompt()

    @AppLogger.get_instance(
        name = 'DynamicListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def cancel_selected_rows_changes(self) -> None:
        """Отменяет изменения выбранных строк (делегирует _cancel_with_selection_prompt)."""

        if not self.edit_mode:
            self.logger.warning("cancel_selected_rows_changes вызван вне режима редактирования")
            return
        
        self._cancel_with_selection_prompt()

    @AppLogger.get_instance(
        name = 'DynamicListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def save_all_changes(self) -> bool:
        """
        Сохраняет все изменения (делегирует _save_changes).
        
        Returns: 
            bool – True при успешном сохранении, иначе False.
        """

        return self._save_changes(if_question=True)

    @AppLogger.get_instance(
        name = 'DynamicListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def refresh_data(self) -> None:
        """Перезагружает данные из БД (делегирует _load_data)."""
        self._load_data()

    @AppLogger.get_instance(
        name = 'DynamicListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def get_selected_entity_ids(self) -> Set[int]:
        """
        Возвращает множество ID сущностей, выбранных в таблице.
        Объединяет обычное выделение и чекбоксы.

        Returns: 
            Set[int] – Множество ID выбранных сущностей.
        """

        selected = self._get_selected_ids_from_view()
        checkbox = self._get_selected_checkbox_ids()

        return selected.union(checkbox)

    @AppLogger.get_instance(
        name = 'DynamicListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def is_selection_empty(self) -> bool:
        """Проверяет, есть ли выбранные строки."""
        return len(self.get_selected_entity_ids()) == 0