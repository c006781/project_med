# interfaces/gui/gui_window/mixins/edit_mode_mixin.py

"""
Миксин для включения/выключения режима редактирования, сохранения и отмены изменений.

**Назначение:**
    Предоставляет страницам списка (например, PaginatedListPage) универсальный механизм
    переключения между режимом просмотра и режимом редактирования. В режиме редактирования
    пользователь может изменять данные прямо в таблице, добавлять/удалять строки,
    а затем сохранять или отменять изменения.

**Абстрактные методы, которые должен реализовать класс-наследник:**
    - _has_unsaved_changes() -> bool
    - _discard_all_changes() -> None
    - _save_all_changes_impl() -> bool
    - reload_data() -> None

**Как использовать:**
    - Класс, использующий этот миксин, должен определить атрибут `edit_mode` (обычно через property),
      чтобы хранить состояние режима.
    - В `_set_edit_mode` вызывается `_update_ui_for_edit_mode` (если он есть), который должен обновлять UI.

**Примечание:** атрибут `edit_mode` не создаётся в миксине, так как он может быть определён в наследнике.
    Это позволяет гибко настраивать его хранение (например, через property в PaginatedListPage).

Пример:
    >>> class MyListPage(BasePage, EditModeMixin):
    ...     def __init__(self):
    ...         super().__init__()
    ...         self.edit_mode = False
    ...         self.edit_mode_btn = QPushButton("Режим редактирования")
    ...         self.edit_mode_btn.setCheckable(True)
    ...         self.edit_mode_btn.toggled.connect(self.toggle_edit_mode)
    ...
    ...     def _has_unsaved_changes(self) -> bool:
    ...         return bool(self.modified_ids or self.deleted_ids or self.new_rows)
    ...
    ...     def _discard_all_changes(self) -> None:
    ...         self.modified_ids.clear()
    ...         self.deleted_ids.clear()
    ...         self.new_rows.clear()
    ...         self.reload_data()
    ...
    ...     def _save_all_changes_impl(self) -> bool:
    ...         try:
    ...             self._save_new_rows()
    ...             self._save_modified_rows()
    ...             self._save_deleted_rows()
    ...             return True
    ...         except Exception:
    ...             return False
    ...
    ...     def reload_data(self) -> None:
    ...         self._load_data()
"""

from abc import ABC, abstractmethod

from app.utils.logger.logger import AppLogger

from PySide6.QtWidgets import QMessageBox
# from PySide6.QtGui import QColor


