# interfaces/gui/gui_window/pages/appointment_list_page.py
# -*- coding: utf-8 -*-
"""
Страница со списком приёмов.
Левая часть - таблица приёмов, правая - детали выбранного приёма (с фото).
При клике на строку в таблице справа показывается информация.
"""
from app.config.config_manager.manager import get_config_env
from app.utils.logger.logger import AppLogger

from app.dependencies import (
    # get_appointment_service, 
    get_photo_service
)

from interfaces.gui.gui_window.pages.dynamic_detail_list_page import DynamicDetailListPage
from interfaces.gui.gui_window.widgets.photo_uploader_widget import PhotoUploaderWidget

from PySide6.QtWidgets import (
    # QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    # QTableView, QPushButton, QHeaderView, QMessageBox,
    # QLineEdit, 
    QLabel, QTextEdit, QListWidget, QListWidgetItem
)

from PySide6.QtCore import (
    Qt, 
    # QAbstractTableModel, QModelIndex, 
    # Signal, Slot, 
    # QSortFilterProxyModel, 
    QSize
)

from PySide6.QtGui import QPixmap, QIcon


class AppointmentListPage(DynamicDetailListPage):
    """
    Страница со списком приёмов с правой панелью (заметка и фото).
    """

    @AppLogger.get_instance(
        name = 'AppointmentListPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="AppointmentListPage.__init__",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def __init__(
        self,
        service,
        loader_func,
        dto_class,
        field_configs,

        # exclude_columns=None,
        *args,
        **kwargs
    ):
        """
        Инициализирует страницу со списком приёмов с правой панелью (заметка и фото).
        """
        
        super().__init__(service, loader_func, dto_class, field_configs, *args, **kwargs)
        
        self.logger = AppLogger.get_instance(
            name = 'gui.AppointmentListPage',
            enable_file_logging = 'user',
            use_name_in_filename = 'user',
        )

        self.photo_service = get_photo_service()

        self.current_appointment_id = None
        self._setup_detail_panel()

    @AppLogger.get_instance(
        name = 'AppointmentListPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _setup_detail_panel(self):
        """
        Создает виджету правой панели.

        Создает виджету с заметкой и фотографиями приема.
        """
        # Создаем виджету с заметкой

        self.note_text_edit = QTextEdit()

        # Установка режима "только для чтения"
        self.note_text_edit.setReadOnly(True)

        # Добавляем виджету с заметкой в верхнюю часть detail_layout
        self.detail_layout.addWidget(QLabel("Заметка:"))
        self.detail_layout.addWidget(self.note_text_edit)




        # # Создаем виджету со списком фотографий
        # self.photo_list = QListWidget()

        # # Установка размера иконок фотографий
        # self.photo_list.setIconSize(QSize(100, 100))

        self.photo_widget = PhotoUploaderWidget()
        config = get_config_env()
        storage_path = config.get('PHOTOS_STORAGE_PATH', './photos')
        self.logger.debug(f'storage_path: {storage_path}')
        self.photo_widget.set_storage_path(storage_path)
        self.photo_widget.set_readonly(True)          # режим только просмотр

        # Добавляем виджету со списком фотографий в верхнюю часть detail_layout
        self.detail_layout.addWidget(QLabel("Фотографии:"))
        self.detail_layout.addWidget(self.photo_widget)


    @AppLogger.get_instance(
        name = 'AppointmentListPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def update_details(self, dto):
        """
        Обновляет правую панель данными выбранного приёма.
        Вызывается автоматически при выборе строки в таблице.

        :param dto: данные приёма
        :type dto: AppointmentDTO
        """
        # self.logger.debug(f"dto {dto}")
        self.logger.debug(f"update_details получил dto типа {type(dto)}")
        if not dto:
            return
        
        self.current_appointment_id = dto.id

        self.note_text_edit.setText(dto.note_text or "")

        # self._load_photos(dto.id)
        self.logger.debug(f"Проверка photos: hasattr={hasattr(dto, 'photos')}, is not None={dto.photos is not None}")

        # Обновляем фото
        # self.logger.debug(f"result {hasattr(dto, 'photos') and dto.photos is not None}")

        if hasattr(dto, 'photos') and dto.photos is not None: # нужно переделать в динамику...
            self.logger.debug(f"dto.photos тип = {type(dto.photos)}")
            self.photo_widget.set_existing_photos(dto.photos)

            self.photo_widget.update()
            self.photo_widget.repaint()
        else:
            self.logger.debug("Нет фото, передаём пустой список")
            self.photo_widget.set_existing_photos([])


    @AppLogger.get_instance(
        name = 'AppointmentListPage',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        # description="AppointmentListPage._load_photos",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _load_photos(self, appointment_id):
        """
        Загружает фото для приёма и отображает их в списке.

        :param appointment_id: ID приёма
        :raises Exception: если произошла ошибка загрузки
        """
        self.photo_list.clear()
        try:
            photos = self.photo_service.get_photos_for_appointment(appointment_id)
            for photo in photos:
                # TODO: загружать реальный QPixmap из файла
                pixmap = QPixmap()  # заглушка
                if not pixmap.isNull():
                    icon = QIcon(pixmap.scaled(100, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                else:
                    icon = QIcon()
                item = QListWidgetItem(icon, photo.description or "")
                item.setData(Qt.UserRole, photo.id)
                self.photo_list.addItem(item)
        except Exception as e:
            self.logger.exception(f"Ошибка загрузки фото: {e}")