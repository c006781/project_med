# app/utils/logger/_handlers_mgmt.py

"""
Часть ``BaseAppLogger``: Сборка обработчиков.

Содержит примесь ``_HandlersMixin``: _update_handlers и помощники: консоль, свой файл, путь к файлу.
Сам по себе модуль не используется — класс собирается в ``base_logger.py``:
``class BaseAppLogger(_HandlersMixin, ...)``. Методы перенесены из ``base_logger.py``
(2026-10-14) без изменений, вместе с комментариями и закомментированным старым кодом.

Имя ``BaseAppLogger`` внутри методов (``BaseAppLogger._share_lock`` и т. п.) указывает
на итоговый класс: ``base_logger.py`` подставляет его в этот модуль сразу после создания
класса (до первого вызова любого метода).

Пример:
    >>> from app.utils.logger.base_logger import BaseAppLogger
    >>> issubclass(BaseAppLogger, _HandlersMixin)
    True
"""

import os
import logging
from typing import List, Optional, Any


from ._common import LOGGER_CODE_FILES
from .handlers import CallableHandler, RobustRotatingFileHandler

LOGGER_CODE_FILES.append((lambda: None).__code__.co_filename)

# Подставляется в base_logger.py после создания класса (см. докстринг модуля)
BaseAppLogger: Any = None


