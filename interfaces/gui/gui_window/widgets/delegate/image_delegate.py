# interfaces/gui/gui_window/widgets/delegate/image_delegate.py
"""
Делегат для отображения миниатюры изображения в ячейке таблицы.

Поддерживает:
    - асинхронную загрузку миниатюр (через QRunnable и кэш);
    - открытие диалога редактирования фото по двойному клику или нажатию кнопки;
    - режим "только просмотр" (readonly);
    - поиск файлов во временных папках черновиков (через ссылку на `PaginatedListPage`).

Атрибуты класса:
    _cache (Dict[str, QPixmap]): Кэш загруженных миниатюр.
    _pending (Dict[str, bool]): Флаги для предотвращения повторной загрузки.

Атрибуты экземпляра:
    logger (AppLogger): Логгер.
    storage_path (str): Базовый путь к хранилищу фотографий.
    target_size (QSize): Желаемый размер миниатюры.
    _readonly (bool): Режим "только просмотр".
    _allowed_extensions (List[str]): Разрешённые расширения файлов.
    _description_field (Optional[str]): Имя поля в DTO, содержащего описание.
    _page (PaginatedListPage): Ссылка на страницу-владельца (для доступа к временным папкам).
    _hovered_row, _hovered_col (int): Индексы строки/столбца под курсором.
    _button_rect (Optional[QRect]): Прямоугольник кнопки для последней ячейки.
    _page_ref (weakref.ref): Слабая ссылка на экземпляр `PaginatedListPage`,
        предоставляющая доступ к временным папкам черновиков через методы
        `_get_temp_dir` и `_ensure_temp_dir`.

Args:
    parent (QWidget): Родительский виджет (таблица).
    page (PaginatedListPage): Обязательная ссылка на экземпляр страницы списка.
    storage_path (str): Базовый путь к хранилищу фотографий.
    target_size (QSize, optional): Желаемый размер миниатюры (по умолч. 80x80).
    allowed_extensions (List[str], optional): Разрешённые расширения.
    description_field (str, optional): Имя поля в DTO, содержащего описание.

Пример:
    >>> delegate = ImageThumbnailDelegate(table_view, page, '/path/to/photos')
    >>> table_view.setItemDelegateForColumn(photo_column, delegate)
"""

import os
from typing import (
    Dict,
    List,
    Optional, 
    # Optional,
)

from collections import OrderedDict

import weakref

from app.utils.logger.logger import AppLogger

from app.utils.colors import RowStatusColor
from app.utils.file_deletions import resolve_photo_path

# from interfaces.gui.gui_window.pages.paginated_list_page import PaginatedListPage
# from interfaces.gui.gui_window.widgets.delegate.photo_edit_dialog import PhotoEditDialog


from PySide6.QtCore import (
    # QMetaObject, Q_ARG, QRect, 
    Q_ARG, QEvent, QMetaObject,
    QRect, QRunnable, QSize, 
    QThreadPool, Qt, Signal, 
    Slot, 
    # QModelIndex,
    # QThread, 
)
from PySide6.QtGui import (
    # QPalette, 
    QPixmap, QPainter, 
    QColor,
)
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QStyle,
    QStyleOptionButton,
    QStyledItemDelegate,
    QStyleOptionViewItem, 
    # QMessageBox,
)

