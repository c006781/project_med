# interfaces/gui/gui_window/pages/dynamic_edit_page.py
# -*- coding: utf-8 -*-

from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout, QPushButton, QMessageBox
from PySide6.QtCore import Slot

from interfaces.gui.gui_window.pages.base_page import BasePage
from interfaces.gui.gui_window.widgets.dynamic_edit_form import DynamicEditForm
from app.utils.logger.logger import AppLogger


class DynamicEditPage(BasePage):
    """
    Универсальная страница редактирования.
    Использует service.create и service.update (добавленные в сервисы).
    """

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

        self.current_id = None
        self._setup_ui()

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

    def on_enter(self, extra_data=None):
        self.current_id = extra_data.get('id') if extra_data else None
        if self.current_appointment_id is None and self.current_patient_id:
            # Режим создания – предзаполняем поле пациента
            # Если форма содержит поле patient_id, заполняем его
            self.patient_id_edit.setText(str(self.current_patient_id))
            # Можно сделать поле только для чтения
            self.patient_id_edit.setReadOnly(True)
        # Далее загрузка существующего приёма или очистка
        else:
            self.form.clear()
            self.delete_btn.setEnabled(False)

    def _load_entity(self, entity_id):
        try:
            dto = self.service.get_by_id(entity_id)
            self.form.load_data(dto)
            self.logger.debug(f"Загружена запись id={entity_id}")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить данные: {e}")
            self.logger.exception("Ошибка загрузки записи")
            self._go_back()

    @Slot()
    def _save(self):
        data = self.form.get_data()
        # try:
        #     dto = self.dto_class(**data)
        #     if self.current_id is None:
        #         # Создание
        #         created = self.service.create(dto)  # используем универсальный create
        #         QMessageBox.information(self, "Успех", f"Запись создана с ID {created.id}")
        #         self.logger.info(f"Создана запись ID={created.id}")
        #     else:
        #         # Обновление
        #         dto.id = self.current_id
        #         updated = self.service.update(dto)  # используем универсальный update
        #         QMessageBox.information(self, "Успех", f"Запись ID {updated.id} обновлена")
        #         self.logger.info(f"Обновлена запись ID={updated.id}")
        # except Exception as e:
        try:
            dto = self.dto_class(**data)
            if self.current_id is None:
                created = self.service.create(dto)
                QMessageBox.information(self, "Успех", f"Запись создана с ID {created.id}")
            else:
                updated = self.service.update(dto)
                QMessageBox.information(self, "Успех", f"Запись ID {updated.id} обновлена")
            
            # # Находим страницу списка в page_manager и помечаем, что нужно обновить
            # if self.page_manager:
            #     list_page_id = self._get_list_page_id()  # нужно определить для каждого типа
            #     list_page = self.page_manager._pages.get(list_page_id)
            #     if list_page and hasattr(list_page, 'set_needs_refresh'):
            #         list_page.set_needs_refresh(True)
            # self._go_back()
                    # Помечаем список для обновления
            #  Находим страницу списка в page_manager и помечаем, что нужно обновить
            if self.page_manager and hasattr(self, 'list_page_id'):
                list_page = self.page_manager._pages.get(self.list_page_id)
                if list_page and hasattr(list_page, 'set_needs_refresh'):
                    list_page.set_needs_refresh(True)
            
            self._go_back()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить: {e}")
            self.logger.exception("Ошибка сохранения")
            return
        # self._go_back()

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
                self.service.delete(self.current_id)  # используем универсальный delete (из BaseService)
                QMessageBox.information(self, "Успех", "Запись удалена")
                self.logger.info(f"Удалена запись ID={self.current_id}")

                # Аналогично помечаем список для обновления
                if self.page_manager and hasattr(self, 'list_page_id'):
                    list_page = self.page_manager._pages.get(self.list_page_id)
                    if list_page and hasattr(list_page, 'set_needs_refresh'):
                        list_page.set_needs_refresh(True)
            
                self._go_back()

            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Не удалось удалить: {e}")
                self.logger.exception("Ошибка удаления")
                return
            # self._go_back()

            

    @Slot()
    def _cancel(self):
        self._go_back()

    def _go_back(self):
        if self.page_manager:
            self.page_manager.go_back()