# interfaces/gui/gui_window/pages/patient_list_page.py
"""
Страница списка пациентов с пагинацией, фильтрацией и черновиками.
Наследует PaginatedListPage.
"""

from interfaces.gui.gui_window.pages.paginated_list_page import PaginatedListPage

from app.dependencies import get_patient_service

from app.dto.dto_all import PatientDTO
from app.dto.field_configs import PATIENT_CONFIG

from app.utils.logger.logger import AppLogger


class PatientListPage(PaginatedListPage):
    """
    Страница списка пациентов.

    Использует PaginatedListPage со следующими параметрами:
        - entity_type = "patient"
        - show_controls включает все основные кнопки: режим редактирования,
          выпадающие списки, сохранение, поиск и дополнительную кнопку "Приёмы".
    """

    @AppLogger.get_instance(
        name='PatientListPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def __init__(self, parent=None, shared_registry=None):
        # Сохраняем исходные пункты inline_action_combo для восстановления
        self._original_inline_items = []

        super().__init__(
            service=get_patient_service(),
            dto_class=PatientDTO,
            field_configs=PATIENT_CONFIG,
            page_title="Пациенты",
            add_action_text="Добавить пациента",
            action_button_text="Приёмы",
            parent=parent,
            exclude_columns=None,
            entity_type="patient",
            shared_registry=shared_registry,
            show_controls=[
                'edit_mode_btn',
                'action_combo', #
                'inline_action_combo',
                'save_btn',
                'search',
                'action_btn'
            ]
        )

    @AppLogger.get_instance(
        name='PatientListPage',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def _update_ui_for_edit_mode(self, edit_mode: bool):
        # Вызываем родительский метод (он обновит таблицу, чекбоксы и т.д.)
        super()._update_ui_for_edit_mode(edit_mode)

        # Управляем action_combo
        if hasattr(self, 'action_combo'):
            if edit_mode:
                # В режиме редактирования: показываем комбобокс и заполняем только "Отменить все изменения"
                self.action_combo.setVisible(True)
                # Словарь только с одним действием
                cancel_only_actions = {
                    "item_0": {"text": "▼ Действия", "enabled": False},
                    "cancel_all": {
                        "text": "Отменить все изменения",
                        "func": self._discard_all_changes,
                        "args": (),
                        "kwargs": {}
                    }
                }
                self._rebuild_combo(self.action_combo, cancel_only_actions)
            else:
                # Обычный режим: скрываем комбобокс полностью
                self.action_combo.setVisible(False)

        # inline_action_combo в PatientListPage не используется, скрываем
        if hasattr(self, 'inline_action_combo'):
            self.inline_action_combo.setVisible(False)

    #     self.selection_changed.connect(self._on_selection_changed)  # Подключаем сигнал на выыбранали строка в ТБ

    # def _on_selection_changed_for_button(self, dto):
    #     """Активирует/деактивирует кнопку «Приёмы» при выборе строки."""
    #     if hasattr(self, 'action_btn') and self.action_btn:
    #         # dto может быть None (выделение снято) или PatientDTO
    #         self.action_btn.setEnabled(dto is not None)


    # @AppLogger.get_instance(
    #     name='PatientListPage',
    #     enable_file_logging='system',
    #     use_name_in_filename=False,
    # ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    # def _update_ui_for_edit_mode(self, edit_mode: bool):
    #     """При включении режима отключаем ненужные пункты, оставляя активным только 'Отменить все изменения'."""
    #     super()._update_ui_for_edit_mode(edit_mode)
        
    #     if not hasattr(self, 'inline_action_combo'):
    #         return
        
    #     combo = self.inline_action_combo
    #     model = combo.model()
        
    #     if edit_mode:
    #         # Отключаем пункты 1,2,3 (Добавить строку, Удалить строку, Отменить изменения строки)
    #         for idx in [1, 2, 3]:
    #             if idx < model.rowCount():
    #                 model.item(idx).setEnabled(False)
    #         # Пункт "Отменить все изменения" (обычно индекс 4) оставляем активным
    #         if 4 < model.rowCount():
    #             model.item(4).setEnabled(True)
    #     else:
    #         # Восстанавливаем активность всех пунктов (хотя комбобокс будет скрыт)
    #         for idx in [1, 2, 3, 4]:
    #             if idx < model.rowCount():
    #                 model.item(idx).setEnabled(True)
    # @AppLogger.get_instance(
    #     name='PatientListPage',
    #     enable_file_logging='system',
    #     use_name_in_filename=False,
    # ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    # def _save_inline_items(self):
    #     """Сохраняет текущие пункты inline_action_combo."""
    #     if not hasattr(self, 'inline_action_combo'):
    #         return
    #     combo = self.inline_action_combo
    #     self._original_inline_items = [combo.itemText(i) for i in range(combo.count())]

    # @AppLogger.get_instance(
    #     name='PatientListPage',
    #     enable_file_logging='system',
    #     use_name_in_filename=False,
    # ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    # def _keep_only_cancel_all_inline_items(self):
    #     """Оставляет в inline_action_combo только пункт 'Отменить все изменения'."""
    #     if not hasattr(self, 'inline_action_combo'):
    #         return
    #     combo = self.inline_action_combo
    #     # Находим индекс пункта "Отменить все изменения"
    #     cancel_all_index = -1
    #     for i in range(combo.count()):
    #         if combo.itemText(i) == "Отменить все изменения":
    #             cancel_all_index = i
    #             break
    #     if cancel_all_index == -1:
    #         return
    #     # Удаляем все пункты, кроме индекса 0 (заглушка) и cancel_all_index
    #     for i in range(combo.count() - 1, -1, -1):
    #         if i != 0 and i != cancel_all_index:
    #             combo.removeItem(i)

    # @AppLogger.get_instance(
    #     name='PatientListPage',
    #     enable_file_logging='system',
    #     use_name_in_filename=False,
    # ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    # def _restore_inline_items(self):
    #     """Восстанавливает исходные пункты inline_action_combo."""
    #     if not hasattr(self, 'inline_action_combo') or not self._original_inline_items:
    #         return
    #     combo = self.inline_action_combo
    #     combo.blockSignals(True)
    #     # Очищаем комбобокс
    #     combo.clear()
    #     # Добавляем сохранённые пункты
    #     for text in self._original_inline_items:
    #         combo.addItem(text)
    #     # Устанавливаем заглушку (индекс 0) и делаем её невыбираемой
    #     combo.model().item(0).setEnabled(False)
    #     combo.setCurrentIndex(0)
    #     combo.blockSignals(False)