class AsyncImageLoader(QRunnable):
    """Загружает миниатюру в отдельном потоке."""

    finished = Signal(int, QPixmap)  # row, pixmap

    @AppLogger.get_instance(
        name='AsyncImageLoader',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def __init__(
        self, 
        widget, row: int, 
        full_path: str, 
        target_size: QSize
    ):
        """
        Инициализирует загрузчик.

        Args:
            widget: Родительский виджет (PhotoUploaderWidget или ImageThumbnailDelegate).
            row: Индекс строки.
            full_path: Абсолютный путь к файлу.
            target_size: Желаемый размер миниатюры.
        """

        super().__init__()
        self.widget = widget
        self.row = row
        self.full_path = full_path
        self.target_size = target_size

    @AppLogger.get_instance(
        name='AsyncImageLoader',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def run(self):
        pixmap = QPixmap(self.full_path)
        if not pixmap.isNull():
            pixmap = pixmap.scaled(
                self.target_size, 
                Qt.KeepAspectRatio, 
                Qt.SmoothTransformation
            )
        # self.finished.emit(self.row, pixmap)
        
        # Вызовем слот в главном потоке
        QMetaObject.invokeMethod(
            self.widget,
            "_on_thumbnail_loaded",
            Qt.QueuedConnection,
            Q_ARG(int, self.row),
            Q_ARG(QPixmap, pixmap),
            Q_ARG(str, self.full_path)
        )

class ImageThumbnailDelegate(QStyledItemDelegate):
    """
    Делегат для отображения миниатюры изображения в ячейке таблицы.

    Поддерживает:
        - асинхронную загрузку миниатюр (через QRunnable и кэш);
        - открытие диалога редактирования фото по двойному клику или нажатию кнопки;
        - режим "только просмотр" (readonly);
        - поиск файлов во временных папках черновиков (через ссылку на `PaginatedListPage`).

    Атрибуты класса:
        _cache (Dict[str, QPixmap]): Кэш загруженных миниатюр.
        _pending (Dict[str, bool]): Флаги для предотвращения повторной загрузки.

    Атрибуты экземпляра:
        logger (AppLogger): Логгер.
        storage_path (str): Базовый путь к хранилищу фотографий.
        target_size (QSize): Желаемый размер миниатюры.
        _readonly (bool): Режим "только просмотр".
        _allowed_extensions (List[str]): Разрешённые расширения файлов.
        _description_field (Optional[str]): Имя поля описания (если есть).
        _hovered_row (int): Строка под курсором.
        _hovered_col (int): Столбец под курсором.
        _button_rect (Optional[QRect]): Прямоугольник кнопки для последней ячейки.

    Args:
        parent (QWidget, optional): Родительский виджет (обычно QTableView).
        page (PaginatedListPage): Обязательная ссылка на экземпляр страницы списка,
            которая предоставляет методы работы с черновиками (_get_temp_dir, _ensure_temp_dir)
            и доступ к реестру. Не может быть None.
        storage_path (str, optional): Базовый путь к хранилищу фотографий.
        target_size (QSize, optional): Желаемый размер миниатюры.
        allowed_extensions (List[str], optional): Разрешённые расширения.
        description_field (str, optional): Имя поля в DTO, содержащего описание.
    """

    _cache: OrderedDict[str, QPixmap] = OrderedDict()          # общий кэш для всех экземпляров
    _pending: Dict[str, bool] = {}           # флаги, чтобы не дублировать загрузку

    _cache_maxsize = 100   # максимальное количество хранимых миниатюр

    @property
    def logger(self) -> AppLogger:
        try:
            return self._logger
        except AttributeError as e:
            self._logger = AppLogger.get_instance(
                name='gui.ImageThumbnailDelegate',
                enable_file_logging = 'user',
                use_name_in_filename = False, # 'system'
            )

        return self._logger

    @logger.setter
    def logger(self, value):
        self._logger = value

    @AppLogger.get_instance(
        name='ImageThumbnailDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def __init__(
        self,
        parent,
        page: 'PaginatedListPage' , # type: ignore
        # page: Optional['PaginatedListPage'] ,
        storage_path: str = "", 
        target_size: QSize = QSize(80, 80),
        allowed_extensions: List[str] = None,
        description_field: str = None,
    ):
        """
        Делегат для отображения миниатюры изображения в ячейке таблицы.

        Поддерживает:
            - асинхронную загрузку миниатюр (через QRunnable и кэш);
            - открытие диалога редактирования фото по двойному клику или нажатию кнопки;
            - режим "только просмотр" (readonly);
            - поиск файлов во временных папках черновиков (через ссылку на `PaginatedListPage`).

        Атрибуты класса:
            _cache (Dict[str, QPixmap]): Кэш загруженных миниатюр (общий для всех экземпляров).
            _pending (Dict[str, bool]): Флаги для предотвращения повторной загрузки.

        Атрибуты экземпляра:
            logger (AppLogger): Логгер.
            storage_path (str): Базовый путь к хранилищу фотографий.
            target_size (QSize): Желаемый размер миниатюры.
            _readonly (bool): Режим "только просмотр".
            _allowed_extensions (List[str]): Разрешённые расширения файлов.
            _description_field (Optional[str]): Имя поля в DTO, содержащего описание.
            _page (PaginatedListPage): Ссылка на страницу-владельца (для доступа к временным папкам).
            _hovered_row, _hovered_col (int): Индексы строки/столбца под курсором.
            _button_rect (Optional[QRect]): Прямоугольник кнопки для последней ячейки.

        Args:
            parent (QWidget, optional): Родительский виджет (обычно QTableView).
                Не может быть None.
            page (PaginatedListPage): Обязательная ссылка на экземпляр страницы списка,
                которая предоставляет методы работы с черновиками (_get_temp_dir, _ensure_temp_dir)
                и доступ к реестру. Не может быть None.
            storage_path (str, optional): Базовый путь к хранилищу фотографий.
                По умолчанию пустая строка.
            target_size (QSize, optional): Желаемый размер миниатюры (ширина, высота).
                По умолчанию QSize(80, 80).
            allowed_extensions (List[str], optional): Список разрешённых расширений файлов.
                Если None, используются стандартные: .jpg, .jpeg, .png, .gif, .bmp, .tiff.
            description_field (str, optional): Имя поля в DTO, содержащего описание фото.
                Если указано, делегат будет искать это поле при редактировании.
                По умолчанию None.

        Примечания:
            - Параметр `page` является обязательным и должен быть передан первым
              (позиционно или через ключевое слово `page=...`).
            - Родительский виджет `parent` передаётся отдельно через именованный аргумент,
              чтобы избежать путаницы с `page`.
            - После инициализации делегат получает доступ к методам страницы
              `_get_temp_dir` и `_ensure_temp_dir`, что позволяет работать
              с временными папками черновиков.
            - Циклическая зависимость устранена за счёт использования строковой
              аннотации типа 'PaginatedListPage' и отсутствия прямого импорта.
        """

        super().__init__(parent)
        
        self.storage_path = storage_path
        
        self.target_size = target_size 

        self._allowed_extensions = allowed_extensions or ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff']
        self._description_field = description_field
        
        # self._page = page  # <-- сохраняем ссылку на страницу
        self._page_ref = weakref.ref(page) if page is not None else None

        self._readonly = True
        self._hovered_row = -1
        self._hovered_col = -1
        self._button_rect = None

        # self._registry = None      # DraftRegistry
        # self._entity_type = None   # тип сущности (например, 'appointment')

        # Устанавливаем фильтр событий на таблицу для отслеживания Leave
        if parent:
            parent.installEventFilter(self)

    @classmethod
    def clear_cache(cls):
        """Очищает кэш миниатюр (вызывать при уходе со страницы)."""
        cls._cache.clear()
        cls._pending.clear()

    @AppLogger.get_instance(
        name='ImageThumbnailDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def set_readonly(self, readonly: bool) -> None:
        """
        Устанавливает режим "только просмотр".

        Args:
            readonly: True – редактирование запрещено, False – разрешено.
        """
        self._readonly = readonly

    @AppLogger.get_instance(
        name='ImageThumbnailDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def sizeHint(
        self, 
        option : QStyleOptionViewItem, 
        index 
    ) -> QSize:
        """
        Возвращает высоту строки для ячейки.

        Если в ячейке есть фото (поле `file_path` не пустое), возвращает фиксированную высоту,
        равную высоте миниатюры плюс отступ (10 пикселей). Если фото нет, вызывает базовый метод
        для стандартного размера.

        Args:
            option (QStyleOptionViewItem): Параметры стиля для отображения ячейки.
            index (QModelIndex): Индекс ячейки в модели.

        Returns:
            QSize: Рекомендуемый размер ячейки (ширина, высота).
        """
        
        file_path = index.data(Qt.UserRole) if index.isValid() else None
        if not file_path:
            # Нет пути – используем стандартное поведение
            return super().sizeHint(option, index)
        # Есть фото – фиксированная высота на основе target_size
        return QSize(self.target_size.width(), self.target_size.height() + 10)

    @AppLogger.get_instance(
        name='ImageThumbnailDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def set_storage_path(self, path: str) -> None:
        """
        Устанавливает базовый путь к хранилищу фотографий.

        Args:
            path (str): Абсолютный или относительный путь к папке, где хранятся файлы фото.
        """

        self.storage_path = path

        self.clear_cache() # очищаем общий кэш миниатюр

    @AppLogger.get_instance(
        name='ImageThumbnailDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _get_entity_id_at_row(self, row: int) -> Optional[int]:
        """
        Возвращает ID сущности (из DTO) для указанной строки таблицы.

        Метод получает модель из родительского виджета, проверяет наличие метода `get_item_at_row`,
        извлекает DTO и возвращает его атрибут `id`.

        Args:
            row (int): Индекс строки в модели.

        Returns:
            Optional[int]: ID сущности, если строка существует и DTO имеет атрибут `id`, иначе None.
        """
        
        parent = self.parent()
        if parent is None:
            return None
        
        model = parent.model()
        if model is None:
            return None
        
        if not hasattr(model, 'get_item_at_row'):
            return None
        
        dto = model.get_item_at_row(row)

        return getattr(dto, 'id', None) if dto else None

    @AppLogger.get_instance(
        name='ImageThumbnailDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def paint(
        self, 
        painter: QPainter, 
        option: QStyleOptionViewItem, 
        index
    ):
        """
        Отрисовывает ячейку таблицы с миниатюрой фото или заглушкой.

        Алгоритм:
            1. Получает относительный путь к файлу из данных ячейки (Qt.UserRole).
            2. Если пути нет – рисует заглушку «Нет фото».
            3. Преобразует относительный путь в абсолютный (с учётом временной папки черновика,
            если файл находится там).
            4. Если файл не существует – рисует заглушку «Файл не найден».
            5. Проверяет кэш миниатюр; если есть – рисует кэшированную миниатюру.
            6. Если миниатюра ещё не загружена – запускает асинхронную загрузку и рисует
            заглушку «Загрузка...».
            7. Если ячейка под курсором и включён режим редактирования, рисует кнопку «...».

        Args:
            painter (QPainter): Объект для рисования.
            option (QStyleOptionViewItem): Параметры стиля ячейки (прямоугольник, состояние и т.д.).
            index (QModelIndex): Индекс ячейки в модели.
        """

        # Заливаем фон цветом строки (если задан)
        bg_color = index.data(Qt.BackgroundRole)
        if bg_color and isinstance(bg_color, QColor):
            painter.fillRect(option.rect, bg_color)
        else:
            # Если цвета нет
            painter.fillRect(
                option.rect, 
                # option.palette.brush(option.state, QPalette.Window)  # используем стандартный фон из опции
                # option.palette.color(QPalette.Window)  #, используем стандартный цвет фона из палитры
                RowStatusColor.NORMAL # используем унифицированный нормальный цвет
            )

        # Получаем путь к файлу (из UserRole, т.к. DisplayRole возвращает строку)
        file_path = index.data(Qt.UserRole) if index.isValid() else None
        if not file_path:
            self._draw_placeholder(painter, option, "Нет фото")
            return

        # Получаем entity_id для строки (нужен для поиска во временной папке)
        entity_id = self._get_entity_id_at_row(index.row())
        full_path = self._get_full_path(file_path, entity_id)

        if (
            full_path is None
        ) or (
            not os.path.exists(full_path)
        ):
            self._draw_placeholder(painter, option, "Файл не найден")
            return

        # Проверяем кэш
        if full_path in self._cache:
            pixmap = self._cache[full_path]
            self._draw_pixmap(painter, option, pixmap)
            return

        # Если ещё не загружали – запускаем загрузку
        if full_path not in self._pending:
            self._pending[full_path] = True
            loader = AsyncImageLoader(self, index.row(), full_path, self.target_size)
            QThreadPool.globalInstance().start(loader)

        self._draw_placeholder(painter, option, "Загрузка...")

        # full_path = os.path.join(self.storage_path, file_path) if self.storage_path else file_path
        # if not os.path.exists(full_path):
        #     self._draw_placeholder(painter, option, "Файл не найден")
        #     return

        # # Проверяем кэш
        # if full_path in self._cache:
        #     pixmap = self._cache[full_path]
        #     self._draw_pixmap(painter, option, pixmap)
        # else:
        #     # Если ещё не загружали – запускаем загрузку
        #     if full_path not in self._pending:
        #         self._pending[full_path] = True
        #         loader = AsyncImageLoader(self, index.row(), full_path, self.target_size)
        #         QThreadPool.globalInstance().start(loader)
        #     self._draw_placeholder(painter, option, "Загрузка...")


        # Рисуем кнопку, если ячейка под курсором и режим редактирования
        if (
        #     not self._readonly
        # ) and (
            self._hovered_row == index.row()
        ) and (
            self._hovered_col == index.column()
        ):
            btn_rect = self._get_button_rect(option.rect)
            btn_opt = QStyleOptionButton()
            btn_opt.rect = btn_rect
            btn_opt.text = "..."
            btn_opt.state = QStyle.State_Enabled
            self._button_rect = btn_rect
            QApplication.style().drawControl(QStyle.CE_PushButton, btn_opt, painter)

    @AppLogger.get_instance(
        name='ImageThumbnailDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _draw_pixmap(
        self, 
        painter: QPainter, 
        option: QStyleOptionViewItem, 
        pixmap: QPixmap
    ) -> None:
        """
        Рисует миниатюру изображения, центрируя её внутри ячейки.

        Масштабирует `pixmap` до размеров ячейки с сохранением пропорций и рисует
        отцентрированным.

        Args:
            painter (QPainter): Объект для рисования.
            option (QStyleOptionViewItem): Параметры ячейки (прямоугольник).
            pixmap (QPixmap): Изображение для отрисовки.
        """

        rect = option.rect
        scaled = pixmap.scaled(rect.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        x = rect.x() + (rect.width() - scaled.width()) // 2
        y = rect.y() + (rect.height() - scaled.height()) // 2
        # self.logger.debug(f"_draw_pixmap: x: {x}, y: {y}")
        painter.drawPixmap(x, y, scaled)

    @AppLogger.get_instance(
        name='ImageThumbnailDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _get_button_rect(
        self, 
        cell_rect: QRect
    ) -> QRect:
        """
        Возвращает прямоугольник кнопки «...» в правой части ячейки.

        Кнопка имеет фиксированный размер 20×20 пикселей, располагается с отступом
        2 пикселя от правого и верхнего/нижнего краёв (центрируется по вертикали).

        Args:
            cell_rect (QRect): Прямоугольник ячейки.

        Returns:
            QRect: Прямоугольник кнопки.
        """

        btn_w, btn_h = 20, 20
        x = cell_rect.right() - btn_w - 2
        y = cell_rect.top() + (cell_rect.height() - btn_h) // 2

        return QRect(x, y, btn_w, btn_h)

    @AppLogger.get_instance(
        name='ImageThumbnailDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _draw_placeholder(
        self, 
        painter: QPainter, 
        option: QStyleOptionViewItem, 
        text: str
    ) -> None:
        """
        Рисует заглушку в ячейке: серый фон и текст по центру.

        Args:
            painter (QPainter): Объект для рисования.
            option (QStyleOptionViewItem): Параметры ячейки (прямоугольник).
            text (str): Текст для отображения (например, «Нет фото», «Загрузка...»).
        """
        
        # painter.fillRect(option.rect, QColor(240, 240, 240))
        # Фон уже залит в paint, рисуем только текст
        painter.drawText(option.rect, Qt.AlignCenter, text)

    # ------------------------------------------------------------------
    # Асинхронная загрузка
    # ------------------------------------------------------------------

    @AppLogger.get_instance(
        name='ImageThumbnailDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    @Slot(int, QPixmap, str)
    def _on_thumbnail_loaded(
        self, 
        row: int, 
        pixmap: QPixmap,
        full_path: str,
    ) -> None:
        """
        Слот, вызываемый после асинхронной загрузки миниатюры.
        Выполняется в главном потоке (благодаря invokeMethod в загрузчике).

        Сохраняет загруженный `pixmap` в кэш (ключ – `full_path`), удаляет флаг ожидания
        из `_pending` и перерисовывает указанную строку таблицы.

        **Управление кэшем (LRU):**
            - Если путь уже есть в кэше, он перемещается в конец (обновляется порядок).
            - Если путь новый, добавляется в кэш.
            - Если размер кэша превышает `_cache_maxsize`, удаляется самый старый элемент.

        **Алгоритм:**
            1. Удаляет флаг ожидания для данного пути.
            2. Сохраняет загруженный pixmap в кэш (LRU).
            3. Если таблица видима, асинхронно вызывает `refreshRow` для пересчёта высоты
            и перерисовки строки.

        Args:
            row (int): Индекс строки (в исходной модели).
            pixmap (QPixmap): Загруженная миниатюра (может быть пустой при ошибке).
            full_path (str): Абсолютный путь к файлу (ключ кэша).

        Returns:
            None

        Note:
            Использует `QMetaObject::invokeMethod` с `Qt.QueuedConnection`, чтобы
            гарантировать, что операции с геометрией таблицы выполнятся в главном потоке
            после завершения текущих событий.
        """
        
        # Файл больше не в процессе загрузки (всегда удаляем флаг, даже если pixmap пустой)
        self._pending.pop(full_path, None) # удаляется до проверки pixmap.isNull(), чтобы даже при ошибке загрузки повторные запросы для того же файла не блокировались
        
        if not pixmap.isNull():
            # self._cache[full_path] = pixmap
            # self._pending.pop(full_path, None)
            
            # Добавляем в кэш с контролем размера (LRU)
            if full_path in self._cache:
                # Перемещаем в конец (обновляем порядок)
                self._cache.move_to_end(full_path)

            else:
                self._cache[full_path] = pixmap
                # Если превышен лимит, удаляем первый (самый старый) элемент
                if len(self._cache) > self._cache_maxsize:
                    self._cache.popitem(last=False)

            # self._pending.pop(full_path, None)
            
        # Обновляем только затронутую ячейку, если таблица ещё жива
        parent = self.parent()
        if parent is None:
            return

        if not parent.isVisible():
            return
        
        # Асинхронно обновляем строку (пересчёт высоты + перерисовка)
        if hasattr(parent, 'refreshRow'):
            QMetaObject.invokeMethod(
                parent,
                "refreshRow",
                Qt.QueuedConnection,
                Q_ARG(int, row)
            )
        else:
            # Fallback для старых версий (без refreshRow)
            parent.resizeRowToContents(row)
            QMetaObject.invokeMethod(parent, "update", Qt.QueuedConnection)

        # model = parent.model()
        # if model is None:
        #     return
        
        # top_left = model.index(row, 0)
        # bottom_right = model.index(row, model.columnCount() - 1)
        # if top_left.isValid():
        #     # parent.update(top_left, bottom_right)
        #     # parent.viewport().update()
        #     parent.viewport().update()
            
        #         # # Используем invokeMethod для гарантии выполнения в главном потоке
        #     QMetaObject.invokeMethod(
        #         parent,
        #         "update",
        #         Qt.QueuedConnection,
        #         Q_ARG(QModelIndex, top_left),
        #         Q_ARG(QModelIndex, bottom_right)
        #     )



        # # Сохраняем в кэш (ключ – полный путь, но мы его не знаем – можно передавать)
        # # В упрощённом варианте – обновляем ячейку, заставив перерисовать
        # # Для простоты будем обновлять весь виджет таблицы
        # if self.parent() and hasattr(self.parent(), 'viewport'):
        #     self.parent().viewport().update()

    # ------------------------------------------------------------------
    # Обработка событий
    # ------------------------------------------------------------------

    # @AppLogger.get_instance(
    #     name='ImageThumbnailDelegate',
    #     # share_file_with = 'system',
    #     enable_file_logging = 'system',
    #     use_name_in_filename = False, # 'system'
    # ).log_execution_time(
    #     level=AppLogger._parse_log_level('DEBUG')
    # )
    def eventFilter(self, obj, event) -> bool:
        """
        Фильтр событий для отслеживания ухода курсора мыши из таблицы.

        При событии `QEvent.Leave` сбрасывает состояние hover (переменные `_hovered_row`,
        `_hovered_col`) и перерисовывает последнюю ячейку, над которой был курсор.

        Args:
            obj: Объект, на котором произошло событие (обычно таблица).
            event (QEvent): Событие.

        Returns:
            bool: False, чтобы не блокировать дальнейшую обработку события.
        """

        if obj == self.parent() and event.type() == QEvent.Leave:
            if self._hovered_row != -1:
                old_row, old_col = self._hovered_row, self._hovered_col
                self._hovered_row = -1
                self._hovered_col = -1
                idx = self.parent().model().index(old_row, old_col)
                if idx.isValid():
                    self.parent().update(idx)

            return False
        return super().eventFilter(obj, event)

    @AppLogger.get_instance(
        name='ImageThumbnailDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def editorEvent(
        self, 
        event, 
        model, 
        option, 
        index
    ):
        """
        Обрабатывает события мыши для ячейки с фото:
            - движение мыши (hover) – отображает кнопку
            - двойной клик – открывает диалог редактирования
            - клик по кнопке – открывает диалог редактирования

        **Подробное описание:**
            1. **MouseMove**: при движении курсора над ячейкой обновляет индексы `_hovered_row`
            и `_hovered_col`, перерисовывает старую и новую ячейки, что приводит к отображению
            кнопки «...» в правой части ячейки (если режим редактирования включён).
            2. **MouseButtonDblClick**: при двойном клике левой кнопкой мыши, если режим
            редактирования не `readonly`, открывает диалог `PhotoEditDialog` для замены/удаления
            фото и редактирования описания.
            3. **MouseButtonRelease**: при клике левой кнопкой мыши проверяет, попал ли курсор
            в область отрисованной кнопки (прямоугольник `self._button_rect`). Если да –
            открывает диалог редактирования.

        Args:
            event (QEvent): Событие мыши (может быть QMouseEvent, QHoverEvent и т.д.).
            model (QAbstractItemModel): Модель таблицы (источник данных).
            option (QStyleOptionViewItem): Опции отображения ячейки.
            index (QModelIndex): Индекс ячейки, над которой произошло событие.

        Returns:
            bool: True, если событие обработано (например, открыт диалог), иначе
                возвращает результат вызова родительского метода.

        Примечания:
            - Для корректной работы необходимо, чтобы `self.parent()` возвращал указатель
            на таблицу (QTableView), у которой есть метод `update()` для перерисовки ячеек.
            - Диалог редактирования открывается только если `self._readonly == False`.
            - После закрытия диалога изменения в DTO (путь к файлу и описание) применяются
            через вызов `model.setData()`.
        """
                
        # Обновление hover при движении мыши
        if event.type() == QEvent.MouseMove:
            new_row, new_col = index.row(), index.column()
            if (new_row, new_col) != (self._hovered_row, self._hovered_col):
                old_row, old_col = self._hovered_row, self._hovered_col
                self._hovered_row, self._hovered_col = new_row, new_col
                # Перерисовываем старую и новую ячейки
                if old_row != -1:
                    old_idx = model.index(old_row, old_col)
                    if old_idx.isValid():
                        self.parent().update(old_idx)
                self.parent().update(index)
            return False

        # Двойной клик (только в режиме редактирования)
        if event.type() == QEvent.MouseButtonDblClick and event.button() == Qt.LeftButton:
            # if not self._readonly:
            self._open_edit_dialog(model, index)
            return True
            # return False

        # Клик по кнопке
        if event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
            if (self._button_rect) and (self._button_rect.contains(event.pos())):
                self._open_edit_dialog(model, index)
                return True

        return super().editorEvent(event, model, option, index)
    
    @AppLogger.get_instance(
        name='ImageThumbnailDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _get_full_path(
        self,
        rel_path: str,
        entity_id: int
    ) -> str:
        """
        Возвращает полный путь к файлу.

        Сначала проверяет наличие во временной папке черновика (если entity_id известен и
        временная папка существует). Если файл не найден во временной папке,
        возвращает путь в основном хранилище.

        Если `entity_id` известен и для него существует временная папка (через `_page_ref._get_temp_dir`),
        проверяет наличие файла там. Если не найден – возвращает путь в основном хранилище.
        Абсолютные пути возвращаются без изменений (если файл существует).

        **Алгоритм:**
            1. Если `rel_path` – абсолютный путь, проверяет существование файла и возвращает его (или None).
            2. Иначе получает временную папку через `self._page_ref()._get_temp_dir(entity_id)` (слабая ссылка на страницу).
            3. Если временная папка существует и файл в ней присутствует – возвращает полный путь в ней.
            4. Иначе возвращает путь в основном хранилище (`self.storage_path`).

        Args:
            rel_path (str): Относительный путь или имя файла (может быть просто именем).
            entity_id (int): ID сущности (родителя) для поиска временной папки.

        Returns:
            str: Абсолютный путь к файлу (может указывать на несуществующий файл,
                если файл не найден ни во временной папке, ни в основном хранилище).

        Примечание:
            Используется слабая ссылка `self._page_ref`, чтобы не создавать циклических
            зависимостей между делегатом и страницей.
        """

        page = self._page_ref() if hasattr(self, '_page_ref') else None
        temp_dir = None
        if page and entity_id is not None:
            temp_dir = page._get_temp_dir(entity_id)
        
        return resolve_photo_path(
            rel_path=rel_path,
            temp_dir=temp_dir,
            storage_path=self.storage_path,
        )

        # if not rel_path:
        #     return None

        # # Проверка на абсолютный путь
        # if os.path.isabs(rel_path):
        #     return rel_path if os.path.exists(rel_path) else None

        # # Проверяем временную папку черновика  (через слабую ссылку на страницу)
        # # # if self._registry and entity_id is not None and self._entity_type:
        # # if self._page and entity_id is not None:
        # #     # Получаем существующую временную папку (если есть)
        # #     temp_dir = self._page._get_temp_dir(entity_id)

        # # Проверяем временную папку черновика
        # page = self._page_ref() if hasattr(self, '_page_ref') else None
        # if (page is None)  :
        #     self.logger.warning("ImageThumbnailDelegate: page уже уничтожена, невозможно получить временную папку")
        #     return os.path.join(self.storage_path, rel_path) if self.storage_path else rel_path

        # if (entity_id is not None):
        #     temp_dir = page._get_temp_dir(entity_id)
        #     if temp_dir:
        #         candidate = os.path.join(temp_dir, rel_path)
        #         if os.path.exists(candidate):
        #             return candidate
                
        # # elif self._registry is None:
        # #     self.logger.warning("ImageThumbnailDelegate: реестр не установлен, невозможно проверить временную папку")

        # # Основное хранилище
        # return os.path.join(self.storage_path, rel_path) if self.storage_path else rel_path
    
        # # """Возвращает полный путь к файлу, сначала проверяя временную папку."""
        # # if self._registry and entity_id is not None and self._entity_type:
        # #     temp_key = f"__temp_dir__:{self._entity_type}:{entity_id}"
        # #     temp_dir = self._registry.get(temp_key)
        # #     if temp_dir:
        # #         candidate = os.path.join(temp_dir, rel_path)
        # #         if os.path.exists(candidate):
        # #             return candidate
        # # return os.path.join(self.storage_path, rel_path)

    # ------------------------------------------------------------------
    # Диалог редактирования
    # ------------------------------------------------------------------

    @AppLogger.get_instance(
        name='ImageThumbnailDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _update_description_field(
        self, 
        model, 
        row: int, 
        new_description: str
    ) -> None:
        """
        Обновляет поле описания фото в указанной строке модели.
        
        Args:
            model: Модель таблицы (должна иметь метод get_column_at_visible_index).
            row: Индекс строки.
            new_description: Новое описание (может быть пустой строкой).
        """

        if not self._description_field:
            return
        
        for col in range(model.columnCount()):
            col_info = model.get_column_at_visible_index(col) if hasattr(model, 'get_column_at_visible_index') else None
            if col_info and col_info.field_name == self._description_field:
                desc_index = model.index(row, col)
                model.setData(desc_index, new_description, Qt.EditRole)
                break

    @AppLogger.get_instance(
        name='ImageThumbnailDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _open_edit_dialog(self, model, index):
        """
        Открывает диалог редактирования фото.
        Получает текущий путь и описание (если есть) из модели.
        
        **Алгоритм:**
            1. Извлекает относительный путь к файлу из модели (порядок: Qt.UserRole, затем Qt.DisplayRole).
            2. Определяет полный путь к файлу, проверяя сначала временную папку черновика
            (через `self._page_ref._get_temp_dir(entity_id)`), затем основное хранилище.
            3. Если в конфигурации поля указан `description_field`, находит соответствующий столбец
            в модели и получает текущее описание.
            4. Получает ID родительской сущности из DTO строки (через `model.get_item_at_row`).
            5. Создаёт диалог `PhotoEditDialog` в режиме `'single'`, передавая:
            - текущий путь (если файл существует),
            - описание,
            - разрешённые расширения,
            - режим `readonly` (синхронизируется с `self._readonly`),
            - `parent_id`,
            - путь к основному хранилищу,
            - временную папку (если есть, из `self._page_ref._get_temp_dir(parent_id)`).
            6. При успешном закрытии диалога:
            - Если пользователь удалил фото (`new_path is None and new_description is None`),
                очищает поле пути (устанавливает пустую строку) и, если есть поле описания,
                очищает его.
            - Если выбрано новое фото, обновляет поле пути и, при необходимости, поле описания.

        **Примечания:**
            - Метод предполагает, что модель имеет метод `get_item_at_row` для получения DTO.
            - Для поиска столбца описания используется `model.get_column_at_visible_index`,
            если такой метод отсутствует, описание не обновляется (но это не вызывает ошибки).
            - Диалог создаётся только для режима `'single'` (одно фото). Для массового добавления
            используется отдельный механизм (`PaginatedListPage._on_multi_photo_clicked`).

        **Важно:**
            Для любой строки (и новой, и существующей) перед открытием диалога
            вызывается `self._page_ref._ensure_temp_dir(parent_id)`, гарантирующая существование
            временной папки черновика. Все изменения (новое фото, удаление) сохраняются
            во временную папку; окончательное копирование в хранилище происходит при сохранении
            строки в `PaginatedListPage._save_new_row_recursive` или `_save_modified_rows_for_ids`.

        Args:
            model (QAbstractItemModel): Модель таблицы (обычно `PaginatedTableModel`).
            index (QModelIndex): Индекс ячейки, для которой вызывается редактирование.

        Returns:
            None
        """

        #  Режим только просмотра – ничего не делаем
        # if self._readonly:
        #     return

        #  Получаем ссылку на страницу (PaginatedListPage)
        page = self._page_ref() if hasattr(self, '_page_ref') else None
        if page is None:
            self.logger.error("ImageThumbnailDelegate: нет ссылки на страницу для редактирования фото")
            return

        #  Преобразуем индекс из прокси-модели (если есть) в исходный индекс строки
        source_index = index
        parent_view = self.parent()
        if parent_view and hasattr(parent_view, 'model'):
            proxy_model = parent_view.model()
            if hasattr(proxy_model, 'mapToSource'):
                source_index = proxy_model.mapToSource(index)
        if not source_index.isValid():
            self.logger.error("ImageThumbnailDelegate: не удалось получить исходный индекс строки")
            return

        source_row = source_index.row()

        #  Вызываем метод страницы, который выполнит всё остальное
        page.edit_photo_in_row(source_row)


        # # Ленивый импорт, чтобы избежать циклических зависимостей
        # # from interfaces.gui.gui_window.widgets.photo_edit_dialog import PhotoEditDialog
    
        # # Получаем относительный путь из модели
        # rel_path = model.data(index, Qt.UserRole)
        # if rel_path is None:
        #     rel_path = model.data(index, Qt.DisplayRole)

        # if not rel_path or not isinstance(rel_path, str):
        #     rel_path = ""

        # full_path = os.path.join(self.storage_path, rel_path) if rel_path else None
        # if full_path and not os.path.exists(full_path):
        #     full_path = None

        # # Получаем описание, если указано поле
        # description = ""
        # if self._description_field:

        #     # ВНИМАНИЕ: предполагается, что модель имеет метод get_column_at_visible_index,
        #     # который возвращает TableColumn по видимому индексу. Это верно для PaginatedTableModel,
        #     # но может не работать с другими моделями.

        #     # Ищем индекс столбца описания (по имени поля)
        #     for col in range(model.columnCount()):
        #         col_obj = getattr(model, 'get_column_at_visible_index', None)
        #         if col_obj:
        #             column_info = col_obj(col)
        #             if column_info and (
        #                 column_info.field_name == self._description_field
        #             ):
        #                 desc_index = model.index(index.row(), col)
        #                 description = model.data(desc_index, Qt.DisplayRole) or ""
        #                 break
        
        # # Получаем ID родителя из DTO
        # dto = model.get_item_at_row(index.row()) if hasattr(model, 'get_item_at_row') else None
        # parent_id = getattr(dto, 'id', None) if dto else None

        # # Получаем временную папку из реестра (если есть)
        # # temp_dir = None
        # # if self._registry and parent_id is not None and self._entity_type:
        # #     temp_key = f"__temp_dir__:{self._entity_type}:{parent_id}"
        # #     temp_dir = self._registry.get(temp_key)

        # # if self._page_ref is None:
        # #     self.logger.error("ImageThumbnailDelegate: нет ссылки на страницу, невозможно создать временную папку")
        # #     return
        
        # # Получаем временную папку через слабую ссылку на страницу
        # page = self._page_ref() if hasattr(self, '_page_ref') else None
        # if page is None:
        #     self.logger.error("ImageThumbnailDelegate: нет ссылки на страницу, невозможно создать временную папку")
        #     return
        
        # # temp_dir = None
        # # # if self._registry and parent_id is not None and self._entity_type:
        # # #     temp_key = f"__temp_dir__:{self._entity_type}:{parent_id}"
        # # #     temp_dir = self._registry.get(temp_key)
        # # if parent_id is not None :
        # #     # Всегда создаём временную папку для любых строк при редактировании
        # #     # temp_dir = page._ensure_temp_dir(parent_id)
        # #     try:
        # #         temp_dir = page._ensure_temp_dir(parent_id)
        # #     except Exception as e:
        # #         self.logger.error(f"Не удалось создать временную папку для parent_id={parent_id}: {e}")

        # #         QMessageBox.critical(self.parent(), "Ошибка", "Не удалось создать временную папку для черновика.")
        # #         return
        # #     # # Получаем существующую временную папку (если есть)
        # #     # temp_dir = self._page._get_temp_dir(parent_id)
            
        # #     # # Если временной папки нет, создаём её для любой строки (и новой, и существующей)   
        # #     # if temp_dir is None:
        # #     #     temp_dir = self._page._ensure_temp_dir(parent_id)

        # #     # # Гарантируем существование временной папки для существующей строки
        # #     # if parent_id > 0:
        # #     #     # Получаем существующую временную папку (если есть)
        # #     #     temp_dir = self._page._get_temp_dir(parent_id)
        # #     # else:
        # #     #     # Если временной папки нет, создаём её для любой строки (и новой, и существующей)  
        # #     #     temp_dir = self._page._ensure_temp_dir(parent_id)

        # #     # # Получаем существующую временную папку (если есть)
        # #     # temp_dir = self._page._get_temp_dir(parent_id)

        # #     # # # Если временной папки нет, но строка существующая (id > 0) – создаём через страницу
        # #     # # if temp_dir is None and parent_id > 0 and self._page:

        # #     # # Если временной папки нет, создаём её для любой строки (и новой, и существующей)   
        # #     # if temp_dir is None:
        # #     #     temp_dir = self._page._ensure_temp_dir(parent_id)

        # #     # # Если временной папки нет, но строка существующая (id > 0) – создаём
        # #     # if temp_dir is None and parent_id > 0:
        # #     #     # Находим родительскую страницу (таблица -> ... -> PaginatedListPage)
        # #     #     parent_widget = self.parent()
        # #     #     while parent_widget:
        # #     #         if hasattr(parent_widget, '_ensure_temp_dir'):
        # #     #             temp_dir = parent_widget._ensure_temp_dir(parent_id)
        # #     #             break
        # #     #         parent_widget = parent_widget.parent()

        # # if temp_dir is None:
        # #     self.logger.error(f"Не удалось получить временную папку для parent_id={parent_id}")
        # #     return
        
        # # dialog = PhotoEditDialog(
        # #     parent=self.parent(),
        # #     current_path=full_path if full_path and os.path.exists(full_path) else None,
        # #     description=description,
        # #     allowed_extensions=self._allowed_extensions,
        # #     readonly=self._readonly,
        # #     parent_id=parent_id,
        # #     storage_path=self.storage_path,
        # #     mode='single',
        # #     temp_dir=temp_dir, # всегда передан для любых parent_id (не None)
        # # )

        # # if dialog.exec() == QDialog.Accepted:
        # #     new_path, new_description = dialog.get_result()
        # #     if new_path is None and new_description is None:
        # #         # Фото удалено – очищаем поле
        # #         # Полное удаление фото (без изменений описания)
        # #         model.setData(index, "", Qt.EditRole)
        # #         self._update_description_field(model, index.row(), "")
        # #         # if self._description_field:
        # #         #     # Найти индекс столбца описания и очистить
        # #         #     for col in range(model.columnCount()):
        # #         #         col_info = model.get_column_at_visible_index(col) if hasattr(model, 'get_column_at_visible_index') else None
        # #         #         if col_info and col_info.field_name == self._description_field:
        # #         #             desc_index = model.index(index.row(), col)
        # #         #             model.setData(desc_index, "", Qt.EditRole)
        # #         #             break
        # #     elif new_path is None:
        # #         # Фото удалено, но описание изменено
        # #         model.setData(index, "", Qt.EditRole)
        # #         if new_description is not None:
        # #             self._update_description_field(model, index.row(), new_description)                  
        # #     else:
        # #         # Сохраняем относительный путь (копирование файла выполнит сервис)
        # #         # Пока сохраняем абсолютный путь – при сохранении строки сервис скопирует
        # #         # Для правильного хранения нужно определить целевой относительный путь,
        # #         # но это выходит за рамки делегата. Оставляем как есть – модель сохранит строку.
        # #         # Новое фото
        # #         model.setData(index, new_path, Qt.EditRole)
        # #         if new_description is not None and new_description != description:
        # #             self._update_description_field(model, index.row(), new_description)
        # #             # if self._description_field:
        # #             #     for col in range(model.columnCount()):
        # #             #         col_info = model.get_column_at_visible_index(col) if hasattr(model, 'get_column_at_visible_index') else None
        # #             #         if col_info and col_info.field_name == self._description_field:
        # #             #             desc_index = model.index(index.row(), col)
        # #             #             model.setData(desc_index, new_description, Qt.EditRole)
        # #             #             break

        
        # # Получаем имя поля фото (если не задано в делегате)
        # photo_field = getattr(self, '_photo_field', None)
        # if photo_field is None:
        #     photo_field = page.get_photo_field_name()  # предполагаем, что метод добавлен
        #     if photo_field is None:
        #         self.logger.error("ImageThumbnailDelegate: не удалось определить поле фото")
        #         return

        # # Вызываем централизованный метод страницы
        # if_new, new_path, new_description = page.show_photo_edit_dialog(
        #     current_full_path=full_path,
        #     description=description,
        #     photo_field=photo_field,
        #     entity_id=parent_id
        # )

        # if not if_new:
        #     return  # изменений нет
        
        # # Применяем изменения
        # if new_path is None and new_description is None:
        #     # Фото удалено – очищаем поле
        #     model.setData(index, "", Qt.EditRole)
        #     if self._description_field:
        #         self._update_description_field(model, index.row(), "")

        # elif new_path is None:
        #     # Фото удалено, но описание изменено
        #     model.setData(index, "", Qt.EditRole)
        #     if new_description is not None:
        #         self._update_description_field(model, index.row(), new_description)

        # else:
        #     # Новое фото
        #     model.setData(index, new_path, Qt.EditRole)
        #     if new_description is not None and new_description != description:
        #         self._update_description_field(model, index.row(), new_description)
        
        # self._button_rect = None