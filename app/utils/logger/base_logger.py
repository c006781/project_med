# app/utils/logger/base_logger.py

"""
Базовый модуль логирования.

Содержит класс BaseAppLogger, который:
- Управляет созданием и хранением экземпляров логгеров (паттерн Multiton).
- Каждый экземпляр настраивается индивидуально (имя, конфигурация, параметры файла).
- Предоставляет методы для логирования и декоратор log_execution_time.
- Поддерживает запись в отдельные файлы для разных экземпляров и отключение файлового логирования.
- Не использует глобальные переменные (все данные хранятся в атрибутах класса).

Пример использования:
    # Базовый логгер (пишет в файл по умолчанию)
    logger = BaseAppLogger.get_instance()
    logger.info("Сообщение")

    # Логгер, который пишет в отдельный файл с именем экземпляра
    logger_db = BaseAppLogger.get_instance(name='db', use_name_in_filename = True)
    logger_db.info("Сообщение для db")

    # Логгер только в консоль (без файла)
    logger_console = BaseAppLogger.get_instance(name='console', enable_file_logging = False)
    logger_console.info("Только в консоль")

Особенности настройки LOG_FILE (base_log_file):
    - Может быть путём к ДИРЕКТОРИИ (например, "logs" или "./logs/").
      В этом случае внутри директории автоматически создаётся файл с именем,
      зависящим от параметров use_name_in_filename и use_timestamp.
    - Может быть полным путём к ФАЙЛУ с расширением .log (например, "logs/app.log").
      В этом случае используется именно этот файл (родительские директории создаются).
    - Если путь не существует и не оканчивается на .log, он интерпретируется как директория.
"""

import asyncio
import os
import logging
import sys
import time
from typing import (
    List, Optional, Dict, 
    Any, Callable, Tuple, Union
)

import warnings
import inspect

import threading

import contextvars

from functools import wraps
from logging.handlers import RotatingFileHandler
import weakref

class RobustRotatingFileHandler(RotatingFileHandler):
    """
    Обработчик файла с поддержкой восстановления при удалении файла.
    Потокобезопасен, проверяет существование файла не чаще 1 раза в секунду
    """
    def __init__(
        self,
        filename,
        mode='a',
        maxBytes=0, backupCount=0,
        encoding=None,
        delay=False
    ):
        super().__init__(
            filename,
            mode,
            maxBytes,
            backupCount,
            encoding,
            delay
        )

        self._lock = threading.RLock()
        self._last_check = 0
        self._check_interval = 1.0  # проверять не чаще раза в секунд

    def emit(self, record):
        """
        Переопределённый метод emit: перед записью проверяет существование файла.
        Если файл удалён, переоткрывает его.
        """
        max_retries = 5
        retry_delay = 0.2        # добавить задержку между попытками
        for attempt in range(max_retries):
            with self._lock:
                try:
                    need_reopen = False
                    now = time.time()
                    # Проверяем существование файла, если прошло достаточно времени
                    if now - self._last_check > self._check_interval:
                        if not os.path.exists(self.baseFilename):
                            # Файл удалён – переоткрываем
                            need_reopen = True

                        self._last_check = now 

                    if need_reopen: # Файл удалён – переоткрываем
                        with self._lock:
                            self._reopen() 
                            #  После переоткрытия принудительно сбросим таймер, чтобы следующая запись не ждала
                            self._last_check = 0

                    super().emit(record)
                    return
                
                except (FileNotFoundError, PermissionError) as e:
                    # Если файл внезапно исчез между проверкой и записью
                    # self.handleError(record)
                    if attempt == max_retries - 1:
                        self.handleError(record)
                        return
                    print(f"подход {attempt} провал")
                    time.sleep(retry_delay)
                    with self._lock:

                        self._reopen()

                except Exception:
                    self.handleError(record)
                    return

    def _reopen(self):
        """Принудительно закрывает и открывает файл."""
        with self._lock:
            # Файл удалён – закрываем текущий поток и открываем заново
            if self.stream:
                self.stream.close()
                self.stream = None

            # Создаём директорию для файла лога, если её нет
            log_dir = os.path.dirname(self.baseFilename)
            if log_dir:
                os.makedirs(log_dir, exist_ok=True) 

            self._open() # открывает файл заново (определён в базовом классе)

    def reopen_if_needed(self):
        """Принудительно проверяет и переоткрывает файл, если он отсутствует."""
        with self._lock:
            if not os.path.exists(self.baseFilename):
                self._reopen()

    def force_reopen(self):
        """Принудительно закрывает и переоткрывает файл."""
        with self._lock:
            self._reopen()
            self._last_check = time.time()

