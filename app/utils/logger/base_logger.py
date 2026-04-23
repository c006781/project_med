#!/usr/bin/env python3
# -*- coding: utf-8 -*-

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
    logger_db = BaseAppLogger.get_instance(name='db', use_name_in_filename=True)
    logger_db.info("Сообщение для db")

    # Логгер только в консоль (без файла)
    logger_console = BaseAppLogger.get_instance(name='console', enable_file_logging=False)
    logger_console.info("Только в консоль")

Особенности настройки LOG_FILE (base_log_file):
    - Может быть путём к ДИРЕКТОРИИ (например, "logs" или "./logs/").
      В этом случае внутри директории автоматически создаётся файл с именем,
      зависящим от параметров use_name_in_filename и use_timestamp.
    - Может быть полным путём к ФАЙЛУ с расширением .log (например, "logs/app.log").
      В этом случае используется именно этот файл (родительские директории создаются).
    - Если путь не существует и не оканчивается на .log, он интерпретируется как директория.
"""

import os
import logging
import sys
import time
from typing import (
    List, Optional, Dict, 
    Any, Callable, Union
)

import warnings
import inspect

import threading

from functools import wraps
from logging.handlers import RotatingFileHandler

class RobustRotatingFileHandler(RotatingFileHandler):
    """
    Обработчик файла с поддержкой восстановления при удалении файла.
    Потокобезопасен, проверяет существование файла не чаще 1 раза в секунду
    """
    def __init__(self, filename, mode='a', maxBytes=0, backupCount=0, encoding=None, delay=False):
        super().__init__(filename, mode, maxBytes, backupCount, encoding, delay)

        self._lock = threading.RLock()
        self._last_check = 0
        self._check_interval = 1.0  # проверять не чаще раза в секунд

    def emit(self, record):
        """
        Переопределённый метод emit: перед записью проверяет существование файла.
        Если файл удалён, переоткрывает его.
        """
        try:
            now = time.time()
            # Проверяем существование файла, если прошло достаточно времени
            if now - self._last_check > self._check_interval:
                with self._lock:
                    if not os.path.exists(self.baseFilename):
                        # Файл удалён – переоткрываем
                        self._reopen()

                    self._last_check = now 
                    
            super().emit(record)
        except (FileNotFoundError, PermissionError) as e:
            # Если файл внезапно исчез между проверкой и записью
            self.handleError(record)
            
            with self._lock:
                self._reopen()

            try:
                super().emit(record)  # повторяем запись
            except Exception:
                self.handleError(record)

        except Exception:
            self.handleError(record)

    def _reopen(self):
        """Принудительно закрывает и открывает файл."""
        # Файл удалён – закрываем текущий поток и открываем заново
        if self.stream:
            self.stream.close()
            self.stream = None
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
                     enable_file_logging=True, use_name_in_filename=False) -> BaseAppLogger:
            Возвращает экземпляр логгера с указанным именем.
    """

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

    # Словарь экземпляров (ключ - имя логгера)
    _instances: Dict[str, 'BaseAppLogger'] = {}

    _global_handlers = []  # список обработчиков, добавляемых ко всем логгерам

    # Простой формат лога: время, уровень, сообщение (всё остальное формируем вручную)
    LOG_FORMAT = '%(asctime)s\t%(levelname)s\t%(message)s'

    level_map = {
        'DEBUG': logging.DEBUG,
        'INFO': logging.INFO,
        'WARNING': logging.WARNING,
        'ERROR': logging.ERROR,
        'CRITICAL': logging.CRITICAL
    }


    @classmethod
    def disable_exact(cls, name: str):
        """Отключает логгер с точным именем (не префикс)."""
        inst = cls._instances.get(name)
        if inst:
            inst.disable()

    @classmethod
    def enable_exact(cls, name: str):
        """Включает логгер с точным именем."""
        inst = cls._instances.get(name)
        if inst:
            inst.enable()

    @classmethod
    def disable_console_exact(cls, name: str):
        """Отключает консольный вывод для точного логгера."""
        inst = cls._instances.get(name)
        if inst:
            inst.disable_console()

    @classmethod
    def enable_console_exact(cls, name: str):
        """Включает консольный вывод для точного логгера."""
        inst = cls._instances.get(name)
        if inst:
            inst.enable_console()

    @classmethod
    def disable_file_exact(cls, name: str):
        """Отключает файловое логирование для точного логгера."""
        inst = cls._instances.get(name)
        if inst:
            inst.disable_file()

    @classmethod
    def enable_file_exact(cls, name: str):
        """Включает файловое логирование для точного логгера."""
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
        def watch():
            while True:
                time.sleep(interval_sec)
                cls.reopen_all_files()

        thread = threading.Thread(target=watch, daemon=True, name="LoggerWatchdog")
        thread.start()

    @classmethod
    def reopen_all_files(cls):
        """Переоткрывает файловые обработчики всех логгеров (например, после изменения пути)."""
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
        cls._global_handlers.append(handler)
        # Добавляем ко всем уже созданным экземплярам
        for instance in cls._instances.values():
            instance.logger.addHandler(handler)
            # Обновляем список обработчиков экземпляра (опционально)
            instance.handlers = instance.logger.handlers[:]

    @classmethod
    def remove_global_handler(cls, handler):
        """
        Удаляет обработчик из глобального списка и из каждого существующего экземпляра логгера.

        :param handler: Обработчик, который нужно удалить.
        """

        # Если обработчик есть в глобальном списке, удаляем его
        if handler in cls._global_handlers:
            cls._global_handlers.remove(handler)

        # Удаляем обработчик из каждого существующего экземпляра
        for instance in cls._instances.values():
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
        for inst in cls._instances.values():
            if inst.name.startswith(name_prefix):
                inst.disable()

    @classmethod
    def enable_group(cls, name_prefix: str):
        """Включает все логгеры группы."""
        for inst in cls._instances.values():
            if inst.name.startswith(name_prefix):
                inst.enable()

    @classmethod
    def set_group_level(cls, name_prefix: str, level: str):
        """Устанавливает уровень логирования для всех логгеров группы."""
        for inst in cls._instances.values():
            if inst.name.startswith(name_prefix):
                inst.setLevel(cls._parse_log_level(level))

    @classmethod
    def get_group_loggers(cls, name_prefix: str) -> list:
        """
        Возвращает список имён логгеров, чьи имена начинаются с name_prefix.
        """
        return [inst.name for inst in cls._instances.values() if inst.name.startswith(name_prefix)]

    @classmethod
    def reconfigure_group(cls, name_prefix: str, **kwargs):
        """
        Переконфигурирует все логгеры группы (например, изменить уровень).
        """
        for inst in cls._instances.values():
            if inst.name.startswith(name_prefix):
                inst.reconfigure(**kwargs)

    def __init__(
        self,
        name: str,
        config: Optional[Union[str,Dict[str, Any]]] = None,
        enable_file_logging: Union[str,bool] = False,
        use_name_in_filename: Union[str,bool] = False
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

        self._shared_handler = False    # флаг, что используется общий обработчик
        self._master_logger = None      # ссылка на логгер, предоставивший общий обработчик
        self._shared_slaves = []        # логгеры, которые используют мой обработчик

        # self._console_enabled = True   # флаг для консольного вывода
        # self._enabled = True            # полное отключение логирования

        # self._file_enabled = bool(enable_file_logging)# флаг для файлового вывода
        # self._use_name_in_filename = bool(use_name_in_filename)

        # Сохраняем ссылки, если переданы строки
        if isinstance(enable_file_logging, str):
            self._enable_file_logging_ref = enable_file_logging
            self._enable_file_logging = False  # placeholder
        else:
            self._enable_file_logging_ref = None
            self._enable_file_logging = enable_file_logging

        if isinstance(use_name_in_filename, str):
            self._use_name_in_filename_ref = use_name_in_filename
            self._use_name_in_filename = False
        else:
            self._use_name_in_filename_ref = None
            self._use_name_in_filename = use_name_in_filename

        
        config = self._load_config(config)  # Обработка config: если строка, берём из другого экземпляра
        self._validate_config(config)       # Проверяем наличие обязательных ключей

        self._init_config_load( # Чтение флагов из конфигурации (с значениями по умолчанию)
            config, 
            # enable_file_logging, 
            # use_name_in_filename
            None, 
            None
        )

        # Преобразуем строковые значения в нужные типы
        try:
            self.log_level = self._parse_log_level(config['LOG_LEVEL'])
            self.base_log_file = config['LOG_FILE']
            self.log_max_bytes = int(config['LOG_MAX_BYTES'])
            self.log_backup_count = int(config['LOG_BACKUP_COUNT'])
            self.log_args = config.get('LOG_ARGS', False)   # новый атрибут
        except ValueError as e:
            raise ValueError(f"Ошибка преобразования параметров логирования: {e}")



        # Создаём логгер (без обработчиков)
        self.logger = logging.getLogger(name)
        self.logger.setLevel(self.log_level)
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

    def _reopen_file_handler_if_needed(self):
        """Переоткрывает файловый обработчик, если файл лога был удалён извне."""
        if self.file_handler and hasattr(self.file_handler, 'reopen_if_needed'):
            # self.file_handler.reopen_if_needed()
            self.file_handler.reopen_if_needed()

    @property
    def effective_enable_file_logging(self) -> bool:
        """Возвращает реальное состояние файлового логирования с учётом ссылки на другой логгер."""
        if self._enable_file_logging_ref:
            parent = self._instances.get(self._enable_file_logging_ref)
            if parent:
                return parent.effective_enable_file_logging
            
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

    @property
    def effective_use_name_in_filename(self) -> bool:
        if self._use_name_in_filename_ref:
            parent = self._instances.get(self._use_name_in_filename_ref)

            if parent:
                return parent.effective_use_name_in_filename
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


    def get_level(self) -> str:
        return logging.getLevelName(self.log_level)

    def set_formatter(self, formatter: logging.Formatter):
        """Устанавливает новый форматтер для всех обработчиков."""
        self.formatter = formatter
        for handler in self.logger.handlers:
            handler.setFormatter(formatter)

        if self._shared_slaves:
            for slave in self._shared_slaves:
                slave.set_formatter(formatter)

    def _reopen_file_handler(self):
        """Принудительно переоткрывает файловый обработчик (удаляет и создаёт заново)."""
        if self.file_handler:
            self.logger.removeHandler(self.file_handler)
            self.file_handler.close()
            self.file_handler = self._create_file_handler()
            self.logger.addHandler(self.file_handler)

            if self._shared_slaves:
                self._update_shared_slaves()

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

    def _validate_config (self, config):
        required_keys = [
            'LOG_LEVEL', 
            'LOG_FILE', 
            'LOG_MAX_BYTES', 
            'LOG_BACKUP_COUNT'
        ]

        missing_keys = [key for key in required_keys if key not in config]

        if missing_keys:
            raise ValueError(f"Отсутствуют обязательные ключи конфигурации: {missing_keys}")        

    def _load_config (self, config):
        # Обработка config: если строка, берём из другого экземпляра
        if isinstance(config, str) and config is not None:
            parent = self._instances.get(config)
            if parent is not None:
                config = {
                    'LOG_LEVEL' : dict(
                        zip(
                            BaseAppLogger.level_map.values(), 
                            BaseAppLogger.level_map.keys()
                        )
                    )[parent.log_level],
                    'LOG_FILE' : parent.base_log_file,
                    'LOG_MAX_BYTES' : parent.log_max_bytes,
                    'LOG_BACKUP_COUNT' : parent.log_backup_count,
                }
            else:
                # родитель не найден – используем дефолт
                config = None

        # Загружаем конфигурацию
        if config is None:
            config = self.get_default_config()

        return config

    def _init_config_load (self, config, enable_file_logging, use_name_in_filename):
        # Чтение флагов из конфигурации (с значениями по умолчанию)
        # self._enabled = config.get('enabled', True)
        # self._console_enabled = config.get('console_enabled', True)
        # self._file_enabled = config.get('file_enabled', bool(enable_file_logging)) # флаг для файлового вывода
        # self._use_name_in_filename = config.get('use_name_in_filename', bool(use_name_in_filename))
        # self.use_timestamp = config.get('use_timestamp', False)

        # Общие флаги (если есть специфичные для имени)
        self._enabled = config.get(f'{self.name}_enabled', config.get('enabled', True))
        self._console_enabled = config.get(
            f'{self.name}_console_enabled', 
            config.get('console_enabled', True)
        )

        # Определяем эффективное значение флагов (с учётом ссылок)
        effective_file = self.effective_enable_file_logging
        effective_name = self.effective_use_name_in_filename

        # Берём значение из конфига, если нет — используем эффективное
        self._file_enabled = config.get(
            f'{self.name}_file_enabled', 
            # config.get('file_enabled', enable_file_logging)
            config.get('file_enabled', effective_file)
        )
        self._use_name_in_filename = config.get(
            f'{self.name}_use_name_in_filename', 
            # use_name_in_filename
            effective_name
        )

        # Приводим к bool (на случай, если в конфиге оказалась строка)
        self._file_enabled = bool(self._file_enabled)
        self._use_name_in_filename = bool(self._use_name_in_filename)

        self.use_timestamp = config.get(
            f'{self.name}_use_timestamp', 
            config.get('use_timestamp', False)
        )

    def get_config(self) -> Dict[str, Any]:
        """Возвращает текущую конфигурацию логгера."""
        return {
            'level': logging.getLevelName(self.log_level),
            'base_log_file': self.base_log_file,
            'log_max_bytes': self.log_max_bytes,
            'log_backup_count': self.log_backup_count,
            'log_args': self.log_args,
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

    def _clear_handlers_old(self): 
        # Удаляем старые "свои" обработчики, если они были
        self._remove_console_handler(if_close_console_handler=True)

        # Удаляем ТОЛЬКО свой файловый обработчик, если он не общий
        if self.file_handler and not self._shared_handler:
            self._remove_file_handler(if_close_file_handler=True)

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

    def _update_console_handler_if_on (self):
        # Консольный обработчик (если включён)
        if self._enabled and self._console_enabled:
            self.console_handler = logging.StreamHandler()
            self.console_handler.setLevel(self.log_level)
            self.console_handler.setFormatter(self.formatter)
            self.logger.addHandler(self.console_handler)   
             
    # def _file_handler_update (self):
    #     # Файловый обработчик
    #     if self._enabled and self._file_enabled:
    #         self.file_handler = self._create_file_handler()
    #         self.logger.addHandler(self.file_handler)

    #     else:
    #         if self.file_handler:
    #             self.file_handler.close()
    #             self.file_handler = None

    def _file_handler_update_if_on (self):
        # Файловый обработчик (если включён)
        if self._enabled and self._file_enabled:
            self.file_handler = self._create_file_handler()
            self.logger.addHandler(self.file_handler)

    def is_enabled(self) -> bool:
        return self._enabled

    def is_console_enabled(self) -> bool:
        return self._console_enabled

    def is_file_enabled(self) -> bool:
        return self._file_enabled
    
    def has_shared_handler(self) -> bool:
        """Возвращает True, если логгер использует общий файловый обработчик."""
        return self._shared_handler
    
    def _update_handlers(self):
        """
        Обновляет набор обработчиков (консольный и файловый) в соответствии с текущими флагами:
        - _enabled, _console_enabled, _file_enabled
        - _shared_handler (использует общий обработчик от другого логгера)
        - эффективные значения (с учётом ссылок enable_file_logging_ref)

        При включении файлового логирования дополнительно вызывает _reopen_file_handler_if_needed()
        для восстановления файла, если он был удалён извне.

        После обновления собственных обработчиков синхронизирует зависимые логгеры (_shared_slaves).
        """

        # self._clear_handlers_all() # Удаляем все обработчики
        # self._update_console_handler() # Консольный обработчик
        # self._file_handler_update() # Файловый обработчик

        # self._clear_handlers_old() # Удаляем старые "свои" обработчики, если они были

        # 1. Удаляем старые «свои» обработчики (консольный и файловый, если они не общие)
        #    Закрываем их только если они не являются общими с другими логгерами.
        self._remove_console_handler(if_close_console_handler=True)

        if self.file_handler and not self._shared_handler:
            self._remove_file_handler(if_close_file_handler=True)


        # Если логгер полностью отключён – больше ничего не добавляем
        if not self._enabled:
            self._save_handlers()
            return
        
        # self._update_console_handler_if_on() # Консольный обработчик (если включён)

        # Консольный обработчик (всегда создаётся заново, если включён)
        if self._console_enabled:
            self.console_handler = logging.StreamHandler()
            self.console_handler.setLevel(self.log_level)
            self.console_handler.setFormatter(self.formatter)
            self.logger.addHandler(self.console_handler)
        else:
            self.console_handler = None

        # # Создаём файловый обработчик только если не используется общий
        # # if not self._shared_handler:
        # #     self._file_handler_update_if_on() # Файловый обработчик (если включён) #  не создаём новый обработчик, если общий
        # if not self._shared_handler:
        #     # Проверяем эффективное состояние файлового логирования
        #     if self.effective_enable_file_logging:
        #         self._file_handler_update_if_on()

        # Файловый обработчик – только если не используется общий и файловое логирование включено
        if not self._shared_handler and self._file_enabled:
            self.file_handler = self._create_file_handler()
            self.logger.addHandler(self.file_handler)
            # Важно: после создания обработчика проверяем существование файла
            # и при необходимости переоткрываем (восстановление после удаления)
            self._reopen_file_handler_if_needed()
        else:
            # Если используется общий обработчик, он уже присутствует (был добавлен через share_file_handler_with)
            # Ничего не делаем, просто убеждаемся, что self.file_handler ссылается на него
            pass


        # Добавляем глобальные обработчики обратно (например, для GUI-логов)
        # Убедимся, что глобальные обработчики присутствуют (они не удалялись, но на всякий случай)
        for handler in self._global_handlers:
            if handler not in self.logger.handlers:
                self.logger.addHandler(handler)

        # Синхронизируем зависимые логгеры (которые используют наш файловый обработчик)
        if self._shared_slaves:
            self._update_shared_slaves()

        self._save_handlers() # Сохраняем ссылки на обработчики (может пригодиться для GUI)               

    def _create_file_handler(self):
        """Создаёт файловый обработчик на основе текущих настроек."""

        log_file = self._get_log_file() # Возвращает имя файла лога с учётом use_name_in_filename

        log_dir = os.path.dirname(log_file) # Получаем директорию

        if log_dir and not os.path.exists(log_dir): # Если директория не существует
            os.makedirs(log_dir, exist_ok=True)

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

        path = self.base_log_file

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

        # Если путь содержит расширение .log (или другое стандартное) – считаем файлом
        if path.lower().endswith('.log'):
            # Создаём родительскую директорию, если её нет (будет позже в _create_file_handler,
            # но можно сразу для ясности)
            parent = os.path.dirname(path)
            if parent and not os.path.exists(parent):
                os.makedirs(parent, exist_ok=True)
            return path

        # Иначе предполагаем, что пользователь указал директорию (без слеша)
        return self._build_log_file_in_dir(path)

        # if os.path.exists(path):
        #     if os.path.isdir(path):
        #         # Это существующая директория
        #         return self._build_log_file_in_dir(path)
        #     else:
        #         # Это существующий файл (или симлинк) – используем как есть
        #         return path

        # # Если base_log_file – это директория, а не файл
        # if os.path.isdir(self.base_log_file):
        #     log_dir = self.base_log_file
        #     if self.use_name_in_filename:
        #         timestamp = time.strftime("%Y%m%d_%H%M%S") if self.use_timestamp else ""
        #         base_name = f"{self.name}_{timestamp}" if timestamp else self.name
        #         filename = f"{base_name}.log"
        #     else:
        #         filename = f"{self.name}.log"
        #     return os.path.join(log_dir, filename)
        # else:
        #     # Обратная совместимость: если передан полный путь, используем его
        #     return self.base_log_file

    def _build_log_file_in_dir(self, dir_path: str) -> str:
        """Формирует имя файла внутри директории с учётом use_name_in_filename и use_timestamp."""
        if self.use_name_in_filename:
            timestamp = time.strftime("%Y%m%d_%H%M%S") if self.use_timestamp else ""
            base_name = f"{self.name}_{timestamp}" if timestamp else self.name
            filename = f"{base_name}.log"

        else:
            filename = f"{self.name}.log"

        return os.path.join(dir_path, filename)    

    def _sync_log_level_and_formatters (self):
        # Синхронизируем уровень и формат для файлового обработчика
        if self.file_handler:
            self.file_handler.setLevel(self.log_level)
            self.file_handler.setFormatter(self.formatter)

    def _sync_formatters (self, formatter):
        # Синхронизация форматирования
        self.formatter = formatter
        if self.file_handler:
            self.file_handler.setFormatter(self.formatter)

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

    def share_file_handler_with(self, other: 'BaseAppLogger') -> None:
        """
        Добавляет файловый обработчик другого логгера к текущему.
        После этого оба логгера пишут в один и тот же файл (с общей ротацией).

        ВНИМАНИЕ: после вызова этого метода НЕ вызывайте turn_off_file_logging()
        у текущего логгера, так как это закроет общий обработчик и остановит
        запись и для другого логгера. Для отключения файлового логирования
        у текущего логгера используйте этот метод только если другой логгер
        больше не нуждается в обработчике, или управляйте файловым логированием
        через исходный логгер.
        """

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

        self.base_log_file = other.base_log_file    # синхронизация пути

        self.log_level = other.log_level            # синхронизация уровня
        self.logger.setLevel(self.log_level)        # применение уровня # важно: уровень логгера тоже должен совпадать
        self.file_handler.setLevel(self.log_level)  

        self._sync_formatters( # Синхронизация форматирования
            formatter=other.formatter
        )

        self.log_args = other.log_args

        # # Используем обработчик другого логгера
        # self.file_handler = other.file_handler
        # self.logger.addHandler(self.file_handler) # Добавляем обработчик


        # Синхронизируем параметры ротации, чтобы при возможном пересоздании обработчика
        # использовались актуальные значения
        self.log_max_bytes = other.log_max_bytes 
        self.log_backup_count = other.log_backup_count

        self.use_timestamp = other.use_timestamp

        # # Синхронизируем флаги и параметры
        # self._file_enabled = other._file_enabled  # флаг, что файловое логирование включено
        # self._use_name_in_filename = other.use_name_in_filename  # копируем настройку
        self._file_enabled = other.effective_enable_file_logging
        self._use_name_in_filename = other.effective_use_name_in_filename

        self._file_enabled = bool(self._file_enabled)
        self._use_name_in_filename = bool(self._use_name_in_filename)

        # Устанавливаем флаги общего обработчика
        self._shared_handler = True
        self._master_logger = other   # запоминаем, от кого взяли обработчик

        # # После успешного шаринга зарегистрировать текущего как зависимого у мастера
        # if other != self and other not in other._shared_slaves:
        #     other._shared_slaves.append(self)

        # Регистрируем себя как слейва у мастера
        if self not in other._shared_slaves:
            other._shared_slaves.append(self)

        self._sync_log_level_and_formatters() # Синхронизируем уровень и формат для файлового обработчика

        self._save_handlers() # Сохраняем ссылки на обработчики (может пригодиться для GUI)

    def get_shared_group(self) -> List['BaseAppLogger']:
        """Возвращает список всех логгеров, использующих тот же файловый обработчик."""
        if self._shared_handler and self._master_logger:
            return [self] + self._master_logger._shared_slaves
        
        elif self._shared_slaves:
            return [self] + self._shared_slaves
        
        return [self]

    def _sync_console_handler (self, slave) -> None:
        # Если у зависимого логгера включён консольный вывод, убедимся, что его уровень совпадает
        if slave._console_enabled and slave.console_handler:
            slave.console_handler.setLevel(self.log_level)

    def _sync_log_formatters(self, slave) -> None:
        # Синхронизируем формат сообщений (если изменился у мастера)
        if slave.formatter != self.formatter:
            slave.formatter = self.formatter

            # Для консольного обработчика тоже нужно обновить формат (если он есть)
            if slave.console_handler:
                slave.console_handler.setFormatter(self.formatter)

            if slave.file_handler:
                slave.file_handler.setFormatter(self.formatter)
                
    def _update_shared_slave(self, slave) -> None:
        # Убедимся, что он всё ещё использует наш обработчик
        if slave.file_handler != self.file_handler:
            # Возможно, он уже переключился – перепривязываем
            slave.logger.removeHandler(slave.file_handler)
            slave.file_handler = self.file_handler

            if self.file_handler not in slave.logger.handlers:
                slave.logger.addHandler(self.file_handler)
                slave._save_handlers()

    def _update_shared_slaves(self) -> None:
        """
        Обновляет всех зависимых логгеров (которые используют наш файловый обработчик)
        при изменении параметров мастера (уровень, путь, лимиты и т.д.).
        """
        if not self._shared_slaves:
            return
        
        for slave in self._shared_slaves[:]:  # копия на случай изменения списка
            # Если зависимый логгер уже неактивен или отключил файловое логирование – пропускаем
            # if not slave._enabled or not slave._file_enabled:
            if not slave._enabled or not slave.effective_enable_file_logging:
                continue

            self._update_shared_slave(slave)# Убедимся, что он всё ещё использует наш обработчик

            # Синхронизируем параметры
            slave.log_level = self.log_level
            slave.logger.setLevel(self.log_level)

            if slave.file_handler:
                slave.file_handler.setLevel(self.log_level)

            # Если нужно синхронизировать другие параметры 
            slave.log_max_bytes = self.log_max_bytes
            slave.log_backup_count = self.log_backup_count
            slave.base_log_file = self.base_log_file
            slave._use_name_in_filename = self._use_name_in_filename
            slave.use_timestamp = self.use_timestamp
            
            slave.log_args = self.log_args

           
            self._sync_log_formatters(slave) # Синхронизируем формат сообщений (если изменился у мастера)
           
            self._sync_console_handler(slave) # Если у зависимого логгера включён консольный вывод, убедимся, что его уровень совпадает

            # Дополнительно можно синхронизировать флаги (но они обычно уже скопированы при создании)
            # slave._enabled = self._enabled  # обычно не нужно, так как включение/отключение индивидуально
            # slave._console_enabled = self._console_enabled

    def _unshare_file_handler_master_logger (self):
        master = self._master_logger
        if master is not None:
            # Удаляем текущий логгер из списка зависимых у мастера
            try:
                master._shared_slaves.remove(self)
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

        if not self._shared_handler:
            return
        
        self._unshare_file_handler_master_logger()


        self._remove_file_handler( # Удаляем общий обработчик  (не закрываем, т.к. он может использоваться другим)
            if_close_file_handler=False # (не закрываем, т.к. он может использоваться другим)
        ) 

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
        if 'base_log_file' in kwargs:
            self.base_log_file = kwargs['base_log_file']
            need_rebuild = True

        if 'log_max_bytes' in kwargs:
            self.log_max_bytes = int(kwargs['log_max_bytes'])
            need_rebuild = True

        if 'log_backup_count' in kwargs:
            self.log_backup_count = int(kwargs['log_backup_count'])
            need_rebuild = True

        if 'use_timestamp' in kwargs:
            # self.use_timestamp = kwargs['use_timestamp']
            self.use_timestamp = bool(kwargs['use_timestamp'])
            need_rebuild = True

        if 'use_name_in_filename' in kwargs:
            # self._use_name_in_filename = kwargs['use_name_in_filename']
            if isinstance(kwargs['use_name_in_filename'], str):
                self._use_name_in_filename = self.effective_use_name_in_filename
            else:
                self._use_name_in_filename = bool(kwargs['use_name_in_filename'])
            need_rebuild = True

        if 'enable_file_logging' in kwargs:
            # warnings.warn("'enable_file_logging' устарел, используйте 'file_enabled'", DeprecationWarning)
            # self._file_enabled = bool(kwargs['enable_file_logging'])
            if isinstance(kwargs['enable_file_logging'], str):
                self._file_enabled = self.effective_enable_file_logging 
            else:
                self._file_enabled = bool(kwargs['enable_file_logging'])
      
            need_rebuild = True

        return need_rebuild

    def _update_flags(self, **kwargs) -> bool:
        """Обновляет флаги включения/отключения.
        Возвращает True, если требуется перестроить обработчики.
        """
        need_rebuild = False
        if 'console_enabled' in kwargs:
            self._console_enabled = kwargs['console_enabled']
            need_rebuild = True

        if 'file_enabled' in kwargs:
            self._file_enabled = kwargs['file_enabled']
            need_rebuild = True

        if 'enabled' in kwargs:
            self._enabled = kwargs['enabled']
            need_rebuild = True

        # Отдельные уровни для консоли и файла (не требуют перестройки)
        if 'console_level' in kwargs:
            self.set_console_level(kwargs['console_level'])

        if 'file_level' in kwargs:
            self.set_file_level(kwargs['file_level'])
        return need_rebuild

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
        if 'level' in kwargs:
            self._update_level(kwargs['level'])

        # Обновляем log_args (не влияет на обработчики, просто сохраняем)
        if 'log_args' in kwargs:
            self.log_args = kwargs['log_args']
 
        # Обновляем параметры файла (сохраняем всегда, пересоздадим обработчики в конце)

        need_rebuild = self._update_file_params(**kwargs)
        need_rebuild = self._update_flags(**kwargs) or need_rebuild

        if need_rebuild:
            self._update_handlers() # внутри вызывает _update_shared_slaves при наличии зависимых
            # После перестроения обработчика уведомляем зависимых
            # self._update_shared_slaves()
        # elif level_changed:
        #     # Уровень изменился, но обработчики не перестраивались – синхронизируем зависимых вручную
        #     self._update_shared_slaves()
        else:
            # Если менялся только уровень, но обработчик не пересоздавался, тоже нужно синхронизировать
            if 'level' in kwargs:
                self._update_shared_slaves()

        # need_rebuild = False
        # if not self._shared_handler:
        #     need_rebuild = self._update_file_params(**kwargs)

        # # Обновление флагов консоли/файла/полного отключения
        # need_rebuild = self._update_flags(**kwargs) or need_rebuild

        # # Если используется общий обработчик, запрещаем изменение файловых параметров
        # if self._shared_handler and self._master_logger:
        #     # Запрещаем менять параметры файла
        #     file_params = [
        #         'base_log_file', 'log_max_bytes', 'log_backup_count',
        #         'use_name_in_filename', 'enable_file_logging', 'file_enabled'
        #     ]
        #     if any(p in kwargs for p in file_params):
        #         self.logger.warning(
        #             f"Логгер '{self.name}' использует общий обработчик от '{self._master_logger.name}'. "
        #             f"Перенаправляю вызов reconfigure мастеру."
        #         )
        #         self._master_logger.reconfigure(**kwargs)
        #         return

        #     # attempted = [p for p in file_params if p in kwargs]
        #     # if attempted:
        #     #     self.logger.warning(
        #     #         f"Логгер '{self.name}' использует общий обработчик. "
        #     #         f"Изменение параметров {attempted} игнорируется. "
        #     #         f"Управляйте файловым логированием через исходный логгер."
        #     #     )
        #         # # Удаляем запрещённые ключи, чтобы не вызывать перестроение
        #         # for p in attempted:
        #         #     kwargs.pop(p, None)

        #         # # Если после удаления нет других параметров, выходим
        #         # if not kwargs:
        #         #     return    
                
        #         # # Если после удаления не осталось параметров, требующих перестройки, выходим
        #         # if not any(k in kwargs for k in ('console_enabled', 'file_enabled', 'enabled')):
        #         #     # Но уровень менять можно
        #         #     if 'level' in kwargs:
        #         #         self.logger.setLevel(self._parse_log_level(kwargs['level']))
        #         #         for handler in self.logger.handlers:
        #         #             handler.setLevel(self.log_level)
        #         #     return

        # else:
        #     # Обрабатываем параметры файла (только если не были удалены на шаге 3)
        #     if 'base_log_file' in kwargs:
        #         self.base_log_file = kwargs['base_log_file']
        #         need_rebuild = True

        #     if 'log_max_bytes' in kwargs:
        #         self.log_max_bytes = int(kwargs['log_max_bytes'])
        #         need_rebuild = True

        #     if 'log_backup_count' in kwargs:
        #         self.log_backup_count = int(kwargs['log_backup_count'])
        #         need_rebuild = True

        #     if 'use_name_in_filename' in kwargs:
        #         self._use_name_in_filename = kwargs['use_name_in_filename']
        #         need_rebuild = True

        #     if 'enable_file_logging' in kwargs:
        #         warnings.warn("'enable_file_logging' устарел, используйте 'file_enabled'", DeprecationWarning)
        #         self._file_enabled = kwargs['enable_file_logging']
        #         need_rebuild = True

        #     # Обновляем флаги включения/отключения
        #     if 'console_enabled' in kwargs:
        #         self._console_enabled = kwargs['console_enabled']
        #         need_rebuild = True

        #     if 'file_enabled' in kwargs:
        #         self._file_enabled = kwargs['file_enabled']
        #         need_rebuild = True

        #     if 'enabled' in kwargs:
        #         self._enabled = kwargs['enabled']
        #         need_rebuild = True

            
        #     if 'use_timestamp' in kwargs:
        #         self.use_timestamp = kwargs['use_timestamp']
        #         need_rebuild = True

        # # Отдельная настройка уровней для консоли и файла
        # if 'console_level' in kwargs:
        #     self.set_console_level(kwargs['console_level'])
        # if 'file_level' in kwargs:
        #     self.set_file_level(kwargs['file_level'])

        # Если что-то изменилось, перестраиваем обработчики
        # if need_rebuild:
        #     self._update_handlers()
        # else:
        #     # Если менялся только уровень, обновляем обработчики на месте
        #     if 'level' in kwargs:
        #         for handler in self.logger.handlers:
        #             handler.setLevel(self.log_level)
    
    @classmethod
    def disable_group_console(cls, name_prefix: str):
        """Отключает вывод в консоль для всех логгеров группы."""
        for inst in cls._instances.values():
            if inst.name.startswith(name_prefix):
                inst.disable_console()

    @classmethod
    def enable_group_console(cls, name_prefix: str):
        """Включает вывод в консоль для всех логгеров группы."""
        for inst in cls._instances.values():
            if inst.name.startswith(name_prefix):
                inst.enable_console()

    @classmethod
    def disable_group_file(cls, name_prefix: str):
        """Отключает файловое логирование для всех логгеров группы."""
        for inst in cls._instances.values():
            if inst.name.startswith(name_prefix):
                inst.turn_off_file_logging()

    @classmethod
    def enable_group_file(cls, name_prefix: str):
        """Включает файловое логирование для всех логгеров группы."""
        for inst in cls._instances.values():
            if inst.name.startswith(name_prefix):
                inst.turn_on_file_logging()

    # Также можно добавить установку уровня отдельно для консоли и файла для группы:
    @classmethod
    def set_group_console_level(cls, name_prefix: str, level: str):
        """Устанавливает уровень логирования для консольного вывода всех логгеров группы."""
        lvl = cls._parse_log_level(level)
        for inst in cls._instances.values():
            if inst.name.startswith(name_prefix):
                inst.set_console_level(lvl)

    @classmethod
    def set_group_file_level(cls, name_prefix: str, level: str):
        """Устанавливает уровень логирования для файлового вывода всех логгеров группы."""
        lvl = cls._parse_log_level(level)
        for inst in cls._instances.values():
            if inst.name.startswith(name_prefix):
                inst.set_file_level(lvl)


    def reload_from_config(self, new_config: Dict[str, Any]):
        """
        Полностью перезагружает настройки логгера из словаря.
        Удобно вызывать после изменения конфигурации приложения.
        """
        # Если используем общий обработчик, перенаправляем вызов мастеру
        if self._shared_handler and self._master_logger:
            self._master_logger.reload_from_config(new_config)
            return

        # Сохраняем старые флаги для сравнения
        old_file_enabled = self._file_enabled
        old_console_enabled = self._console_enabled
        old_enabled = self._enabled

        # Применяем новые настройки
        # self._init_config_load(new_config, self._file_enabled, self._use_name_in_filename)
        self._init_config_load(new_config, None, None)

        # Обновляем остальные параметры
        if 'LOG_LEVEL' in new_config:
            self.log_level = self._parse_log_level(new_config['LOG_LEVEL'])
            self.logger.setLevel(self.log_level)

        if 'LOG_FILE' in new_config:
            self.base_log_file = new_config['LOG_FILE']

        if 'LOG_MAX_BYTES' in new_config:
            self.log_max_bytes = int(new_config['LOG_MAX_BYTES'])

        if 'LOG_BACKUP_COUNT' in new_config:
            self.log_backup_count = int(new_config['LOG_BACKUP_COUNT'])

        if 'LOG_ARGS' in new_config:
            self.log_args = new_config['LOG_ARGS']

        # Если изменились флаги – перестраиваем обработчики
        if (self._file_enabled != old_file_enabled or
            self._console_enabled != old_console_enabled or
            self._enabled != old_enabled):
            self._update_handlers()
        else:
            # Иначе просто обновляем уровни у существующих обработчиков
            for handler in self.logger.handlers:
                handler.setLevel(self.log_level)

        if self._shared_slaves:
            self._update_shared_slaves()
    
    
    # ----------------------------------------------------------------------
    # Методы для включения/отключения логирования
    # ----------------------------------------------------------------------

    def enable(self):
        """
        Полностью включает логирование (консоль + файл согласно настройкам).
        """
        if not self._enabled:
            self._enabled = True
            self._update_handlers()

    def disable(self):
        """
        Полностью отключает логирование (ничего не выводится).
        """
        if self._enabled:
            self._enabled = False
            self._update_handlers()

    def enable_console(self):
        """
        Включает вывод в консоль.
        """
        if not self._console_enabled:
            self._console_enabled = True
            self._update_handlers()

    def disable_console(self):
        """
        Отключает вывод в консоль.
        """
        if self._console_enabled:
            self._console_enabled = False
            self._update_handlers()

    def enable_file(self):
        self.turn_on_file_logging()

    def disable_file(self):
        self.turn_off_file_logging()

    def turn_on_file_logging(self):
        """
        Включает файловое логирование.
        """
        if self.effective_enable_file_logging:
            return
    
        if self._shared_handler:
            self.logger.warning(
                f"Логгер '{self.name}' использует общий обработчик. "
                "Включение файлового логирования невозможно. "
                "Сначала вызовите unshare_file_handler()."
            )
            return
        
        self._file_enabled = True
        self._update_handlers()

        self._reopen_file_handler_if_needed() # после перестроения обработчиков проверяем существование файл
           

    def turn_off_file_logging(self):
        """
        Отключает файловое логирование.
        """
        if not self.effective_enable_file_logging:
            return

        if self._shared_handler:
            # Отвязываемся от общего обработчика, затем отключаем своё файловое логирование
            self.unshare_file_handler(if_update_handlers=False)

            # После отвязки у нас будет свой обработчик (или None), теперь отключаем
            self._file_enabled = False

            # Удаляем общий обработчик из этого логгера, но не закрываем
            self._remove_file_handler(if_close_file_handler=True)

            self._update_handlers() 

            return
        
        # Обычное отключение (свой обработчик)
        self._file_enabled = False
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
                f"enable_file_logging={value} должен быть bool. Используйте turn_on_file_logging/turn_off_file_logging для управления.",
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
    def thec_craete(
        cls,
        name: str,
    ) -> bool:
        """
        Проверяем, существует ли уже экземпляр класса с именем name.
        
        :param name: Имя экземпляра класса.
        :return: True, если экземпляр с именем name существует, False в противном случае.
        """
        return (name in cls._instances )

    
    @classmethod
    def _create_instance_and_share(
        cls, 
        name, # имя экземпляра логгера (строка)
        config, # конфигурация логгера (словарь)
        enable_file_logging=True, # включить файловое логирование 
        use_name_in_filename=False,  # использовать имя экземпляра в имени файла
        auto_share=True, # автоматический шаринг
    ):
        # Создаём новый экземпляр
        instance = cls(
            name=name,
            config=config,
            enable_file_logging=enable_file_logging,
            use_name_in_filename=use_name_in_filename
        )
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
                    not other.effective_use_name_in_filename and  # Используем эффективное значение, чтобы правильно обработать строковые ссылки
                    other.base_log_file == instance.base_log_file and
                    other.file_handler is not None
                ):
                    instance.share_file_handler_with(other)
                    break


        return instance

    @classmethod
    def _get_instance(cls, name, share_file_with):

        # экземпляр с таким именем уже существует - возвращается существующий
        inst = cls._instances[name]
        # Если запрошен шаринг с другим логгером, но ещё не настроен – настраиваем
        if share_file_with and not inst.has_shared_handler():
            other = cls._instances.get(share_file_with)
            if other and other.file_handler:
                inst.share_file_handler_with(other)

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
        auto_share: bool = False,
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
        if isinstance(enable_file_logging, str) and enable_file_logging.lower() not in ('true', 'false'):
            share_file_with = enable_file_logging
            enable_file_logging = True   # файловое логирование включаем, но обработчик будет общим
        
        if not force_new and name in cls._instances:
            # Если экземпляр с таким именем уже существует и force_new=False, возвращается существующий
            return cls._get_instance(
                name=name,
                share_file_with=share_file_with
            )

       
        instance = cls._create_instance_and_share( # Создаём новый экземпляр и применяем шаринг
            name=name,
            config=config,
            enable_file_logging=enable_file_logging,
            use_name_in_filename=use_name_in_filename,

            auto_share=False
        )

        # После создания – если нужен шаринг, применяем
        if share_file_with:
            other = cls._instances.get(share_file_with)
            if other and other.file_handler:
                instance.share_file_handler_with(other)

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
        
    def _thec_skip_patterns_modeles(
        self,
        patterns_modeles
    ):  
        """
        Проверяет, если при указанных параметрах modeles стоит пропустить
        логирование.

        :param patterns_modeles: Словарь с параметрами для фильтрации.
        :return: True - указатель есть в блок листе, False - нет в блок листе.
        """

        # Проверяем, если указатель на место вызова есть в общем блоке лист
        for skip_patterns_modele in self.skip_patterns_modeles: 
            # общий блок лист
            for i in [
                'filename', 
                'function',
            ]:
                # Флаг, указывающий на то, что мы проверяем filename или function
                if_filename  = (i == 'filename')
                
                # Проверяем, есть ли указатель на место вызова в skip
                thec_skip = self._thec_patterns_modeles( 
                    modeles     = skip_patterns_modele.get(i,{}) ,
                    if_err_tip  = if_filename,
                )
                if thec_skip is None:
                    # если нет в skip указателя на function, блок лист (так как filename пройден)
                    # то возвращаем True
                    return True  
                
                # Проверяем, есть ли указатель на место вызова в patterns_modeles
                thec_modeles = self._thec_patterns_modeles(
                    modeles     = patterns_modeles.get(i,{}) ,
                    if_err_tip  = if_filename,
                )
                if thec_modeles is None:
                    # если нет в skip указателя на function, блок лист (так как filename пройден)
                    # то возвращаем True
                    return True  
                    
                # Проверяем, если указатель на место вызова есть в блок листе
                for modele in thec_modeles: 
                    # что проверяем на наличие в блок листе  
                
                    if self._thec_patterns_modeles_is_none(
                        modeles     = modele ,
                        if_err_tip  = if_filename  , 
                    ):
                        # если нет в skip указателя на function, блок лист (так как filename пройден)
                        # то возвращаем True
                        return True

                    if ( # проверка на наличие в блок листе
                        modele in thec_skip
                    ) or (
                        modele == thec_skip
                    ) :
                        # если указатель на место вызова есть в общем блоке лист, то возвращаем True
                        return True  
                    else:
                        # иначе мы проверяем, если указатель на место вызова есть в skip
                        skip_thec = True
                        for skip in thec_skip:
                            if self._thec_patterns_modeles_is_none(
                                modeles     = skip ,   
                                if_err_tip  = if_filename  , 
                            ):
                                # если нет в skip указателя на function, блок лист (так как filename пройден)
                                # то возвращаем True
                                return True 

                            # проверка на наличие каждого элимента по пути
                            skip_thec_ = (
                                (skip in modele) or (skip == modele)
                            )
                            
                            if if_filename or ( skip_thec) : 
                                # если filename, то нудно проверить нахождение каждого элимента по пути. Если все есть, то переход на проверку function
                                skip_thec = skip_thec and skip_thec_
                            else: 
                                # возможно вернуть  skip_thec_, а не continue
                                continue

                        if not skip_thec:
                            # если указатель на место вызова не находится в skip, то возвращаем False
                            return False   
            if not skip_thec:
                # если указатель на место вызова не находится в skip, то возвращаем False
                return False 

        # если указатель на место вызова не находится в общем блоке лист, то возвращаем True
        return True
        



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
        import inspect
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
                        'filename':(frame_info.filename),
                        'function':(frame_info.function),  
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
    
    def _format_message(self, caller_info: str, message: str) -> str:
        """
        Форматирует итоговое сообщение, добавляя имя логгера и указатель.

        caller_info - строка, полученная из _get_caller_info, содержащая информацию о вызове функции:
            - имя файла, в котором находится вызов функции
            - номер строки в файле, в которой находится вызов функции
            - имя функции

        message - текст сообщения, который будет добавлен к caller_info

        Возвращаемый результат - строка, содержащая caller_info и message, разделенные символом табуляции '\t'
        """
        return f"[{self.name}]\t{caller_info}:\t{message}"

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
        if levels_up is None:
            levels_up = self._levels_up

        caller = self._get_caller_info(
            levels_up=levels_up
        )
        return self._format_message(
            caller, 
            message,
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
            if not logger_instance.logger.isEnabledFor(level):
                return func

            # Используем квалифицированное имя (с классом, если это метод)
            func_qualname = func.__qualname__
            try:
                # Получаем имя файла, в котором находится вызов функции
                func_filename = inspect.getfile(func)
            except TypeError:
                # Если функция - встроенная, то имя файла не может быть получено
                func_filename = "<built-in>"

            # Получаем номер строки в файле, в которой находится вызов функции
            func_lineno = func.__code__.co_firstlineno
            # Определяем, является ли функция асинхронной
            is_async = inspect.iscoroutinefunction(func)

            # Общая логика для формирования сообщений и замера времени
            def make_wrapper():
                # Формируем базовую информацию о caller'е (один раз для всех вызовов)
                caller_info = f'File "{func_filename}", line {func_lineno}, in <{func_qualname}>'
                desc_part = f"{description} " if description else ""

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
                    formatted = logger_instance._format_message(caller_info, start_msg)
                    logger_instance.logger.log(level, formatted)

                def log_end(execution_time: float, error: Optional[Exception] = None):
                    end_msg = f"{desc_part}[Завершение: {execution_time:.4f} сек]" if desc_part else f"[Завершение: {execution_time:.4f} сек]"
                    if error:
                        end_msg += f": {error}"
                    formatted = logger_instance._format_message(caller_info, end_msg)
                    logger_instance.logger.log(level, formatted)

                # Создаём синхронную обёртку
                @wraps(func)
                def sync_wrapper(*args, **kwargs):

                    # Вызываем функцию
                    # try:
                    #     result = func(*args, **kwargs)
                    # except Exception as e:
                    #     err = e
                    #     raise e
                    #     # func_qualname
                    # return result
                    
                    log_start(args, kwargs)
                    start_time = time.time()
                    error = None
                    try:
                        result = func(*args, **kwargs)
                    except Exception as e:
                        error = e
                        # raise
                    finally:
                        execution_time = time.time() - start_time
                        log_end(execution_time, error)

                    if error:
                        raise error
                        
                    return result

                # Создаём асинхронную обёртку
                @wraps(func)
                async def async_wrapper(*args, **kwargs):
                    log_start(args, kwargs)
                    start_time = time.time()
                    error = None
                    try:
                        result = await func(*args, **kwargs)
                    except Exception as e:
                        error = e
                        # raise
                    finally:
                        execution_time = time.time() - start_time
                        log_end(execution_time, error)

                    if error:
                        raise error
                    
                    return result
                
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
        for instance in cls._instances.values():
            instance.close()
        cls._instances.clear()


# ------------------------------------------------------------------------------
# Экспортируем только класс
# ------------------------------------------------------------------------------
__all__ = ['BaseAppLogger']