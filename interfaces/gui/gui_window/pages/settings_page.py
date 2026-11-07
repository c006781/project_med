# interfaces/gui/gui_window/pages/settings_page.py

"""
Экран настроек: форма значений ``config.msgpack`` и вкладка «О программе».

* ``SettingsPage`` — страница главного окна. Поля заполняются из менеджера настроек при входе
  (``on_enter``); кнопка «Сохранить настройки» пишет поля в менеджер и файл, затем применяет
  изменившиеся блоки (``create_config_applier``) и сообщает окну (``on_settings_changed``);
* ``TokenCheckThread``, ``PathCheckThread`` — проверка токена и папки Яндекс.Диска в отдельном
  потоке; ``remote_folder_of`` — какую папку проверять;
* ``confirm_cleanup``, ``storage_report_notes`` — список и подтверждение кнопок уборки;
* ``open_folder_detached`` — открытие папки в файловом менеджере.

Подробно — ``interfaces/gui/gui_window/IMPLEMENTATION.md``.

Example:
    >>> page = SettingsPage(page_title = "Настройки")    # doctest: +SKIP
    >>> page.on_enter({'first_start': True})             # doctest: +SKIP
"""

import os
import posixpath
import shutil
import sys
from typing import Any, Dict, List, Optional, Tuple

from app.config import APP_VERSION, GITHUB_REPO_SLUG
from app.dependencies import create_database
from app.dependencies import create_config_applier  # применитель с сервисами (К6)
from app.dependencies import get_db, get_photo_service  # уборка без ссылок
from app.database.table_events import table_def_of  # заголовки таблиц в списке уборки
from app.utils.logger.bool_strings import to_bool  # одно правило для строк-флагов
from app.utils.logger.logger import AppLogger

from app.network.ya_dop import PATH_MISSING_PREFIX  # отличить «нет папки» от ошибки
from app.network.ya_dop import DB_EXTENSIONS, check_and_create_path, check_token, normalize_remote_path

from app.config.config_applier import ConfigApplier
from app.config.config_manager.manager import (
    DRAFT_MOVED_RULE_KEY,       # правило перенесённой записи
    UPDATE_CHECK_ON_START_KEY,  # проверка обновлений при запуске
    WORD_DOCUMENTS_PATH_KEY,    # папка документов Word
    AppConfigManager,           # менеджер настроек
)

from interfaces.gui.gui_window.pages.base_page import BasePage

from PySide6.QtWidgets import (
    # QWidget, 
    QApplication, QComboBox, QDialog, QDialogButtonBox, QFrame, QLabel, QMenu, QPlainTextEdit, QScrollArea,
    QTabWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QPushButton, QSpinBox, QCheckBox,
    QFileDialog, QMessageBox, QGroupBox, QWidget
)
from PySide6.QtCore import QPoint, QProcess, QThread, QUrl, Signal, Slot, Qt
from PySide6.QtGui import QDesktopServices

# запуск файлового менеджера для папки отдельным процессом
def open_folder_detached(
    folder   : str,       # путь к существующей папке
    platform : str = '',  # sys.platform; '' — текущая система
) -> Optional[str]:
    """
    Открывает папку в файловом менеджере, не дожидаясь его завершения.

    Windows — ``explorer``, macOS — ``open``, остальные — ``xdg-open``. Раньше результат
    ``QProcess.startDetached`` не проверялся: без ``xdg-open`` (минимальный Linux, контейнер)
    кнопка молча ничего не делала. Путь передаётся аргументом списка, без оболочки, поэтому
    пробелы и кириллица безопасны.

    Args:
        folder   : (str) Путь к существующей папке.
        platform : (str) Значение ``sys.platform``; '' — взять текущее.

    Returns:
        (str/None) Текст ошибки для пользователя; None — программа запущена.

    Example:
        >>> open_folder_detached(
        ...     folder   =   "/home/user/Журнал приёмов/logs",   # путь с пробелом и кириллицей
        ... )
    """
    platform = platform or sys.platform
    if platform == 'win32':
        program = 'explorer'
    elif platform == 'darwin':
        program = 'open'
    else: # Linux и другие Unix
        program = 'xdg-open'

    # программа должна быть в PATH — иначе startDetached вернёт False без пояснений
    if shutil.which(program) is None and platform != 'win32':
        return (
            f"Не найдена программа «{program}» для открытия папки.\n"
            f"Откройте папку вручную:\n{folder}"
        )
    result = QProcess.startDetached(
        program,        # файловый менеджер
        [folder],       # аргумент — папка
    )
    started = result[0] if isinstance(result, tuple) else bool(result) # PySide6 отдаёт (успех, pid)
    if not started:
        return f"Не удалось запустить «{program}».\nОткройте папку вручную:\n{folder}"
    return None


# Журнал страницы настроек и её потоков проверки
_log = AppLogger.get_instance(
    name                 = 'gui.SettingsPage',  # тот же логгер, что у страницы
    enable_file_logging  = 'user',              # файл пользовательского журнала
    use_name_in_filename = False,               # имя логгера не в имени файла
)


# папка на Диске, которую проверяет кнопка
def remote_folder_of(
    remote_path : str,  # значение поля «Удалённый путь БД»
) -> str:
    """
    Возвращает папку на Яндекс.Диске для пути из настроек.

    В настройке можно указать и папку, и файл базы: путь с расширением базы (``DB_EXTENSIONS``) —
    это файл (так же считает ``remote_db_file_path``), его папка — родительская. Файл в корне
    Диска — папка ``/``.

    Args:
        remote_path : (str) Значение поля «Удалённый путь БД».

    Returns:
        (str) Нормализованный путь к папке.

    Example:
        >>> remote_folder_of("Проекты/test/bd/clinic.db")
        'Проекты/test/bd'
        >>> remote_folder_of("Проекты/test/bd/")
        'Проекты/test/bd'
        >>> remote_folder_of("clinic.db")
        '/'
    """
    normalized = normalize_remote_path(remote_path)
    if normalized.lower().endswith(DB_EXTENSIONS): # файл базы
        return posixpath.dirname(normalized) or '/'
    return normalized


# удаляется ли большая часть файлов фото
def cleanup_removes_most(
    extra  : int,   # файлов без ссылок, к удалению
    linked : int,   # файлов со ссылками
) -> bool:
    """
    Сообщает, что к удалению — больше половины файлов папки фото (решение владельца, В-35).

    Обычно так бывает, когда сохранён путь к другой базе, а папка фото прежняя: тогда «без ссылок»
    окажутся нужные снимки.

    Args:
        extra  : (int) Файлов без ссылок, к удалению.
        linked : (int) Файлов со ссылками.

    Returns:
        (bool) True — нужно отдельное подтверждение.

    Example:
        >>> cleanup_removes_most(1, 1), cleanup_removes_most(2, 1), cleanup_removes_most(0, 0)
        (False, True, False)
    """
    return extra > linked


# окно подтверждения уборки со списком того, что будет удалено
def confirm_cleanup(
    parent : QWidget,     # родитель окна
    title  : str,         # заголовок окна
    intro  : str,         # что и откуда будет удалено
    lines  : List[str],   # что будет удалено, по строке на запись
) -> bool:
    """
    Показывает весь список того, что будет удалено, и спрашивает подтверждение.

    Список — в прокручиваемом поле, а не в окне сообщения: файлов может быть много, а скрытые
    подробности можно не открыть. По умолчанию выбрана отмена.

    Args:
        parent : (QWidget) Родитель окна.
        title  : (str) Заголовок окна.
        intro  : (str) Что и откуда будет удалено.
        lines  : (List[str]) Что будет удалено, по строке на запись.

    Returns:
        (bool) ``True`` — пользователь подтвердил удаление.

    Example:
        >>> confirm_cleanup(
        ...     page,                           # родитель
        ...     "Очистка фото",                 # заголовок
        ...     "Будет удалено файлов: 1",      # пояснение
        ...     ["20261001_101500.jpg"],        # список
        ... )    # doctest: +SKIP
        True
    """
    dialog = QDialog(parent)
    dialog.setWindowTitle(title)
    dialog.resize(560, 420)
    layout = QVBoxLayout(dialog)

    intro_label = QLabel(intro)
    intro_label.setWordWrap(True)
    layout.addWidget(intro_label)

    list_view = QPlainTextEdit()
    list_view.setReadOnly(True)
    list_view.setPlainText(
        '\n'.join(lines),
    )
    layout.addWidget(list_view)

    buttons = QDialogButtonBox()
    delete_button = buttons.addButton(
        "Удалить",                                  # надпись
        QDialogButtonBox.ButtonRole.AcceptRole,     # подтверждает
    )
    cancel_button = buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
    delete_button.setAutoDefault(False)
    cancel_button.setDefault(True)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)
    return dialog.exec() == QDialog.DialogCode.Accepted


# пояснения к сверке файлов: что не будет удалено
def storage_report_notes(
    report : Dict[str, List[str]],  # результат PhotoService.check_storage
) -> List[str]:
    """
    Составляет пояснения к сверке папки фото: что сверка нашла, но удалять не будет.

    Args:
        report : (Dict[str, List[str]]) Результат ``PhotoService.check_storage``.

    Returns:
        (List[str]) Строки пояснений; нечего пояснять — пустой список.

    Example:
        >>> storage_report_notes(
        ...     {'extra': [], 'fresh': ['a.jpg'], 'empty_dirs': [], 'missing': ['b.jpg', 'c.jpg']},
        ... )
        ['Не трогаются файлы моложе 10 минут: 1.', 'В базе есть фото без файла на диске: 2 (удалять нечего).']
    """
    notes : List[str] = []
    if report.get('fresh'):
        notes.append(f"Не трогаются файлы моложе 10 минут: {len(report['fresh'])}.")
    if report.get('missing'):
        notes.append(f"В базе есть фото без файла на диске: {len(report['missing'])} (удалять нечего).")
    return notes


class TokenCheckThread(QThread):
    """
    Поток проверки токена Яндекс.Диска: результат и любая ошибка приходят сигналом ``result``.

    Без перехвата исключение в ``run`` терялось бы вместе с сигналом, и кнопка проверки навсегда
    осталась бы выключенной.

    Attributes:
        token : (str) OAuth-токен.

    Example:
        >>> thread = TokenCheckThread("y0_...")                     # doctest: +SKIP
        >>> thread.result.connect(page._on_token_checked)           # doctest: +SKIP
        >>> thread.start()                                          # doctest: +SKIP
    """

    result = Signal(bool, str)   # успех, сообщение пользователю

    # поток проверки заданного токена
    def __init__(
        self,
        token : str,  # OAuth-токен
    ) -> None:
        """
        Запоминает токен; проверка начнётся при ``start()``.

        Args:
            token : (str) OAuth-токен.

        Example:
            >>> thread = TokenCheckThread("y0_...")    # doctest: +SKIP
        """
        super().__init__()
        self.token = token

    # проверка токена в отдельном потоке
    def run(self) -> None:
        """
        Проверяет токен и всегда отправляет ``result``: ошибка — ``(False, текст)`` и запись в журнал.

        Example:
            >>> thread.run()    # doctest: +SKIP
        """
        try:
            ok = check_token(self.token)
            message = "Токен действителен" if ok else "Токен недействителен или нет соединения"
        except Exception as exc:
            _log.exception(f"Ошибка проверки токена Яндекс.Диска: {exc}")
            ok = False
            message = f"Не удалось проверить токен: {exc}"
        self.result.emit(
            ok,         # успех
            message,    # сообщение
        )


