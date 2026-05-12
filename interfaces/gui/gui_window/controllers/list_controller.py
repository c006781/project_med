# interfaces/gui/gui_window/controllers/list_controller.py
"""
Абстрактный интерфейс для контроллера динамического списка.
Определяет публичные методы управления списком (добавление, удаление, отмена, сохранение).
"""

from abc import ABC, ABCMeta, abstractmethod
from typing import Set
from PySide6.QtCore import QObject

# Создаём метакласс, совместимый с QObjectMeta и ABCMeta
class QABCMeta(type(QObject), ABCMeta):
    """Метакласс, объединяющий метакласс QObject и ABCMeta."""
    pass

class IDynamicListController(ABC, metaclass=QABCMeta):
    """
    Интерфейс для управления динамическим списком записей.
    Используется для инкапсуляции логики работы с таблицей.
    """

    @abstractmethod
    def add_row(self) -> None:
        """Добавляет новую пустую строку в таблицу (в режиме редактирования)."""
        pass

    @abstractmethod
    def delete_selected_rows(self) -> None:
        """
        Удаляет выбранные строки (с учётом чекбоксов и обычного выделения).
        Для существующих записей помечает их на удаление (deleted_ids),
        для новых – удаляет сразу.
        """
        pass

    @abstractmethod
    def cancel_selected_rows_changes(self) -> None:
        """
        Отменяет изменения для выбранных строк (с учётом чекбоксов и обычного выделения).
        Для существующих записей перезагружает данные из БД, сбрасывает черновики,
        для новых – удаляет строки.
        """
        pass

    @abstractmethod
    def save_all_changes(self) -> bool:
        """
        Сохраняет все изменения (новые, изменённые, удалённые строки) в БД.
        Возвращает True при успешном сохранении, иначе False.
        """
        pass

    @abstractmethod
    def refresh_data(self) -> None:
        """Перезагружает данные списка из источника (БД)."""
        pass

    @abstractmethod
    def get_selected_entity_ids(self) -> Set[int]:
        """
        Возвращает множество ID сущностей, выбранных в таблице.
        Учитывает как обычное выделение (Shift/Ctrl), так и чекбоксы.
        """
        pass

    @abstractmethod
    def is_selection_empty(self) -> bool:
        """Проверяет, есть ли выбранные строки (включая чекбоксы)."""
        pass