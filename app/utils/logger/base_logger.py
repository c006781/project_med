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
"""

import os
import logging
import time
import inspect
from functools import wraps
from logging.handlers import RotatingFileHandler
from typing import Optional, Dict, Any, Callable


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

    # Словарь экземпляров (ключ - имя логгера)
    _instances: Dict[str, 'BaseAppLogger'] = {}

    # Простой формат лога: время, уровень, сообщение (всё остальное формируем вручную)
    LOG_FORMAT = '%(asctime)s\t%(levelname)s\t%(message)s'

    @classmethod
    def get_default_config(cls) -> Dict[str, Any]:
        """
        Возвращает конфигурацию по умолчанию.
        Должен быть переопределён в наследнике.
        """
        raise RuntimeError(
            "Метод get_default_config() не переопределён в наследнике. "
            "Передайте config напрямую в get_instance() или переопределите метод."
        )

    def __init__(
            self,
            name: str,
            config: Optional[Dict[str, Any]] = None,
            enable_file_logging: bool = False,
            use_name_in_filename: bool = False
    ):
        """
        Инициализирует новый экземпляр логгера. Не вызывается напрямую – используйте get_instance().

        :param name: (str) Имя логгера.
        :param config: (dict) Словарь с настройками. Если не передан, загружается через get_default_config().
        :param enable_file_logging: (bool) Если True, добавляется файловый обработчик. Иначе только консоль.
        :param use_name_in_filename: (bool) Если True, имя экземпляра вставляется в имя файла лога.
        """
        self.name = name
        self.enable_file_logging = enable_file_logging
        self.use_name_in_filename = use_name_in_filename

        # Загружаем конфигурацию
        if config is None:
            config = self.get_default_config()

        # Проверяем наличие обязательных ключей
        required_keys = ['LOG_LEVEL', 'LOG_FILE', 'LOG_MAX_BYTES', 'LOG_BACKUP_COUNT']
        missing_keys = [key for key in required_keys if key not in config]
        if missing_keys:
            raise ValueError(f"Отсутствуют обязательные ключи конфигурации: {missing_keys}")

        # Преобразуем строковые значения в нужные типы
        try:
            self.log_level = self._parse_log_level(config['LOG_LEVEL'])
            self.base_log_file = config['LOG_FILE']
            self.log_max_bytes = int(config['LOG_MAX_BYTES'])
            self.log_backup_count = int(config['LOG_BACKUP_COUNT'])
        except ValueError as e:
            raise ValueError(f"Ошибка преобразования параметров логирования: {e}")

        # Формируем фактическое имя файла лога (если нужно)
        if self.enable_file_logging and self.use_name_in_filename:
            base, ext = os.path.splitext(self.base_log_file)
            self.log_file = f"{base}_{self.name}{ext}"
        else:
            self.log_file = self.base_log_file

        # Создаём папку для логов, если она не существует
        log_dir = os.path.dirname(self.log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)

        # Настраиваем логгер
        self.logger = logging.getLogger(name)
        self.logger.setLevel(self.log_level)
        self.logger.propagate = False  # предотвращаем дублирование, если есть корневой логгер

        # Формат сообщений
        formatter = logging.Formatter(self.LOG_FORMAT)

        # Добавляем файловый обработчик, если разрешено
        if self.enable_file_logging:
            file_handler = RotatingFileHandler(
                filename=self.log_file,
                maxBytes=self.log_max_bytes,
                backupCount=self.log_backup_count,
                encoding='utf-8'
            )
            file_handler.setLevel(self.log_level)
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)

        # Консольный обработчик (всегда включён для отладки)
        console_handler = logging.StreamHandler()
        console_handler.setLevel(self.log_level)
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)

        # Сохраняем ссылки на обработчики (может пригодиться для добавления GUI-обработчика позже)
        self.handlers = self.logger.handlers[:]

    @classmethod
    def thec_craete(
        cls,
        name: str,
    ) -> bool:
        return (name in cls._instances ) 

    @classmethod
    def get_instance(
        cls,
        name: str = 'default',
        force_new: bool = False,
        config: Optional[Dict[str, Any]] = None,
        enable_file_logging: bool = True,
        use_name_in_filename: bool = False,
    ) -> 'BaseAppLogger':
        """
        Возвращает экземпляр логгера с указанным именем.

        Если экземпляр с таким именем уже существует и force_new=False, возвращается существующий
        (параметры enable_file_logging и use_name_in_filename игнорируются).
        Если force_new=True, создаётся новый экземпляр (старый при этом не удаляется).

        :param name: (str) Имя логгера.
        :param force_new: (bool) Принудительное создание нового экземпляра.
        :param config: (dict) Конфигурация для нового экземпляра (если None, используется провайдер).
        :param enable_file_logging: (bool) Для нового экземпляра: включать ли запись в файл.
        :param use_name_in_filename: (bool) Для нового экземпляра: добавлять ли имя в имя файла.
        :return: Экземпляр BaseAppLogger.
        """
        # if not force_new and name in cls._instances:
        if not force_new and (cls.thec_craete(name = name)):
            return cls._instances[name]

        # Создаём новый экземпляр
        instance = cls(
            name=name,
            config=config,
            enable_file_logging=enable_file_logging,
            use_name_in_filename=use_name_in_filename
        )
        cls._instances[name] = instance
        return instance

    @staticmethod
    def _parse_log_level(level_str: str) -> int:
        """
        Преобразует строковое представление уровня логирования в константу logging.
        """
        level_map = {
            'DEBUG': logging.DEBUG,
            'INFO': logging.INFO,
            'WARNING': logging.WARNING,
            'ERROR': logging.ERROR,
            'CRITICAL': logging.CRITICAL
        }
        upper_str = level_str.upper()
        if upper_str not in level_map:
            raise ValueError(f"Неизвестный уровень логирования: {level_str}. Допустимые: DEBUG, INFO, WARNING, ERROR, CRITICAL")
        return level_map[upper_str]

    # --------------------------------------------------------------------------
    # Вспомогательные методы для формирования указателя на место вызова
    # --------------------------------------------------------------------------
    def _get_caller_info(self, levels_up: int = 2) -> str:
        """Возвращает строку с информацией о caller'е на указанное количество уровней выше."""
        stack = inspect.stack()
        if len(stack) <= levels_up:
            frame_info = stack[-1]
        else:
            frame_info = stack[levels_up]

        filename = frame_info.filename
        lineno = frame_info.lineno
        funcname = frame_info.function
        return f'File "{filename}", line {lineno}, in <{funcname}>'

    def _format_message(self, caller_info: str, message: str) -> str:
        """Форматирует итоговое сообщение, добавляя имя логгера и указатель."""
        return f"[{self.name}]\t{caller_info}:\t{message}"

    # --------------------------------------------------------------------------
    # Прямые методы логирования
    # --------------------------------------------------------------------------
    
    def _formatted(
            self,
            message,
            levels_up=2,
    ):
        caller = self._get_caller_info(
            levels_up=levels_up
        )
        return self._format_message(
            caller, 
            message,
        )
        
    
    def debug(self, message: str) -> None:
        self.logger.debug(
            self._formatted(
                message = message,   
            )
        )

    def info(self, message: str) -> None:
        self.logger.info(
            self._formatted(
                message = message,   
            )
        )

    def warning(self, message: str) -> None:
        self.logger.warning(
            self._formatted(
                message = message,   
            )
        )

    def error(self, message: str) -> None:
        self.logger.error(
            self._formatted(
                message = message,   
            )
        )

    def critical(self, message: str) -> None:
        self.logger.critical(
            self._formatted(
                message = message,   
            )
        )

    def exception(self, message: str, exc_info: bool = True) -> None:
        self.logger.error(
            self._formatted(
                message = message,   
            ), exc_info=exc_info
        )

    # --------------------------------------------------------------------------
    # Декоратор для замера времени выполнения
    # --------------------------------------------------------------------------
    def log_execution_time(self, description: str = "", level: int = logging.DEBUG) -> Callable:
        """
        Декоратор для логирования времени выполнения функции или метода.
        """
        logger_instance = self

        def decorator(func: Callable) -> Callable:
            func_filename = inspect.getfile(func)
            func_lineno = func.__code__.co_firstlineno
            func_name = func.__name__
            is_async = inspect.iscoroutinefunction(func)

            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                caller_info = f'File "{func_filename}", line {func_lineno}, in <{func_name}>'
                desc_part = description if description else ""

                start_msg = f"{desc_part} [Начало]" if desc_part else "[Начало]"
                formatted_start = logger_instance._format_message(caller_info, start_msg)
                logger_instance.logger.log(level, formatted_start)

                start_time = time.time()
                result = func(*args, **kwargs)
                execution_time = time.time() - start_time

                end_msg = f"{desc_part} [Завершение: {execution_time:.4f} сек]" if desc_part else f"[Завершение: {execution_time:.4f} сек]"
                formatted_end = logger_instance._format_message(caller_info, end_msg)
                logger_instance.logger.log(level, formatted_end)

                return result

            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                caller_info = f'File "{func_filename}", line {func_lineno}, in <{func_name}>'
                desc_part = description if description else ""

                start_msg = f"{desc_part} [Начало]" if desc_part else "[Начало]"
                formatted_start = logger_instance._format_message(caller_info, start_msg)
                logger_instance.logger.log(level, formatted_start)

                start_time = time.time()
                result = await func(*args, **kwargs)
                execution_time = time.time() - start_time

                end_msg = f"{desc_part} [Завершение: {execution_time:.4f} сек]" if desc_part else f"[Завершение: {execution_time:.4f} сек]"
                formatted_end = logger_instance._format_message(caller_info, end_msg)
                logger_instance.logger.log(level, formatted_end)

                return result

            return async_wrapper if is_async else sync_wrapper

        return decorator

    # --------------------------------------------------------------------------
    # Закрытие логгера
    # --------------------------------------------------------------------------
    def close(self) -> None:
        for handler in self.logger.handlers[:]:
            handler.close()
            self.logger.removeHandler(handler)
        self.handlers.clear()

    @classmethod
    def close_all(cls) -> None:
        for instance in cls._instances.values():
            instance.close()
        cls._instances.clear()


# ------------------------------------------------------------------------------
# Экспортируем только класс
# ------------------------------------------------------------------------------
__all__ = ['BaseAppLogger']