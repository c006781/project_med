# interfaces/gui/gui_window/widgets/photo_uploader_widget.py

import os
from typing import List, Set, Tuple, Dict

from app.utils.logger.logger import AppLogger
from app.dto import PhotoDTO

from PySide6.QtCore import QEvent, Signal, Qt, QSize
from PySide6.QtGui import QColor, QPixmap, QFontMetrics, QPainter, QTextOption
from PySide6.QtWidgets import (
    QAbstractItemView, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
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
    Поддерживает перенос строк, автоматический перенос при наборе и ручной ввод Shift+Enter.
    """

    @AppLogger.get_instance(
        name = 'TextEditDelegate',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def __init__(self, parent=None):
        super().__init__(parent)

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
        editor.setAcceptRichText(False)  # только обычный текст
        editor.setWordWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)  # перенос по словам
        editor.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        # Устанавливаем высоту около 100 пикселей для удобства
        editor.setMinimumHeight(80)
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

    @AppLogger.get_instance(
        name = 'TextEditDelegate',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def setModelData(self, editor, model, index):
        """Сохраняет текст из редактора в модель."""
        model.setData(index, editor.toPlainText(), Qt.EditRole)

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
                    # Shift+Enter: вставляем перенос строки (стандартное поведение QTextEdit)
                    return False  # пусть обрабатывает QTextEdit
                else:
                    # Enter без Shift: завершаем редактирование
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

        text_delegate = TextEditDelegate(self.table)
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
    def _on_item_changed(self, item: QTableWidgetItem):
        """
        Обработчик события изменения элемента таблицы.

        Если изменение произошло в столбце 1 (описание), то обновляет описание фото, если оно существует в БД,
        или обновляет описание нового фото, если оно pending.

        Выводит событие photosChanged, если описание фото было изменено.
        """
        row = item.row()
        column = item.column()
        if column != 1:
            return

        new_text = item.text()
        if row < len(self.existing_photos): # существующие фото
            photo = self.existing_photos[row]
            if photo.description != new_text:
                photo.description = new_text
                self.modified_photo_ids.add(photo.id) # помечаем как изменённое
                self._update_row_color(row)          # перекрасить в жёлтый
                self.photosChanged.emit()
                self.logger.debug(f"Обновлено описание фото ID={photo.id}")
        else:
            pending_index = row - len(self.existing_photos)
            if pending_index < len(self.pending_photos):
                file_path, old_desc = self.pending_photos[pending_index]
                if old_desc != new_text:
                    self.pending_photos[pending_index] = (file_path, new_text)
                    # Для новых фото цвет уже зелёный, не меняем
                    self.photosChanged.emit()
                    self.logger.debug("Обновлено описание нового фото")

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
        Добавляет новое фото в список pending_photos.

        Открывает файл для добавления с помощью QFileDialog.getOpenFileName.

        Если файл не выбран, то ничего не делается.

        Добавляет путь к файлу и пустое описание в список pending_photos.

        Обновляет таблицу с новым фото.

        Вызывает сигнал photosChanged.

        :return: None
        :rtype: None
        """
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Выберите изображение", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.gif)"
        )
        if not file_path:
            return

        self.pending_photos.append((file_path, ""))
        self._refresh_table()
        self.photosChanged.emit()
        self.logger.info(f"Добавлено фото: {file_path}")

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
            self.logger.info(f"Помечено на удаление {len(selected_rows)} фото")

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
        Обновляет таблицу с существующими и новыми фото.

        :return: None
        :rtype: None
        """
        total_rows = len(self.existing_photos) + len(self.pending_photos)
        self.table.setRowCount(total_rows)
        self.table.setUpdatesEnabled(False)

        for i, photo in enumerate(self.existing_photos):
            try:
                self._set_table_row(i, photo.file_path, photo.description or "", is_existing=True)
            except Exception as e:
                self.logger.exception(f'Err: {e}')
                raise e

        for i, (file_path, desc) in enumerate(self.pending_photos):
            row = len(self.existing_photos) + i
            try:
                self._set_table_row(row, file_path, desc, is_existing=False)
            except Exception as e:
                self.logger.exception(f'Err: {e}')
                raise e
        # Устанавливаем цвета для всех строк после заполнения

        for row in range(total_rows):
            try:
                self._set_row_color(row)
            except Exception as e:
                self.logger.exception(f'row: {row}, Err: {e}')
                raise e

        self._adjust_row_heights()
        self.table.setUpdatesEnabled(True)
        self.logger.debug(f"Таблица обновлена: {total_rows} строк")

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
        name = 'PhotoUploaderWidget',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def set_existing_photos(self, photos: List[PhotoDTO]):
        """
        Установка существующих фото.

        :param photos: Список существующих фото (PhotoDTO)
        :type photos: List[PhotoDTO]
        """
        self.logger.debug(f"set_existing_photos: photos type = {type(photos)}")
        if photos:
            self.logger.debug(f"  первый элемент: {type(photos[0])}")

        self.logger.debug(f"set_existing_photos: photos type = {type(photos)}")
        # self.existing_photos = photos # Список существующих фото

        if photos and isinstance(photos[0], dict):
            # from app.dto import PhotoDTO
            self.logger.debug("Обнаружены словари, преобразуем в PhotoDTO")
            self.existing_photos = [PhotoDTO(**p) for p in photos]
            self.logger.debug("Преобразование завершено")
        else:
            self.logger.debug("Список уже в нужном формате, используем как есть")
            self.existing_photos = photos


        self.deleted_photo_ids.clear()

        self.modified_photo_ids.clear() 

        self._refresh_table() # Обновление таблицы

        self.logger.debug(f"Установлено {len(photos)} существующих фото")

    @AppLogger.get_instance(
        name = 'PhotoUploaderWidget',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
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
        level = AppLogger._parse_log_level(
            # 'INFO'
            'DEBUG'
        )
    )
    def get_deleted_photo_ids(self) -> List[int]:
        """
        Возвращает список ID фото, помеченных на удаление.

        :return: Список ID фото, помеченных на удаление
        :rtype: List[int]
        """
        return list(self.deleted_photo_ids)

    @AppLogger.get_instance(
        name = 'PhotoUploaderWidget',
        enable_file_logging = 'system',
        use_name_in_filename = 'system',
    ).log_execution_time(
        level = AppLogger._parse_log_level('DEBUG')
    )
    def clear(self):
        """
        Очищает виджет, удаляя все данные (новые фото, существующие фото, ID на удаление, ID изменённых фото).
        """
        self.pending_photos.clear()
        self.existing_photos.clear()
        self.deleted_photo_ids.clear()
        self.modified_photo_ids.clear()
        self._image_cache.clear()

        self.table.setRowCount(0) # Очистка таблицы
        self.logger.debug("Виджет очищен")

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
        if row < len(self.existing_photos):
            photo = self.existing_photos[row]

            if photo.id in self.deleted_photo_ids:
                return 'deleted'
            
            if photo.id in self.modified_photo_ids:
                return 'modified'
            
            return 'normal'
        
        else:
            # Новые фото (pending)
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
        Устанавливает цвет фона для всей строки на основе состояния.

        Состояние строки может быть одним из следующих:
        - 'new': светло-зелёный (новое фото)
        - 'modified': светло-жёлтый (изменённое фото)
        - 'deleted': светло-красный (фото на удаление)
        - 'normal': белый (не изменённое фото)

        :param row: Номер строки
        :type row: int
        """
        try:
            state = self._get_row_state(row)
        except Exception as e:
            self.logger.exception(f'Err: {e}')
            raise e

        color = None
        if state == 'new':
            color = QColor(200, 255, 200)  # светло-зелёный
        elif state == 'modified':
            color = QColor(255, 255, 180)  # светло-жёлтый
        elif state == 'deleted':
            color = QColor(255, 200, 200)  # светло-красный
        else:
            color = QColor(255, 255, 255)  # белый
            pass

        for col in range(self.table.columnCount()):
            item = self.table.item(row, col) # получаем ячейку
            if item:
                item.setBackground(color)

        # Принудительная перерисовка
        self.table.viewport().update

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