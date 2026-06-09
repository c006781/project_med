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
from app.utils.file_deletions import resolve_photo_path, schedule_deletion

from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QListWidget,
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QMessageBox, QTextEdit,
    # QScrollArea
)
from PySide6.QtCore import (
    Qt,
    # Signal
)
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


    @property
    def MAX_FILES(self) -> int:
        try:
            return self._MAX_FILES
        except AttributeError as e:
            self._MAX_FILES:int = 20

        return self._MAX_FILES

    @MAX_FILES.setter
    def MAX_FILES(self, value:int):
        self._MAX_FILES:int = value

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
        # description: str = "", 
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
            # description: Текущее описание фото.
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
        # self._description = description
        self._allowed_extensions = allowed_extensions or ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff']
        self._readonly = readonly
        self._parent_id = parent_id          # ID родителя (существующей сущности) или None
        self._storage_path = storage_path    # базовый путь к хранилищу
        
        self._new_path = current_path  # None
        # self._new_description = description  # None

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
    def reject(self) -> None:
        """
        Переопределяет reject для очистки временного файла при отмене.

        Если был создан временный файл (self._new_path) и существует временная папка,
        удаляет файл через `schedule_deletion` (немедленно, так как ctx=None).
        Также удаляет временную папку, если она стала пустой.
        """
        if self._new_path and self._temp_dir:
            full_path = os.path.join(self._temp_dir, self._new_path)

            schedule_deletion(
                path=full_path,
                ctx=None,
                remove_parent_if_empty=False,
                force=False,
                logger=self.logger
            )
        
            # if os.path.exists(full_path):
            #     try:
            #         os.remove(full_path)
            #         self.logger.debug(f"Удалён временный файл {full_path} при отмене")
            #     except OSError as e:
            #         self.logger.warning(f"Не удалось удалить временный файл {full_path}: {e}")
            
            self._new_path = None
            self._current_path = None   # так как удалённый файл больше не актуален

        # Если диалог был открыт без изменений (не было выбрано новое фото)
        # и временная папка существует и пуста – удаляем её
        if self._temp_dir and not self._new_path and os.path.exists(self._temp_dir):
            if not os.listdir(self._temp_dir):
                schedule_deletion(
                    path=self._temp_dir,
                    ctx=None,
                    remove_parent_if_empty=False,
                    force=False,
                    logger=self.logger
                )

        super().reject()

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
        return resolve_photo_path(
            rel_path=rel_path,
            temp_dir=self._temp_dir,
            storage_path=self._storage_path,
        )        
        # if not rel_path:
        #     return None
        
        # if os.path.isabs(rel_path):
        #     return rel_path if os.path.exists(rel_path) else None
        
        # # # Относительный путь – ищем во временной папке, потом в основной
        # # if self._temp_dir:
        # #     cand = os.path.join(self._temp_dir, rel_path)
        # #     if os.path.exists(cand):
        # #         return cand
            
        # # if self._storage_path:
        # #     cand = os.path.join(self._storage_path, rel_path)
        # #     if os.path.exists(cand):
        # #         return cand

        # # Если rel_path уже содержит self._storage_path как префикс – не дублируем
        # if self._storage_path and rel_path.startswith(self._storage_path):
        #     cand = rel_path
        # else:
        #     cand = os.path.join(self._storage_path, rel_path) if self._storage_path else rel_path
        
        # if os.path.exists(cand):
        #     return cand
        
        # # Проверка во временной папке (если есть)
        # if self._temp_dir:
        #     # Пробуем соединить как есть
        #     cand2 = os.path.join(self._temp_dir, rel_path)
        #     if os.path.exists(cand2):
        #         return cand2
            
        #     # Если rel_path содержит вложенные папки, пробуем взять только имя файла
        #     base = os.path.basename(rel_path)
        #     cand3 = os.path.join(self._temp_dir, base)
        #     if os.path.exists(cand3):
        #         return cand3
            
        # return None
    
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
        Копирует файл во временную папку черновика (self._temp_dir).

        Всегда предполагает, что временная папка передана при создании диалога.
        Возвращает просто имя файла (без пути).

        **Назначение:**
            Используется в режиме 'single' для копирования выбранного пользователем файла
            во временную папку, связанную с родительской сущностью. Возвращает только имя
            файла (без пути), которое затем сохраняется в DTO.

        **Требования:**
            - `self._temp_dir` должна быть установлена до вызова (обычно в конструкторе).
            - Если `self._temp_dir` не задана, выбрасывается `RuntimeError`.

        Args:
            source_path (str): Абсолютный путь к исходному файлу.

        Returns:
            str: Уникальное имя файла во временной папке (например, "a1b2c3d4.jpg").

        Raises:
            RuntimeError: Если `self._temp_dir` не задана.
            PhotoFileError: При ошибках копирования (пробрасывается из `shutil.copy2`).

        Пример:
            >>> dialog = PhotoEditDialog(..., temp_dir="/tmp/med_app_draft_...")
            >>> name = dialog._copy_file_to_storage("/home/user/photo.jpg")
            >>> print(name)  # "a1b2c3d4.jpg"
        """

        if not self._temp_dir:
            raise RuntimeError(
                "Для копирования файла необходима временная папка (temp_dir). "
                "Убедитесь, что диалог получил temp_dir из делегата."
            )
        
        os.makedirs(self._temp_dir, exist_ok=True)
        ext = os.path.splitext(source_path)[1]
        unique_name = f"{uuid.uuid4().hex}{ext}"
        dest_path = os.path.join(self._temp_dir, unique_name)
        shutil.copy2(source_path, dest_path)

        return unique_name
    
        # """
        # Копирует файл в хранилище или временную папку в зависимости от наличия temp_dir.

        # Если задан `self._temp_dir` – копирует во временную папку, возвращает просто имя файла.
        # Иначе копирует в основное хранилище (в подпапку `app_{parent_id}`) и возвращает
        # относительный путь относительно `self._storage_path`.

        # Args:
        #     source_path (str): Абсолютный путь к исходному файлу.

        # Returns:
        #     str: Имя файла (если копировали во временную папку) или относительный путь.
        
        # Raises:
        #     RuntimeError: Если для новой строки (parent_id <= 0) не передана временная папка,
        #         или для существующей строки не задан storage_path.
        # """
        # if self._parent_id is None or self._parent_id <= 0:
        #     if not self._temp_dir:
        #         raise RuntimeError(
        #             "Для новой строки (parent_id <= 0) должна быть передана временная папка (temp_dir)."
        #         )
            
        #     # Временная папка черновика
        #     os.makedirs(self._temp_dir, exist_ok=True)
        #     ext = os.path.splitext(source_path)[1]

        #     unique_name = f"{uuid.uuid4().hex}{ext}"
        #     dest_path = os.path.join(self._temp_dir, unique_name)

        #     shutil.copy2(source_path, dest_path)

        #     # Возвращаем просто имя файла (относительно temp_dir)
        #     return unique_name
        
        # # Существующая строка (parent_id > 0) – копируем в основное хранилище
        # if not self._storage_path:
        #     raise RuntimeError("Не задан путь к хранилищу фото (storage_path).")
        
        # # Прямое копирование в основное хранилище (для уже сохранённых строк)
        # if not self._storage_path or self._parent_id is None or self._parent_id <= 0:
        #     # Для новых строк или без родителя не копируем – вернём абсолютный путь
        #     return source_path

        # # Создаём подпапку для родителя
        # parent_folder = os.path.join(self._storage_path, f"app_{self._parent_id}")
        # os.makedirs(parent_folder, exist_ok=True)

        # # import uuid
        # # Генерируем уникальное имя файла
        # ext = os.path.splitext(source_path)[1]
        # unique_name = f"{uuid.uuid4().hex}{ext}"
        # dest_path = os.path.join(parent_folder, unique_name)

        # # import shutil
        # # Копируем файл
        # shutil.copy2(source_path, dest_path)

        # # Возвращаем относительный путь
        # rel_path = os.path.relpath(dest_path, self._storage_path)

        # return rel_path

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

        Ограничивает количество выбираемых файлов (не более MAX_FILES).

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


        if len(files) > self.MAX_FILES:
            QMessageBox.warning(
                self,
                "Слишком много файлов",
                f"Выбрано {len(files)} файлов, но допустимо не более {self.MAX_FILES}.\n"
                "Добавлено только {self.MAX_FILES} файлов."
            )
            files = files[:self.MAX_FILES]


        added = 0
        for f in files:
            # self.list_widget.addItem(f)
            ext = os.path.splitext(f)[1].lower()
            if ext not in self._allowed_extensions:
                self.logger.warning(f"Файл {f} имеет недопустимое расширение {ext}, пропущен")
                continue

            self.list_widget.addItem(f)
            added += 1

  
        if added == 0 and files:
            QMessageBox.warning(self, "Ошибка", "Ни один из выбранных файлов не имеет допустимого расширения.")


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

        # # Поле для описания
        # self.desc_label = QLabel("Описание:")
        # layout.addWidget(self.desc_label)
        # self.desc_edit = QTextEdit()
        # self.desc_edit.setPlainText(self._description)
        # self.desc_edit.setReadOnly(self._readonly)
        # self.desc_edit.setMaximumHeight(100)
        # layout.addWidget(self.desc_edit)

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

        # Удаляем предыдущий временный файл, если он был
        if self._new_path and self._temp_dir:
            old_full = os.path.join(self._temp_dir, self._new_path)
            schedule_deletion(
                path=old_full,
                ctx=None,
                remove_parent_if_empty=False,
                force=False,
                logger=self.logger
            )
            # if os.path.exists(old_full):
            #     try:
            #         os.remove(old_full)
            #         self.logger.debug(f"Удалён предыдущий временный файл {old_full} при выборе нового")
            #     except OSError as e:
            #         self.logger.warning(f"Не удалось удалить предыдущий файл {old_full}: {e}")

        # Загружаем preview
        pixmap = QPixmap(file_path)
        if pixmap.isNull():
            QMessageBox.warning(self, "Ошибка", "Не удалось загрузить изображение")
            return

        scaled = pixmap.scaled(self.preview_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.preview_label.setPixmap(scaled)
        self._new_path = self._copy_file_to_storage(file_path)

        # Обновляем текущий путь для корректной работы при повторном открытии диалога
        self._current_path = self._new_path  # синхронизируем
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
        """
        Удаляет текущее фото из временной папки или хранилища.
        Если был выбран новый файл (self._new_path), удаляет и его.
        """

        self.logger.debug(f"_delete_photo: current_path={self._current_path}")

        # Удаляем старый текущий файл (если есть)
        if self._current_path and not os.path.isabs(self._current_path):
            # Сначала ищем во временной папке
            if self._temp_dir:
                full_path = os.path.join(self._temp_dir, self._current_path)
            else:
                full_path = os.path.join(self._storage_path, self._current_path)

            schedule_deletion(
                path=full_path,
                ctx=None,
                remove_parent_if_empty=False,
                force=False,
                logger=self.logger
            )

            # if os.path.exists(full_path):
            #     try:
            #         os.remove(full_path)
            #         self.logger.debug(f"Удалён файл {full_path}")
            #     except OSError as e:
            #         self.logger.warning(f"Не удалось удалить файл {full_path}: {e}")

        # Удаляем временный файл, если был выбран новый (и он ещё не стал current_path)
        if self._new_path and self._temp_dir:
            full_path = os.path.join(self._temp_dir, self._new_path)

            schedule_deletion(
                path=full_path,
                ctx=None,
                remove_parent_if_empty=False,
                force=False,
                logger=self.logger
            )
            # if os.path.exists(full_path):
            #     try:
            #         os.remove(full_path)
            #         self.logger.debug(f"Удалён временный файл {full_path} при удалении фото")
            #     except OSError as e:
            #         self.logger.warning(f"Не удалось удалить временный файл {full_path}: {e}")

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
    def get_result(self) -> Tuple[
        Optional[str]
    ]:
        """
        Возвращает результат редактирования после закрытия диалога.

        Возвращает:
            Optional[str]: новый_путь_к_файлу

            Правила возврата:
                - Если в режиме 'single' было выбрано новое фото: (new_path)
                - Если текущее фото было удалено: (None)
                - Если изменений не было: (None)
                - В режиме 'multi' следует использовать get_selected_files().

        Примечание:
            Для режима 'single' new_path может быть относительным (если копировали
            во временную папку) или абсолютным (если копировали в основное хранилище).
            Вызывающий код должен обработать путь в соответствии с контекстом.

        Пример:
            >>> new_path = dialog.get_result()
            >>> if new_path is None:
            ...     # фото удалено
            ... elif new_path is not None:
            ...     # фото изменено
        """

        # new_desc = self.desc_edit.toPlainText()

        # if (
        #     (
        #         new_desc is None 
        #     )and(
        #         (self._description is not None) and self._description == ''
        #     )
        # ) or (
        #     (
        #         self._description is None
        #     ) and (
        #         (new_desc is not None) and new_desc == ''
        #     )
        # ):
        #     new_desc = self._description   

        # if self._new_path is not None:
        return self._new_path #, new_desc
        
        # if self._current_path is None:
        #     return None, None
        
        # if new_desc != self._description:
        #     return self._current_path, new_desc
        
        # return None, None

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
            Вызывает родительский QDialog.accept().

        Примечание:
            Это необходимо, потому что в момент закрытия диалога виджеты
            могут быть уже уничтожены, и get_result() не сможет получить
            значение из self.desc_edit. Сохранение в self._new_description
            гарантирует, что данные доступны после accept().

        Returns:
            None
        """
            
        # self._new_description = self.desc_edit.toPlainText()

        # После сохранения удаляем временную папку, если она пуста
        if self._temp_dir and os.path.exists(self._temp_dir):
            if not os.listdir(self._temp_dir):
                schedule_deletion(
                    path=self._temp_dir,
                    ctx=None,
                    remove_parent_if_empty=False,
                    force=False,
                    logger=self.logger
                )

        super().accept()