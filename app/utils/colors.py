# app/utils/colors.py
"""
Цветовые константы для отображения статусов строк в таблицах.
"""

# from alembic.environment import Optional
from typing import Optional
from app.utils.logger.logger import AppLogger


from PySide6.QtGui import QColor

class RowStatusColor:
    """Цвета строк в зависимости от статуса сущности."""

    # Новая строка (ещё не сохранена в БД, временный ID)
    NEW = QColor(200, 255, 200)      # светло-зелёный

    # Изменённая строка (есть несохранённые изменения)
    MODIFIED = QColor(255, 255, 180) # светло-жёлтый

    # Удалённая строка (помечена на удаление)
    DELETED = QColor(255, 200, 200)  # светло-красный

    # Нормальная строка (без изменений)
    NORMAL = QColor(255, 255, 255)   # белый


# # Для обратной совместимости можно добавить синонимы:
# NEW_ROW = RowStatusColor.NEW
# MODIFIED_ROW = RowStatusColor.MODIFIED
# DELETED_ROW = RowStatusColor.DELETED
# NORMAL_ROW = RowStatusColor.NORMAL


@AppLogger.get_instance(
    name='colors.py',
    enable_file_logging='system',
    use_name_in_filename=False,
).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
def get_color_for_entity_status(
    status: Optional[str], 
    is_new: bool = False, 
    is_deleted: bool = False
) -> QColor:
    if is_deleted:
        return RowStatusColor.DELETED # красный
    
    if is_new:
        return RowStatusColor.NEW # светло-зелёный
    
    if status in ('own', 'child', 'both'):
        return RowStatusColor.MODIFIED # жёлтый
    
    return RowStatusColor.NORMAL  # белый