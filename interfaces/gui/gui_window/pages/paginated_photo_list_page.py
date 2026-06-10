# interfaces/gui/gui_window/pages/paginated_photo_list_page.py
"""
Страница списка фотографий на базе PaginatedListPage.
Используется в новом фрейме с двумя таблицами (приёмы + фото).
"""

import os
from typing import List, Optional

from app.utils.logger.logger import AppLogger

from app.dependencies import get_photo_service

from app.dto.dto_all import PhotoDTO
from app.dto.field_configs import PHOTO_CONFIG

from interfaces.gui.gui_window.pages.paginated_list_page import PaginatedListPage

from PySide6.QtWidgets import QFileDialog, QMessageBox

class PaginatedPhotoListPage(PaginatedListPage):
    """
    Страница списка фотографий (одно фото на строку) с пагинацией,
    фильтрацией и черновиками. Предназначена для использования в связке
    с PaginatedAppointmentListPage.
    """

    @AppLogger.get_instance(
        name='PaginatedPhotoListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def __init__(
        self, 
        parent=None, 
        shared_registry=None, 
        show_controls=None,
        exclude_columns=None,
    ):
        if show_controls is None:
            show_controls = [
                'edit_mode_btn',
                'action_combo',
                'inline_action_combo',
                'save_btn',
                'search'
            ]


        if exclude_columns is None:
            exclude_columns = []

        exclude_columns = exclude_columns + ['appointment_id']

        super().__init__(
            service=get_photo_service(),
            dto_class=PhotoDTO,
            field_configs=PHOTO_CONFIG,
            page_title="Фотографии",
            add_action_text="Добавить фото",
            action_button_text=None,
            parent=parent,
            exclude_columns=exclude_columns,   # скрываем столбец ID приёма
            entity_type="photo",
            shared_registry=shared_registry,
            show_controls=show_controls
        )

        # # Отключаем обработку двойного клика на уровне страницы,
        # # потому что фото редактируется через делегат ImageThumbnailDelegate
        # self.action_requested.disconnect()

    @AppLogger.get_instance(
        name='PaginatedPhotoListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _get_parent_id_for_new_row(self, dto) -> int: # в будущем перенести в PaginatedListPage и сделать диначическим
        
        """
        Возвращает ID родительской сущности для новой строки фото.

        Для фото родителем является приём (appointment). ID приёма должен быть передан
        в self._context_params под ключом 'appointment_id' (устанавливается родительским фреймом).

        Returns:
            ID приёма или None, если контекст не задан.
        """
        # return self._context_params.get('appointment_id', None)
        return getattr(dto, 'appointment_id', None)

    @AppLogger.get_instance(
        name='PaginatedPhotoListPage',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def _get_parent_id(self, child_id: int) -> Optional[int]:
        """
        Возвращает ID приёма (appointment_id) для фото.
        Используется для уведомления родителя об изменениях.
        """
        # Находим строку по ID фото в модели
        row = self._find_row_by_id(child_id)
        if row < 0:
            return None
        
        dto = self.source_model.get_item_at_row(row)
        if dto:
            return getattr(dto, 'appointment_id', None)
        
        return None
    
    @AppLogger.get_instance(
        name='PaginatedPhotoListPage',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def _get_parent_entity_type(self, child_id: int) -> str:
        """
        Родитель фото – приём, тип 'appointment'.
        """
        return 'appointment'

    @AppLogger.get_instance(
        name='PaginatedPhotoListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _get_child_ids(self, parent_id: int) -> list:
        """
        У фото нет дочерних сущностей.
        """
        return []

    @AppLogger.get_instance(
        name='PaginatedPhotoListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def add_photo_to_new_row(self, file_path: str) -> bool:
        """Создаёт новую строку с фото (использует _add_photo_from_file)."""
        photo_field = self._get_photo_field_name_impl()
        
        if not photo_field:
            return False
        
        self._add_photo_from_file(file_path, photo_field)

        return True
    
    @AppLogger.get_instance(
        name='PaginatedPhotoListPage',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def _get_selected_photo_files(self) -> List[str]:
        """
        Открывает диалог выбора файлов и возвращает список путей к выбранным изображениям.
        Если пользователь отменил выбор, возвращает пустой список.
        """
        extensions = self._get_allowed_extensions_for_photo()
        filter_str = f"Images (*{' *'.join(extensions)})"
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Выберите изображения",
            "",
            filter_str
        )
        return file_paths or []

    @AppLogger.get_instance(
        name='PaginatedPhotoListPage',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def add_photo_directly(self) -> None:
        """Добавляет фото напрямую в БД (вне режима редактирования)."""
        # Получаем ID приёма из контекстных параметров (устанавливается родительским фреймом)
        appointment_id = self._context_params.get('appointment_id')
        if not appointment_id:
            QMessageBox.warning(self, "Ошибка", "Не указан приём для добавления фото.")
            return

        # Открываем диалог выбора файла
        file_paths = self._get_selected_photo_files()

        if not file_paths:
            return

        try:
            # Сохраняем фото напрямую через сервис
            photo_service = get_photo_service()
            added = 0
            for file_path in file_paths:
                try:
                    photo_dto = photo_service.add_photo_to_appointment(appointment_id, file_path, "")
                    # self.logger.debug(f"Фото добавлено напрямую: id={photo_dto.id}")
                    added += 1
                except Exception as e:
                    self.logger.exception(f"Ошибка добавления фото {file_path}: {e}")
                    QMessageBox.critical(self, "Ошибка", f"Не удалось добавить фото {os.path.basename(file_path)}: {e}")
            
            if added:
                self.logger.debug(f"Добавлено {added} фото напрямую для приёма {appointment_id}")
                # Обновляем таблицу фото (перезагружаем данные с фильтром по appointment_id)
                self.reload_with_filters({
                    'column': 'appointment_id',
                    'operator': 'eq',
                    'value': appointment_id
                })

                # Уведомляем родительский фрейм об изменении родительской сущности (приёма)
                self.parent_entity_updated.emit('appointment', appointment_id)

        except Exception as e:
            self.logger.exception(f"Ошибка добавления фото: {e}")
            QMessageBox.critical(self, "Ошибка", f"Не удалось добавить фото: {e}")

    @AppLogger.get_instance(
        name='PaginatedPhotoListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _add_row(self) -> None:
        """
        Переопределяет метод добавления строки: открывает диалог выбора файлов
        и создаёт новую строку с фото, вставляя её в позицию согласно правилам
        (после выделенной строки или в начало).
        """
        if not self.edit_mode:
            return

        # extensions = self._get_allowed_extensions_for_photo()
        # filter_str = f"Images (*{' *'.join(extensions)})"

        # file_path, _ = QFileDialog.getOpenFileName(
        #     self,
        #     "Выберите изображение",
        #     "",
        #     filter_str
        # )
        # if not file_path:
        #     return

        # photo_field = self._get_photo_field_name_impl()
        # if photo_field is None:
        #     self.logger.error("add_row: не найдено поле с фото")
        #     return
        file_paths = self._get_selected_photo_files()
        if not file_paths:
            return

        photo_field = self._get_photo_field_name_impl()
        if photo_field is None:
            self.logger.error("_add_row: не найдено поле с фото")
            return

        for file_path in file_paths:
            self._add_photo_from_file_at_pos(file_path, photo_field)

        self._update_save_button_state()
        0==0

    @AppLogger.get_instance(
        name='PaginatedPhotoListPage',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def add_row(self) -> None:
        """
        Переопределяем: в режиме редактирования – добавляем строку с черновиком (inline),
        в обычном режиме – добавляем фото напрямую в БД.
        """
        if self.edit_mode:
            self._add_row()  # вызывает _add_inline_row
        else:
            self.add_photo_directly()

    @AppLogger.get_instance(
        name='PaginatedPhotoListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _update_ui_for_edit_mode(self, edit_mode: bool):
        super()._update_ui_for_edit_mode(edit_mode)
        # Для таблицы фото в не-режиме редактирования отключаем кнопки добавления/удаления/редактирования
        if hasattr(self, 'side_toolbar'):

            # has_selection = self.get_current_selected_dto() is not None
            # # кнопки активны только при наличии выбранной строки
            # self.side_toolbar.delete_btn.setEnabled(has_selection)
            # # В не-режиме редактирования кнопки активны только при наличии выбранной строки
            # self.side_toolbar.edit_btn.setEnabled(not self.edit_mode and has_selection)

            self.side_toolbar.add_btn.setEnabled(True)
            self.side_toolbar.delete_btn.setEnabled(True)
            self.side_toolbar.edit_btn.setEnabled(edit_mode)   

            #  Кнопка обновления активна: вне режима редактирования И есть выбранный приём
            has_appointment = bool(self._context_params.get('appointment_id'))
            self.side_toolbar.refresh_btn.setEnabled(not edit_mode and has_appointment)


    def reload_data(self) -> None:
        appointment_id = self._context_params.get('appointment_id')
        if appointment_id:
            self.reload_with_filters({
                'column': 'appointment_id',
                'operator': 'eq',
                'value': appointment_id
            })
        else:
            super().reload_data()