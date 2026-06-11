# interfaces/gui/gui_window/mixins/pagination_mixin.py
"""
Миксин для ленивой подгрузки страниц (виртуальная прокрутка).

Обеспечивает:
    - Загрузку данных порциями через `LoadPageThread`.
    - Автоматическую подгрузку следующей страницы при прокрутке или изменении размера окна.
    - Настройку размера страницы (`page_size`) и количества «запасных» строк (`extra_rows`).
    - Перезагрузку данных с новыми фильтрами/сортировкой через `reload_with_filters` и `reload_with_order_by`.

Требует наличия в классе-наследнике:
    - `self.source_model` – модель с методами `append_page`, `set_total_count`, `can_fetch_more`.
    - `self.table_view` – таблица для получения видимых строк.
    - `self.service` – сервис с методом `get_page_filtered`.
    - `self._current_filters` и `self._current_order_by` (устанавливаются извне).
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
    """
    Внутренний фильтр событий для отслеживания изменения размера родительского виджета.
    Используется для того, чтобы при ресайзе окна перепроверить необходимость подгрузки данных.
    """
    
    @AppLogger.get_instance(
        name='_ResizeFilter',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def __init__(self, parent_widget, callback_obj):

        super().__init__(parent_widget)
        self.callback_obj = callback_obj
        self._resize_timer = QTimer()
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(callback_obj._on_resize_timeout)

    # @AppLogger.get_instance(
    #     name='_ResizeFilter',
    #     # share_file_with = 'system',
    #     enable_file_logging = 'system',
    #     use_name_in_filename = False, # 'system'
    # ).log_execution_time(
    #     level=AppLogger._parse_log_level('DEBUG')
    # )
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Resize and obj == self.parent():
            self._resize_timer.start(150)

        return False

class PaginationMixin:
    """
    Миксин для ленивой подгрузки страниц (виртуальная прокрутка).

    **Назначение:**
        Позволяет таблице загружать данные порциями (страницами) по мере прокрутки.
        Работает совместно с сервисом, имеющим метод `get_page_filtered` (из BaseService).

    **Требования к классу-наследнику:**
        - self.table_view (QTableView) – таблица, для которой настраивается пагинация.
        - self.source_model (PaginatedTableModel) – модель, поддерживающая `append_page` и `set_total_count`.
        - self.logger (AppLogger) – для логирования.

    **Параметры пагинации (устанавливаются через setup_pagination):**
        - page_size (int): количество записей за один запрос (по умолчанию 50).
        - extra_rows (int): количество "запасных" строк, после которого запускается подгрузка следующей страницы (по умолчанию 5).

    **Основные методы (должны вызываться извне):**
        - setup_pagination(service, page_size, extra_rows) – инициализация.
        - reload_with_filters(filters_tree) – перезагрузка с новыми фильтрами.
        - reload_with_order_by(order_by) – перезагрузка с новой сортировкой.
        - stop_loading() – отмена текущей загрузки (например, при уходе со страницы).

    **Внутренние методы (не предназначены для вызова извне):**
        - _load_first_page() – загружает первую страницу.
        - _load_next_page() – загружает следующую.
        - _maybe_load_more() – проверяет, нужно ли подгрузить ещё строк (вызывается при скролле и ресайзе).
        - _on_page_loaded(page, total, append) – обрабатывает загруженные данные.
        - _on_page_error(error_msg) – обработчик ошибки загрузки.

    **Пример использования в PaginatedListPage:**
        >>> class MyListPage(PaginationMixin, ...):
        ...     def __init__(self, service, ...):
        ...         super().__init__(...)
        ...         self.setup_pagination(service, page_size=50, extra_rows=5)
        ...         self.reload_with_filters(None)
    """

    @property
    def logger(self) -> AppLogger:
        try:
            return self._logger
        except:
            self._logger = AppLogger.get_instance(
                name='gui.PaginationMixin',
                # share_file_with = 'system',
                enable_file_logging = 'user',
                use_name_in_filename = False, # 'system'
            )
        return self._logger

    @logger.setter
    def logger(self, value):
        self._logger = value

    @AppLogger.get_instance(
        name='PaginationMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def reload_with_order_by(self, order_by: List[str]) -> None:
        """
        
        Перезагружает данные с новой сортировкой (сбрасывает пагинацию).

        Args:
            order_by: Список полей для сортировки.
                Пример: ['-date', 'last_name'] (минус = убывание).

        Note:
            - Отменяет текущую загрузку.
            - Очищает модель и загружает первую страницу с новым order_by.
        """

        self._cancel_loading()
        self._current_order_by = order_by
        self._load_first_page()

    @AppLogger.get_instance(
        name='PaginationMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def setup_pagination(
        self,
        service,
        page_size: int = 50,
        extra_rows: int = 5,
    ) -> None:
        """
        Инициализирует параметры пагинации и подключает сигналы.

        Args:
            service: Экземпляр сервиса (должен иметь метод get_page_filtered).
            page_size: Количество записей, загружаемых за один раз.
            extra_rows: При достижении видимой строки = (общее_загруженное - extra_rows) запускается подгрузка следующей страницы.

        Note:
            - Вызывает очистку модели и загрузку первой страницы.
            - Подключает сигнал скролла таблицы к `_maybe_load_more`.
            - Устанавливает фильтр изменения размера родительского виджета.
        """
        self._setup_pagination(service, page_size, extra_rows)
      
    @AppLogger.get_instance(
        name='PaginationMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )  
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
            
        Note:
            - Вызывает очистку модели и загрузку первой страницы.
            - Подключает сигнал скролла таблицы к `_maybe_load_more`.
            - Устанавливает фильтр изменения размера родительского виджета.
        """

        self._pagination_service = service
        self._page_size = page_size
        self._extra_rows = extra_rows

        self._current_offset = 0
        self._current_filters = None
        self._current_order_by = None
        
        self._load_thread_clear()

        # Подключаем сигналы таблицы
        vscroll = self.table_view.verticalScrollBar()

        self.logger.debug(
            f"vscroll is None = {vscroll is None} "
        )
        if vscroll:
            vscroll.valueChanged.connect(self._on_vertical_scroll)

        # Устанавливаем фильтр изменения размера
        parent = self.table_view.parent()
        self.logger.debug(
            f"parent is None = {parent is None} "
            f"not hasattr(self, '_resize_filter') = {not hasattr(self, '_resize_filter')} "
        )
        if parent and not hasattr(self, '_resize_filter'):
            self._resize_filter = _ResizeFilter(parent, self)
            parent.installEventFilter(self._resize_filter)

        # if not hasattr(self, 'logger'):
        #     self.logger = AppLogger.get_instance(
        #         name='gui.PaginationMixin',
        #         # share_file_with = 'system',
        #         enable_file_logging = 'user',
        #         use_name_in_filename = False, # 'system'
        #     )
        
        self.logger.debug(
            f"Пагинация инициализирована: page_size={page_size}, extra_rows={extra_rows}"
        )

    # def eventFilter(self, obj, event):
    #     """Фильтр событий для отслеживания изменения размера родительского виджета."""
    #     if event.type() == event.Resize and obj == self.table_view.parent():
    #         self._resize_timer.start(150)
    #     return super().eventFilter(obj, event)

    @AppLogger.get_instance(
        name='PaginationMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _on_resize_timeout(self):
        """Вызывается после изменения размера окна – пересчитывает и при необходимости подгружает."""
        self._maybe_load_more()

    @AppLogger.get_instance(
        name='PaginationMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _on_vertical_scroll(self, value):
        """Обработчик скролла – проверяет, нужно ли подгрузить следующую страницу."""
        self._maybe_load_more()

    @AppLogger.get_instance(
        name='PaginationMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _maybe_load_more(self):
        """"
        Проверяет, нужно ли подгрузить следующую страницу (вызывается при скролле и ресайзе).
        если да – запускает загрузку.
        """

        self.logger.debug(
            f"self._loading_in_progress = {self._loading_in_progress} "
        )
        if self._loading_in_progress:
            return
        tt = not self.source_model.can_fetch_more()
        self.logger.debug(
            f"not self.source_model.can_fetch_more() = {tt} "
        )
        if tt:
            return

        # Определяем последнюю видимую строку
        last_visible_row = self._get_last_visible_row()
        total_loaded = self.source_model.rowCount()

        self.logger.debug(
            f"last_visible_row = {last_visible_row} "
            f"last_visible_row + self._extra_rows = {last_visible_row + self._extra_rows} "
            f"total_loaded = {total_loaded} "
        )
        if last_visible_row + self._extra_rows >= total_loaded:
            self._load_next_page()

    @AppLogger.get_instance(
        name='PaginationMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _get_last_visible_row(self) -> int:
        """
        Возвращает индекс последней видимой строки в модели (учитывая прокси-модель,
        если она есть, но в пагинированной версии прокси-модели не будет).
        """
        viewport = self.table_view.viewport()
        last_index = self.table_view.indexAt(viewport.rect().bottomLeft())
        self.logger.debug(
            f"last_index.isValid() = {last_index.isValid()} "
        )
        if last_index.isValid():
            return last_index.row()
        
        return max(self.source_model.rowCount() - 1, 0)

    @AppLogger.get_instance(
        name='PaginationMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _load_first_page(self) -> None:
        """Сбрасывает модель и загружает первую страницу."""
        self.logger.debug(
            f"self._loading_in_progress = {self._loading_in_progress} "
        )
        if self._loading_in_progress:
            return
        # self._loading_in_progress = True
        self.source_model.clear()
        self._current_offset = 0
        self._load_page(offset=0, limit=self._page_size, append=False)

    @AppLogger.get_instance(
        name='PaginationMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _load_next_page(self) -> None:
        """Загружает следующую страницу и добавляет в модель."""
        self.logger.debug(
            f"self._loading_in_progress = {self._loading_in_progress} "
        )
        if self._loading_in_progress:
            return

        offset = len(self.source_model.get_all_data())
        tt = self.source_model.total_count()
        self.logger.debug(
            f"offset = {offset} "
            f"self.source_model.total_count() = {tt} "
        )
        if offset >= tt:
            return

        # self._loading_in_progress = True
        self._load_page(offset=offset, limit=self._page_size, append=True)

    @AppLogger.get_instance(
        name='PaginationMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _load_page(self, offset: int, limit: int, append: bool) -> None:
        """
        Загружает страницу данных в отдельном потоке QThread (LoadPageThread).

        Примечание: Необходимо убедиться, что в классе страницы метод _load_page не вызывается повторно, пока поток активен (флаг _loading_in_progress).
        
        Args:
            offset: Смещение от начала (сколько записей пропустить).
            limit: Количество записей для загрузки.
            append: Если True, добавляет данные в конец модели; если False, сначала очищает модель.

        Note:
            Устанавливает флаг _loading_in_progress = True до завершения потока.
        """

        self.logger.debug(
            f"self._loading_in_progress = {self._loading_in_progress} "
        )
        if self._loading_in_progress:
            self.logger.debug(f"self._loading_in_progress = {self._loading_in_progress}")
            return

        tt = self._thec_load_thread_isRunning()
        self.logger.debug(
            f"self._thec_load_thread_isRunning = {tt} "
        )
        if tt:
            return
        
        self._loading_in_progress = True

        self.logger.debug(f"Creating load thread for offset={offset}, limit={limit}")
        self._load_thread = LoadPageThread(
            self._pagination_service, offset, limit,
            self._current_filters, self._current_order_by
        )
        self._load_thread.finished.connect(
            lambda page, total: self._on_page_loaded(page, total, append)
        )
        self._load_thread.error.connect(self._on_page_error)
        self.logger.debug("Starting load thread")
        self._load_thread.start()
        self.logger.debug("Load thread started")

    @AppLogger.get_instance(
        name='PaginationMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _on_page_loaded(self, page, total, append):
        """
        Обработчик успешной загрузки страницы.

        Args:
            page: Список DTO, полученных от сервиса.
            total: Общее количество записей в БД (с учётом фильтров).
            append: Если True, данные добавляются к уже загруженным; иначе модель сначала очищается.

        Note:
            - Вызывает source_model.append_page(page) и source_model.set_total_count(total).
            - Сбрасывает флаг _loading_in_progress.
            - **Если append == False (загружена первая страница), через QTimer.singleShot(0, ...)**
            **вызывает _maybe_load_more(), чтобы при необходимости догрузить следующую страницу**
            **сразу после применения фильтра.** Это обеспечивает заполнение видимой области таблицы
            без необходимости скролла.ниц.
        """
        self.logger.debug(f"Страница загружена: append={append}, rows={len(page)}, total={total}")

        self.logger.debug(
            f"not append = {not append} "
        )
        if not append:
            self.source_model.clear()

        self.source_model.append_page(page)

        tt = self.source_model.total_count()
        self.logger.debug(
            f"total = {total} "
            f"self.source_model.total_count() = {tt} "
        )
        if total != tt:
            self.source_model.set_total_count(total)

        self._load_thread_clear()

        # После загрузки первой страницы проверяем, нужно ли догрузить ещё
        self.logger.debug(
            f"not append = {not append} "
        )
        if not append:
            # from PySide6.QtCore import QTimer
            QTimer.singleShot(0, self._maybe_load_more)

    @AppLogger.get_instance(
        name='PaginationMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _load_thread_clear(self):
        self._loading_in_progress = False
        self._load_thread = None

    @AppLogger.get_instance(
        name='PaginationMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _on_page_error(self, error_msg):
        self.logger.exception(f"Ошибка загрузки страницы: {error_msg}")
        self._load_thread_clear()

    @AppLogger.get_instance(
        name='PaginationMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def stop_loading(self):
        """
        Останавливает текущую загрузку (если поток активен) и сбрасывает флаг `_loading_in_progress`.

        Используется при уходе со страницы или перед перезагрузкой с новыми параметрами.
        """
        self._cancel_loading()
        # if self._load_thread and self._load_thread.isRunning():
        #     self._load_thread.quit()
        #     self._load_thread.wait(500)
        #     self._load_thread = None
        # self._loading_in_progress = False

    @AppLogger.get_instance(
        name='PaginationMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def reload_with_filters(self, filters_tree: Union[Dict, List, None]) -> None:
        """
        Перезагружает данные с новыми фильтрами (сбрасывает пагинацию).
        Должен вызываться извне при изменении фильтров.

        Args:
            filters_tree: Дерево фильтров в формате, который понимает сервис.
                Например: {'and': [{'column': 'last_name', 'operator': 'like', 'value': 'Петров'}]}
                или список старых фильтров (для обратной совместимости).

        Note:
            - Отменяет текущую загрузку (если есть).
            - Очищает модель и загружает первую страницу.
        """

        self._cancel_loading()
        self._current_filters = filters_tree
        self._load_first_page()

    @AppLogger.get_instance(
        name='PaginationMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _cancel_loading(self):
        tt = self._thec_load_thread_isRunning()
        self.logger.debug(
            f"self._thec_load_thread_isRunning = {tt} "
        )
        if tt:
            self._load_thread.quit()
            self._load_thread.wait(500)
            self._load_thread = None

        self._loading_in_progress = False

    @AppLogger.get_instance(
        name='PaginationMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _reload_with_order_by(self, order_by: List[str]) -> None:
        """
        Перезагружает данные с новой сортировкой.
        """
        self._current_order_by = order_by
        self._load_first_page()

    @AppLogger.get_instance(
        name='PaginationMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _thec_load_thread_isRunning(self):
        self.logger.debug(
            f"self._load_thread is None = {self._load_thread is None} "
        )
        if self._load_thread is not None:
            tt = self._load_thread.isRunning()
            self.logger.debug(
                f"self._load_thread is None = {self._load_thread is None} "
                f"self._load_thread.isRunning() = {tt} "
            )
            if tt:
                return True

        return False
    @AppLogger.get_instance(
        name='PaginationMixin',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def cancel_loading(self):
        tt = self._thec_load_thread_isRunning()
        self.logger.debug(
            f"self._thec_load_thread_isRunning = {tt} "
        )
        if tt:
            self._load_thread.terminate()   # или requestInterruption, но лучше использовать флаг
            self._load_thread.wait()
            self._load_thread = None

        self._loading_in_progress = False
