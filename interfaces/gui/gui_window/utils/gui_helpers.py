# interfaces/gui/gui_window/utils/gui_helpers.py

"""
Вспомогательные функции для GUI.
"""
from typing import Dict, Any

from app.utils.logger.logger import AppLogger

from PySide6.QtWidgets import QWidget


@AppLogger.get_instance(
    name='system',
).log_execution_time(
    level=AppLogger._parse_log_level('DEBUG')
)
def apply_readonly_to_widgets(
    widgets: Dict[str, QWidget],
    field_configs: Dict[str, Dict[str, Any]]
) -> None:
    """
    Применяет readOnly или отключает виджеты, у которых в конфигурации
    установлен 'editable': False.
    """
    for field_name, widget in widgets.items():
        config = field_configs.get(field_name, {})
        if not config.get('editable', True):
            if hasattr(widget, 'setReadOnly'):
                widget.setReadOnly(True)
            elif hasattr(widget, 'setEnabled'):
                widget.setEnabled(False)