# interfaces/gui/gui_window/widgets/photo_edit_dialog.py
"""
Диалог для просмотра и редактирования фотографии.

Поддерживает два режима:
    - 'single' (по умолчанию): редактирование одного фото (просмотр, выбор нового файла,
      удаление, редактирование описания). Файл копируется во временную папку (если передан
      temp_dir) или сразу в основное хранилище (если известен parent_id).
    - 'multi': выбор нескольких файлов (без превью) – возвращает список путей.

Атрибуты:
    _mode (str): 'single' или 'multi'.
    _current_path (Optional[str]): Текущий путь к файлу (относительный или абсолютный).
    _description (str): Текущее описание фото.
    _allowed_extensions (List[str]): Разрешённые расширения.
    _readonly (bool): Режим "только просмотр".
    _parent_id (Optional[int]): ID родительской сущности (для копирования файла).
    _storage_path (str): Базовый путь к хранилищу фотографий.
    _temp_dir (Optional[str]): Временная папка для черновика (если задана).
    _new_path (Optional[str]): Новый путь (после выбора файла, для single-режима).
    _selected_files (List[str]): Список выбранных файлов (для multi-режима).

Args:
    parent (QWidget, optional): Родительский виджет.
    current_path (Optional[str]): Текущий путь (может быть None).
    description (str): Описание.
    allowed_extensions (List[str], optional): Список разрешённых расширений.
    readonly (bool): Режим только просмотра.
    parent_id (Optional[int]): ID родительской сущности (для копирования в основное хранилище).
    storage_path (str): Базовый путь к хранилищу.
    mode (str): 'single' или 'multi'.
    temp_dir (Optional[str]): Временная папка для черновика (если есть).
"""

import os
import shutil
from typing import List, Optional, Tuple
import uuid

from app.utils.logger.logger import AppLogger

from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QListWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QMessageBox, QTextEdit, QScrollArea
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap



