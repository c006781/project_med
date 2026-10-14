# app/utils/logger/_modes.py

"""
Часть ``BaseAppLogger``: Режимы на лету.

Содержит примесь ``_ModesMixin``: enable/disable, консоль, файл, уровни, reconfigure, свойства, close.
Сам по себе модуль не используется — класс собирается в ``base_logger.py``:
``class BaseAppLogger(_ModesMixin, ...)``. Методы перенесены из ``base_logger.py``
(2026-10-14) без изменений, вместе с комментариями и закомментированным старым кодом.

Имя ``BaseAppLogger`` внутри методов (``BaseAppLogger._share_lock`` и т. п.) указывает
на итоговый класс: ``base_logger.py`` подставляет его в этот модуль сразу после создания
класса (до первого вызова любого метода).

Пример:
    >>> from app.utils.logger.base_logger import BaseAppLogger
    >>> issubclass(BaseAppLogger, _ModesMixin)
    True
"""

import logging
import sys
from typing import Any, Union

import warnings


from ._common import LOGGER_CODE_FILES

LOGGER_CODE_FILES.append((lambda: None).__code__.co_filename)

# Подставляется в base_logger.py после создания класса (см. докстринг модуля)
BaseAppLogger: Any = None


class _ModesMixin:
    """
    Примесь ``BaseAppLogger``: enable/disable, консоль, файл, уровни, reconfigure, свойства, close.

    Отдельно не используется: атрибуты и блокировки (``_instances``, ``_handler_lock``…)
    объявлены в ``BaseAppLogger``.

    Пример:
        >>> BaseAppLogger.__mro__  # doctest: +ELLIPSIS
        (<class '...BaseAppLogger'>, <class '..._ModesMixin'>, ...)
    """

    def _retire(self) -> None:
        """
        Выводит экземпляр из работы перед заменой через ``get_instance(force_new=True)``.

        ``logging.getLogger(name)`` один на имя, поэтому старый и новый экземпляр
        делят один ``logging.Logger``. Чтобы не было дублей, старый снимает с него
        свои обработчики:
            * консоль — снимается и закрывается;
            * свои функции вывода (``add_output``) — снимаются и закрываются;
            * файл: если пишет через чужой (общий) — отцепляется у мастера, не закрывая;
              если свой и через него пишут слейвы — снимается, но не закрывается
              (слейвы продолжают писать); иначе — снимается и закрывается.

        Постоянный ``NullHandler`` и глобальные обработчики остаются — они общие.
        Сам объект продолжает работать: его вызовы идут через обработчики нового
        экземпляра (тот же ``logging.Logger``).

        Returns:
            None

        Пример:
            >>> old = AppLogger.get_instance('svc')
            >>> new = AppLogger.get_instance('svc', force_new=True)   # внутри old._retire()
        """
        with BaseAppLogger._share_lock:
            with self._handler_lock:
                self._remove_console_handler(if_close_console_handler=True)

                for output in list(getattr(self, '_outputs', [])):
                    self.logger.removeHandler(output)
                    output.close()
                if hasattr(self, '_outputs'):
                    self._outputs.clear()

                if self.file_handler is not None:
                    if self._shared_handler:
                        self._unshare_file_handler_master_logger()
                        self._remove_file_handler(if_close_file_handler=False)
                    else:
                        live_slaves, _ = self._get_shared_slaves()
                        self._remove_file_handler(if_close_file_handler=not live_slaves)

                self.file_handler = None
                self._shared_handler = False
                self._master_logger = None

            self._save_handlers()

    def _report_self_problem(self, message: str) -> None:
        """
        Сообщает о проблеме в настройке самого логгера (не о событии приложения).

        Пока у логгера нет своего вывода (например, во время ``__init__``), сообщение
        идёт прямо в stderr; иначе — через сам логгер уровнем ERROR. Без этого
        сообщение поглотил бы постоянный ``NullHandler`` (R6).

        Args:
            message: Текст сообщения.

        Returns:
            None

        Пример:
            >>> log._report_self_problem("Циклическая ссылка в effective_enable_file_logging для a")
        """
        if self._has_output_handlers():
            self.logger.error(message)
        else:
            print(f"ERROR: {message}", file=sys.stderr)

    def get_level(self) -> str:
        """
        Текущий уровень логгера по имени.

        Returns:
            ``'DEBUG'``, ``'INFO'``, … (для нестандартного числа — ``'Level N'``).

        Пример:
            >>> AppLogger.get_instance('system').get_level()
            'DEBUG'
        """
        return logging.getLevelName(self.log_level)

    def set_formatter(self, formatter: logging.Formatter) -> None:
        """
        Ставит форматтер всем обработчикам логгера и запоминает его для будущих.

        Затрагивает и общие обработчики (файл мастера, глобальные), а также выводы
        ``add_output`` без своего форматтера. Переживает перестроения обработчиков.

        Args:
            formatter: Новый ``logging.Formatter``.

        Returns:
            None

        Пример:
            >>> log.set_formatter(logging.Formatter('%(asctime)s %(plain_message)s'))
        """
        with self._handler_lock:
            self.formatter = formatter
            
            for handler in self.logger.handlers:
                handler.setFormatter(formatter)

        if self._shared_slaves:
            self._update_shared_slaves()
            # for slave in self._shared_slaves:
            #     slave.set_formatter(formatter)

    # def _reopen_file_handler(self):
    #     """Принудительно переоткрывает файловый обработчик (удаляет и создаёт заново)."""
    #     if self.file_handler:
    #         self.logger.removeHandler(self.file_handler)
    #         self.file_handler.close()
    #         self.file_handler = self._create_file_handler()
    #         self.logger.addHandler(self.file_handler)

    #         # if self._shared_slaves:
    #         self._update_shared_slaves()

    # def _reopen_file_handler_if_needed(self):
    #     """Переоткрывает файловый обработчик, если он существует и файл отсутствует."""
    #     if self.file_handler and hasattr(self.file_handler, 'force_reopen'):
    #         # Проверяем существование файла
    #         log_file = self._get_log_file()
    #         if not os.path.exists(log_file):
    #             self.file_handler.force_reopen()
    #             self.logger.debug(f"Файл лога {log_file} переоткрыт (был удалён)")

    def setLevel(self, level: Union[int, str]) -> None:
        """
        Меняет порог только у ``logging.Logger`` (как ``logging.Logger.setLevel``).

        ``log_level`` и ``get_level()`` не меняются, после перестроения или перезагрузки
        конфига порог вернётся. Для полной смены уровня — ``reconfigure(level=...)``.

        Args:
            level: Число или имя уровня (как принимает ``logging``).

        Returns:
            None

        Пример:
            >>> log.setLevel(logging.ERROR)
        """
        self.logger.setLevel(level)
        # super().setLevel(level)
        if self._shared_slaves:
            self._update_shared_slaves()

    def is_enabled(self) -> bool:
        """
        Включён ли логгер целиком (``enable()``/``disable()``, ключ ``enabled``).

        Список отключённых (``add_disabled_logger``) на результат не влияет.

        Returns:
            ``True``, если логгер включён.

        Пример:
            >>> log.disable(); log.is_enabled()
            False
        """
        return self._enabled

    def is_console_enabled(self) -> bool:
        """
        Включён ли вывод в консоль (флаг, а не наличие обработчика).

        Returns:
            ``True``, если консоль включена.

        Пример:
            >>> log.disable_console(); log.is_console_enabled()
            False
        """
        return self._console_enabled

    def is_file_enabled(self) -> bool:
        """
        Включена ли запись в файл — ТЕКУЩЕЕ состояние (в отличие от ``effective_enable_file_logging``).

        Returns:
            ``True``, если файл включён.

        Пример:
            >>> log.enable_file(); log.is_file_enabled()
            True
        """
        return self._file_enabled
    
    def set_console_level(self, level_str: Union[str, int]) -> None:
        """
        Отдельный порог консоли (выше уровня логгера смысла не имеет ниже — логгер отфильтрует раньше).

        Действует до следующего перестроения обработчиков; в ``reconfigure(console_level=...)``
        применяется после перестроения (R4).

        Args:
            level_str: Имя уровня или число.

        Returns:
            None

        Пример:
            >>> log.set_console_level('ERROR')   # в консоль только ошибки, в файл — всё
        """
        level = self._parse_log_level(level_str)
        if self.console_handler:
            self.console_handler.setLevel(level)

    def set_file_level(self, level_str: Union[str, int]) -> None:
        """
        Отдельный порог файлового обработчика.

        Если файл общий, порог действует на всех, кто через него пишет.

        Args:
            level_str: Имя уровня или число.

        Returns:
            None

        Пример:
            >>> log.set_file_level('WARNING')
        """
        level = self._parse_log_level(level_str)
        if self.file_handler:
            self.file_handler.setLevel(level)

    def _update_file_params(self, **kwargs: Any) -> bool:
        """
        Обновляет параметры файла из аргументов ``reconfigure``.

        Учитываются: ``base_log_FILE``, ``log_MAX_BYTES``, ``log_BACKUP_COUNT``,
        ``use_timestamp``, ``use_name_in_filename``, ``enable_file_logging``.

        Args:
            **kwargs: Аргументы ``reconfigure``; остальные ключи игнорируются.

        Returns:
            ``True``, если хоть один параметр передан и нужно перестроить обработчики.

        Пример:
            >>> log._update_file_params(log_MAX_BYTES='2048')
            True
        """
        need_rebuild = False
        if 'base_log_FILE' in kwargs:
            self.base_log_file = kwargs['base_log_FILE']
            need_rebuild = True

        if 'log_MAX_BYTES' in kwargs:
            self.log_max_bytes = int(kwargs['log_MAX_BYTES'])
            need_rebuild = True

        if 'log_BACKUP_COUNT' in kwargs:
            self.log_backup_count = int(kwargs['log_BACKUP_COUNT'])
            need_rebuild = True

        if 'use_timestamp' in kwargs:
            # self.use_timestamp = kwargs['use_timestamp']
            self.use_timestamp = self._to_bool(kwargs['use_timestamp'])
            need_rebuild = True

        if 'use_name_in_filename' in kwargs:
            # self._use_name_in_filename = kwargs['use_name_in_filename']
            # if isinstance(kwargs['use_name_in_filename'], str):
            #     self._use_name_in_filename = self.effective_use_name_in_filename(_visited=None)
            # else:
            #     self._use_name_in_filename = bool(kwargs['use_name_in_filename'])

            # need_rebuild = True


            val = kwargs['use_name_in_filename']
            if isinstance(val, str):
                self._use_name_in_filename = self._to_bool(val)
            else:
                self._use_name_in_filename = bool(val)
            need_rebuild = True

        if 'enable_file_logging' in kwargs:
            # P7 (2026-10-14): синоним file_enabled — оставлен для совместимости.
            warnings.warn(
                "reconfigure(enable_file_logging=...) устарел: используйте file_enabled=...",
                DeprecationWarning,
                stacklevel=3,
            )
            # warnings.warn("'enable_file_logging' устарел, используйте 'file_enabled'", DeprecationWarning)
            # self._file_enabled = bool(kwargs['enable_file_logging'])
            # if isinstance(kwargs['enable_file_logging'], str):
            #     self._file_enabled = self.effective_enable_file_logging(_visited=None) 
            # else:
            #     self._file_enabled = bool(kwargs['enable_file_logging'])
      
            # need_rebuild = True
            val = kwargs['enable_file_logging']
            if isinstance(val, str):
                self._file_enabled = self._to_bool(val)
            else:
                self._file_enabled = bool(val)
            need_rebuild = True

        if need_rebuild and self.file_handler:
            # После изменения параметров, если обработчик существует, переоткрываем его
            self._reopen_file_handler_if_needed()

        return need_rebuild

    def _update_flags(self, **kwargs: Any) -> bool:
        """
        Обновляет флаги включения: ``enabled``, ``console_enabled``, ``file_enabled``.

        Отдельные уровни ``console_level`` / ``file_level`` здесь НЕ применяются:
        их ставит ``reconfigure()`` после перестроения обработчиков, иначе
        перестроение тут же сбросило бы их к общему уровню (исправление R4,
        IMPLEMENTATION.md §5.1).

        Args:
            **kwargs: Аргументы ``reconfigure()``; учитываются только перечисленные
                флаги, значения приводятся через ``_to_bool``.

        Returns:
            ``True``, если хотя бы один флаг был передан и нужно перестроить обработчики.

        Пример:
            >>> log._update_flags(console_enabled='False')
            True
            >>> log._update_flags(level='INFO')
            False
        """
        need_rebuild = False
        # level_changed = False
        # ↑ P3: после исправления R4 отдельные уровни здесь не применяются — не используется.

        if 'console_enabled' in kwargs:
            self._console_enabled = self._to_bool(kwargs['console_enabled'])
            need_rebuild = True

        if 'file_enabled' in kwargs:
            self._file_enabled = self._to_bool(kwargs['file_enabled'])
            need_rebuild = True

        if 'enabled' in kwargs:
            self._enabled = self._to_bool(kwargs['enabled'])
            need_rebuild = True

        # # Отдельные уровни для консоли и файла (не требуют перестройки)
        # if 'console_level' in kwargs:
        #     self.set_console_level(kwargs['console_level'])
        #     level_changed = True
        #
        # if 'file_level' in kwargs:
        #     self.set_file_level(kwargs['file_level'])
        #     level_changed = True
        #
        # return need_rebuild or level_changed
        # ↑ до исправления R4: уровень ставился здесь, а True в ответе запускал
        #   _update_handlers(), который пересоздавал консоль с общим уровнем.
        #   Теперь отдельные уровни применяет reconfigure() после перестроения.

        return need_rebuild

    def reconfigure(self, **kwargs: Any) -> None:
        """
        Меняет настройки логгера на лету.

        Поддерживаемые ключи:
            * ``level`` — уровень (имя или число);
            * ``console_enabled``, ``file_enabled``, ``enabled`` — флаги (bool или строка);
            * ``enable_file_logging`` — то же, что ``file_enabled``;
            * ``base_log_FILE``, ``log_MAX_BYTES``, ``log_BACKUP_COUNT``, ``use_timestamp``,
              ``use_name_in_filename`` — параметры файла;
            * ``log_ARGS``, ``show_call_depth`` — поведение;
            * ``console_level``, ``file_level`` — отдельные пороги (после перестроения, R4).

        У слейва параметры файла уходят мастеру (файл общий), остальное меняется у
        самого слейва (S3). Неизвестные ключи игнорируются.

        Args:
            **kwargs: Настройки из списка выше.

        Returns:
            None

        Пример:
            >>> log.reconfigure(level='DEBUG', console_enabled=False)
            >>> log.reconfigure(base_log_FILE='D:/logs/', log_MAX_BYTES=50_000_000)
        """
        # # Если используем общий обработчик, перенаправляем вызов мастеру
        # if self._shared_handler and self._master_logger:
        #     # self.logger.debug(f"Перенаправляю reconfigure мастеру '{self._master_logger.name}'")
        #     self._master_logger.reconfigure(**kwargs)
        #     return
        # ↑ до S3: слейв перенаправлял мастеру ВСЁ, включая уровень и флаги, — вызов
        #   slave.reconfigure(level=...) менял уровень мастеру (и его файлу), а не слейву.
        # Теперь мастеру уходят только параметры общего файла (путь, ротация, имя файла):
        # файл один на всех, менять его может только владелец. Уровень и флаги — свои.
        if self._shared_handler and self._master_logger:
            file_kwargs = {k: v for k, v in kwargs.items() if k in self._SHARED_FILE_PARAMS}
            if file_kwargs:
                self._master_logger.reconfigure(**file_kwargs)
            kwargs = {k: v for k, v in kwargs.items() if k not in self._SHARED_FILE_PARAMS}
            if not kwargs:
                return
        
        # Обновляем уровень логирования

        level_changed = False
        if 'level' in kwargs:
            self._update_level(kwargs['level'])
            level_changed = True

        # Обновляем log_args (не влияет на обработчики, просто сохраняем)
        if 'log_ARGS' in kwargs:
            self.log_args = kwargs['log_ARGS']

        if 'show_call_depth' in kwargs:
            self._show_call_depth = self._to_bool(kwargs['show_call_depth'])
            # не требует перестройки обработчиков
 
        # Обновляем параметры файла (сохраняем всегда, пересоздадим обработчики в конце)

        need_rebuild = self._update_file_params(**kwargs)
        flags_changed = self._update_flags(**kwargs)
        need_rebuild = need_rebuild or flags_changed

        if need_rebuild:
            self._update_handlers() # внутри вызывает _update_shared_slaves при наличии зависимых
            # После перестроения обработчика уведомляем зависимых
            # self._update_shared_slaves()
        # elif level_changed:
        #     # Уровень изменился, но обработчики не перестраивались – синхронизируем зависимых вручную
        #     self._update_shared_slaves()
        elif level_changed or flags_changed:
            # Если менялся только уровень, но обработчик не пересоздавался, тоже нужно синхронизировать
            # if 'level' in kwargs:
            self._update_shared_slaves()

        # Отдельные уровни консоли/файла — строго ПОСЛЕ перестроения обработчиков,
        # иначе _update_handlers() пересоздаст их с общим уровнем (R4).
        if 'console_level' in kwargs:
            self.set_console_level(kwargs['console_level'])

        if 'file_level' in kwargs:
            self.set_file_level(kwargs['file_level'])
    
    def _set_enabled(self, value: bool) -> bool:
        """
        Меняет флаг ``enabled`` под блокировкой.

        Args:
            value: Новое значение.

        Returns:
            ``True``, если значение изменилось (нужно перестроить обработчики).

        Пример:
            >>> log._set_enabled(False)
            True
        """
        with self._handler_lock:
            if self._enabled != value:
                self._enabled = value

                return True
            
        return False
    


    def _set_console_enabled(self, value: bool) -> bool:
        """
        Меняет флаг ``console_enabled`` под блокировкой.

        Args:
            value: Новое значение.

        Returns:
            ``True``, если значение изменилось.

        Пример:
            >>> log._set_console_enabled(False)
            True
        """
        with self._handler_lock:
            if self._console_enabled != value:
                self._console_enabled = value

                return True
            
        return False

    def _set_file_enabled(self, value: bool) -> bool:
        """
        Меняет флаг ``file_enabled`` под блокировкой.

        Args:
            value: Новое значение.

        Returns:
            ``True``, если значение изменилось.

        Пример:
            >>> log._set_file_enabled(True)
            True
        """
        with self._handler_lock:
            if self._file_enabled != value:
                self._file_enabled = value

                return True
            
        return False

    def enable(self) -> None:
        """
        Включает логгер целиком: консоль, файл и выводы — по их флагам.

        Returns:
            None

        Пример:
            >>> log.disable(); log.enable()
            >>> log.info('снова пишу')
        """
        if self._set_enabled(True):
            self._update_handlers()

    def disable(self) -> None:
        """
        Выключает логгер целиком: методы и декоратор молчат, консоль и файл сняты.

        Настройки (флаги консоли, файла) сохраняются и вернутся при ``enable()``. У мастера
        с полной синхронизацией выключатся и слейвы (S4).

        Returns:
            None

        Пример:
            >>> log.disable(); log.error('не будет записано')
        """
        if self._set_enabled(False):
            self._update_handlers()

    def enable_console(self) -> None:
        """
        Включает вывод в консоль (stderr).

        Returns:
            None

        Пример:
            >>> log.enable_console()
        """
        if self._set_console_enabled(True):
            self._update_handlers()

    def disable_console(self) -> None:
        """
        Выключает вывод в консоль; файл и выводы-функции продолжают работать.

        Returns:
            None

        Пример:
            >>> log.disable_console()
        """
        if self._set_console_enabled(False):
            self._update_handlers()

    def enable_file(self) -> None:
        """
        Включает запись в файл — короткое имя для ``turn_on_file_logging()``.

        Returns:
            None

        Пример:
            >>> log.enable_file()
        """
        self.turn_on_file_logging()

    def disable_file(self) -> None:
        """
        Выключает запись в файл — короткое имя для ``turn_off_file_logging()``.

        Returns:
            None

        Пример:
            >>> log.disable_file()
        """
        self.turn_off_file_logging()

    def turn_on_file_logging(self) -> None:
        """
        Включает запись в файл для этого логгера.

        Поведение:
            * файл уже включён и обработчик есть — только проверяет, что файл на диске
              существует (переоткрывает, если его удалили);
            * файл уже включён, но обработчика нет (например, логгер был выключен
              целиком) — перестраивает обработчики;
            * логгер пишет через общий обработчик другого логгера — ничего не делает
              и пишет предупреждение (сначала ``unshare_file_handler()``);
            * иначе — включает флаг и создаёт свой файловый обработчик.

        Решение принимается по ТЕКУЩЕМУ состоянию ``is_file_enabled()``, а не по
        аргументу ``enable_file_logging`` конструктора (исправление R2,
        IMPLEMENTATION.md §5.1).

        Returns:
            None

        Пример:
            >>> log = AppLogger.get_instance('svc', enable_file_logging=True)
            >>> log.turn_off_file_logging()
            >>> log.turn_on_file_logging()
            >>> log.is_file_enabled()
            True
        """
        # if self.effective_enable_file_logging(_visited=None):
        # ↑ до исправления R2: effective_enable_file_logging() — это аргумент конструктора
        #   (или родителя по ссылке), а не текущее состояние. У логгера, созданного с
        #   enable_file_logging=True, после disable_file() метод считал файл «уже
        #   включённым» и ничего не делал.
        if self._file_enabled:
            # логирование уже включено, вызвать self._reopen_file_handler_if_needed() и затем вернуться

            if self.file_handler is None:
                # Обработчик отсутствует – создаём его без перестройки всего
                self._update_handlers()  

            self._reopen_file_handler_if_needed()

            return
    
        if self._shared_handler:
            self.logger.warning(
                f"Логгер '{self.name}' использует общий обработчик. "
                "Включение файлового логирования невозможно. "
                "Сначала вызовите unshare_file_handler()."
            )
            return
        
        # with self._handler_lock:
        #     self._file_enabled = True
        if self._set_file_enabled(True):
            self._update_handlers()

            self._reopen_file_handler_if_needed() # после перестроения обработчиков проверяем существование файл
        # self._reopen_file_handler_if_needed() # после перестроения обработчиков проверяем существование файл
           

    def turn_off_file_logging(self) -> None:
        """
        Выключает запись в файл для этого логгера.

        Поведение:
            * если у логгера есть слейвы (другие логгеры пишут через его обработчик) —
              сначала отвязывает их: каждый создаёт свой обработчик по своим настройкам;
            * если запись в файл уже выключена — больше ничего не делает;
            * если логгер сам пишет через чужой (общий) обработчик — отвязывается от него,
              не закрывая его (им пользуется мастер и другие слейвы);
            * иначе — закрывает свой файловый обработчик.

        Решение принимается по ТЕКУЩЕМУ состоянию ``is_file_enabled()``, а не по
        аргументу конструктора (исправление R3, IMPLEMENTATION.md §5.1).

        Returns:
            None

        Пример:
            >>> log = AppLogger.get_instance('svc')        # без файла
            >>> log.turn_on_file_logging()
            >>> log.turn_off_file_logging()
            >>> log.file_handler is None
            True
        """
        if self._shared_slaves:
            with BaseAppLogger._share_lock:
                # Используем копию списка, так как он будет изменяться
                for slave_ref in self._shared_slaves[:]:
                    slave = slave_ref()
                    if slave is not None:
                        slave.unshare_file_handler(if_update_handlers=True)

        # Если файловое логирование уже отключено, ничего не делаем
        # if not self.effective_enable_file_logging(_visited=None):
        # ↑ до исправления R3: проверялся аргумент конструктора. У логгера, созданного
        #   без enable_file_logging=True, включённый позже файл нельзя было выключить.
        if not self._file_enabled:
            return
        
        # Если логгер использует общий обработчик (мастер)
        if self._shared_handler:                  
            # Отвязываемся от общего обработчика (без автоматического перестроения,
            # чтобы избежать рекурсивных вызовов)      
            self.unshare_file_handler( # Отвязываемся от общего обработчика, затем отключаем своё файловое логирование
                if_update_handlers=False
            )

            # Критическая секция: сброс флагов и удаление обработчика
            with self._handler_lock:

                # Дополнительная проверка: убеждаемся, что отвязка прошла успешно
                if self._shared_handler:
                    self.logger.warning(
                        f"Логгер '{self.name}' не смог отвязаться от общего обработчика, "
                        "принудительно сбрасываю флаги."
                    )
                    self._shared_handler = False
                    self._master_logger = None

                # Явно удаляем файловый обработчик (на случай, если он остался)
                if self.file_handler:   
                    # Удаляем из списка обработчиков, но не закрываем
                    if self.file_handler in self.logger.handlers:
                        self._remove_file_handler(
                            if_close_file_handler=True
                        )
                    
                # self._file_enabled = False     

            # self._file_enabled = False # После отвязки у нас будет свой обработчик (или None), теперь отключаем
            if self._set_file_enabled(False):
                # self._save_handlers() # есть в _update_handlers
                self._update_handlers()  # Перестраиваем обработчики (этот метод сам захватит _handler_lock при необходимости)
            

            return
        
        # Обычное отключение (свой обработчик)
        # with self._handler_lock:
        #     self._file_enabled = False
        # self._set_file_enabled(False)

        # self._update_handlers()

        if self._set_file_enabled(False):
            self._update_handlers()

    def _update_level(self, new_level: Union[str, int]) -> None:
        """
        Меняет уровень логгера: ``log_level``, порог ``logging.Logger`` и своей консоли.

        Общие обработчики (файл, глобальные) не трогаются (S3).

        Args:
            new_level: Имя уровня или число.

        Returns:
            None

        Пример:
            >>> log._update_level('ERROR'); log.get_level()
            'ERROR'
        """
        level = self._parse_log_level(new_level)
        if level != self.log_level:
            self.log_level = level
            self.logger.setLevel(level)
            # for handler in self.logger.handlers:
            # handler.setLevel(level)
            # ↑ до S3: уровень ставился и общим/глобальным обработчикам, заглушая других
            #   логгеров (S3, IMPLEMENTATION.md §5.2: общий обработчик не фильтрует по уровню одного логгера). Теперь — только своей консоли.
            if self.console_handler:
                self.console_handler.setLevel(level)
   
    # @property
    # def enable_file_logging(self):
    #     if self._enable_file_logging_ref:
    #         parent = self._instances.get(self._enable_file_logging_ref)
    #         if parent is not None:
    #             return parent.enable_file_logging
    #     return self._enable_file_logging


    # @enable_file_logging.setter
    # def enable_file_logging(self, value):
    #     if self._enable_file_logging_ref:
    #         parent = self._instances.get(self._enable_file_logging_ref)
    #         if parent is not None:
    #             parent.enable_file_logging = value
    #             return
    #     self._enable_file_logging = value
    #     self._update_file_handler()

    # ----------------------------------------------------------------------
    # Свойство enable_file_logging (для обратной совместимости)
    # ----------------------------------------------------------------------

    @property
    def enable_file_logging(self) -> bool:
        """
        Включена ли запись в файл (то же, что ``is_file_enabled()``).

        Returns:
            ``True``, если файл включён.

        Пример:
            >>> log.enable_file_logging
            True
        """
        return self._file_enabled

    @enable_file_logging.setter
    def enable_file_logging(self, value: bool) -> None:
        """
        Включает/выключает файл через присваивание: ``log.enable_file_logging = False``.

        Не ``bool`` приводится к ``bool`` с ``DeprecationWarning``.

        Args:
            value: ``True`` — ``turn_on_file_logging()``, ``False`` — ``turn_off_file_logging()``.

        Returns:
            None

        Пример:
            >>> log.enable_file_logging = False
        """
        # P7 (2026-10-14): устаревшее — оставлено для совместимости, не удаляется.
        warnings.warn(
            'Присваивание log.enable_file_logging = ... устарело: используйте log.enable_file() / log.disable_file().',
            DeprecationWarning,
            stacklevel=2,
        )

        if not isinstance(value, bool):
            warnings.warn(
                f"enable_file_logging = {value} должен быть bool. Используйте turn_on_file_logging/turn_off_file_logging для управления.",
                DeprecationWarning
            )
            value = bool(value)

        if value:
            self.turn_on_file_logging()
        else:
            self.turn_off_file_logging()

 # --- Свойства для динамического получения значений от родителя ---

    @property
    def use_name_in_filename(self) -> bool:
        """
        Пишет ли логгер в файл ``<имя>.log`` вместо общего ``app.log``.

        Returns:
            Текущее значение флага.

        Пример:
            >>> AppLogger.get_instance('svc', use_name_in_filename=True).use_name_in_filename
            True
        """
        return self._use_name_in_filename

    @use_name_in_filename.setter
    def use_name_in_filename(self, value: bool) -> None:
        """
        Переключает отдельный файл ``<имя>.log`` и сразу перестраивает обработчики.

        Args:
            value: ``True`` — свой файл, ``False`` — общий ``app.log``.

        Returns:
            None

        Пример:
            >>> log.use_name_in_filename = True    # дальше пишет в logs/<имя>.log
        """
        self._use_name_in_filename = value
        self._update_handlers()   # перестроить обработчики, чтобы применить новое имя файла


    # @property
    # def use_name_in_filename(self):
    #     if self._use_name_in_filename_ref:
    #         parent = self._instances.get(self._use_name_in_filename_ref)
    #         if parent is not None:
    #             return parent.use_name_in_filename
    #     return self._use_name_in_filename

    # @use_name_in_filename.setter
    # def use_name_in_filename(self, value):
    #     if self._use_name_in_filename_ref:
    #         parent = self._instances.get(self._use_name_in_filename_ref)
    #         if parent is not None:
    #             parent.use_name_in_filename = value
    #             return
    #     self._use_name_in_filename = value
    #     self._update_file_handler()



    # --------------------------------------------------------------------------
    # Закрытие логгера
    # --------------------------------------------------------------------------
    def close(self) -> None:
        """
        Снимает с логгера все обработчики; свои (консоль, файл, выводы) закрывает.

        Глобальные обработчики снимаются, но не закрываются — ими пользуются другие
        логгеры (B7). Объект остаётся рабочим: WARNING+ уйдут в ``logging.lastResort``.
        Из реестра логгер не удаляется (для этого — ``close_all``).

        Returns:
            None

        Пример:
            >>> log.close()
        """
        # for handler in self.logger.handlers[:]:
        #     handler.close()
        #     self.logger.removeHandler(handler)
        # ↑ до 2026-10-14 закрывались и глобальные обработчики (окно логов GUI, глобальные
        #   выводы-функции): close() одного логгера ломал их для всех остальных.
        with BaseAppLogger._global_handlers_lock:
            global_handlers = list(BaseAppLogger._global_handlers)
        # Общие выводы класса (OUTPUTS) тоже общие — их закрывает close_class_outputs()
        global_handlers += self._class_output_handlers()
        for handler in self.logger.handlers[:]:
            self.logger.removeHandler(handler)
            if handler not in global_handlers:
                handler.close()
        self._outputs.clear()
        self.handlers.clear()
