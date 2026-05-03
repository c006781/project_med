# interfaces/gui/gui_window/widgets/photo_uploader_widget.py

import os
from typing import List, Set, Tuple, Dict

from app.utils.logger.logger import AppLogger

from app.dto import PhotoDTO

from interfaces.gui.gui_window.utils.gui_helpers import add_copy_paste_to_table, install_standard_context_menu

from interfaces.gui.gui_window.widgets.delegate.type_delegate import CompleterStringDelegate

from PySide6.QtCore import (
    Q_ARG, QEvent, QMetaObject, 
    QRunnable, QThreadPool, Signal, 
    Qt, QSize, Slot
)
from PySide6.QtGui import (
    QColor, QPixmap,
    QFontMetrics, QPainter, 
    QTextOption
)
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QMessageBox, 
    QWidget, QVBoxLayout, 
    QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, 
    QHeaderView, QFileDialog, 
    QDialog, QLabel, 
    QScrollArea, QStyledItemDelegate,
    QStyleOptionViewItem, QTextEdit, 
    # QApplication
)



class AsyncImageLoader(QRunnable):
    """Загружает миниатюру изображения в отдельном потоке."""
    #
    # @AppLogger.get_instance(
    #     name = 'AsyncImageLoader',
    #     # share_file_with = 'system',
    #     enable_file_logging = 'system',
    #     use_name_in_filename = False, # 'system',
    # ).log_execution_time(
    #     level = AppLogger._parse_log_level('DEBUG')
    # )
    # def __init__(self, path: str, target_size: QSize, callback):
    #     super().__init__()
    #     self.path = path
    #     self.target_size = target_size
    #     self.callback = callback   # callable, который будет вызван в главном потоке с QPixmap
    #
    # @AppLogger.get_instance(
    #     name = 'AsyncImageLoader',
    #     # share_file_with = 'system',
    #     enable_file_logging = 'system',
    #     use_name_in_filename = False, # 'system',
    # ).log_execution_time(
    #     level = AppLogger._parse_log_level('DEBUG')
    # )
    # def run(self):
    #     pixmap = QPixmap(self.path)
    #     if not pixmap.isNull():
    #         pixmap = pixmap.scaled(
    #             self.target_size,
    #             Qt.KeepAspectRatio,
    #             Qt.SmoothTransformation
    #         )
    #
    #     QMetaObject.invokeMethod(
    #         self.callback,
    #         'on_image_loaded',
    #         Qt.QueuedConnection,
    #         Q_ARG(QPixmap, pixmap)
    #     )

    @AppLogger.get_instance(
        name = 'AsyncImageLoader',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def __init__(self, widget, row, full_path, target_size):
        super().__init__()
        self.widget = widget          # PhotoUploaderWidget (наследник QObject)
        self.row = row
        self.full_path = full_path
        self.target_size = target_size

    @AppLogger.get_instance(
        name = 'AsyncImageLoader',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def run(self):
        pixmap = QPixmap(self.full_path)
        if not pixmap.isNull():
            pixmap = pixmap.scaled(
                self.target_size, 
                Qt.KeepAspectRatio, 
                Qt.SmoothTransformation
            )

        # Вызовем метод _on_thumbnail_loaded в главном потоке
        QMetaObject.invokeMethod(
            self.widget,
            "_on_thumbnail_loaded",
            Qt.QueuedConnection,
            Q_ARG(int, self.row),
            Q_ARG(QPixmap, pixmap),
            Q_ARG(str, self.full_path)
        )

class PhotoDelegate(QStyledItemDelegate):
    """
    Делегат для отрисовки масштабированной иконки в ячейке таблицы.
    """

    @AppLogger.get_instance(
        name = 'PhotoDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def __init__(self, parent, photo_widget):
        super().__init__(parent)
        
        self.photo_widget = photo_widget

        self._target_size = QSize(300, 300)  # желаемый размер миниатюры

        # логгер
        self.logger = AppLogger.get_instance(
            name=f"gui.PhotoDelegate",
            # share_file_with = 'user',
            enable_file_logging = 'user',
            use_name_in_filename = False, # 'user',
        )

    @AppLogger.get_instance(
        name = 'PhotoDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def paint(
        self, 
        painter: QPainter, 
        option: QStyleOptionViewItem, 
        index
    ):
        """
        Переопределяет метод для отрисовки масштабированной иконки в ячейке таблицы.
        
        :param painter: QPainter - объект для отрисовки
        :param option: QStyleOptionViewItem - параметры для отрисовки
        :param index: QModelIndex - индекс элемента в таблице
        """
        full_path = index.data(Qt.UserRole) # абсолютный путь к файлу изображения

        self.logger.debug(f"paint: full_path : {full_path}")
        def _tt(painter_,option_, gray, AlignCenter, text ):
            painter_.fillRect(option_.rect, gray)
            painter_.drawText(option_.rect, AlignCenter, text)

        if not full_path:
            # Путь не задан – показываем заглушку
            _tt(painter, option, Qt.gray, Qt.AlignCenter, "Нет фото")
            # super().paint(painter, option, index)
            return
        
        # Проверяем существование файла
        if not os.path.exists(full_path):
            _tt(painter, option, Qt.lightGray, Qt.AlignCenter, "Фото отсутствует в папке хранения фото")
            # super().paint(painter, option, index)
            return
        
        # Попытка взять из кэша
        # pixmap = self.photo_widget._get_pixmap(full_path)
        pixmap = self.photo_widget._image_cache.get(full_path)
        self.logger.debug(f"paint: pixmap : {pixmap is not None and not pixmap.isNull()}")

        if pixmap is not None and not pixmap.isNull():
            rect = option.rect
            scaled = pixmap.scaled(rect.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)

            x = rect.x() + (rect.width() - scaled.width()) // 2
            y = rect.y() + (rect.height() - scaled.height()) // 2

            self.logger.debug(f"paint: x, y : {x}, {y}")

            painter.drawPixmap(x, y, scaled)

            return

        # Заглушка "Загрузка..."
        # Файл существует, но не загружен – показываем заглушку "Загрузка..."
        _tt(painter, option, Qt.lightGray, Qt.AlignCenter, "Загрузка...")

        # Запрашиваем асинхронную загрузку, если ещё не запрошено
        if full_path not in self.photo_widget._image_cache:
            self.photo_widget.request_thumbnail(index.row(), full_path, self._target_size)

    @AppLogger.get_instance(
        name = 'PhotoDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def sizeHint(self, option: QStyleOptionViewItem, index):
        return QSize(100, 100)

class TextEditDelegate(QStyledItemDelegate):
    """
    Делегат для редактирования текста в ячейке с помощью многострочного QTextEdit.

    Что это (кратко):
        Позволяет редактировать описание фото с переносами строк (Shift+Enter — новая строка, Enter — завершить редактирование).

    Что это (максимально подробно):
        Стандартный QStyledItemDelegate заменяется на QTextEdit для поддержки многострочного текста.
        Поддерживает автоматический перенос по словам, вертикальную прокрутку и специальную обработку клавиш.
        После завершения редактирования **принудительно** вызывает _on_item_changed родительского PhotoUploaderWidget,
        чтобы гарантировать срабатывание photosChanged даже если Qt не сгенерировал itemChanged.

    Как работает:
        1. createEditor — создаёт QTextEdit.
        2. setEditorData / setModelData — загружает/сохраняет текст.
        3. eventFilter — обрабатывает Enter / Shift+Enter.
        4. После commitData вручную вызывает метод photo_widget._on_item_changed.

    param parent : (QWidget) Родительский виджет (обычно таблица).
    param photo_widget : (PhotoUploaderWidget) Ссылка на основной виджет, чтобы вызвать _on_item_changed.
    """

    @AppLogger.get_instance(
        name = 'TextEditDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def __init__(self, parent=None, photo_widget=None):
        super().__init__(parent)

        self.photo_widget = photo_widget 
        
        self.logger = AppLogger.get_instance(
            name='gui.TextEditDelegate',
            # share_file_with = 'user',
            enable_file_logging = 'user',
            use_name_in_filename = False, # 'user',
        )

        self.logger.debug("TextEditDelegate инициализирован")

    @AppLogger.get_instance(
        name = 'TextEditDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def createEditor(self, parent, option, index):
        """Создаёт QTextEdit вместо стандартного QLineEdit."""
        editor = QTextEdit(parent)
        editor.setAcceptRichText(False)
        editor.setWordWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        editor.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        editor.setMinimumHeight(80)

        install_standard_context_menu(editor)

        self.logger.debug(f"createEditor: создан QTextEdit для строки {index.row()}")

        return editor

    @AppLogger.get_instance(
        name = 'TextEditDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def setEditorData(self, editor, index):
        """Загружает текущий текст в редактор."""
        value = index.model().data(index, Qt.EditRole)
        if value is not None:
            editor.setPlainText(str(value))
            self.logger.debug(f"setEditorData: загружен текст для строки {index.row()}")

    @AppLogger.get_instance(
        name = 'TextEditDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def setModelData(self, editor, model, index):
        """Сохраняет текст из редактора в модель."""

        new_text = editor.toPlainText()
        model.setData(index, new_text, Qt.EditRole)

        self.logger.debug(
            f"setModelData: "
            f"сохранён текст '{new_text[:50]}...' "
            f"для строки {index.row()}"
        )

        # # Принудительно вызываем обработчик изменений в PhotoUploaderWidget
        # if self.photo_widget and hasattr(self.photo_widget, '_on_item_changed'):
        #     item = self.photo_widget.table.item(index.row(), index.column())
        #     if item:
        #         self.photo_widget._on_item_changed(item)
        #         self.logger.debug("setModelData: ПРИНУДИТЕЛЬНО вызван _on_item_changed → photosChanged")
        #     else:
        #         self.logger.warning("setModelData: item не найден")
        # else:
        #     self.logger.warning("setModelData: photo_widget отсутствует или нет метода _on_item_changed")

    @AppLogger.get_instance(
        name = 'TextEditDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def updateEditorGeometry(self, editor, option, index):
        """Устанавливает геометрию редактора (растягивается на всю ячейку)."""
        editor.setGeometry(option.rect)

    @AppLogger.get_instance(
        name = 'TextEditDelegate',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def eventFilter(self, editor, event):
        """
        Обрабатывает нажатия клавиш в редакторе.
        Enter завершает редактирование, Shift+Enter вставляет перенос строки.
        """
        if event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_Enter or event.key() == Qt.Key_Return:
                if event.modifiers() == Qt.ShiftModifier:
                    self.logger.debug("eventFilter: Shift+Enter — перенос строки")
                    return False
                else:
                    self.logger.debug("eventFilter: Enter — завершение редактирования")
                    self.commitData.emit(editor)
                    self.closeEditor.emit(editor, QStyledItemDelegate.NoHint)
                    return True
        return super().eventFilter(editor, event)


class PhotoUploaderWidget(QWidget):
    """
    Виджет для управления фотографиями приёма.

    Отображает таблицу с двумя столбцами:
        - столбец 0: миниатюра фото (асинхронная загрузка)
        - столбец 1: описание фото (редактируемое, с автодополнением)

    Поддерживает:
        - добавление фото через кнопку или drag-and-drop
        - удаление фото (помечает на удаление, не удаляет сразу)
        - редактирование описаний
        - отмену изменений (всех или только для текущей строки)
        - режим «только просмотр» (readonly)
        - асинхронную загрузку миниатюр (ленивая загрузка при прокрутке)
        - восстановление состояния (черновиков) через `dump_state` / `load_state`

    Сигналы:
        photosChanged: испускается при любом изменении состава фото или описаний.
    """

    MAX_PHOTOS = 0  # ограничить максимальное количество загружаемых фото в приём. 0 - без ограницений

    VALID_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff'}

    photosChanged = Signal()

    @AppLogger.get_instance(
        name = 'PhotoUploaderWidget',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def __init__(self, parent=None):
        """
        Инициализирует виджет для управления фотографиями приёма.

        Создаёт необходимые структуры данных:
            - pending_photos: новые фото (ещё не сохранены в БД)
            - existing_photos: фото, загруженные из БД (список PhotoDTO)
            - deleted_photo_ids: ID фото, помеченных на удаление
            - modified_photo_ids: ID фото, у которых изменено описание
            - original_descriptions: исходные описания для сравнения

        Настраивает таблицу, делегаты, кэш изображений и пул потоков для асинхронной загрузки.
        По умолчанию виджет находится в режиме «только просмотр» (`self._readonly = True`).

        Args:
            parent (QWidget, optional): Родительский виджет. По умолчанию None.
        """

        super().__init__(parent)

        self.logger = AppLogger.get_instance(
            name='gui.PhotoUploaderWidget',
            # share_file_with = 'user',
            enable_file_logging = 'user',
            use_name_in_filename = False, # 'user',
        )
        self.logger.debug("Инициализация PhotoUploaderWidget")

        self._readonly = True  # по умолчанию виджет только для просмотра

        # Данные
        self.pending_photos: List[Tuple[str, str]] = []   # (путь, описание)
        self.existing_photos: List[PhotoDTO] = []         # существующие фото
        self.original_descriptions: Dict[int, str] = {}   # начальные данные из БД
        self.deleted_photo_ids: Set[int] = set()          # ID на удаление
        self.modified_photo_ids: Set[int] = set()         # ID изменённых фото
        
        self._storage_path: str = None                    # базовый путь к хранилищу
        self._image_cache: Dict[str, QPixmap] = {}        # кэш изображений

        self._thumbnail_target_size = QSize(300, 300)

        self._async_loader_pool = QThreadPool.globalInstance()  # пул загрузчиков
        self._pending_loaders = set()

        self.setAcceptDrops(True)       # разрешить перетаскивание

        self._setup_ui()                # инициализация интерфейса

        self._adjust_column_widths()    # настройка ширин столбцов

    @AppLogger.get_instance(
        name = 'PhotoUploaderWidget',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def request_thumbnail(self, row: int, full_path: str, target_size: QSize):
        """Асинхронно загружает миниатюру для указанной строки."""
        if full_path in self._image_cache:
            self._on_thumbnail_loaded(row, self._image_cache[full_path])
            return
        
        # Предотвращаем повторные запросы для одного пути (опционально)
        if hasattr(self, '_loading_paths') and full_path in self._loading_paths:
            return
        
        if not hasattr(self, '_loading_paths'):
            self._loading_paths = set()

        self._loading_paths.add(full_path)

        # loader = AsyncImageLoader(
        #     full_path, 
        #     target_size, 
        #     lambda pixmap: self._on_thumbnail_loaded(
        #         row, 
        #         pixmap, 
        #         full_path
        #     )
        # )

        loader = AsyncImageLoader(self, row, full_path, target_size)

        self._async_loader_pool.start(loader)
        self._pending_loaders.add(loader)


    @AppLogger.get_instance(
        name = 'PhotoUploaderWidget',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    @Slot(int, QPixmap, str)
    def _on_thumbnail_loaded(
        self,
        row: int,
        pixmap: QPixmap,
        full_path: str
    ):
        """
        Вызывается в главном потоке после асинхронной загрузки миниатюры.

        Сохраняет QPixmap в кэш (`self._image_cache`), затем запускает пересчёт
        высоты строки (только для указанной строки) и обновляет viewport.

        Параметры:
            row (int): Индекс строки, для которой загружена миниатюра.
            pixmap (QPixmap): Загруженная миниатюра (уже масштабирована).
            full_path (str): Абсолютный путь к файлу.
        """

        if row >= self.table.rowCount():
            return
        
        if full_path in self._loading_paths:
            self._loading_paths.discard(full_path)

        if not pixmap.isNull():
            self._image_cache[full_path] = pixmap
            # После загрузки миниатюры обновляем высоту строки
            self._adjust_row_heights(
                row
            )

        # Перерисовываем строку
        self.table.viewport().update()

    @AppLogger.get_instance(
        name = 'PhotoUploaderWidget',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _load_visible_thumbnails(self):
        """Загружает миниатюры для строк, видимых в данный момент."""
        if not self.table.isVisible():
            return
        
        viewport = self.table.viewport()
        first_row = self.table.rowAt(0)
        last_row = self.table.rowAt(viewport.height())

        if first_row < 0:
            first_row = 0

        if last_row < 0:
            last_row = self.table.rowCount() - 1

        for row in range(first_row, last_row + 1):
            item = self.table.item(row, 0)
            if item:
                full_path = item.data(Qt.UserRole)
                if full_path and full_path not in self._image_cache:
                    self.request_thumbnail(row, full_path, self._thumbnail_target_size)

    @AppLogger.get_instance(
        name = 'PhotoUploaderWidget',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _on_scroll(self, value):
        """Обработчик прокрутки – подгружаем видимые миниатюры."""
        self._load_visible_thumbnails()
        
    @AppLogger.get_instance(
        name = 'PhotoUploaderWidget',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def get_existing_photos(self) -> List[PhotoDTO]:
        """Возвращает список существующих фото (актуальные после редактирования описаний)."""
        # return self.existing_photos
        result = []
        for p in self.existing_photos:
            if isinstance(p, dict):
                result.append(PhotoDTO(**p))
            elif isinstance(p, PhotoDTO):
                result.append(p)
            else:
                # fallback – попробуем преобразовать через model_validate
                result.append(PhotoDTO.model_validate(p))
        return result

    
    @AppLogger.get_instance(
        name='PhotoUploaderWidget',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def dump_state(self) -> dict:
        """
        Возвращает сериализуемое состояние виджета: существующие фото, pending, удалённые, изменённые.
        Используется для сохранения черновиков при переключении между приёмами.
        """
        return {
            'existing_photos': [p.model_dump() for p in self.existing_photos],
            'original_descriptions': self.original_descriptions.copy(),
            'pending_photos': self.pending_photos.copy(),
            'deleted_photo_ids': list(self.deleted_photo_ids),
            'modified_photo_ids': list(self.modified_photo_ids)
        }

    @AppLogger.get_instance(
        name='PhotoUploaderWidget',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def load_state(self, state: dict) -> None:
        """
        Восстанавливает состояние виджета из словаря, полученного от `dump_state`.

        Полностью заменяет текущие данные (очищает виджет, загружает существующие фото, черновики, удалённые ID и изменённые ID). После загрузки вызывает `_refresh_table(if_blockSignals=self._readonly)`, что улучшает производительность в режиме просмотра.

        Параметры:
            state (dict): Словарь, содержащий ключи:
                - 'existing_photos': список словарей PhotoDTO (сериализованных)
                - 'original_descriptions': словарь {photo_id: original_description}
                - 'pending_photos': список кортежей (file_path, description)
                - 'deleted_photo_ids': список int
                - 'modified_photo_ids': список int
        """

        self.logger.debug(f"load_state: pending={state.get('pending_photos')}, existing={state.get('existing_photos')}")
        
        self.clear()

        # Восстанавливаем существующие фото
        self.existing_photos = [PhotoDTO(**p) for p in state['existing_photos']]

        # Дополнительная страховка: если вдруг элементы не PhotoDTO, преобразуем
        self.existing_photos = [
            p if isinstance(p, PhotoDTO) else PhotoDTO.model_validate(p)
            for p in self.existing_photos
        ]
        
        # Восстанавливаем оригинальные описания из сохранённого состояния
        self.original_descriptions = state.get('original_descriptions', {}).copy()

        # Для обратной совместимости: если в state нет original_descriptions, заполняем из current description
        if not self.original_descriptions:
            # Восстанавливаем оригинальные описания из загруженного состояния
            for photo in self.existing_photos:
                self.original_descriptions[photo.id] = photo.description or ""

        self.pending_photos = state['pending_photos']
        self.deleted_photo_ids = set(state['deleted_photo_ids'])
        self.modified_photo_ids = set(state['modified_photo_ids'])

        self._refresh_table(
            if_blockSignals = self._readonly,  # Блокируем сигналы, если виджет в режиме только просмотр
        )

    @AppLogger.get_instance(
        name='PhotoUploaderWidget',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def clear_pending_and_deleted(self) -> None:
        """Сбрасывает только pending и deleted, оставляя существующие фото."""
        self.logger.debug("clear() — ПОЛНАЯ очистка PhotoUploaderWidget")

        self.pending_photos.clear()
        self.existing_photos.clear()
        self.deleted_photo_ids.clear()
        self.modified_photo_ids.clear()
        self._image_cache.clear()

        self.table.setRowCount(0)
        self.table.clearContents()   # <-- это важно

        self.logger.debug("PhotoUploaderWidget полностью очищен")


    # ----------------------------------------------------------------------
    # Построение интерфейса
    # ----------------------------------------------------------------------

    @AppLogger.get_instance(
        name='PhotoUploaderWidget',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    @Slot(int)
    def _on_action_selected(self, index):
        """Обрабатывает выбор действия в выпадающем списке."""
        if index == 1:  # Добавить фото
            self.add_photo()
        elif index == 2:  # Удалить выбранное
            self._remove_selected()
        elif index == 3:        # Отменить все изменения
            self._cancel_all_changes()
        elif index == 4:        # Отменить текущее
            self._cancel_current_row_changes()

        # Сбрасываем индекс на заглушку
        self.action_combo.blockSignals(True)
        self.action_combo.setCurrentIndex(0)
        self.action_combo.blockSignals(False)

    @AppLogger.get_instance(
        name='PhotoUploaderWidget',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _cancel_all_changes(self):
        """
        Отменить все несохранённые изменения:
        - Удалить все новые (pending) фото
        - Восстановить удалённые существующие фото (убрать из deleted_photo_ids)
        - Восстановить исходные описания для изменённых фото
        """
        self.logger.info("Отмена всех изменений в фото")
        
        # 1. Очистить pending_photos (новые фото, которые ещё не сохранены)
        self.pending_photos.clear()
        
        # 2. Восстановить удалённые фото (убрать ID из deleted_photo_ids)
        self.deleted_photo_ids.clear()
        
        # 3. Восстановить описания изменённых фото
        for photo in self.existing_photos:
            original_desc = self.original_descriptions.get(photo.id, "")
            if photo.description != original_desc:
                photo.description = original_desc
        
        # 4. Очистить modified_photo_ids
        self.modified_photo_ids.clear()
        
        # 5. Обновить таблицу и цвета
        self._refresh_table()
        self.photosChanged.emit()
        self.logger.debug("Все изменения в фото отменены")

    @AppLogger.get_instance(
        name='PhotoUploaderWidget',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _cancel_current_row_changes(self):
        """
        Отменить изменения только для текущей выбранной строки.
        - Если строка соответствует новому фото (pending) – удалить его.
        - Если строка соответствует существующему фото:
            - Если фото помечено на удаление – снять пометку.
            - Если описание изменено – восстановить исходное.
        """

        # Получаем текущую выбранную строку
        selected_rows = set()
        for item in self.table.selectedItems():
            selected_rows.add(item.row())
        if not selected_rows:
            self.logger.debug("Нет выбранной строки для отмены")
            QMessageBox.warning(self, "Внимание", "Выберите строку для отмены изменений.")
            return
        
        row = next(iter(selected_rows))
        self.logger.debug(f"Отмена изменений для строки {row}")
        
        # Определяем, существующее это фото или новое
        if row < len(self.existing_photos):
            # Существующее фото
            photo = self.existing_photos[row]
            photo_id = photo.id
            
            # Снимаем пометку на удаление, если была
            if photo_id in self.deleted_photo_ids:
                self.deleted_photo_ids.discard(photo_id)
                self.logger.debug(f"Снята пометка удаления для фото ID={photo_id}")
            
            # Восстанавливаем описание, если было изменено
            original_desc = self.original_descriptions.get(photo_id, "")
            if photo.description != original_desc:
                photo.description = original_desc
                # Убираем из modified_photo_ids
                self.modified_photo_ids.discard(photo_id)
                self.logger.debug(f"Восстановлено описание для фото ID={photo_id}")

                # Обновляем текст в ячейке таблицы
                item = self.table.item(row, 1)
                if item:
                    item.setText(original_desc)
            
            # Обновляем цвет строки и перерисовываем
            self._set_row_color(row)
        else:
            # Новое фото (pending)
            pending_index = row - len(self.existing_photos)
            if pending_index < len(self.pending_photos):
                del self.pending_photos[pending_index]
                self.logger.debug(f"Удалено новое фото (строка {row})")
                # Полностью перестраиваем таблицу, так как количество строк изменилось
                self._refresh_table()
            else:
                self.logger.warning(f"Не удалось найти pending фото для строки {row}")
        
        # Обновляем состояние кнопок и сигнал
        self.photosChanged.emit()
        self._update_buttons_state() 
        # Обновляем доступность кнопки просмотра
        self.view_btn.setEnabled(len(self.table.selectedItems()) > 0)
        
        # Обновляем состояние пунктов меню отмены
        self._update_undo_actions_state()

        self.logger.debug("Отмена для текущей строки завершена")

    AppLogger.get_instance(
        name='PhotoUploaderWidget',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _has_unsaved_changes(self) -> bool:
        """
        Возвращает True, если есть несохранённые изменения:
        - новые фото (pending)
        - удалённые фото (deleted_photo_ids)
        - изменённые описания (modified_photo_ids)
        """
        return bool(self.pending_photos or self.deleted_photo_ids or self.modified_photo_ids)

    @AppLogger.get_instance(
        name='PhotoUploaderWidget',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _has_current_row_changes(self, row: int) -> bool:
        """
        Проверяет, есть ли изменения у конкретной строки.
        """
        if row < len(self.existing_photos):
            photo = self.existing_photos[row]
            if photo.id in self.deleted_photo_ids:
                return True
            if photo.id in self.modified_photo_ids:
                return True
            return False
        else:
            # Новая строка (pending)
            pending_index = row - len(self.existing_photos)
            return pending_index < len(self.pending_photos)

    @AppLogger.get_instance(
        name='PhotoUploaderWidget',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _update_undo_actions_state(self):
        """
        Обновляет доступность пунктов «Отменить все изменения» и «Отменить текущее»
        в выпадающем списке в зависимости от наличия изменений.
        """
        model = self.action_combo.model()
        # Пункт "Отменить все изменения" (индекс 3) активен, если есть любые изменения
        has_changes = self._has_unsaved_changes()
        model.item(3).setEnabled(has_changes)
        
        # Пункт "Отменить текущее" (индекс 4) активен, если есть выбранная строка с изменениями
        selected_rows = set()
        for item in self.table.selectedItems():
            selected_rows.add(item.row())
        if selected_rows:
            row = next(iter(selected_rows))
            has_current_changes = self._has_current_row_changes(row)
        else:
            has_current_changes = False
        model.item(4).setEnabled(has_current_changes)

    @AppLogger.get_instance(
        name = 'PhotoUploaderWidget',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _update_buttons_state(self):
        """Обновляет состояние кнопок в зависимости от выделения."""
        has_selection = len(self.table.selectedItems()) > 0
        self.view_btn.setEnabled(has_selection)
        # Можно также управлять доступностью пунктов меню, но комбобокс остаётся всегда активным в режиме редактирования

    @AppLogger.get_instance(
        name = 'PhotoUploaderWidget',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _setup_ui(self):
        """
        Построение интерфейса PhotoUploaderWidget: таблица, кнопок добавления/удаления,
        кнопки просмотра, настройка столбцов, делегатов, сигналов.
        """
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # Таблица
        self.table = QTableWidget()
        self.table.verticalScrollBar().valueChanged.connect(self._on_scroll)

        add_copy_paste_to_table(self.table)
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Фото", "Описание"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)

        # Настройка столбцов
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setWordWrap(True)  # для отображения многострочного текста

        # Делегаты
        photo_delegate = PhotoDelegate(self.table, self)
        self.table.setItemDelegateForColumn(0, photo_delegate)

        # # text_delegate = TextEditDelegate(self.table)
        # text_delegate = TextEditDelegate(self.table, self)  # <-- передаём self (PhotoUploaderWidget)
        # self.table.setItemDelegateForColumn(1, text_delegate)

        # Создаём делегат с автодополнением
        # Функция получения уникальных значений должна быть установлена извне
        self.description_delegate = CompleterStringDelegate(
            self.table,
            get_unique_values_func=self._get_unique_values_for_description,
            column=1
        )
        self.table.setItemDelegateForColumn(1, self.description_delegate)

        # Сигналы
        self.table.itemDoubleClicked.connect(self._on_table_double_clicked)
        self.table.itemChanged.connect(self._on_item_changed)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)

        main_layout.addWidget(self.table)

        # Кнопки
        # btn_layout = QHBoxLayout()
        # self.add_btn = QPushButton("Добавить фото")
        # self.add_btn.clicked.connect(self.add_photo)
        # btn_layout.addWidget(self.add_btn)

        # self.view_btn = QPushButton("Просмотр")
        # self.view_btn.clicked.connect(self._view_photo)
        # self.view_btn.setEnabled(False)
        # btn_layout.addWidget(self.view_btn)

        # self.remove_btn = QPushButton("Удалить выбранное")
        # self.remove_btn.clicked.connect(self._remove_selected)
        # btn_layout.addWidget(self.remove_btn)

        # main_layout.addLayout(btn_layout)

        # Кнопки
        btn_layout = QHBoxLayout()

        # Выпадающий список действий
        self.action_combo = QComboBox()
        self.action_combo.addItem("▼ Действия")
        self.action_combo.addItem("Добавить фото")
        self.action_combo.addItem("Удалить выбранное")
        self.action_combo.addItem("Отменить все изменения")  
        self.action_combo.addItem("Отменить текущее")        
        self.action_combo.setEditable(False)
        self.action_combo.setMaximumWidth(150)
        self.action_combo.model().item(0).setEnabled(False)  # первый пункт невыбираемый
        self.action_combo.setCurrentIndex(0)
        self.action_combo.currentIndexChanged.connect(self._on_action_selected)
        btn_layout.addWidget(self.action_combo)

        # Кнопка просмотра (отдельно)
        self.view_btn = QPushButton("Просмотр")
        self.view_btn.clicked.connect(self._view_photo)
        self.view_btn.setEnabled(False)
        btn_layout.addWidget(self.view_btn)

        # # Кнопка удаления (можно оставить, но она дублирует пункт в комбобоксе, поэтому скроем)
        # self.remove_btn = QPushButton("Удалить выбранное")
        # self.remove_btn.clicked.connect(self._remove_selected)
        # self.remove_btn.setVisible(False)  # скрываем, т.к. действие в комбобоксе
        # btn_layout.addWidget(self.remove_btn)  # не добавляем, или добавляем, но скрываем

        main_layout.addLayout(btn_layout)

    @AppLogger.get_instance(
        name='PhotoUploaderWidget',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    def _append_pending_row(
        self,
        file_path: str,
        description: str = ""
    ):
        """
        Добавляет одну строку в конец таблицы для нового фотографии (pending).

        Используется вместо полной перестройки таблицы при добавлении одного фото.
        Это предотвращает сброс уже загруженных миниатюр и повышает производительность.

        Параметры:
            file_path (str): Путь к исходному файлу (абсолютный).
            description (str): Начальное описание фото (по умолчанию пустая строка).
        """

        row = self.table.rowCount()

        self.table.insertRow(row)
        self._set_table_row(
            row,
            file_path,
            description,
            is_existing=False
        )
        self._set_row_color(row)
        self._adjust_row_heights(row)  # пересчёт высоты только для новой строки

    @AppLogger.get_instance(
        name = 'PhotoUploaderWidget',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _get_unique_values_for_description(self, column: int) -> List[str]:
        """
        Возвращает список уникальных описаний фото.
        Используется для автодополнения.
        """
        if not hasattr(self, '_unique_values_func') or self._unique_values_func is None:
            return []
        return self._unique_values_func()
    
    @AppLogger.get_instance(
        name = 'PhotoUploaderWidget',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def set_unique_values_func(self, func):
        """
        Устанавливает функцию, возвращающую список уникальных строк для автодополнения.
        :param func: вызываемый объект без аргументов, возвращающий List[str]
        """
        self._unique_values_func = func
        # Обновим делегат, если он уже создан
        if hasattr(self, 'description_delegate'):
            self.description_delegate._get_unique_values_func = lambda col: func()
            self.description_delegate._cache.clear()

    @AppLogger.get_instance(
        name = 'PhotoUploaderWidget',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _adjust_column_widths(self):
        """
        Устанавливает ширину столбцов таблицы.

        Ширина столбца 0 составляет 1/3 ширины таблицы.
        Если ширина таблицы не определена, то ширина столбцов не изменяется.
        """
        width = self.table.viewport().width()
        if width > 0:
            col0_width = int(width * 0.33)
            self.table.setColumnWidth(0, col0_width)
            self.logger.debug(f"Ширина столбца 0: {col0_width}")

    @AppLogger.get_instance(
        name = 'PhotoUploaderWidget',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._adjust_column_widths()
        # self._adjust_row_heights() # Убрано – высота будет корректироваться по необходимости

    # ----------------------------------------------------------------------
    # Обработчики событий таблицы
    # ----------------------------------------------------------------------

    @AppLogger.get_instance(
        name = 'PhotoUploaderWidget',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _on_selection_changed(self):
        """
        Обработчик события changes selection в таблице.

        Enables view button if there is at least one selected item.
        """
        self.view_btn.setEnabled(
            len(self.table.selectedItems()) > 0
        )

        self._update_undo_actions_state()   # обновить состояние кнопки отмены текущей строки

    @AppLogger.get_instance(
        name = 'PhotoUploaderWidget',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _on_table_double_clicked(
        self, 
        item: QTableWidgetItem
    ):
        """
        Обработчик события двой клики по таблице.

        Если двой клик произошел в столбце 0 (фото), то отображает фото.
        Если двой клик произошел в столбце 1 (описание), то ничего не делает.
        """
        if item.column() == 0:
            self._view_photo()
        # столбец 1 редактируется автоматически через делегат


    @AppLogger.get_instance(
        name = 'PhotoUploaderWidget',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _row_work_modified_photo(
        self, 
        row,
        new_text
    ):
        photo = self.existing_photos[row]
        # original_desc = photo.description or "" 
        original_desc = self.original_descriptions.get(photo.id, "")

        self.logger.debug(
            f"photo.description = {photo.description}, "
            f"original_desc = {original_desc}, "
            f"new_text = {new_text}, "
            f"original_desc != new_text = {original_desc != new_text}"
        )  

        self.logger.debug(
            f"_on_item_changed: "
            f"row={row}, : "
            # f"col={column}, : "
            f"new_text='{new_text}', : "
            f"old_desc='{original_desc}'"
        )
            
        
        photo.description = new_text # указываем новое значение

        if original_desc != new_text:
            # Действительно изменилось относительно оригинала
            if photo.id not in self.modified_photo_ids:
                self.logger.debug("  → описание изменилось, эмитируем photosChanged")
                self.modified_photo_ids.add(photo.id) # помечаем как изменённое

                return True
        else:  
            if photo.id in self.modified_photo_ids: # если вернулось, то удаляем из модификации  
                self.logger.debug("  → описание как в БД")
                self.modified_photo_ids.discard(photo.id) # удаляем из изменённое   
                return True
            else:
                self.logger.debug(f"  → Фото ID={photo.id} не было modified — ничего не делаем")    

        return False                                 

    @AppLogger.get_instance(
        name = 'PhotoUploaderWidget',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _row_work_create_photo(
        self, 
        row,
        new_text
    ):
        # Обработка новых фото (pending) 
        pending_index = row - len(self.existing_photos)

        self.logger.debug(f"if pending_index < len(self.pending_photos) = {pending_index < len(self.pending_photos)}")  
        if pending_index < len(self.pending_photos):
            file_path, old_desc = self.pending_photos[pending_index]
            if old_desc != new_text:
                self.pending_photos[pending_index] = (file_path, new_text)
                # Для новых фото цвет уже зелёный, не меняем
                # self.photosChanged.emit()
                self.logger.debug("Обновлено описание нового фото")
                return True
            
        return False
    

    @AppLogger.get_instance(
        name = 'PhotoUploaderWidget',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _on_item_changed(self, item: QTableWidgetItem):
        """
        Обработчик изменения описания фото в таблице.

        Что делает:
        - Для существующих фото: сравнивает новое описание с оригинальным.
          Если отличается — помечает в modified_photo_ids и красит строку в жёлтый.
          Если вернули точно к оригиналу — снимает пометку modified_photo_ids и красит в белый.
        - Для новых фото (pending): просто обновляет описание.
        - В любом случае изменений вызывает photosChanged, чтобы AppointmentListPage
          мог синхронизировать состояние и обновить выделение строки приёма.

        :param item: Изменённый QTableWidgetItem (столбец описания)
        :type item: QTableWidgetItem
        """

        if not item:
            self.logger.warning("_on_item_changed: item is None")
            # return

        row = item.row()
        column = item.column()

        self.logger.debug(f"if rcolumn != 1 = {column != 1}")  

        if column != 1:
            self.logger.debug(f"_on_item_changed: пропуск — изменение не в столбце описания (column={column})")
            return

        new_text = item.text() # .strip() НЕ используем — пользователь может хотеть пробелы

        self.logger.debug(f"_on_item_changed: new_text = '{new_text[:60]}...'")

        self.logger.debug(f"if row < len(self.existing_photos) = {row < len(self.existing_photos)}")  


        thec = False
        if row < len(self.existing_photos): # существующие фото
            thec = self._row_work_modified_photo( # работа с покраской строки в можифицированно или нет
                row=row,
                new_text = new_text
            )
           
            if thec:
                self._update_row_color(row)          # перекрасить
                # self.photosChanged.emit() # сигнал : Что-то изменилось в фотографиях этого приёма
            
        else:
            # Обработка новых фото (pending) 
            thec = self._row_work_create_photo( # Обработка новых фото
                row=row,
                new_text = new_text
            )

        if thec:
            # self._update_row_color(row)          # перекрасить
            self.photosChanged.emit() # сигнал : Что-то изменилось в фотографиях этого приёма
            self._update_undo_actions_state()

        # 0==0

    # ----------------------------------------------------------------------
    # Действия с фотографиями
    # ----------------------------------------------------------------------

    @AppLogger.get_instance(
        name = 'PhotoUploaderWidget',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _add_photo_files(
        self,
        file_paths
    ) -> int:
        """
        Добавляет список файлов в pending_photos с проверкой расширений и лимита.

        Для каждого валидного файла:
            - добавляет запись в `self.pending_photos`
            - вызывает `_append_pending_row` для добавления строки в таблицу

        Параметры:
            file_paths (List[str]): Список путей к файлам.

        Returns:
            int: Количество успешно добавленных фото.
        """

        added = 0
        for file_path in file_paths:
            ext = os.path.splitext(file_path)[1].lower()
            if ext not in self.VALID_EXTENSIONS:
                self.logger.debug(
                    f"Файл {file_path} имеет неподдерживаемое расширение, пропускаем"
                )
                continue
            
            if self.MAX_PHOTOS > 0 and len(self.pending_photos) + added >= self.MAX_PHOTOS:
                self.logger.warning(
                    f"Достигнут лимит фото ({self.MAX_PHOTOS}), остальные файлы не добавлены"
                )
                break
            
            self.pending_photos.append((file_path, ""))
            self._append_pending_row(file_path, "")

            added += 1

            self.logger.debug(f"Добавлено фото: {file_path}")
        
        if added:
            # self._refresh_table()
            self.photosChanged.emit()
            self._update_undo_actions_state()

        return added


    @AppLogger.get_instance(
        name = 'PhotoUploaderWidget',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def dragEnterEvent(self, event):
        """
        Обработчик начала перетаскивания. Если виджет в режиме readonly – игнорирует.
        Иначе проверяет, есть ли среди перетаскиваемых URL-адресов файлы с допустимыми
        расширениями (VALID_EXTENSIONS). Если есть – принимает действие.

        Параметры:
            event (QDragEnterEvent): Событие перетаскивания.
        """

        if self._readonly:
            event.ignore()
            return

        mime_data = event.mimeData()
        if not mime_data.hasUrls():
            event.ignore()
            return

        for url in mime_data.urls():
            file_path = url.toLocalFile()
            if file_path and os.path.splitext(file_path)[1].lower() in self.VALID_EXTENSIONS:
                event.acceptProposedAction()
                return

        event.ignore()

    @AppLogger.get_instance(
        name = 'PhotoUploaderWidget',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def dragMoveEvent(self, event):
        """
        Обработчик перемещения при перетаскивании. Повторяет логику dragEnterEvent.
        Если виджет в режиме readonly – игнорирует.

        Параметры:
            event (QDragMoveEvent): Событие перемещения.
        """

        if self._readonly:
            event.ignore()
            return

        # Если не readonly, можно разрешить перемещение
        self.dragEnterEvent(event)

    @AppLogger.get_instance(
        name = 'PhotoUploaderWidget',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def dropEvent(self, event):
        """Обрабатывает сброшенные файлы, добавляя их через _add_photo_files."""
        """
        Обработчик сброса файлов.
            Если виджет в режиме readonly – игнорирует.
            Иначе извлекает пути из mimeData и передаёт их в `_add_photo_files`.

        Параметры:
            event (QDropEvent): Событие сброса.
        """

        if self._readonly:
            event.ignore()
            return

        mime_data = event.mimeData()
        if not mime_data.hasUrls():
            event.ignore()
            return
        
        file_paths = []
        for url in mime_data.urls():
            file_path = url.toLocalFile()
            if file_path:
                file_paths.append(file_path)
        
        if file_paths:
            self._add_photo_files(file_paths)

        event.acceptProposedAction()   

    @AppLogger.get_instance(
        name = 'PhotoUploaderWidget',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def add_photo(self):
        """Добавляет одно или несколько новых фото через диалог выбора файлов."""
        file_paths, _ = QFileDialog.getOpenFileNames(
            self, 
            "Выберите изображение", 
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.gif)"
        )
        if file_paths:
            self._add_photo_files(file_paths)
            self.logger.debug(f"Добавлено {len(file_paths)} фото")

    @AppLogger.get_instance(
        name = 'PhotoUploaderWidget',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _remove_selected(self):
        """
        Удаляет выбранные строки таблицы (если они существующие, то помечает их как изменённые).
        :return: None
        :rtype: None
        """
        try:
            selected_rows = set()

            for item in self.table.selectedItems(): # помечаем как удалённые
                selected_rows.add(item.row())

            if not selected_rows:
                return

            for row in sorted(selected_rows, reverse=True): # удаляем в обратном порядке
                self._remove_row(row)

            # Обновляем цвет для помеченных строк
            for row in selected_rows:
                self._update_row_color(row)

            self.photosChanged.emit() # сигнал об изменениях
            self._update_undo_actions_state()
            self.logger.debug(f"Помечено на удаление {len(selected_rows)} фото")

        except Exception as e:
            self.logger.exception(f"Ошибка при удалении фото: {e}")
            raise e

    @AppLogger.get_instance(
        name = 'PhotoUploaderWidget',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    # def _remove_row(self, row: int):
    #     """Помечает строку на удаление, но не удаляет её из таблицы."""
    #     if row < len(self.existing_photos):
    #         photo = self.existing_photos[row]
    #         if photo.id not in self.deleted_photo_ids:
    #             self.deleted_photo_ids.add(photo.id)
    #             # Если фото было изменено, убираем из modified (оно теперь удаляется)
    #             self.modified_photo_ids.discard(photo.id)
    #         # Не удаляем из existing_photos – они останутся, но будут удалены при сохранении
    #     else:
    #         # Новые фото (pending) – удаляем сразу, так как они ещё не в БД
    #         pending_index = row - len(self.existing_photos)
    #         if pending_index < len(self.pending_photos):
    #             del self.pending_photos[pending_index]
    #             self._refresh_table()   # перестроим таблицу (новые фото исчезнут)
    #             self.logger.debug("Удалено новое фото")

    def _remove_row(self, row: int):
        """
        Помечает строку на удаление, но не удаляет её из таблицы.

        Если строка соответствует существующему фото, то добавляет ID в множество self.deleted_photo_ids.
        Если фото было изменено, то убираем из множества self.modified_photo_ids.

        Если строка соответствует новому фото (pending), то удаляет его из self.pending_photos и перестраивает таблицу.
        """

        """
        Помечает строку на удаление, но не удаляет её из таблицы.

        Если строка соответствует существующему фото, её ID добавляется в `self.deleted_photo_ids`, а также убирается из `self.modified_photo_ids` (если было изменено описание). 
        Сама строка не удаляется – удаление произойдёт при сохранении.

        Если строка соответствует новому (pending) фото, то оно удаляется из `self.pending_photos` и строка удаляется из таблицы (вызовом `removeRow`), после чего таблица не перестраивается.

        Параметры:
            row (int): Индекс строки в таблице.
        """

        if row < len(self.existing_photos):
            photo = self.existing_photos[row]
            if photo.id not in self.deleted_photo_ids:

                # добавляем ID в множество удалённых
                self.deleted_photo_ids.add(photo.id)
            
                # если фото было изменено, убираем из modified (оно всё равно удалится)
                self.modified_photo_ids.discard(photo.id)  # если было изменено, убираем из modified

                self._set_row_color(row)  # перекрасить в красный

                # не удаляем из existing_photos, чтобы сохранить возможность отмены
        else:
            # новые фото (pending) – удаляем сразу
            pending_index = row - len(self.existing_photos)
            if pending_index < len(self.pending_photos):

                del self.pending_photos[pending_index]

                # self._refresh_table()
                self.table.removeRow(row)
                self.logger.debug("Удалено новое фото")


    @AppLogger.get_instance(
        name = 'PhotoUploaderWidget',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _view_photo(self):
        """
        Открывает фото, выбранное в таблице.

        Если фото существует в БД, то берёт путь к файлу из _storage_path.
        Если фото pending, то берёт путь из pending_photos.

        Если файл не найден, то выводит предупреждение.

        Если файл не удалось загрузить, то выводит предупреждение.

        Создаёт диалог с просмотром фото, если файл существует и можно загрузить.
        """

        selected_rows = set()

        for item in self.table.selectedItems():
            selected_rows.add(item.row())

        if not selected_rows:
            return
        
        row = next(iter(selected_rows))

        # Определяем путь к файлу (может быть даже для удалённых фото)
        if row < len(self.existing_photos):
            photo = self.existing_photos[row]
            full_path = os.path.join(self._storage_path, photo.file_path) if self._storage_path else photo.file_path
        else:
            pending_index = row - len(self.existing_photos)
            file_path, _ = self.pending_photos[pending_index]
            full_path = file_path

        if not os.path.exists(full_path):
            self.logger.warning(f"Файл не найден: {full_path}")
            return

        # pixmap = self._get_pixmap(full_path)
        pixmap = QPixmap(full_path)
        if pixmap.isNull():
            self.logger.warning(f"Не удалось загрузить: {full_path}")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Просмотр фото")
        layout = QVBoxLayout(dialog)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        label = QLabel()
        label.setPixmap(pixmap)
        scroll.setWidget(label)
        layout.addWidget(scroll)
        close_btn = QPushButton("Закрыть")
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn)
        dialog.resize(800, 600)
        dialog.exec()

    # ----------------------------------------------------------------------
    # Работа с таблицей
    # ----------------------------------------------------------------------

    @AppLogger.get_instance(
        name = 'PhotoUploaderWidget',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _refresh_table(
        self,
        if_blockSignals: bool = False
    ):
        """
        Полностью перестраивает таблицу фото и сбрасывает все цвета.

        Этот метод вызывается при массовой замене данных (например, из `set_existing_photos` или `load_state`).
        Если `if_blockSignals=True`, то на время заполнения отключаются сигналы `itemChanged`, лишние вызовы `_on_item_changed`.

        Параметры:
            if_blockSignals (bool): Если True, сигналы таблицы блокируются на время вставки строк.
        """

        self.logger.debug(
            f"_refresh_table: "
            f"existing={len(self.existing_photos)}, "
            f"pending={len(self.pending_photos)}"
        )

        total_rows = len(self.existing_photos) + len(self.pending_photos)

        self.table.setRowCount(0)
        self.table.setRowCount(total_rows)
        self.table.setUpdatesEnabled(False)

        if if_blockSignals:
            self.table.blockSignals(True)  # отключение сигналов на время первичного заполнения

        try:
            # Заполняем строки
            for i, photo in enumerate(self.existing_photos):
                self._set_table_row(
                    i,
                    photo.file_path,
                    photo.description or "",
                    is_existing=True
                )

            for i, (file_path, desc) in enumerate(self.pending_photos):
                row = len(self.existing_photos) + i
                self._set_table_row(
                    row,
                    file_path,
                    desc,
                    is_existing=False
                )

            # Принудительно пересчитываем цвет КАЖДОЙ строки
            for row in range(total_rows):
                self._set_row_color(row)

        finally:
            if if_blockSignals:
                self.table.blockSignals(False)  # <-- Восстанавливаем сигналы  после отключение сигналов на время первичного заполнения

            self.table.setUpdatesEnabled(True)

        # # Цвета можно установить после восстановления сигналов
        # for row in range(total_rows):
        #     self._set_row_color(row)

        self._adjust_row_heights()

        # Максимально агрессивная перерисовка
        self.table.viewport().update()
        self.table.repaint()
        self.table.horizontalHeader().repaint()
        self.table.verticalHeader().repaint()

        self._update_undo_actions_state()

        self.logger.debug(
            f"_refresh_table завершена. "
            f"Строк в таблице: {total_rows}"
        )

        self._load_visible_thumbnails()

    @AppLogger.get_instance(
        name = 'PhotoUploaderWidget',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _set_table_row(
        self, 
        row: int, 
        file_path: str, 
        description: str, 
        is_existing: bool
    ):
        """
        Устанавливает значения для строки таблицы.

        :param row: Номер строки
        :type row: int
        :param file_path: Путь к файлу (может быть дельным для удалённых фото)
        :type file_path: str
        :param description: Описание фото
        :type description: str
        :param is_existing: True, если фото существует в БД, False, если фото pending
        :type is_existing: bool
        """

        self.logger.debug(f'file_path : {file_path}')

        full_path = file_path

        self.logger.debug(f'is_existing and self._storage_path : {is_existing and self._storage_path}')
        if is_existing and self._storage_path:
            full_path = os.path.join(self._storage_path, file_path)
            self.logger.debug(f"Установка фото: {full_path}, существует: {os.path.exists(full_path)}")

        item_icon = QTableWidgetItem()
        item_icon.setData(Qt.UserRole, full_path)
        item_icon.setFlags(item_icon.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(row, 0, item_icon)

        item_text = QTableWidgetItem(description)
        item_text.setFlags(item_text.flags() | Qt.ItemIsEditable)
        item_text.setTextAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.table.setItem(row, 1, item_text)

    @AppLogger.get_instance(
        name = 'PhotoUploaderWidget',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _adjust_row_heights(self, row: int = None):
        
        """
        Устанавливает высоту строк таблицы на основе ширины столбца 0.

        Если ширина столбца 0 не определена, то ничего не делается.

        Для каждой строки таблицы берется путь к файлу из столбца 0 и ширина столбца 1.
        Если путь к файлу не определен, то для строки ничего не делается.

        Берется пиксель из файла (если файл существует) и вычисляется соотношение ширины к высоте.
        Если пиксель не может быть загружен, то используется высота 100.

        Высота вычисляется как максимум из:
            - высоты миниатюры (после масштабирования к ширине столбца 0)
            - высоты текста описания (с учётом переноса слов)
        плюс небольшой отступ (10 пикселей).

        Пересчитывает высоту строк(и). Если row не указан – пересчитывает все строки

        Параметры:
            row (Optional[int]): Если указан, пересчитывается только эта строка; если None – все строки таблицы.
        """
        
        col0_width = self.table.columnWidth(0)
        if col0_width <= 0:
            return

        font = self.table.font()
        metrics = QFontMetrics(font)
        rows = [row] if row is not None else range(self.table.rowCount())

        for r in rows:
            if r >= self.table.rowCount():
                continue

            item_icon = self.table.item(r, 0)
            full_path = item_icon.data(Qt.UserRole) if item_icon else None

            if not full_path:
                continue
            pixmap = self._get_pixmap(full_path)
            if pixmap.isNull():
                # Нет миниатюры – используем дефолтную высоту 100
                icon_height = 100
            else:
                # Миниатюра уже есть – вычисляем высоту на её основе
                ratio = pixmap.width() / pixmap.height() if pixmap.height() > 0 else 1.0
                scaled_width = min(col0_width, pixmap.width())
                icon_height = max(int(scaled_width / ratio) if ratio > 0 else 100 , 1)


            # Высота текста описания
            item_text = self.table.item(r, 1)
            text = item_text.text() if item_text else ""
            text_height = 0

            if text:
                text_width = self.table.columnWidth(1) - 10
                if text_width > 0:
                    rect = metrics.boundingRect(0, 0, text_width, 0, Qt.TextWordWrap, text)
                    text_height = rect.height()

            row_height = max(icon_height, text_height) + 10
            self.table.setRowHeight(r, row_height)

    # ----------------------------------------------------------------------
    # Кэширование
    # ----------------------------------------------------------------------

    @AppLogger.get_instance(
        name = 'PhotoUploaderWidget',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _get_pixmap(self, full_path: str) -> QPixmap:
        """
        Возвращает QPixmap по полному пути к файлу.

        Если файл находится в кэше изображений, то возвращает кэшированное изображение.
        Если файл не существует или не удалось загрузить, то возвращает пустой QPixmap.

        :param full_path: путь к файлу
        :type full_path: str
        :return: QPixmap по полному пути к файлу
        :rtype: QPixmap
        """
        self.logger.debug(f'full_path : {full_path}, full_path in self._image_cache : {full_path in self._image_cache}')
        if full_path in self._image_cache:
            return self._image_cache[full_path]

        if not os.path.exists(full_path):
            self.logger.warning(f"Файл не найден: {full_path}")
            return QPixmap()

        pixmap = QPixmap(full_path)

        self.logger.debug(f'if not pixmap.isNull() : {not pixmap.isNull()}')
        if not pixmap.isNull():
            self._image_cache[full_path] = pixmap
        else:
            self.logger.warning(f"Не удалось загрузить изображение: {full_path}")

        return pixmap

    # ----------------------------------------------------------------------
    # Публичные методы
    # ----------------------------------------------------------------------

    @AppLogger.get_instance(
        name = 'PhotoUploaderWidget',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def set_storage_path(self, path: str):
        """
        Установка пути к хранилищу.

        :param path: Путь к хранилищу
        :type path: str
        """
        self._storage_path = path
        self.logger.debug(f"Путь к хранилищу: {path}")

    @AppLogger.get_instance(
        name='PhotoUploaderWidget',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def set_existing_photos(
        self,
        photos: List[PhotoDTO]
    ):
        """
        Устанавливает существующие фото из БД (после сохранения или при загрузке приёма).

        Полностью очищает все временные состояния (pending, deleted, modified),
        кэш и таблицу, затем нормализует входные данные (преобразует dict → PhotoDTO),
        сохраняет оригинальные описания и перестраивает таблицу с блокировкой сигналов,
        если виджет находится в режиме просмотра.

        Параметры:
            photos (List[PhotoDTO]): Список DTO фотографий из БД.
        """

        self.logger.debug(f"set_existing_photos ЗАПУЩЕН. Получено {len(photos) if photos else 0} фото из БД")

        # Полная очистка ВСЕГО состояния виджета
        self.clear() # полный сброс
        # self.pending_photos.clear()
        # self.deleted_photo_ids.clear()
        # self.modified_photo_ids.clear()
        # self._image_cache.clear()


        # Заполняем новыми данными
        # self.existing_photos = list(photos) if photos else []
        # if photos and isinstance(photos[0], dict):
        #     self.existing_photos = [PhotoDTO(**p) for p in photos]
        #     self.logger.debug("Фото преобразованы из dict → PhotoDTO")
        # else:
        #     self.existing_photos = list(photos) if photos else []

        # Нормализация: гарантируем, что все элементы – PhotoDTO
        normalized = []
        for p in (photos or []):
            if isinstance(p, dict):
                normalized.append(PhotoDTO(**p))
            elif isinstance(p, PhotoDTO):
                normalized.append(p)
            else:
                normalized.append(PhotoDTO.model_validate(p))

        self.existing_photos = normalized

        # Сохраняем оригинальные описания
        self.original_descriptions.clear()

        for photo in self.existing_photos:
            self.original_descriptions[photo.id] = photo.description or ""

        self._refresh_table(
            if_blockSignals = self._readonly, # Блокируем сигналы, если виджет в режиме только просмотр
        )

        # # Принудительно сбрасываем цвета всех строк (убираем зелёный)
        # for row in range(self.table.rowCount()):
        #     self._set_row_color(row)

        self.table.viewport().update()      # принудительная перерисовка
        self.table.repaint()

        self.logger.debug(
            f"set_existing_photos ЗАВЕРШЁН. "
            f"existing={len(self.existing_photos)}, "
            f"pending={len(self.pending_photos)}, "
            f"строк в таблице={self.table.rowCount()}"
        )

    @AppLogger.get_instance(
        name = 'PhotoUploaderWidget',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def get_pending_photos(self) -> List[Tuple[str, str]]:
        """
        Возвращает список новых фото (pending) в формате (путь, описание).

        :return: Список новых фото (pending)
        :rtype: List[Tuple[str, str]]
        """
        return self.pending_photos

    @AppLogger.get_instance(
        name = 'PhotoUploaderWidget',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def get_deleted_photo_ids(self) -> List[int]:
        """
        Возвращает список ID фото, помеченных на удаление.

        :return: Список ID фото, помеченных на удаление
        :rtype: List[int]
        """
        return list(self.deleted_photo_ids)

    @AppLogger.get_instance(
        name='PhotoUploaderWidget',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def clear(self):
        """
        Полная очистка виджета перед загрузкой свежих данных из БД.
        """
        self.logger.debug("clear() — ПОЛНАЯ очистка PhotoUploaderWidget")

        self.pending_photos.clear()
        self.existing_photos.clear()
        self.original_descriptions.clear()
        self.deleted_photo_ids.clear()
        self.modified_photo_ids.clear()
        self._image_cache.clear()

        if hasattr(self, '_loading_paths'):
            self._loading_paths.clear()

        self._pending_loaders.clear()
        
        self.table.setRowCount(0)
        self.table.clearContents()


        self.logger.debug("PhotoUploaderWidget полностью очищен")

    @AppLogger.get_instance(
        name = 'PhotoUploaderWidget',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def set_readonly(
        self, 
        readonly: bool = True, # Режим "только просмотр"
    ):
        """
        Устанавливает режим «только просмотр»: отключает кнопки добавления/удаления.

        В режиме readonly:
            - отключаются кнопки добавления/удаления
            - запрещается редактирование описаний (ячеек)
            - запрещается drag-and-drop файлов
            - таблица переводится в режим NoEditTriggers

        Параметры:
            readonly (bool): True – режим просмотра, False – режим редактирования.
        """
        self._readonly = readonly
        self.setAcceptDrops(not readonly)  # запрещаем перетаскивание в режиме просмотра

        self.action_combo.setEnabled(not readonly)
        self.view_btn.setEnabled(not readonly)

        # Если требуется запретить редактирование описаний, можно установить делегату другой режим,
        # но для простоты оставим как есть (пользователь может кликнуть, но изменения не сохранятся,
        # так как в режиме просмотра мы не вызываем _save). Однако можно также отключить редактирование ячеек:
        # self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)

        if readonly:
            self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        else:
            self.table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)

        # обновить состояние пунктов (они станут неактивными,
        # если комбобокс выключен, но это не нужно, т.к. комбобокс отключён целиком)
        self._update_undo_actions_state()
    # ----------------------------------------------------------------------
    # Вспомогательные методы для цвета строк
    # ----------------------------------------------------------------------

    @AppLogger.get_instance(
        name = 'PhotoUploaderWidget',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _get_row_state(self, row: int) -> str:
        """
        Возвращает состояние строки: 'new', 'modified', 'deleted', 'normal'.
        
        Если строка соответствует существующему фото, то возвращает 'deleted', если фото было помечено на удаление, 
        'modified', если фото было изменено, или 'normal', если фото не было изменено.
        
        Если строка соответствует новому фото (pending), то возвращает 'new'.
        """
        self.logger.debug(f"_get_row_state(row={row})") 
        if row < len(self.existing_photos):
            photo = self.existing_photos[row]

            self.logger.debug(
                f"if photo.id : in self.deleted_photo_ids = {photo.id in self.deleted_photo_ids} "
                f"| in self.modified_photo_ids = {photo.id in self.modified_photo_ids}"
            )

            if photo.id in self.deleted_photo_ids:
                self.logger.debug(f"{row}    → состояние: deleted (красный)")
                return 'deleted'
            
            if photo.id in self.modified_photo_ids:
                self.logger.debug(f"{row}     → состояние: modified (жёлтый)")
                return 'modified'
            
            self.logger.debug(f"{row}     → состояние: normal (белый)")
            return 'normal'
        
        else:
            # Новые фото (pending)
            self.logger.debug(f"{row}     → pending photo → состояние: new (зелёный)")
            return 'new'

    @AppLogger.get_instance(
        name = 'PhotoUploaderWidget',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _set_row_color(self, row: int):
        """
        Устанавливает цвет фона для всей строки на основе текущего состояния.

        После сохранения все добавленные фото становятся существующими,
        поэтому зелёный цвет ('new') больше не должен применяться.
        """
        self.logger.debug(f"_set_row_color: НАЧАЛО, row={row}")
        try:
            state = self._get_row_state(row)
            self.logger.debug(f"_set_row_color: row={row}, state={state}")
        except Exception as e:
            self.logger.exception(f"Ошибка определения состояния строки {row}: {e}")
            # state = 'normal'
            raise e

        if state == 'new':
            color = QColor(200, 255, 200)   # светло-зелёный
        elif state == 'modified':
            color = QColor(255, 255, 180)   # светло-жёлтый
        elif state == 'deleted':
            color = QColor(255, 200, 200)   # светло-красный
        else:
            color = QColor(255, 255, 255)   # белый (нормальное состояние)

        self.logger.debug(f"    → выбран цвет для '{state}': {color.name()}")

        # Блокируем сигналы таблицы, чтобы setBackground не вызывал itemChanged
        self.table.blockSignals(True)
        try:
            for col in range(self.table.columnCount()): # перебираем все столбцы
                self.logger.debug(f"item = self.table.item(row={row}, col={col}), color={color}") 
                item = self.table.item(row, col) # получаем item по координатам строки и столбца
                if item:
                    item.setBackground(color)
        finally:
            self.table.blockSignals(False)

        # # Принудительная перерисовка (опционально)
        # self.table.viewport().update()
        # self.logger.debug(f"Строка {row} окрашена в состояние '{state}'")
        
        # # Принудительная перерисовка
        # self.table.viewport().update
        # self.table_view.viewport().update()   # перерисовка видимой области
        # self.table_view.update()              # перерисовка всей таблицы
        self.logger.debug(f"Строка {row} окрашена в состояние '{state}' и перерисована")

    @AppLogger.get_instance(
        name = 'PhotoUploaderWidget',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _update_row_color(self, row: int):
        """Обновляет цвет строки без перестроения таблицы."""
        self._set_row_color(row)