# interfaces/gui/gui_window/widgets/base_table_model.py
"""
Абстрактный базовый класс для всех табличных моделей приложения.

Определяет единый интерфейс, который должны реализовывать все модели таблиц
(DynamicTableModel, PaginatedTableModel и т.д.). Это позволяет использовать
их в DynamicListPage без привязки к конкретной реализации.

Поддерживаемые возможности:
    - Доступ к данным (get_item_at_row, get_all_data)
    - Редактирование строк (update_row, add_row, remove_row, clear)
    - Чекбоксы (set_checkbox_column_visible, set_checkbox_state)
    - Цвета строк (set_row_color, clear_row_colors)
    - Пагинация (can_fetch_more, append_page, set_total_count) – для моделей,
      поддерживающих ленивую загрузку.

Все наследники должны реализовать помеченные @abstractmethod методы.
"""

from abc import ABC, abstractmethod
from typing import Any, List, Optional

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Signal, Qt
from PySide6.QtGui import QColor


class BaseTableModel(QAbstractTableModel, ABC): 
    """
    Абстрактный базовый класс для табличных моделей.

    Сигналы:
        row_modified(int): Испускается при изменении данных в строке.
            Передаётся индекс строки в модели.

    Атрибуты (должны быть определены в наследниках):
        _data (List[Any]): Список DTO (загруженные строки).
        _checkbox_column_enabled (bool): Флаг видимости столбца чекбоксов.
        _checkbox_states (Dict[int, bool]): Состояния чекбоксов для строк.
        _row_colors (Dict[int, QColor]): Цвета фона строк.

    Note:
        Все методы, работающие с индексами строк, используют "сырые" индексы
        модели (без учёта прокси). Предполагается, что прокси-модели (если есть)
        занимаются пересчётом индексов самостоятельно.
    """

    row_modified = Signal(int)


    # ----------------------------------------------------------------------
    # Пагинация (для моделей, поддерживающих ленивую загрузку)
    # ----------------------------------------------------------------------

    def can_fetch_more(self) -> bool:
        """
        Определяет, может ли модель загрузить ещё данные.

        Базовая реализация возвращает False (непагинированная модель).
        Наследники, поддерживающие пагинацию, должны переопределить этот метод.

        Returns:
            True, если есть ещё незагруженные страницы, иначе False.
        """

        return False

    def append_page(self, data: List[Any]) -> None:
        """
        Добавляет очередную страницу данных в конец модели.

        Базовая реализация ничего не делает.
        Наследники, поддерживающие пагинацию, должны переопределить метод.

        """

        pass

    def set_total_count(self, total: int) -> None:
        """
        Устанавливает общее количество записей в БД (с учётом фильтров).

        Базовая реализация ничего не делает.
        Наследники, поддерживающие пагинацию, должны переопределить метод.

        """

        pass

    # ----------------------------------------------------------------------
    # Доступ к данным
    # ----------------------------------------------------------------------

    @abstractmethod
    def get_item_at_row(self, row: int) -> Optional[Any]:
        """
        Возвращает DTO для указанной строки.

        Args:
            row: Индекс строки в модели (0-based).

        Returns:
            DTO или None, если строка не существует.
        """
        pass

    @abstractmethod
    def get_all_data(self) -> List[Any]:
        """
        Возвращает копию списка всех загруженных DTO.

        Returns:
            Список DTO (копия, не ссылка на внутренний список).
        """
        pass

    @abstractmethod
    def update_row(self, row: int, new_dto: Any) -> None:
        """
        Заменяет DTO в указанной строке на новый.

        После замены должен испускаться сигнал dataChanged для всей строки.

        Args:
            row: Индекс строки.
            new_dto: Новый DTO.
        """
        pass

    @abstractmethod
    def add_row(self, dto: Any) -> int:
        """
        Добавляет новую строку в конец модели.

        Args:
            dto: DTO новой записи.

        Returns:
            Индекс добавленной строки.
        """
        pass

    @abstractmethod
    def remove_row(self, row: int) -> Optional[Any]:
        """
        Удаляет строку из модели.

        Args:
            row: Индекс удаляемой строки.

        Returns:
            Удалённый DTO или None, если строка не существовала.
        """
        pass

    @abstractmethod
    def clear(self) -> None:
        """
        Полностью очищает модель: удаляет все данные, сбрасывает чекбоксы и цвета.
        """
        pass

    # # ----------------------------------------------------------------------
    # # Чекбоксы - убираем, так как у нас вся информация есть в столбце 
    # # ----------------------------------------------------------------------

    # @abstractmethod
    # def set_checkbox_column_visible(self, visible: bool) -> None:
    #     """
    #     Показывает или скрывает столбец чекбоксов (первый столбец).

    #     Args:
    #         visible: True – показать, False – скрыть.
    #     """
    #     pass

    # @abstractmethod
    # def set_checkbox_state(self, row: int, checked: bool) -> None:
    #     """
    #     Устанавливает состояние чекбокса для строки.

    #     Args:
    #         row: Индекс строки.
    #         checked: True – выбран, False – не выбран.
    #     """
    #     pass

    # ----------------------------------------------------------------------
    # Цвета строк
    # ----------------------------------------------------------------------

    @abstractmethod
    def set_row_color(self, row: int, color: QColor) -> None:
        """
        Устанавливает цвет фона для строки.

        Args:
            row: Индекс строки.
            color: Цвет фона.
        """
        pass

    @abstractmethod
    def clear_row_colors(self) -> None:
        """
        Сбрасывает все установленные цвета строк.
        """
        pass

    # # ----------------------------------------------------------------------
    # # Вспомогательные методы (необязательные для переопределения)
    # # ----------------------------------------------------------------------

    # def has_checkbox_column(self) -> bool:
    #     """
    #     Возвращает, виден ли в данный момент столбец чекбоксов.

    #     Returns:
    #         True, если столбец чекбоксов показан, иначе False.
    #     """
    #     col = self.get_column_by_system_name('__checkbox__')
    #     return col is not None and col.visible