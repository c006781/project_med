# interfaces/gui/gui_window/pages/dynamic_edit_page.py
# -*- coding: utf-8 -*-

from app.utils.logger.logger import AppLogger

from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout, QPushButton, QMessageBox, QLineEdit, QSpinBox
from PySide6.QtCore import Slot

from interfaces.gui.gui_window.pages.base_page import BasePage
from interfaces.gui.gui_window.widgets.dynamic_edit_form import DynamicEditForm

class DynamicEditPage(BasePage):
    """
    Универсальная страница редактирования.
    Поддерживает автоматическую подстановку patient_id при создании приёма.
    """

    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="DynamicEditPage.__init__",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def __init__(
        self,
        service,
        dto_class,
        page_title="Редактирование",
        exclude_fields=None,
        field_choices=None,
        field_rename=None,
        parent=None
    ):
        super().__init__(parent)
        self.service = service
        self.dto_class = dto_class
        self.page_title = page_title
        self.exclude_fields = exclude_fields or ['id']
        self.field_choices = field_choices or {}
        self.field_rename = field_rename or {}
        self.logger = AppLogger.get_instance(f"gui.{self.__class__.__name__}")

        self.current_id = None               # ID редактируемой записи
        self.current_patient_id = None        # для приёмов: ID пациента при создании
        self.current_appointment_id = None    # для приёмов: ID приёма (дублирует current_id)

        self._setup_ui()

    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="DynamicEditPage._setup_ui",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _setup_ui(self):
        main_layout = QVBoxLayout(self)

        self.form = DynamicEditForm(
            dto_class=self.dto_class,
            exclude_fields=self.exclude_fields,
            field_choices=self.field_choices,
            field_rename=self.field_rename
        )
        main_layout.addWidget(self.form)

        btn_layout = QHBoxLayout()
        self.save_btn = QPushButton("Сохранить")
        self.save_btn.clicked.connect(self._save)
        btn_layout.addWidget(self.save_btn)

        self.cancel_btn = QPushButton("Отмена")
        self.cancel_btn.clicked.connect(self._cancel)
        btn_layout.addWidget(self.cancel_btn)

        self.delete_btn = QPushButton("Удалить")
        self.delete_btn.clicked.connect(self._delete)
        self.delete_btn.setEnabled(False)
        btn_layout.addWidget(self.delete_btn)

        btn_layout.addStretch()
        main_layout.addLayout(btn_layout)

    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="DynamicEditPage.on_enter",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def on_enter(self, extra_data=None):
        """
        При входе на страницу:
          - если передан 'id' – загружаем существующую запись
          - если передан 'patient_id' и нет 'id' – создаём новый приём для этого пациента
        """
        self.current_id = extra_data.get('id') if extra_data else None
        self.current_patient_id = extra_data.get('patient_id') if extra_data else None
        self.current_appointment_id = self.current_id  # для совместимости

        if self.current_id is not None:
            # Режим редактирования
            self._load_entity(self.current_id)
            self.delete_btn.setEnabled(True)
        else:
            # Режим создания
            self.form.clear()
            self.delete_btn.setEnabled(False)

            # Если передан patient_id и это страница приёма, заполняем поле
            if self.current_patient_id is not None and 'patient_id' in self.form.widgets:
                widget = self.form.widgets['patient_id']
                if isinstance(widget, QSpinBox):
                    widget.setValue(self.current_patient_id)
                elif isinstance(widget, QLineEdit):
                    widget.setText(str(self.current_patient_id))
                # Можно сделать поле только для чтения
                widget.setReadOnly(True)

    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="DynamicEditPage._load_entity",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _load_entity(self, entity_id):
        try:
            dto = self.service.get_by_id(entity_id)
            self.form.load_data(dto)
            self.logger.debug(f"Загружена запись id={entity_id}")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить данные: {e}")
            self.logger.exception("Ошибка загрузки записи")
            self._go_back()

    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="DynamicEditPage._save",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    @Slot()
    def _save(self):
        data = self.form.get_data()
        try:
            dto = self.dto_class(**data)
            if self.current_id is None:
                created = self.service.create(dto)
                QMessageBox.information(self, "Успех", f"Запись создана с ID {created.id}")
                self.logger.info(f"Создана запись ID={created.id}")
            else:
                dto.id = self.current_id
                updated = self.service.update(dto)
                QMessageBox.information(self, "Успех", f"Запись ID {updated.id} обновлена")
                self.logger.info(f"Обновлена запись ID={updated.id}")

            # Помечаем список для обновления
            if self.page_manager and hasattr(self, 'list_page_id'):
                list_page = self.page_manager._pages.get(self.list_page_id)
                if list_page and hasattr(list_page, 'set_needs_refresh'):
                    list_page.set_needs_refresh(True)

            self._go_back()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить: {e}")
            self.logger.exception("Ошибка сохранения")

    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="DynamicEditPage._delete",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    @Slot()
    def _delete(self):
        if not self.current_id:
            return
        reply = QMessageBox.question(
            self, "Подтверждение",
            "Удалить эту запись?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                self.service.delete(self.current_id)
                QMessageBox.information(self, "Успех", "Запись удалена")
                self.logger.info(f"Удалена запись ID={self.current_id}")

                if self.page_manager and hasattr(self, 'list_page_id'):
                    list_page = self.page_manager._pages.get(self.list_page_id)
                    if list_page and hasattr(list_page, 'set_needs_refresh'):
                        list_page.set_needs_refresh(True)

                self._go_back()
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Не удалось удалить: {e}")
                self.logger.exception("Ошибка удаления")

    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="DynamicEditPage._cancel",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    @Slot()
    def _cancel(self):
        self._go_back()

    @AppLogger.get_instance(
            name = 'system'
    ).log_execution_time(
        description="DynamicEditPage._go_back",
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def _go_back(self):
        if self.page_manager:
            self.page_manager.go_back()