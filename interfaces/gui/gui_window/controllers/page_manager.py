# -*- coding: utf-8 -*-
"""
Менеджер навигации между страницами.
Хранит историю посещений, управляет переключением в QStackedWidget,
испускает сигналы при изменении.
"""
from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtWidgets import QStackedWidget
from typing import Dict, List, Optional


class PageManager(QObject):
    """
    Управляет стеком страниц и историей переходов.
    Сигналы:
        navigation_changed(history, current_page_id) - при изменении навигации.
    """

    navigation_changed = Signal(list, str)  # history, current_page_id
    page_entered = Signal(str, object)      # page_id, extra_data

    def __init__(self, stacked_widget: QStackedWidget, pages: Dict[str, QObject]):
        """
        :param stacked_widget: QStackedWidget, содержащий страницы.
        :param pages: словарь {id: виджет страницы}. Все страницы должны быть добавлены в stacked_widget.
        """
        super().__init__()
        self._stack = stacked_widget
        self._pages = pages
        self._page_to_index = {}   # отображение id -> индекс в стеке
        self._index_to_page = {}   # обратное отображение

        # Заполняем отображения
        for idx in range(self._stack.count()):
            widget = self._stack.widget(idx)
            for page_id, page_widget in pages.items():
                if page_widget == widget:
                    self._page_to_index[page_id] = idx
                    self._index_to_page[idx] = page_id
                    break

        # История посещений (список id страниц)
        self._history: List[str] = []

        # Текущая страница (по умолчанию первая в стеке)
        current_idx = self._stack.currentIndex()
        self._current_page_id = self._index_to_page.get(current_idx, list(pages.keys())[0] if pages else None)
        self._extra_data = None

    def switch_to(
            self, 
            page_id: str, 
            add_to_history: bool = True, 
            extra_data: object = None
        ):
        """
        Переключает на указанную страницу.
        :param page_id: идентификатор страницы.
        :param add_to_history: добавлять ли текущую страницу в историю.
        """
        if page_id not in self._page_to_index:
            raise ValueError(f"Страница с id '{page_id}' не найдена")

        # Если это та же страница, ничего не делаем
        if page_id == self._current_page_id:
            # Если та же страница, просто передаём данные
            if extra_data is not None:
                self._extra_data = extra_data
                self.page_entered.emit(page_id, extra_data)
            return

        # Если нужно сохранить в историю текущую страницу
        if add_to_history and self._current_page_id:
            self._history.append(self._current_page_id)

        # Переключаем
        self._stack.setCurrentIndex(self._page_to_index[page_id])
        self._current_page_id = page_id
        self._extra_data = extra_data

        # Оповещаем об изменении
        self.navigation_changed.emit(self._history.copy(), self._current_page_id)
        self.page_entered.emit(page_id, extra_data)

    def go_back(self):
        """Возврат на предыдущую страницу."""
        if not self._history:
            return

        # Извлекаем последний элемент истории
        prev_page_id = self._history.pop()
        self._stack.setCurrentIndex(self._page_to_index[prev_page_id])
        self._current_page_id = prev_page_id

        self.navigation_changed.emit(self._history.copy(), self._current_page_id)

    @property
    def current_page_id(self) -> Optional[str]:
        """Текущий идентификатор страницы."""
        return self._current_page_id

    @property
    def history(self) -> List[str]:
        """Копия истории посещений."""
        return self._history.copy()

    def clear_history(self):
        """
        Очистить историю (но не переключать страницу).

        Это метод очищает историю посещений, но не изменяет текущую страницу.
        """
        self._history.clear()
        # Оповещаем об изменении
        self.navigation_changed.emit(self._history.copy(), self._current_page_id)

    def get_current_extra_data(self):
        """
        Возвращает дополнительные данные, переданные на текущую страницу.
        :return: объект с дополнительными данными или None, если не было передано.
        """
        return self._extra_data
