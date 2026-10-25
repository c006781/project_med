# app/utils/colors.py
"""
Цветовые константы для отображения статусов строк в таблицах.

Цвета — общие объекты ``QColor`` уровня класса: модели таблиц хранят ссылки на них, поэтому
менять их на месте (``setAlpha``, ``setRgb`` …) нельзя — изменится цвет во всех таблицах;
для оттенка — ``QColor(RowStatusColor.NEW)`` или ``.darker()`` / ``.lighter()`` (новый объект).
``QColor`` создаётся без приложения Qt — импорт модуля его не требует.

Пример:
    >>> get_color_for_entity_status('own') is RowStatusColor.MODIFIED
    True
    >>> get_color_for_entity_status(None, is_new=True).name()
    '#c8ffc8'
"""

# from alembic.environment import Optional
from typing import Optional
from app.utils.logger.logger import AppLogger


from PySide6.QtGui import QColor

class RowStatusColor:
    """
    Цвета строк в зависимости от статуса сущности.

    Общие объекты — не менять на месте (см. описание модуля).

    Пример:
        >>> model.set_row_color(row, RowStatusColor.DELETED)
        >>> RowStatusColor.NORMAL.name()
        '#ffffff'
    """

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
# def get_color_for_entity_status(
#     status: Optional[str],
#     is_new: bool = False,
#     is_deleted: bool = False
# ) -> QColor:
# ↑ до 2026-10-25 (CL1): сигнатура без комментариев к параметрам, функция без докстринга
#   (формат skill п. 7, правило проекта — документировать всё).
def get_color_for_entity_status(
    status     : Optional[str],  # статус черновика: 'own', 'child', 'both' или None
    is_new     : bool = False,   # новая строка (ещё не в БД)
    is_deleted : bool = False,   # помечена на удаление
) -> QColor:
    """
    Цвет фона строки по состоянию сущности.

    Приоритет: удалённая (красный) → новая (зелёный) → изменённая (жёлтый: статус
    ``'own'`` — свои несохранённые правки, ``'child'`` — правки дочерних записей,
    ``'both'`` — и те и другие) → обычная (белый; любой другой статус, в том числе ``None``).

    Args:
        status: Статус несохранённых изменений (черновика) строки.
        is_new: Строка новая (временный id, черновик ``__new__``).
        is_deleted: Строка помечена на удаление (черновик ``__deleted__``).

    Returns:
        QColor: Один из общих цветов ``RowStatusColor`` (не менять на месте).

    Пример:
        >>> get_color_for_entity_status('child') is RowStatusColor.MODIFIED
        True
        >>> get_color_for_entity_status('own', is_new=True, is_deleted=True) is RowStatusColor.DELETED
        True
        >>> get_color_for_entity_status(None) is RowStatusColor.NORMAL
        True
    """
    if is_deleted:
        return RowStatusColor.DELETED # красный
    
    if is_new:
        return RowStatusColor.NEW # светло-зелёный
    
    if status in ('own', 'child', 'both'):
        return RowStatusColor.MODIFIED # жёлтый
    
    return RowStatusColor.NORMAL  # белый