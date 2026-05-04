# interfaces/gui/gui_window/controllers/page_manager.py

"""
Менеджер навигации между страницами.
Хранит историю посещений (с заголовками), управляет переключением в QStackedWidget,
испускает сигналы при изменении.
"""

from typing import (
    Dict, List, Optional, Tuple
)

from app.utils.logger.logger import AppLogger

from PySide6.QtCore import (
    QObject, 
    Signal, 
    # Slot
)
from PySide6.QtWidgets import QStackedWidget


class PageManager(QObject):
    """
    Управляет стеком страниц и историей переходов в QStackedWidget.

    Позволяет переключаться между страницами, сохранять историю, возвращаться назад.
    Поддерживает передачу дополнительных данных (`extra_data`) при переходе.

    Сигналы:
        navigation_changed (list, str): Испускается при изменении навигации.
            Передаёт копию истории (список кортежей (page_id, title)) и текущий page_id.
        page_entered (str, object): Испускается при входе на страницу.
            Передаёт page_id и extra_data.

    Атрибуты:
        _stack (QStackedWidget): Стек виджетов, содержащий страницы.
        _pages (Dict[str, QWidget]): Словарь {id: виджет страницы}.
        _page_to_index (Dict[str, int]): Отображение page_id → индекс в стеке.
        _index_to_page (Dict[int, str]): Обратное отображение.
        _history (List[Tuple[str, str]]): История посещений (id, title).
        _current_page_id (str): Текущий идентификатор страницы.
        _extra_data (Any): Дополнительные данные, переданные на текущую страницу.

    Пример:
        >>> stacked = QStackedWidget()
        >>> pages = {'main': MainPage(), 'settings': SettingsPage()}
        >>> for page in pages.values(): stacked.addWidget(page)
        >>> manager = PageManager(stacked, pages)
        >>> manager.switch_to('settings', extra_data={'user': 'admin'})
        >>> manager.navigation_changed.connect(update_breadcrumbs)
    """

    navigation_changed = Signal(list, str)  # history: List[Tuple[str,str]], current_page_id: str
    page_entered = Signal(str, object)      # page_id, extra_data

    @AppLogger.get_instance(
        name = 'PageManager',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def __init__(
        self, 
        stacked_widget: QStackedWidget, 
        pages: Dict[str, QObject]
    ):
        """
        Инициализирует страницу менеджера.
        Создаёт отображение id -> индекс в стеке и обратное отображение.
        Инициализирует историю посещений (список кортежей (id, title)) и текущую страницу (по умолчанию первая в стеке).

        Параметры:
            stacked_widget (QStackedWidget): Стек, в который уже добавлены страницы.
            pages (Dict[str, QWidget]): Словарь {id: виджет}. Все виджеты должны быть
                добавлены в `stacked_widget` (порядок не важен).

        Примечание:
            Автоматически определяет текущую страницу по индексу стека и устанавливает
            её как `_current_page_id`.
        """

        # Вызов parent class
        super().__init__()

        self.logger = AppLogger.get_instance(
            name = 'gui.PageManager',
            # share_file_with = 'user',
            enable_file_logging = 'user',
            use_name_in_filename = False, # 'user',
        )

        # QStackedWidget, содержащий страницы
        self._stack = stacked_widget

        # Словарь {id: виджет страницы}
        self._pages = pages

        # Словарь {id: индекс в стеке}
        self._page_to_index = {} # отображение id -> индекс в стеке

        # Словарь {индекс в стеке: id}
        self._index_to_page = {}# обратное отображение

        # Заполняем отображения
        for idx in range(self._stack.count()):
            widget = self._stack.widget(idx)
            for page_id, page_widget in pages.items():
                if page_widget == widget:
                    self._page_to_index[page_id] = idx
                    self._index_to_page[idx] = page_id
                    break

        # История посещений (список кортежей (id, title))
        self._history: List[Tuple[str, str]] = []

        # Текущая страница (по умолчанию первая в стеке)
        current_idx = self._stack.currentIndex()
        self._current_page_id = self._index_to_page.get(
            current_idx, 
            list(pages.keys())[0] if pages else None
        )
        self._current_page_title = self._get_page_title(self._current_page_id)
        self._extra_data = None
        self.navigation_changed.emit(self._history.copy(), self._current_page_id)

    @AppLogger.get_instance(
        name = 'PageManager',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _get_page_title(self, page_id: str) -> str:
        """
        Метод для получения заголовка страницы по ее идентификатору.
        
        Если страница не существует, возвращает идентификатор страницы.
        Если страница существует, но не имеет метода get_page_title, возвращает идентификатор страницы.
        Если страница имеет метод get_page_title, возвращает результат вызова этого метода.
        """
        if page_id is None:
            return "Главная"
        
        page = self._pages.get(page_id)
        if page is None:
            return page_id
        
        # Если у страницы есть метод get_page_title, используем его
        if hasattr(page, 'get_page_title'):
            return page.get_page_title()
        
        # fallback
        return page_id

    @AppLogger.get_instance(
        name = 'PageManager',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def switch_to(
        self,
        page_id: str,
        add_to_history: bool = True,
        extra_data: object = None
    ):
        """
        Переключает на указанную страницу.

        Параметры:
            page_id (str): Идентификатор страницы (должен существовать в `_pages`).
            add_to_history (bool): Добавлять ли текущую страницу в историю (по умолч. True).
            extra_data (object, optional): Дополнительные данные, которые будут переданы
                в метод `on_enter` целевой страницы.

        Исключения:
            ValueError: Если страница с `page_id` не найдена.
        """

        self.logger.debug(f'page_id not in self._page_to_index : {page_id not in self._page_to_index}')
        if page_id not in self._page_to_index:
            err_ = f"Страница с id '{page_id}' не найдена"
            self.logger.exception(err_)
            raise ValueError(err_)

        # Если это та же страница, просто передаём данные
        self.logger.debug(f'page_id == self._current_page_id : {page_id == self._current_page_id}')
        if page_id == self._current_page_id:
            self.logger.debug(f'extra_data is not None : {extra_data is not None}')
            # if extra_data is not None:
            # Всегда испускаем сигнал, чтобы страница могла обновиться
            self._extra_data = extra_data
            self.page_entered.emit(page_id, extra_data)
            return
            
        # Вызываем on_leave у текущей страницы перед уходом
        current_page = self._pages.get(self._current_page_id)
        if current_page and hasattr(current_page, 'on_leave'):
            current_page.on_leave()

        # Если нужно сохранить в историю текущую страницу
        self.logger.debug(f'add_to_history and self._current_page_id : {add_to_history and self._current_page_id}')
        if add_to_history and self._current_page_id:
            self._history.append((self._current_page_id, self._current_page_title))

        # Переключаем
        self._stack.setCurrentIndex(self._page_to_index[page_id])
        self._current_page_id = page_id
        self._current_page_title = self._get_page_title(page_id)
        self._extra_data = extra_data

        # Оповещаем об изменении
        self.navigation_changed.emit(self._history.copy(), self._current_page_id)
        self.page_entered.emit(page_id, extra_data)

    @AppLogger.get_instance(
        name = 'PageManager',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def go_back(self):
        # """Возврат на предыдущую страницу."""
        """
        Возврат на предыдущую страницу.
        
        Если история пустая, то ничего не происходит.
        
        Если история не пустая, то извлекаем последний элемент истории,
        переключаем на соответствующую страницу и оповещаем об изменении навигации.

        Вызывает `on_leave` у текущей страницы перед переходом.
        """

        if not self._history:
            return

        # Вызываем on_leave у текущей страницы перед уходом
        current_page = self._pages.get(self._current_page_id)
        if current_page and hasattr(current_page, 'on_leave'):
            current_page.on_leave()

        # Извлекаем последний элемент истории
        prev_page_id, prev_page_title = self._history.pop()
        self._stack.setCurrentIndex(self._page_to_index[prev_page_id])
        self._current_page_id = prev_page_id
        self._current_page_title = prev_page_title

        # Оповещаем об изменении навигации
        self.navigation_changed.emit(self._history.copy(), self._current_page_id)
        self.page_entered.emit(prev_page_id, None)

    # @AppLogger.get_instance(
    #     name = 'PageManager',
    #     enable_file_logging = 'system',
    #    use_name_in_filename = False, # 'system',
    # ).log_execution_time(
    #     level = AppLogger._parse_log_level(
    #         # 'INFO'
    #         'DEBUG'
    #     )
    # )
    @property
    def current_page_id(self) -> Optional[str]:
        # """Текущий идентификатор страницы."""
        """
        Возвращает текущий идентификатор страницы.
        
        Если страница не была установлен, то возвращает None.
        """

        return self._current_page_id

    # @AppLogger.get_instance(
    #     name = 'PageManager',
    #     enable_file_logging = 'system',
    #    use_name_in_filename = False, # 'system',
    # ).log_execution_time(
    #     level = AppLogger._parse_log_level(
    #         # 'INFO'
    #         'DEBUG'
    #     )
    # )
    @property
    def history(self) -> List[Tuple[str, str]]:
        # """Копия истории посещений (список кортежей (id, title))."""
        """
        Возвращает копию истории посещений (список кортежей (id, title)).
        
        История хранит список кортежей (id, title), где id - идентификатор страницы,
        а title - заголовок страницы.

        Возвращает:
            List[Tuple[str, str]]: Список кортежей (page_id, title).
        """

        return self._history.copy()

    @AppLogger.get_instance(
        name = 'PageManager',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def clear_history(self):
        """
        Очистить историю (но не переключать страницу).
        История навигации будет очищена, а сигнал navigation_changed будет отправлен с пустым списком истории.
        """
        self._history.clear()
        # Оповещаем об изменении
        self.navigation_changed.emit(self._history.copy(), self._current_page_id)

    @AppLogger.get_instance(
        name = 'PageManager',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def get_current_extra_data(self):
        """
        Возвращает дополнительные данные, переданные на текущую страницу.

        Возвращает:
            object: Данные, переданные при последнем вызове `switch_to`, или None.
        """

        return self._extra_data
