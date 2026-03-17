# -*- coding: utf-8 -*-
"""
Страница редактирования/создания пациента.
Содержит форму с полями и кнопку сохранения/удаления.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QLineEdit,
    QDateEdit, QPushButton, QMessageBox, QHBoxLayout
)
from PySide6.QtCore import Slot, QDate

from interfaces.gui.gui_window.pages.base_page import BasePage
from app.services import PatientService
from app.dto import PatientDTO
from app.exceptions import PatientNotFoundError, PatientValidationError
from app.dependencies import get_patient_service
from app.utils.logger.logger import AppLogger


class PatientEditPage(BasePage):
    """
    Страница для просмотра и редактирования данных пациента.
    Если patient_id не передан (или None), создаётся новый пациент.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = AppLogger.get_instance("gui.PatientEditPage")
        self.patient_service = get_patient_service()
        self.current_patient_id = None  # ID редактируемого пациента

        self._setup_ui()
        self._clear_form()

    def _setup_ui(self):
        """Создаёт элементы формы."""
        main_layout = QVBoxLayout(self)

        # Форма
        form_layout = QFormLayout()

        self.first_name_edit = QLineEdit()
        form_layout.addRow("Имя:", self.first_name_edit)

        self.last_name_edit = QLineEdit()
        form_layout.addRow("Фамилия:", self.last_name_edit)

        self.birth_date_edit = QDateEdit()
        self.birth_date_edit.setCalendarPopup(True)
        self.birth_date_edit.setDate(QDate.currentDate())
        self.birth_date_edit.setSpecialValueText("не указана")
        form_layout.addRow("Дата рождения:", self.birth_date_edit)

        self.phone_edit = QLineEdit()
        form_layout.addRow("Телефон:", self.phone_edit)

        self.email_edit = QLineEdit()
        form_layout.addRow("Email:", self.email_edit)

        main_layout.addLayout(form_layout)

        # Кнопки
        btn_layout = QHBoxLayout()

        self.save_btn = QPushButton("Сохранить")
        self.save_btn.clicked.connect(self._save_patient)
        btn_layout.addWidget(self.save_btn)

        self.delete_btn = QPushButton("Удалить")
        self.delete_btn.clicked.connect(self._delete_patient)
        self.delete_btn.setEnabled(False)  # по умолчанию отключена (для нового пациента)
        btn_layout.addWidget(self.delete_btn)

        btn_layout.addStretch()

        self.cancel_btn = QPushButton("Отмена")
        self.cancel_btn.clicked.connect(self._cancel)
        btn_layout.addWidget(self.cancel_btn)

        main_layout.addLayout(btn_layout)

    def _clear_form(self):
        """Очищает поля формы."""
        self.first_name_edit.clear()
        self.last_name_edit.clear()
        self.birth_date_edit.setDate(QDate.currentDate())
        self.phone_edit.clear()
        self.email_edit.clear()

    def on_enter(self, extra_data=None):
        """
        Вызывается при переходе на страницу.
        extra_data может содержать 'patient_id'.
        """
        patient_id = extra_data.get('patient_id') if extra_data else None
        self.current_patient_id = patient_id
        if patient_id is not None:
            # Режим редактирования: загружаем данные
            self._load_patient(patient_id)
            self.delete_btn.setEnabled(True)
        else:
            # Режим создания
            self._clear_form()
            self.delete_btn.setEnabled(False)

    def _load_patient(self, patient_id):
        """Загружает данные пациента по ID и заполняет форму."""
        try:
            patient = self.patient_service.get_patient_by_id(patient_id)
            self.first_name_edit.setText(patient.first_name)
            self.last_name_edit.setText(patient.last_name)
            if patient.birth_date:
                qdate = QDate(patient.birth_date.year, patient.birth_date.month, patient.birth_date.day)
                self.birth_date_edit.setDate(qdate)
            else:
                self.birth_date_edit.setDate(QDate.currentDate())  # или специальное значение
            self.phone_edit.setText(patient.phone or "")
            self.email_edit.setText(patient.email or "")
            self.logger.debug(f"Загружены данные пациента ID={patient_id}")
        except PatientNotFoundError:
            QMessageBox.warning(self, "Ошибка", "Пациент не найден.")
            self._cancel()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить данные: {e}")
            self.logger.exception("Ошибка загрузки пациента")

    @Slot()
    def _save_patient(self):
        """Сохраняет данные пациента (создание или обновление)."""
        # Собираем данные из формы
        first_name = self.first_name_edit.text().strip()
        last_name = self.last_name_edit.text().strip()
        if not first_name or not last_name:
            QMessageBox.warning(self, "Ошибка", "Имя и фамилия обязательны.")
            return

        birth_date = None
        if self.birth_date_edit.date() != QDate.currentDate():
            qdate = self.birth_date_edit.date()
            birth_date = qdate.toPython()

        phone = self.phone_edit.text().strip() or None
        email = self.email_edit.text().strip() or None

        dto = PatientDTO(
            id=self.current_patient_id,
            first_name=first_name,
            last_name=last_name,
            birth_date=birth_date,
            phone=phone,
            email=email
        )

        try:
            if self.current_patient_id is None:
                # Создание
                created = self.patient_service.create_patient(dto)
                QMessageBox.information(self, "Успех", f"Пациент создан с ID {created.id}")
                self.logger.info(f"Создан пациент ID={created.id}")
            else:
                # Обновление
                updated = self.patient_service.update_patient(dto)
                QMessageBox.information(self, "Успех", f"Пациент ID {updated.id} обновлён")
                self.logger.info(f"Обновлён пациент ID={updated.id}")
            # Возвращаемся к списку пациентов
            self._go_back_to_list()
        except PatientValidationError as e:
            QMessageBox.warning(self, "Ошибка валидации", str(e))
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить: {e}")
            self.logger.exception("Ошибка сохранения пациента")

    @Slot()
    def _delete_patient(self):
        """Удаляет текущего пациента после подтверждения."""
        if not self.current_patient_id:
            return
        reply = QMessageBox.question(
            self, "Подтверждение",
            "Вы уверены, что хотите удалить этого пациента? Все связанные приёмы и фото также будут удалены.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                self.patient_service.delete_patient(self.current_patient_id)
                QMessageBox.information(self, "Успех", "Пациент удалён.")
                self.logger.info(f"Удалён пациент ID={self.current_patient_id}")
                self._go_back_to_list()
            except PatientNotFoundError:
                QMessageBox.warning(self, "Ошибка", "Пациент не найден.")
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Не удалось удалить: {e}")
                self.logger.exception("Ошибка удаления пациента")

    @Slot()
    def _cancel(self):
        """Отмена редактирования."""
        self._go_back_to_list()

    def _go_back_to_list(self):
        """Возврат к списку пациентов."""
        if self.page_manager:
            self.page_manager.go_back()  # предполагаем, что предыдущая страница - список пациентов