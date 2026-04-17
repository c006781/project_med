# interfaces/gui/gui_window/pages/dynamic_list_page.py


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

from interfaces.gui.gui_window.pages.base_page import BasePage
from interfaces.gui.gui_window.utils.gui_helpers import add_copy_paste_to_table
from interfaces.gui.gui_window.widgets.dynamic_table_model import DynamicTableModel
from interfaces.gui.gui_window.widgets.filter_table_view import FilterTableView
from interfaces.gui.gui_window.widgets.advanced_filter_proxy_model import AdvancedFilterProxyModel

from interfaces.gui.gui_window.widgets.delegate.type_delegate import (
    CompleterStringDelegate,
    DateStringDelegate,
    StringDelegate,
    DateDelegate,
    TimeDelegate,
    BoolDelegate,
    ComboBoxDelegate,
    TimeStringDelegate,
)

# from interfaces.gui.gui_window.widgets.delegate.str_delegate import StringDelegate
# from interfaces.gui.gui_window.widgets.delegate.date_delegate import DateDelegate
# from interfaces.gui.gui_window.widgets.delegate.time_delegate import TimeDelegate
# from interfaces.gui.gui_window.widgets.delegate.bool_delegate import BoolDelegate
# from interfaces.gui.gui_window.widgets.delegate.combo_box_delegate import ComboBoxDelegate

