# interfaces/gui/gui_window/widgets/photo_uploader_widget.py

import os
from typing import List, Set, Tuple, Dict

from app.utils.logger.logger import AppLogger
from app.dto import PhotoDTO

from PySide6.QtCore import QEvent, Signal, Qt, QSize
from PySide6.QtGui import QColor, QPixmap, QFontMetrics, QPainter, QTextOption
from PySide6.QtWidgets import (
    QAbstractItemView, QMessageBox, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QFileDialog, QDialog, QLabel, QScrollArea, QStyledItemDelegate,
    QStyleOptionViewItem, QTextEdit, QApplication
)



class PhotoDelegate(QStyledItemDelegate):
    """
    Делегат для отрисовки масштабированной иконки в ячейке таблицы.
    """

    @AppLogger.get_instance(
        name = 'PhotoDelegate',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def __init__(self, parent, photo_widget):
        super().__init__(parent)
        self.photo_widget = photo_widget

        # логгер
        self.logger = AppLogger.get_instance(
            name=f"gui.PhotoDelegate",
            enable_file_logging='user',
            use_name_in_filename='user',
        )

    @AppLogger.get_instance(
        name = 'PhotoDelegate',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        """
        Переопределяет метод для отрисовки масштабированной иконки в ячейке таблицы.
        
        :param painter: QPainter - объект для отрисовки
        :param option: QStyleOptionViewItem - параметры для отрисовки
        :param index: QModelIndex - индекс элемента в таблице
        """
        full_path = index.data(Qt.UserRole)
        self.logger.debug(f"full_path : {full_path}")
        if not full_path:
            super().paint(painter, option, index)
            return

        pixmap = self.photo_widget._get_pixmap(full_path)

        self.logger.debug(f"pixmap : {pixmap.isNull()}")
        if pixmap.isNull():
            super().paint(painter, option, index)
            return

        rect = option.rect
        scaled_pixmap = pixmap.scaled(rect.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        x = rect.x() + (rect.width() - scaled_pixmap.width()) // 2
        y = rect.y() + (rect.height() - scaled_pixmap.height()) // 2

        self.logger.debug(f"x, y : {x}, {y}")
        painter.drawPixmap(x, y, scaled_pixmap)

    @AppLogger.get_instance(
        name = 'PhotoDelegate',
        enable_file_logging  = 'system',
        use_name_in_filename = 'system',
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
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def __init__(self, parent=None, photo_widget=None):
        super().__init__(parent)
        self.photo_widget = photo_widget  # <-- главное исправление
        self.logger = AppLogger.get_instance(
            name='gui.TextEditDelegate',
            enable_file_logging='user',
            use_name_in_filename='user',
        )
        self.logger.debug("TextEditDelegate инициализирован")

    @AppLogger.get_instance(
        name = 'TextEditDelegate',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
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
        self.logger.debug(f"createEditor: создан QTextEdit для строки {index.row()}")
        return editor

    @AppLogger.get_instance(
        name = 'TextEditDelegate',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
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
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def setModelData(self, editor, model, index):
        """Сохраняет текст из редактора в модель."""
        new_text = editor.toPlainText()
        model.setData(index, new_text, Qt.EditRole)
        self.logger.debug(f"setModelData: сохранён текст '{new_text[:50]}...' для строки {index.row()}")

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
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def updateEditorGeometry(self, editor, option, index):
        """Устанавливает геометрию редактора (растягивается на всю ячейку)."""
        editor.setGeometry(option.rect)

    @AppLogger.get_instance(
        name = 'TextEditDelegate',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
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
    Отображает фото в таблице: столбец 0 – масштабированная иконка,
    столбец 1 – редактируемое описание с поддержкой переноса строк и многострочного редактирования.
    """
    MAX_PHOTOS = 0  # ограничить максимальное количество загружаемых фото в приём. 0 - без ограницений

    photosChanged = Signal()

    @AppLogger.get_instance(
        name = 'PhotoUploaderWidget',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def __init__(self, parent=None):
        """
        Инициализирует виджет для управления фотографиями приёма.

        :param parent: Родительский виджет
        :type parent: QWidget
        """
        super().__init__(parent)

        self.logger = AppLogger.get_instance(
            name='gui.PhotoUploaderWidget',
            enable_file_logging='user',
            use_name_in_filename='user',
        )
        self.logger.debug("Инициализация PhotoUploaderWidget")

        # Данные
        self.pending_photos: List[Tuple[str, str]] = []   # (путь, описание)
        self.existing_photos: List[PhotoDTO] = []         # существующие фото
        self.original_descriptions: Dict[int, str] = {}   # начальные данные из БД
        self.deleted_photo_ids: Set[int] = set()          # ID на удаление
        self.modified_photo_ids: Set[int] = set()         # ID изменённых фото
        
        self._storage_path: str = None                    # базовый путь к хранилищу
        self._image_cache: Dict[str, QPixmap] = {}        # кэш изображений

        self._setup_ui()
        self._adjust_column_widths()


    @AppLogger.get_instance(
        name = 'PhotoUploaderWidget',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def get_existing_photos(self) -> List[PhotoDTO]:
        """Возвращает список существующих фото (актуальные после редактирования описаний)."""
        return self.existing_photos
    
    @AppLogger.get_instance(
        name='PhotoUploaderWidget',
        enable_file_logging='system',
        use_name_in_filename='system',
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
        enable_file_logging='system',
        use_name_in_filename='system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def load_state(self, state: dict) -> None:
        """
        Восстанавливает состояние виджета из словаря, полученного от dump_state.
        Полностью заменяет текущие данные.
        """
        self.logger.debug(f"load_state: pending={state.get('pending_photos')}, existing={state.get('existing_photos')}")
        
        self.clear()

        # Восстанавливаем существующие фото
        self.existing_photos = [PhotoDTO(**p) for p in state['existing_photos']]
        
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
        self._refresh_table()

    @AppLogger.get_instance(
        name='PhotoUploaderWidget',
        enable_file_logging='system',
        use_name_in_filename='system',
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
        name = 'PhotoUploaderWidget',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
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

        # text_delegate = TextEditDelegate(self.table)
        text_delegate = TextEditDelegate(self.table, self)  # <-- передаём self (PhotoUploaderWidget)
        self.table.setItemDelegateForColumn(1, text_delegate)

        # Сигналы
        self.table.itemDoubleClicked.connect(self._on_table_double_clicked)
        self.table.itemChanged.connect(self._on_item_changed)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)

        main_layout.addWidget(self.table)

        # Кнопки
        btn_layout = QHBoxLayout()
        self.add_btn = QPushButton("Добавить фото")
        self.add_btn.clicked.connect(self.add_photo)
        btn_layout.addWidget(self.add_btn)

        self.view_btn = QPushButton("Просмотр")
        self.view_btn.clicked.connect(self._view_photo)
        self.view_btn.setEnabled(False)
        btn_layout.addWidget(self.view_btn)

        self.remove_btn = QPushButton("Удалить выбранное")
        self.remove_btn.clicked.connect(self._remove_selected)
        btn_layout.addWidget(self.remove_btn)

        main_layout.addLayout(btn_layout)

    @AppLogger.get_instance(
        name = 'PhotoUploaderWidget',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
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
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._adjust_column_widths()
        self._adjust_row_heights()

    # ----------------------------------------------------------------------
    # Обработчики событий таблицы
    # ----------------------------------------------------------------------

    @AppLogger.get_instance(
        name = 'PhotoUploaderWidget',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
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

    @AppLogger.get_instance(
        name = 'PhotoUploaderWidget',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
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
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
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
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
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
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
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

        0==0

    # ----------------------------------------------------------------------
    # Действия с фотографиями
    # ----------------------------------------------------------------------

    @AppLogger.get_instance(
        name = 'PhotoUploaderWidget',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def add_photo(self):
        """
        Добавляет одно или несколько новых фото в список pending_photos.
        Открывает диалог выбора файлов с возможностью множественного выбора.

        Открывает файл для добавления с помощью QFileDialog.getOpenFileName.

        Если файл не выбран, то ничего не делается.

        Добавляет путь к файлу и пустое описание в список pending_photos.

        Обновляет таблицу с новым фото.

        Вызывает сигнал photosChanged.

        :return: None
        :rtype: None
        """
        file_paths, _ = QFileDialog.getOpenFileNames(
            self, 
            "Выберите изображение", 
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.gif)"
        )


        if not file_paths:
            return
        
        if (
            len(self.pending_photos) + len(file_paths) > self.MAX_PHOTOS
        ) and (
            self.MAX_PHOTOS > 0
        ):
            QMessageBox.warning(self, "Предупреждение", f"Можно добавить не более {self.MAX_PHOTOS} фото.")
            return
                
        for file_path in file_paths:
            self.pending_photos.append((file_path, ""))
            self.logger.debug(f"Добавлено фото: {file_path}")

        self._refresh_table()
        self.photosChanged.emit() # сигнал : Что-то изменилось в фотографиях этого приём
        self.logger.debug(f"Добавлено {len(file_paths)} фото")

    @AppLogger.get_instance(
        name = 'PhotoUploaderWidget',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
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
            self.logger.debug(f"Помечено на удаление {len(selected_rows)} фото")

        except Exception as e:
            self.logger.exception(f"Ошибка при удалении фото: {e}")
            raise e

    @AppLogger.get_instance(
        name = 'PhotoUploaderWidget',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
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

        if row < len(self.existing_photos):
            photo = self.existing_photos[row]
            if photo.id not in self.deleted_photo_ids:

                # добавляем ID в множество удалённых
                self.deleted_photo_ids.add(photo.id)
            
                # если фото было изменено, убираем из modified (оно всё равно удалится)
                self.modified_photo_ids.discard(photo.id)  # если было изменено, убираем из modified

                # не удаляем из existing_photos, чтобы сохранить возможность отмены
        else:
            # новые фото (pending) – удаляем сразу
            pending_index = row - len(self.existing_photos)
            if pending_index < len(self.pending_photos):
                del self.pending_photos[pending_index]
                self._refresh_table()
                self.logger.debug("Удалено новое фото")


    @AppLogger.get_instance(
        name = 'PhotoUploaderWidget',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
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

        pixmap = self._get_pixmap(full_path)
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
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _refresh_table(self):
        """
        Полностью перестраивает таблицу фото и сбрасывает все цвета.
        Вызывается после set_existing_photos и load_state.
        """
        self.logger.debug(f"_refresh_table: existing={len(self.existing_photos)}, pending={len(self.pending_photos)}")

        total_rows = len(self.existing_photos) + len(self.pending_photos)

        self.table.setRowCount(0)
        self.table.setRowCount(total_rows)
        self.table.setUpdatesEnabled(False)

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

        self._adjust_row_heights()

        self.table.setUpdatesEnabled(True)

        # Максимально агрессивная перерисовка
        self.table.viewport().update()
        self.table.repaint()
        self.table.horizontalHeader().repaint()
        self.table.verticalHeader().repaint()

        self.logger.debug(f"_refresh_table завершена. Строк в таблице: {total_rows}")

    @AppLogger.get_instance(
        name = 'PhotoUploaderWidget',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
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
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _adjust_row_heights(self):
        
        """
        Устанавливает высоту строк таблицы на основе ширины столбца 0.

        Если ширина столбца 0 не определена, то ничего не делается.

        Для каждой строки таблицы берется путь к файлу из столбца 0 и ширина столбца 1.
        Если путь к файлу не определен, то для строки ничего не делается.

        Берется пиксель из файла (если файл существует) и вычисляется соотношение ширины к высоте.
        Если пиксель не может быть загружен, то используется высота 100.

        Вычисляется максимальная высота для строки, учитывая высоту пикселя и высоту текста.
        """
        
        col0_width = self.table.columnWidth(0)
        if col0_width <= 0:
            return

        font = self.table.font()
        metrics = QFontMetrics(font)

        for row in range(self.table.rowCount()):
            item_icon = self.table.item(row, 0)
            full_path = item_icon.data(Qt.UserRole) if item_icon else None
            if not full_path:
                continue

            pixmap = self._get_pixmap(full_path)
            if pixmap.isNull():
                icon_height = 100
            else:
                ratio = pixmap.width() / pixmap.height() if pixmap.height() > 0 else 1.0
                scaled_width = min(col0_width, pixmap.width())
                icon_height = int(scaled_width / ratio) if ratio > 0 else 100
                icon_height = max(icon_height, 1)

            item_text = self.table.item(row, 1)
            text = item_text.text() if item_text else ""

            text_height = 0
            if text:
                text_width = self.table.columnWidth(1) - 10
                if text_width > 0:
                    rect = metrics.boundingRect(0, 0, text_width, 0, Qt.TextWordWrap, text)
                    text_height = rect.height()

            row_height = max(icon_height, text_height) + 10
            self.table.setRowHeight(row, row_height)

    # ----------------------------------------------------------------------
    # Кэширование
    # ----------------------------------------------------------------------

    @AppLogger.get_instance(
        name = 'PhotoUploaderWidget',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
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
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
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
        enable_file_logging='system',
        use_name_in_filename='system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def set_existing_photos(self, photos: List[PhotoDTO]):
        """
        Устанавливает существующие фото из БД после сохранения.
        Полностью очищает все временные состояния и сбрасывает выделение новых фото.
        """
        self.logger.debug(f"set_existing_photos ЗАПУЩЕН. Получено {len(photos) if photos else 0} фото из БД")

        # Полная очистка ВСЕГО состояния виджета
        self.clear()#  полный сброс
        # self.pending_photos.clear()
        # self.deleted_photo_ids.clear()
        # self.modified_photo_ids.clear()
        # self._image_cache.clear()


        # Заполняем новыми данными
        # self.existing_photos = list(photos) if photos else []
        if photos and isinstance(photos[0], dict):
            self.existing_photos = [PhotoDTO(**p) for p in photos]
            self.logger.debug("Фото преобразованы из dict → PhotoDTO")
        else:
            self.existing_photos = list(photos) if photos else []

        # Сохраняем оригинальные описания
        self.original_descriptions.clear()
        for photo in self.existing_photos:
            self.original_descriptions[photo.id] = photo.description or ""

        self._refresh_table()

        # Принудительно сбрасываем цвета всех строк (убираем зелёный)
        for row in range(self.table.rowCount()):
            self._set_row_color(row)

        self.table.viewport().update()      # принудительная перерисовка
        self.table.repaint()

        self.logger.debug(f"set_existing_photos ЗАВЕРШЁН. "
                        f"existing={len(self.existing_photos)}, "
                        f"pending={len(self.pending_photos)}, "
                        f"строк в таблице={self.table.rowCount()}")



    @AppLogger.get_instance(
        name = 'PhotoUploaderWidget',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
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
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
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
        enable_file_logging='system',
        use_name_in_filename='system',
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

        self.table.setRowCount(0)
        self.table.clearContents()

        self.logger.debug("PhotoUploaderWidget полностью очищен")

    @AppLogger.get_instance(
        name = 'PhotoUploaderWidget',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def set_readonly(
        self, 
        readonly: bool = True, # Режим "только просмотр"
    ):
        """
        Устанавливает режим «только просмотр»: отключает кнопки добавления/удаления.
        Если нужно, также можно заблокировать редактирование описаний.
        """

        self.add_btn.setEnabled(not readonly)
        self.remove_btn.setEnabled(not readonly)

        # Если требуется запретить редактирование описаний, можно установить делегату другой режим,
        # но для простоты оставим как есть (пользователь может кликнуть, но изменения не сохранятся,
        # так как в режиме просмотра мы не вызываем _save). Однако можно также отключить редактирование ячеек:
        # self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)

        if readonly:
            self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        else:
            self.table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
            
    # ----------------------------------------------------------------------
    # Вспомогательные методы для цвета строк
    # ----------------------------------------------------------------------

    @AppLogger.get_instance(
        name = 'PhotoUploaderWidget',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
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
                f"""
                if photo.id in self.deleted_photo_ids = {photo.id in self.deleted_photo_ids}
                if photo.id in self.modified_photo_ids = {photo.id in self.modified_photo_ids}"""
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
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
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
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def _update_row_color(self, row: int):
        """Обновляет цвет строки без перестроения таблицы."""
        self._set_row_color(row)