class PhotoEditDialog(QDialog):
    """
    Диалог для просмотра и редактирования фотографии.

    Поддерживает два режима:
        - 'single' (по умолчанию): редактирование одного фото (просмотр, выбор нового файла,
          удаление, редактирование описания). Файл копируется во временную папку (если передан
          temp_dir) или сразу в основное хранилище (если известен parent_id).
        - 'multi': выбор нескольких файлов (без превью) – возвращает список путей.

    Атрибуты:
        _mode (str): 'single' или 'multi'.
        _current_path (Optional[str]): Текущий путь к файлу (относительный или абсолютный).
        _description (str): Текущее описание фото.
        _allowed_extensions (List[str]): Разрешённые расширения.
        _readonly (bool): Режим "только просмотр".
        _parent_id (Optional[int]): ID родительской сущности (для копирования файла).
        _storage_path (str): Базовый путь к хранилищу фотографий.
        _temp_dir (Optional[str]): Временная папка для черновика (если задана).
        _new_path (Optional[str]): Новый путь (после выбора файла, для single-режима).
        _selected_files (List[str]): Список выбранных файлов (для multi-режима).

    Args:
        parent (QWidget, optional): Родительский виджет.
        current_path (Optional[str]): Текущий путь (может быть None).
        description (str): Описание.
        allowed_extensions (List[str], optional): Список разрешённых расширений.
        readonly (bool): Режим только просмотра.
        parent_id (Optional[int]): ID родительской сущности (для копирования в основное хранилище).
        storage_path (str): Базовый путь к хранилищу.
        mode (str): 'single' или 'multi'.
        temp_dir (Optional[str]): Временная папка для черновика (если есть).

    Примечание:
        Для режима 'single' обязательно должен быть передан либо parent_id (при сохранении
        существующей строки), либо temp_dir (при работе с черновиком новой строки).
        В противном случае копирование файла вызовет исключение.
    """

    # ------------------------------------------------------------------
    # Ленивая инициализация атрибутов (без __init__)
    # ------------------------------------------------------------------

    @property
    def logger(self) -> AppLogger:
        try:
            return self._logger
        except AttributeError as e:
            self._logger = AppLogger.get_instance(
                name='gui.PhotoEditDialog',
                enable_file_logging = 'user',
                use_name_in_filename = False, # 'system'
            )

        return self._logger

    @logger.setter
    def logger(self, value):
        self._logger = value

    @AppLogger.get_instance(
        name='PhotoEditDialog',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def __init__(
        self, 
        parent=None, 
        current_path: Optional[str] = None,
        description: str = "", 
        allowed_extensions: List[str] = None,
        readonly: bool = False,
        parent_id: Optional[int] = None,
        storage_path: str = "",
        mode: str = 'single',
        temp_dir: Optional[str] = None,
    ):
        """
        Инициализирует диалог.

        Args:
            parent: Родительский виджет.
            current_path: Абсолютный путь к текущему файлу (может быть None).
            description: Текущее описание фото.
            allowed_extensions: Список разрешённых расширений (по умолчанию стандартные).
            readonly: Режим "только просмотр" (запрещает изменения).
            parent_id: ID родительской сущности (для копирования файла).
            storage_path: Базовый путь к хранилищу фотографий.
            mode: Режим работы – 'single' (одно фото) или 'multi' (несколько файлов).
        """
        super().__init__(parent)

        # self.logger = AppLogger.get_instance('gui.PhotoEditDialog')
        self._mode = mode

        self._temp_dir = temp_dir

        # self.setWindowTitle("Редактирование фото")
        self.setWindowTitle("Редактирование фото" if self._mode == 'single' else "Выбор нескольких фото")
        self.resize(600, 500)

        self._current_path = current_path
        self._description = description
        self._allowed_extensions = allowed_extensions or ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff']
        self._readonly = readonly
        self._parent_id = parent_id          # ID родителя (существующей сущности) или None
        self._storage_path = storage_path    # базовый путь к хранилищу
        self._new_path = None
        self._new_description = None

        self._selected_files = []   # для multi-режима

        self._setup_ui()
        if self._mode == 'single':
            self._load_photo()

    @AppLogger.get_instance(
        name='PhotoEditDialog',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _get_full_path(self, rel_path: str) -> Optional[str]:
        """
        Возвращает полный путь к файлу, сначала проверяя временную папку.

        Если передан относительный путь, ищет файл во временной папке черновика (`self._temp_dir`),
        затем в основном хранилище (`self._storage_path`). Если путь абсолютный, проверяет его
        существование и возвращает его же (или None, если файл не существует).

        Args:
            rel_path (str): Относительный путь к файлу (или имя файла) или абсолютный путь.

        Returns:
            Optional[str]: Абсолютный путь к существующему файлу, или None, если файл не найден.
        """
                
        if not rel_path:
            return None
        
        if os.path.isabs(rel_path):
            return rel_path if os.path.exists(rel_path) else None
        
        # Относительный путь – ищем во временной папке, потом в основной
        if self._temp_dir:
            cand = os.path.join(self._temp_dir, rel_path)
            if os.path.exists(cand):
                return cand
            
        if self._storage_path:
            cand = os.path.join(self._storage_path, rel_path)
            if os.path.exists(cand):
                return cand
            
        return None
    
    # ------------------------------------------------------------------
    # Копирование файла в хранилище (для single-режима)
    # ------------------------------------------------------------------

    @AppLogger.get_instance(
        name='PhotoEditDialog',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _copy_file_to_storage(self, source_path: str) -> str:
        """
        Копирует файл в хранилище или временную папку в зависимости от наличия temp_dir.

        Если задан `self._temp_dir` – копирует во временную папку, возвращает просто имя файла.
        Иначе копирует в основное хранилище (в подпапку `app_{parent_id}`) и возвращает
        относительный путь относительно `self._storage_path`.

        Args:
            source_path (str): Абсолютный путь к исходному файлу.

        Returns:
            str: Имя файла (если копировали во временную папку) или относительный путь.
        
        Raises:
            RuntimeError: Если для новой строки (parent_id <= 0) не передана временная папка,
                или для существующей строки не задан storage_path.
        """
        if self._parent_id is None or self._parent_id <= 0:
            if not self._temp_dir:
                raise RuntimeError(
                    "Для новой строки (parent_id <= 0) должна быть передана временная папка (temp_dir)."
                )
            
            # Временная папка черновика
            os.makedirs(self._temp_dir, exist_ok=True)
            ext = os.path.splitext(source_path)[1]

            unique_name = f"{uuid.uuid4().hex}{ext}"
            dest_path = os.path.join(self._temp_dir, unique_name)

            shutil.copy2(source_path, dest_path)

            # Возвращаем просто имя файла (относительно temp_dir)
            return unique_name
        
        # Существующая строка (parent_id > 0) – копируем в основное хранилище
        if not self._storage_path:
            raise RuntimeError("Не задан путь к хранилищу фото (storage_path).")
        
        # Прямое копирование в основное хранилище (для уже сохранённых строк)
        if not self._storage_path or self._parent_id is None or self._parent_id <= 0:
            # Для новых строк или без родителя не копируем – вернём абсолютный путь
            return source_path

        # Создаём подпапку для родителя
        parent_folder = os.path.join(self._storage_path, f"app_{self._parent_id}")
        os.makedirs(parent_folder, exist_ok=True)

        # import uuid
        # Генерируем уникальное имя файла
        ext = os.path.splitext(source_path)[1]
        unique_name = f"{uuid.uuid4().hex}{ext}"
        dest_path = os.path.join(parent_folder, unique_name)

        # import shutil
        # Копируем файл
        shutil.copy2(source_path, dest_path)

        # Возвращаем относительный путь
        rel_path = os.path.relpath(dest_path, self._storage_path)

        return rel_path

    @AppLogger.get_instance(
        name='PhotoEditDialog',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _add_files_multi(self):
        """
        Добавляет файлы в список для множественного выбора через стандартный диалог.

        Открывает QFileDialog с множественным выбором, фильтрует файлы по разрешённым
        расширениям (`self._allowed_extensions`) и добавляет каждый путь в `self.list_widget`.
        В режиме `readonly` кнопка вызова этого метода отключена, поэтому дополнительная
        проверка не требуется.

        Args:
            None

        Returns:
            None
        """

        files, _ = QFileDialog.getOpenFileNames(
            self, 
            "Выберите изображения", 
            "",
            f"Изображения (*{' *'.join(self._allowed_extensions)})"
        )

        for f in files:
            self.list_widget.addItem(f)

    @AppLogger.get_instance(
        name='PhotoEditDialog',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def dragEnterEvent(self, event):
        """
        Обрабатывает событие входа перетаскиваемых данных в область диалога.

        Если перетаскиваемые данные содержат URL-адреса (файлы), принимает действие.
        Это позволяет отобразить курсор-подсказку, что сброс файлов разрешён.

        Args:
            event (QDragEnterEvent): Событие перетаскивания.

        Returns:
            None
        """

        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    @AppLogger.get_instance(
        name='PhotoEditDialog',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def dropEvent(self, event):
        """
        Обрабатывает событие сброса файлов в область диалога.

        Извлекает URL-адреса из события, преобразует каждый в локальный путь к файлу,
        проверяет расширение на соответствие `self._allowed_extensions` и добавляет
        допустимые файлы в `self.list_widget`. Невалидные файлы игнорируются.

        Примечание:
            В режиме `readonly` диалог не принимает сброс файлов (setAcceptDrops(False)),
            поэтому этот метод не будет вызван.

        Args:
            event (QDropEvent): Событие сброса.

        Returns:
            None
        """
            
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path and os.path.splitext(path)[1].lower() in self._allowed_extensions:
                self.list_widget.addItem(path)

        event.acceptProposedAction()

    @AppLogger.get_instance(
        name='PhotoEditDialog',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def get_selected_files(self) -> List[str]:
        """
        Возвращает список выбранных файлов в зависимости от режима диалога.

        Для режима 'multi' возвращает пути всех файлов, отображаемых в `self.list_widget`.
        Для режима 'single' возвращает список с одним элементом – новым путём к файлу
        (если он был выбран), либо пустой список.

        Returns:
            List[str]: Список абсолютных путей к выбранным файлам.
                Для 'multi' – все файлы в списке.
                Для 'single' – [new_path] или [].
        """
            
        if self._mode == 'multi':
            return [self.list_widget.item(i).text() for i in range(self.list_widget.count())]
        else:
            return [self._new_path] if self._new_path else []

    # ------------------------------------------------------------------
    # Построение UI в зависимости от режима
    # ------------------------------------------------------------------

    @AppLogger.get_instance(
        name='PhotoEditDialog',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _setup_ui(self):
        """
        Вызывает соответствующий метод построения UI в зависимости от режима.

        Если режим 'multi', вызывает `_setup_multi_ui()`, иначе – `_setup_single_ui()`.

        Args:
            None

        Returns:
            None
        """

        if self._mode == 'multi':
            self._setup_multi_ui()
        else:
            self._setup_single_ui()

    @AppLogger.get_instance(
        name='PhotoEditDialog',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _setup_single_ui(self):
        """
        Создаёт интерфейс для режима редактирования одного фото.

        Виджеты:
            - Область предпросмотра (QLabel)
            - Кнопка «Выбрать файл» – открывает диалог выбора одного файла
            - Кнопка «Удалить фото» – удаляет текущее фото
            - Поле для редактирования описания (QTextEdit)
            - Кнопки OK / Cancel

        Примечание:
            Кнопки выбора и удаления, а также поле описания отключаются,
            если диалог находится в режиме только просмотра (self._readonly = True).

        Returns:
            None
        """

        layout = QVBoxLayout(self)

        # Область для превью
        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumHeight(300)
        self.preview_label.setStyleSheet("border: 1px solid gray; background-color: #f0f0f0;")
        layout.addWidget(self.preview_label)

        # Кнопки выбора файла и удаления
        btn_layout = QHBoxLayout()
        self.select_btn = QPushButton("Выбрать файл")
        self.select_btn.clicked.connect(self._select_file)
        self.select_btn.setEnabled(not self._readonly)
        btn_layout.addWidget(self.select_btn)

        self.delete_btn = QPushButton("Удалить фото")
        self.delete_btn.clicked.connect(self._delete_photo)
        self.delete_btn.setEnabled(not self._readonly and self._current_path is not None)
        btn_layout.addWidget(self.delete_btn)
        layout.addLayout(btn_layout)

        # Поле для описания
        self.desc_label = QLabel("Описание:")
        layout.addWidget(self.desc_label)
        self.desc_edit = QTextEdit()
        self.desc_edit.setPlainText(self._description)
        self.desc_edit.setReadOnly(self._readonly)
        self.desc_edit.setMaximumHeight(100)
        layout.addWidget(self.desc_edit)

        # Кнопки OK/Cancel
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    @AppLogger.get_instance(
        name='PhotoEditDialog',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _setup_multi_ui(self):
        """
        Создаёт интерфейс для режима множественного выбора файлов.

        Виджеты:
            - QListWidget для отображения выбранных файлов
            - Кнопка «Добавить файлы» – открывает диалог выбора нескольких файлов
            - Кнопка «Очистить» – удаляет все файлы из списка
            - Кнопки OK / Cancel

        Drag-and-drop:
            Пользователь может перетащить файлы из проводника в список.
            Допустимые расширения определяются self._allowed_extensions.

        Примечание:
            Все виджеты отключаются, если диалог в режиме только просмотра.

        Returns:
            None
        """
            
        layout = QVBoxLayout(self)

        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QListWidget.ExtendedSelection)
        layout.addWidget(self.list_widget)

        btn_layout = QHBoxLayout()
        add_btn = QPushButton("Добавить файлы")
        add_btn.clicked.connect(self._add_files_multi)
        clear_btn = QPushButton("Очистить")
        clear_btn.clicked.connect(self.list_widget.clear)
        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(clear_btn)
        layout.addLayout(btn_layout)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)


        add_btn.setEnabled(not self._readonly)
        clear_btn.setEnabled(not self._readonly)
        self.list_widget.setEnabled(not self._readonly)

        # Отключаем drag-and-drop в режиме только для чтения
        self.setAcceptDrops(not self._readonly)

        # self.setAcceptDrops(True)

    @AppLogger.get_instance(
        name='PhotoEditDialog',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _load_photo(self):
        """
        Загружает текущее фото (self._current_path) в область предпросмотра.

        Алгоритм:
            1. Получает полный путь через _get_full_path(self._current_path).
            2. Если файл существует и является изображением – масштабирует его
            до размеров self.preview_label с сохранением пропорций.
            3. Если файл не существует или не может быть загружен – отображает
            текст «Нет фото».

        Примечание:
            Метод вызывается только в режиме 'single' (в конструкторе после _setup_ui).

        Returns:
            None
        """

        full_path = self._get_full_path(self._current_path)
        if full_path:
            pixmap = QPixmap(full_path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(self.preview_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.preview_label.setPixmap(scaled)
                return
            
        self.preview_label.setText("Нет фото")

        # if self._current_path and os.path.exists(self._current_path):
        #     pixmap = QPixmap(self._current_path)
        #     if not pixmap.isNull():
        #         scaled = pixmap.scaled(self.preview_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        #         self.preview_label.setPixmap(scaled)
        #         return
        # self.preview_label.setText("Нет фото")

    @AppLogger.get_instance(
        name='PhotoEditDialog',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _select_file(self):
        """
        Удаляет текущее фото (режим 'single').

        Алгоритм:
            1. Если self._current_path является относительным путём (не абсолютным),
            пытается удалить физический файл:
                - сначала ищет во временной папке (self._temp_dir)
                - затем в основном хранилище (self._storage_path)
            2. Устанавливает self._current_path = None, self._new_path = None.
            3. Очищает preview_label (показывает «Нет фото»).
            4. Отключает кнопку удаления.

        Примечание:
            Файл удаляется немедленно, черновики должны быть обновлены вызывающим кодом.
            В режиме только просмотра кнопка удаления недоступна.

        Returns:
            None
        """

        file_path, _ = QFileDialog.getOpenFileName(
            self, "Выберите изображение", "",
            f"Изображения (*{' *'.join(self._allowed_extensions)})"
        )
        if not file_path:
            return

        ext = os.path.splitext(file_path)[1].lower()
        if ext not in self._allowed_extensions:
            QMessageBox.warning(
                self, 
                "Ошибка",
                f"Недопустимый формат файла.\nРазрешены: {', '.join(self._allowed_extensions)}"
            )
            return

        # Загружаем preview
        pixmap = QPixmap(file_path)
        if pixmap.isNull():
            QMessageBox.warning(self, "Ошибка", "Не удалось загрузить изображение")
            return

        scaled = pixmap.scaled(self.preview_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.preview_label.setPixmap(scaled)
        self._new_path = self._copy_file_to_storage(file_path)

        # Обновляем текущий путь для корректной работы при повторном открытии диалога
        self._current_path = self._new_path
        self.delete_btn.setEnabled(True)

    @AppLogger.get_instance(
        name='PhotoEditDialog',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def _delete_photo(self):
        """Удаляет текущее фото из хранилища (если путь относительный)."""

        self.logger.debug(f"_delete_photo: current_path={self._current_path}")
        if self._current_path and not os.path.isabs(self._current_path):
            # Сначала ищем во временной папке
            if self._temp_dir:
                full_path = os.path.join(self._temp_dir, self._current_path)
            else:
                full_path = os.path.join(self._storage_path, self._current_path)

            if os.path.exists(full_path):
                try:
                    os.remove(full_path)
                    self.logger.debug(f"Удалён файл {full_path}")
                except OSError as e:
                    self.logger.warning(f"Не удалось удалить файл {full_path}: {e}")

        self._current_path = None
        self._new_path = None
        self.preview_label.setText("Нет фото")
        self.delete_btn.setEnabled(False)
    
    @AppLogger.get_instance(
        name='PhotoEditDialog',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def get_result(self) -> Tuple[Optional[str], Optional[str]]:
        """
        Возвращает результат редактирования после закрытия диалога.

        Возвращает:
            Tuple[Optional[str], Optional[str]]: (новый_путь_к_файлу, новое_описание)

            Правила возврата:
                - Если в режиме 'single' было выбрано новое фото: (new_path, new_description)
                - Если текущее фото было удалено: (None, None)
                - Если изменений не было: (None, None)
                - В режиме 'multi' следует использовать get_selected_files().

        Примечание:
            Для режима 'single' new_path может быть относительным (если копировали
            во временную папку) или абсолютным (если копировали в основное хранилище).
            Вызывающий код должен обработать путь в соответствии с контекстом.

        Пример:
            >>> new_path, new_desc = dialog.get_result()
            >>> if new_path is None:
            ...     # фото удалено
            ... elif new_path is not None:
            ...     # фото изменено
        """

        new_desc = self.desc_edit.toPlainText()

        if self._new_path is not None:
            return self._new_path, new_desc
        
        if self._current_path is None:
            return None, None
        
        if new_desc != self._description:
            return self._current_path, new_desc
        
        return None, None

    @AppLogger.get_instance(
        name='PhotoEditDialog',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system'
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    def accept(self):
        """
        Переопределяет QDialog.accept для сохранения результата перед закрытием.

        Алгоритм:
            1. Сохраняет текущий текст описания в self._new_description.
            2. Вызывает родительский QDialog.accept().

        Примечание:
            Это необходимо, потому что в момент закрытия диалога виджеты
            могут быть уже уничтожены, и get_result() не сможет получить
            значение из self.desc_edit. Сохранение в self._new_description
            гарантирует, что данные доступны после accept().

        Returns:
            None
        """
            
        self._new_description = self.desc_edit.toPlainText()
        super().accept()