class PathCheckThread(QThread):
    """
    Поток проверки папки на Яндекс.Диске (создаёт только при ``create=True``, иначе сигнал ``missing``): нет папки — создаёт её; результат и любая ошибка — сигналом.

    Attributes:
        token : (str) OAuth-токен.
        path  : (str) Значение поля «Удалённый путь БД» (папка или файл базы).

    Example:
        >>> thread = PathCheckThread("y0_...", "Проекты/test/bd")   # doctest: +SKIP
        >>> thread.result.connect(page._on_path_checked)            # doctest: +SKIP
        >>> thread.start()                                          # doctest: +SKIP
    """

    result = Signal(bool, str)   # успех, сообщение пользователю
    missing = Signal(str)        # папки нет, а создавать не просили: какая папка

    # поток проверки заданной папки
    def __init__(
        self,
        token  : str,           # OAuth-токен
        path   : str,           # значение поля «Удалённый путь БД»
        create : bool = False,  # создать отсутствующую папку (пользователь согласился)
    ) -> None:
        """
        Запоминает токен и путь; проверка начнётся при ``start()``.

        Args:
            token : (str) OAuth-токен.
            path  : (str) Значение поля «Удалённый путь БД».
            create : (bool) Создать отсутствующую папку; False — только сообщить ``missing``.

        Example:
            >>> thread = PathCheckThread("y0_...", "Проекты/test/bd")    # doctest: +SKIP
        """
        super().__init__()
        self.token = token
        self.path = path
        self.create = create

    # проверка папки в отдельном потоке
    def run(self) -> None:
        """
        Проверяет папку и всегда отправляет ``result``: ошибка — ``(False, текст)`` и запись в журнал.

        Example:
            >>> thread.run()    # doctest: +SKIP
        """
        try:
            # ok, msg = check_and_create_path(self.token, self.path, create_if_missing=True)
            # ↑ до 2026-11-07 (ST2): путь по умолчанию — файл (…/clinic.db), на Диске создавалась
            #   папка с именем файла, и потом база не могла туда записаться.
            # ↑ до 2026-11-07 (В-34): папка создавалась сразу, без вопроса пользователю
            folder = remote_folder_of(self.path)
            ok, message = check_and_create_path(
                self.token,                         # токен
                folder,                             # папка, а не файл базы
                create_if_missing   =   self.create,  # создать, только если согласились
            )
            if not ok and not self.create and message.startswith(PATH_MISSING_PREFIX):
                self.missing.emit(folder)   # вопрос задаёт экран
                return
        except Exception as exc:
            _log.exception(f"Ошибка проверки папки на Яндекс.Диске: {exc}")
            ok = False
            message = f"Не удалось проверить папку: {exc}"
        self.result.emit(
            ok,         # успех
            message,    # сообщение
        )


