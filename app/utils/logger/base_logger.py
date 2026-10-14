# app/utils/logger/base_logger.py

"""
Ядро логирования: BaseAppLogger и обработчики.

Самостоятельный модуль — только стандартная библиотека Python 3.8+. Его можно
скопировать в другой проект под любым именем (см. IMPLEMENTATION.md §8).

Состав:
    BaseAppLogger              — именованные логгеры поверх ``logging``: реестр (Multiton),
                                 место вызова в каждой строке, декоратор
                                 ``log_execution_time``, режимы на лету, общий файл
                                 (мастер/слейв), выводы в функции.
    RobustRotatingFileHandler  — файл с ротацией, который пересоздаётся после удаления и
                                 переживает кратковременные блокировки.
    CallableHandler            — передаёт записи в функцию вида ``print(text)``
                                 (Telegram-бот, окно программы), в т. ч. в фоне.

Формат строки:
    2026-10-14 16:37:36,183<TAB>INFO<TAB>[имя]<TAB> File "путь", line N, in <функция>:<TAB>текст

Пример (свой логгер в другом проекте):
    >>> class Log(BaseAppLogger):
    ...     _instances = {}
    ...     @classmethod
    ...     def get_default_config(cls):
    ...         return {'LOG_LEVEL': 'INFO', 'LOG_FILE': 'logs/', 'LOG_MAX_BYTES': 10_000_000,
    ...                 'LOG_BACKUP_COUNT': 5, 'file_enabled': 'True'}
    >>> log = Log.get_instance('worker')
    >>> log.info('старт')
    >>> log.add_output(print, level='ERROR', formatter='%(levelname)s: %(plain_message)s')

    >>> @log.log_execution_time(description='обработка', log_args=True)
    ... def handle(order_id): ...

Путь LOG_FILE (base_log_file):
    * папка (существующая или с разделителем на конце) → внутри ``app.log`` или ``<имя>.log``;
    * путь на ``.log`` или существующий файл → этот файл;
    * иное несуществующее → считается папкой.

Устройство, проблемы и история решений — IMPLEMENTATION.md рядом с модулем.
"""

import asyncio
import os
import logging
import sys
import time
from typing import (
    List, Optional, Dict, Sequence,
    Any, Callable, Tuple, Union
)

import warnings
import inspect

import threading

import contextvars

from functools import wraps
from logging.handlers import RotatingFileHandler
import weakref
import queue

# Части класса (2026-10-14: файл разбит на модули; методы перенесены без изменений)
from ._common import (
    LOGGER_CODE_FILES, _NOT_FOUND, _STOP_OUTPUT, _level_to_int,
)
from .handlers import CallableHandler, RobustRotatingFileHandler
from ._registry import _RegistryMixin
from ._config import _ConfigMixin
from ._handlers_mgmt import _HandlersMixin
from ._sharing import _SharingMixin
from ._modes import _ModesMixin
from ._outputs import _OutputsMixin
from ._emit import _EmitMixin
from ._decorator import _DecoratorMixin
from . import _registry, _config, _handlers_mgmt, _sharing, _modes, _outputs, _emit, _decorator

# Имя файла этого модуля так, как его видят кадры стека (frame.f_code.co_filename).
# Оставлено для совместимости: правила пропуска кадров теперь строятся по всем
# модулям пакета (LOGGER_CODE_FILES).
_THIS_CODE_FILENAME: str = (lambda: None).__code__.co_filename
LOGGER_CODE_FILES.append(_THIS_CODE_FILENAME)


