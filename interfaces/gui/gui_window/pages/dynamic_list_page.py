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

from app.utils.logger.logger import AppLogger

from interfaces.gui.gui_window.pages.base_page import BasePage
from interfaces.gui.gui_window.widgets.dynamic_table_model import DynamicTableModel
from interfaces.gui.gui_window.widgets.filter_table_view import FilterTableView
from interfaces.gui.gui_window.widgets.delegate.combo_box_delegate import ComboBoxDelegate
from interfaces.gui.gui_window.widgets.advanced_filter_proxy_model import AdvancedFilterProxyModel

from interfaces.gui.gui_window.widgets.delegate.date_delegate import DateDelegate
from interfaces.gui.gui_window.widgets.delegate.time_delegate import TimeDelegate
from interfaces.gui.gui_window.widgets.delegate.bool_delegate import BoolDelegate
from interfaces.gui.gui_window.widgets.delegate.combo_box_delegate import ComboBoxDelegate

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


def preserve_selection(func):
    """
    Декоратор для методов, которые могут изменить данные или режим редактирования.
    Сохраняет текущую строку перед выполнением и восстанавливает её после. 
    (работает от DynamicListPage)
    """
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        self._store_current_row()
        try:
            result = func(self, *args, **kwargs)
        except Exception as e:
            self.logger.exception(f"Ошибка в {func.__name__}: {e}")
            raise 
        finally:
            self._restore_current_row()
        return result
    
    return wrapper

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
        proxy_index = self.proxy_model.index(row, 0)
        self.table_view.setCurrentIndex(proxy_index)
        self.table_view.scrollTo(proxy_index)

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
        self._saved_row = self._get_current_row()

    @AppLogger.get_instance(
        name = 'ListSelectionMixin',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _restore_current_row(self) -> None:
        """
        Восстанавливает ранее сохранённую строку.
        Если сохранённой строки не существует, выбирает первую строку.
        :return: None
        :rtype: None
        """
        if hasattr(self, '_saved_row') and self._saved_row != -1:
            if self._saved_row < self.proxy_model.rowCount():
                self._set_current_row(self._saved_row)
            else:
                self._select_first_row()
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
        selected_id = None
        if self.selected_dto and hasattr(self.selected_dto, 'id'):
            selected_id = self.selected_dto.id
            
        try:
            self.current_data = self.loader_func(self.current_extra)
            self.source_model.update_data(self.current_data)
            self.source_model.clear_row_colors()

            # Сбрасываем все отслеживаемые изменения
            self.modified_rows.clear()
            self.deleted_rows.clear()
            self.new_rows.clear()
            self.original_data.clear()
            self._update_save_button_state()

            # self.table_view.clearSelection()
            # Восстанавливаем выделение по ID
            if selected_id is not None:
                row = self._find_row_by_dto_id(selected_id)
                if row >= 0:
                    self._set_current_row(row)
                else:
                    self._select_first_row()
            else:
                self._select_first_row()

            # Обновляем состояние кнопок на основе текущего выделения
            self._update_selection_state()
        
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
        if reload_needed:
            self._load_data()
            self._needs_refresh = False
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


class ListChangesMixin:
    """
    Миксин для обработки изменений в таблице.
    """
    
    @AppLogger.get_instance(
        name = 'ListChangesMixin',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _update_row_color(self, row: int):
        """
        Обновляет цвет строки в таблице в зависимости от статуса строки (новая, изменена, удалена).
        :param row: индекс строки в таблице
        :type row: int
        """
        proxy_index = self.proxy_model.index(row, 0)
        if not proxy_index.isValid():
            return
        
        source_row = self.proxy_model.mapToSource(proxy_index).row()
        if source_row == -1:
            return

        if row in self.deleted_rows:
            color = QColor(255, 200, 200)   # красный
        elif row in self.new_rows:
            color = QColor(200, 255, 200)   # зелёный
        elif row in self.modified_rows:
            color = QColor(255, 255, 180)   # жёлтый
        else:
            color = QColor(255, 255, 255)   # белый

        self.logger.debug(f"Обновление цвета строки {row} - {color.name()}")
        self.source_model.set_row_color(source_row, color)

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
        has_changes = bool(self.modified_rows or self.deleted_rows or self.new_rows)
        self.save_changes_btn.setEnabled(has_changes)

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

        self.logger.debug(f"Строка {row} изменена")

        # Пропускаем, если строка уже помечена на удаление
        if row in self.deleted_rows:
            return
        
        self.modified_rows.add(row)
        self._update_row_color(row)
        self._update_save_button_state()


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
    @preserve_selection
    @Slot(bool)
    def _on_edit_mode_toggled(self, checked: bool):
        """
        Вызывается при переключении режима редактирования.
        Если режим редактирования отключен и есть несохраненные изменения, то выводит предупреждение о необходимости подтверждения.
        Если пользователь подтвердил удаление, то извлекается соответствующий сигнал.

        Если включён и таблица пуста, автоматически добавляет новую строку
        """
        if not checked and (self.modified_rows or self.deleted_rows or self.new_rows):
            reply = QMessageBox.question(
                self, "Несохранённые изменения",
                "Есть несохранённые изменения. Сохранить перед выходом из режима редактирования?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._save_changes()
                self.edit_mode = False
            elif reply == QMessageBox.StandardButton.No:
                self._load_data()
                self.modified_rows.clear()
                self.deleted_rows.clear()
                self.new_rows.clear()
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

        if self.edit_mode:
            self.action_combo.setVisible(False)
            self.inline_action_combo.setVisible(True)
            self.save_changes_btn.setVisible(True)
            if hasattr(self, 'action_btn') and self.action_btn:
                self.action_btn.setVisible(False)
            self.table_view.setEditTriggers(QAbstractItemView.DoubleClicked)
            self.table_view.doubleClicked.disconnect(self._on_row_double_clicked)
        else:
            self.action_combo.setVisible(True)
            self.inline_action_combo.setVisible(False)
            self.save_changes_btn.setVisible(False)
            if hasattr(self, 'action_btn') and self.action_btn:
                self.action_btn.setVisible(True)
            self.table_view.setEditTriggers(QAbstractItemView.NoEditTriggers)
            self.table_view.doubleClicked.connect(self._on_row_double_clicked)

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
    @preserve_selection
    @Slot()
    def _save_changes(self):
        """
        Сохраняет все изменения в БД.

        1. Удаление удаленных строк
        2. Обновление измененных строк
        3. Создание новых строк

        После сохранения изменений, обновляет данные на странице и восстанавливает кнопку сохранения.
        """
        self.logger.info("=== _save_changes ВЫЗВАН В DynamicListPage ===")
        if not (self.modified_rows or self.deleted_rows or self.new_rows):
            return

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
            # 1. Удаление
            for row in sorted(self.deleted_rows, reverse=True):
                dto = self.source_model.get_item_at_row(row)
                if dto and hasattr(dto, 'id') and dto.id is not None:
                    self.service.delete(dto.id)
                    self.logger.info(f"Удалена запись ID={dto.id}")
                self.source_model.remove_row(row)
            self.deleted_rows.clear()

            # 2. Обновление
            for row in self.modified_rows:
                dto = self.source_model.get_item_at_row(row)
                if dto and hasattr(dto, 'id') and dto.id is not None:
                    updated = self.service.update(dto)
                    self.source_model.update_row(row, updated)
                    self.logger.info(f"Обновлена запись ID={updated.id}")
            self.modified_rows.clear()

            # 3. Новые строки
            for row in self.new_rows:
                dto = self.source_model.get_item_at_row(row)
                if dto:
                    created = self.service.create(dto)
                    self.source_model.update_row(row, created)
                    self.logger.info(f"Создана новая запись ID={created.id}")
            self.new_rows.clear()

            self._load_data()
            QMessageBox.information(self, "Успех", "Изменения сохранены.")
        except Exception as e:
            self.logger.exception(f"Ошибка при сохранении изменений: {e}")
            QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить изменения: {e}")
        finally:
            self.table_view.setEnabled(True)
            self._update_save_button_state()

class ListUIMixin:

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
        self.table_view.doubleClicked.connect(self._on_row_double_clicked)

        # Модель таблицы
        self.source_model = DynamicTableModel(self.current_data, self.columns)
        self.source_model.row_modified.connect(self._on_row_modified) # Подключаем сигнал изменения строки для отслеживания изменений

        # Прокси-модель
        self.proxy_model = AdvancedFilterProxyModel()
        self.proxy_model.setSourceModel(self.source_model)
        self.table_view.setModel(self.proxy_model)

        # Настройка заголовка таблицы
        header = self.table_view.horizontalHeader()
        if hasattr(header, 'set_get_unique_values_func'):
            header.set_get_unique_values_func(self.get_unique_values_for_column)
            header.filter_requested.connect(self.on_filter_requested)
            header.filter_clear_requested.connect(self.on_filter_clear)

        header.setStretchLastSection(True)
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)

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
        for col_idx, col_info in enumerate(self.columns):
            field_name = col_info['name']
            config = self.field_configs.get(field_name, {})

            choices = config.get('choices')
            if choices:
                delegate = ComboBoxDelegate(self.table_view, choices)
                self.table_view.setItemDelegateForColumn(col_idx, delegate)
                continue

            widget_type = config.get('widget_type')
            if widget_type == 'date':
                delegate = DateDelegate(self.table_view)
                self.table_view.setItemDelegateForColumn(col_idx, delegate)
                continue
            elif widget_type == 'time':
                delegate = TimeDelegate(self.table_view)
                self.table_view.setItemDelegateForColumn(col_idx, delegate)
                continue

            field_type = col_info.get('type')
            if field_type == datetime.date:
                delegate = DateDelegate(self.table_view)
                self.table_view.setItemDelegateForColumn(col_idx, delegate)
            elif field_type == datetime.time:
                delegate = TimeDelegate(self.table_view)
                self.table_view.setItemDelegateForColumn(col_idx, delegate)
            elif field_type == bool:
                delegate = BoolDelegate(self.table_view)
                self.table_view.setItemDelegateForColumn(col_idx, delegate)

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

        row = self.source_model.add_row(new_dto)
        self.new_rows.add(row)
        self._update_row_color(row)
        self._update_save_button_state()

        proxy_index = self.proxy_model.mapFromSource(self.source_model.index(row, 0))
        if proxy_index.isValid():
            self.table_view.setCurrentIndex(proxy_index)
            self.table_view.scrollTo(proxy_index)

        self.logger.info(f"Добавлена новая строка (индекс {row})")

    @Slot()
    def _mark_selected_for_deletion(self):
        if not self.selected_dto:
            return
        proxy_index = self.table_view.currentIndex()
        if not proxy_index.isValid():
            return
        
        row = proxy_index.row()
        if row in self.deleted_rows:
            return
        
        # Добавляем в множество удалённых
        self.deleted_rows.add(row)
        # Если строка была изменена или новая, убираем из соответствующих множеств
        self.modified_rows.discard(row)
        self.new_rows.discard(row)
        self._update_row_color(row)
        self._update_save_button_state()

        self.table_view.clearSelection()
        self.selected_dto = None
        # if hasattr(self, 'delete_btn'):
        #     self.delete_btn.setEnabled(False)
        if hasattr(self, 'action_btn'):
            self.action_btn.setEnabled(False)

        self.logger.info(f"Строка {row} помечена на удаление")

class DynamicListPage(
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

        # Словарь для отслеживания изменённых строк:
        # modified_rows: set of row indices, которые были изменены пользователем (но ещё не сохранены)
        self.modified_rows: Set[int] = set()
        # deleted_rows: set of row indices, помеченные на удаление (соответствующие DTO будут удалены при сохранении)
        self.deleted_rows: Set[int] = set()
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

        self._setup_ui()
        
        self._load_data() # загрузка данных на страницу

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
        self._update_row_color(row)
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
            if self.selected_dto:
                self._mark_selected_for_deletion()
            else:
                QMessageBox.warning(self, "Внимание", "Выберите строку для удаления.")

        # Сбрасываем индекс на заглушку (0), но блокируем сигнал, чтобы не вызывать снова
        self.inline_action_combo.blockSignals(True)
        self.inline_action_combo.setCurrentIndex(0)
        self.inline_action_combo.blockSignals(False)