class _HandlersMixin:
    """
    Примесь ``BaseAppLogger``: _update_handlers и помощники: консоль, свой файл, путь к файлу.

    Отдельно не используется: атрибуты и блокировки (``_instances``, ``_handler_lock``…)
    объявлены в ``BaseAppLogger``.

    Пример:
        >>> BaseAppLogger.__mro__  # doctest: +ELLIPSIS
        (<class '...BaseAppLogger'>, <class '..._HandlersMixin'>, ...)
    """

    def _reopen_file_handler_if_needed(self) -> None:
        """
        Переоткрывает файл своего обработчика (``force_reopen``), если обработчик есть.

        Название историческое: переоткрывает всегда, а не «если нужно». Ошибки не
        пробрасываются: ``FileNotFoundError`` игнорируется, остальное — WARNING в лог.

        Returns:
            None

        Пример:
            >>> log._reopen_file_handler_if_needed()
        """
        # if self.file_handler and hasattr(self.file_handler, 'reopen_if_needed'):
            # self.file_handler.reopen_if_needed()
        # if self.file_handler and hasattr(self.file_handler, 'force_reopen'):
        #     self.file_handler.force_reopen()

        # Если обработчик существует и есть метод force_reopen, вызываем его
        if self.file_handler and hasattr(self.file_handler, 'force_reopen'):
            try:
                self.file_handler.force_reopen()

            except FileNotFoundError:
                # файл мог быть удалён между проверкой и переоткрытием – игнорируем
                pass

            except Exception as e:
                self.logger.warning(f"Ошибка при переоткрытии файла: {e}")
        # Если обработчика нет – ничего не делаем. Пересоздание произойдёт при следующем

    def _has_output_handlers(self) -> bool:
        """
        Есть ли у логгера реальный вывод: консоль, файл или глобальный обработчик.

        Постоянный ``NullHandler`` (R6) не считается. Нужен там, где сообщение
        логгера о самом себе может прийти до создания обработчиков (в ``__init__``):
        тогда его надо вывести в stderr напрямую, иначе оно потеряется.

        Returns:
            ``True``, если хотя бы один обработчик, кроме NullHandler, подключён.

        Пример:
            >>> log = AppLogger.get_instance('x')
            >>> log._has_output_handlers()
            True
            >>> log.disable(); log._has_output_handlers()   # остались глобальные?
            False
        """
        logger = getattr(self, 'logger', None)
        if logger is None:
            return False
        return any(not isinstance(h, logging.NullHandler) for h in logger.handlers)

    def _file_output_missing(self) -> bool:
        """
        Файл логгеру нужен, а файлового обработчика нет.

        Так бывает, когда флаги логгера не менялись, но мастер, через которого он
        писал, закрыл общий файл (S2): обработчик у слейва отцеплен, а сам слейв
        файл по-прежнему хочет. Используется как дополнительный повод перестроить
        обработчики в ``reload_from_config()`` / ``apply_config_from_dict()``.

        Returns:
            ``True``, если логгер включён, файл включён, а ``file_handler`` пустой.

        Пример:
            >>> log.reconfigure(file_enabled=True)
            >>> log._file_output_missing()
            False
        """
        return self._enabled and self._file_enabled and self.file_handler is None

    def _save_handlers (self) -> None:
        """
        Обновляет ``self.handlers`` — копию списка обработчиков ``logging.Logger``.

        Вызывается после любого изменения набора обработчиков.

        Returns:
            None

        Пример:
            >>> log._save_handlers(); log.handlers == log.logger.handlers
            True
        """
        # Сохраняем ссылки на обработчики (может пригодиться для GUI)
        self.handlers = self.logger.handlers[:]

    # def _clear_handlers_old(self): 
    #     # Удаляем старые "свои" обработчики, если они были
    #     self._remove_console_handler(if_close_console_handler=True)

    #     # Удаляем ТОЛЬКО свой файловый обработчик, если он не общий
    #     if self.file_handler and not self._shared_handler:
    #         self._remove_file_handler(if_close_file_handler=True)

        # Если общий – ничего не делаем, оставляем как есть

    # def _clear_handlers_all(self):
    #     # Удаляем все обработчики
    #     for handler in self.logger.handlers[:]:

    #         self.logger.removeHandler(handler)
    #         if hasattr(handler, 'close'):
    #             handler.close()

    # def _update_console_handler (self):
    #     # Консольный обработчик
    #     if self._enabled and self._console_enabled:
    #         self.console_handler = logging.StreamHandler()
    #         self.console_handler.setLevel(self.log_level)
    #         self.console_handler.setFormatter(self.formatter)
    #         self.logger.addHandler(self.console_handler)

    #     else:
    #         self.console_handler = None

    # def _update_console_handler_if_on (self):
    #     # Консольный обработчик (если включён)
    #     if self._enabled and self._console_enabled:
    #         self.console_handler = logging.StreamHandler()
    #         self.console_handler.setLevel(self.log_level)
    #         self.console_handler.setFormatter(self.formatter)
    #         self.logger.addHandler(self.console_handler)   
             
    # def _file_handler_update (self):
    #     # Файловый обработчик
    #     if self._enabled and self._file_enabled:
    #         self.file_handler = self._create_file_handler()
    #         self.logger.addHandler(self.file_handler)

    #     else:
    #         if self.file_handler:
    #             self.file_handler.close()
    #             self.file_handler = None

    # def _file_handler_update_if_on (self):
    #     # Файловый обработчик (если включён)
    #     if self._enabled and self._file_enabled:
    #         self.file_handler = self._create_file_handler()
    #         self.logger.addHandler(self.file_handler)

    def _update_file_handler_if_not_shared(self) -> None:
        """
        Сбрасывает связь с мастером и, если файл включён, создаёт свой обработчик.

        Вызывается при аномалии «флаг общего обработчика есть, а мастера нет».

        Returns:
            None

        Пример:
            Вызывается из ``_update_handlers``.
        """
        with self._handler_lock:
            if self.file_handler and self.file_handler in self.logger.handlers:
                self.logger.removeHandler(self.file_handler)

            self.file_handler = None

            # Если используется общий обработчик, он уже присутствует (был добавлен через share_file_handler_with)
            # У мастера нет обработчика – значит, мы больше не слейв

            self._shared_handler = False
            self._master_logger = None
            
            # Пересоздаём собственный обработчик, если нужно
            if self._file_enabled:
                self._update_file_handler()
                # self.file_handler = self._create_file_handler()
                # self.logger.addHandler(self.file_handler)
                # self._reopen_file_handler_if_needed()

    # def _copy_master(self, master):
    #     if not master:
    #         return
        
    #     with master._handler_lock:
    #         if master.file_handler is None:
    #             return
            
    #         visited = set()
    #         # Копируем все настройки мастера, которые могут измениться
    #         return {
    #             'master_log_LEVEL': master.log_level,
    #             'master_formatter': master.formatter,
    #             'master_base_log_FILE': master.base_log_file,
    #             'master_MAX_BYTES': master.log_max_bytes,
    #             'master_BACKUP_COUNT': master.log_backup_count,
    #             'master_timestamp': master.use_timestamp,
    #             # 'master_file_enabled': master.effective_enable_file_logging(),
    #             'master_file_enabled': master.effective_enable_file_logging(_visited=visited),
    #             # 'master_use_name': master.effective_use_name_in_filename(),
    #             'master_use_name': master.effective_use_name_in_filename(_visited=visited),
    #             'master_sync_full': master._sync_full_state,
    #             'master_ARGS': master.log_args,
    #             'master_show_depth': master._show_call_depth,
    #         }

    def _update_file_handler_if_on_and_not_shared_with_master_handler(
        self,
        master_handler: Optional[logging.Handler],
        master_log_level: int,
        master_formatter: logging.Formatter,
        master_base_log_file: str,
        master_max_bytes: int,
        master_backup_count: int,
        master_timestamp: bool,
        master_file_enabled: bool,
        master_use_name: bool,
        master_sync_full: bool,
        master_args: bool,
        master_show_depth: bool,
    ) -> None:
        """
        Подключает слейва к обработчику мастера и копирует параметры файла.

        Ничего не делает, если обработчика у мастера нет или слейв уже подключён к нему.
        Уровень мастера (``master_log_level``) больше не копируется (S3) — параметр оставлен
        для совместимости вызова.

        Args:
            master_handler: Файловый обработчик мастера.
            master_log_level: Уровень мастера (не используется, S3).
            master_formatter: Форматтер мастера.
            master_base_log_file: Путь к логам у мастера.
            master_max_bytes: Размер ротации у мастера.
            master_backup_count: Число старых файлов у мастера.
            master_timestamp: ``use_timestamp`` мастера.
            master_file_enabled: Включён ли файл у мастера (фактическое состояние).
            master_use_name: ``use_name_in_filename`` мастера.
            master_sync_full: Флаг полной синхронизации мастера.
            master_args: ``log_args`` мастера.
            master_show_depth: ``show_call_depth`` мастера.

        Returns:
            None

        Пример:
            Вызывается из ``_update_file_handler_if_on`` со снимком состояния мастера.
        """
        if master_handler is None: 
            return
        
        if self.file_handler != master_handler:
            if self.file_handler and self.file_handler in self.logger.handlers:
                self.logger.removeHandler(self.file_handler)
                # self.file_handler.close() # Не закрываем обработчик – он может использоваться другими слейвами

            self.file_handler = master_handler
            self._reopen_file_handler_if_needed()

            # self.log_level = master_log_level
            # self.logger.setLevel(self.log_level)
            # ↑ до S3: слейв при подключении получал уровень мастера (S3, IMPLEMENTATION.md §5.2: общий обработчик не фильтрует по уровню одного логгера).
            self.formatter = master_formatter
            self.base_log_file = master_base_log_file
            self.log_max_bytes = master_max_bytes
            self.log_backup_count = master_backup_count
            self.use_timestamp = master_timestamp
            self._file_enabled = master_file_enabled
            self._use_name_in_filename = master_use_name
            self._sync_full_state = master_sync_full
            self.log_args = master_args
            self._show_call_depth = master_show_depth


            if not self.file_handler:
                return

            self._sync_log_level_and_formatters() # Синхронизируем уровень и формат

            if self.file_handler not in self.logger.handlers:
                self.logger.addHandler(self.file_handler)
                self._save_handlers()


        else:
            # ничего не делается
            pass

            
    # def _update_file_handler_if_on_and_not_shared_with_master_handler (
    #     self,
    #     master_handler,
    # ):
    #     if self.file_handler != master_handler:
    #         # удаляем старый обработчик, если был
    #         if self.file_handler and self.file_handler in self.logger.handlers:
    #             self.logger.removeHandler(self.file_handler)

    #         self.file_handler = master_handler
    #         self._sync_all_from_master()   # синхронизируем все параметры

    #         if self.file_handler not in self.logger.handlers:
    #             self.logger.addHandler(self.file_handler)

    #         self._reopen_file_handler_if_needed()

    def _update_file_handler_if_on (self) -> None:
        """
        Для слейва: берёт текущий обработчик мастера и подключается к нему.

        Снимок состояния мастера делается под его блокировкой, подключение — под своей.
        Защищён от повторного входа (флаг ``_updating_file_handler``).

        Returns:
            None

        Пример:
            Вызывается из ``_update_handlers`` для логгера с общим обработчиком.
        """
        if getattr(self, '_updating_file_handler', False):
            return
        self._updating_file_handler = True

        try:
            with BaseAppLogger._share_lock:
                master = self._master_logger

                if not master or master.file_handler is None:
                    return

                # Если обработчик мастера существует, используем его
                # Захватываем блокировку мастера и копируем его состояние
                master_handler = None
                with master._handler_lock:
                    master_handler = master.file_handler

                    if master_handler is None:
                        return

                    # Теперь захватываем блокировку мастера, чтобы скопировать остальные параметры, не меняющиеся редко
                    # master_ = self._copy_master(master)  # состояние мастера копируем

                    # visited = set()
                    # ↑ P3: остаток от вызовов effective_*(_visited=visited) ниже (заменены
                    #   на фактические флаги мастера при исправлении S1/S2) — не используется.
                    # Копируем все настройки мастера, которые могут измениться
                    # master_ =  {
                    #     'master_log_LEVEL': master.log_level,
                    #     'master_formatter': master.formatter,
                    #     'master_base_log_FILE': master.base_log_file,
                    #     'master_MAX_BYTES': master.log_max_bytes,
                    #     'master_BACKUP_COUNT': master.log_backup_count,
                    #     'master_timestamp': master.use_timestamp,
                    #     # 'master_file_enabled': master.effective_enable_file_logging(),
                    #     'master_file_enabled': master.effective_enable_file_logging(_visited=visited),
                    #     # 'master_use_name': master.effective_use_name_in_filename(),
                    #     'master_use_name': master.effective_use_name_in_filename(_visited=visited),
                    #     'master_sync_full': master._sync_full_state,
                    #     'master_ARGS': master.log_args,
                    #     'master_show_depth': master._show_call_depth,
                    # }
                    master_ =  {
                        'master_log_level': master.log_level,
                        'master_formatter': master.formatter,
                        'master_base_log_file': master.base_log_file,
                        'master_max_bytes': master.log_max_bytes,
                        'master_backup_count': master.log_backup_count,
                        'master_timestamp': master.use_timestamp,
                        # 'master_file_enabled': master.effective_enable_file_logging(_visited=visited),
                        # 'master_use_name': master.effective_use_name_in_filename(_visited=visited),
                        # ↑ до исправления S1/S2: effective_* — аргументы конструктора мастера,
                        #   а не его состояние. Для system (создан без enable_file_logging=True)
                        #   слейв получал _file_enabled=False в момент подключения к файлу.
                        'master_file_enabled': master._file_enabled,
                        'master_use_name': master._use_name_in_filename,
                        'master_sync_full': master._sync_full_state,
                        'master_args': master.log_args,
                        'master_show_depth': master._show_call_depth,
                    }

                # Захватываем свой лок перед изменением состояния
                with self._handler_lock:
                    self._update_file_handler_if_on_and_not_shared_with_master_handler(
                        master_handler,
                        **master_,
                    )

        finally:
            self._updating_file_handler = False

    def _update_file_handler (self) -> None:
        """
        Создаёт свой файловый обработчик и добавляет его в ``logging.Logger``.

        Для слейва не вызывается (пишет предупреждение и выходит). Если файл создать не
        удалось — ошибка в лог и ``file_enabled`` выключается.

        Returns:
            None

        Пример:
            Вызывается из ``_update_handlers``.
        """
        if self._shared_handler:
            self.logger.warning(
                "_update_file_handler вызван для логгера с общим обработчиком"
            )
            return
        
        try:
            self.file_handler = self._create_file_handler()
            self.logger.addHandler(self.file_handler)
            # Важно: после создания обработчика проверяем существование файла
            # и при необходимости переоткрываем (восстановление после удаления)
            self._reopen_file_handler_if_needed()

        except Exception as e:
            self.logger.error(f"Не удалось создать файловый обработчик: {e}")
            self._file_enabled = False

    def _update_console_handler (self) -> None:
        """
        Создаёт консольный обработчик, если консоль включена.

        Куда пишет «консоль»:
            * по умолчанию — ``sys.stderr`` (поток запоминается в момент создания);
            * если у класса задан ``CONSOLE_OUTPUT`` (функция вида ``print(text)``) —
              в эту функцию (``CallableHandler``). Так наследник может заменить вывод
              в консоль, например, на Telegram-бот или виджет.

        Уровень — уровень логгера, форматтер — текущий (тот же формат, что у файла).

        Returns:
            None

        Пример:
            Вызывается из ``_update_handlers``.
        """
        # Консольный обработчик (всегда создаётся заново, если включён)
        if self._console_enabled:
            # self.console_handler = logging.StreamHandler()
            # ↑ до 2026-10-14 — только stderr. Теперь класс может задать свою функцию.
            console_output = type(self).CONSOLE_OUTPUT
            if console_output is None:
                self.console_handler = logging.StreamHandler()
            else:
                self.console_handler = CallableHandler(console_output, name='console')
            self.console_handler.setLevel(self.log_level)
            self.console_handler.setFormatter(self.formatter)
            self.logger.addHandler(self.console_handler)
        else:
            self.console_handler = None

    def _del_console_handler_and_file_handler (
        self,
        if_close_console_handler: bool = True,
        if_close_file_handler: bool = True,
    ) -> None:
        """
        Снимает свой консольный и свой (не общий) файловый обработчики.

        Общий обработчик мастера здесь не трогается — им занимается ``_update_handlers``.

        Args:
            if_close_console_handler: Закрыть консольный обработчик после снятия.
            if_close_file_handler: Закрыть файловый обработчик после снятия.

        Returns:
            None

        Пример:
            Вызывается в начале ``_update_handlers``.
        """
        # Удаляем старые «свои» обработчики (консольный и файловый, если они не общие)

        #    Закрываем их только если они не являются общими с другими логгерами.
        self._remove_console_handler(if_close_console_handler=if_close_console_handler)

        if self.file_handler and not self._shared_handler:
            self._remove_file_handler(if_close_file_handler=if_close_file_handler)

    def _get_all_handlers (self) -> List[logging.Handler]:
        """
        Копия списка глобальных обработчиков (под блокировкой).

        Returns:
            Список обработчиков из ``add_global_handler``/``add_global_output``.

        Пример:
            >>> log._get_all_handlers()
            [<LogViewerHandler (NOTSET)>]
        """
        with BaseAppLogger._global_handlers_lock:
            return list(BaseAppLogger._global_handlers)
        
    def _set_all_handlers (self, handlers_copy: List[logging.Handler]) -> None:
        """
        Добавляет в ``logging.Logger`` недостающие глобальные обработчики (без дублей).

        Args:
            handlers_copy: Результат ``_get_all_handlers()``.

        Returns:
            None

        Пример:
            >>> log._set_all_handlers(log._get_all_handlers())
        """
        for handler in handlers_copy:
            if handler not in self.logger.handlers:
                self.logger.addHandler(handler)
                
    
    def _update_handlers(self) -> None:
        """
        Перестраивает обработчики под текущие флаги — центральный метод класса.

        Порядок:
            1. Снимает свою консоль и свой файл; у слейва, которому файл не нужен,
               отцепляет общий обработчик (не закрывая).
            2. Если логгер выключен — на этом всё (остаются ``NullHandler``, выводы,
               глобальные обработчики — они молчат по ``_enabled``).
            3. Создаёт консоль (если включена), добавляет глобальные обработчики.
            4. Файл: если есть к кому подключиться (``_file_share_target``) — подключается
               к его обработчику (один обработчик на файл); иначе создаёт свой. Слейв
               обновляет обработчик мастера или, если у мастера файла нет, отвязывается и
               пишет сам (S2).
            5. Обновляет ``self.handlers`` и синхронизирует своих слейвов.

        Не вызывайте, удерживая ``_handler_lock``: метод берёт его сам, затем ``_share_lock``.

        Returns:
            None

        Пример:
            >>> log._enabled = False; log._update_handlers()   # так работает disable()
        """
        def _tt() -> None:
            """
            Шаги 1–4 ``_update_handlers`` (под блокировками).

            Returns:
                None

            Пример:
                Вызывается только из ``_update_handlers``.
            """
            with self._handler_lock:
                # 1. Удаляем старые «свои» обработчики (консольный и файловый, если они не общие)
                #    Закрываем их только если они не являются общими с другими логгерами.
                self._del_console_handler_and_file_handler(
                    if_close_console_handler=True,
                    if_close_file_handler=True,
                )

                # Слейв, которому файл сейчас не нужен (логгер или файл выключены),
                # отцепляет общий обработчик, НЕ закрывая его — им пользуются мастер и
                # другие слейвы. Раньше общий обработчик оставался подключённым и
                # слейв продолжал писать в файл (часть исправления S2).
                if self._shared_handler and self.file_handler is not None and not (
                    self._enabled and self._file_enabled
                ):
                    self._remove_file_handler(if_close_file_handler=False)

                # Если логгер полностью отключён – больше ничего не добавляем
                if not self._enabled:
                    return
                
                self._update_console_handler() # Консольный обработчик (всегда создаётся заново, если включён)

                # Добавляем глобальные обработчики (под блокировкой)
                
                handlers_copy = self._get_all_handlers()
                self._set_all_handlers(handlers_copy)

                # Общие выводы класса (OUTPUTS / outputs=... при наследовании)
                self._set_all_handlers(self._class_output_handlers())

                # self._save_handlers()
                # if not self._shared_handler and self._file_enabled:
                #     self._update_file_handler()

                # Создаём свой файловый обработчик, если не общий и включён
                # Файловый обработчик – только если не используется общий и файловое логирование включено

                # if not self._shared_handler and self._file_enabled:
                #     self._update_file_handler()
                # ↑ до исправления S1: свой обработчик создавался всегда, даже если
                #   логгер ссылается на родителя (enable_file_logging='system'), у которого
                #   файл уже открыт → N обработчиков на один app.log.
                #   Теперь в этом случае ниже (после _tt) логгер подключается к родителю.
                if (
                    not self._shared_handler
                    and self._file_enabled
                    and self._file_share_target() is None
                ):
                    self._update_file_handler()

                # Для остальных случаев (общий обработчик или потеря мастера) – не создаём,
                # так как они будут обработаны позже без блокировки
                # self._save_handlers()   # сохраняем состояние после базовой настройки

            with BaseAppLogger._share_lock:
                # Обновление общего обработчика (без удержания self._handler_lock)
                if self._shared_handler and self._master_logger:
                    # # Если обработчик мастера существует, используем его
                    # self._update_file_handler_if_on()
                    #
                    # self._reopen_file_handler_if_needed()# Добавлено: при переключении на общий обработчик проверяем существование файла
                    # ↑ до исправления S2: если файл у мастера выключен, слейв оставался без
                    #   файла, даже когда ему самому файл нужен (user_file_enabled=True).
                    if self._file_enabled:
                        if self._master_logger.file_handler is None:
                            # У мастера файла нет, а нам нужен — отвязываемся и пишем сами
                            # (внутри снова вызовется _update_handlers уже без общего обработчика)
                            self.unshare_file_handler(if_update_handlers=True, keep_ref_sharing=True)
                        else:
                            # Если обработчик мастера существует, используем его
                            self._update_file_handler_if_on()

                            self._reopen_file_handler_if_needed()# Добавлено: при переключении на общий обработчик проверяем существование файла

                elif self._shared_handler and not self._master_logger:
                    # Аномалия: флаг установлен, а мастера нет – сбрасываем
                    self.logger.warning(
                        f"Логгер '{self.name}' имеет _shared_handler=True, но _master_logger отсутствует. Сбрасываю флаг."
                    )
                    self._update_file_handler_if_not_shared()
                    
                elif not self._shared_handler and self._file_enabled:
                    # уже создали, ничего не делаем
                    pass

                else:
                    # Случай, когда не общий и файловое логирование выключено – ничего не делаем
                    pass     

        _tt()

        # S1: логгер со ссылкой на родителя (enable_file_logging='system') подключается к
        # обработчику родителя, если у того файл реально открыт и это тот же файл.
        # Раньше привязка проверяла аргумент конструктора родителя и не срабатывала.
        # share_file_handler_with() сам ещё раз вызовет _update_handlers() — уже по ветке
        # «общий обработчик», так что повторного входа сюда не будет.
        if (
            self._enabled
            and self._file_enabled
            and not self._shared_handler
            and self.file_handler is None
        ):
            parent = self._file_share_target()
            if parent is not None:
                self.share_file_handler_with(parent)

        # Добавляем глобальные обработчики обратно (например, для GUI-логов) (безопасное копирование)
        # Убедимся, что глобальные обработчики присутствуют (они не удалялись, но на всякий случай)
        # for handler in self._global_handlers:
        #     if handler not in self.logger.handlers:
        #         self.logger.addHandler(handler)

        # with type(self)._global_handlers_lock:
        #     handlers_copy = list(type(self)._global_handlers)
        # with BaseAppLogger._global_handlers_lock:
        #     handlers_copy = list(BaseAppLogger._global_handlers)

        # for handler in handlers_copy:
        #     if handler not in self.logger.handlers:
        #         self.logger.addHandler(handler)        
        
        self._save_handlers() # Сохраняем ссылки на обработчики (может пригодиться для GUI)  
        
        # Синхронизируем зависимые логгеры (которые используют наш файловый обработчик)  (уже вне блокировки) # намеренно тут, что бы 1н раз после всех условий...
        if self._shared_slaves: # Если есть зависимые логгеры
            self._update_shared_slaves() # Синхронизируем зависимые логгеры

        # self._save_handlers() # Сохраняем ссылки на обработчики (может пригодиться для GUI)               

    def _create_file_handler(self) -> RobustRotatingFileHandler:
        """
        Создаёт файловый обработчик по текущим настройкам (папка создаётся при необходимости).

        Порог обработчика — ``NOTSET`` (фильтрует уровень логгера; файл может стать общим, S3).

        Returns:
            Новый ``RobustRotatingFileHandler`` (в ``logging.Logger`` не добавлен).

        Raises:
            RuntimeError: Не удалось создать папку для логов.

        Пример:
            >>> h = log._create_file_handler(); h.baseFilename
            'C:\\proj\\logs\\app.log'
        """

        log_file = self._get_log_file() # Возвращает имя файла лога с учётом use_name_in_filename

        log_dir = os.path.dirname(log_file) # Получаем директорию

        if log_dir and not os.path.exists(log_dir): # Если директория не существует
            try:
                os.makedirs(log_dir, exist_ok=True)

            except OSError as e:
                raise RuntimeError(f"Не удалось создать директорию для логов {log_dir}: {e}") from e

        # handler = RotatingFileHandler(
        handler = RobustRotatingFileHandler(
            filename=log_file,
            maxBytes=self.log_max_bytes,
            backupCount=self.log_backup_count,
            encoding='utf-8'
        )

        # handler.setLevel(self.log_level) # Устанавливаем уровень
        # ↑ до S3. Порог задаёт уровень каждого логгера (logging.Logger.setLevel): файл может
        #   стать общим, и тогда уровень создавшего логгера заглушал бы остальных (S3, IMPLEMENTATION.md §5.2: общий обработчик не фильтрует по уровню одного логгера).
        #   Отдельный порог файла по-прежнему можно задать через set_file_level().
        handler.setLevel(logging.NOTSET)
        handler.setFormatter(self.formatter) # Устанавливаем формат

        return handler

    def _get_log_file(self) -> str:
        """
        Итоговый путь к файлу лога из ``base_log_file`` (правила — IMPLEMENTATION.md §3.5).

        * существующая папка или путь с разделителем на конце → ``<папка>/app.log``
          (или ``<имя>.log``, с меткой времени при ``use_timestamp``);
        * несуществующий путь на ``.log`` или существующий файл → он сам;
        * иначе путь считается папкой.

        Returns:
            Путь к файлу.

        Raises:
            ValueError: ``base_log_file`` не задан.

        Пример:
            >>> log.base_log_file = 'logs/'; log._get_log_file()
            'logs\\app.log'
        """
        if not self.base_log_file:
            raise ValueError("base_log_file (LOG_DIR) не задан")

        path = os.path.normpath(self.base_log_file)   # нормализуем

        # 1. Если путь существует – определяем по факту
        if os.path.exists(path):
            if os.path.isdir(path):
                # Это существующая директория
                return self._build_log_file_in_dir(path)
            else:
                # Это существующий файл (или симлинк) – используем как есть
                return path

        # 2. Путь не существует – пытаемся угадать намерение
        # Если путь явно заканчивается на разделитель – считаем директорией
        if path.endswith(('/', '\\')):
            return self._build_log_file_in_dir(path.rstrip('/\\'))

        # Если путь оканчивается на .log — считаем его файлом.
        # ВАЖНО: если пользователь хотел указать директорию, имя которой оканчивается на .log,
        # он должен добавить завершающий разделитель (слеш). Иначе будет создан файл.
        if path.lower().endswith('.log'):
            # Если путь не существует и оканчивается на .log, считаем его файлом.
            # Если пользователь хотел указать директорию с именем, оканчивающимся на .log,
            # он должен добавить завершающий разделитель (слеш).
            # if hasattr(self, 'logger') and self.logger:
            #     self.logger.debug(
            #         f"Интерпретация пути '{path}' как файла, так как он оканчивается на .log. "
            #         "Если вы имели в виду директорию, добавьте завершающий слеш."
            #     )
            return path   
        
        # basename = os.path.basename(path)
        # # Если путь содержит расширение .log (или другое стандартное) – считаем файлом
        # if path.lower().endswith('.log') and '.' in basename and basename.count('.') == 1:
        #     return path

        # if path.lower().endswith('.log') and os.path.splitext(path)[1].lower() == '.log':
        #     # Директория будет создана в _create_file_handler

        #     # # Создаём родительскую директорию, если её нет (будет позже в _create_file_handler,
        #     # # но можно сразу для ясности)
        #     # parent = os.path.dirname(path)
        #     # if parent and not os.path.exists(parent):
        #     #     os.makedirs(parent, exist_ok=True)

        #     return path

        # Иначе предполагаем, что пользователь указал директорию (без слеша)
        return self._build_log_file_in_dir(path)

    def _build_log_file_in_dir(self, dir_path: str) -> str:
        """
        Имя файла внутри папки: ``app.log`` / ``<имя>.log``, с ``_<YYYYmmdd_HHMMSS>`` при ``use_timestamp``.

        Метка времени — момент создания логгера (``_start_timestamp``).

        Args:
            dir_path: Папка для логов.

        Returns:
            Путь к файлу в этой папке.

        Пример:
            >>> log._build_log_file_in_dir('logs')
            'logs\\app.log'
        """
        
        timestamp = self._start_timestamp
        
        # name =  f"{self.name}" if self.use_name_in_filename else f"app"
        name = self.name if self.use_name_in_filename else "app"  # P3: f-строки без подстановок
        
        if self.use_name_in_filename:
            timestamp = timestamp if self.use_timestamp else ""
            name = f"{name}_{timestamp}" if timestamp else name
            # filename = f"{base_name}.log"
        else:
            if self.use_timestamp:
                name = f"{name}_{timestamp}"

        filename = f"{name}.log" 

        return os.path.join(dir_path, filename)    

    def _sync_log_level_and_formatters (self) -> None:
        """
        Ставит текущий форматтер файловому обработчику.

        Уровень больше не ставится (S3): файл может быть общим. Название историческое.

        Returns:
            None

        Пример:
            >>> log._sync_log_level_and_formatters()
        """
        # Синхронизируем уровень и формат для файлового обработчика
        if self.file_handler: # Если есть файловый обработчик
            # self.file_handler.setLevel(self.log_level) # устанавливаем уровень
            # ↑ до S3: уровень файла = уровень логгера; файл общий → заглушал других (S3, IMPLEMENTATION.md §5.2: общий обработчик не фильтрует по уровню одного логгера)
            self.file_handler.setFormatter(self.formatter) # устанавливаем формат 
 
    # def _sync_formatters (self, formatter):
    #     # Синхронизация форматирования
    #     self.formatter = formatter
    #     if self.file_handler:
    #         self.file_handler.setFormatter(self.formatter)

    def _set_file_handler (self, file_handler: logging.Handler) -> None:
        """
        Делает ``file_handler`` текущим файловым обработчиком и добавляет его в ``logging.Logger``.

        Args:
            file_handler: Обработчик (обычно — мастера).

        Returns:
            None

        Пример:
            Вызывается из ``share_file_handler_with``.
        """
        # Берём обработчик другого логгера
        self.file_handler = file_handler

        # Добавляем, если ещё не добавлен (защита от дублирования)
        if self.file_handler not in self.logger.handlers:
            self.logger.addHandler(self.file_handler)

    def _remove_console_handler (self, if_close_console_handler: bool = True) -> None:
        """
        Снимает консольный обработчик (если есть) и, по желанию, закрывает его.

        Args:
            if_close_console_handler: Закрыть после снятия.

        Returns:
            None

        Пример:
            >>> log._remove_console_handler(); log.console_handler is None
            True
        """
        # Удаляем старые "свои" обработчики, если они были
        if self.console_handler:
            self.logger.removeHandler(self.console_handler)

            if if_close_console_handler:
                self.console_handler.close()

            self.console_handler = None

    def _remove_file_handler (self, if_close_file_handler: bool = True) -> None:
        """
        Снимает файловый обработчик (если есть) и, по желанию, закрывает его.

        Общий обработчик мастера закрывать нельзя — передавайте ``False``.

        Args:
            if_close_file_handler: Закрыть после снятия.

        Returns:
            None

        Пример:
            >>> slave._remove_file_handler(if_close_file_handler=False)
        """
        # Удаляем текущий файловый обработчик, если есть
        if self.file_handler:
            self.logger.removeHandler(self.file_handler)

            if if_close_file_handler:
                self.file_handler.close()

            self.file_handler = None
