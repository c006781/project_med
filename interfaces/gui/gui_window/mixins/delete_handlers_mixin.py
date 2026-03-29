# -*- coding: utf-8 -*-
"""
Миксин с обработчиками удаления записей (пациентов, приёмов, заметок, фото).
"""

from app.utils.logger.logger import AppLogger
from app.dependencies import (
    get_patient_service, get_appointment_service,
    get_note_service, get_photo_service
)
from PySide6.QtWidgets import QMessageBox


class DeleteHandlersMixin:
    """
    Миксин, содержащий слоты для удаления сущностей с подтверждением.
    """

    @AppLogger.get_instance(
        name='DeleteHandlersMixin',
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _on_patient_delete(self, dto):
        """
        Удаление пациента после подтверждения пользователя.
        Удаляются также все связанные приёмы и фотографии (каскадно).
        """
        # Запрашиваем подтверждение
        reply = QMessageBox.question(
            self, "Подтверждение",
            f"Удалить пациента {dto.last_name} {dto.first_name}? "
            "Все связанные приёмы и фото также будут удалены.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            service = get_patient_service()
            service.delete_patient(dto.id)
            QMessageBox.information(self, "Успех", "Пациент удалён.")
            self.patient_list_page._load_data()      # обновляем список
            self.logger.info(f"Удалён пациент ID={dto.id}")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось удалить: {e}")
            self.logger.exception(f"Ошибка удаления пациента: {e}")

    @AppLogger.get_instance(
        name='DeleteHandlersMixin',
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _on_appointment_delete(self, dto):
        """
        Удаление приёма после подтверждения.
        """
        reply = QMessageBox.question(
            self, "Подтверждение",
            f"Удалить приём ID {dto.id} от {dto.date}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            service = get_appointment_service()
            service.delete_appointment(dto.id)
            QMessageBox.information(self, "Успех", "Приём удалён.")
            self.appointment_list_page._load_data()   # обновляем список
            self.logger.info(f"Удалён приём ID={dto.id}")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось удалить: {e}")
            self.logger.exception(f"Ошибка удаления приёма: {e}")

    @AppLogger.get_instance(
        name='DeleteHandlersMixin',
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _on_note_delete(self, dto):
        """
        Удаление заметки после подтверждения.
        """
        reply = QMessageBox.question(
            self, "Подтверждение",
            f"Удалить заметку ID {dto.id}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            service = get_note_service()
            service.delete_note(dto.id)
            QMessageBox.information(self, "Успех", "Заметка удалена.")
            self.note_list_page._load_data()         # обновляем список
            self.logger.info(f"Удалена заметка ID={dto.id}")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось удалить: {e}")
            self.logger.exception(f"Ошибка удаления заметки: {e}")

    @AppLogger.get_instance(
        name='DeleteHandlersMixin',
        enable_file_logging='system',
        use_name_in_filename='system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _on_photo_delete(self, dto):
        """
        Удаление фотографии (запись в БД и физический файл) после подтверждения.
        """
        reply = QMessageBox.question(
            self, "Подтверждение",
            f"Удалить фото ID {dto.id}? Файл будет удалён с диска.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            service = get_photo_service()
            service.delete_photo(dto.id)
            QMessageBox.information(self, "Успех", "Фото удалено.")
            self.photo_list_page._load_data()        # обновляем список
            self.logger.info(f"Удалено фото ID={dto.id}")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось удалить: {e}")
            self.logger.exception(f"Ошибка удаления фото: {e}")