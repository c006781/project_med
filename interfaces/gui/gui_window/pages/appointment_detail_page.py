# -*- coding: utf-8 -*-
"""
Страница просмотра и редактирования приёма.
Позволяет изменять дату, время, заметку, добавлять и удалять фото.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QDateEdit, QTimeEdit,
    QTextEdit, QPushButton, QMessageBox, QHBoxLayout,
    QListWidget, QListWidgetItem, QFileDialog, QInputDialog, QLabel
)
from PySide6.QtCore import Qt, Slot, QDate, QTime, QSize
from PySide6.QtGui import QPixmap, QIcon

from interfaces.gui.gui_window.pages.base_page import BasePage
from app.services import AppointmentService, PhotoService, NoteService
from app.dto import AppointmentDTO
from app.exceptions import AppointmentNotFoundError, PhotoFileError
from app.dependencies import get_appointment_service, get_photo_service, get_note_service
from app.utils.logger.logger import AppLogger


class AppointmentDetailPage(BasePage):
    """
    Страница создания/редактирования приёма.
    """

    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="AppointmentDetailPage.__init__",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = AppLogger.get_instance("gui.AppointmentDetailPage")
        self.appointment_service = get_appointment_service()
        self.photo_service = get_photo_service()
        self.note_service = get_note_service()

        self.current_patient_id = None
        self.current_appointment_id = None
        self.current_note_id = None

        self._setup_ui()
        self._clear_form()

    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="AppointmentDetailPage._setup_ui",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _setup_ui(self):
        """Создаёт форму."""
        main_layout = QVBoxLayout(self)

        # Форма
        form_layout = QFormLayout()

        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        form_layout.addRow("Дата:", self.date_edit)

        self.time_edit = QTimeEdit()
        self.time_edit.setTime(QTime.currentTime())
        form_layout.addRow("Время:", self.time_edit)

        self.note_text = QTextEdit()
        form_layout.addRow("Заметка:", self.note_text)

        main_layout.addLayout(form_layout)

        # Список фото
        self.photo_list = QListWidget()
        self.photo_list.setIconSize(QSize(100, 100))
        self.photo_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.photo_list.setResizeMode(QListWidget.ResizeMode.Adjust)
        main_layout.addWidget(QLabel("Фотографии:"))
        main_layout.addWidget(self.photo_list)

        # Кнопки управления фото
        photo_btn_layout = QHBoxLayout()
        self.add_photo_btn = QPushButton("Добавить фото")
        self.add_photo_btn.clicked.connect(self._add_photo)
        photo_btn_layout.addWidget(self.add_photo_btn)

        self.delete_photo_btn = QPushButton("Удалить выбранное")
        self.delete_photo_btn.clicked.connect(self._delete_photo)
        photo_btn_layout.addWidget(self.delete_photo_btn)
        photo_btn_layout.addStretch()
        main_layout.addLayout(photo_btn_layout)

        # Кнопки сохранения/отмены
        btn_layout = QHBoxLayout()
        self.save_btn = QPushButton("Сохранить")
        self.save_btn.clicked.connect(self._save_appointment)
        btn_layout.addWidget(self.save_btn)

        self.cancel_btn = QPushButton("Отмена")
        self.cancel_btn.clicked.connect(self._cancel)
        btn_layout.addWidget(self.cancel_btn)

        btn_layout.addStretch()
        main_layout.addLayout(btn_layout)

    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="AppointmentDetailPage._clear_form",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _clear_form(self):
        """Очищает форму."""
        self.date_edit.setDate(QDate.currentDate())
        self.time_edit.setTime(QTime.currentTime())
        self.note_text.clear()
        self.photo_list.clear()
        self.current_note_id = None

    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="AppointmentDetailPage.on_enter",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def on_enter(self, extra_data=None):
        """
        При входе загружаем данные приёма, если передан appointment_id.
        extra_data: {'patient_id': ..., 'appointment_id': ...}
        """
        self.current_patient_id = extra_data.get('patient_id') if extra_data else None
        self.current_appointment_id = extra_data.get('appointment_id') if extra_data else None

        if self.current_appointment_id is not None:
            # Режим редактирования
            self._load_appointment(self.current_appointment_id)
        else:
            # Режим создания
            self._clear_form()
            self.current_note_id = None

    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="AppointmentDetailPage._load_appointment",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _load_appointment(self, appointment_id):
        """Загружает данные приёма и заполняет форму."""
        try:
            app = self.appointment_service.get_appointment(appointment_id)
            self.current_patient_id = app.patient_id
            if app.date:
                self.date_edit.setDate(QDate(app.date.year, app.date.month, app.date.day))
            if app.time:
                self.time_edit.setTime(QTime(app.time.hour, app.time.minute))
            self.note_text.setText(app.note_text or "")
            self.current_note_id = app.note_id

            # Загружаем фото
            self._load_photos(appointment_id)

            self.logger.debug(f"Загружен приём ID={appointment_id}")
        except AppointmentNotFoundError:
            QMessageBox.warning(self, "Ошибка", "Приём не найден.")
            self._cancel()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить данные: {e}")
            self.logger.exception("Ошибка загрузки приёма")

    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="AppointmentDetailPage._load_photos",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _load_photos(self, appointment_id):
        """Загружает список фото для приёма."""
        self.photo_list.clear()
        try:
            photos = self.photo_service.get_photos_for_appointment(appointment_id)
            for photo in photos:
                # Здесь нужно получить полный путь к файлу
                # Временно используем заглушку
                pixmap = QPixmap()  # должна загружаться из photo.file_path
                if not pixmap.isNull():
                    icon = QIcon(pixmap.scaled(100, 100, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                else:
                    icon = QIcon()
                item = QListWidgetItem(icon, photo.description or "")
                item.setData(Qt.ItemDataRole.UserRole, photo.id)
                self.photo_list.addItem(item)
        except Exception as e:
            self.logger.exception("Ошибка загрузки фото")

    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="AppointmentDetailPage._add_photo",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    @Slot()
    def _add_photo(self):
        """Добавляет новое фото к приёму."""
        if not self.current_appointment_id:
            QMessageBox.warning(self, "Предупреждение", "Сначала сохраните приём.")
            return
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Выберите изображение", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.gif)"
        )
        if not file_path:
            return
        description, ok = QInputDialog.getText(self, "Описание", "Введите описание фото:")
        if not ok:
            description = ""
        try:
            photo_dto = self.photo_service.add_photo_to_appointment(
                self.current_appointment_id, file_path, description
            )
            QMessageBox.information(self, "Успех", "Фото добавлено.")
            self._load_photos(self.current_appointment_id)  # обновить список
            self.logger.info(f"Добавлено фото ID={photo_dto.id} к приёму {self.current_appointment_id}")
        except PhotoFileError as e:
            QMessageBox.critical(self, "Ошибка", str(e))
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось добавить фото: {e}")
            self.logger.exception("Ошибка добавления фото")

    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="AppointmentDetailPage._delete_photo",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    @Slot()
    def _delete_photo(self):
        """Удаляет выбранное фото."""
        current_item = self.photo_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "Предупреждение", "Выберите фото для удаления.")
            return
        photo_id = current_item.data(Qt.ItemDataRole.UserRole)
        reply = QMessageBox.question(
            self, "Подтверждение",
            "Удалить это фото? Файл будет удалён с диска.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                self.photo_service.delete_photo(photo_id)
                self._load_photos(self.current_appointment_id)
                self.logger.info(f"Удалено фото ID={photo_id}")
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Не удалось удалить фото: {e}")
                self.logger.exception("Ошибка удаления фото")

    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="AppointmentDetailPage._save_appointment",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    @Slot()
    def _save_appointment(self):
        """Сохраняет приём (создание или обновление)."""
        date = self.date_edit.date().toPython()
        time = self.time_edit.time().toPython()
        note_text = self.note_text.toPlainText().strip()

        # Создаём DTO
        dto = AppointmentDTO(
            id=self.current_appointment_id,
            patient_id=self.current_patient_id,
            date=date,
            time=time,
            note_id=self.current_note_id
        )

        try:
            if self.current_appointment_id is None:
                # Создание
                created = self.appointment_service.create_appointment(dto, note_text=note_text)
                self.current_appointment_id = created.id
                self.current_note_id = created.note_id
                QMessageBox.information(self, "Успех", f"Приём создан с ID {created.id}")
                self.logger.info(f"Создан приём ID={created.id}")
            else:
                # Обновление
                updated = self.appointment_service.update_appointment(dto, note_text=note_text)
                self.current_note_id = updated.note_id
                QMessageBox.information(self, "Успех", f"Приём ID {updated.id} обновлён")
                self.logger.info(f"Обновлён приём ID={updated.id}")
            # Возврат к списку приёмов
            self._go_back()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить приём: {e}")
            self.logger.exception("Ошибка сохранения приёма")

    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="AppointmentDetailPage._cancel",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    @Slot()
    def _cancel(self):
        """Отмена редактирования."""
        self._go_back()

    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="AppointmentDetailPage._go_back",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _go_back(self):
        """Возврат к предыдущей странице (списку приёмов)."""
        if self.page_manager:
            self.page_manager.go_back()