class EditModeMixin(ABC):
    """
    Предоставляет методы для переключения режима редактирования,
    сохранения и отмены изменений.

    Сигналы (должны быть определены в наследнике при необходимости):
        - edit_mode_changed(bool): испускается при переключении режима.

    Атрибуты (должны быть определены в наследнике):
        edit_mode (bool): Текущее состояние режима редактирования.
    """

    # ------------------------------------------------------------------
    # Ленивая инициализация атрибутов (без __init__)
    # ------------------------------------------------------------------

    @property
    def logger(self) -> AppLogger:
        """Логгер для записи событий (ленивая инициализация)."""

        if not hasattr(self, '_logger'):
            self._logger = AppLogger.get_instance(
                name='gui.EditModeMixin',
                enable_file_logging = 'user',
                use_name_in_filename = False, # 'system'
            )
        return self._logger

    @logger.setter
    def logger(self, value):
        self._logger = value


    @property 
    def _saving_in_progress(self) -> bool: # убрал, так как наследуется  из EditModeMixin
        """
        Флаг блокировки повторного входа в методы сохранения.

        Используется в `_save_all_changes_impl` и `save_rows_with_children`
        для предотвращения рекурсивных вызовов или одновременного сохранения.

        Returns:
            True, если сохранение уже выполняется в другом вызове.
        """

        if not hasattr(self, '__saving_in_progress'):
            self.__saving_in_progress = False  # флаг блокировки

        return self.__saving_in_progress

    @_saving_in_progress.setter
    def _saving_in_progress(self, value: bool):
        self.__saving_in_progress = value  # флаг блокировки

    @property
    def edit_mode(self) -> bool:
        """
        Режим редактирования (True – включён, False – выключен).

        Должен быть переопределён в наследнике.
        """

        if not hasattr(self, '_edit_mode'):
            self._edit_mode = False
        return self._edit_mode

    @edit_mode.setter
    def edit_mode(self, value: bool):
        self._edit_mode = value

    # ------------------------------------------------------------------
    # Абстрактные методы, которые должен реализовать наследник
    # ------------------------------------------------------------------

    @abstractmethod
    def _has_unsaved_changes(self) -> bool:
        """
        Проверяет наличие несохранённых изменений.

        Должен быть реализован в наследнике.

        Returns:
            True, если есть несохранённые изменения (новые, изменённые, удалённые строки
            или черновики дочерних компонентов), иначе False.
        """
        pass

    @abstractmethod
    def _discard_all_changes(self) -> None:
        """"
        Полностью отменяет все несохранённые изменения.

        **Действия:**
            - Очищает реестр черновиков для текущего типа сущности.
            - Удаляет все новые строки, сбрасывает изменённые и удалённые записи.
            - Перезагружает данные из БД (через reload_data).

        **ВНИМАНИЕ:** При переопределении в наследниках убедитесь, что вы вызываете
        `discard_entity_subtree` для всех сущностей, что автоматически уменьшит
        счётчики родителей. Не нужно вручную обновлять счётчики здесь.

        Должен быть реализован в наследнике.
        """
        pass

    @abstractmethod
    def reload_data(self) -> None:
        """Перезагружает данные из БД (сбрасывает текущую страницу) 
        (должен быть реализован в наследнике).
        """
        pass

    @abstractmethod
    def _save_all_changes_impl(self) -> bool:
        """
        Основной метод сохранения всех изменений (возвращает True при успехе).

        **Порядок действий (рекомендуемый):**
            1. Сохранить новые строки (получить реальные ID).
            2. Применить дочерние черновики (фото, заметки и т.д.).
            3. Сохранить изменённые существующие строки.
            4. Удалить помеченные строки.

        ВНИМАНИЕ ДЛЯ НАСЛЕДНИКОВ:
            При реализации этого метода убедитесь, что:
            1. Вы сначала сохраняете новые строки (`_save_new_rows`), которые возвращают словарь
            {temp_id: created_dto}. Это необходимо для переноса дочерних черновиков.
            2. Затем сохраняете дочерние черновики (например, фото) через `_save_child_changes`.
            3. Затем сохраняете изменённые строки (`_save_modified_rows`), и только потом удалённые
            (`_save_deleted_rows`).
            4. ВСЕ обновления счётчиков родителей (увеличение/уменьшение количества активных потомков)
            должны происходить в методах, изменяющих статус сущности (например, в `_save_new_rows`
            и `_save_modified_rows`), а НЕ внутри `clear_own_change`. Это предотвратит двойной учёт.
        
        Returns:
            True, если сохранение прошло успешно, иначе False.
        """
            
        pass

    # ------------------------------------------------------------------
    # Публичные методы управления режимом
    # ------------------------------------------------------------------

    @AppLogger.get_instance(
        name='EditModeMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def toggle_edit_mode(self, enable: bool) -> None:
        """
        Включает или выключает режим редактирования.

        **Логика:**
            - Если выключаем режим (enable=False) и есть несохранённые изменения (`_has_unsaved_changes()`),
              показываем диалог с тремя вариантами:
                * Сохранить – вызывает `_save_all_changes_impl()`.
                * Не сохранять – вызывает `_discard_all_changes()` (отменяет все изменения).
                * Отмена – остаёмся в режиме редактирования.
            - Включаем/выключаем режим через `_set_edit_mode`.

        **Абстрактные методы, которые должен реализовать наследник:**
            - `_has_unsaved_changes() -> bool` – проверка наличия изменений.
            - `_discard_all_changes() -> None` – отмена всех изменений.
            - `_save_all_changes_impl() -> bool` – сохранение всех изменений.
            - `reload_data() -> None` – перезагрузка данных.

        **Важно:** 
            Не вызывает диалог повторно при выходе из режима после успешного сохранения.

        Args:
            enable: True – включить режим редактирования, False – выключить.

        Note:
            Не вызывает диалог повторно при выходе из режима после успешного сохранения.
        """

        if enable == self.edit_mode:
            return
        
        if not enable and self._has_unsaved_changes():
            reply = QMessageBox.question(
                self, "Несохранённые изменения",
                "Есть несохранённые изменения. Сохранить перед выходом из режима редактирования?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel
            )

            if reply == QMessageBox.StandardButton.Yes:
                if not self._save_all_changes_impl():
                    return
                
            elif reply == QMessageBox.StandardButton.No:
                self._discard_all_changes()

            else:
                return
            
        self._set_edit_mode(enable)

    @AppLogger.get_instance(
        name='EditModeMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def is_edit_mode(self) -> bool:
        """Возвращает True, если режим редактирования включён."""
        return getattr(self, 'edit_mode', False)

    @AppLogger.get_instance(
        name='EditModeMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def save_all_changes(self) -> bool:
        """
        Публичный метод для сохранения всех изменений (вызывается из UI).

        Использует флаг `_saving_in_progress` для предотвращения повторного входа
        (например, при многократном нажатии на кнопку «Сохранить»).

        Реальная логика сохранения находится в `_save_all_changes_impl`, который
        должен быть реализован в наследнике.

        Returns:
            True, если сохранение прошло успешно, иначе False.
        """

        if self._saving_in_progress:
            self.logger.warning("save_all_changes уже выполняется, повторный вызов игнорирован")
            return False
        
        self._saving_in_progress = True
        try:
            return self._save_all_changes_impl()
        
        finally:
            self._saving_in_progress = False

    # def _save_all_changes_impl(self) -> bool:
    #     """Сохраняет все изменения в БД. Возвращает True при успехе."""
    #
    #     if not self._has_unsaved_changes():
    #         return True
    #
    #     reply = QMessageBox.question(
    #         self, "Подтверждение",
    #         "Сохранить все изменения?",
    #         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
    #     )
    #
    #     if reply != QMessageBox.StandardButton.Yes:
    #         return False
    #
    #     try:
    #         self._save_new_rows()
    #         self._save_modified_rows()
    #         self._save_deleted_rows()
    #         self.reload_data()
    #         self._exit_edit_mode()
    #         QMessageBox.information(self, "Успех", "Изменения сохранены.")
    #
    #         return True
    #
    #     except Exception as e:
    #         self.logger.exception(f"Ошибка сохранения: {e}")
    #         QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить: {e}")
    #
    #         return False

    @AppLogger.get_instance(
        name='EditModeMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def cancel_all_changes(self) -> None:
        """
        Отменяет все изменения и перезагружает данные.

        Вызывает `_discard_all_changes()` и `reload_data()`, после чего выходит из режима редактирования.
        """
        
        self._discard_all_changes()
        self.reload_data()
        self._exit_edit_mode()

    # ------------------------------------------------------------------
    # Вспомогательные методы (могут быть переопределены)
    # ------------------------------------------------------------------

    # def _has_unsaved_changes(self) -> bool:
    #     """
    #     Возвращает True, если есть несохранённые изменения:
    #     - новые строки (new_rows)
    #     - удалённые строки (deleted_ids)
    #     - изменённые строки (modified_ids)
    #     """
    #
    #     return bool(self.modified_ids or self.deleted_ids or self.new_rows)

    # def _discard_all_changes(self):
    #     self.modified_ids.clear()
    #     self.deleted_ids.clear()
    #     self.new_rows.clear()
    #     self._clear_drafts()
    #     self.source_model.clear_row_colors()

    @AppLogger.get_instance(
        name='EditModeMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _set_edit_mode(self, enable: bool)-> None:
        """
        Устанавливает флаг режима и обновляет UI.

        Args:
            enable: True – включить режим редактирования, False – выключить.
        """

        self.edit_mode = enable

        if hasattr(self, 'source_model'):
            self.source_model.set_checkbox_column_visible(enable)

        if hasattr(self, '_update_ui_for_edit_mode'):
            self._update_ui_for_edit_mode(enable)

    # def _set_edit_mode(self, enable: bool):
    #     self.edit_mode = enable
    #     self.source_model.set_checkbox_column_visible(enable)
    #     self._update_ui_for_edit_mode(enable)

    @AppLogger.get_instance(
        name='EditModeMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _exit_edit_mode(self)-> None:
        """Выходит из режима редактирования (без диалога)."""
        if self.edit_mode:
            # self.toggle_edit_mode(False)

            # Выходим без диалога, так как изменения уже сохранены (или отменены)
            self._set_edit_mode(False)

    # def _save_new_rows(self):
    #     raise NotImplementedError
    #
    # def _save_modified_rows(self):
    #     raise NotImplementedError
    #
    # def _save_deleted_rows(self):
    #     raise NotImplementedError

    # def reload_data(self):
    #     """Перезагружает данные – должен быть реализован в наследнике."""
    #
    #     raise NotImplementedError

    # def _clear_drafts(self):
    #     """Очищает черновики – переопределяется в AppointmentListPage."""
    #     pass