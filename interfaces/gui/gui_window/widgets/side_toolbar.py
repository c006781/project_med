# interfaces/gui/gui_window/widgets/side_toolbar.py
"""
Виджет вертикальной боковой панели с кнопками управления таблицей.

Используется в PaginatedListPage для добавления дополнительных кнопок:
    - Добавить строку
    - Удалить выбранные строки
    - Отменить изменения выбранных строк
    - Сохранить все изменения
    - Свернуть/развернуть панель

Кнопки адаптируются под режим редактирования (edit_mode) и состояние сохранения.
"""


from app.utils.logger.logger import AppLogger

from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton
from PySide6.QtCore import Qt


class SideToolbar(QWidget):
    """
    Боковая панель с кнопками управления.

    Атрибуты:
        controller: объект, реализующий интерфейс IDynamicListController
                   (должен иметь методы add_row, delete_selected_rows,
                   cancel_selected_rows_changes, save_all_changes).
        add_btn (QPushButton): кнопка добавления строки.
        delete_btn (QPushButton): кнопка удаления.
        cancel_btn (QPushButton): кнопка отмены изменений.
        save_btn (QPushButton): кнопка сохранения.
        toggle_btn (QPushButton): кнопка сворачивания/разворачивания панели.
    """

    @AppLogger.get_instance(
        name='SideToolbar',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def __init__(self, parent, controller):
        """
        Инициализирует боковую панель.

        Args:
            parent (QWidget): Родительский виджет (обычно PaginatedListPage).
            controller: Объект, реализующий IDynamicListController.
        """
        super().__init__(parent)
        self.controller = controller
        self.setFixedWidth(40)  # фиксированная ширина панели

        layout = QVBoxLayout(self)
        layout.setSpacing(5)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setAlignment(Qt.AlignTop)

        # Кнопка добавления строки
        self.add_btn = QPushButton("+")
        self.add_btn.setToolTip("Добавить строку")
        self.add_btn.clicked.connect(controller.add_row)
        layout.addWidget(self.add_btn)

        # Кнопка удаления выбранных строк
        self.delete_btn = QPushButton("✖")
        self.delete_btn.setToolTip("Удалить выбранные строки")
        self.delete_btn.clicked.connect(controller.delete_selected_rows)
        layout.addWidget(self.delete_btn)

        # Кнопка отмены изменений выбранных строк
        self.cancel_btn = QPushButton("↺")
        self.cancel_btn.setToolTip("Отменить изменения выбранных строк")
        self.cancel_btn.clicked.connect(controller.cancel_selected_rows_changes)
        layout.addWidget(self.cancel_btn)

        # Кнопка сохранения всех изменений
        self.save_btn = QPushButton("💾")
        self.save_btn.setToolTip("Сохранить все изменения")
        self.save_btn.clicked.connect(controller.save_all_changes)
        layout.addWidget(self.save_btn)

        # Кнопка сворачивания/разворачивания панели
        self.toggle_btn = QPushButton("◀")
        self.toggle_btn.setToolTip("Скрыть панель")
        self.toggle_btn.clicked.connect(self._toggle_visibility)
        layout.addWidget(self.toggle_btn)

        # Базовый стиль (можно переопределить в qss)
        self.setStyleSheet("""
            QPushButton {
                min-width: 30px;
                min-height: 30px;
                font-size: 16px;
            }
        """)

        # Начальное состояние (режим редактирования выключен)
        self._update_for_edit_mode(False)

    @AppLogger.get_instance(
        name='SideToolbar',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def _toggle_visibility(self):
        """Сворачивает/разворачивает панель и меняет символ на кнопке."""
        self.setVisible(not self.isVisible())
        if self.isVisible():
            self.toggle_btn.setText("◀")
            self.toggle_btn.setToolTip("Скрыть панель")
        else:
            self.toggle_btn.setText("▶")
            self.toggle_btn.setToolTip("Показать панель")

    @AppLogger.get_instance(
        name='SideToolbar',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def _update_for_edit_mode(self, edit_mode):
        """
        Обновляет доступность кнопок в зависимости от режима редактирования.

        Args:
            edit_mode (bool): True – режим редактирования включён,
                              False – выключен.
        """
        self.add_btn.setEnabled(edit_mode)
        self.delete_btn.setEnabled(edit_mode)
        self.cancel_btn.setEnabled(edit_mode)
        # Кнопка сохранения обновляется отдельно через set_save_enabled

    @AppLogger.get_instance(
        name='SideToolbar',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def update_for_edit_mode(self, edit_mode):
        """
        Публичный метод для синхронизации состояния панели с режимом редактирования.

        Args:
            edit_mode (bool): Текущее состояние режима редактирования.
        """
        self._update_for_edit_mode(edit_mode)

    @AppLogger.get_instance(
        name='SideToolbar',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def set_save_enabled(self, enabled):
        """
        Устанавливает доступность кнопки сохранения.

        Args:
            enabled (bool): True – кнопка активна, False – неактивна.
        """
        self.save_btn.setEnabled(enabled)