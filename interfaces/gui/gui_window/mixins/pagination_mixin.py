# interfaces/gui/gui_window/mixins/pagination_mixin.py
"""
Миксин для ленивой подгрузки страниц.
"""

# from inspect import _Object
# from threading import Event, Timer
from typing import Dict, List, Union

from app.utils.logger.logger import AppLogger

from interfaces.gui.gui_window.widgets.paginated_table_model import LoadPageThread

from PySide6.QtCore import (
    QObject, QEvent, QTimer
)

class _ResizeFilter(QObject):
    """Внутренний класс-фильтр для отслеживания изменения размера родительского виджета."""
    
    def __init__(self, parent_widget, callback_obj):

        super().__init__(parent_widget)
        self.callback_obj = callback_obj
        self._resize_timer = QTimer()
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(callback_obj._on_resize_timeout)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Resize and obj == self.parent():
            self._resize_timer.start(150)

        return False

class PaginationMixin:
    """
    Миксин для добавления пагинации в страницу списка.

    Требует наличия в классе-наследнике:
        - self.source_model (PaginatedTableModel) – модель с поддержкой append_page, set_total_count
        - self.table_view (QTableView) – таблица для подключения сигналов скролла
        - self.service (BaseService) – сервис с методами get_page_filtered, get_total_count
        - self._current_filters (tree) – текущее дерево фильтров (обновляется извне)
        - self._current_order_by (list) – текущая сортировка
        - self.logger (AppLogger)
        - _on_resize_timeout() – метод, вызываемый при изменении размера родительского виджета
          (реализован в миксине, но может быть переопределён при необходимости)

    Все остальные методы (_maybe_load_more, _load_first_page, _load_next_page, _on_vertical_scroll и т.д.)
    предоставляются миксином и не требуют переопределения.
    """

    def reload_with_order_by(self, order_by: List[str]) -> None:
        """
        Перезагружает данные с новой сортировкой.

        Args:
            order_by: Список полей для сортировки (например, ['-date'] или ['last_name']).
        """
        
        self._cancel_loading()
        self._current_order_by = order_by
        self._load_first_page()

    def setup_pagination(
        self,
        service,
        page_size: int = 50,
        extra_rows: int = 5,
    ) -> None:
        self._setup_pagination(service, page_size, extra_rows)
        
    def _setup_pagination(
        self,
        service,
        page_size: int = 50,
        extra_rows: int = 5,
    ) -> None:
        """
        Инициализирует параметры пагинации.

        Args:
            service: Сервис для загрузки данных (должен иметь методы get_page_filtered и get_total_count).
            page_size: Базовый размер страницы (количество строк, загружаемых за один запрос).
            extra_rows: Количество дополнительных строк, подгружаемых "про запас" (чтобы скролл не дёргался).
        """

        self._pagination_service = service
        self._page_size = page_size
        self._extra_rows = extra_rows

        self._loading_in_progress = False
        self._current_offset = 0
        self._current_filters = None
        self._current_order_by = None

        self._load_thread = None

        # Подключаем сигналы таблицы
        vscroll = self.table_view.verticalScrollBar()
        if vscroll:
            vscroll.valueChanged.connect(self._on_vertical_scroll)

        # Устанавливаем фильтр изменения размера
        parent = self.table_view.parent()
        if parent and not hasattr(self, '_resize_filter'):
            self._resize_filter = _ResizeFilter(parent, self)
            parent.installEventFilter(self._resize_filter)

        if not hasattr(self, 'logger'):
            self.logger = AppLogger.get_instance(
                name='gui.PaginationMixin',
                # share_file_with = 'system',
                enable_file_logging = 'user',
                use_name_in_filename = False, # 'system'
            )
        
        self.logger.debug(
            f"Пагинация инициализирована: page_size={page_size}, extra_rows={extra_rows}"
        )

    # def eventFilter(self, obj, event):
    #     """Фильтр событий для отслеживания изменения размера родительского виджета."""
    #     if event.type() == event.Resize and obj == self.table_view.parent():
    #         self._resize_timer.start(150)
    #     return super().eventFilter(obj, event)

    def _on_resize_timeout(self):
        """Вызывается после изменения размера окна – пересчитывает и при необходимости подгружает."""
        self._maybe_load_more()

    def _on_vertical_scroll(self, value):
        """Обработчик скролла – проверяет, нужно ли подгрузить следующую страницу."""
        self._maybe_load_more()

    def _maybe_load_more(self):
        """Проверяет, нужно ли подгрузить ещё строки, и если да – запускает загрузку."""
        if self._loading_in_progress:
            return
        if not self.source_model.can_fetch_more():
            return

        # Определяем последнюю видимую строку
        last_visible_row = self._get_last_visible_row()
        total_loaded = self.source_model.rowCount()
        if last_visible_row + self._extra_rows >= total_loaded:
            self._load_next_page()

    def _get_last_visible_row(self) -> int:
        """
        Возвращает индекс последней видимой строки в модели (учитывая прокси-модель,
        если она есть, но в пагинированной версии прокси-модели не будет).
        """
        viewport = self.table_view.viewport()
        last_index = self.table_view.indexAt(viewport.rect().bottomLeft())
        if last_index.isValid():
            return last_index.row()
        
        return max(self.source_model.rowCount() - 1, 0)

    def _load_first_page(self) -> None:
        """Сбрасывает модель и загружает первую страницу."""
        if self._loading_in_progress:
            return
        self._loading_in_progress = True
        self.source_model.clear()
        self._current_offset = 0
        self._load_page(offset=0, limit=self._page_size, append=False)

    def _load_next_page(self) -> None:
        """Загружает следующую страницу и добавляет в модель."""
        if self._loading_in_progress:
            return
        offset = len(self.source_model.get_all_data())
        if offset >= self.source_model.total_count():
            return
        self._loading_in_progress = True
        self._load_page(offset=offset, limit=self._page_size, append=True)

    def _load_page(self, offset: int, limit: int, append: bool) -> None:
        """
        Загружает страницу данных через QThread 

        Примечание: Необходимо убедиться, что в классе страницы метод _load_page не вызывается повторно, пока поток активен (флаг _loading_in_progress).
        """
        if self._loading_in_progress:
            return
        if self._load_thread and self._load_thread.isRunning():
            return
        
        self._loading_in_progress = True

        self._load_thread = LoadPageThread(
            self._pagination_service, offset, limit,
            self._current_filters, self._current_order_by
        )
        self._load_thread.finished.connect(
            lambda page, total: self._on_page_loaded(page, total, append)
        )
        self._load_thread.error.connect(self._on_page_error)
        self._load_thread.start()

    def _on_page_loaded(self, page, total, append):
        if not append:
            self.source_model.clear()
        self.source_model.append_page(page)
        if total != self.source_model.total_count():
            self.source_model.set_total_count(total)

        self._loading_in_progress = False
        self._load_thread = None

    def _on_page_error(self, error_msg):
        self.logger.exception(f"Ошибка загрузки страницы: {error_msg}")
        self._loading_in_progress = False
        self._load_thread = None

    def stop_loading(self):
        if self._load_thread and self._load_thread.isRunning():
            self._load_thread.quit()
            self._load_thread.wait(500)
            self._load_thread = None
        self._loading_in_progress = False

    def reload_with_filters(self, filters_tree: Union[Dict, List, None]) -> None:
        """
        Перезагружает данные с новыми фильтрами.
        Должен вызываться извне при изменении фильтров.
        """

        self._cancel_loading()
        self._current_filters = filters_tree
        self._load_first_page()

    def _cancel_loading(self):
        if self._load_thread and self._load_thread.isRunning():
            self._load_thread.quit()
            self._load_thread.wait(500)
            self._load_thread = None
        self._loading_in_progress = False

    def _reload_with_order_by(self, order_by: List[str]) -> None:
        """
        Перезагружает данные с новой сортировкой.
        """
        self._current_order_by = order_by
        self._load_first_page()

    def cancel_loading(self):
        if self._load_thread and self._load_thread.isRunning():
            self._load_thread.terminate()   # или requestInterruption, но лучше использовать флаг
            self._load_thread.wait()
            self._load_thread = None
        self._loading_in_progress = False