class BaseAppLogger:
    """
    Менеджер логгеров с поддержкой нескольких именованных экземпляров.

    Атрибуты класса:
        _instances (dict): Словарь созданных экземпляров {имя: экземпляр}.

    Методы класса:
        get_instance(name='default', force_new=False, config=None,
                     enable_file_logging = True, use_name_in_filename = False) -> BaseAppLogger:
            Возвращает экземпляр логгера с указанным именем.





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
        {
            'filename':('app','utils','logger','base_logger.py'),
            'function':('_formatted', 'info', 'debug', 'warning', 'error', 'critical'), 
        },
    )


    # Простой формат лога: время, уровень, сообщение (всё остальное формируем вручную)
    LOG_FORMAT = '%(asctime)s\t%(levelname)s\t%(message)s'

    level_map = {
        'DEBUG': logging.DEBUG,
        'INFO': logging.INFO,
        'WARNING': logging.WARNING,
        'ERROR': logging.ERROR,
        'CRITICAL': logging.CRITICAL
    }

    _watchdog_started = False
    _watchdog_started_lock = threading.Lock()
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

    # Вместо свойства list_stop_loger используем обычный классовый атрибут
    _disabled_loggers: List[str] = []

    @classmethod
    def on_show_call_depth_global(cls):
        cls._show_call_depth_global = True

    @classmethod
    def off_show_call_depth_global(cls):
        cls._show_call_depth_global = False


    @classmethod
    def status_show_call_depth_global(cls):
        return cls._show_call_depth_global


    @classmethod
    def add_disabled_logger(cls, name: str):
        """Добавляет имя логгера в список отключённых."""
        if name not in cls._disabled_loggers:
            cls._disabled_loggers.append(name)

    @classmethod
    def remove_disabled_logger(cls, name: str):
        """Удаляет имя из списка отключённых."""
        if name in cls._disabled_loggers:
            cls._disabled_loggers.remove(name)

    @classmethod
    def clear_disabled_loggers(cls):
        """Очищает список отключённых логгеров."""
        cls._disabled_loggers.clear()

    @classmethod
    def is_disabled(cls, name: str) -> bool:
        """Проверяет, отключён ли логгер с указанным именем."""
        return name in cls._disabled_loggers

    @classmethod
    def disable_exact(cls, name: str):
        """Отключает логгер с точным именем (не префикс)."""
        inst = None

        with cls._instances_lock:
            inst = cls._instances.get(name)

        if inst:
            inst.disable()

    @classmethod
    def enable_exact(cls, name: str):
        """Включает логгер с точным именем."""
        with cls._instances_lock:
            inst = cls._instances.get(name)
            if inst:
                inst.enable()

    @classmethod
    def disable_console_exact(cls, name: str):
        """Отключает консольный вывод для точного логгера."""
        with cls._instances_lock:
            inst = cls._instances.get(name)
            if inst:
                inst.disable_console()

    @classmethod
    def enable_console_exact(cls, name: str):
        """Включает консольный вывод для точного логгера."""
        with cls._instances_lock:
            inst = cls._instances.get(name)
            if inst:
                inst.enable_console()

    @classmethod
    def disable_file_exact(cls, name: str):
        """Отключает файловое логирование для точного логгера."""
        with cls._instances_lock:
            inst = cls._instances.get(name)
            if inst:
                inst.disable_file()

    @classmethod
    def enable_file_exact(cls, name: str):
        """Включает файловое логирование для точного логгера."""
        with cls._instances_lock:
            inst = cls._instances.get(name)
            if inst:
                inst.enable_file()

    # @classmethod
    # def disable_group_exact(cls, name: str):
    #     """Отключает логгер с точным именем (не префикс)."""
    #     inst = cls._instances.get(name)
    #     if inst:
    #         inst.disable()

    # @classmethod
    # def enable_group_exact(cls, name: str):
    #     inst = cls._instances.get(name)
    #     if inst:
    #         inst.enable()

    @classmethod
    def start_file_watchdog(cls, interval_sec: float = 5.0):
        """Запускает фоновый поток, проверяющий существование файлов логов."""
        # import threading
        with cls._watchdog_started_lock:
            if cls._watchdog_started:
                return
            
            cls._watchdog_started = True

        def watch():
            while True:
                time.sleep(interval_sec)  
                cls.reopen_all_files()  # внутри есть блокировка

        thread = threading.Thread(target=watch, daemon=True, name="LoggerWatchdog")
        thread.start()

    @classmethod
    def reopen_all_files(cls):
        """Переоткрывает файловые обработчики всех логгеров (например, после изменения пути)."""
        with cls._instances_lock:
            for inst in cls._instances.values():
                if inst.file_handler and hasattr(inst.file_handler, 'force_reopen'):
                    inst.file_handler.force_reopen()

    @classmethod
    def reload_all_from_config(cls, global_config: Dict[str, Any]):
        """
        Перезагружает настройки для всех существующих логгеров из словаря.
        Ключи вида '<name>_enabled' и т.д. применяются к конкретным логгерам,
        ключи без префикса – как значения по умолчанию.
        """
        with cls._instances_lock:

            for inst in cls._instances.values():
                # Формируем конфиг для этого логгера: сначала общие настройки, затем специфичные
                specific = {}
                for key, value in global_config.items():
                    if key.startswith(f"{inst.name}_"):
                        # Убираем префикс для внутреннего использования
                        specific[key[len(inst.name)+1:]] = value

                # Объединяем: специфичные переопределяют общие
                merged = {**global_config, **specific}
                inst.reload_from_config(merged)

            # Дополнительно: после изменения конфигурации можно принудительно переоткрыть файлы
            # для всех логгеров, у которых включено файловое логирование
            for inst in cls._instances.values():
                if inst._file_enabled and inst.file_handler:
                    inst._reopen_file_handler_if_needed()

    @classmethod
    def add_global_handler(cls, handler):
        """
        Добавляет обработчик ко всем существующим и будущим экземплярам логгеров.

        Это может быть полезно, если вам нужно добавить общий обработчик для всех логгеров в программе.
        Пример использования:
            def my_handler(record):
                # обработка записи лога
                pass
            BaseAppLogger.add_global_handler(logging.Handler(my_handler))

        """
        with cls._global_handlers_lock:
            cls._global_handlers.append(handler)

        # добавление к экземплярам уже под _instances_lock
        with cls._instances_lock:
            # Добавляем ко всем уже созданным экземплярам
            for instance in cls._instances.values():
                with instance._handler_lock:
                    instance.logger.addHandler(handler)
                    # Обновляем список обработчиков экземпляра (опционально)
                    instance.handlers = instance.logger.handlers[:]

    @classmethod
    def remove_global_handler(cls, handler):
        """
        Удаляет обработчик из глобального списка и из каждого существующего экземпляра логгера.

        :param handler: Обработчик, который нужно удалить.
        """

        with cls._global_handlers_lock:
            # Если обработчик есть в глобальном списке, удаляем его
            if handler in cls._global_handlers:
                cls._global_handlers.remove(handler)

        with cls._instances_lock:
            # Удаляем обработчик из каждого существующего экземпляра
            for instance in cls._instances.values():
                with instance._handler_lock:
                    instance.logger.removeHandler(handler)

                    # Обновляем список обработчиков экземпляра (опционально)
                    instance.handlers = instance.logger.handlers[:]
            
    @classmethod
    def get_default_config(cls) -> Dict[str, Any]:
        """
        Возвращает конфигурацию по умолчанию, которая будет использоваться, если не указать config при вызове get_instance().

        Метод должен быть переопределён в наследнике, потому что конфигурация по умолчанию зависит от конкретного приложения.

        Если не переопределён, то будет выброшено исключение RuntimeError.

        В наследнике необходимо переопределить метод, чтобы он возвращал словарь с конфигурацией по умолчанию для конкретного приложения.

        Например, если в приложении по умолчанию логгер должен писать в файл с именем "app.log", то
        метод get_default_config() должен возвращать словарь {"LOG_FILE": "app.log"}.

        """
        raise RuntimeError(
            "Метод get_default_config() не переопределён в наследнике. "
            "Передайте config напрямую в get_instance() или переопределите метод."
        )

    @classmethod
    def disable_group(cls, name_prefix: str):
        """Отключает все логгеры, чьи имена начинаются с name_prefix."""
        with cls._instances_lock:
            for inst in cls._instances.values():
                if inst.name.startswith(name_prefix):
                    inst.disable()

    @classmethod
    def enable_group(cls, name_prefix: str):
        """Включает все логгеры группы."""
        with cls._instances_lock:
            for inst in cls._instances.values():
                if inst.name.startswith(name_prefix):
                    inst.enable()

    @classmethod
    def set_group_level(cls, name_prefix: str, level: str):
        """Устанавливает уровень логирования для всех логгеров группы."""
        with cls._instances_lock:
            for inst in cls._instances.values():
                if inst.name.startswith(name_prefix):
                    inst.setLevel(cls._parse_log_level(level))

    @classmethod
    def get_group_loggers(cls, name_prefix: str) -> list:
        """
        Возвращает список имён логгеров, чьи имена начинаются с name_prefix.
        """
        with cls._instances_lock:
            return [
                inst.name 
                for inst in cls._instances.values() 
                if inst.name.startswith(name_prefix)
            ]

    @classmethod
    def reconfigure_group(cls, name_prefix: str, **kwargs):
        """
        Переконфигурирует все логгеры группы (например, изменить уровень).
        """
        with cls._instances_lock:
            for inst in cls._instances.values():
                if inst.name.startswith(name_prefix):
                    inst.reconfigure(**kwargs)

    def __init__(
        self,
        name: str,
        config: Optional[Union[str,Dict[str, Any]]] = None,
        enable_file_logging: Union[str,bool] = False,
        use_name_in_filename: Union[str,bool] = False, # 
        # show_call_depth: bool = False,
        show_call_depth: bool = True,
        sync_full_state = True,    # по умолчанию копируем флаги консоли/включения
    ): 
        """
        Инициализирует новый экземпляр логгера. Не вызывается напрямую – используйте get_instance().

        :param name: (str) Имя логгера.
        :param config: (str/dict) : Конфигурация для нового экземпляра (если None, используется провайдер
                str     - Указатель на экземпляр лога откуда берём этот параметр. 
                dict    - Словарь с настройками. 
                None    - Если не передан, загружается через get_default_config(). 
                
                Поддерживаемые ключи для dict:
                        - 'LOG_FILE' : str – путь к директории (логи будут внутри с именем <name>.log)
                                        или полный путь к файлу с расширением .log.

        :param enable_file_logging: (str/bool) : Для нового экземпляра: включать ли запись в файл.
                str     - Указатель на экземпляр лога откуда берём этот параметр. 
                True    - добавляется файловый обработчик. 
                False   - только консоль.
        :param use_name_in_filename: (str/bool) : Для нового экземпляра: добавлять ли имя в имя файла.
                str     - Указатель на экземпляр лога откуда берём этот параметр. 
                True    - имя экземпляра вставляется в имя файла лога. 
                False   - имя экземпляра НЕ вставляется в имя файла лога.
        """

        self.name = name
        self._start_timestamp = time.strftime("%Y%m%d_%H%M%S")

        # Создаём логгер немедленно
        self.logger = logging.getLogger(name)
        self.logger.propagate = False
        self.logger.setLevel(logging.DEBUG)  # временно

        self._shared_handler = False    # флаг, что используется общий обработчик
        self._master_logger = None      # ссылка на логгер, предоставивший общий обработчик
        self._shared_slaves = []        # логгеры, которые используют мой обработчик

        # self._sync_full_state = True   # по умолчанию копируем флаги консоли/включения

        self._show_call_depth = show_call_depth

        self._handler_lock = threading.RLock()

        self._sync_full_state = sync_full_state  # по умолчанию копируем флаги консоли/включения

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

    def _get_settings_parent(self) -> Optional['BaseAppLogger']:
        """Возвращает логгер, от которого следует наследовать настройки (конфиг)."""
        with self._handler_lock:
            # Приоритет: мастер файлового обработчика > ссылка enable_file_logging > ссылка use_name_in_filename
            if self._master_logger:
                return self._master_logger
            
            if self._enable_file_logging_ref:
                return self._get_parent(self._enable_file_logging_ref)
            
            if self._use_name_in_filename_ref:
                return self._get_parent(self._use_name_in_filename_ref)
        
        return None

    def _get_config_with_inheritance(
        self,
        config: Dict[str, Any],
        key: str,
        default: Any = None,
        _visited: Optional[set] = None
    ) -> Any:
        """
        Возвращает значение параметра из конфига с учётом иерархии мастер-слейв.
        Приоритет (по убыванию):
        1. {self.name}_{key}
        2. если есть мастер, значение от мастера (рекурсивно, с его именем)
        3. LOG_{key}
        4. key
        5. default
        """
        
        if _visited is None:
            _visited = set()

        # if self.name in _visited:
        #     # защита от циклической ссылки
        #     return default
        
        if id(self) in _visited:          # используем id для защиты от циклов
            return default
        
        _visited.add(id(self))

        # 1. Специфичный ключ для текущего логгера
        specific_key = f"{self.name}_{key}"
        if specific_key in config:
            return config[specific_key]

        # # 2. Если есть мастер, запросить у него (рекурсивно)
        # if self._master_logger:
        #     return self._master_logger._get_config_with_inheritance(
        #         config, key, default, _visited
        #     )

        # 2. Родитель по настройкам (мастер файлового обработчика или ссылка enable_file_logging)
        parent = self._get_settings_parent()
        if parent:
            return parent._get_config_with_inheritance(config, key, default, _visited)

        # 3. Общий префикс LOG_
        log_key = f"LOG_{key}"
        if log_key in config:
            return config[log_key]

        # 4. Простой ключ
        if key in config:
            return config[key]

        # 5. default
        return default

    def _apply_config(self, config_dict: Dict[str, Any]) -> None:
        """Применяет настройки из словаря, полученного от _init_config_load."""
        self._enabled = config_dict['enabled']
        self._console_enabled = config_dict['console_enabled']
        self._file_enabled = config_dict['file_enabled']
        self._use_name_in_filename = config_dict['use_name_in_filename']
        self.use_timestamp = config_dict['use_timestamp']
        self.log_args = config_dict['ARGS']
        self.log_level = config_dict['LEVEL']
        self.base_log_file = config_dict['FILE']
        self.log_max_bytes = config_dict['MAX_BYTES']
        self.log_backup_count = config_dict['BACKUP_COUNT']
        self._show_call_depth = config_dict['show_call_depth']

        self.logger.setLevel(self.log_level)

    def _get_call_depth(self) -> int:
        """
        Вычисляет реальную глубину вызовов на основе стека.
        Пропускает фреймы самого логгера и его внутренних методов.
        Возвращает количество пользовательских фреймов (глубину вложенности).
        """
        # import inspect
        stack = inspect.stack()
        depth = 0
        for frame_info in stack[1:]:  # пропускаем текущий фрейм
            # Пропускаем фреймы, относящиеся к логгеру
            if self._thec_skip_patterns_modeles({
                'filename': (frame_info.filename,),
                'function': (frame_info.function,)
            }):
                continue

            depth += 1

        return depth

    def _get_current_depth(self) -> int:
        """Возвращает текущую глубину вложенности для текущего контекста (поток/задача)."""

        try:
            loop = asyncio.get_running_loop()
            # Если есть текущая задача, считаем, что это асинхронный контекст
            if asyncio.current_task(loop) is not None:
                return self._depth_context.get()
            
            else:
                return getattr(self._depth_local, 'depth', 0)
        
        except (RuntimeError, LookupError) as e:
            err = e
            # Если не задан, используем threading.local (синхронный поток)
            # Нет запущенного event loop – синхронный контекст
            return getattr(self._depth_local, 'depth', 0)

    def _set_current_depth(self, depth: int) -> None:
        """Устанавливает глубину для текущего контекста."""
        try:
            self._depth_context.set(depth)

        except LookupError:
            self._depth_local.depth = depth

    def _increase_depth(self) -> int:
        """Увеличивает глубину на 1 и возвращает новое значение."""
        current = self._get_current_depth()
        new_depth = current + 1
        self._set_current_depth(new_depth)
        
        return new_depth

    def _decrease_depth(self) -> int:
        """Уменьшает глубину на 1 и возвращает новое значение."""
        current = self._get_current_depth()
        new_depth = max(0, current - 1)
        self._set_current_depth(new_depth)

        return new_depth

    def apply_config_from_dict(self, config_dict: Dict[str, Any]):
        """Применяет настройки из словаря (аналогично reload_from_config, но без перенаправления мастеру)."""
        # # Если используем общий обработчик, перенаправляем мастеру
        # if self._shared_handler and self._master_logger:
        #     self._master_logger.apply_config_from_dict(config_dict)
        #     return
        
        need_rebuild = False
        with self._handler_lock:      
            # Сохраняем старые флаги
            old_file = self._file_enabled
            old_console = self._console_enabled
            old_enabled = self._enabled
            old_base_log_file = self.base_log_file
            old_max_bytes = self.log_max_bytes
            old_backup_count = self.log_backup_count
            old_use_timestamp = self.use_timestamp
            old_use_name = self._use_name_in_filename

            # Обновляем текущие параметры

            self._update_config_from(config_dict)
    
            # self._init_config_load(config_dict, None, None)

            # # обновление остальных параметров

            # if 'LOG_LEVEL' in config_dict:
            #     self.log_level = self._parse_log_level(config_dict['LOG_LEVEL'])
            #     self.logger.setLevel(self.log_level)

            # if 'LOG_FILE' in config_dict:
            #     self.base_log_file = config_dict['LOG_FILE']

            # if 'LOG_MAX_BYTES' in config_dict:
            #     self.log_max_bytes = int(config_dict['LOG_MAX_BYTES'])

            # if 'LOG_BACKUP_COUNT' in config_dict:
            #     self.log_backup_count = int(config_dict['LOG_BACKUP_COUNT'])

            # if 'LOG_ARGS' in config_dict:
            #     self.log_args = self._to_bool(config_dict['LOG_ARGS'])

            # if 'show_call_depth' in config_dict:
            #     self._show_call_depth = self._to_bool(config_dict['show_call_depth'])

            # if self._shared_slaves:
            #     self._update_shared_slaves()

            # Проверяем, изменились ли параметры файла
            file_params_changed = (
                self.base_log_file != old_base_log_file or
                self.log_max_bytes != old_max_bytes or
                self.log_backup_count != old_backup_count or
                self.use_timestamp != old_use_timestamp or
                self._use_name_in_filename != old_use_name
            )

            need_rebuild = (
                self._file_enabled != old_file or
                self._console_enabled != old_console or
                self._enabled != old_enabled or
                file_params_changed
            )

        # применение изменений БЕЗ блокировки
        if need_rebuild:
            self._update_handlers()
            
        else:
            # обновить уровни
            for handler in self.logger.handlers:
                handler.setLevel(self.log_level)

            if self._shared_slaves:
                self._update_shared_slaves()

    def _reopen_file_handler_if_needed(self):
        """Переоткрывает файловый обработчик, если файл лога был удалён извне."""
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

    # @property # убираем изза циклических ссылок _visited
    def effective_enable_file_logging(self, _visited=None) -> bool:
        """Возвращает реальное состояние файлового логирования с учётом ссылки на другой логгер."""

        if _visited is None:
            _visited = set()

        obj_id = id(self)

        if self.name in _visited:
            self.logger.error(f"Циклическая ссылка в effective_enable_file_logging для {self.name}")
            return self._enable_file_logging
        
        # _visited.add(self.name)
        _visited.add(obj_id)
        
        if self._enable_file_logging_ref:
            # parent = self._instances.get(self._enable_file_logging_ref)
            parent = self._get_parent(self._enable_file_logging_ref)
            
            if parent:
                return parent.effective_enable_file_logging(_visited=_visited)
            
            # # если родитель не найден, логируем предупреждение и возвращаем собственное значение
            # self.logger.warning(
            #     f"Логгер '{self.name}' ссылается на несуществующий '{self._enable_file_logging_ref}'"
            # )
            # родитель не найден

            if hasattr(self, 'logger') and self.logger:
                self.logger.warning(
                    f"Логгер '{self.name}' "
                    f"ссылается на несуществующий '{self._enable_file_logging_ref}'"
                )
            else:
                # логгер ещё не создан — выводим в stderr
                # import sys
                print(
                    f"WARNING: Логгер '{self.name}' "
                    f"ссылается на несуществующий '{self._enable_file_logging_ref}'", 
                    file=sys.stderr
                )

        return self._enable_file_logging

    # def effective_enable_file_logging(self, _visited=None):
    #     visited = set()
    #     current = self
    #     while True:
    #         if current.name in visited:
    #             current.logger.error(f"Циклическая ссылка в effective_enable_file_logging для {current.name}")
    #             return current._enable_file_logging
            
    #         visited.add(current.name)
    #         if current._enable_file_logging_ref is None:
    #             return current._enable_file_logging
            
    #         parent = current._get_parent(current._enable_file_logging_ref)
    #         if parent is None:
    #             return current._enable_file_logging
            
    #         current = parent


    # @property # убираем изза циклических ссылок _visited
    def effective_use_name_in_filename(self, _visited=None) -> bool:
        if _visited is None:
            _visited = set()
        obj_id = id(self)
        if self.name in _visited:
            self.logger.error(f"Циклическая ссылка в effective_use_name_in_filename для {self.name}")
            # return self._enable_file_logging
            return self._use_name_in_filename
        
        _visited.add(obj_id)
        # _visited.add(self.name)

        if self._use_name_in_filename_ref:
            # parent = self._instances.get(self._use_name_in_filename_ref)
            parent = self._get_parent(self._use_name_in_filename_ref)

            if parent:
                return parent.effective_use_name_in_filename(_visited=_visited)
            # родитель не найден — логируем предупреждение, если логгер уже существует

            if hasattr(self, 'logger') and self.logger:
                self.logger.warning(
                    f"Логгер '{self.name}' "
                    f"ссылается на несуществующий '{self._use_name_in_filename_ref}'"
                )
            else:
                # логгер ещё не создан — выводим в stderr
                # import sys
                print(
                    f"WARNING: Логгер '{self.name}' "
                    f"ссылается на несуществующий '{self._use_name_in_filename_ref}'", 
                    file=sys.stderr
                )
            
        return self._use_name_in_filename


    def _get_parent(self, key) -> Optional['BaseAppLogger']:
        cls = type(self)
        with cls._instances_lock:
        # with type(self)._instances_lock:
            # return self._instances.get(
            return cls._instances.get(
                key 
            )
        
    def get_level(self) -> str:
        return logging.getLevelName(self.log_level)

    def set_formatter(self, formatter: logging.Formatter):
        """Устанавливает новый форматтер для всех обработчиков."""
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

    def setLevel(self, level):
        """
        Установка уровня логирования для логгера.

        Уровень logging, который будет использоваться для логгера, определяется параметром level.
        """
        self.logger.setLevel(level)
        # super().setLevel(level)
        if self._shared_slaves:
            self._update_shared_slaves()

    def _validate_config (self, config):
        """
        Проверка конфигурации на наличие обязательных ключей
        """
        # required_keys = [
        #     'LOG_LEVEL', 
        #     'LOG_FILE', 
        #     'LOG_MAX_BYTES', 
        #     'LOG_BACKUP_COUNT'
        # ]


        required_keys = ['LEVEL', 'FILE', 'MAX_BYTES', 'BACKUP_COUNT']
        for key in required_keys:
            # Проверяем, есть ли хотя бы один из возможных вариантов ключа
            variants = self._get_key_name_config(key)
            if not any(v in config for v in variants):
                raise ValueError(f"Отсутствует обязательный ключ '{key}' (ни один из вариантов {variants})")     

        # required_keys = []

        # for key in [
        #     'LEVEL', 
        #     'FILE', 
        #     'MAX_BYTES', 
        #     'BACKUP_COUNT'
        # ]:
        #     thec = False
        #     for key2 in self._get_key_name_config(key):
        #         if key2  in config:
        #             required_keys.append(key2)
        #             thec = True

        #     if not thec:
        #         raise ValueError(f"Отсутствует обязательный ключ '{key}' в конфигурации")

        # missing_keys = [key for key in required_keys if key not in config]

        # if missing_keys:
        #     raise ValueError(f"Отсутствуют обязательные ключи конфигурации: {missing_keys}")        

    def _load_config (self, config):
        # Обработка config: если строка, берём из другого экземпляра
        if isinstance(config, str) and config is not None:
            # parent = self._instances.get(config)
            # with type(self)._instances_lock:
            #     parent = self._instances.get(config)
            parent = self._get_parent(config)

            if parent is not None:
                # config = {
                #     'LOG_LEVEL' : dict(
                #         zip(
                #             BaseAppLogger.level_map.values(), 
                #             BaseAppLogger.level_map.keys()
                #         )
                #     )[parent.log_level],
                #     'LOG_FILE' : parent.base_log_file,
                #     'LOG_MAX_BYTES' : parent.log_max_bytes,
                #     'LOG_BACKUP_COUNT' : parent.log_backup_count,
                # }
                config = {
                    'LOG_LEVEL': dict(
                        zip(
                            BaseAppLogger.level_map.values(), 
                            BaseAppLogger.level_map.keys()
                        )
                    )[parent.log_level],
                    'LOG_FILE': parent.base_log_file,
                    'LOG_MAX_BYTES': parent.log_max_bytes,
                    'LOG_BACKUP_COUNT': parent.log_backup_count,
                    'enabled': parent._enabled,
                    'console_enabled': parent._console_enabled,
                    'file_enabled': parent._file_enabled,
                    'use_name_in_filename': parent._use_name_in_filename,
                    'use_timestamp': parent.use_timestamp,
                    'LOG_ARGS': parent.log_args,
                    'show_call_depth': parent._show_call_depth,
                }
            else:
                # родитель не найден – используем дефолт
                print(f"WARNING: Logger '{self.name}' references unknown config '{config}'", file=sys.stderr)
                config = None

        # Загружаем конфигурацию
        if config is None:
            config = self.get_default_config()

        return config

    @staticmethod
    def _to_bool(value):
        if isinstance(value, str):
            return value.lower() in ('true', '1', 'yes')
        return bool(value)
    
    def _get_config_param (
            self, 
            config: Dict[str, Any],
            key: str, 
            default: Any=None, 
            fun: Callable=None
        )-> Any:

        # if key == 'LEVEL':
        #     0==0

        temp = self._get_config(
            config= config, 
            key= key, 
            default= default,
        )

        if fun is not None:
            try:
                temp = fun(temp)
            except ValueError as e:
                raise ValueError(f"Ошибка преобразования параметров логирования: {e}")
            
        return temp

        
    def _init_config_load (self, config, enable_file_logging, use_name_in_filename)-> Dict[str, Any]:
        # Чтение флагов из конфигурации (с значениями по умолчанию)
        # self._enabled = config.get('enabled', True)
        # self._console_enabled = config.get('console_enabled', True)
        # self._file_enabled = config.get('file_enabled', bool(enable_file_logging)) # флаг для файлового вывода
        # self._use_name_in_filename = config.get('use_name_in_filename', bool(use_name_in_filename))
        # self.use_timestamp = config.get('use_timestamp', False)


        # Определяем эффективное значение флагов (с учётом ссылок)
        effective_file = self.effective_enable_file_logging(_visited=None)
        effective_name = self.effective_use_name_in_filename(_visited=None)

        # if self.name in (
        #     'Database',
        #     'DynamicTableModel',
        # ):
        #     0==0

        # Общие флаги (если есть специфичные для имени)
        result = {}
        
        # temp = self._get_config(config, 'FILE', None)
        temp = self._get_config_with_inheritance(config, 'FILE', None)
        if temp is None:
            # temp = self._get_config(config, 'DIR', 'logs')
            temp = self._get_config_with_inheritance(config, 'DIR', 'logs')

        result['FILE'] = temp

        del temp  

        for key, default, fun  in [
            ['enabled',True,self._to_bool],
            ['console_enabled',True,self._to_bool],
            ['file_enabled',effective_file, self._to_bool],
            ['use_name_in_filename',effective_name, self._to_bool],
            ['use_timestamp',False, self._to_bool],
            ['ARGS', False, self._to_bool],

            ['LEVEL', 'DEBUG', self._parse_log_level],
            # ['FILE', None, None],
            # ['DIR', None, None],
            ['MAX_BYTES', 10*1024*1024, int],
            ['BACKUP_COUNT', 5, int],
            ['show_call_depth', False, self._to_bool],
            # ['show_call_depth', True, self._to_bool],
        ]:
            # if key == 'LEVEL':
            #     0==0
            
            # result[key] = self._get_config_param(
            #     config= config, 
            #     key= key, 
            #     default= default,
            #     fun= fun,
            # )

            raw = self._get_config_with_inheritance(config, key, default)
            result[key] = fun(raw) if fun is not None else raw
            

     

        # self._enabled = self._to_bool(
        #     # config.get(
        #     #     f'{self.name}_enabled', 
        #     #     config.get('enabled', True)
        #     # )
        #     # self._get_config(
        #     #     config= config, 
        #     #     key= 'enabled', 
        #     #     default= True,
        #     # )    
        #     # 
        #     _config['enabled']            
        # )

        # self._console_enabled = self._to_bool(
        #     # config.get(
        #     #     f'{self.name}_console_enabled', 
        #     #     config.get('console_enabled', True)
        #     # )
        #     # self._get_config(
        #     #     config= config, 
        #     #     key= 'console_enabled', 
        #     #     default= True,
        #     # )  
        #     _config['console_enabled']
        # )


        # # Берём значение из конфига, если нет — используем эффективное
        # self._file_enabled = self._to_bool(
        #     # config.get(
        #     #     f'{self.name}_file_enabled', 
        #     #     # config.get('file_enabled', enable_file_logging)
        #     #     config.get('file_enabled', effective_file)
        #     # )
        #     # self._get_config(
        #     #     config= config, 
        #     #     key= 'file_enabled',
        #     #     default= effective_file,
        #     # )  
        #     _config['file_enabled']
        # )
        # self._use_name_in_filename = self._to_bool(
        #     # config.get(
        #     #     f'{self.name}_use_name_in_filename', 
        #     #     # use_name_in_filename
        #     #     effective_name
        #     # )
        #     # self._get_config(
        #     #     config= config, 
        #     #     key= 'use_name_in_filename',
        #     #     default= effective_name,
        #     # )  
        #     _config['use_name_in_filename']
        # )

        # # Приводим к bool (на случай, если в конфиге оказалась строка)
        # self._file_enabled = bool(self._file_enabled)
        # self._use_name_in_filename = bool(self._use_name_in_filename)

        # self.use_timestamp = self._to_bool(
        #     # config.get(
        #     #     f'{self.name}_use_timestamp', 
        #     #     config.get('use_timestamp', False)
        #     # )
        #     # self._get_config(
        #     #     config= config, 
        #     #     key= 'use_timestamp', 
        #     #     default= False,
        #     # )  
        #     _config['use_timestamp']
        # )

        # self.log_args = self._to_bool(
        #     # config.get('LOG_ARGS', False)
        #     # self._get_config(
        #     #     config= config, 
        #     #     key=  'ARGS', 
        #     #     default= False,
        #     # )  
        #     _config['ARGS']
        # )

        # # сохраняем во внутренние атрибуты
        # self._enabled = result['enabled']
        # self._console_enabled = result['console_enabled']
        # self._file_enabled = result['file_enabled']
        # self._use_name_in_filename = result['use_name_in_filename']
        # self.use_timestamp = result['use_timestamp']
        # self.log_args = result['ARGS']
        
        # self.log_level = result['LEVEL']
        # self.base_log_file = result['FILE']
        # self.log_max_bytes = result['MAX_BYTES']
        # self.log_backup_count = result['BACKUP_COUNT']
        # self._show_call_depth = result['show_call_depth']


        return result

    def dump_config(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'enabled': self._enabled,
            'console_enabled': self._console_enabled,
            'file_enabled': self._file_enabled,
            'level': logging.getLevelName(self.log_level),
            'use_name_in_filename': self._use_name_in_filename,
            'use_timestamp': self.use_timestamp,
            'log_FILE': self._get_log_file(),
        }

    def get_config(self) -> Dict[str, Any]:
        """Возвращает текущую конфигурацию логгера."""
        return {
            'level': logging.getLevelName(self.log_level),
            'base_log_FILE': self.base_log_file,
            'log_MAX_BYTES': self.log_max_bytes,
            'log_BACKUP_COUNT': self.log_backup_count,
            'log_ARGS': self.log_args,
            'enabled': self._enabled,
            'console_enabled': self._console_enabled,
            'file_enabled': self._file_enabled,
            'use_name_in_filename': self._use_name_in_filename,
            'use_timestamp': self.use_timestamp,
        }

    def _save_handlers (self):
        """Сохраняет копию списка обработчиков."""
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

    def is_enabled(self) -> bool:
        return self._enabled

    def is_console_enabled(self) -> bool:
        return self._console_enabled

    def is_file_enabled(self) -> bool:
        return self._file_enabled
    
    def has_shared_handler(self) -> bool:
        """Возвращает True, если логгер использует общий файловый обработчик."""
        return self._shared_handler
    
    def _sync_all_from_master(self):
        """Копирует все настройки от мастера (для слейва)."""
        if not self._master_logger:
            return
        
        self.log_level = self._master_logger.log_level # устанавливаем уровень
        self.logger.setLevel(self.log_level) # устанавливаем уровень

        self.formatter = self._master_logger.formatter # устанавливаем формат
        self.base_log_file = self._master_logger.base_log_file # устанавливаем имя файла
        self.log_max_bytes = self._master_logger.log_max_bytes # устанавливаем максимальный размер файла
        self.log_backup_count = self._master_logger.log_backup_count # устанавливаем количество бэкапов
        self.use_timestamp = self._master_logger.use_timestamp # устанавливаем флаг использования времени
        self.log_args = self._master_logger.log_args # устанавливаем флаг использования аргументов
        self._use_name_in_filename = self._master_logger._use_name_in_filename  # устанавливаем флаг использования имени
        self._file_enabled = self._master_logger._file_enabled  # устанавливаем флаг использования файлового обработчика

        self._sync_full_state = self._master_logger._sync_full_state # устанавливаем флаг использования полного состояния

        # Копируем флаги консоли и включения только если явно запрошено
        if self._sync_full_state: # Если нужно, чтобы слейв имел независимую консоль
            # Если нужно, чтобы слейв имел независимую консоль - убираем эти две строки
            self._console_enabled = self._master_logger._console_enabled  # устанавливаем флаг использования консольного обработчика
            self._enabled = self._master_logger._enabled    # устанавливаем флаг включения

        self._show_call_depth = self._master_logger._show_call_depth  # устанавливаем флаг использования глубины стека вызовов

        # Обновляем обработчик, если он уже привязан
        if self.console_handler: # Если есть консольный обработчик
            self.console_handler.setLevel(self.log_level) # устанавливаем уровень

        self._sync_log_level_and_formatters()  # Синхронизируем уровень и формат



    def _update_file_handler_if_not_shared(
        self,
    ):
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
        master_handler, master_log_level, master_formatter, master_base_log_file,
        master_max_bytes, master_backup_count, master_timestamp,
        master_file_enabled, master_use_name, master_sync_full, master_args, master_show_depth
    ):
        if master_handler is None: 
            return
        
        if self.file_handler != master_handler:
            if self.file_handler and self.file_handler in self.logger.handlers:
                self.logger.removeHandler(self.file_handler)
                # self.file_handler.close() # Не закрываем обработчик – он может использоваться другими слейвами

            self.file_handler = master_handler
            self._reopen_file_handler_if_needed()

            self.log_level = master_log_level
            self.logger.setLevel(self.log_level)
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

    def _update_file_handler_if_on (
        self,
    ):
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

                    visited = set()
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
                        'master_file_enabled': master.effective_enable_file_logging(_visited=visited),
                        'master_use_name': master.effective_use_name_in_filename(_visited=visited),
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

    def _update_file_handler (
        self,
    ):
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

    def _update_console_handler (
        self,
    ):
        # Консольный обработчик (всегда создаётся заново, если включён)
        if self._console_enabled:
            self.console_handler = logging.StreamHandler()
            self.console_handler.setLevel(self.log_level)
            self.console_handler.setFormatter(self.formatter)
            self.logger.addHandler(self.console_handler)
        else:
            self.console_handler = None

    def _del_console_handler_and_file_handler (
        self,
        if_close_console_handler=True,
        if_close_file_handler=True,
    ):
        # Удаляем старые «свои» обработчики (консольный и файловый, если они не общие)

        #    Закрываем их только если они не являются общими с другими логгерами.
        self._remove_console_handler(if_close_console_handler=if_close_console_handler)

        if self.file_handler and not self._shared_handler:
            self._remove_file_handler(if_close_file_handler=if_close_file_handler)

    def _get_all_handlers (
        self,
    ):
        with BaseAppLogger._global_handlers_lock:
            return list(BaseAppLogger._global_handlers)
        
    def _set_all_handlers (
        self,
        handlers_copy,
    ):             
        for handler in handlers_copy:
            if handler not in self.logger.handlers:
                self.logger.addHandler(handler)
                
    
    def _update_handlers(self):
        """
        Обновляет набор обработчиков (консольный и файловый) в соответствии с текущими флагами:
        - _enabled, _console_enabled, _file_enabled
        - _shared_handler (использует общий обработчик от другого логгера)
        - эффективные значения (с учётом ссылок enable_file_logging_ref)

        При включении файлового логирования дополнительно вызывает _reopen_file_handler_if_needed()
        для восстановления файла, если он был удалён извне.

        После обновления собственных обработчиков синхронизирует зависимые логгеры (_shared_slaves).

        Пытаться НЕ вызывать в блокировках. Блокировка self._handler_lock уже есть
        """
        def _tt():
            with self._handler_lock:
                # 1. Удаляем старые «свои» обработчики (консольный и файловый, если они не общие)
                #    Закрываем их только если они не являются общими с другими логгерами.
                self._del_console_handler_and_file_handler(
                    if_close_console_handler=True,
                    if_close_file_handler=True,
                )

                # Если логгер полностью отключён – больше ничего не добавляем
                if not self._enabled:
                    return
                
                self._update_console_handler() # Консольный обработчик (всегда создаётся заново, если включён)

                # Добавляем глобальные обработчики (под блокировкой)
                
                handlers_copy = self._get_all_handlers()
                self._set_all_handlers(handlers_copy)

                # self._save_handlers()
                # if not self._shared_handler and self._file_enabled:
                #     self._update_file_handler()

                # Создаём свой файловый обработчик, если не общий и включён
                # Файловый обработчик – только если не используется общий и файловое логирование включено

                if not self._shared_handler and self._file_enabled:
                    self._update_file_handler()
                    
                # Для остальных случаев (общий обработчик или потеря мастера) – не создаём,
                # так как они будут обработаны позже без блокировки
                # self._save_handlers()   # сохраняем состояние после базовой настройки

            with BaseAppLogger._share_lock:
                # Обновление общего обработчика (без удержания self._handler_lock)
                if self._shared_handler and self._master_logger:
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

    def _create_file_handler(self):
        """Создаёт файловый обработчик на основе текущих настроек."""

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

        handler.setLevel(self.log_level) # Устанавливаем уровень
        handler.setFormatter(self.formatter) # Устанавливаем формат

        return handler

    def _get_log_file(self):
        """Возвращает имя файла лога с учётом use_name_in_filename."""
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
        """Формирует имя файла внутри директории с учётом use_name_in_filename и use_timestamp."""
        
        timestamp = self._start_timestamp
        
        name =  f"{self.name}" if self.use_name_in_filename else f"app"
        
        if self.use_name_in_filename:
            timestamp = timestamp if self.use_timestamp else ""
            name = f"{name}_{timestamp}" if timestamp else name
            # filename = f"{base_name}.log"
        else:
            if self.use_timestamp:
                name = f"{name}_{timestamp}"

        filename = f"{name}.log" 

        return os.path.join(dir_path, filename)    

    def _sync_log_level_and_formatters (self):
        # Синхронизируем уровень и формат для файлового обработчика
        if self.file_handler: # Если есть файловый обработчик
            self.file_handler.setLevel(self.log_level) # устанавливаем уровень 
            self.file_handler.setFormatter(self.formatter) # устанавливаем формат 
 
    # def _sync_formatters (self, formatter):
    #     # Синхронизация форматирования
    #     self.formatter = formatter
    #     if self.file_handler:
    #         self.file_handler.setFormatter(self.formatter)

    def _set_file_handler (self, file_handler):
        # Берём обработчик другого логгера
        self.file_handler = file_handler

        # Добавляем, если ещё не добавлен (защита от дублирования)
        if self.file_handler not in self.logger.handlers:
            self.logger.addHandler(self.file_handler)

    def _remove_console_handler (self, if_close_console_handler: bool = True):
        # Удаляем старые "свои" обработчики, если они были
        if self.console_handler:
            self.logger.removeHandler(self.console_handler)

            if if_close_console_handler:
                self.console_handler.close()

            self.console_handler = None

    def _remove_file_handler (self, if_close_file_handler: bool = True):
        # Удаляем текущий файловый обработчик, если есть
        if self.file_handler:
            self.logger.removeHandler(self.file_handler)

            if if_close_file_handler:
                self.file_handler.close()

            self.file_handler = None

    def share_file_handler_with(
        self, 
        other: 'BaseAppLogger',
        sync_full_state: Optional[bool] = None,
    ) -> None:
        """
        Добавляет файловый обработчик другого логгера к текущему.
        После этого оба логгера пишут в один и тот же файл (с общей ротацией).

        sync_full_state: синхронизировать состояние, если True
        (состояние: включен ли файловый логирование, включен ли обработчик, etc.)

        ВНИМАНИЕ: после вызова этого метода НЕ вызывайте turn_off_file_logging()
        у текущего логгера, так как это закроет общий обработчик и остановит
        запись и для другого логгера. Для отключения файлового логирования
        у текущего логгера используйте этот метод только если другой логгер
        больше не нуждается в обработчике, или управляйте файловым логированием
        через исходный логгер.
        
        """

        if self is other:
            return

        # Если уже расшарены друг с другом – выходим
        if self._master_logger is other or other._master_logger is self:
            return

        with BaseAppLogger._share_lock:
        
            if self._shared_handler:
                # self.unshare_file_handler(if_update_handlers=False)
                # Ручная отвязка без дополнительных блокировок
                self._unshare_file_handler_master_logger()
                with self._handler_lock:
                    # При отвязке от старого мастера изменение self._shared_handler, self._master_logger, self.file_handler 
                    # происходит без захвата self._handler_lock. Хотя эти поля защищены _share_lock (который уже захвачен), 
                    # в других методах они могут читаться без _share_lock. Во избежание неконсистентности рекомендуется 
                    # обернуть эти операции в self._handler_lock
                    
                    self._remove_file_handler(if_close_file_handler=False)
                    self._shared_handler = False
                    self._master_logger = None
                    self.file_handler = None

            # Упорядочиваем локи по id объектов
            first, second = sorted([self, other], key=id)
            with first._handler_lock, second._handler_lock:
                # Проверка, что у other есть активный файловый обработчик
                if other.file_handler is None or not other._file_enabled or not other._enabled:
                    self.logger.warning(
                        f"Логгер '{other.name}' не имеет активного файлового обработчика. "
                        "Сначала включите файловое логирование у исходного логгера."
                    )
                    return
                
                self._remove_file_handler( # Удаляем текущий файловый обработчик, если есть
                    if_close_file_handler=not self._shared_handler
                )
                self._set_file_handler( # Берём обработчик другого логгера
                    file_handler=other.file_handler
                )

                # if sync_full_state is None:
                #     sync_full_state = other._sync_full_state
                    
                # self._sync_full_state = sync_full_state # сохраняем флаг синхронизации

                # self.base_log_file = other.base_log_file    # синхронизация пути

                # self.log_level = other.log_level            # синхронизация уровня
                # self.logger.setLevel(self.log_level)        # применение уровня # важно: уровень логгера тоже должен совпадать

                # if self.file_handler:
                #     self.file_handler.setLevel(self.log_level)  

                # self._sync_formatters( # Синхронизация форматирования
                #     formatter=other.formatter
                # )

                # self.log_args = other.log_args

                # # Используем обработчик другого логгера
                # self.file_handler = other.file_handler
                # self.logger.addHandler(self.file_handler) # Добавляем обработчик


                # Синхронизируем параметры ротации, чтобы при возможном пересоздании обработчика
                # использовались актуальные значения
                # self.log_max_bytes = other.log_max_bytes 
                # self.log_backup_count = other.log_backup_count

                # self.use_timestamp = other.use_timestamp

                # # Синхронизируем флаги и параметры
                # self._file_enabled = other._file_enabled  # флаг, что файловое логирование включено
                # self._use_name_in_filename = other.use_name_in_filename  # копируем настройку
                # self._file_enabled = other.effective_enable_file_logging() # флаг, что файловое логирование включено
                # self._use_name_in_filename = other.effective_use_name_in_filename() # копируем настройку

                # self._file_enabled = bool(self._file_enabled)
                # self._use_name_in_filename = bool(self._use_name_in_filename)

                # Устанавливаем флаги общего обработчика
                self._shared_handler = True     # признак общего обработчика
                self._master_logger = other     # запоминаем, от кого взяли обработчик (мастер)

                # # Применяем уровень к логгеру
                # self.logger.setLevel(self.log_level)

                self._sync_all_from_master() # Синхронизируем уровень и формат для файлового обработчика # копирует все параметры, включая _sync_full_state от мастера
                
                if sync_full_state is not None:
                    self._sync_full_state = sync_full_state # сохраняем флаг синхронизации (добавляем из шапки ф-ции)

                # # После успешного шаринга зарегистрировать текущего как зависимого у мастера
                # if other != self and other not in other._shared_slaves:
                #     other._shared_slaves.append(self)

                # Регистрируем себя как слейва у мастера
                # if self not in other._shared_slaves:
                if not any(ref() is self for ref in other._shared_slaves):
                    # other._shared_slaves.append(self)
                    other._shared_slaves.append(weakref.ref(self))

                # self._sync_log_level_and_formatters() # Синхронизируем уровень и формат для файлового обработчика

                self._save_handlers() # Сохраняем ссылки на обработчики (может пригодиться для GUI)

                # Перестраиваем обработчики, чтобы новый уровень применился к консоли и файлу
                self._update_handlers()
                
                self._reopen_file_handler_if_needed() # Проверяем, нужно ли переоткрыть файловый обработчик



    def get_shared_group(self) -> List['BaseAppLogger']:
        """Возвращает список всех логгеров, использующих тот же файловый обработчик."""
        with BaseAppLogger._share_lock:
            # if self._shared_handler and self._master_logger:
            #     # слейв: возвращаем мастера и всех его слейвов
            #     result = {self._master_logger}.union(self._master_logger._shared_slaves)
            #     return list(result)
            
            # elif self._shared_slaves:
            #     # мастер: возвращаем себя и всех слейвов
            #     return [self] + self._shared_slaves
            
            # return [self]
            if self._shared_handler and self._master_logger:
                # Собираем мастера и всех живых слейвов
                result = {self._master_logger}
                for ref in self._master_logger._shared_slaves:
                    slave = ref()
                    if slave is not None:
                        result.add(slave)

                return list(result)
            
            elif self._shared_slaves:
                result = {self}
                for ref in self._shared_slaves:
                    slave = ref()
                    if slave is not None:
                        result.add(slave)

                return list(result)
            
            return [self]
    
    # def _sync_console_handler (self, slave) -> None:
    #     # Если у зависимого логгера включён консольный вывод, убедимся, что его уровень совпадает
    #     with self._handler_lock:                # блокировка мастера
    #         level = self.log_level

    #     with slave._handler_lock:
    #         if slave._console_enabled and slave.console_handler:
    #             # slave.console_handler.setLevel(self.log_level)
    #             slave.console_handler.setLevel(level)

    # def _sync_formatters_slave (self, slave, formatter) :
    #     with slave._handler_lock:
    #         if slave.formatter != formatter:
    #             slave.formatter = formatter

    #             # Для консольного обработчика тоже нужно обновить формат (если он есть)
    #             if slave.console_handler:
    #                 slave.console_handler.setFormatter(formatter)

    #             if slave.file_handler:
    #                 slave.file_handler.setFormatter(formatter)

    # def _sync_log_formatters(self, slave) -> None:
    #     # Синхронизируем формат сообщений (если изменился у мастера)
    #     with self._handler_lock:                # блокировка мастера
    #         formatter = self.formatter

    #     self._sync_formatters_slave(
    #         slave = slave,
    #         formatter = formatter
    #     )  
                
    def _update_shared_slave(self, slave, master_state: dict) -> None:
        """
        Полностью синхронизирует одного слейва с мастером, используя переданное состояние мастера.
        
        :param slave: экземпляр слейва (BaseAppLogger)
        :param master_state: словарь с ключами:
            - 'file_handler': файловый обработчик мастера
            - 'log_LEVEL': уровень логирования мастера
            - 'formatter': форматтер мастера
            - 'base_log_FILE', 'log_MAX_BYTES', 'log_BACKUP_COUNT', 'use_timestamp',
            'use_name_in_filename', 'sync_full_state', 'show_call_depth', 'log_ARGS'
            - 'console_enabled' (опционально, для консольного уровня)
        """
        if slave is None:
            return
        
        with slave._handler_lock:
            master_handler = master_state['file_handler']
            if master_handler is None:
                return

            # --- файловый обработчик обновляем ТОЛЬКО если он есть у мастера и у слейва разрешён файловый вывод ---
            if master_handler is not None and slave._file_enabled:
                # 1. Обновляем файловый обработчик
                if slave.file_handler != master_handler:
                    if slave.file_handler and slave.file_handler in slave.logger.handlers:
                        slave.logger.removeHandler(slave.file_handler)

                    slave.file_handler = master_handler
                    slave._reopen_file_handler_if_needed()

                # 2. Добавляем обработчик, если его нет    
                if master_handler not in slave.logger.handlers:
                    slave.logger.addHandler(master_handler)

            
            # if slave.file_handler != master_handler:
            #     if slave.file_handler and slave.file_handler in slave.logger.handlers:
            #         slave.logger.removeHandler(slave.file_handler)
            #     slave.file_handler = master_handler

            #     slave._reopen_file_handler_if_needed()

            # if master_handler not in slave.logger.handlers:
            #     slave.logger.addHandler(master_handler)


            # --- основные параметры синхронизируются ВСЕГДА ---
            # 3. Синхронизируем параметры (уровень, формат, лимиты и т.д.)
            slave.log_level = master_state['log_LEVEL']
            slave.logger.setLevel(slave.log_level)

            if slave.file_handler:
                slave.file_handler.setLevel(slave.log_level)

            slave.log_max_bytes = master_state['log_MAX_BYTES']
            slave.log_backup_count = master_state['log_BACKUP_COUNT']
            slave.base_log_file = master_state['base_log_FILE']
            slave._use_name_in_filename = master_state['use_name_in_filename']
            slave.use_timestamp = master_state['use_timestamp']
            slave._sync_full_state = master_state['sync_full_state']
            slave._show_call_depth = master_state['show_call_depth']
            slave.log_args = master_state['log_ARGS']

            # 4. Форматтер
            if slave.formatter != master_state['formatter']:
                slave.formatter = master_state['formatter']

                if slave.console_handler:
                    slave.console_handler.setFormatter(master_state['formatter'])

                if slave.file_handler:
                    slave.file_handler.setFormatter(master_state['formatter'])

            # 5. Консольный уровень (если консольный вывод включён)
            if slave._console_enabled and slave.console_handler:
                slave.console_handler.setLevel(slave.log_level)

            # --- полная синхронизация флагов (опционально) ---
            # 5.1. Синхронизация флагов консоли и включения, если требуется полная синхронизация
            if master_state.get('sync_full_state', False):
                slave._console_enabled = master_state['console_enabled']
                slave._enabled = master_state['enabled']

            # 6. Сохраняем список обработчиков для GUI
            slave._save_handlers()


    def _get_shared_slaves(self) -> Tuple[List, List]: 
        # Разыменовываем слабые ссылки, удаляем мёртвые
        active_slaves = []
        dead_refs = []

        for ref in self._shared_slaves[:]:
            slave = ref()
            if slave is not None:
                active_slaves.append(slave)
            else:
                dead_refs.append(ref)
        
        return active_slaves, dead_refs
    

    def _get_master_state(self) -> Dict[str, Any]:
        with self._handler_lock:
            return  {
                'file_handler': self.file_handler,
                'log_LEVEL': self.log_level,
                'formatter': self.formatter,
                'base_log_FILE': self.base_log_file,
                'log_MAX_BYTES': self.log_max_bytes,
                'log_BACKUP_COUNT': self.log_backup_count,
                'use_timestamp': self.use_timestamp,
                'use_name_in_filename': self._use_name_in_filename,
                'sync_full_state': self._sync_full_state,
                'show_call_depth': self._show_call_depth,
                'log_ARGS': self.log_args,

                'console_enabled': self._console_enabled,
                'enabled': self._enabled,
                # 'sync_full_state': self._sync_full_state,
            }  
    def _update_shared_slaves(self) -> None:
        """
        Обновляет всех зависимых логгеров (которые используют наш файловый обработчик)
        при изменении параметров мастера (уровень, путь, лимиты и т.д.).
        """

        with BaseAppLogger._share_lock:

            if not self._shared_slaves:
                return
            
            # Разыменовываем слабые ссылки, удаляем мёртвые
            active_slaves, dead_refs = self._get_shared_slaves() 

            for ref in dead_refs:
                # Ссылка мертва – удаляем её из списка
                self._shared_slaves.remove(ref)

            if not active_slaves:
                return
            
            # slaves_copy = list(active_slaves)   # делаем копию

        master_state = self._get_master_state()
        
        if master_state['file_handler'] is None:
            # У мастера нет файлового обработчика – ничего не синхронизируем
            return

        for slave in active_slaves:  # копия на случай изменения списка
            # Если зависимый логгер уже неактивен или отключил файловое логирование – пропускаем
            # if not slave._enabled or not slave._file_enabled:
            # if not slave._enabled or not slave.effective_enable_file_logging(_visited=None):
            #     continue
            if not slave._enabled:
                continue

            self._update_shared_slave(slave, master_state )# Убедимся, что он всё ещё использует наш обработчик # внутри будет захвачен slave._handler_lock, но _share_lock уже свободен

            # self._sync_log_formatters(slave) # Синхронизируем формат сообщений (если изменился у мастера)
        
            # self._sync_console_handler(slave) # Если у зависимого логгера включён консольный вывод, убедимся, что его уровень совпадает

   

    def _unshare_file_handler_master_logger (self):
        # Предполагается, что вызывающий код уже удерживает BaseAppLogger._share_lock
   
        master = self._master_logger
        if master is not None:
            # Удаляем текущий логгер из списка зависимых у мастера
            try:
                # master._shared_slaves.remove(self)
                # Ищем слабую ссылку на self в списке мастера
                for ref in master._shared_slaves[:]:
                    if ref() is self:
                        master._shared_slaves.remove(ref)
                        break

            except ValueError:
                # Если по какой-то причине нас там нет – игнорируем
                self.logger.warning(
                    f"Логгер '{self.name}' не найден в списке зависимых мастера '{master.name}'"
                )
            # Также можно уведомить мастера, что он больше не должен обновлять нас
        else:
            self.logger.warning(
                f"Логгер '{self.name}' имеет флаг _shared_handler=True, но _master_logger отсутствует"
            )

    def unshare_file_handler(self, if_update_handlers=True) -> None:
        """
        Отвязывает текущий логгер от общего обработчика и создаёт собственный.
        """
        with BaseAppLogger._share_lock:
            if not self._shared_handler:
                return
            
            with self._handler_lock:
                self._unshare_file_handler_master_logger()

                self._remove_file_handler( # Удаляем общий обработчик  (не закрываем, т.к. он может использоваться другим)
                    if_close_file_handler=False # (не закрываем, т.к. он может использоваться другим)
                ) 
                self.file_handler = None
                self._shared_handler = False
                self._master_logger = None

        if if_update_handlers:
            # Пересоздаём собственный обработчик согласно текущим настройкам
            self._update_handlers()

    def get_master_logger(self):
        """Возвращает логгер, предоставивший общий обработчик, или None."""
        return self._master_logger

    def set_console_level(self, level_str: str):
        """Устанавливает уровень логирования для консольного вывода."""
        level = self._parse_log_level(level_str)
        if self.console_handler:
            self.console_handler.setLevel(level)

    def set_file_level(self, level_str: str):
        """Устанавливает уровень логирования для файлового вывода."""
        level = self._parse_log_level(level_str)
        if self.file_handler:
            self.file_handler.setLevel(level)

    def _update_file_params(self, **kwargs) -> bool:
        """Обновляет параметры, связанные с файловым логированием.
        Возвращает True, если требуется перестроить обработчики.
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

    def _update_flags(self, **kwargs) -> bool:
        """Обновляет флаги включения/отключения.
        Возвращает True, если требуется перестроить обработчики.
        """
        need_rebuild = False
        level_changed = False

        if 'console_enabled' in kwargs:
            self._console_enabled = self._to_bool(kwargs['console_enabled'])
            need_rebuild = True

        if 'file_enabled' in kwargs:
            self._file_enabled = self._to_bool(kwargs['file_enabled'])
            need_rebuild = True

        if 'enabled' in kwargs:
            self._enabled = self._to_bool(kwargs['enabled'])
            need_rebuild = True

        # Отдельные уровни для консоли и файла (не требуют перестройки)
        if 'console_level' in kwargs:
            self.set_console_level(kwargs['console_level'])
            level_changed = True

        if 'file_level' in kwargs:
            self.set_file_level(kwargs['file_level'])
            level_changed = True

        return need_rebuild or level_changed

    def reconfigure(self, **kwargs):
        """
        Динамически изменяет настройки логгера.
        Поддерживаемые ключи:
            - level: str ('DEBUG', 'INFO', ...)
            - base_log_file: str
            - log_max_bytes: int
            - log_backup_count: int
            - enable_file_logging: bool
            - use_name_in_filename: bool
            - console_enabled: bool
            - file_enabled: bool
            - enabled: bool
        """
        # Если используем общий обработчик, перенаправляем вызов мастеру
        if self._shared_handler and self._master_logger:
            # self.logger.debug(f"Перенаправляю reconfigure мастеру '{self._master_logger.name}'")
            self._master_logger.reconfigure(**kwargs)
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
    
    @classmethod
    def disable_group_console(cls, name_prefix: str):
        """Отключает вывод в консоль для всех логгеров группы."""
        with cls._instances_lock:
            for inst in cls._instances.values():
                if inst.name.startswith(name_prefix):
                    inst.disable_console()

    @classmethod
    def enable_group_console(cls, name_prefix: str):
        """Включает вывод в консоль для всех логгеров группы."""
        with cls._instances_lock:
            for inst in cls._instances.values():
                if inst.name.startswith(name_prefix):
                    inst.enable_console()

    @classmethod
    def disable_group_file(cls, name_prefix: str):
        """Отключает файловое логирование для всех логгеров группы."""
        with cls._instances_lock:
            for inst in cls._instances.values():
                if inst.name.startswith(name_prefix):
                    inst.turn_off_file_logging()

    @classmethod
    def enable_group_file(cls, name_prefix: str):
        """Включает файловое логирование для всех логгеров группы."""
        with cls._instances_lock:
            for inst in cls._instances.values():
                if inst.name.startswith(name_prefix):
                    inst.turn_on_file_logging()

    # Также можно добавить установку уровня отдельно для консоли и файла для группы:
    @classmethod
    def set_group_console_level(cls, name_prefix: str, level: str):
        """Устанавливает уровень логирования для консольного вывода всех логгеров группы."""
        with cls._instances_lock:
            lvl = cls._parse_log_level(level)
            for inst in cls._instances.values():
                if inst.name.startswith(name_prefix):
                    inst.set_console_level(lvl)

    @classmethod
    def set_group_file_level(cls, name_prefix: str, level: str):
        """Устанавливает уровень логирования для файлового вывода всех логгеров группы."""
        with cls._instances_lock:
            lvl = cls._parse_log_level(level)
            for inst in cls._instances.values():
                if inst.name.startswith(name_prefix):
                    inst.set_file_level(lvl)

    def _get_key_name_config (self, key, list_name:List = None) -> List:
        """
        Возвращает список ключей для конфига с учётом префиксов.
        Приоритет: {self.name}_{key} -> LOG_{key} -> key
        """
        rezult = []

        if list_name is None:
            list_name = [
                self.name,  # Сначала ищем специфичный для этого логгера
                'LOG',      # Затем общий для всех логгеров (с префиксом LOG_)
                None,       # Наконец, просто ключ (без префикса)
            ]

        for i in list_name:
            name_key = "_".join(
                [i, key]
            ) if i else key

            rezult.append(name_key)

        return rezult

    def _get_config (
        self, 
        config: Dict[str, Any], 
        key: str, 
        default: Any = None,
        if_lower: bool = False,
    ) -> Any:
        """
        Возвращает значение параметра из конфига с учётом префиксов.
        Приоритет: {self.name}_{key} -> LOG_{key} -> key -> default
        """
        # if key == 'LEVEL':
        #     0==0

        if if_lower:
            list_key = list(config.keys())
            lowercase_dict = list(map(str.lower, list_key))

        for name_key in self._get_key_name_config(key):
            if if_lower:
                try:
                    index= lowercase_dict.index(name_key.lower())
                except ValueError:
                    index= None

                if index is not None:
                    return config[list_key[index]]
            else:
                if name_key in config :
                    return config[name_key]
                      
        else:
            return default


    def _update_config_from (self, config_dict):
        # Обновляем текущие параметры

            _config = self._init_config_load(config_dict, None, None)

            self._apply_config(_config)   # вместо ручного присваивания

            # # обновление остальных параметров
            # self._enabled = _config['enabled']
            # self._console_enabled = _config['console_enabled']
            # self._file_enabled = _config['file_enabled']
            # self._use_name_in_filename = _config['use_name_in_filename']
            # self.use_timestamp = _config['use_timestamp']
            # self.log_args = _config['ARGS']
            
            # self.log_level = _config['LEVEL']
            # self.base_log_file = _config['FILE']
            # self.log_max_bytes = _config['MAX_BYTES']
            # self.log_backup_count = _config['BACKUP_COUNT']
            # self._show_call_depth = _config['show_call_depth']

            # if 'LEVEL' in _config:
            #     # self.log_level = self._parse_log_level(config_dict['LOG_LEVEL'])
            #     # self.log_level = self._parse_log_level(_config['LEVEL'])
            #     self.logger.setLevel(self.log_level)

            # if 'FILE' in config_dict:
            #     # self.base_log_file = config_dict['LOG_FILE']
            #     self.base_log_file = _config['FILE']


            # if 'BYTES' in config_dict:
            #     # self.log_max_bytes = int(config_dict['LOG_MAX_BYTES'])
            #     self.log_max_bytes = int(_config['MAX_BYTES'])

            # if 'BACKUP_COUNT' in config_dict:
            #     # self.log_backup_count = int(config_dict['LOG_BACKUP_COUNT'])
            #     self.log_backup_count = int(_config['BACKUP_COUNT'])

            # if 'ARGS' in config_dict:
            #     # self.log_args = self._to_bool(config_dict['LOG_ARGS'])
            #     self.log_args = self._to_bool(_config['ARGS'])

            # if 'show_call_depth' in config_dict:
            #     # self._show_call_depth = self._to_bool(config_dict['show_call_depth'])
            #     self._show_call_depth = self._to_bool(_config['show_call_depth'])


    def reload_from_config(self, new_config: Dict[str, Any]):
        """
        Полностью перезагружает настройки логгера из словаря.
        Удобно вызывать после изменения конфигурации приложения.
        """
        # # Если используем общий обработчик, перенаправляем вызов мастеру
        # if self._shared_handler and self._master_logger:
        #     self._master_logger.reload_from_config(new_config)
        #     return
        
        need_rebuild = False
        with self._handler_lock:
            # Сохраняем старые флаги для сравнения
            old_file_enabled = self._file_enabled
            old_console_enabled = self._console_enabled
            old_enabled = self._enabled
            old_base_log_file = self.base_log_file
            old_max_bytes = self.log_max_bytes
            old_backup_count = self.log_backup_count
            old_use_timestamp = self.use_timestamp
            old_use_name = self._use_name_in_filename

            self._update_config_from(new_config)

            # # Применяем новые настройки
            # # self._init_config_load(new_config, self._file_enabled, self._use_name_in_filename)
            # self._init_config_load(new_config, None, None)

            # # Обновляем остальные параметры
            # if 'LOG_LEVEL' in new_config:
            #     # self.log_level = self._parse_log_level(new_config['LOG_LEVEL'])
            #     self.log_level = self._parse_log_level(
            #         self._get_config(
            #             config=new_config, 
            #             key='LEVEL',
            #         )
            #     )
            #     self.logger.setLevel(self.log_level)

            # if 'LOG_FILE' in new_config:
            #     # self.base_log_file = new_config['LOG_FILE']
            #     self.base_log_file = self._get_config(
            #         config= new_config, 
            #         key= 'FILE',
            #     )

            # if 'LOG_MAX_BYTES' in new_config:
            #     # self.log_max_bytes = int(new_config['LOG_MAX_BYTES'])
            #     self.log_max_bytes = int(
            #         self._get_config(
            #             config= new_config, 
            #             key= 'MAX_BYTES',
            #         )
            #     )

            # if 'LOG_BACKUP_COUNT' in new_config:
            #     # self.log_backup_count = int(new_config['LOG_BACKUP_COUNT'])
            #     self.log_backup_count = int(
            #         self._get_config(
            #             config= new_config, 
            #             key= 'BACKUP_COUNT',
            #         )
            #     )

            # if 'LOG_ARGS' in new_config:
            #     # self.log_args = self._to_bool(new_config['LOG_ARGS'])
            #     self.log_args = self._to_bool(
            #         self._get_config(
            #             config= new_config, 
            #             key= 'ARGS',
            #         )
            #     )

            # if 'show_call_depth' in new_config:
            #     # self._show_call_depth = self._to_bool(new_config['show_call_depth'])
            #     self._show_call_depth = self._to_bool(
            #         self._get_config(
            #             config= new_config, 
            #             key= 'show_call_depth',
            #         )
            #     )

            # if 'use_timestamp' in new_config:
            #     # self.use_timestamp = self._to_bool(new_config['use_timestamp'])
            #     self.use_timestamp = self._to_bool(
            #         self._get_config(
            #             config= new_config, 
            #             key= 'use_timestamp',
            #         )
            #     )


            need_rebuild = ( # Проверяем, изменились ли параметры, требующие перестройки обработчиков
                self._file_enabled != old_file_enabled or
                self._console_enabled != old_console_enabled or
                self._enabled != old_enabled or
                self.base_log_file != old_base_log_file or
                self.log_max_bytes != old_max_bytes or
                self.log_backup_count != old_backup_count or
                self.use_timestamp != old_use_timestamp or
                self._use_name_in_filename != old_use_name
            )

        # применение изменений БЕЗ блокировки
        # Если изменились флаги – перестраиваем обработчики
        if need_rebuild:
            self._update_handlers()

        else:
            # Иначе просто обновляем уровни у существующих обработчиков
            for handler in self.logger.handlers:
                handler.setLevel(self.log_level)

            # if self._shared_slaves:
            self._update_shared_slaves()

            # if self._shared_slaves:
            #     self._update_shared_slaves()
    
    
    # ----------------------------------------------------------------------
    # Методы для включения/отключения логирования
    # ----------------------------------------------------------------------



    def _set_enabled(self, value: bool):
        """
        Устанавливает состояние логирования.

        возвращает True, если изменилось
        """
        with self._handler_lock:
            if self._enabled != value:
                self._enabled = value

                return True
            
        return False
    


    def _set_console_enabled(self, value: bool):
        """
        Устанавливает состояние вывода в консоль

        возвращает True, если изменилось
        """
        with self._handler_lock:
            if self._console_enabled != value:
                self._console_enabled = value

                return True
            
        return False

    def _set_file_enabled(self, value: bool):
        """
        Устанавливает состояние вывода в файл

        возвращает True, если изменилось
        """
        with self._handler_lock:
            if self._file_enabled != value:
                self._file_enabled = value

                return True
            
        return False

    def enable(self):
        """
        Полностью включает логирование (консоль + файл согласно настройкам).
        """
        if self._set_enabled(True):
            self._update_handlers()

    def disable(self):
        """
        Полностью отключает логирование (ничего не выводится).
        """
        if self._set_enabled(False):
            self._update_handlers()

    def enable_console(self):
        """
        Включает вывод в консоль.
        """
        if self._set_console_enabled(True):
            self._update_handlers()

    def disable_console(self):
        """
        Отключает вывод в консоль.
        """
        if self._set_console_enabled(False):
            self._update_handlers()

    def enable_file(self):
        self.turn_on_file_logging()

    def disable_file(self):
        self.turn_off_file_logging()

    def turn_on_file_logging(self):
        """
        Включает файловое логирование.
        """
        if self.effective_enable_file_logging(_visited=None):
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
           

    def turn_off_file_logging(self):
        """
        Отключает файловое логирование.
        """
        if self._shared_slaves:
            with BaseAppLogger._share_lock:
                # Используем копию списка, так как он будет изменяться
                for slave_ref in self._shared_slaves[:]:
                    slave = slave_ref()
                    if slave is not None:
                        slave.unshare_file_handler(if_update_handlers=True)

        # Если файловое логирование уже отключено, ничего не делаем
        if not self.effective_enable_file_logging(_visited=None):
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

    def _update_level(self, new_level):
        level = self._parse_log_level(new_level)
        if level != self.log_level:
            self.log_level = level
            self.logger.setLevel(level)
            for handler in self.logger.handlers:
                handler.setLevel(level)
   
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
        """Возвращает текущее состояние файлового логирования (bool)."""
        return self._file_enabled

    @enable_file_logging.setter
    def enable_file_logging(self, value: bool):
        """Устанавливает состояние файлового логирования через свойство."""

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
        """Возвращает текущее состояние флага использования имени экземпляра в имени файла."""
        return self._use_name_in_filename

    @use_name_in_filename.setter
    def use_name_in_filename(self, value: bool):
        """Устанавливает флаг использования имени экземпляра в имени файла."""
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



    @classmethod
    def thec_create(
        cls,
        name: str,
    ) -> bool:
        """
        Проверяем, существует ли уже экземпляр класса с именем name.
        
        :param name: Имя экземпляра класса.
        :return: True, если экземпляр с именем name существует, False в противном случае.
        """
        with cls._instances_lock:
            return (name in cls._instances )

    
    @classmethod
    def _create_instance_and_share(
        cls, 
        name, # имя экземпляра логгера (строка)
        config, # конфигурация логгера (словарь)
        enable_file_logging = True, # включить файловое логирование 
        use_name_in_filename = False,  # использовать имя экземпляра в имени файла
        show_call_depth=False, # показывать глубину вызова
        sync_full_state=False, # синхронизировать полное состояние
        auto_share=True, # автоматический шаринг
    ):
        with cls._instances_lock:
            # Создаём новый экземпляр
            instance = cls(
                name=name,
                config=config,
                enable_file_logging = enable_file_logging,
                use_name_in_filename = use_name_in_filename,
                show_call_depth=show_call_depth, 
                sync_full_state=sync_full_state,
            )
            instance._sync_full_state = sync_full_state
            cls._instances[name] = instance

            # Автоматический шаринг, если разрешено
            if auto_share and not instance._use_name_in_filename:
                # Ищем любой другой логгер с таким же base_log_file и без использования имени
                for other_name, other in cls._instances.items():
                    if other_name == name:
                        continue
                    # Используем effective_use_name_in_filename для проверки        
                    if (
                        # not other._use_name_in_filename and
                        not other.effective_use_name_in_filename(_visited=None) and  # Используем эффективное значение, чтобы правильно обработать строковые ссылки
                        other.base_log_file == instance.base_log_file and
                        other.file_handler is not None
                    ):
                        instance.share_file_handler_with(other)
                        break

            return instance

    @classmethod
    def _get_instance(
        cls, 
        name, 
        share_file_with,
        sync_full_state: bool = False,
    ):
        with cls._instances_lock:
            # экземпляр с таким именем уже существует - возвращается существующий
            inst = cls._instances[name]
            # Если запрошен шаринг с другим логгером, но ещё не настроен – настраиваем
            if share_file_with and not inst.has_shared_handler():
                other = cls._instances.get(share_file_with)

                if other and other.file_handler:
                    inst.share_file_handler_with(
                        other,
                        sync_full_state=sync_full_state,
                    )

        return inst

    @classmethod
    def get_instance(
        cls,
        name: str = 'default',
        force_new: bool = False,
        config: Optional[Dict[str, Any]] = None,
        enable_file_logging: Union[str,bool] = False,
        use_name_in_filename: Union[str,bool] = False,
        share_file_with: Optional[str] = None,
        show_call_depth: bool = False, # показывать уровень вложенности
        sync_full_state: bool = False,
        auto_share: bool = False, # Пока не используется
    ) -> 'BaseAppLogger':
        """
        Возвращает экземпляр логгера с указанным именем.

        Если force_new=False, то происходит следующее:
        - Если экземпляр с таким именем уже существует, возвращается существующий
          (параметры enable_file_logging и use_name_in_filename игнорируются).
        - Если экземпляр с таким именем не существует, создаётся новый экземпляр.

        Если force_new=True, то:
        - Создаётся новый экземпляр (старый при этом не удаляется).

        :param name: (str) Имя логгера.
        :param force_new: (bool) Принудительное создание нового экземпляра.
        :param config: (dict) Конфигурация для нового экземпляра (если None, используется провайдер).
        :param enable_file_logging: (bool) Для нового экземпляра: включать ли запись в файл.
        :param use_name_in_filename: (bool) Для нового экземпляра: добавлять ли имя в имя файла.
        :param share_file_with: (str) Для нового экземпляра: имя другого экземпляра, с которым будет общий файл
        :return: Экземпляр BaseAppLogger.
        """

        # Если enable_file_logging – строка и это не 'true'/'false', используем как имя для шаринга
        if (
            isinstance(enable_file_logging, str) 
            # and enable_file_logging.lower() not in ('true', 'false')
        ):
            low = enable_file_logging.lower()
            if low in ('true', 'false'):
                enable_file_logging = low == 'true'
                
            else:
                share_file_with = enable_file_logging
                # enable_file_logging = True # файловое логирование включаем, но обработчик будет общим  

        if isinstance(use_name_in_filename, str):
            low = use_name_in_filename.lower()
            if low in ('true', 'false'):
                use_name_in_filename = low == 'true'
            else:
                # небулева строка – оставляем как есть, конструктор разберётся
                pass
        
        with cls._instances_lock:

            if not cls._instances:
                cls.start_file_watchdog()

            if not force_new and name in cls._instances:
                # Если экземпляр с таким именем уже существует и force_new=False, возвращается существующий
                return cls._get_instance(
                    name=name,
                    share_file_with=share_file_with,
                    sync_full_state=sync_full_state,
                )
            auto_share_flag = share_file_with is None
            instance = cls._create_instance_and_share( # Создаём новый экземпляр и применяем шаринг
                name=name,
                config=config,
                enable_file_logging = enable_file_logging,
                use_name_in_filename = use_name_in_filename,
                show_call_depth=show_call_depth,
                sync_full_state=sync_full_state,

                # auto_share=False,
                auto_share=auto_share_flag
            )

            # После создания – если нужен шаринг, применяем
            # if share_file_with:
            #     other = cls._instances.get(share_file_with)
            #     # if other and other.file_handler:
            #     if other and other._file_enabled and other.file_handler:
            #         instance.share_file_handler_with(
            #             other,
            #             sync_full_state=sync_full_state,
            #         )
            #         # # Немедленно перезагружаем настройки с учётом нового мастера
            #         # instance.reload_from_config(
            #         #     instance.get_default_config()
            #         # )
            #     else:
            #         # Логгируем предупреждение, но продолжаем
            #         print(f"WARNING: Не удалось расшарить файловый обработчик с '{share_file_with}' для логгера '{name}'.", file=sys.stderr)
            #         # if instance.logger:
            #         #     instance.logger.info(
            #         #         f"Файловый обработчик не общий с '{share_file_with}': у мастера он отключён. Будет использоваться собственный."
            #         #     )

            if share_file_with:
                other = cls._instances.get(share_file_with)
                if other:
                    # Проверяем, должен ли у other быть файловый обработчик
                    # (учитываем эффективное состояние файлового логирования)
                    if other.effective_enable_file_logging(_visited=None):
                        # Файловое логирование включено, но обработчик отсутствует – это ошибка
                        if other.file_handler is None:
                            print(f"WARNING: У логгера '{share_file_with}' включено файловое логирование, "
                                  f"но обработчик отсутствует. Расшаривание для '{name}' невозможно.",
                                  file=sys.stderr)
                        else:
                            instance.share_file_handler_with(
                                other,
                                sync_full_state=sync_full_state,
                            )
                    else:
                        # У other файловое логирование отключено – ничего не делаем, предупреждение не нужно
                        pass
                else:
                    # Логгер с именем share_file_with не существует
                    print(
                        f"WARNING: Логгер '{share_file_with}', с которым требуется расшарить обработчик, не найден.",
                        file=sys.stderr
                    )


            return instance

    @staticmethod
    def _parse_log_level(level_str: str) -> int:
        """
        Преобразует строковое представление уровня логирования в константу logging.
        """

        upper_str = level_str.upper()

        if upper_str not in BaseAppLogger.level_map:
            raise ValueError(f"Неизвестный уровень логирования: {level_str}. Допустимые: DEBUG, INFO, WARNING, ERROR, CRITICAL")
        
        return BaseAppLogger.level_map[upper_str]
    
    @staticmethod
    def parse_log_level(level_str: str) -> int:
        return BaseAppLogger._parse_log_level(level_str)    
    
    # --------------------------------------------------------------------------
    # Вспомогательные методы для формирования указателя на место вызова
    # --------------------------------------------------------------------------

    def _convert_patterns_modeles_tips(
        self,
        modeles,
        simple_types = (int, float, str, bool, type(None)),
    ):  
        """
        Преобразует указатель на место вызова в множество значений.

        Если указатель на место вызова является одним из простых типов (int, float, str, bool, None), то возвращает множество с одним элементом - этим указателем.
        Если указатель на место вызова не является множеством, то возвращает множество с указателем на место вызова как единственным элементом.
        """
        
        if  isinstance(modeles, simple_types):
            return {modeles}
        
        elif  not isinstance(modeles, set):
            return set(modeles) 
       
    def _thec_patterns_modeles_is_none(
        self,
        modeles,
        if_err_tip: bool,
    )-> bool: 
        """
        Проверяет, является ли указатель на место вызова None или пустым.
        
        :param modeles: (Any) Указатель на место вызова.
        :param if_err_tip: (bool) Если True, то если указатель на место вызова None или пустой, то будет выброшено исключение ValueError.
        :return: (bool) True, если указатель на место вызова None или пустой, False в противном случае.
        """
        # Проверка на наличие              
        if (modeles is None)  : 
            if if_err_tip :  
                raise ValueError('err: filename is None')  
            return True  
        
        if (len(modeles) == 0) :
            if if_err_tip :  
                raise ValueError('err: filename is None')  
            return True 
        
        return False 

    def _thec_patterns_modeles(
        self,
        modeles,
        if_err_tip,
    ): 
        """
        Проверяет, является ли указатель на место вызова None или пустым.
        
        Если указатель на место вызова None или пустой, то возвращает None.
        Если указатель на место вызова не является множеством, то возвращает множество с указателем на место вызова как единственным элементом.
        """
        
                      
        # Проверка на наличие   
        if self._thec_patterns_modeles_is_none(
            modeles     = modeles,
            if_err_tip  = if_err_tip,
        ):
            return None             
                
        modeles = self._convert_patterns_modeles_tips(
            modeles = modeles
        )
        
        return modeles 
        
    # def _thec_skip_patterns_modeles(
    #     self,
    #     patterns_modeles
    # ):  
    #     """
    #     Проверяет, если при указанных параметрах modeles стоит пропустить
    #     логирование.

    #     :param patterns_modeles: Словарь с параметрами для фильтрации.
    #     :return: True - указатель есть в блок листе, False - нет в блок листе.
    #     """



    #     # Проверяем, если указатель на место вызова есть в общем блоке лист
    #     for skip_patterns_modele in self.skip_patterns_modeles: 
    #         # общий блок лист
    #         for i in [
    #             'filename', 
    #             'function',
    #         ]:
    #             # Флаг, указывающий на то, что мы проверяем filename или function
    #             if_filename  = (i == 'filename')
                
    #             # Проверяем, есть ли указатель на место вызова в skip
    #             thec_skip = self._thec_patterns_modeles( 
    #                 modeles     = skip_patterns_modele.get(i,{}) ,
    #                 if_err_tip  = if_filename,
    #             )
    #             if thec_skip is None:
    #                 # если нет в skip указателя на function, блок лист (так как filename пройден)
    #                 # то возвращаем True
    #                 return True  
                
    #             # Проверяем, есть ли указатель на место вызова в patterns_modeles
    #             thec_modeles = self._thec_patterns_modeles(
    #                 modeles     = patterns_modeles.get(i,{}) ,
    #                 if_err_tip  = if_filename,
    #             )
    #             if thec_modeles is None:
    #                 # если нет в skip указателя на function, блок лист (так как filename пройден)
    #                 # то возвращаем True
    #                 return True  
                    
    #             # Проверяем, если указатель на место вызова есть в блок листе
    #             for modele in thec_modeles: 
    #                 # что проверяем на наличие в блок листе  
                
    #                 if self._thec_patterns_modeles_is_none(
    #                     modeles     = modele ,
    #                     if_err_tip  = if_filename  , 
    #                 ):
    #                     # если нет в skip указателя на function, блок лист (так как filename пройден)
    #                     # то возвращаем True
    #                     return True

    #                 if ( # проверка на наличие в блок листе
    #                     modele in thec_skip
    #                 ) or (
    #                     modele == thec_skip
    #                 ) :
    #                     # если указатель на место вызова есть в общем блоке лист, то возвращаем True
    #                     return True  
    #                 else:
    #                     # иначе мы проверяем, если указатель на место вызова есть в skip
    #                     skip_thec = True
    #                     for skip in thec_skip:
    #                         if self._thec_patterns_modeles_is_none(
    #                             modeles     = skip ,   
    #                             if_err_tip  = if_filename  , 
    #                         ):
    #                             # если нет в skip указателя на function, блок лист (так как filename пройден)
    #                             # то возвращаем True
    #                             return True 

    #                         # проверка на наличие каждого элимента по пути
    #                         skip_thec_ = (
    #                             (skip in modele) or (skip == modele)
    #                         )
                            
    #                         if if_filename or ( skip_thec) : 
    #                             # если filename, то нудно проверить нахождение каждого элимента по пути. Если все есть, то переход на проверку function
    #                             skip_thec = skip_thec and skip_thec_
    #                         else: 
    #                             # возможно вернуть  skip_thec_, а не continue
    #                             continue

    #                     if not skip_thec:
    #                         # если указатель на место вызова не находится в skip, то возвращаем False
    #                         return False   
    #         if not skip_thec:
    #             # если указатель на место вызова не находится в skip, то возвращаем False
    #             return False 

    #     # если указатель на место вызова не находится в общем блоке лист, то возвращаем True
    #     return True
    def _thec_skip_patterns_modeles(self, patterns_modeles: dict) -> bool:
        """
        Проверяет, нужно ли пропустить фрейм (т.е. является ли он внутренним для логгера).
        
        :param patterns_modeles: словарь с ключами 'filename' и 'function',
                                каждый значение — кортеж из одного элемента (строка).
        :return: True — фрейм нужно пропустить, False — не пропускать.
        """

        # Извлекаем filename и function из переданного словаря
        frame_filename_tuple = patterns_modeles.get('filename')
        frame_function_tuple = patterns_modeles.get('function')
        
        # Если нет ни того, ни другого — не пропускаем
        if not frame_filename_tuple and not frame_function_tuple:
            return False
        
        # Берём первый (и единственный) элемент
        filename = frame_filename_tuple[0] if frame_filename_tuple else None
        function = frame_function_tuple[0] if frame_function_tuple else None
        
        # Перебираем все правила пропуска
        for rule in self.skip_patterns_modeles:
            # Части пути, которые должны ВСЕ присутствовать в filename
            required_parts = rule.get('filename', ())
            # Имена функций, которые должны совпадать
            required_functions = rule.get('function', ())
            
            # Проверка по filename: все required_parts должны быть подстроками в filename
            # if required_parts:
            #     if not filename:
            #         continue   # нет filename, а правило требует — пропускаем правило

            #     if not all(part in filename for part in required_parts):
            #         continue   # не все части найдены — правило не подходит


            # Проверка filename: путь должен заканчиваться на os.path.join(*required_parts)
            if required_parts:
                if not filename:
                    continue

                # Нормализуем путь и целевой суффикс
                norm_filename = os.path.normpath(filename)
                target_suffix = os.path.normpath(os.path.join(*required_parts))

                if not norm_filename.endswith(target_suffix):
                    continue
            
            # Проверка по function: если правило требует конкретные имена функций
            if required_functions:
                if not function or function not in required_functions:
                    continue
            
            # Если дошли сюда — правило сработало, фрейм нужно пропустить
            return True
        
        # Ни одно правило не подошло
        return False    



    def _get_caller_info(self, levels_up: int = 2) -> str:
        """
        Возвращает строку с информацией о caller'е.

        - Если levels_up > 0: поднимается на указанное количество уровней (стандартное поведение).
        - Если levels_up == 0: автоматически ищет первый фрейм вне модулей логирования.

        Важно: мы используем inspect.stack() для получения стека вызываемых функций.
        Каждый элемент стека - это объект FrameInfo, содержащий информацию о текущей функции:
          - filename: путь к файлу, в котором находится функция
          - lineno: номер строки в файле, в которой находится функция
          - function: имя функции

        Мы ищем фрейм, чей файл не содержит 'logger' или 'base_logger', чтобы не учитывать
        вызовы изнутри модулей логирования. Если таких фреймов не найдено, берем последний
        фрейм (в конце стека).
        """

        # import inspect
        stack = inspect.stack()
        frame_info = stack[-1]

        if levels_up > 0:
            # Явно заданная глубина
            if len(stack) <= levels_up:
                frame_info = stack[-1]
            else:
                frame_info = stack[levels_up]
        else:
            # Автоматический поиск: пропускаем фреймы, относящиеся к логгеру
            # Пропускаем текущий фрейм (индекс 0) и ищем первый, чей файл не содержит 'logger'
            
            for frame_info in stack[1:]:

                if self._thec_skip_patterns_modeles( # если входит в список пропуска, то след итерация
                    patterns_modeles={
                        'filename':(frame_info.filename,),
                        'function':(frame_info.function,),  
                    }
                ):
                    continue
                # если не в списке, то выводим            
                filename = frame_info.filename
                break
                
            else:
                # Если не нашли (вдруг весь стек состоит из логгера), берём последний
                frame_info = stack[-1]

        filename = frame_info.filename
        lineno = frame_info.lineno
        funcname = frame_info.function

        return f'File "{filename}", line {lineno}, in <{funcname}>'
    
    def _format_message(
        self, 
        caller_info: str,
        message: str,
        depth: Optional[int] = None
    ) -> str:
        """
        Форматирует итоговое сообщение, добавляя имя логгера и указатель.

        caller_info - строка, полученная из _get_caller_info, содержащая информацию о вызове функции:
            - имя файла, в котором находится вызов функции
            - номер строки в файле, в которой находится вызов функции
            - имя функции

        message - текст сообщения, который будет добавлен к caller_info

        Возвращаемый результат - строка, содержащая caller_info и message, разделенные символом ">"
        """
        if depth is None:
            # Нет переданной глубины – определяем автоматически
            if self._show_call_depth:
                effective_depth = self._get_call_depth()
            else:
                effective_depth = self._get_current_depth()   # ручная глубина от декоратора (0 по умолчанию)
        else:
            # Переданная глубина (обычно из декоратора) имеет приоритет
            effective_depth = depth

        indent = ">" * effective_depth  #  уровень вложенности
        
        return f"[{self.name}]\t{indent} {caller_info}:\t{message}"

    # --------------------------------------------------------------------------
    # Прямые методы логирования
    # --------------------------------------------------------------------------
    
    def _formatted(
        self,
        message: str,  # текст сообщения, которое будет добавлено к caller_info
        levels_up: int = None,  # глубина поиска в стеке вызов (0 - автоматически, > 0 - явно)
    ):
        """
        Форматирует итоговое сообщение, добавляя имя логгера и указатель.

        - levels_up: глубина поиска в стеке вызов (0 - автоматически, > 0 - явно)
        - message: текст сообщения, которое будет добавлено к caller_info

        Возвращаемый результат - строка, содержащая caller_info и message, разделенные символом табуляции '\t'
        """

        if not self._enabled:
            return ""
        
        if levels_up is None:
            levels_up = self._levels_up

        caller = self._get_caller_info(
            levels_up=levels_up
        )

        depth = self._get_call_depth() if self._show_call_depth else None

        return self._format_message(
            caller, 
            message,
            depth,
        )
        
    
    def debug(self, message: str) -> None:
        """
        Метод для логирования отладки в уровне DEBUG.

        Он вызывает self.logger.debug сформатированным сообщением, которое содержит информацию о вызове функции:
            - имя файла, в котором находится вызов функции
            - номер строки в файле, в которой находится вызов функции
            - имя функции

        message - текст сообщения, которое будет добавлено к caller_info
        """

        if not self._enabled or self.__class__.is_disabled(self.name):
            return
        
        self.logger.debug(
            self._formatted(
                message = message,   
            )
        )

    def info(self, message: str) -> None:
        """
        Метод для логирования информации в уровне INFO.

        Он вызывает self.logger.info сформатированным сообщением, которое содержит информацию о вызове функции:
            - имя файла, в котором находится вызов функции
            - номер строки в файле, в которой находится вызов функции
            - имя функции

        message - текст сообщения, которое будет добавлено к caller_info
        """

        if not self._enabled or self.__class__.is_disabled(self.name):
            return
        
        self.logger.info(
            self._formatted(
                message = message,   
            )
        )

    def warning(self, message: str) -> None:
        """
        Метод для логирования предупреждения в уровне WARNING.

        Он вызывает self.logger.warning сформатированным сообщением, которое содержит информацию о вызове функции:
            - имя файла, в котором находится вызов функции
            - номер строки в файле, в которой находится вызов функции
            - имя функции

        message - текст сообщения, которое будет добавлено к caller_info
        """

        if not self._enabled:
            return
        
        self.logger.warning(
            self._formatted(
                message = message,   
            )
        )

    def error(self, message: str) -> None:
        """
        Метод для логирования ошибки в уровне ERROR.

        Он вызывает self.logger.error сформатированным сообщением, которое содержит информацию о вызове функции:
            - имя файла, в котором находится вызов функции
            - номер строки в файле, в которой находится вызов функции
            - имя функции

        message - текст сообщения, которое будет добавлено к caller_info
        """

        if not self._enabled:
            return
        
        self.logger.error(
            self._formatted(
                message = message,   
            )
        )

    def critical(self, message: str) -> None:
        """
        Метод для логирования критических ошибок в уровне CRITICAL.

        Он вызывает self.logger.critical сформатированным сообщением, которое содержит информацию о вызове функции:
            - имя файла, в котором находится вызов функции
            - номер строки в файле, в которой находится вызов функции
            - имя функции

        message - текст сообщения, которое будет добавлено к caller_info
        """

        if not self._enabled or self.__class__.is_disabled(self.name):
            return
        
        self.logger.critical(
            self._formatted(
                message = message,   
            )
        )

    def exception(self, message: str, exc_info: bool = True) -> str:
        """
        Метод для логирования информации об ошибке в уровне ERROR.

        Он вызывает self.logger.error сформатированным сообщением, которое содержит информацию о вызове функции:
            - имя файла, в котором находится вызов функции
            - номер строки в файле, в которой находится вызов функции
            - имя функции
            - информацию об ошибке (если exc_info == True)

        message - текст сообщения, которое будет добавлено к caller_info
        exc_info - флаг, указывающий, нужно ли добавлять информацию об ошибке
        """

        if not self._enabled or self.__class__.is_disabled(self.name):
            return message
    
        self.logger.error(
            self._formatted(
                message = message,   
            ), exc_info=exc_info
        )
        return message
        

    # --------------------------------------------------------------------------
    # Декоратор для замера времени выполнения
    # --------------------------------------------------------------------------

    def log_execution_time(
        self, 
        description: str = "", 
        level: int = logging.DEBUG,
        log_args: Optional[bool] = None,
        # log_args: Optional[bool] = True,
        log_return: bool = False,
        show_depth: bool = False,
        # show_depth: bool = True,
    ) -> Callable:
        """
        Декоратор для логирования времени выполнения функции или метода.

        :param description: дополнительное описание (будет добавлено перед сообщением)
        :param level: уровень логирования
        :param log_args: если True, в начало логирования добавляются переданные аргументы.
                         Если None, используется значение из конфигурации логгера (self.log_args).
        """

        logger_instance = self

        if log_args is None:
            log_args = self.log_args

        def decorator(func: Callable) -> Callable:
            """
            Декоратор для логирования времени выполнения функции или метода.

            Он обернул функцию, добавляя информацию о вызове функции:
                - имя файла, в котором находится вызов функции
                - номер строки в файле, в которой находится вызов функции
                - имя функции
                - информацию об ошибке (если exc_info == True)

            description - текст, добавляемый к caller_info
            level - уровень логирования
            log_args - флаг, указывающий, нужно ли добавлять информацию об аргументах
            """

            # func_filename = inspect.getfile(func)
            # func_lineno = func.__code__.co_firstlineno
            # func_name = func.__name__
            # is_async = inspect.iscoroutinefunction(func)
            
            # Если указанный уровень логирования не активен, возвращаем исходную функцию без обёртки
            # if not logger_instance.logger.isEnabledFor(level):
            #     return func
            
            # сохраняем значение log_return для использования внутри обёртки
            _log_return = log_return

            # Используем квалифицированное имя (с классом, если это метод)
            func_qualname = func.__qualname__
            try:
                # Получаем имя файла, в котором находится вызов функции
                func_filename = inspect.getfile(func)
            except TypeError:
                # Если функция - встроенная, то имя файла не может быть получено
                func_filename = "<built-in>"

            # Получаем номер строки в файле, в которой находится вызов функции

            if isinstance(func, staticmethod):
                func = func.__func__
            elif isinstance(func, classmethod):
                func = func.__func__

            func_lineno = func.__code__.co_firstlineno

            # Определяем, является ли функция асинхронной
            is_async = inspect.iscoroutinefunction(func)

            # Общая логика для формирования сообщений и замера времени
            def make_wrapper():
                # Формируем базовую информацию о caller'е (один раз для всех вызовов)
                caller_info = f'File "{func_filename}", line {func_lineno}, in <{func_qualname}>'
                desc_part = f"{description} " if description else ""

                # Определяем, нужно ли показывать глубину
                _show_depth = show_depth#  or type(logger_instance).status_show_call_depth_global()

                # Определяем, нужно ли логировать аргументы
                effective_log_args = log_args
                if func.__name__ == '__init__':
                    effective_log_args = False

                def format_args(args, kwargs):
                    """Форматирует аргументы для логирования."""

                    if not effective_log_args:
                        return ""
                    
                    display_args = args

                    if args and inspect.ismethod(func) and func.__self__ is not None:
                        display_args = args[1:]  # убираем self

                    args_str = ', '.join(repr(a) for a in display_args)
                    kwargs_str = ', '.join(f"{k}={repr(v)}" for k, v in kwargs.items())
                    all_args = ', '.join(filter(None, [args_str, kwargs_str]))

                    return f" with args: ({all_args})"

                def log_start(args, kwargs):
                    args_part = format_args(args, kwargs)
                    start_msg = f"{desc_part}[Начало]{args_part}"

                    # Определяем, нужно ли показывать глубину
                    if _show_depth:# or type(logger_instance).status_show_call_depth_global():
                        depth = logger_instance._get_current_depth()
                        formatted = logger_instance._format_message(caller_info, start_msg, depth)
                    else:
                        formatted = logger_instance._format_message(caller_info, start_msg)

                    logger_instance.logger.log(level, formatted)

                def log_end(
                    execution_time: float, 
                    error: Optional[Exception] = None,
                    return_value=None,
                ):

                    if desc_part:
                        end_msg = f"{desc_part}[Завершение: {execution_time:.4f} сек]" 
                    else:
                        end_msg = f"[Завершение: {execution_time:.4f} сек]"
                    
                    if error:
                        end_msg += f": {error}"

                    if _log_return and return_value is not None and not error:
                        ret_str = repr(return_value)
                        # if len(ret_str) > 200:
                        #     ret_str = ret_str[:197] + "..."
                        end_msg += f" -> {ret_str}"

                    if _show_depth:#  or type(logger_instance).status_show_call_depth_global():
                        depth = logger_instance._get_current_depth()
                        formatted = logger_instance._format_message(caller_info, end_msg, depth)
                    else:
                        formatted = logger_instance._format_message(caller_info, end_msg)

                    logger_instance.logger.log(level, formatted)

                    # if 'PhotoUploaderWidget.set_existing_photos' in formatted:
                    #     0==0
                    # 0==0
                def _thec(tp, level):
                    return (
                        (
                            not logger_instance.logger.isEnabledFor(level)
                         ) or (
                            not logger_instance._enabled
                        )
                    ) or (
                        tp.is_disabled(logger_instance.name)
                    )

                # Создаём синхронную обёртку
                @wraps(func)
                def sync_wrapper(*args, **kwargs):


                    # thec = (
                    #     (
                    #         not logger_instance.logger.isEnabledFor(level)
                    #      ) or (
                    #         not logger_instance._enabled
                    #     )
                    # ) or (
                    #     type(logger_instance).is_disabled(logger_instance.name)
                    # )

                    thec = _thec(type(logger_instance), level)

                    if not thec: 
                        if _show_depth:#  or type(logger_instance).status_show_call_depth_global():
                            logger_instance._increase_depth()
                    try:
                        
                        result = None
                        err = None
                        
                        if not thec: 
                            log_start(args, kwargs)
                            start_time = time.time()

                        try:
                            result = func(*args, **kwargs)
                        except Exception as e:
                            err = e
                            # 0==0
                        finally:

                            if not thec: 
                                # execution_time = time.time() - start_time

                                log_end(
                                    time.time() - start_time, 
                                    err, 
                                    result
                                )

                        if err:
                            raise err
                        
                        return result
                    
                    finally:
                        if not thec: 
                            if _show_depth:#  or type(logger_instance).status_show_call_depth_global():
                                logger_instance._decrease_depth()


                    # if thec:
                    #     # return func(*args, **kwargs)
                    #     # Вызываем функцию
                    #     try:
                    #         result = func(*args, **kwargs)
                    #     except Exception as e:
                    #         err = e
                    #         raise err
                    #         # 0==0
                        
                    #         # func_qualname
                    #     return result


                    # if _show_depth:#  or type(logger_instance).status_show_call_depth_global():
                    #     logger_instance._increase_depth()
                    # try:

                    #     log_start(args, kwargs)
                    #     start_time = time.time()
                    #     result = None
                    #     error = None
                        
                    #     try:
                    #         result = func(*args, **kwargs)
                    #     except Exception as e:
                    #         error = e
                    #         # raise
                    #     finally:
                    #         execution_time = time.time() - start_time

                    #         log_end(execution_time, error, result)

                    #     if error:
                    #         raise error

                    #     # if execution_time > 17:
                    #     # if execution_time > 17.2:
                    #     # if execution_time > 15.2:
                    #     #     0 == 0

                    #     return result
                    
                    # finally:
                    #     if _show_depth:#  or type(logger_instance).status_show_call_depth_global():
                    #         logger_instance._decrease_depth()

                # Создаём асинхронную обёртку
                @wraps(func)
                async def async_wrapper(*args, **kwargs):
                    
                    if (
                        (not logger_instance.logger.isEnabledFor(level))
                        or (not logger_instance._enabled)
                    ) or (
                        type(logger_instance).is_disabled(logger_instance.name)
                    ):
                        # return func(*args, **kwargs)
                        # Вызываем функцию
                        try:
                            result = await func(*args, **kwargs)
                        except Exception as e:
                            err = e
                            raise err
                            # 0==0
                            # func_qualname
                        return result

                    # if not logger_instance._enabled:
                    #     return await func(*args, **kwargs)
                    
                    if _show_depth:#  or type(logger_instance).status_show_call_depth_global():
                        logger_instance._increase_depth()

                    try:
                        log_start(args, kwargs)
                        start_time = time.time()
                        result = None
                        error = None

                        try:
                            result = await func(*args, **kwargs)
                        except Exception as e:
                            error = e
                            # raise
                        finally:
                            execution_time = time.time() - start_time

                            log_end(execution_time, error, result)

                        if error:
                            raise error
                        
                        return result
                    
                    finally:
                        if _show_depth:#  or type(logger_instance).status_show_call_depth_global():
                            logger_instance._decrease_depth()
                
                return async_wrapper if is_async else sync_wrapper
            
            return make_wrapper()
        
            # @wraps(func)
            # def sync_wrapper(*args, **kwargs):
            #     """
            #     Обернулка для синхронных функций.

            #     Она вызывает функцию, добавляя информацию о вызове функции:
            #         - имя файла, в котором находится вызов функции
            #         - номер строки в файле, в которой находится вызов функции
            #         - имя функции
            #         - информацию об аргументах (если log_args == True)

            #     description - текст, добавляемый к caller_info
            #     level - уровень логирования
            #     log_args - флаг, указывающий, нужно ли добавлять информацию об аргументах
            #     """

                

            #     # Вызываем функцию
            #     # try:
            #     #     result = func(*args, **kwargs)
            #     # except Exception as e:
            #     #     err = e
            #     #     raise e
            #     #     # func_qualname
            #     # return result
        
        
            #     caller_info = f'File "{func_filename}", line {func_lineno}, in <{func_qualname}>'

            #     # Формируем строку с описанием
            #     desc_part = f"{description} " if description else ""

            #     # Определяем, нужно ли логировать аргументы
            #     effective_log_args = log_args

            #     # Для __init__ всегда отключаем логирование аргументов
            #     if func.__name__ == '__init__':
            #         effective_log_args = False
                    
            #     # Формируем строку с аргументами
            #     # args_part = ""
            #     # if log_args:
            #     #     args_str = ', '.join(repr(a) for a in args) if effective_log_args else ''
            #     #     kwargs_str = ', '.join(f"{k}={repr(v)}" for k, v in kwargs.items())
            #     #     all_args = ', '.join(filter(None, [args_str, kwargs_str]))
            #     #     args_part = f" with args: ({all_args})"
            #     args_part = ""
            #     if effective_log_args:
            #         # Для методов исключаем self из отображения
            #         display_args = args
            #         # Проверяем, является ли функция методом (первый аргумент обычно self)
            #         if args and inspect.ismethod(func) and func.__self__ is not None:
            #             display_args = args[1:]  # убираем self
            #         args_str = ', '.join(repr(a) for a in display_args)
            #         kwargs_str = ', '.join(f"{k}={repr(v)}" for k, v in kwargs.items())
            #         all_args = ', '.join(filter(None, [args_str, kwargs_str]))
            #         args_part = f" with args: ({all_args})"

            #     # Формируем строку с информацией о вызове функции
            #     start_msg = f"{desc_part}[Начало]{args_part}"

            #     # Формируем полное сообщение
            #     formatted_start = logger_instance._format_message(caller_info, start_msg)

            #     # Логируем сообщение
            #     logger_instance.logger.log(level, formatted_start)

            #     # Получаем время начала выполнения
            #     start_time = time.time()
                
            #     err = None
            #     # Вызываем функцию
            #     try:
            #         result = func(*args, **kwargs)
            #     except Exception as e:
            #         err = e
            #         # raise

            #     # Получаем время окончания выполнения
            #     execution_time = time.time() - start_time

            #     # Формируем строку с информацией о времени выполнения
            #     end_msg = f"{desc_part} [Завершение: {execution_time:.4f} сек]" if desc_part else f"[Завершение: {execution_time:.4f} сек]"

            #     # Если есть ошибка, добавляем ее в конце сообщения
            #     if err:
            #         end_msg += f": {err}"

            #     # Формируем полное сообщение
            #     formatted_end = logger_instance._format_message(caller_info, end_msg)

            #     # Логируем сообщение
            #     logger_instance.logger.log(level, formatted_end)

            #     # Возвращаем ошибку если она есть
            #     if err:
            #         raise err
                
            #     return result

            # @wraps(func)
            # async def async_wrapper(*args, **kwargs):
            #     """
            #     Обернулка для асинхронных функций.

            #     Она вызывает функцию, добавляя информацию о вызове функции:
            #         - имя файла, в котором находится вызов функции
            #         - номер строки в файле, в которой находится вызов функции
            #         - имя функции
            #         - информацию об аргументах (если log_args == True)

            #     description - текст, добавляемый к caller_info
            #     level - уровень логирования
            #     log_args - флаг, указывающий, нужно ли добавлять информацию об аргументах
            #     """
            #     caller_info = f'File "{func_filename}", line {func_lineno}, in <{func_qualname}>'

            #     # Формируем строку с описанием
            #     desc_part = f"{description} " if description else ""


            #     effective_log_args = log_args
            #     if func.__name__ == '__init__':
            #         effective_log_args = False

            #     # Формируем строку с аргументами
            #     # args_part = ""
            #     # if log_args:
            #     #     args_str = ', '.join(repr(a) for a in args)
            #     #     kwargs_str = ', '.join(f"{k}={repr(v)}" for k, v in kwargs.items())
            #     #     all_args = ', '.join(filter(None, [args_str, kwargs_str]))
            #     #     args_part = f" with args: ({all_args})"

            #     args_part = ""
            #     if effective_log_args:
            #         display_args = args
            #         if args and inspect.ismethod(func) and func.__self__ is not None:
            #             display_args = args[1:]
            #         args_str = ', '.join(repr(a) for a in display_args)
            #         kwargs_str = ', '.join(f"{k}={repr(v)}" for k, v in kwargs.items())
            #         all_args = ', '.join(filter(None, [args_str, kwargs_str]))
            #         args_part = f" with args: ({all_args})"
            #     # Формируем строку с информацией о вызове функции
            #     start_msg = f"{desc_part}[Начало]{args_part}"

            #     # Формируем полное сообщение
            #     formatted_start = logger_instance._format_message(caller_info, start_msg)

            #     # Логируем сообщение
            #     logger_instance.logger.log(level, formatted_start)

            #     # Получаем время начала выполнения
            #     start_time = time.time()

            #     err = None
            #     # Вызываем функцию
            #     try:
            #         result = await func(*args, **kwargs)
            #     except Exception as e:
            #         err = e
                
            #     # Получаем время окончания выполнения
            #     execution_time = time.time() - start_time

            #     # Формируем строку с информацией о времени выполнения
            #     end_msg = f"{desc_part} [Завершение: {execution_time:.4f} сек]" if desc_part else f"[Завершение: {execution_time:.4f} сек]"
                
            #     # Если есть ошибка, добавляем ее в конце сообщения
            #     if err:
            #         end_msg += f": {err}"

            #     # Формируем полное сообщение
            #     formatted_end = logger_instance._format_message(caller_info, end_msg)

            #     # Логируем сообщение
            #     logger_instance.logger.log(level, formatted_end)

            #     # Возвращаем ошибку если она есть
            #     if err:
            #         raise err

            #     return result

            # return async_wrapper if is_async else sync_wrapper

        return decorator

    # --------------------------------------------------------------------------
    # Закрытие логгера
    # --------------------------------------------------------------------------
    def close(self) -> None:
        """
        Закрывает логгер, удаляя все хендлеры из него и очищает список хендлеров.
        
        1. Берем все хендлеры из логгера (self.logger.handlers[:])
        2. Закрываем каждый хендлер (handler.close())
        3. Удаляем каждый хендлер из логгера (self.logger.removeHandler(handler))
        4. Очищаем список хендлеров (self.handlers.clear())
        """
        for handler in self.logger.handlers[:]:
            handler.close()
            self.logger.removeHandler(handler)
        self.handlers.clear()

    @classmethod
    def close_all(cls) -> None:
        """
        Закрывает все экземпляры логгера, удаляя все хендлеры из каждого из них,
        и очищает словарь экземпляров.
        """

        with cls._instances_lock:
            for instance in cls._instances.values():
                instance.close()
            cls._instances.clear()


# ------------------------------------------------------------------------------
# Экспортируем только класс
# ------------------------------------------------------------------------------
__all__ = ['BaseAppLogger']