class SettingsPage(BasePage):
    """
    Страница настроек: две вкладки, «Основные» и «О программе».

    Значения читает и пишет менеджер настроек; применение сохранённого — ``ConfigApplier``, страницы
    главного окна обновляет само окно. Путь к базе обязателен: без существующего файла базы со
    страницы нельзя уйти (``can_leave``).

    Attributes:
        logger         : (AppLogger) Журнал страницы.
        page_title     : (str) Заголовок страницы.
        config_manager : (AppConfigManager) Менеджер настроек.
        first_start    : (bool) Страницу открыли при первом запуске: после сохранения — список
            пациентов.
        token_thread   : (TokenCheckThread/None) Идущая или последняя проверка токена.
        path_thread    : (PathCheckThread/None) Идущая или последняя проверка папки.

    Example:
        >>> page = SettingsPage(page_title = "Настройки")    # doctest: +SKIP
        >>> page.can_leave()                                 # doctest: +SKIP
        True
    """

    # @AppLogger.get_instance(
    #     name = 'SettingsPage',
    #     enable_file_logging = 'system',
    #    use_name_in_filename = False, # 'system',
    # ).log_execution_time(
    #     level=AppLogger._parse_log_level('DEBUG')
    # )
    # значение настройки как bool по единому правилу программы
    @staticmethod
    def _to_bool(
        value : Any,  # значение настройки
    ) -> bool:
        """
        Приводит значение настройки к ``bool`` по единому правилу программы.

        Строки — ``parse_bool_string``: ``'on'`` — истина, ``'off'`` — ложь, нераспознанная
        строка — ложь (менеджер настроек такую строку оставляет как есть, флажок экрана
        показывает её снятой). Не строки — обычный ``bool(value)``.

        Args:
            value : (Any) Значение настройки.

        Returns:
            (bool) Значение флага.

        Example:
            >>> SettingsPage._to_bool('on'), SettingsPage._to_bool('off'), SettingsPage._to_bool(1)
            (True, False, True)
        """
        # if isinstance(value, bool):
        #     return value
        #
        # if isinstance(value, str):
        #     return value.lower() in ('true', '1', 'yes', 'on')
        #
        # return bool(value)
        # ↑ до 2026-11-07 (ST1): своё правило — у журналов и менеджера настроек оно было другим.
        return to_bool(value)

    @AppLogger.get_instance(
        name = 'SettingsPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    # страница с полями, заполненными из настроек
    def __init__(
        self,
        parent     : Optional[QWidget] = None,   # родительский виджет
        page_title : str = "Настройки",          # заголовок страницы
    ) -> None:
        """
        Создаёт страницу настроек и заполняет поля из менеджера настроек.

        Args:
            parent     : (QWidget/None) Родительский виджет; None — без родителя.
            page_title : (str) Заголовок страницы.

        Example:
            >>> page = SettingsPage(page_title = "Настройки")    # doctest: +SKIP
        """
        super().__init__(parent)

        self.logger = AppLogger.get_instance(
            name = 'gui.SettingsPage',
            # share_file_with = 'user',
            enable_file_logging = 'user',
            use_name_in_filename = False, # 'user',
        )

        self.page_title = page_title
        
        self.config_manager = AppConfigManager.get_instance()

        self.first_start = False          # флаг первого запуска

        self.token_thread : Optional[TokenCheckThread] = None   # идущая или последняя проверка токена
        self.path_thread  : Optional[PathCheckThread] = None    # идущая или последняя проверка папки

        self._setup_ui()
        self.setMinimumHeight(400)
        self._load_settings()

        # Поток проверки, уничтоженный на ходу при выходе из программы, роняет процесс
        application = QApplication.instance()
        if application is not None:
            application.aboutToQuit.connect(self.wait_check_threads)

    # ----------------------------------------------------------------------
    # Построение интерфейса
    # ----------------------------------------------------------------------

    @AppLogger.get_instance(
        name = 'SettingsPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    # вкладки страницы и подключение сигналов
    def _setup_ui(self) -> None:
        """
        Создаёт вкладки «Основные» и «О программе» и подключает сигналы виджетов.

        Example:
            >>> page._setup_ui()    # doctest: +SKIP
        """
        main_layout = QVBoxLayout(self)

        # Создаём виджет вкладок
        self.tab_widget = QTabWidget()

        # Создаём две страницы
        self.settings_tab = QWidget()
        self.about_tab = QWidget()

        # Добавляем вкладки
        self.tab_widget.addTab(self.settings_tab, "Основные")
        self.tab_widget.addTab(self.about_tab, "О программе")

        main_layout.addWidget(self.tab_widget)

        # Наполняем вкладку "Основные"
        self._setup_settings_scroll_area(self.settings_tab)

        # Наполняем вкладку "О программе"
        self._setup_about_scroll_area(self.about_tab)

        # Подключаем сигналы (те, что не зависят от вкладок)
        self._connect_signals()

        # # ----- Вкладка "О программе" -----
        # self._setup_about_tab()

    @AppLogger.get_instance(
        name = 'SettingsPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    # вкладка «Основные» с прокруткой
    def _setup_settings_scroll_area(
        self,
        parent_widget : QWidget,  # виджет вкладки
    ) -> None:
        """
        Добавляет в виджет вкладки область прокрутки с виджетами настроек.

        Args:
            parent_widget : (QWidget) Виджет вкладки «Основные».

        Example:
            >>> page._setup_settings_scroll_area(page.settings_tab)    # doctest: +SKIP
        """
        scroll = QScrollArea(parent_widget)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        container = QWidget()
        scroll.setWidget(container)
        layout = QVBoxLayout(container)
        layout.setAlignment(Qt.AlignTop)
        layout.setSpacing(15)

        # Создаём виджеты (без layout – они будут добавлены сюда)
        self._create_settings_widgets()  # создаёт basic_group, maintenance_group, log_group, save_btn

        # Добавляем в layout
        layout.addWidget(self.basic_group)
        layout.addWidget(self.maintenance_group)
        layout.addWidget(self.log_group)
        layout.addWidget(self.save_btn)
        layout.addStretch()

        # Устанавливаем scroll в parent_widget
        parent_layout = QVBoxLayout(parent_widget)
        parent_layout.setContentsMargins(0, 0, 0, 0)
        parent_layout.addWidget(scroll)

    @AppLogger.get_instance(
        name = 'SettingsPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    # вкладка «О программе» с прокруткой
    def _setup_about_scroll_area(
        self,
        parent_widget : QWidget,  # виджет вкладки
    ) -> None:
        """
        Добавляет в виджет вкладки область прокрутки со сведениями о программе.

        Args:
            parent_widget : (QWidget) Виджет вкладки «О программе».

        Example:
            >>> page._setup_about_scroll_area(page.about_tab)    # doctest: +SKIP
        """
        scroll = QScrollArea(parent_widget)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        scroll.setWidget(container)
        layout = QVBoxLayout(container)
        layout.setAlignment(Qt.AlignTop)
        layout.setSpacing(10)

        # Создаём виджеты (если ещё не созданы)
        self._create_about_widgets()

        # layout.addWidget(self.about_title, alignment=Qt.AlignCenter)
        layout.addWidget(self.version_update_widget, alignment=Qt.AlignCenter)
        layout.addWidget(self.link_widget, alignment=Qt.AlignCenter)
        layout.addStretch()

        parent_layout = QVBoxLayout(parent_widget)
        parent_layout.setContentsMargins(0, 0, 0, 0)
        parent_layout.addWidget(scroll)

    @AppLogger.get_instance(
        name = 'SettingsPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    # виджеты вкладки «Основные»
    def _create_settings_widgets(self) -> None:
        """
        Создаёт группы и поля вкладки «Основные»; в раскладку их добавляет вызывающий.

        Значения не заполняет: это ``_load_settings``. Поля способа хранения копий кода видны
        только на Linux: на других системах таких копий нет.

        Example:
            >>> page._create_settings_widgets()    # doctest: +SKIP
        """

        # ----- Группа основных настроек -----

        self.basic_group = QGroupBox("Основные настройки")
        form_layout = QFormLayout(self.basic_group)

        # Путь к БД
        self.db_path_edit = QLineEdit()

        self.db_path_btn = QPushButton("Обзор...")
        self.db_path_btn.setMaximumWidth(80)

        self.create_db_btn = QPushButton("Создать тестовую БД")
        self.create_db_btn.setMaximumWidth(150)
        self.create_db_btn.setVisible(False)

        db_path_layout = QHBoxLayout()
        db_path_layout.addWidget(self.db_path_edit)
        db_path_layout.addWidget(self.db_path_btn)
        db_path_layout.addWidget(self.create_db_btn)
        
        form_layout.addRow("Путь к БД:", db_path_layout)

        # Папка для фото
        self.photos_path_edit = QLineEdit()
        self.photos_path_btn = QPushButton("Обзор...")
        self.photos_path_btn.setMaximumWidth(80)

        photos_layout = QHBoxLayout()
        photos_layout.addWidget(self.photos_path_edit)
        photos_layout.addWidget(self.photos_path_btn)

        form_layout.addRow("Папка для фото:", photos_layout)

        # Папка документов Word: откуда импорт берёт .docx без указания папки
        self.word_path_edit = QLineEdit()
        self.word_path_edit.setToolTip("Папка с документами Word для импорта; пусто — папку нужно указать при импорте")
        self.word_path_btn = QPushButton("Обзор...")
        self.word_path_btn.setMaximumWidth(80)

        word_layout = QHBoxLayout()
        word_layout.addWidget(self.word_path_edit)
        word_layout.addWidget(self.word_path_btn)

        form_layout.addRow("Папка документов Word:", word_layout)

        # Токен Яндекс.Диска
        self.token_edit = QLineEdit()
        self.token_edit.setEchoMode(QLineEdit.Password)

        token_layout = QHBoxLayout()
        token_layout.addWidget(self.token_edit)

        self.check_token_btn = QPushButton("Проверить")
        self.check_token_btn.setMaximumWidth(80)

        token_layout.addWidget(self.check_token_btn)

        form_layout.addRow("Токен Яндекс.Диска:", token_layout)

        # Удалённый путь БД
        self.remote_path_edit = QLineEdit()

        remote_layout = QHBoxLayout()
        remote_layout.addWidget(self.remote_path_edit)

        self.check_path_btn = QPushButton("Проверить наличие папки")
        self.check_path_btn.setMaximumWidth(180)

        remote_layout.addWidget(self.check_path_btn)

        form_layout.addRow("Удалённый путь БД:", remote_layout)

        # Папка для бекапов
        self.backup_path_edit = QLineEdit()
        self.backup_path_btn = QPushButton("Обзор...")
        self.backup_path_btn.setMaximumWidth(80)

        backup_layout = QHBoxLayout()
        backup_layout.addWidget(self.backup_path_edit)
        backup_layout.addWidget(self.backup_path_btn)

        form_layout.addRow("Папка для локальных бекапов БД:", backup_layout)

        # Количество бекапов
        self.backup_count_spin = QSpinBox()
        self.backup_count_spin.setRange(1, 100)

        form_layout.addRow("Количество бекапов:", self.backup_count_spin)

        # Старые копии кода при автообновлении: есть только у Linux-версии
        self.update_keep_mode_combo = QComboBox()
        self.update_keep_mode_combo.addItem("по количеству", 'count')
        self.update_keep_mode_combo.addItem("по времени", 'days')
        self.update_keep_count_spin = QSpinBox()
        self.update_keep_count_spin.setRange(1, 100)
        self.update_keep_count_spin.setSuffix(" шт.")
        self.update_keep_days_spin = QSpinBox()
        self.update_keep_days_spin.setRange(1, 3650)
        self.update_keep_days_spin.setSuffix(" дн.")
        self.update_keep_mode_combo.currentIndexChanged.connect(self._on_update_keep_mode_changed)

        update_keep_layout = QHBoxLayout()
        update_keep_layout.setContentsMargins(0, 0, 0, 0)
        update_keep_layout.addWidget(self.update_keep_mode_combo)
        update_keep_layout.addWidget(self.update_keep_count_spin)
        update_keep_layout.addWidget(self.update_keep_days_spin)
        self.update_keep_row = QWidget()
        self.update_keep_row.setLayout(update_keep_layout)
        self.update_keep_label = QLabel("Хранить копии кода при обновлении:")
        form_layout.addRow(self.update_keep_label, self.update_keep_row)
        for widget in (self.update_keep_label, self.update_keep_row):
            widget.setVisible(sys.platform.startswith('linux'))

        # Что делать с записью, перенесённой в новую запись, если новую потом удалили
        self.draft_moved_rule_combo = QComboBox()
        self.draft_moved_rule_combo.addItem("удалить вместе с новой записью", 'delete')
        self.draft_moved_rule_combo.addItem("оставить у прежней записи", 'keep')
        self.draft_moved_rule_hint = QLabel(
            "Например, фото перенесли из приёма 1 в новый приём 2, а приём 2 удалили, "
            "не сохранив: фото удалится вместе с приёмом 2 или останется у приёма 1."
        )
        self.draft_moved_rule_hint.setWordWrap(True)

        form_layout.addRow("Перенесённая запись при удалении новой:", self.draft_moved_rule_combo)
        form_layout.addRow(self.draft_moved_rule_hint)

        # Проверка обновлений при запуске: обращение к api.github.com через 1,5 с после старта
        self.update_check_on_start_check = QCheckBox("Проверять обновления при запуске")
        form_layout.addRow(self.update_check_on_start_check)

        # ----- Группа уборки: файлы и строки, на которые никто не ссылается -----
        self.maintenance_group = QGroupBox("Уборка данных")
        maintenance_layout = QVBoxLayout(self.maintenance_group)

        self.maintenance_hint = QLabel(
            "Сначала будет показан список того, что удалится; без подтверждения ничего не удаляется."
        )
        self.maintenance_hint.setWordWrap(True)
        maintenance_layout.addWidget(self.maintenance_hint)

        self.clean_photos_btn = QPushButton("Очистить фото без ссылок")
        self.clean_photos_btn.setToolTip("Файлы в папке фото, на которые нет ссылок в базе")
        self.clean_rows_btn = QPushButton("Очистить записи без ссылок")
        self.clean_rows_btn.setToolTip("Заметки и строки файлов фото, на которые больше никто не ссылается")

        maintenance_buttons = QHBoxLayout()
        maintenance_buttons.addWidget(self.clean_photos_btn)
        maintenance_buttons.addWidget(self.clean_rows_btn)
        maintenance_buttons.addStretch()
        maintenance_layout.addLayout(maintenance_buttons)

        # ----- Группа настроек логирования -----
        self.log_group = QGroupBox("Настройки логирования")
        log_layout = QFormLayout(self.log_group)

        # Папка для логов
        self.log_dir_edit = QLineEdit()
        self.log_dir_btn = QPushButton("Обзор...")

        log_dir_layout = QHBoxLayout()
        log_dir_layout.addWidget(self.log_dir_edit)
        log_dir_layout.addWidget(self.log_dir_btn)

        log_layout.addRow("Папка для логов:", log_dir_layout)
        # self._update_log_folder_button() # Обновляем текст кнопки

        # Временная метка
        self.log_timestamp_check = QCheckBox("Добавлять дату/время в имя файла лога")

        log_layout.addRow(self.log_timestamp_check)

        # Системный логгер
        system_frame = QFrame()
        system_frame.setFrameShape(QFrame.Box)
        system_frame.setMaximumHeight(180)

        system_vbox = QVBoxLayout(system_frame)
        system_vbox.addWidget(QLabel("<b>Системный логгер</b>"))

        self.system_enabled_check = QCheckBox("Включить системный логгер")

        self.system_console_check = QCheckBox("Вывод в консоль")

        self.system_file_check = QCheckBox("Запись в файл")

        self.system_level_combo = QComboBox()
        self.system_level_combo.addItems(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])

        system_vbox.addWidget(self.system_enabled_check)
        system_vbox.addWidget(self.system_console_check)
        system_vbox.addWidget(self.system_file_check)
        system_vbox.addWidget(QLabel("Уровень:"))
        system_vbox.addWidget(self.system_level_combo)

        log_layout.addRow(system_frame)

        # Пользовательский логгер
        user_frame = QFrame()
        user_frame.setFrameShape(QFrame.Box)
        user_frame.setMaximumHeight(180)

        user_vbox = QVBoxLayout(user_frame)
        user_vbox.addWidget(QLabel("<b>Пользовательский логгер</b>"))
        
        self.user_enabled_check = QCheckBox("Включить пользовательский логгер")

        self.user_console_check = QCheckBox("Вывод в консоль")

        self.user_file_check = QCheckBox("Запись в файл")

        self.user_level_combo = QComboBox()
        self.user_level_combo.addItems(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])

        user_vbox.addWidget(self.user_enabled_check)
        user_vbox.addWidget(self.user_console_check)
        user_vbox.addWidget(self.user_file_check)
        user_vbox.addWidget(QLabel("Уровень:"))
        user_vbox.addWidget(self.user_level_combo)

        log_layout.addRow(user_frame)

        # Ротация
        self.log_max_bytes_spin = QSpinBox()
        self.log_max_bytes_spin.setRange(1024, 100 * 1024 * 1024)
        self.log_max_bytes_spin.setSuffix(" байт")
        self.log_max_bytes_spin.setToolTip("Максимальный размер одного файла лога")

        self.log_backup_count_spin = QSpinBox()
        self.log_backup_count_spin.setRange(1, 50)
        self.log_backup_count_spin.setToolTip("Количество сохраняемых архивных копий")

        log_layout.addRow("Макс. размер файла (байт):", self.log_max_bytes_spin)
        log_layout.addRow("Количество бэкапов:", self.log_backup_count_spin)


        # Значения запросов к базе в журнале: только для отладки, это личные данные
        self.log_sql_params_check = QCheckBox("Значения запросов к базе в журнал")
        self.log_sql_params_hint = QLabel(
            "Только для отладки: в журнал попадут личные данные пациентов (ФИО, телефоны, "
            "тексты приёмов). При смене база будет открыта заново."
        )
        self.log_sql_params_hint.setWordWrap(True)

        log_layout.addRow(self.log_sql_params_check)
        log_layout.addRow(self.log_sql_params_hint)

        # Кнопка открытия папки логов
        self.log_folder_btn = QPushButton()
        self.log_folder_btn.setCursor(Qt.PointingHandCursor)
        self.log_folder_btn.setContextMenuPolicy(Qt.CustomContextMenu)
        self.log_folder_btn.customContextMenuRequested.connect(self._show_log_folder_context_menu)
        self.log_folder_btn.clicked.connect(self._open_log_folder)

        # Добавляем строку в form layout группы логирования
        log_layout.addRow("Папка логов:", self.log_folder_btn)

        # Кнопка сохранения
        self.save_btn = QPushButton("Сохранить настройки")
        self.save_btn.setMaximumWidth(200)

        # Обновляем текст кнопки пути к папке логов (после того, как она создана)
        self._update_log_folder_button()

        self._bind_settings_fields()

    @AppLogger.get_instance(
        name = 'SettingsPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    # виджеты вкладки «О программе»
    def _create_about_widgets(self) -> None:
        """
        Создаёт версию, кнопку проверки обновлений и ссылку на страницу проекта.

        Example:
            >>> page._create_about_widgets()    # doctest: +SKIP
        """
        # self.about_title = QLabel("<h2>Медицинское приложение</h2>")
        # self.about_title.setAlignment(Qt.AlignCenter)

       # Горизонтальная панель для версии и кнопки обновления
        self.version_update_widget = QWidget()

        version_layout = QHBoxLayout(self.version_update_widget)
        version_layout.setContentsMargins(0, 0, 0, 0)
        version_layout.setSpacing(10)

        self.version_label = QLabel(f"Версия: <b>{APP_VERSION}</b>")
        self.version_label.setAlignment(Qt.AlignCenter)

        version_layout.addWidget(self.version_label)

        self.check_update_btn = QPushButton("Проверить обновления")
        self.check_update_btn.clicked.connect(self._on_check_updates_clicked)

        version_layout.addWidget(self.check_update_btn)
        version_layout.addStretch()  # чтобы не растягивалось на всю ширину
        version_layout.setAlignment(Qt.AlignCenter)

        repo_url = f"https://github.com/{GITHUB_REPO_SLUG}"
        # self.link_label = QLabel(f'<a href="{repo_url}">Страница проекта на GitHub</a>')
        # self.link_label.setOpenExternalLinks(True)
        # self.link_label.setAlignment(Qt.AlignCenter)

        # Виджет-контейнер для ссылки (компактный)
        self.link_widget = QWidget()

        link_layout = QHBoxLayout(self.link_widget)
        link_layout.setContentsMargins(0, 0, 0, 0)
        link_layout.setSpacing(10)

        # QLabel с возможностью выделения и копирования текста (не растягивается)
        self.link_label = QLabel(repo_url)
        # self.link_edit.setReadOnly(True)
        self.link_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.link_label.setAlignment(Qt.AlignLeft)
        self.link_label.setStyleSheet("border: none; background: transparent;")

        link_layout.addWidget(self.link_label)

        self.open_link_btn = QPushButton("Открыть")
        self.open_link_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(repo_url)))

        link_layout.addWidget(self.open_link_btn)


    @AppLogger.get_instance(
        name = 'SettingsPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    # сигналы кнопок и полей
    def _connect_signals(self) -> None:
        """
        Подключает сигналы виджетов (общие для всех вкладок).

        Example:
            >>> page._connect_signals()    # doctest: +SKIP
        """
        self.db_path_btn.clicked.connect(lambda: self._browse_file(self.db_path_edit, "Выберите файл БД", "*.db"))
        self.photos_path_btn.clicked.connect(lambda: self._browse_dir(self.photos_path_edit, "Выберите папку для фото"))
        self.word_path_btn.clicked.connect(lambda: self._browse_dir(self.word_path_edit, "Выберите папку документов Word"))
        self.backup_path_btn.clicked.connect(lambda: self._browse_dir(self.backup_path_edit, "Выберите папку для бекапов"))
        self.log_dir_btn.clicked.connect(lambda: self._browse_dir(self.log_dir_edit, "Выберите папку для логов"))
        self.save_btn.clicked.connect(self._save_settings)
        self.db_path_edit.textChanged.connect(self._update_create_db_button_visibility)
        self.create_db_btn.clicked.connect(self._on_create_test_db_clicked)
        self.check_token_btn.clicked.connect(self._check_token)
        self.check_path_btn.clicked.connect(self._check_remote_path)
        self.clean_photos_btn.clicked.connect(self._on_clean_photos_clicked)
        self.clean_rows_btn.clicked.connect(self._on_clean_rows_clicked)

        # self.log_dir_edit.textChanged.connect(self._update_log_folder_button)
        self.log_dir_edit.textChanged.connect(lambda: self._update_log_folder_button())

    @AppLogger.get_instance(
        name = 'SettingsPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    # старая замена содержимого при смене вкладки (не подключена)
    def _on_tab_changed(
        self,
        index : int,  # номер вкладки
    ) -> None:
        """
        Заменяет содержимое ``content_layout`` при переключении вкладки.

        Note:
            Не подключён ни к какому сигналу и не работает: ``content_layout`` и ``about_title``
            остались от прежней раскладки, вкладки теперь наполняются один раз в ``_setup_ui``.

        Args:
            index : (int) Номер вкладки.

        Example:
            >>> page._on_tab_changed(0)    # doctest: +SKIP
        """
        # Очищаем текущий layout
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if index == 0:  # Основные настройки
            self.content_layout.addWidget(self.basic_group)
            self.content_layout.addWidget(self.log_group)
            self.content_layout.addWidget(self.save_btn)
            self.content_layout.addStretch()
            
        else:           # О программе
            self.content_layout.addWidget(self.about_title)
            self.content_layout.addWidget(self.version_label)
            self.content_layout.addWidget(self.check_update_btn)
            self.content_layout.addWidget(self.link_widget)
            self.content_layout.addStretch()

    # @AppLogger.get_instance(
    #     name = 'SettingsPage',
    #     # share_file_with = 'system',
    #     enable_file_logging = 'system',
    #     use_name_in_filename = False, # 'system',
    # ).log_execution_time(
    #     level=AppLogger._parse_log_level('DEBUG')
    # )
    # def _setup_about_tab(self):
    #     layout = QVBoxLayout(self.about_tab)
        
    #     # Логотип (опционально)
    #     # logo = QLabel()
    #     # logo.setPixmap(QPixmap(":/icons/app_icon.png").scaled(64,64))
    #     # layout.addWidget(logo, alignment=Qt.AlignCenter)
        
    #     # Название и версия
    #     title = QLabel("<h2>Медицинское приложение</h2>")
    #     title.setAlignment(Qt.AlignCenter)
    #     layout.addWidget(title)
        
    #     version_label = QLabel(f"Версия: <b>{APP_VERSION}</b>")
    #     version_label.setAlignment(Qt.AlignCenter)
    #     layout.addWidget(version_label)
        
    #     # Кнопка проверки обновлений
    #     self.check_update_btn = QPushButton("Проверить обновления")
    #     self.check_update_btn.clicked.connect(self._on_check_updates_clicked)
    #     layout.addWidget(self.check_update_btn, alignment=Qt.AlignCenter)
        
    #     # Ссылка на GitHub
    #     repo_url = f"https://github.com/{GITHUB_REPO_SLUG}"
    #     link_label = QLabel(f'<a href="{repo_url}">Страница проекта на GitHub</a>')
    #     link_label.setOpenExternalLinks(True)
    #     link_label.setAlignment(Qt.AlignCenter)
    #     layout.addWidget(link_label)
        
    #     layout.addStretch()

    @AppLogger.get_instance(
        name='SettingsPage',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    # ручная проверка обновлений
    def _on_check_updates_clicked(self) -> None:
        """
        Запускает ручную проверку обновлений через главное окно.

        Example:
            >>> page._on_check_updates_clicked()    # doctest: +SKIP
        """
        if self.main_window and hasattr(self.main_window, 'check_for_updates'):
            self.main_window.check_for_updates()
        else:
            QMessageBox.warning(self, "Ошибка", "Система обновлений недоступна")

    @AppLogger.get_instance(
        name='SettingsPage',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    # можно ли уйти со страницы
    def can_leave(self) -> bool:
        """
        Проверяет, что в поле указан существующий файл базы; иначе предупреждает пользователя.

        Returns:
            (bool) ``True`` — можно покинуть страницу.

        Example:
            >>> page.can_leave()    # doctest: +SKIP
            True
        """
        db_path = self.db_path_edit.text().strip()
        if not db_path or not os.path.isfile(db_path):
            QMessageBox.warning(self, "Ошибка", "Сначала укажите существующий файл БД или создайте его.")
            return False
        
        return True

    @AppLogger.get_instance(
        name='SettingsPage',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    # видимость кнопки создания базы
    def _update_create_db_button_visibility(
        self,
        text : Optional[str] = None,  # текст поля (передаёт сигнал); не нужен: берётся из поля
    ) -> None:
        """
        Показывает кнопку «Создать тестовую БД», если путь пуст или такого файла нет.

        Args:
            text : (str/None) Текст поля; не используется.

        Example:
            >>> page._update_create_db_button_visibility()    # doctest: +SKIP
        """
        path = self.db_path_edit.text().strip()
        if not path:
            self.create_db_btn.setVisible(True)
            return
        
        exists = os.path.exists(path)
        self.create_db_btn.setVisible(not exists)
        self.adjustSize()  # или self.updateGeometry()

    # Обработчик кнопки создания БД
    @AppLogger.get_instance(
        name='SettingsPage',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    # создание базы по кнопке
    def _on_create_test_db_clicked(self) -> None:
        """
        Создаёт базу по пути из поля (пусто — ``./clinic.db``), спросив про тестовые данные.

        Ошибка создания — в журнал и сообщением пользователю.

        Example:
            >>> page._on_create_test_db_clicked()    # doctest: +SKIP
        """
        db_path = self.db_path_edit.text().strip()
        if not db_path:
            default_path = os.path.join('.', 'clinic.db')
            db_path = default_path
            self.db_path_edit.setText(default_path)
        
        reply = QMessageBox.question(
            self,
            "Создание базы данных",
            "Заполнить тестовыми данными?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        fill_test = (reply == QMessageBox.StandardButton.Yes)
        try:
            create_database(db_path, fill_test_data=fill_test)
            QMessageBox.information(self, "Успех", f"База данных создана: {db_path}")
            self._update_create_db_button_visibility()

        except Exception as e:
            self.logger.exception(f"Ошибка создания БД: {e}")
            QMessageBox.critical(self, "Ошибка", f"Не удалось создать БД: {e}")

    # ----------------------------------------------------------------------
    # Вспомогательные методы для выбора путей
    # ----------------------------------------------------------------------

    @AppLogger.get_instance(
        name = 'SettingsPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    # выбор файла в поле ввода
    def _browse_file(
        self,
        line_edit  : QLineEdit,  # поле, куда записать путь
        title      : str,        # заголовок окна выбора
        filter_str : str,        # фильтр файлов
    ) -> None:
        """
        Открывает окно выбора файла и записывает выбранный путь в поле; отмена поле не меняет.

        Args:
            line_edit  : (QLineEdit) Поле, куда записать путь.
            title      : (str) Заголовок окна выбора.
            filter_str : (str) Фильтр файлов.

        Example:
            >>> page._browse_file(page.db_path_edit, "Выберите файл БД", "*.db")    # doctest: +SKIP
        """
        file_path, _ = QFileDialog.getOpenFileName(self, title, "", filter_str)
        if file_path:
            line_edit.setText(file_path)

    @AppLogger.get_instance(
        name = 'SettingsPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    # доступно только поле выбранного способа хранения копий кода
    def _on_update_keep_mode_changed(
        self,
        index : int = -1,  # номер выбранного способа (передаёт сигнал); не нужен: способ берётся из поля
    ) -> None:
        """
        Включает поле количества или дней по выбранному способу хранения копий кода.

        Значение второго поля сохраняется: к нему можно вернуться, сменив способ.

        Args:
            index : (int) Номер выбранного способа; не используется.

        Example:
            >>> page.update_keep_mode_combo.setCurrentIndex(1)  # doctest: +SKIP
            >>> page.update_keep_days_spin.isEnabled()          # doctest: +SKIP
            True
        """
        by_days = self.update_keep_mode_combo.currentData() == 'days'
        self.update_keep_count_spin.setEnabled(not by_days)
        self.update_keep_days_spin.setEnabled(by_days)

    # выбор папки в поле ввода
    def _browse_dir(
        self,
        line_edit : QLineEdit,  # поле, куда записать путь
        title     : str,        # заголовок окна выбора
    ) -> None:
        """
        Открывает окно выбора папки и записывает выбранный путь в поле; отмена поле не меняет.

        Args:
            line_edit : (QLineEdit) Поле, куда записать путь.
            title     : (str) Заголовок окна выбора.

        Example:
            >>> page._browse_dir(page.log_dir_edit, "Выберите папку для логов")    # doctest: +SKIP
        """
        dir_path = QFileDialog.getExistingDirectory(self, title)
        if dir_path:
            line_edit.setText(dir_path)

    # ----------------------------------------------------------------------
    # Загрузка настроек из конфига в поля формы
    # ----------------------------------------------------------------------

    @AppLogger.get_instance(
        name = 'SettingsPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    # значения настроек — в поля формы
    def _load_settings(self) -> None:
        """
        Заполняет поля формы значениями менеджера настроек.

        Значение негодного типа (строка вместо числа в старом файле) не роняет экран: показывается
        умолчание, в журнал — предупреждение; в файл оно попадёт только при сохранении. Какие
        поля какими настройками заполняются — ``_bind_settings_fields``.

        Example:
            >>> page._load_settings()    # doctest: +SKIP
        """
    # def _load_settings(self):
    #     # Основные
    #     self.db_path_edit.setText(self.config_manager.get('database_local_path', ''))
    #     self.photos_path_edit.setText(self.config_manager.get('PHOTOS_STORAGE_PATH', ''))
    #     self.token_edit.setText(self.config_manager.get('YANDEX_TOKEN', ''))
    #     self.remote_path_edit.setText(self.config_manager.get('database_remote_path', ''))
    #     self.backup_path_edit.setText(self.config_manager.get('BACKUP_PATH', ''))
    #     self.backup_count_spin.setValue(int(self.config_manager.get('BACKUP_COUNT', 5)))
    #     keep_index = self.update_keep_mode_combo.findData(
    #         self.config_manager.get('UPDATE_BACKUP_KEEP_MODE', 'count'),
    #     )
    #     self.update_keep_mode_combo.setCurrentIndex(max(keep_index, 0))
    #     self.update_keep_count_spin.setValue(int(self.config_manager.get('UPDATE_BACKUP_KEEP_COUNT', 3)))
    #     self.update_keep_days_spin.setValue(int(self.config_manager.get('UPDATE_BACKUP_KEEP_DAYS', 30)))
    #     self._on_update_keep_mode_changed()
    #
    #     # Настройки логирования
    #     self.log_dir_edit.setText(self.config_manager.get('LOG_DIR', ''))
    #     self.log_timestamp_check.setChecked(self._to_bool(self.config_manager.get('use_timestamp', False)))
    #
    #     # Системный логгер
    #     self.system_enabled_check.setChecked(self._to_bool(self.config_manager.get('system_enabled', True)))
    #     self.system_console_check.setChecked(self._to_bool(self.config_manager.get('system_console_enabled', True)))
    #     self.system_file_check.setChecked(self._to_bool(self.config_manager.get('system_file_enabled', True)))
    #     self.system_level_combo.setCurrentText(self.config_manager.get('system_LEVEL', 'DEBUG'))
    #
    #     # Пользовательский логгер
    #     self.user_enabled_check.setChecked(self._to_bool(self.config_manager.get('user_enabled', True)))
    #     self.user_console_check.setChecked(self._to_bool(self.config_manager.get('user_console_enabled', True)))
    #     self.user_file_check.setChecked(self._to_bool(self.config_manager.get('user_file_enabled', True)))
    #     self.user_level_combo.setCurrentText(self.config_manager.get('user_LEVEL', 'DEBUG'))
    #
    #     # Ротация
    #     self.log_max_bytes_spin.setValue(int(self.config_manager.get('LOG_MAX_BYTES', 10 * 1024 * 1024)))
    #     self.log_backup_count_spin.setValue(int(self.config_manager.get('LOG_BACKUP_COUNT', 5)))
    #
    # ↑ до 2026-11-07 (ST4): int() падал на строке вроде '10 МБ', которую менеджер намеренно
    #   оставляет как есть, — экран настроек не открывался. Теперь поля заполняются по таблице.
        for key, edit in self._text_fields:
            edit.setText(
                self._text_setting(key),
            )
        for key, spin in self._int_fields:
            self._load_spin(
                spin,   # поле
                key,    # настройка
            )
        for key, check in self._flag_fields:
            check.setChecked(
                self._to_bool(
                    self._setting(key),
                ),
            )
        for key, combo in self._level_fields:
            self._load_level(
                combo,  # поле
                key,    # настройка
            )
        for key, combo in self._choice_fields:
            combo.setCurrentIndex(
                max(
                    combo.findData(self._setting(key)),  # индекс сохранённого значения
                    0,                                   # неизвестное значение — первое в списке
                ),
            )
        self._on_update_keep_mode_changed()

        self._update_log_folder_button()

    @AppLogger.get_instance(
        name='SettingsPage',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    # таблицы «настройка — поле» для чтения и записи
    def _bind_settings_fields(self) -> None:
        """
        Составляет таблицы «настройка — поле», по которым читаются и пишутся значения.

        Тип значения задаёт таблица: текст — ``str``, спин — ``int``, флажок — ``bool``, уровень —
        ``str`` из списка уровней, выбор — ``currentData`` списка. Новое поле — одна строка здесь.

        Example:
            >>> page._bind_settings_fields()    # doctest: +SKIP
        """
        self._text_fields : Tuple[Tuple[str, QLineEdit], ...] = (
            ('database_local_path', self.db_path_edit),         # путь к базе
            ('PHOTOS_STORAGE_PATH', self.photos_path_edit),     # папка фото
            (WORD_DOCUMENTS_PATH_KEY, self.word_path_edit),     # папка документов Word
            ('YANDEX_TOKEN', self.token_edit),                  # токен Диска
            ('database_remote_path', self.remote_path_edit),    # путь на Диске
            ('BACKUP_PATH', self.backup_path_edit),             # папка копий базы
            ('LOG_DIR', self.log_dir_edit),                     # папка журналов
        )
        self._int_fields : Tuple[Tuple[str, QSpinBox], ...] = (
            ('BACKUP_COUNT', self.backup_count_spin),                   # число копий базы
            ('UPDATE_BACKUP_KEEP_COUNT', self.update_keep_count_spin),  # копий кода: штук
            ('UPDATE_BACKUP_KEEP_DAYS', self.update_keep_days_spin),    # копий кода: дней
            ('LOG_MAX_BYTES', self.log_max_bytes_spin),                 # размер файла журнала
            ('LOG_BACKUP_COUNT', self.log_backup_count_spin),           # архивов журнала
        )
        self._flag_fields : Tuple[Tuple[str, QCheckBox], ...] = (
            ('use_timestamp', self.log_timestamp_check),                    # дата в имени журнала
            ('LOG_SQL_PARAMS', self.log_sql_params_check),                  # значения запросов в журнал
            (UPDATE_CHECK_ON_START_KEY, self.update_check_on_start_check),  # проверка при запуске
            ('system_enabled', self.system_enabled_check),                  # системный журнал
            ('system_console_enabled', self.system_console_check),          # он же в консоль
            ('system_file_enabled', self.system_file_check),                # он же в файл
            ('user_enabled', self.user_enabled_check),                      # пользовательский журнал
            ('user_console_enabled', self.user_console_check),              # он же в консоль
            ('user_file_enabled', self.user_file_check),                    # он же в файл
        )
        self._level_fields : Tuple[Tuple[str, QComboBox], ...] = (
            ('system_LEVEL', self.system_level_combo),  # уровень системного журнала
            ('user_LEVEL', self.user_level_combo),      # уровень пользовательского журнала
        )
        self._choice_fields : Tuple[Tuple[str, QComboBox], ...] = (
            ('UPDATE_BACKUP_KEEP_MODE', self.update_keep_mode_combo),  # как хранить копии кода
            (DRAFT_MOVED_RULE_KEY, self.draft_moved_rule_combo),       # перенесённая запись
        )

    # значение настройки; нет у менеджера — умолчание программы
    def _setting(
        self,
        key : str,  # ключ настройки
    ) -> Any:
        """
        Возвращает значение настройки как есть, без приведения типа.

        Args:
            key : (str) Ключ настройки.

        Returns:
            (Any) Значение менеджера; нет ключа — умолчание программы.

        Example:
            >>> page._setting('BACKUP_COUNT')    # doctest: +SKIP
            5
        """
        return self.config_manager.get(
            key,                                # ключ
            AppConfigManager.default_of(key),   # нет ключа
        )

    # значение настройки как текст поля
    def _text_setting(
        self,
        key : str,  # ключ настройки
    ) -> str:
        """
        Возвращает значение настройки как текст для поля ввода.

        Args:
            key : (str) Ключ настройки.

        Returns:
            (str) Текст; нет значения — пустая строка.

        Example:
            >>> page._text_setting('BACKUP_PATH')    # doctest: +SKIP
            './backups'
        """
        value = self._setting(key)
        return '' if value is None else str(value)

    # значение настройки в числовое поле
    def _load_spin(
        self,
        spin : QSpinBox,  # поле
        key  : str,       # ключ настройки
    ) -> None:
        """
        Показывает значение настройки в числовом поле, приведя его к границам поля.

        Не число (``'10 МБ'`` из старого файла) — показывается умолчание, в журнал — предупреждение.

        Args:
            spin : (QSpinBox) Поле.
            key  : (str) Ключ настройки.

        Example:
            >>> page._load_spin(page.backup_count_spin, 'BACKUP_COUNT')    # doctest: +SKIP
        """
        raw = self._setting(key)
        try:
            value = int(raw)
        except (TypeError, ValueError, OverflowError): # не число, бесконечность из файла
            value = int(
                AppConfigManager.default_of(
                    key,                    # ключ
                    fallback    =   0,      # без умолчания
                ),
            )
            self.logger.warning(f"Настройка {key}: не число ({raw!r}), показано умолчание {value}")
        # границы — здесь: слишком большое целое setValue не примет вообще (OverflowError)
        spin.setValue(
            min(
                max(value, spin.minimum()),     # не меньше нижней границы
                spin.maximum(),                 # не больше верхней
            ),
        )

    # значение настройки в список уровней журнала
    def _load_level(
        self,
        combo : QComboBox,  # список уровней
        key   : str,        # ключ настройки
    ) -> None:
        """
        Выбирает уровень журнала в списке; неизвестный уровень — умолчание программы.

        Регистр не важен (``'debug'`` — ``DEBUG``).

        Args:
            combo : (QComboBox) Список уровней.
            key   : (str) Ключ настройки.

        Example:
            >>> page._load_level(page.user_level_combo, 'user_LEVEL')    # doctest: +SKIP
        """
        index = combo.findText(
            self._text_setting(key).strip().upper(),
        )
        if index < 0: # неизвестный уровень
            index = combo.findText(
                str(
                    AppConfigManager.default_of(key, 'DEBUG'),
                ),
            )
        combo.setCurrentIndex(
            max(index, 0),
        )

    # текст кнопки папки логов
    def _update_log_folder_button(
        self,
        text : Optional[str] = None,  # текст поля; не нужен: берётся из поля
    ) -> None:
        """
        Обновляет текст кнопки с путём к папке логов.

        Args:
            text : (str/None) Текст поля; не используется.

        Example:
            >>> page._update_log_folder_button()    # doctest: +SKIP
        """
        log_dir = self.log_dir_edit.text().strip()
        if not log_dir:
            log_dir = "не указана"
        self.log_folder_btn.setText(log_dir)
        self.log_folder_btn.setToolTip("Нажмите, чтобы открыть папку логов\nПКМ – скопировать путь")

    @AppLogger.get_instance(
        name='SettingsPage',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    # открытие папки логов
    def _open_log_folder(self) -> None:
        """
        Открывает папку логов в файловом менеджере; нет папки или программы — сообщение.

        Example:
            >>> page._open_log_folder()    # doctest: +SKIP
        """
        log_dir = self.log_dir_edit.text().strip()
        # еее = os.path.exists(log_dir)
        # ↑ до 2026-11-07 (ST6): значение нигде не использовалось (оставлено от отладки).
        if (not log_dir) or (not os.path.exists(log_dir)):
            QMessageBox.warning(self, "Ошибка", f"Папка логов не существует:\n{log_dir}")
            return
        # from PySide6.QtCore import QUrl
        # from PySide6.QtGui import QDesktopServices

        log_dir = os.path.join(log_dir, '')
        # if sys.platform == 'win32':
        #     QProcess.startDetached('explorer', [log_dir])
        # elif sys.platform == 'darwin':
        #     QProcess.startDetached('open', [log_dir])
        # else:  # Linux
        #     QProcess.startDetached('xdg-open', [log_dir])
        # ↑ до 2026-11-07 (LX2): результат запуска не проверялся — без xdg-open кнопка молчала.
        error = open_folder_detached(
            log_dir,    # папка логов
        )
        if error:
            QMessageBox.warning(self, "Не удалось открыть папку", error)

        # try:
        #     url = QUrl.fromLocalFile(log_dir)
        #     QDesktopServices.openUrl(url)
        # except:
        #     # Добавляем слеш в конце, чтобы указать, что это директория
        #     log_dir = os.path.join(log_dir, '')
        #     # if not log_dir.endswith('/'):
        #     #     log_dir += '/'
        #     url = QUrl.fromLocalFile(log_dir)
        #     QDesktopServices.openUrl(url)

    @AppLogger.get_instance(
        name='SettingsPage',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    # меню кнопки папки логов
    def _show_log_folder_context_menu(
        self,
        pos : QPoint,  # место щелчка на кнопке
    ) -> None:
        """
        Показывает контекстное меню кнопки папки логов; папка не указана — меню нет.

        Args:
            pos : (QPoint) Место щелчка на кнопке.

        Example:
            >>> page._show_log_folder_context_menu(QPoint(0, 0))    # doctest: +SKIP
        """
        log_dir = self.log_dir_edit.text().strip()
        if not log_dir:
            return

        menu = QMenu(self)
        copy_action = menu.addAction("Скопировать путь")
        copy_action.triggered.connect(lambda: self._copy_log_path(log_dir))
        menu.exec(self.log_folder_btn.mapToGlobal(pos))

    @AppLogger.get_instance(
        name='SettingsPage',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    # путь в буфер обмена
    def _copy_log_path(
        self,
        path : str,  # путь к папке логов
    ) -> None:
        """
        Копирует путь в буфер обмена и сообщает об этом.

        Args:
            path : (str) Путь к папке логов.

        Example:
            >>> page._copy_log_path("./logs")    # doctest: +SKIP
        """
        # from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(path)
        QMessageBox.information(self, "Копирование", "Путь к папке логов скопирован.")

    @AppLogger.get_instance(
        name='SettingsPage',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    # проверка токена в отдельном потоке
    def _check_token(self) -> None:
        """
        Запускает проверку токена в отдельном потоке и выключает кнопку до результата.

        Результат — ``_on_token_checked``. Токен не задан — предупреждение, поток не запускается.

        Example:
            >>> page._check_token()    # doctest: +SKIP
        """
        token = self.token_edit.text().strip()
        
        if not token:
            QMessageBox.warning(self, "Ошибка", "Токен не задан.")
            return

        # class TokenCheckThread(QThread):
        #     result = Signal(bool, str)
        #     def __init__(self, token):
        #         super().__init__()
        #         self.token = token
        #
        #     def run(self):
        #         from app.network.ya_dop import check_token # циклы
        #         ok = check_token(self.token)
        #         msg = "Токен действителен" if ok else "Токен недействителен или нет соединения"
        #         self.result.emit(ok, msg)
        # ↑ до 2026-11-07 (ST3): класс внутри метода, исключение в run не доходило до сообщения,
        #   кнопка оставалась выключенной. Теперь TokenCheckThread на уровне модуля. Импорт
        #   check_token — наверху модуля: check_and_create_path из того же модуля уже был там.

        self.token_thread = TokenCheckThread(token)
        self.token_thread.result.connect(self._on_token_checked)
        self.check_token_btn.setEnabled(False)
        self.check_token_btn.setText("Проверка...")
        self.token_thread.start()

    @AppLogger.get_instance(
        name='SettingsPage',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    # результат проверки токена
    def _on_token_checked(
        self,
        ok      : bool,  # токен действителен
        message : str,   # сообщение пользователю
    ) -> None:
        """
        Возвращает кнопку проверки токена и показывает результат.

        Args:
            ok      : (bool) Токен действителен.
            message : (str) Сообщение пользователю.

        Example:
            >>> page._on_token_checked(True, "Токен действителен")    # doctest: +SKIP
        """
        self.check_token_btn.setEnabled(True)
        self.check_token_btn.setText("Проверить")

        if ok:
            QMessageBox.information(self, "Результат", message)
        else:
            QMessageBox.warning(self, "Результат", message)

    @AppLogger.get_instance(
        name='SettingsPage',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    # проверка папки на Диске в отдельном потоке
    def _check_remote_path(self) -> None:
        """
        Запускает проверку папки на Яндекс.Диске в отдельном потоке и выключает кнопку до результата.

        Папки нет — поток создаёт её (без вопроса). В поле может быть и файл базы — проверяется
        его папка (``remote_folder_of``). Результат — ``_on_path_checked``. Токен или путь не
        заданы — предупреждение, поток не запускается.

        Example:
            >>> page._check_remote_path()    # doctest: +SKIP
        """
        token = self.token_edit.text().strip()
        path = self.remote_path_edit.text().strip()
        if not token:
            QMessageBox.warning(self, "Ошибка", "Токен не задан.")
            return
        
        if not path:
            QMessageBox.warning(self, "Ошибка", "Удалённый путь не задан.")
            return

        # class PathCheckThread(QThread):
        #     result = Signal(bool, str)
        #
        #     def __init__(self, token, path):
        #         super().__init__()
        #         self.token = token
        #         self.path = path
        #
        #     def run(self):
        #         # from app.network.ya_dop import check_and_create_path
        #         ok, msg = check_and_create_path(self.token, self.path, create_if_missing=True)
        #         self.result.emit(ok, msg)
        # ↑ до 2026-11-07 (ST3): как TokenCheckThread в _check_token.

        self._start_path_thread(
            token,  # токен
            path,   # значение поля
            False,  # только проверить
        )

    # запуск потока проверки папки
    def _start_path_thread(
        self,
        token  : str,   # OAuth-токен
        path   : str,   # значение поля «Удалённый путь БД»
        create : bool,  # создать отсутствующую папку
    ) -> None:
        """
        Запускает поток проверки папки и выключает кнопку на это время.

        Args:
            token  : (str) OAuth-токен.
            path   : (str) Значение поля «Удалённый путь БД».
            create : (bool) Создать отсутствующую папку.

        Example:
            >>> page._start_path_thread(
            ...     'y0_...',           # токен
            ...     'Проекты/test/bd',  # путь
            ...     False,              # только проверить
            ... )    # doctest: +SKIP
        """
        self.path_thread = PathCheckThread(
            token,                  # токен
            path,                   # путь
            create  =   create,     # создавать ли
        )
        self.path_thread.result.connect(self._on_path_checked)
        self.path_thread.missing.connect(self._on_path_missing)
        self.check_path_btn.setEnabled(False)
        self.check_path_btn.setText("Проверка...")
        self.path_thread.start()

    # папки нет: спросить, создавать ли
    def _on_path_missing(
        self,
        folder : str,   # папка на Диске
    ) -> None:
        """
        Спрашивает, создать ли отсутствующую папку на Диске (решение владельца, В-34).

        Кнопка называется «проверить», поэтому Диск без согласия не меняется. По умолчанию — отказ.

        Args:
            folder : (str) Папка на Диске.

        Example:
            >>> page._on_path_missing('Проекты/test/bd')    # doctest: +SKIP
        """
        finished_thread = self.path_thread
        finished_thread.wait()  # поток уже отправил сигнал; ссылка на него сейчас заменится
        self.check_path_btn.setEnabled(True)
        self.check_path_btn.setText("Проверить наличие папки")
        reply = QMessageBox.question(
            self,                                                               # родитель
            "Папки нет",                                                        # заголовок
            f"На Яндекс.Диске нет папки:\n{folder}\n\nСоздать её?",              # текст
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,     # кнопки
            QMessageBox.StandardButton.No,                                      # по умолчанию отказ
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._start_path_thread(
                finished_thread.token,  # тот же токен
                finished_thread.path,   # тот же путь
                True,                   # создать
            )

    @AppLogger.get_instance(
        name='SettingsPage',
        enable_file_logging='system',
        use_name_in_filename=False,
    ).log_execution_time(level=AppLogger._parse_log_level('DEBUG'))
    # результат проверки папки
    def _on_path_checked(
        self,
        ok      : bool,  # папка есть или создана
        message : str,   # сообщение пользователю
    ) -> None:
        """
        Возвращает кнопку проверки папки и показывает результат.

        Args:
            ok      : (bool) Папка есть или создана.
            message : (str) Сообщение пользователю.

        Example:
            >>> page._on_path_checked(True, "Путь существует")    # doctest: +SKIP
        """
        self.check_path_btn.setEnabled(True)
        self.check_path_btn.setText("Проверить наличие папки")
        if ok:
            QMessageBox.information(self, "Результат", message)
        else:
            QMessageBox.warning(self, "Результат", message)

    # ----------------------------------------------------------------------
    # Уборка: файлы и строки без ссылок
    # ----------------------------------------------------------------------

    # почему уборку сейчас нельзя запускать
    def _cleanup_blocked_reason(self) -> Optional[str]:
        """
        Возвращает причину, по которой уборку запускать нельзя.

        Сверяются база и папка фото, которые открыты в программе. Без этих проверок уборка могла бы
        удалить нужное:

        * файла базы нет — открылась бы новая пустая база, и все фото оказались бы «без ссылок»;
        * поля формы не сохранены — пользователь видит одни пути, а сверка идёт по другим;
        * есть несохранённые черновики — их ссылки ещё не в базе.

        Returns:
            (str/None) Текст для пользователя; None — можно.

        Example:
            >>> page._cleanup_blocked_reason()    # doctest: +SKIP
        """
        db_path = self.db_path_edit.text().strip()
        if not os.path.isfile(db_path):
            return "Сначала укажите существующий файл БД и сохраните настройки."
        unsaved = (
            db_path != self._text_setting('database_local_path').strip()
            or self.photos_path_edit.text().strip() != self._text_setting('PHOTOS_STORAGE_PATH').strip()
        )
        if unsaved:
            return "Путь к БД или папка для фото изменены: сначала сохраните настройки."
        drafts = getattr(self.main_window, 'drafts', None)
        if drafts is not None and not drafts.store.is_empty:
            return "Есть несохранённые черновики: сначала сохраните или отмените их."
        return None

    # очистка папки фото: список, подтверждение, удаление
    def _on_clean_photos_clicked(self) -> None:
        """
        Удаляет файлы в папке фото, на которые нет ссылок в базе, после показа списка.

        Порядок: проверки (``_cleanup_blocked_reason``) → ``PhotoService.check_storage`` (только
        чтение) → список и подтверждение → ``clean_storage`` (удаляет только то, что и сейчас без
        ссылок). Нечего удалять — только сообщение; любая ошибка — в журнал и сообщением.

        Example:
            >>> page._on_clean_photos_clicked()    # doctest: +SKIP
        """
        reason = self._cleanup_blocked_reason()
        if reason:
            QMessageBox.warning(self, "Очистка фото", reason)
            return
        try:
            service = get_photo_service()
            report = service.check_storage()
        except Exception as exc:
            self.logger.exception(f"Ошибка сверки папки фото: {exc}")
            QMessageBox.critical(self, "Очистка фото", f"Не удалось проверить папку фото: {exc}")
            return

        notes = storage_report_notes(report)
        files = list(report['extra'])
        folders = list(report['empty_dirs'])
        if not files and not folders:
            QMessageBox.information(
                self,                                                   # родитель
                "Очистка фото",                                         # заголовок
                '\n'.join(["Файлов без ссылок нет.", *notes]),          # текст
            )
            return

        intro = '\n'.join([
            f"Будет удалено файлов без ссылок: {len(files)}, пустых папок: {len(folders)}. Отменить это нельзя.",
            f"База: {self._text_setting('database_local_path')}",
            f"Папка фото: {self._text_setting('PHOTOS_STORAGE_PATH')}",
            *notes,
        ])
        lines = [*files, *(f"{name} (пустая папка)" for name in folders)]
        confirmed = confirm_cleanup(
            self,               # родитель
            "Очистка фото",     # заголовок
            intro,              # пояснение
            lines,              # список
        )
        if not confirmed:
            return
        linked = service.linked_file_count(report)
        if cleanup_removes_most(len(files), linked):  # похоже на чужую базу при прежней папке
            reply = QMessageBox.question(
                self,                                                               # родитель
                "Очистка фото: проверьте базу",                                     # заголовок
                f"Будет удалено файлов: {len(files)}, останется со ссылками: {linked}.\n\n"
                f"Удаляется больше половины папки. Так бывает, если открыта другая база:\n"
                f"{self._text_setting('database_local_path')}\n\n"
                "Файлы удаляются безвозвратно. Всё равно удалить?",                  # текст
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,     # кнопки
                QMessageBox.StandardButton.No,                                      # по умолчанию отказ
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        try:
            result = service.clean_storage(report)
        except Exception as exc:
            self.logger.exception(f"Ошибка очистки папки фото: {exc}")
            QMessageBox.critical(self, "Очистка фото", f"Не удалось очистить папку фото: {exc}")
            return
        self._show_cleanup_result(
            "Очистка фото",         # заголовок
            len(result['deleted']), # удалено
            result['kept'],         # не удалено
        )

    # итог уборки пользователю
    def _show_cleanup_result(
        self,
        title   : str,        # заголовок окна
        deleted : int,        # сколько удалено
        kept    : List[str],  # что не удалено
    ) -> None:
        """
        Показывает итог уборки; что-то не удалилось — предупреждением со списком.

        Args:
            title   : (str) Заголовок окна.
            deleted : (int) Сколько удалено.
            kept    : (List[str]) Что не удалено (уже привязано, свежее, ошибка удаления).

        Example:
            >>> page._show_cleanup_result("Очистка фото", 2, [])    # doctest: +SKIP
        """
        text = f"Удалено: {deleted}."
        if kept:
            shown = '\n'.join(kept[:20])
            more = f"\n… и ещё {len(kept) - 20}" if len(kept) > 20 else ''
            QMessageBox.warning(
                self,                                                                       # родитель
                title,                                                                      # заголовок
                f"{text}\nНе удалено (уже используется или ошибка, см. журнал):\n{shown}{more}",  # текст
            )
        else:
            QMessageBox.information(self, title, text)

    # заголовки таблиц «только используемые»
    @staticmethod
    def _unused_table_titles(
        db : Any,  # общая база
    ) -> Dict[str, str]:
        """
        Возвращает заголовки таблиц «только используемые» для списка уборки.

        Args:
            db : (Database) Общая база.

        Returns:
            (Dict[str, str]) Имя таблицы → заголовок; нет описания — имя таблицы.

        Example:
            >>> SettingsPage._unused_table_titles(get_db())    # doctest: +SKIP
            {'photo_files': 'Файлы фото', 'appointments_notes': 'Заметки'}
        """
        titles : Dict[str, str] = {}
        for table, mapper in db.table_events.plan.used.items():
            table_def = table_def_of(mapper)
            titles[table.name] = getattr(table_def, 'title', None) or table.name
        return titles

    # очистка строк без ссылок: список, подтверждение, удаление
    def _on_clean_rows_clicked(self) -> None:
        """
        Удаляет строки таблиц «только используемые», на которые никто не ссылается, после показа списка.

        Порядок: проверки (``_cleanup_blocked_reason``) → ``find_unused`` (только чтение) → список и
        подтверждение → ``delete_unused`` (удаляет только то, что и сейчас без ссылок). Строка файла
        фото после коммита забирает с собой файл: для этого сервис фото кладёт папку фото в ресурсы
        базы. Нечего удалять — только сообщение; любая ошибка — в журнал и сообщением.

        Example:
            >>> page._on_clean_rows_clicked()    # doctest: +SKIP
        """
        reason = self._cleanup_blocked_reason()
        if reason:
            QMessageBox.warning(self, "Очистка записей", reason)
            return
        try:
            get_photo_service() # папка фото — в ресурсах базы (удаление файла после коммита)
            db = get_db()
            with db.session_scope() as session:
                found = db.table_events.find_unused(session)
            titles = self._unused_table_titles(db)
        except Exception as exc:
            self.logger.exception(f"Ошибка поиска записей без ссылок: {exc}")
            QMessageBox.critical(self, "Очистка записей", f"Не удалось найти записи без ссылок: {exc}")
            return

        if not found:
            QMessageBox.information(self, "Очистка записей", "Записей без ссылок нет.")
            return

        total = sum(len(ids) for ids in found.values())
        intro = '\n'.join([
            f"Будет удалено записей без ссылок: {total}. Отменить это нельзя.",
            "Вместе со строкой файла фото удаляется и сам файл.",
            f"База: {self._text_setting('database_local_path')}",
        ])
        lines = [
            f"{titles.get(name, name)}: {row_id}"
            for name, ids in found.items()
            for row_id in ids
        ]
        confirmed = confirm_cleanup(
            self,                   # родитель
            "Очистка записей",      # заголовок
            intro,                  # пояснение
            lines,                  # список
        )
        if not confirmed:
            return

        try:
            with db.session_scope() as session:
                deleted = db.table_events.delete_unused(session, found)
        except Exception as exc:
            self.logger.exception(f"Ошибка очистки записей без ссылок: {exc}")
            QMessageBox.critical(self, "Очистка записей", f"Не удалось удалить записи: {exc}")
            return
        kept = [
            f"{titles.get(name, name)}: {row_id}"
            for name, ids in found.items()
            for row_id in ids
            if row_id not in deleted.get(name, [])
        ]
        self._show_cleanup_result(
            "Очистка записей",                              # заголовок
            sum(len(ids) for ids in deleted.values()),      # удалено
            kept,                                           # не удалено
        )

    # ожидание потоков проверки перед выходом
    def wait_check_threads(
        self,
        timeout_ms : int = 3000,  # сколько ждать каждый поток, мс
    ) -> None:
        """
        Ждёт завершения идущих проверок Диска; вызывается при выходе из программы.

        Поток не прерывается: прерванный посреди запроса он может оставить интерпретатор в плохом
        состоянии. Не успел за ``timeout_ms`` (медленная сеть) — на выходе будет то же сообщение Qt,
        что и без этого ожидания; настройки и база от него не зависят.

        Args:
            timeout_ms : (int) Сколько ждать каждый поток, мс.

        Example:
            >>> page.wait_check_threads(
            ...     timeout_ms  =   100,   # не дольше 0,1 с на поток
            ... )    # doctest: +SKIP
        """
        for thread in (self.token_thread, self.path_thread):
            if thread is not None and thread.isRunning():
                thread.wait(timeout_ms)

    # ----------------------------------------------------------------------
    # Сохранение настроек и перезагрузка логгеров
    # ----------------------------------------------------------------------

    @AppLogger.get_instance(
        name = 'SettingsPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    # поля формы — в менеджер настроек, нужных типов
    def _sawe_new_config(self) -> None:
        """
        Записывает значения полей в менеджер настроек (в файл — только ``save()``).

        Типы задаёт таблица ``_bind_settings_fields``: текст без пробелов по краям, числа ``int``,
        флажки ``bool``, выбор — строка из списка. Пустая папка копий базы заменяется умолчанием,
        и поле это показывает: пустое значение менеджер всё равно считает «не задано».

        Example:
            >>> page._sawe_new_config()    # doctest: +SKIP
        """
        if not self.backup_path_edit.text().strip():
            self.backup_path_edit.setText(
                self._text_default('BACKUP_PATH'),
            )
        for key, edit in self._text_fields:
            self.config_manager.set(
                key,                    # настройка
                edit.text().strip(),    # пробелы вокруг пути и токена — следствие вставки
            )
        for key, spin in self._int_fields:
            self.config_manager.set(
                key,            # настройка
                spin.value(),   # int
            )
        for key, check in self._flag_fields:
            self.config_manager.set(
                key,                # настройка
                check.isChecked(),  # bool
            )
        for key, combo in self._level_fields:
            self.config_manager.set(
                key,                    # настройка
                combo.currentText(),    # уровень
            )
        for key, combo in self._choice_fields:
            self.config_manager.set(
                key,                    # настройка
                combo.currentData(),    # значение выбранного пункта
            )

    # умолчание настройки как текст поля
    @staticmethod
    def _text_default(
        key : str,  # ключ настройки
    ) -> str:
        """
        Возвращает умолчание настройки как текст для поля ввода.

        Args:
            key : (str) Ключ настройки.

        Returns:
            (str) Текст умолчания; нет умолчания — пустая строка.

        Example:
            >>> SettingsPage._text_default('BACKUP_PATH')    # doctest: +SKIP
            './backups'
        """
        return str(
            AppConfigManager.default_of(
                key,                    # ключ
                fallback    =   '',     # без умолчания
            ),
        )

    # def _sawe_new_config(
    #     self
    # ):
    #     # Сохраняем основные настройки
    #     self.config_manager.set('database_local_path', self.db_path_edit.text())
    #     self.config_manager.set('PHOTOS_STORAGE_PATH', self.photos_path_edit.text())
    #     self.config_manager.set('YANDEX_TOKEN', self.token_edit.text())
    #     self.config_manager.set('database_remote_path', self.remote_path_edit.text())
    #     self.config_manager.set('BACKUP_PATH', self.backup_path_edit.text())
    #     self.config_manager.set('BACKUP_COUNT', self.backup_count_spin.value())
    #     self.config_manager.set('UPDATE_BACKUP_KEEP_MODE', self.update_keep_mode_combo.currentData())
    #     self.config_manager.set('UPDATE_BACKUP_KEEP_COUNT', self.update_keep_count_spin.value())
    #     self.config_manager.set('UPDATE_BACKUP_KEEP_DAYS', self.update_keep_days_spin.value())
    #
    #     # Сохраняем настройки логирования
    #     self.config_manager.set('LOG_DIR', self.log_dir_edit.text())
    #     self.config_manager.set('use_timestamp', self.log_timestamp_check.isChecked())
    #
    #     self.config_manager.set('system_enabled', self.system_enabled_check.isChecked())
    #     self.config_manager.set('system_console_enabled', self.system_console_check.isChecked())
    #     self.config_manager.set('system_file_enabled', self.system_file_check.isChecked())
    #     self.config_manager.set('system_LEVEL', self.system_level_combo.currentText())
    #
    #     self.config_manager.set('user_enabled', self.user_enabled_check.isChecked())
    #     self.config_manager.set('user_console_enabled', self.user_console_check.isChecked())
    #     self.config_manager.set('user_file_enabled', self.user_file_check.isChecked())
    #     self.config_manager.set('user_LEVEL', self.user_level_combo.currentText())
    #
    #     self.config_manager.set('LOG_MAX_BYTES', self.log_max_bytes_spin.value())
    #     self.config_manager.set('LOG_BACKUP_COUNT', self.log_backup_count_spin.value())
    # ↑ до 2026-11-07 (ST5): значения писались построчно, текст — как ввели: токен с пробелом после
    #   вставки сохранялся неверным, а путь к базе проверялся без пробелов, сохранялся с ними.

    @AppLogger.get_instance(
        name = 'SettingsPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    @Slot()
    # сохранение полей и применение изменившихся настроек
    def _save_settings(self) -> None:
        """
        Сохраняет настройки из формы в файл и применяет их.

        Порядок:
            1. Путь к базе обязателен; файла нет — предложить создать, отказ прерывает сохранение.
            2. Снимок прежней конфигурации, поля формы — в менеджер, ``save()``.
            3. ``applier.apply_changes``: только изменившиеся блоки, сбой одного не мешает другим.
            4. Главное окно получает изменившиеся блоки (``on_settings_changed``).
            5. Сообщение пользователю: сбои применения — предупреждением со списком блоков.
            6. При первом запуске (``first_start``) — переход на список пациентов.

        Любая ошибка сохранения перехватывается: сообщение пользователю и запись в журнал.

        Example:
            >>> page._save_settings()    # doctest: +SKIP
        """

        db_path = self.db_path_edit.text().strip()
        if not db_path:
            QMessageBox.warning(self, "Ошибка", "Путь к БД не может быть пустым.")
            return
        if not os.path.isfile(db_path):
            reply = QMessageBox.question(
                self, "База данных не найдена",
                f"Файл БД '{db_path}' не существует.\nСоздать новую БД?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                fill = QMessageBox.question(
                    self, "Тестовые данные",
                    "Заполнить тестовыми данными?"
                ) == QMessageBox.StandardButton.Yes
                try:
                    create_database(db_path, fill_test_data=fill)
                    QMessageBox.information(self, "Успех", "БД создана.")
                    # Путь уже установлен, продолжаем сохранение
                except Exception as e:
                    QMessageBox.critical(self, "Ошибка", f"Не удалось создать БД: {e}")
                    return
            else:
                return  # не сохранять

        # Сохраняем старую конфигурацию для сравнения
        old_config = self.config_manager.get_all().copy()

        self._sawe_new_config()

        try:
            self.config_manager.save()

            # Получаем новую конфигурацию и определяем изменившиеся блоки
            new_config = self.config_manager.get_all()
            # from app.config.config_applier import ConfigApplier
            changed_blocks = ConfigApplier.get_changed_blocks(old_config, new_config)

            # # Применяем только изменённые блоки
            # applier = ConfigApplier()
            # if 'database' in changed_blocks:
            #     applier.apply_database(new_config)
            #
            # if 'photos' in changed_blocks:
            #     applier.apply_photos_storage(new_config)
            #
            # if 'sync' in changed_blocks:
            #     applier.apply_sync(new_config)
            #
            # if any(block.startswith('logging') for block in changed_blocks):
            #     applier.apply_logging(new_config)
            #
            # if 'backup' in changed_blocks:
            #     applier.apply_backup(new_config)
            # ↑ до 2026-10-14: методы сравнивали с уже сохранённым менеджером и ничего не
            #   применяли (A1). Теперь — один вызов со снимком ДО сохранения.
            # applier = ConfigApplier()
            # ↑ до 2026-10-25 (К6): ConfigApplier сам импортировал сервисы из
            #   app.dependencies; теперь их передаёт create_config_applier().
            applier = create_config_applier()
            changed_blocks = applier.apply_changes(old_config, new_config)


            # # ----------------------------------------------------------
            # # Ключевой момент: перезагружаем все логгеры из нового конфига
            # # ----------------------------------------------------------
            # # from app.utils.logger.logger import AppLogger
            # AppLogger.reload_all_from_app_config()


            # Уведомляем главное окно о применённых изменениях (передаём список изменённых блоков)
            if self.main_window and hasattr(self.main_window, 'on_settings_changed'):
                self.main_window.on_settings_changed(
                    changed_blocks
                )

            # QMessageBox.information(self, "Успех", "Настройки сохранены.")
            # ↑ до AP4 (проверка конфига 2, 2026-10-15): сбой применения блока прерывал
            #   остальные и показывался как «не удалось сохранить», хотя файл сохранён.
            #   Теперь ConfigApplier применяет блоки независимо, ошибки — в applier.errors.
            if applier.errors:
                details = '\n'.join(f"• {block}: {err}" for block, err in applier.errors.items())
                QMessageBox.warning(
                    self, "Настройки сохранены частично",
                    "Настройки сохранены, но применить удалось не всё:\n"
                    f"{details}\n\nПодробности — в журнале; изменения вступят в силу "
                    "после перезапуска программы.",
                )
            else:
                QMessageBox.information(self, "Успех", "Настройки сохранены.")
            self.logger.info("Настройки сохранены, логгеры перезагружены")

            self._update_create_db_button_visibility()

            # Если это был первый запуск (настройки открыты при старте) – переходим на список пациентов
            if self.first_start:
                self.main_window.page_manager.switch_to(
                    'patient_list',
                    add_to_history=False,
                )

        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить настройки: {e}")
            self.logger.exception(f"Ошибка сохранения настроек: {e}")

    # ----------------------------------------------------------------------
    # Метод, вызываемый при показе страницы
    # ----------------------------------------------------------------------

    @AppLogger.get_instance(
        name = 'SettingsPage',
        # share_file_with = 'system',
        enable_file_logging = 'system',
        use_name_in_filename = False, # 'system',
    ).log_execution_time(
        level=AppLogger._parse_log_level('DEBUG')
    )
    # вход на страницу: свежие значения полей
    def on_enter(
        self,
        extra_data : Optional[Dict[str, Any]] = None,  # данные перехода
    ) -> None:
        """
        Перечитывает настройки из файла и заполняет поля; несохранённые правки в полях теряются.

        Args:
            extra_data : (dict/None) Данные перехода: ``first_start`` (bool) — первый запуск;
                None — обычный вход.

        Example:
            >>> page.on_enter({'first_start': True})    # doctest: +SKIP
        """

        # """При входе на страницу обновляем настройки и запоминаем флаг первого запуска."""

        self.config_manager.load()
        self._load_settings()
        self.first_start = extra_data.get('first_start', False) if extra_data else False
        self.logger.debug(f"Страница настроек открыта, first_start={self.first_start}")