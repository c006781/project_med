# interfaces/gui/gui_window/widgets/delegate/image_delegate.py
import os
from typing import (
    Dict,
    List,
    Optional, 
    # Optional,
)


from app.utils.logger.logger import AppLogger

from PySide6.QtCore import (
    # QMetaObject, Q_ARG, QRect, 
    Q_ARG, QEvent, QMetaObject, QRect, QRunnable, QSize, QThreadPool, Qt, QThread, Signal, Slot,
)
from PySide6.QtGui import (
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
)

# from interfaces.gui.gui_window.pages.paginated_list_page import PaginatedListPage
from interfaces.gui.gui_window.widgets.delegate.photo_edit_dialog import PhotoEditDialog


class AsyncImageLoader(QRunnable):
    """Загружает миниатюру в отдельном потоке."""

    finished = Signal(int, QPixmap)  # row, pixmap

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

        # super().__init__()
        self.widget = widget
        self.row = row
        self.full_path = full_path
        self.target_size = target_size

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
        - асинхронную загрузку миниатюр
        - кэширование
        - открытие диалога редактирования фото по двойному клику или нажатию кнопки
        - режим "только просмотр" (readonly)

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
    """

    _cache: Dict[str, QPixmap] = {}          # общий кэш для всех экземпляров
    _pending: Dict[str, bool] = {}           # флаги, чтобы не дублировать загрузку

    def __init__(
        self,
        parent,
        page: 'PaginatedListPage' ,
        # page: Optional['PaginatedListPage'] ,
        storage_path: str = "", 
        target_size: QSize = QSize(80, 80),
        allowed_extensions: List[str] = None,
        description_field: str = None,
    ):
        """
        Инициализирует делегат для отображения миниатюр фото в таблице.

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
        self.logger = AppLogger.get_instance('gui.ImageThumbnailDelegate')
        self.storage_path = storage_path
        self.target_size = target_size

        self._allowed_extensions = allowed_extensions or ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff']
        self._description_field = description_field
        
        self._page = page  # <-- сохраняем ссылку на страницу

        self._readonly = True
        self._hovered_row = -1
        self._hovered_col = -1
        self._button_rect = None

        # self._registry = None      # DraftRegistry
        # self._entity_type = None   # тип сущности (например, 'appointment')

        # Устанавливаем фильтр событий на таблицу для отслеживания Leave
        if parent:
            parent.installEventFilter(self)

    # def set_registry(self, registry, entity_type: str):
    #     """
    #     Устанавливает реестр черновиков и тип сущности для поиска временных папок.
    #     Должен быть вызван после создания делегата (например, в _setup_delegates).
    #     (оставлен для обратной совместимости, но теперь не используется)
    #     """
    #     self._registry = registry
    #     self._entity_type = entity_type
    #     # Если есть page, приоритет у page, но можно оставить
    #     if self._page is None:
    #         self.logger.warning("ImageThumbnailDelegate: нет ссылки на страницу, работа с временными папками невозможна")
    #         return
        
    #     if self._page:
    #         self._registry = self._page._draft_registry
    #         self._entity_type = self._page._entity_type

    def set_readonly(self, readonly: bool) -> None:
        """
        Устанавливает режим "только просмотр".

        Args:
            readonly: True – редактирование запрещено, False – разрешено.
        """
        self._readonly = readonly

    def sizeHint(self, option: QStyleOptionViewItem, index):
        """
        Возвращает высоту строки:
            - если в ячейке есть фото → высота миниатюры + отступ
            - иначе → стандартная высота (через базовый метод)
        """
        file_path = index.data(Qt.UserRole) if index.isValid() else None
        if not file_path:
            # Нет пути – используем стандартное поведение
            return super().sizeHint(option, index)
        # Есть фото – фиксированная высота на основе target_size
        return QSize(self.target_size.width(), self.target_size.height() + 10)

    def set_storage_path(self, path: str):
        self.storage_path = path

    def _get_entity_id_at_row(self, row: int) -> Optional[int]:
        """Возвращает ID сущности для указанной строки (из модели)."""
        parent = self.parent()
        if parent is None:
            return None
        
        model = parent.model()
        if model is None:
            return None
        
        dto = model.get_item_at_row(row) if hasattr(model, 'get_item_at_row') else None
        return getattr(dto, 'id', None) if dto else None

    def paint(
        self, 
        painter: QPainter, 
        option: QStyleOptionViewItem, 
        index
    ):
        """
        Отрисовывает ячейку: миниатюру или заглушку, а также кнопку при наведении.
        """

        # Получаем путь к файлу (из UserRole, т.к. DisplayRole возвращает строку)
        file_path = index.data(Qt.UserRole) if index.isValid() else None
        if not file_path:
            self._draw_placeholder(painter, option, "Нет фото")
            return

        # Получаем entity_id для строки (нужен для поиска во временной папке)
        entity_id = self._get_entity_id_at_row(index.row())
        full_path = self._get_full_path(file_path, entity_id)

        if not os.path.exists(full_path):
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
            not self._readonly
        ) and (
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

    def _draw_pixmap(
        self, 
        painter: QPainter, 
        option: QStyleOptionViewItem, 
        pixmap: QPixmap
    ):
        """Рисует миниатюру, центрируя её в ячейке."""

        rect = option.rect
        scaled = pixmap.scaled(rect.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        x = rect.x() + (rect.width() - scaled.width()) // 2
        y = rect.y() + (rect.height() - scaled.height()) // 2
        painter.drawPixmap(x, y, scaled)

    def _get_button_rect(
        self, 
        cell_rect: QRect
    ) -> QRect:
        """Возвращает прямоугольник кнопки в правой части ячейки."""
        btn_w, btn_h = 20, 20
        x = cell_rect.right() - btn_w - 2
        y = cell_rect.top() + (cell_rect.height() - btn_h) // 2
        return QRect(x, y, btn_w, btn_h)

    def _draw_placeholder(
        self, 
        painter: QPainter, 
        option: QStyleOptionViewItem, 
        text: str
    ):
        """Рисует заглушку (серый фон с текстом)."""
        painter.fillRect(option.rect, QColor(240, 240, 240))
        painter.drawText(option.rect, Qt.AlignCenter, text)

    # ------------------------------------------------------------------
    # Асинхронная загрузка
    # ------------------------------------------------------------------

    @Slot(int, QPixmap, str)
    def _on_thumbnail_loaded(
        self, 
        row: int, 
        pixmap: QPixmap,
        full_path: str,
    ):
        """
        Слот, вызываемый после асинхронной загрузки миниатюры.
        Сохраняет pixmap в кэш и перерисовывает ячейку.
        """
        if not pixmap.isNull():
            self._cache[full_path] = pixmap
            self._pending.pop(full_path, None)
            
        # Обновляем только затронутую ячейку, если таблица ещё жива
        
        parent = self.parent()
        if parent is None:
            return
        
        model = parent.model()
        if model is None:
            return
        
        idx = model.index(row, 0)
        if idx.isValid():
            parent.update(idx)

        # # Сохраняем в кэш (ключ – полный путь, но мы его не знаем – можно передавать)
        # # В упрощённом варианте – обновляем ячейку, заставив перерисовать
        # # Для простоты будем обновлять весь виджет таблицы
        # if self.parent() and hasattr(self.parent(), 'viewport'):
        #     self.parent().viewport().update()

    # ------------------------------------------------------------------
    # Обработка событий
    # ------------------------------------------------------------------

    def eventFilter(self, obj, event):
        """Перехватывает событие Leave на таблице, чтобы сбросить hover."""
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
            if not self._readonly:
                self._open_edit_dialog(model, index)
                return True
            return False

        # Клик по кнопке
        if event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
            if self._button_rect and self._button_rect.contains(event.pos()):
                self._open_edit_dialog(model, index)
                return True

        return super().editorEvent(event, model, option, index)

    def sizeHint(self, option, index):
        return QSize(self.target_size.width(), self.target_size.height() + 10)
    
    def _get_full_path(self, rel_path: str, entity_id: int) -> str:
        """
        Возвращает полный путь к файлу.
        Сначала проверяет наличие во временной папке черновика (если entity_id известен).
        Если файл не найден во временной папке, возвращает путь в основном хранилище.
        """
        # Проверяем временную папку черновика
        # if self._registry and entity_id is not None and self._entity_type:
        if self._page and entity_id is not None:
            # Получаем существующую временную папку (если есть)
            temp_dir = self._page._get_temp_dir(entity_id)
            if temp_dir:
                candidate = os.path.join(temp_dir, rel_path)
                if os.path.exists(candidate):
                    return candidate
                
        elif self._registry is None:
            self.logger.warning("ImageThumbnailDelegate: реестр не установлен, невозможно проверить временную папку")

        # Основное хранилище
        return os.path.join(self.storage_path, rel_path) if self.storage_path else rel_path
    
        # """Возвращает полный путь к файлу, сначала проверяя временную папку."""
        # if self._registry and entity_id is not None and self._entity_type:
        #     temp_key = f"__temp_dir__:{self._entity_type}:{entity_id}"
        #     temp_dir = self._registry.get(temp_key)
        #     if temp_dir:
        #         candidate = os.path.join(temp_dir, rel_path)
        #         if os.path.exists(candidate):
        #             return candidate
        # return os.path.join(self.storage_path, rel_path)

    # ------------------------------------------------------------------
    # Диалог редактирования
    # ------------------------------------------------------------------

    def _open_edit_dialog(self, model, index):
        """
        Открывает диалог редактирования фото.
        Получает текущий путь и описание (если есть) из модели.
        """
        # Ленивый импорт, чтобы избежать циклических зависимостей
        # from interfaces.gui.gui_window.widgets.photo_edit_dialog import PhotoEditDialog
    
        # Получаем относительный путь из модели
        rel_path = model.data(index, Qt.UserRole)
        if rel_path is None:
            rel_path = model.data(index, Qt.DisplayRole)

        if not rel_path or not isinstance(rel_path, str):
            rel_path = ""

        full_path = os.path.join(self.storage_path, rel_path) if rel_path else None
        if full_path and not os.path.exists(full_path):
            full_path = None

        # Получаем описание, если указано поле
        description = ""
        if self._description_field:

            # ВНИМАНИЕ: предполагается, что модель имеет метод get_column_at_visible_index,
            # который возвращает TableColumn по видимому индексу. Это верно для PaginatedTableModel,
            # но может не работать с другими моделями.

            # Ищем индекс столбца описания (по имени поля)
            for col in range(model.columnCount()):
                col_obj = getattr(model, 'get_column_at_visible_index', None)
                if col_obj:
                    column_info = col_obj(col)
                    if column_info and column_info.field_name == self._description_field:
                        desc_index = model.index(index.row(), col)
                        description = model.data(desc_index, Qt.DisplayRole) or ""
                        break
        
        # Получаем ID родителя из DTO
        dto = model.get_item_at_row(index.row()) if hasattr(model, 'get_item_at_row') else None
        parent_id = getattr(dto, 'id', None) if dto else None

        # Получаем временную папку из реестра (если есть)
        # temp_dir = None
        # if self._registry and parent_id is not None and self._entity_type:
        #     temp_key = f"__temp_dir__:{self._entity_type}:{parent_id}"
        #     temp_dir = self._registry.get(temp_key)


        if self._page is None:
            self.logger.error("ImageThumbnailDelegate: нет ссылки на страницу, невозможно создать временную папку")
            return
        
        temp_dir = None
        # if self._registry and parent_id is not None and self._entity_type:
        #     temp_key = f"__temp_dir__:{self._entity_type}:{parent_id}"
        #     temp_dir = self._registry.get(temp_key)
        if self._page and parent_id is not None:
            # Получаем существующую временную папку (если есть)
            temp_dir = self._page._get_temp_dir(parent_id)
            # Если временной папки нет, но строка существующая (id > 0) – создаём через страницу
            if self._page is None:
                self.logger.warning("ImageThumbnailDelegate: нет ссылки на страницу, работа с временными папками невозможна")
                return
            
            if temp_dir is None and parent_id > 0 and self._page:
                temp_dir = self._page._ensure_temp_dir(parent_id)

            # # Если временной папки нет, но строка существующая (id > 0) – создаём
            # if temp_dir is None and parent_id > 0:
            #     # Находим родительскую страницу (таблица -> ... -> PaginatedListPage)
            #     parent_widget = self.parent()
            #     while parent_widget:
            #         if hasattr(parent_widget, '_ensure_temp_dir'):
            #             temp_dir = parent_widget._ensure_temp_dir(parent_id)
            #             break
            #         parent_widget = parent_widget.parent()

        dialog = PhotoEditDialog(
            parent=self.parent(),
            current_path=full_path if full_path and os.path.exists(full_path) else None,
            description=description,
            allowed_extensions=self._allowed_extensions,
            readonly=self._readonly,
            parent_id=parent_id,
            storage_path=self.storage_path,
            mode='single',
            temp_dir=temp_dir,
        )
        if dialog.exec() == QDialog.Accepted:
            new_path, new_description = dialog.get_result()
            if new_path is None and new_description is None:
                # Фото удалено – очищаем поле
                model.setData(index, "", Qt.EditRole)
                if self._description_field:
                    # Найти индекс столбца описания и очистить
                    for col in range(model.columnCount()):
                        col_info = model.get_column_at_visible_index(col) if hasattr(model, 'get_column_at_visible_index') else None
                        if col_info and col_info.field_name == self._description_field:
                            desc_index = model.index(index.row(), col)
                            model.setData(desc_index, "", Qt.EditRole)
                            break
            else:
                # Сохраняем относительный путь (копирование файла выполнит сервис)
                # Пока сохраняем абсолютный путь – при сохранении строки сервис скопирует
                # Для правильного хранения нужно определить целевой относительный путь,
                # но это выходит за рамки делегата. Оставляем как есть – модель сохранит строку.
                # Новое фото
                model.setData(index, new_path, Qt.EditRole)
                if new_description is not None and new_description != description:
                    if self._description_field:
                        for col in range(model.columnCount()):
                            col_info = model.get_column_at_visible_index(col) if hasattr(model, 'get_column_at_visible_index') else None
                            if col_info and col_info.field_name == self._description_field:
                                desc_index = model.index(index.row(), col)
                                model.setData(desc_index, new_description, Qt.EditRole)
                                break
        self._button_rect = None