from PySide6.QtWidgets import (
    # QWidget, 
    QComboBox,
    QVBoxLayout, 
    QHBoxLayout, 
    QPushButton, 
    QLineEdit,
    QHeaderView, 
    QMessageBox, 
    # QTableView, 
    QAbstractItemView,
)
from PySide6.QtCore import (
    Qt, 
    Signal, 
    Slot, 
    QModelIndex
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
    """Хранилище сохранённых строк для декоратора preserve_selection."""
    _data = {}

    @classmethod
    def make_key(cls, obj, func_name: str, label: Optional[str] = None) -> str:
        if label:
            return label
        class_name = obj.__class__.__name__
        return f"{class_name}.{func_name}"
    
    @classmethod
    def save(cls, key: str, row: int) -> bool:
        """Сохраняет строку только если для данного ключа ещё нет значения."""
        if key not in cls._data:
            cls._data[key] = row
            return True
        return False

    @classmethod
    def get(cls, key: str) -> int:
        return cls._data.get(key, -1)

    @classmethod
    def clear(cls, key: str):
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
    ):
    """
    Декоратор для сохранения и восстановления текущей строки в таблице.
    
    :param store_method_name: имя метода, возвращающего индекс строки (по умолчанию '_store_current_row')
    :param restore_method_name: имя метода, принимающего индекс строки и восстанавливающего выделение
    :param label: произвольная строка – если указана, используется как ключ в хранилище вместо автоматического "ClassName.method_name"
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


class CheckboxSelectionMixin:
    """
    Миксин для добавления столбца с чекбоксами в таблицу.
    Предоставляет методы для управления выбором строк через чекбоксы.
    """

    @AppLogger.get_instance(
        name = 'CheckboxSelectionMixin',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _setup_checkbox_column(self) -> None:
        """Включает столбец чекбоксов в модели и настраивает заголовок."""
        if not hasattr(self, 'source_model'):
            return
        
        self.source_model.set_checkbox_column_visible(self.edit_mode)
        # Добавляем пункты в контекстное меню заголовка чекбокс-столбца
        if hasattr(self.table_view, 'horizontalHeader'):
            header = self.table_view.horizontalHeader()
            if hasattr(header, 'set_checkbox_header_menu'):
                header.set_checkbox_header_menu(self._toggle_all_checkboxes)

    @AppLogger.get_instance(
        name = 'CheckboxSelectionMixin',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _toggle_all_checkboxes(self, checked: bool) -> None:
        """Устанавливает или снимает все чекбоксы."""
        if not self.edit_mode:
            return
        
        for row in range(self.source_model.rowCount()):
            self.source_model.set_checkbox_state(row, checked)

        # self._update_save_button_state()
        self.table_view.viewport().update()

    @AppLogger.get_instance(
        name = 'CheckboxSelectionMixin',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _get_selected_checkbox_ids(self) -> Set[int]:
        """
        Возвращает множество ID сущностей, у которых в текущей модели
        установлен чекбокс (CheckStateRole == Checked).
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
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _clear_checkboxes(self) -> None:
        """Снимает все чекбоксы (без изменения deleted_ids)."""
        for row in range(self.source_model.rowCount()):
            self.source_model.set_checkbox_state(row, False)

    @AppLogger.get_instance(
        name = 'CheckboxSelectionMixin',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _get_current_selected_dto(self):
        """
        Возвращает DTO текущей выделенной строки или None, если выделения нет.
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
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _delete_with_selection_prompt(self) -> None:
        """
        Вызывает диалог выбора области удаления и выполняет удаление.
        Используется вместо прямого _mark_selected_for_deletion.
        """
        if not self.edit_mode:
            return

        current_dto = self._get_current_selected_dto()
        checkbox_ids = self._get_selected_checkbox_ids() # ID сущностей, выбранных через чекбоксы
        has_checkbox_selection = bool(checkbox_ids) # Есть ли выбранные чекбоксы
        has_current = current_dto is not None # Есть ли текущая строка

        if not has_checkbox_selection and  not has_current:
            QMessageBox.warning(self, "Нет выбора", "Нет строк для удаления.")
            return

        # Если нет выбранных чекбоксов – удаляем только текущую строку без вопросов
        if (
            has_current and not has_checkbox_selection # Есть текущая строка, но нет выбранных чекбоксов
        ) or (
            has_current and (current_dto.id in checkbox_ids) and len(checkbox_ids) == 1 # Есть текущая строка и только она выбрана через чекбокс
        ):
            self._perform_deletion({current_dto.id}, current_dto)
            return

        # Есть выбранные чекбоксы – показываем диалог
        msg = QMessageBox(self)

        msg.setWindowTitle("Удаление записей")
        msg.setText("Выберите, какие записи пометить на удаление:")

        btn_checkbox = msg.addButton("Только выбранные (чекбоксы)", QMessageBox.ActionRole)
        btn_current = msg.addButton("Только текущую", QMessageBox.ActionRole)
        btn_both = msg.addButton("Текущую + выбранные", QMessageBox.ActionRole)
        btn_cancel = msg.addButton("Отмена", QMessageBox.RejectRole)

        # Устанавливаем доступность кнопок
        btn_checkbox.setEnabled(has_checkbox_selection)
        btn_current.setEnabled(has_current)
        btn_both.setEnabled(has_current and has_checkbox_selection)

        msg.setDefaultButton(btn_cancel)

        ret = msg.exec()
        ids_to_delete = set()

        if msg.clickedButton() == btn_current: # Только текущую
            if has_current:
                ids_to_delete.add(current_dto.id)

        elif msg.clickedButton() == btn_checkbox:  # Только выбранные
            ids_to_delete.update(checkbox_ids)

        elif msg.clickedButton() == btn_both:
            ids_to_delete.update(checkbox_ids) # Текущую + выбранные

            if has_current:
                ids_to_delete.add(current_dto.id)  # Текущую

        else:
            return  # отмена

        # Удаляем строки

        self._perform_deletion(
            ids_to_delete, 
            current_dto if has_current and (current_dto.id in ids_to_delete) else None
        )

    @AppLogger.get_instance(
        name = 'CheckboxSelectionMixin',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _perform_deletion(self, ids_to_delete: Set[int], current_dto_to_clear: Optional[Any]= None) -> None:
        """
        Помечает записи на удаление, удаляет из модели новые строки,
        сбрасывает чекбоксы для удалённых.
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
                # Снимаем модификацию, если была
                if entity_id in self.modified_ids:
                    self.modified_ids.discard(entity_id)
                # Обновляем цвет строки
                self._set_row_color_by_source_row(source_row)

        # Сбрасываем чекбоксы для всех удалённых ID
        self._clear_checkboxes()
        # Если текущий DTO был удалён, очищаем правую панель
        if current_dto_to_clear is not None and current_dto_to_clear.id in ids_to_delete:
            self.selected_dto = None
            if hasattr(self, '_clear_right_panel'):
                self._clear_right_panel()

        self._update_save_button_state()
        self.table_view.viewport().update()

    @AppLogger.get_instance(
        name = 'CheckboxSelectionMixin',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
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
    """

    @AppLogger.get_instance(
        name = 'ListSelectionMixin',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _clear_selection(self):
        # Сбрасываем все отслеживаемые изменения
        """
        Очищает все отслеживаемые изменения (modified_rows, deleted_rows, new_rows).
        """
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
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _select_by_id(self, entity_id: int) -> bool:
        """Выделяет строку по ID сущности. Возвращает True, если строка найдена."""
        row = self._find_row_by_dto_id(entity_id)
        if row >= 0:
            self._set_current_row(row)
            return True
        return False

    @AppLogger.get_instance(
        name = 'ListSelectionMixin',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _get_current_row(self) -> int:
        """
        Возвращает индекс текущей строки в таблице или -1, если строка не selected.
        :return: индекс строки или -1
        :rtype: int
        """
        current = self.table_view.currentIndex()
        return current.row() if current.isValid() else -1

    @AppLogger.get_instance(
        name = 'ListSelectionMixin',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _set_current_row(self, row: int) -> None:
        """
        Выделяет строку с указанным индексом (в прокси-модели).
        Если строка не существует, ничего не делает.
        :param row: индекс строки
        :type row: int
        :return: None
        :rtype: None
        """
        if row < 0 or row >= self.proxy_model.rowCount():
            return
        
        proxy_index = self.proxy_model.index(row, 0) # 
        self.table_view.setCurrentIndex(proxy_index) # 
        self.table_view.scrollTo(proxy_index) # 

    @AppLogger.get_instance(
        name = 'ListSelectionMixin',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _store_current_row(self) -> None:
        """
        Запоминает текущую строку в прокси-модели.

        :return: None
        :rtype: None
        """
        row = self._get_current_row()
        self._saved_row = row
        return row

    @AppLogger.get_instance(
        name = 'ListSelectionMixin',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _restore_current_row(self, row: int = None ) -> None:
        """
        Восстанавливает ранее сохранённую строку.
        Если сохранённой строки не существует, выбирает первую строку.
        :return: None
        :rtype: None
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
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _select_first_row(self) -> None:
        """
        Выбирает первую строку в таблице.
        Если таблица не содержит строк, ничего не делает.
        :return: None
        :rtype: None
        """
        
        if self.proxy_model.rowCount() > 0:
            self._set_current_row(0)
            
    @AppLogger.get_instance(
        name = 'ListSelectionMixin',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _find_row_by_dto_id(self, dto_id: int) -> int:
        """Возвращает индекс строки в прокси-модели для DTO с указанным ID, или -1."""
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
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _find_source_row_by_id(self, entity_id: int) -> int:
        """
        Возвращает индекс строки в source_model (исходной модели) по ID сущности, или -1.
        """
        for row in range(self.source_model.rowCount()):
            dto = self.source_model.get_item_at_row(row)
            if dto and getattr(dto, 'id', None) == entity_id:
                return row
        return -1
    
class ListDataMixin:
    """
    Миксин для работы с данными в таблице.
    """

    @AppLogger.get_instance(
        name = 'ListDataMixin',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _load_data(self):
        """
        Загружает данные из лоадера и обновляет модель и таблицу.

        :raises Exception: если не удалось загрузить данные
        """

        # Сохраняем ID выбранного DTO (если есть)
        # selected_id = None
        # if self.selected_dto and hasattr(self.selected_dto, 'id'):
        #     selected_id = self.selected_dto.id

        # Запоминаем ID текущего выделенного приёма (если есть)
        selected_id = self.selected_dto.id if self.selected_dto else None
            
        try:
            self.current_data = self.loader_func(self.current_extra) # Загружаем данные

            self.source_model.update_data(self.current_data)
            # self.original_data = {i: dto for i, dto in enumerate(self.current_data)}
            self.original_data = {i: deepcopy(dto) for i, dto in enumerate(self.current_data)}

            self.source_model.clear_row_colors()

            # Сбрасываем все отслеживаемые изменения
            # self.modified_rows.clear()
            # self.deleted_rows.clear()
            # self.new_rows.clear()
            self._clear_selection() # сбрасываем выделение в таблице (если оно есть)
            # self.original_data.clear()

            
            
            self._update_save_button_state()

            # self.table_view.clearSelection()
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

            # Обновляем состояние кнопок на основе текущего выделения
            self._update_selection_state()
            
            self._data_loaded = True

            self.logger.debug(f"Загружено {len(self.current_data)} записей")
        except Exception as e:
            self.logger.exception(f"Ошибка загрузки данных: {e}")
            QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить данные: {e}")

    @AppLogger.get_instance(
        name = 'ListDataMixin',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def set_needs_refresh(self, value=True):
        """
        Устанавливает флаг, указывающий на необходимость перезагрузки данных.
        Если флаг установлен в True, то при следующем вызове on_enter данные будут перезагружены.
        :param value: флаг, указывающий на необходимость перезагрузки
        :type value: bool
        :return: None
        :rtype: None
        """
        self._needs_refresh = value

    @AppLogger.get_instance(
        name = 'ListDataMixin',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def on_enter(self, extra_data=None):
        """
        Вызывается при переходе на страницу.
        extra_data может содержать новый параметр, отличающийся от self.current_extra.
        Если extra_data не None и отличается от self.current_extra, то self.current_extra обновляется.
        Если self._needs_refresh установлен в True, то данные перезагружаются.
        :param extra_data: словарь с дополнительными данными
        :type extra_data: dict
        """
        reload_needed = self._needs_refresh
        select_id = None

        if extra_data is not None:
            # Запоминаем ID для выделения
            select_id = extra_data.get('select_id')
            # Если extra_data отличается от текущего, обновляем и помечаем необходимость перезагрузки
            if extra_data != self.current_extra:
                self.current_extra = extra_data
                reload_needed = True

        # Загружаем данные, если:
        # - требуется перезагрузка (reload_needed)
        # - или данные ещё не загружены (self._data_loaded == False)     
        if reload_needed or not self._data_loaded: 
            self._load_data()
            self._needs_refresh = False
            self._data_loaded = True
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
    def _apply_draft_to_new_dto(self, dto):
        """Переопределяется в наследниках для применения черновиков к новому DTO перед созданием."""
        pass

class ListChangesMixin:
    """
    Миксин для обработки изменений в таблице.
    """
    
    # @AppLogger.get_instance(
    #     name = 'ListChangesMixin',
    #     enable_file_logging = 'system',
    #     use_name_in_filename = 'system',
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

    @AppLogger.get_instance(
        name = 'ListChangesMixin',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
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
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
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
        self.cancel_all_btn.setEnabled(has_changes) # отменять можно, если есть изменения
        # self.cancel_current_btn.setEnabled(has_changes) # отменять можно, если есть изменения



    @AppLogger.get_instance(
        name='ListChangesMixin',
        enable_file_logging='system',
        use_name_in_filename='system',
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
        enable_file_logging='system',
        use_name_in_filename='system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _modified_ids_control(self, appointment_id, if_add :bool):

        """
        Метод для управления измененных строк в таблице.
        Если if_add=True, то добавляет source_row в множество измененных строк.
        Если if_add=False, то удаляет source_row из множества измененных строк.
        Затем вызывает _set_row_color_by_source_row для обновления цвета строки source_row,
        а также _update_save_button_state для обновления состояния кнопки сохранения изменений.
        """
        
        source_row = self._find_source_row_by_id(appointment_id)

        self._modified_ids(appointment_id, if_add) 

        if source_row != -1: # Если строка была найдена
            self._set_row_color_by_source_row(source_row) # обновляем цвет строки

        self._update_save_button_state() # активируем кнопку сохранения

    @AppLogger.get_instance(
        name = 'ListChangesMixin',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    @Slot(int)
    def _on_row_modified(self, row: int):
        """
        Обработчик события изменения строки в таблице.
        
        Если строка была удалена, то ничего не делает.
        Иначе, добавляет строку в список измененных строк и обновляет цвет строки в таблице, а также состояние кнопки сохранения изменений.
        :param row: индекс строки в таблице
        :type row: int
        """
        self.logger.debug(
            f"_on_row_modified вызван для row={row}, "
            # f"modified_rows={self.modified_rows}"
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
            self.logger.debug(f"Строка {row} — новая, пропускаем добавление в modified_ids")
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
                # Значение совпадает с исходным – убираем из modified_rows
                # self.logger.debug(f"if row in self.modified_rows : {row in self.modified_rows}")
                # if row in self.modified_rows:
                #     self.modified_rows.discard(row)
                #     self.logger.debug(f"Вызов _set_row_color_by_source_row для row={row}")
                #     self._set_row_color_by_source_row(row)   # обновляем цвет
                #     self._update_save_button_state()


                

                self.logger.debug(f"if dto.id in self.modified_ids : {dto.id in self.modified_ids}")
                if dto.id in self.modified_ids:
                    self._modified_ids_control( dto.id, False )

                    
                #     self.modified_ids.discard(dto.id)
                #     self._set_row_color_by_source_row(row)
                #     self._update_save_button_state()

                self._update_selection_state() # обновляем состояние выбора
                return
        
        
        # Иначе добавляем в modified_row

        # self.logger.debug(f"if row not in self.modified_rows : {row not in self.modified_rows}")
        # if row not in self.modified_rows:
        #     self.modified_rows.add(row)
        #     # self._update_row_color(row)
        #     self._set_row_color_by_source_row(row)
        #     self._update_save_button_state()
        self.logger.debug(f"if dto.id not in self.modified_ids : {dto.id not in self.modified_ids}")
        
        if dto.id not in self.modified_ids:
            self._modified_ids_control(dto.id, True) 
            self._update_selection_state()
            # self.modified_ids.add(dto.id)
            # self._set_row_color_by_source_row(row)
            # self._update_save_button_state()    
        # 0==0

    # @AppLogger.get_instance(
    #     name = 'ListChangesMixin',
    #     enable_file_logging = 'system',
    #     use_name_in_filename = 'system',
    # ).log_execution_time(
    #     level = AppLogger._parse_log_level('DEBUG')
    # )
    # def _update_row_color_by_source_row(self, source_row: int):
    #     """Обновляет цвет строки в таблице по индексу исходной модели."""
    #     # Находим соответствующий индекс в прокси-модели
    #     source_index = self.source_model.index(source_row, 0)
    #     if not source_index.isValid():
    #         return
        
    #     proxy_index = self.proxy_model.mapFromSource(source_index)
    #     if not proxy_index.isValid():
    #         return
        
    #     proxy_row = proxy_index.row()
    #     self._update_row_color(proxy_row)   # используем существующий метод

class ListEditModeMixin:
    '''
    Миксин для работы с режимом редактирования.
    '''

    @AppLogger.get_instance(
        name = 'ListEditModeMixin',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _set_visible_edit_mode_elements(self, edit_mode):
        
        
        self.action_combo.setVisible(not edit_mode)
        self.inline_action_combo.setVisible(edit_mode)
        self.save_changes_btn.setVisible(edit_mode)

        self.cancel_all_btn.setVisible(edit_mode)
        self.cancel_current_btn.setVisible(edit_mode)


        if hasattr(self, 'action_btn') and self.action_btn:
            self.action_btn.setVisible(not edit_mode)
        self.table_view.setEditTriggers(
            QAbstractItemView.DoubleClicked if edit_mode else QAbstractItemView.NoEditTriggers
        )

        if edit_mode:   
            self.table_view.doubleClicked.disconnect(self._on_row_double_clicked)    
        else:
            self.table_view.doubleClicked.connect(self._on_row_double_clicked )
        
        


    @AppLogger.get_instance(
        name = 'ListEditModeMixin',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
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
        Вызывается при переключении режима редактирования.
        Если режим редактирования отключен и есть несохраненные изменения, то выводит предупреждение о необходимости подтверждения.
        Если пользователь подтвердил удаление, то извлекается соответствующий сигнал.

        Если включён и таблица пуста, автоматически добавляет новую строку
        """

        has_changes = self._has_unsaved_changes()

        if not checked and has_changes:
            reply = QMessageBox.question(
                self, "Несохранённые изменения",
                "Есть несохранённые изменения. Сохранить перед выходом из режима редактирования?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._save_changes(
                    if_question=False
                )
                self.edit_mode = False

            elif reply == QMessageBox.StandardButton.No:
                self._load_data()
                # self.modified_rows.clear()
                # self.deleted_rows.clear()
                # self.new_rows.clear()

                self._clear_selection() # сбрасываем выделение в таблице (если оно есть)
                self._clear_drafts() # Очистка черновиков (если они есть)

                self._update_save_button_state()
                self.edit_mode = False

            else:
                return
        else:
            # При включении режима редактирования, если таблица пуста, создаём новую строку
            if checked and self.source_model.rowCount() == 0:
                self._add_inline_row()
                
            self.edit_mode = checked

        # Управление видимостью кнопок
        self._set_visible_edit_mode_elements(self.edit_mode)

        # if self.edit_mode:
        #     self.action_combo.setVisible(False)
        #     self.inline_action_combo.setVisible(True)
        #     self.save_changes_btn.setVisible(True)
        #     if hasattr(self, 'action_btn') and self.action_btn:
        #         self.action_btn.setVisible(False)
        #     self.table_view.setEditTriggers(QAbstractItemView.DoubleClicked)
        #     self.table_view.doubleClicked.disconnect(self._on_row_double_clicked)
        # else:
        #     self.action_combo.setVisible(True)
        #     self.inline_action_combo.setVisible(False)
        #     self.save_changes_btn.setVisible(False)
        #     if hasattr(self, 'action_btn') and self.action_btn:
        #         self.action_btn.setVisible(True)
        #     self.table_view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        #     self.table_view.doubleClicked.connect(self._on_row_double_clicked)

        self.table_view.clearSelection()
        self.selected_dto = None

        if hasattr(self, 'action_btn'):
            self.action_btn.setEnabled(False)

        self.logger.debug(f"Режим редактирования: {'включён' if self.edit_mode else 'выключен'}")

class ListSaveMixin:

    '''
    Миксин для сохранения изменений в таблице
    '''
    @AppLogger.get_instance(
        name = 'ListSaveMixin',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    # def _save_deleted(self):
    #     for row in sorted(self.deleted_rows, reverse=True):
    #         dto = self.source_model.get_item_at_row(row)
    #         if dto and dto.id is not None:
    #             self.service.delete(dto.id)
    #             self.logger.info(f"Удалена запись ID={dto.id}")
    #         # self.source_model.remove_row(row)
    #     self.deleted_rows.clear()
    def _save_deleted(self):
        for entity_id in list(self.deleted_ids):
            try:
                self.service.delete(entity_id)
                self.logger.info(f"Удалена запись ID={entity_id}")
            except Exception as e:
                self.logger.exception(f"Ошибка удаления ID={entity_id}: {e}")
        self.deleted_ids.clear()

    @AppLogger.get_instance(
        name = 'ListSaveMixin',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    # def _save_modified(self):
    #     for row in list(self.modified_rows):
    #         dto = self.source_model.get_item_at_row(row)
    #         if dto and dto.id is not None and dto.id > 0:
    #             original = self.original_data.get(row)
    #             if original and dto.model_dump() == original.model_dump():
    #                 # Ничего не изменилось, снимаем пометку
    #                 self.modified_rows.discard(row)
    #                 continue
    #             updated = self.service.update(dto)
    #             self.source_model.update_row(row, updated)
    #             self.logger.info(f"Обновлена запись ID={updated.id}")
    #     self.modified_rows.clear()
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
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _save_new(self):
        for row in list(self.new_rows):
            dto = self.source_model.get_item_at_row(row)
            if dto:
                self._apply_draft_to_new_dto(dto) # если есть черновики
                created = self.service.create(dto)
                self.source_model.update_row(row, created)
                self.logger.info(f"Создана новая запись ID={created.id}")
        self.new_rows.clear()

    @AppLogger.get_instance(
        name = 'ListSaveMixin',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    @preserve_selection()
    @Slot()
    def _save_changes(self , if_question:bool = True):
        """
        Сохраняет все изменения в БД.

        1. Удаление удаленных строк
        2. Обновление измененных строк
        3. Создание новых строк

        После сохранения изменений, обновляет данные на странице и восстанавливает кнопку сохранения.
        """
        self.logger.info("=== _save_changes ВЫЗВАН ИЗ ListSaveMixin ===")

        has_changes = self._has_unsaved_changes()
        if not has_changes:
            return


        if if_question:
            reply = QMessageBox.question(
                self, "Подтверждение",
                "Сохранить все изменения? Будут обновлены, добавлены и удалены записи в БД.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        self.table_view.setEnabled(False)
        self.save_changes_btn.setEnabled(False)

        try:
            # Новые строки
            self._save_new()

            # Обновление
            self._save_modified()

            # Удаление
            self._save_deleted()

            self._load_data()

            QMessageBox.information(self, "Успех", "Изменения сохранены.")

            # Выходим из режима редактирования, если он был включён
            self._exit_edit_mode()

            self._clear_checkboxes() # снимаем все чекбоксы

        except Exception as e:
            self.logger.exception(f"Ошибка при сохранении изменений: {e}")
            QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить изменения: {e}")
        finally:
            self.table_view.setEnabled(True)
            self._update_save_button_state()

    def _exit_edit_mode(self):
        """Выходит из режима редактирования, если он активен."""
        if self.edit_mode:
            self.edit_mode_btn.setChecked(False)

class ListUIMixin:

    @AppLogger.get_instance(
        name = 'ListUIMixin',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
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
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _setup_ui(self):
        """
        Установка UI для страницы со списком записей.

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
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _setup_top_panel(self):
        """
        Установка верхней панели для страницы со списком записей.

        Создает горизонтальный layout и добавляет в него:
        - кнопку "Режим редактирования"
        - комбо-бокс действия
        - кнопку "Сохранить изменения"
        - комбо-бокс inline-действ
        - кнопку "Действие"
        - поле поиска

        :return: None
        :rtype: None
        """
        # Верхняя панель
        top_layout = QHBoxLayout()
        
        # Кнопка переключения режима редактирования (переключатель) (переключатель)     
        self.edit_mode_btn = QPushButton("Режим редактирования")
        self.edit_mode_btn.setCheckable(True)
        self.edit_mode_btn.toggled.connect(self._on_edit_mode_toggled)
        top_layout.addWidget(self.edit_mode_btn)
        
        # Выпадающий список для действий в обычном режиме
        self.action_combo = QComboBox()
        self.action_combo.addItem("▼ Действия с записями")
        self.action_combo.addItem("Добавить")
        self.action_combo.addItem("Редактировать")
        self.action_combo.addItem("Удалить")
        self.action_combo.addItem("Обновить")
        self.action_combo.setEditable(False)
        self.action_combo.setMaximumWidth(170)
        # Делаем первый пункт невыбираемым
        self.action_combo.model().item(0).setEnabled(False)
        self.action_combo.setCurrentIndex(0)
        self.action_combo.currentIndexChanged.connect(self._on_action_selected)
        # Принудительное открытие вниз
        # self.action_combo.setPopupPolicy(QComboBox.PopupPolicy.InstantPopup)
        top_layout.addWidget(self.action_combo)

        # Выпадающий список для inline-действий (скрыт по умолчанию)
        self.inline_action_combo = QComboBox()
        self.inline_action_combo.addItem("▼ Действия со строками")
        self.inline_action_combo.addItem("Добавить строку")
        self.inline_action_combo.addItem("Удалить строку")
        self.inline_action_combo.setEditable(False)
        self.inline_action_combo.setMaximumWidth(170)
        # Делаем первый пункт невыбираемым
        self.inline_action_combo.model().item(0).setEnabled(False)
        self.inline_action_combo.setCurrentIndex(0)
        self.inline_action_combo.currentIndexChanged.connect(self._on_inline_action_selected)
        self.inline_action_combo.setVisible(False)
        top_layout.addWidget(self.inline_action_combo)

        # Кнопка сохранения (отдельная, показывается в режиме редактирования)
        self.save_changes_btn = QPushButton("Сохранить изменения")
        self.save_changes_btn.clicked.connect(self._save_changes)
        self.save_changes_btn.setEnabled(False)
        self.save_changes_btn.setVisible(False)
        top_layout.addWidget(self.save_changes_btn)

        self.cancel_all_btn = QPushButton("Отменить все")
        self.cancel_all_btn.clicked.connect(self._cancel_all_changes)
        self.cancel_all_btn.setVisible(False)          
        self.cancel_all_btn.setEnabled(False)
        top_layout.addWidget(self.cancel_all_btn)

        self.cancel_current_btn = QPushButton("Отменить текущую")
        self.cancel_current_btn.clicked.connect(self._cancel_current_row_changes)
        self.cancel_current_btn.setVisible(False)      
        self.cancel_current_btn.setEnabled(False)
        top_layout.addWidget(self.cancel_current_btn)

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
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
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
        self.table_view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table_view.setEditTriggers(QAbstractItemView.NoEditTriggers) # Изначально двойной клик не редактирует ячейки (режим не редактирования)
        add_copy_paste_to_table(self.table_view)
        self.table_view.doubleClicked.connect(self._on_row_double_clicked)

        # Модель таблицы
        self.source_model = DynamicTableModel(
            self.current_data, 
            self.columns,
            get_unique_values_func=self.get_unique_values_for_column
        )

        self.source_model.row_modified.connect(self._on_row_modified) # Подключаем сигнал изменения строки для отслеживания изменений строк

        # self.source_model.checkbox_toggled.connect(self._on_checkbox_toggled) # Подключаем сигнал изменения строки для отслеживания изменений чекбоксов

        # Прокси-модель
        self.proxy_model = AdvancedFilterProxyModel()
        self.proxy_model.setSourceModel(self.source_model)
        self.table_view.setModel(self.proxy_model)

        # Настройка заголовка таблицы
        header = self.table_view.horizontalHeader()
        if hasattr(header, 'set_get_unique_values_func'):
            header.set_get_unique_values_func(self.get_unique_values_for_column) # Подключаем сигнал изменения строки для отслеживания изменений чекбоксов
            header.filter_requested.connect(self.on_filter_requested) # Подключаем сигнал изменения строки для отслеживания изменений чекбоксов
            header.filter_clear_requested.connect(self.on_filter_clear) # Подключаем сигнал изменения строки для отслеживания изменений чекбоксов


        self._setup_header_settings_table(header=header)

    @AppLogger.get_instance(
        name = 'ListUIMixin',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _setup_header_settings_table(self, header):
        
        header.setStretchLastSection(True) # Растянуть последний столбец
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents) # Размеры столбцов под контент




    @AppLogger.get_instance(
        name = 'ListUIMixin',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _setup_delegates(self):
        """
        Устанавливает делегаты для колонок на основе типов полей и field_configs.
        Приоритет: choices > widget_type > тип поля.
        """

        # Словарь: тип -> класс делегата (и, возможно, дополнительные параметры)
        
        invert_tip = {
            'date': datetime.date,
            'time': datetime.time,
            # 'textarea': StringDelegate,
        }

        type_delegate_map = {
            # datetime.date: DateDelegate,
            datetime.date: DateStringDelegate,
            # datetime.time: TimeDelegate,
            datetime.time: TimeStringDelegate,
            bool: BoolDelegate,
            str: StringDelegate,
        }

        for col_idx, col_info in enumerate(self.columns):
            field_name = col_info['name']
            config = self.field_configs.get(field_name, {})

            # Выпадающий список (choices) – наивысший приоритет
            choices = config.get('choices')
            if choices:
                delegate = ComboBoxDelegate(self.table_view, choices)
                self.table_view.setItemDelegateForColumn(col_idx, delegate)
                continue 


            # Определяем тип поля и его реальный тип (для делегата) автоматически по параметрам
            widget_type = config.get('widget_type') # Специальные типы виджетов из field_configs
            if widget_type:
                field_type = invert_tip.get(widget_type) # определяем по типу поля     
            else:
                field_type = col_info.get('type')   # Определяем по реальному типу поля

            real_type = self._get_real_type( # определяем реальный тип
                field_type
            )


            # Автодополнение для строковых полей (если включено в конфигурации)
            if real_type == str and config.get('autocomplete', False):
                delegate = CompleterStringDelegate(
                    self.table_view,
                    get_unique_values_func=self.get_unique_values_for_column,
                    column=col_idx
                )
                self.table_view.setItemDelegateForColumn(col_idx, delegate)
                continue

            # Стандартные делегаты по типу
            delegate_class = type_delegate_map.get(# определяем класс делегата по реальному типу поля
                real_type
            ) 
            if delegate_class:
                delegate = delegate_class(self.table_view)
                self.table_view.setItemDelegateForColumn(col_idx, delegate)
                continue
                # Для всех остальных типов (int, float и т.д.) оставляем делегат по умолчанию
            # Если тип не найден в словаре – оставляем стандартный делегат (например, для int, float)




class ListFilterMixin:

    @AppLogger.get_instance(
        name = 'ListFilterMixin',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def on_filter_requested(self, column: int, operator: str, value):
        """
        Обработка сигнала фильтрации от заголовка.

        :param column: номер столбца, для которого нужно установить фильтр
        :param operator: оператор фильтрации (eq, like, fuzzy, in)
        :param value: значение для сравнения (зависит от оператора)
        """
        if operator == 'in':
            self.proxy_model.set_column_filter(column, selected_values=value)
        elif operator == 'contains':
            self.proxy_model.set_column_filter(column, filter_text=value)
        elif operator == 'clear':
            self.proxy_model.clear_column_filter(column)

    @AppLogger.get_instance(
        name = 'ListFilterMixin',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def on_filter_clear(self, column: int):
        """
        Очищает фильтр для столбца.

        :param column: номер столбца, для которого нужно очистить фильтр
        """
        self.proxy_model.clear_column_filter(column)

    @AppLogger.get_instance(
        name = 'ListFilterMixin',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def get_unique_values_for_column(self, column: int) -> List[str]:
        """
        Возвращает список уникальных значений для указанного столбца.
        
        :param column: номер столбца
        :return: список уникальных значений для указанного столбца
        :rtype: List[str]
        """
        if self.service is None:
            return []
        
        col_name = self.columns[column]['name']
        values = self.service.get_unique_values(col_name)

        # Преобразуем в строки (могут быть даты, числа)
        return [str(v) for v in values]

    @AppLogger.get_instance(
        name = 'ListFilterMixin',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _on_search_text_changed(self, text):
        """
        Обработка сигнала о изменении текста общего текстового фильтра.
        
        :param text: текст для поиска (необязательно)
        """
        self.proxy_model.set_global_text_filter(text)
    
class ListInlineOpsMixin:
    
    @AppLogger.get_instance(
        name = 'ListFilterMixin',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    @Slot()
    def _add_inline_row(self):
        defaults = {}
        for col_info in self.columns:
            field_name = col_info['name']
            config = self.field_configs.get(field_name, {})
            if config.get('virtual', False) or config.get('hidden', False):
                continue
            field_info = self.dto_class.model_fields.get(field_name)
            if field_info is None:
                continue

            field_type = field_info.annotation
            origin = get_origin(field_type)
            if origin is Union:
                args = get_args(field_type)
                field_type = next((arg for arg in args if arg is not type(None)), None)

            if field_type is None:
                defaults[field_name] = None
            elif field_type == str:
                defaults[field_name] = ""
            elif field_type == int:
                defaults[field_name] = 0
            elif field_type == datetime.date:
                defaults[field_name] = datetime.date.today()
            elif field_type == datetime.time:
                defaults[field_name] = datetime.time(0, 0)
            elif field_type == bool:
                defaults[field_name] = False
            else:
                defaults[field_name] = None

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
        # self._update_row_color(row)
        self._set_row_color_by_source_row(row)
        self._update_save_button_state()

        proxy_index = self.proxy_model.mapFromSource(self.source_model.index(row, 0))
        if proxy_index.isValid():
            self.table_view.setCurrentIndex(proxy_index)
            self.table_view.scrollTo(proxy_index)

        self._update_selection_state() # Обновляем состояние выделения

        self.logger.info(f"Добавлена новая строка (индекс {row})")

    @AppLogger.get_instance(
        name = 'ListFilterMixin',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    @Slot()
    def _mark_selected_for_deletion(self):
        
        
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
        
        # proxy_index = self.table_view.currentIndex()
        # if not proxy_index.isValid():
        #     return
        
        # row = self.proxy_model.mapToSource(proxy_index).row()   # исходный индекс
        # if row == -1:
        #     return
        # # row = proxy_index.row()
        # if row in self.deleted_rows:
        #     return
        
        # Помечаем строку на удаление (для любых строк – и новых, и существующих)
        # self.deleted_rows.add(row)
        self.deleted_ids.add(dto.id)
        # Если строка была изменена, убираем из соответствующих множеств
        # self.modified_rows.discard(row)
        

        self._modified_ids_control(dto.id, False)  # # Если строка новая, убираем из соответствующих множеств
        # self.modified_ids.discard(dto.id)
        # # # Если строка новая, убираем из соответствующих множеств
        # # self.new_rows.discard(row)

        # # Обновляем цвет строки
        # # self._update_row_color(row)
        # # self._set_row_color_by_source_row(row)
        # self._set_row_color_by_source_row(source_row)
        # self._update_save_button_state()

        # # Снимаем выделение
        # self.table_view.clearSelection() # снимаем выделение
        # self.selected_dto = None
        # # if hasattr(self, 'delete_btn'):
        # #     self.delete_btn.setEnabled(False)
        # if hasattr(self, 'action_btn'): # снимаем выделение
        #     self.action_btn.setEnabled(False)

        self._update_selection_state()   #

        # self.logger.info(f"Строка {row} помечена на удаление")
        self.logger.info(f"Строка с id {source_row} помечена на удаление")

class DynamicListPage(
    CheckboxSelectionMixin,
    ListSelectionMixin,
    ListDataMixin,
    ListChangesMixin,
    ListEditModeMixin,
    ListSaveMixin,
    ListUIMixin,
    ListFilterMixin,
    ListInlineOpsMixin,
    BasePage,
):
    """
    Универсальная страница списка с поддержкой inline-редактирования.
    Добавлена возможность отложенного сохранения изменений через кнопку «Сохранить изменения».
    Поддерживает два режима:
        - обычный режим: двойной клик по строке вызывает action_requested (переход на другой фрейм),
          редактирование выполняется через формы.
        - режим редактирования: включается кнопкой-переключателем, появляются inline-кнопки
          «Добавить строку», «Удалить строку», «Сохранить изменения», двойной клик начинает редактирование ячейки.
    """

 
    add_requested = Signal() # сигнал для добавления (можно не использовать, если добавляем строку напрямую)
    edit_requested = Signal(object) # сигнал для открытия формы редактирования
    delete_requested = Signal(object) # сигнал для удаления (с подтверждением)
    action_requested = Signal(object)  # дополнительное действие

    # detail_requested = Signal(object) # сигнал для перехода к детальной странице (двойной клик
        
    @AppLogger.get_instance(
        name = 'DynamicListPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
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
        # """
        # Инициализирует страницу списка.
        # """

        """
        Инициализирует страницу списка.

        :param service: сервис, используемый для редактирования записи
        :param loader_func: функция, которая возвращает список данных
        :param dto_class: класс DTO, используемый для создания записи
        :param field_configs: внешняя конфигурация
        :param page_title: заголовок страницы
        :param add_action_text: текст кнопки добавления
        :param action_button_text: текст дополнительной кнопки (если задана)
        :param edit_on_double_click: True, если редактирование должно быть доступно при двойном нажатии на строке
        :param parent: родительский виджет
        """
        super().__init__(parent)

        self.logger = AppLogger.get_instance(
            name = f"gui.{self.__class__.__name__}",
            enable_file_logging = 'user',
            use_name_in_filename = 'user',
        )

        self._checkbox_setup_done = False

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

        # настройка интерфейса страницы
        self._needs_refresh = False  # флаг, который указывает, нужно ли перезагружать данные при следующем входе на страницу

        self._data_loaded = False   # флаг, что данные ещё не загружены
        self._setup_ui()
        
        # self._load_data() # загрузка данных на страницу
     
    @AppLogger.get_instance(
        name='DynamicListPage',
        enable_file_logging='system',
        use_name_in_filename='system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _setup_ui(self):
        super()._setup_ui()
        if not self._checkbox_setup_done:
            self._setup_checkbox_column()
            self._checkbox_setup_done = True

    @AppLogger.get_instance(
        name='DynamicListPage',
        enable_file_logging='system',
        use_name_in_filename='system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    @preserve_selection()
    def _on_edit_mode_toggled(self, checked: bool):
        # Вызываем родительский (он переключит edit_mode)
        super()._on_edit_mode_toggled(checked)
        # Включаем/отключаем видимость чекбокс-столбца
        self.source_model.set_checkbox_column_visible(self.edit_mode)

        if not self.edit_mode:
            self._clear_checkboxes()
            self.deleted_ids.clear()
            self._update_save_button_state()

        # Принудительно восстанавливаем растяжение последнего столбца
        header = self.table_view.horizontalHeader() # получаем заголовок

        self._setup_header_settings_table(header=header)

        # Обновляем геометрию таблицы
        # self.table_view.resizeColumnsToContents() # обновляем размеры столбцов

        # self.table_view.updateGeometry() # обновляем геометрию

    @AppLogger.get_instance(
        name='DynamicListPage',
        enable_file_logging='system',
        use_name_in_filename='system',
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
        enable_file_logging='system',
        use_name_in_filename='system',
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

        # self._store_current_row()               # сохраняем текущую строку

        # 1. Очистить все множества
        # self.modified_ids.clear()
        # self.deleted_ids.clear()
        # self.new_rows.clear()

        self._clear_selection() # очистить выделение (в базовом классе это заглушка, в AppointmentListPage реализован)

        # 2. Очистить черновики (если есть переопределённый метод в наследнике)
        self._clear_drafts()  # очистить черновики  (в базовом классе это заглушка, в AppointmentListPage реализован)

        # 3. Перезагрузить данные из БД
        self._load_data()

        # # 4. Сбросить выделение и правую панель (если есть)
        # self.table_view.clearSelection()
        # self.selected_dto = None
        # # Очищаем правую панель (заметку и фото)
        # if hasattr(self, '_clear_right_panel'):
        #     self._clear_right_panel()



        # 5. Обновить состояние кнопки сохранения (она должна стать неактивной)
        self._update_save_button_state()

        # Обновить состояние кнопки «Отменить текущую» (выделения нет → кнопка неактивна)
        self._update_selection_state()

        # 6. Если мы в режиме редактирования, остаёмся в нём, но все изменения отменены
        self.logger.debug("Все изменения отменены")



    @AppLogger.get_instance(
        name='DynamicListPage',
        enable_file_logging='system',
        use_name_in_filename='system',
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
        
        if not self.selected_dto:
            QMessageBox.warning(self, "Внимание", "Нет выбранной строки.")
            return

        dto = self.selected_dto
        entity_id = dto.id
        self.logger.info(f"Отмена изменений для строки с id={entity_id}")

        # Найти исходный индекс строки (в source_model)
        source_row = self._find_source_row_by_id(entity_id)
        if source_row == -1:
            self.logger.warning(f"Строка с id={entity_id} не найдена в модели")
            return

        # Если это новая строка (временный ID)
        if entity_id is not None and entity_id < 0:

            # Удаляем строку из модели
            self.source_model.remove_row(source_row)
            self.new_rows.discard(source_row)

            # Очищаем черновики для этого временного ID
            self._clear_drafts(entity_id)
            
            # Снимаем выделение
            self.table_view.clearSelection()
            self.selected_dto = None
            if hasattr(self, '_clear_right_panel'):
                self._clear_right_panel()

            # Обновляем состояние кнопки сохранения
            self._update_save_button_state()
            
            self.logger.debug(f"Новая строка с id={entity_id} удалена")
            return

        # Существующая строка (id > 0)
        # 1. Очистить черновики для этого приёма (если есть)
        self._clear_drafts(entity_id)

        # 2. Перезагрузить DTO из БД
        try:
            fresh_dto = self.service.get_by_id(entity_id)
        except Exception as e:
            self.logger.exception(f"Ошибка загрузки свежих данных для id={entity_id}: {e}")
            QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить данные: {e}")
            return

        # 3. Обновить модель (заменить DTO)
        self.source_model.update_row(source_row, fresh_dto)
        # Обновить original_data
        self.original_data[source_row] = fresh_dto

        # 4. Убрать из modified_ids, если был
        if entity_id in self.modified_ids:
            self.modified_ids.discard(entity_id)


        # убираем из deleted_ids, если был помечен на удаление
        if entity_id in self.deleted_ids:
            self.deleted_ids.discard(entity_id)

        # 5. Обновить цвет строки
        self._set_row_color_by_source_row(source_row)

        # 6. Если есть правая панель, обновить её
        if hasattr(self, 'update_details'):
            self.update_details(fresh_dto)


        # 7. Обновить состояние кнопки сохранения
        self._update_save_button_state()

         # 8. Обновить состояние кнопки «Отменить текущую» и другие элементы UI
        self._update_selection_state()

        # # 8. Обновить состояние кнопки «Отменить текущую»
        # if hasattr(self, 'cancel_current_btn'):
        #     self.cancel_current_btn.setEnabled(self._has_current_row_changes())

        self.logger.debug(f"Изменения для строки id={entity_id} отменены, данные восстановлены из БД")

    @AppLogger.get_instance(
        name='DynamicListPage',
        enable_file_logging='system',
        use_name_in_filename='system',
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
        enable_file_logging='system',
        use_name_in_filename='system',
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
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
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
            self._exit_edit_mode()

        # Дополнительные действия, например, очистка черновиков, если нужно
        # self._clear_drafts()  # если требуется    

    @AppLogger.get_instance(
        name = 'DynamicListPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
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
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
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
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
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
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
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
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
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
        
        # Управляем кнопкой «Отменить текущую»
        if hasattr(self, 'cancel_current_btn'):
            self.cancel_current_btn.setEnabled(self._has_current_row_changes())
    
    @AppLogger.get_instance(
        name = 'DynamicListPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
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
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _on_row_double_clicked(self, index):
        """
        Обработка двойного клика в обычном режиме (не редактирование).
        Вызывает action_requested для перехода на следующий фрейм.
        """
        if not self.edit_mode and index.isValid():
            source_index = self.proxy_model.mapToSource(index)
            dto = self.source_model.get_item_at_row(source_index.row())
            if dto:
                self.action_requested.emit(dto)
                
    
    @AppLogger.get_instance(
        name = 'DynamicListPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
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

    # ----------------------- Вспомогательные методы для inline-добавления (опционально) -----------------------

    @AppLogger.get_instance(
        name = 'DynamicListPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def add_new_row(self, dto: Any = None):
        """
        Добавляет новую пустую строку в таблицу (для inline-создания).
        Если dto не передан, создаётся пустой DTO через конструктор.
        """
        if dto is None:
            # Создаём пустой DTO (все поля None, кроме обязательных)
            dto = self.dto_class()

        row = self.source_model.add_row(dto)
        self.new_rows.add(row)
        # self._update_row_color(row)
        self._set_row_color_by_source_row(row)
        self._update_save_button_state()

        # Прокручиваем к новой строке
        proxy_index = self.proxy_model.mapFromSource(self.source_model.index(row, 0))

        self.logger.debug(
            f'if proxy_index.isValid() : {proxy_index.isValid()}'
        )
        if proxy_index.isValid():
            self.table_view.scrollTo(proxy_index)


    # ----------------------- слоты для обработки выбора действий -----------------------

    @AppLogger.get_instance(
        name = 'DynamicListPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
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
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    @Slot(int)
    def _on_inline_action_selected(self, index):
        """Обрабатывает выбор действия в режиме редактирования."""
        if index == 1:  # Добавить строку
            self._add_inline_row()
        elif index == 2:  # Удалить строку
            # if self.selected_dto:
            self._delete_with_selection_prompt()
                # self._mark_selected_for_deletion()
            # else:
            #     QMessageBox.warning(self, "Внимание", "Выберите строку для удаления.")

        # Сбрасываем индекс на заглушку (0), но блокируем сигнал, чтобы не вызывать снова
        self.inline_action_combo.blockSignals(True)
        self.inline_action_combo.setCurrentIndex(0)
        self.inline_action_combo.blockSignals(False)