class BaseAppLogger(
    _RegistryMixin,
    _ConfigMixin,
    _HandlersMixin,
    _SharingMixin,
    _ModesMixin,
    _OutputsMixin,
    _EmitMixin,
    _DecoratorMixin,
):
    """
    Именованный логгер поверх ``logging`` с реестром, режимами на лету и общим файлом.

    Используйте через наследника, задающего ``get_default_config()`` (как ``AppLogger``),
    и получайте экземпляры только через ``get_instance(name, ...)``.

    Возможности:
        * место вызова в каждой строке (``File "...", line N, in <func>``);
        * ``debug``…``exception`` и декоратор ``log_execution_time``;
        * режимы на лету: ``enable``/``disable``, консоль, файл, уровень, ``reconfigure``,
          групповые методы по префиксу имени, список отключённых;
        * один обработчик на файл: логгеры с одним файлом пишут через обработчик
          мастера, каждый — со своим уровнем (IMPLEMENTATION.md §3.6);
        * выводы в функции: ``add_output``/``add_global_output``.

    Атрибуты класса:
        _instances (Dict[str, BaseAppLogger]): Реестр {имя: логгер}; у каждого
            наследника должен быть свой.
        _global_handlers (List[logging.Handler]): Обработчики для всех логгеров.
        _disabled_loggers (List[str]): Имена, которым запрещено писать.
        skip_patterns_modeles: Правила пропуска своих кадров стека при поиске места вызова.
        LOG_FORMAT (str): Формат строки по умолчанию.

    Атрибуты экземпляра (основные):
        name (str): Имя логгера.
        logger (logging.Logger): ``logging.getLogger(name)`` — один на имя в процессе.
        log_level (int): Уровень.
        console_handler, file_handler: Текущие обработчики (или ``None``).

    Пример:
        >>> class Log(BaseAppLogger):
        ...     _instances = {}
        ...     @classmethod
        ...     def get_default_config(cls):
        ...         return {'LOG_LEVEL': 'INFO', 'LOG_FILE': 'logs/',
        ...                 'LOG_MAX_BYTES': 10_000_000, 'LOG_BACKUP_COUNT': 5}
        >>> log = Log.get_instance('db', enable_file_logging=True)
        >>> log.warning('медленный запрос')





    # Блокировки:
    # - _instances_lock (классовая): защищает словарь _instances.
    # - _global_handlers_lock (классовая): защищает список _global_handlers.
    # - _share_lock (классовая): защищает операции шаринга (связи master-slave, списки _shared_slaves).
    # - _handler_lock (экземплярная): защищает внутреннее состояние экземпляра при перестроении обработчиков.
    # Порядок захвата: сначала _share_lock (если нужно), затем _handler_lock (если нужно).
    """
    _global_handlers = []  # список обработчиков, добавляемых ко всем логгерам
    _global_handlers_lock = threading.RLock()

    _instances: Dict[str, 'BaseAppLogger'] = {}   # Словарь экземпляров (ключ - имя логгера)
    _instances_lock = threading.RLock()

    # Глубина вложенности вызовов для синхронных потоков (threading.local)
    _depth_local = threading.local()

    # Глубина вложенности вызовов для асинхронных задач (contextvars)
    _depth_context: contextvars.ContextVar[int] = contextvars.ContextVar('log_depth', default=0)

    _share_lock = threading.RLock()   # отдельный лок для операций шаринга
    
    # _levels_up = 3
    _levels_up = 0


    skip_patterns_modeles = ( # список пропусков в стеке вызовов модулей и функций для отображения логирования
        # 'filename' - часть пути до модуля, который пропускаем 
        # 'function': - ф-ции, которые пропускаем (если не указываем function', то пропуск всех ф-й из 'filename')
        # {
        #     'filename':('app','utils','logger','base_logger.py'),
        #     'function':('_formatted', 'info', 'debug', 'warning', 'error', 'critical'),
        # },
        # ↑ до 2026-10-14: путь был зашит под этот проект — при копировании модуля в
        #   другой проект свои кадры не пропускались и в лог попадал base_logger.py.
        #   Не было и 'exception' (B6): log.exception() указывал внутрь логгера.
        # {
        #     'filename': (_THIS_CODE_FILENAME,),
        #     'function': ('_formatted', 'info', 'debug', 'warning', 'error', 'critical', 'exception'),
        # },
        # ↑ до разбиения на модули (2026-10-14) весь логгер был в одном файле. Теперь
        #   методы записи живут в _emit.py — правило строится для каждого файла пакета
        #   (LOGGER_CODE_FILES), с тем же списком функций.
    ) + tuple(
        {
            'filename': (_code_file,),
            'function': ('_formatted', 'info', 'debug', 'warning', 'error', 'critical', 'exception'),
        }
        for _code_file in LOGGER_CODE_FILES
    )


    # Простой формат лога: время, уровень, сообщение (всё остальное формируем вручную)
    LOG_FORMAT = '%(asctime)s\t%(levelname)s\t%(message)s'

    # Куда пишет «консоль»: None — sys.stderr; функция вида print(text) — в неё
    # (тот же формат). Задаётся у наследника: атрибутом или console_output=... .
    CONSOLE_OUTPUT: Optional[Callable[[str], Any]] = None

    # Общие выводы класса: функции или словари для add_output (func, level, background,
    # formatter, queue_size). Один обработчик на класс для всех его логгеров.
    OUTPUTS: Tuple[Any, ...] = ()

    def __init_subclass__(
        cls,
        console_output: Optional[Callable[[str], Any]] = None,
        outputs: Optional[Sequence[Any]] = None,
        log_format: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """
        Настройка наследника прямо в объявлении класса.

        Что делает:
            * своему наследнику — свой реестр ``_instances``, если он не объявлен явно.
              До 2026-10-14 наследник без ``_instances = {}`` делил реестр с родителем:
              ``get_instance('x')`` у разных классов возвращал один и тот же объект;
            * ``console_output`` → ``CONSOLE_OUTPUT``: функция вместо ``sys.stderr``;
            * ``outputs`` → ``OUTPUTS``: общие выводы класса (см. ``_class_output_handlers``);
            * ``log_format`` → ``LOG_FORMAT``: формат строки для консоли, файла и выводов.

        То же можно задать атрибутами класса — параметры удобнее для коротких наследников.

        Args:
            console_output: Функция вида ``print(text)`` для вывода «в консоль».
            outputs: Функции или словари описаний общих выводов.
            log_format: Формат ``logging`` (``'%(asctime)s %(levelname)s %(message)s'``).
            **kwargs: Передаются дальше по цепочке ``__init_subclass__``.

        Returns:
            None

        Пример:
            >>> def send_tg(text: str) -> None:
            ...     bot.send_message(CHAT_ID, text)
            >>> class BotLogger(AppLogger, console_output=send_tg,
            ...                 outputs=[{'func': print, 'level': 'ERROR'}]):
            ...     pass
            >>> BotLogger.get_instance('bot').info('в Telegram вместо консоли')
        """
        super().__init_subclass__(**kwargs)
        if '_instances' not in cls.__dict__:
            cls._instances = {}
        if console_output is not None:
            cls.CONSOLE_OUTPUT = console_output
        if outputs is not None:
            cls.OUTPUTS = tuple(outputs)
        if log_format is not None:
            cls.LOG_FORMAT = log_format

    level_map = {
        'DEBUG': logging.DEBUG,
        'INFO': logging.INFO,
        'WARNING': logging.WARNING,
        'ERROR': logging.ERROR,
        'CRITICAL': logging.CRITICAL
    }

    _watchdog_started = False
    _watchdog_started_lock = threading.Lock()
    # Классы, файлы которых проверяет общий поток LoggerWatchdog (P2). Слабые ссылки:
    # поток не мешает освобождать классы, созданные, например, в тестах.
    _watched_classes: 'weakref.WeakSet[type]' = weakref.WeakSet()
    #
    # @property
    # def list_stop_loger(self) -> List[str]:
    #     if not hasattr(BaseAppLogger, '_list_stop_loger'):
    #         BaseAppLogger._list_stop_loger:List[str] = []
    #     return BaseAppLogger._list_stop_loger
    #
    # @list_stop_loger.setter
    # def list_stop_loger(self, value: List[str]):
    #     BaseAppLogger._list_stop_loger = value


    _show_call_depth_global = False

    # Параметры reconfigure(), которые относятся к самому файлу. У слейва они
    # перенаправляются мастеру — владельцу общего обработчика (S3).
    _SHARED_FILE_PARAMS = frozenset({
        'base_log_FILE', 'log_MAX_BYTES', 'log_BACKUP_COUNT',
        'use_timestamp', 'use_name_in_filename',
    })

    # Вместо свойства list_stop_loger используем обычный классовый атрибут
    _disabled_loggers: List[str] = []

    def __init__(
        self,
        name: str,
        config: Optional[Union[str,Dict[str, Any]]] = None,
        enable_file_logging: Union[str,bool] = False,
        use_name_in_filename: Union[str,bool] = False, #
        # show_call_depth: bool = False,
        show_call_depth: bool = True,
        sync_full_state: Optional[bool] = True,    # по умолчанию копируем флаги консоли/включения
    ) -> None:
        """
        Создаёт логгер. Напрямую не вызывайте — используйте ``get_instance()`` (реестр,
        автоподключение к общему файлу).

        Что происходит:
            1. Берётся ``logging.getLogger(name)`` (один на имя в процессе), отключается
               передача записей предкам (``propagate=False``), добавляется постоянный
               ``NullHandler`` (R6).
            2. Строковые ссылки в ``enable_file_logging``/``use_name_in_filename`` (имя другого
               логгера) запоминаются: от того логгера наследуются настройки и общий файл.
            3. Конфиг загружается (``_load_config``), проверяется (``_validate_config``),
               значения вычисляются с учётом иерархии (``_init_config_load``) и применяются.
            4. Создаются обработчики (``_update_handlers``): консоль, файл или подключение
               к общему файлу.

        Args:
            name: Имя логгера (видно в каждой строке: ``[name]``).
            config: Словарь настроек; строка — имя существующего логгера, чьи настройки
                скопировать; ``None`` — ``get_default_config()``. Ключи и приоритеты —
                IMPLEMENTATION.md §3.4.
            enable_file_logging: ``True``/``False`` — писать ли в файл, если в конфиге нет
                ``file_enabled``; ``'true'``/``'false'`` — то же строкой; другая строка — имя
                логгера-родителя: файл и настройки наследуются от него.
            use_name_in_filename: ``True`` — файл ``<name>.log`` вместо ``app.log``; строка —
                имя логгера, чьё значение использовать.
            show_call_depth: Отступ ``>`` по глубине стека в каждой строке; ключ
                ``show_call_depth`` в конфиге сильнее. Дорогой режим.
            sync_full_state: Для мастера — слейвы повторяют его ``enabled``/консоль (S4).
                ``None`` — для слейва унаследовать флаг мастера.

        Returns:
            None

        Raises:
            ValueError: В конфиге нет обязательного ключа или значение не приводится к типу.

        Пример:
            >>> log = AppLogger.get_instance('payments', enable_file_logging='system')
        """

        self.name = name
        self._start_timestamp = time.strftime("%Y%m%d_%H%M%S")

        # Создаём логгер немедленно
        self.logger = logging.getLogger(name)
        self.logger.propagate = False
        self.logger.setLevel(logging.DEBUG)  # временно

        # Постоянный «пустой» обработчик (исправление R6, IMPLEMENTATION.md §5.1).
        # Если у logging.Logger нет ни одного обработчика (консоль и файл выключены),
        # Python пишет WARNING и выше в stderr через logging.lastResort — выключенный
        # логгер «протекал» в консоль. NullHandler ничего не выводит, но обработчик
        # есть, и lastResort не срабатывает. _update_handlers() его не трогает
        # (снимает только console_handler/file_handler), снимает только close().
        # logging.Logger общий для одного имени (force_new) — второй не добавляем.
        self._null_handler: logging.Handler = next(
            (h for h in self.logger.handlers if isinstance(h, logging.NullHandler)),
            None,
        ) or logging.NullHandler()
        if self._null_handler not in self.logger.handlers:
            self.logger.addHandler(self._null_handler)

        self._shared_handler = False    # флаг, что используется общий обработчик
        self._master_logger = None      # ссылка на логгер, предоставивший общий обработчик
        self._shared_slaves = []        # логгеры, которые используют мой обработчик

        # self._sync_full_state = True   # по умолчанию копируем флаги консоли/включения

        self._show_call_depth = show_call_depth

        # Выводы-функции этого логгера (add_output). _update_handlers() их не трогает:
        # он пересоздаёт только console_handler/file_handler.
        self._outputs: List[CallableHandler] = []

        self._handler_lock = threading.RLock()

        # self._sync_full_state = sync_full_state  # по умолчанию копируем флаги консоли/включения
        # None (S4): мастеру — False; если логгер подключится к мастеру, флаг
        # унаследуется (_sync_all_from_master). Явный True/False — свой выбор.
        self._sync_full_state = bool(sync_full_state)
        self._sync_full_state_explicit: Optional[bool] = sync_full_state

        # Разрешено ли при перестроении автоматически подключаться к уже открытому
        # обработчику того же файла: родителя по ссылке enable_file_logging='имя'
        # (исправление S1) или любого другого владельца этого файла.
        # Сбрасывается явным unshare_file_handler(): если логгер попросили писать
        # в свой обработчик, перестроение не должно молча подключить его обратно.
        self._allow_auto_share: bool = True

        # self._console_enabled = True   # флаг для консольного вывода
        # self._enabled = True            # полное отключение логирования

        # self._file_enabled = bool(enable_file_logging)# флаг для файлового вывода
        # self._use_name_in_filename = bool(use_name_in_filename)

        # Сохраняем ссылки, если переданы строки
        if isinstance(enable_file_logging, str):
            # self._enable_file_logging_ref = enable_file_logging
            # self._enable_file_logging = False  # placeholder
            low = enable_file_logging.lower()
            if low in ('true', 'false'):
                enable_file_logging = low == 'true'
                
            else:
                self._enable_file_logging_ref = enable_file_logging
                enable_file_logging = True # файловое логирование включаем, но обработчик будет общим  

        else:
            self._enable_file_logging_ref = None

        self._enable_file_logging = enable_file_logging

        if isinstance(use_name_in_filename, str):
            low = use_name_in_filename.lower()
            if low in ('true', 'false'):
                use_name_in_filename = low == 'true'

            else:
                self._use_name_in_filename_ref = use_name_in_filename
                use_name_in_filename = False             

        else:
            self._use_name_in_filename_ref = None
            
        self._use_name_in_filename = use_name_in_filename
        
        config = self._load_config(config)  # Обработка config: если строка, берём из другого экземпляра
        self._validate_config(config)       # Проверяем наличие обязательных ключей

        _config = self._init_config_load( # Чтение флагов из конфигурации (с значениями по умолчанию)
            config, 
            # enable_file_logging, 
            # use_name_in_filename
            None, 
            None
        )



        # # Преобразуем строковые значения в нужные типы
        # try:
        #     self.log_level = self._parse_log_level(config['LOG_LEVEL'])
        #     self.base_log_file = config['LOG_FILE']
        #     self.log_max_bytes = int(config['LOG_MAX_BYTES'])
        #     self.log_backup_count = int(config['LOG_BACKUP_COUNT'])
        #     self.log_args = config.get('LOG_ARGS', False)   # новый атрибут
        # except ValueError as e:
        #     raise ValueError(f"Ошибка преобразования параметров логирования: {e}")
        self._apply_config(_config) 

        # self.log_level = _config['LEVEL']
        # self.base_log_file = _config['FILE']
        # self.log_max_bytes = _config['MAX_BYTES']
        # self.log_backup_count = _config['BACKUP_COUNT']
        # self.log_args = _config['ARGS']   # новый атрибут


        # Создаём логгер (без обработчиков)
        # self.logger = logging.getLogger(name)

        self.logger.setLevel(self.log_level)
        # if 'LEVEL' in _config:
        #     self.logger.setLevel(self.log_level)

        self.logger.propagate = False  # предотвращаем дублирование, если есть корневой логгер
        self.formatter = logging.Formatter(self.LOG_FORMAT)# Формат сообщений



        # # Консольный обработчик (всегда)
        # self.console_handler = logging.StreamHandler()
        # self.console_handler.setLevel(self.log_level)
        # self.console_handler.setFormatter(self.formatter)
        # self.logger.addHandler(self.console_handler)

        # # Инициализируем файловый обработчик (может быть None)
        # self.file_handler = None
        # self._update_file_handler()  # создаст, если нужно

        # # Добавляем глобальные обработчики
        # for handler in self._global_handlers:
        #     self.logger.addHandler(handler)

        # Инициализируем обработчики через единый метод
        self.console_handler = None
        self.file_handler = None
        self._update_handlers()   # создаст и консольный, и файловый согласно флагам

        
        self._save_handlers() # Сохраняем ссылки на обработчики (может пригодиться для GUI)

    # Кэш ответов _is_logger_frame: (класс, co_filename, co_name) → bool.
    # Набор кадров конечен, а проверка нормализует пути — без кэша это заметно на
    # каждом вызове. Если наследник меняет skip_patterns_modeles во время работы,
    # вызовите _skip_cache.clear().
    _skip_cache: Dict[Tuple[type, str, str], bool] = {}


# Методы в модулях-частях обращаются к классу по имени BaseAppLogger
# (BaseAppLogger._share_lock, BaseAppLogger._skip_cache…). Подставляем итоговый класс.
for _part in (_registry, _config, _handlers_mgmt, _sharing, _modes, _outputs, _emit, _decorator,):
    _part.BaseAppLogger = BaseAppLogger
del _part


# ------------------------------------------------------------------------------
# Экспортируем только класс
# ------------------------------------------------------------------------------
__all__ = ['BaseAppLogger', 'CallableHandler', 'RobustRotatingFileHandler']
