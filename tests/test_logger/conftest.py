# tests/test_logger/conftest.py

"""
Общие фикстуры для характеризующих тестов логгера.

Тесты фиксируют поведение BaseAppLogger/AppLogger «как есть» перед рефакторингом.
Известные дефекты оформлены как ``xfail(strict=True)`` с описанием желаемого
поведения: после исправления такой тест начнёт проходить, strict-xfail упадёт
и напомнит снять маркер.

Изоляция:
    * каждый тест работает с собственным подклассом BaseAppLogger
      (свой реестр ``_instances`` и свой ``get_default_config``);
    * классовое состояние BaseAppLogger (глобальные обработчики, список
      отключённых логгеров, флаги) сохраняется и восстанавливается;
    * созданные обработчики закрываются, чтобы tmp_path можно было удалить на Windows.
"""

import logging
import os
import uuid
from typing import Any, Callable, Dict, List

import pytest

from app.utils.logger.base_logger import BaseAppLogger


def make_config(log_dir: str, **overrides: Any) -> Dict[str, Any]:
    """Минимальная валидная конфигурация в стиле AppLogger.get_default_config().

    Args:
        log_dir: Директория для файлов логов.
        **overrides: Ключи, которые нужно добавить или переопределить.

    Returns:
        Словарь конфигурации.
    """
    config = {
        'LOG_LEVEL': 'DEBUG',
        'LOG_FILE': log_dir.rstrip('/\\') + os.sep,
        'LOG_MAX_BYTES': 10 * 1024 * 1024,
        'LOG_BACKUP_COUNT': 5,
    }
    config.update(overrides)
    return config


def read(path) -> str:
    """Читает файл лога как текст (пустая строка, если файла нет)."""
    path = str(path)
    if not os.path.exists(path):
        return ""
    with open(path, encoding='utf-8') as f:
        return f.read()


@pytest.fixture
def log_dir(tmp_path) -> str:
    """Директория для логов внутри tmp_path."""
    d = tmp_path / 'logs'
    d.mkdir()
    return str(d)


@pytest.fixture
def logger_cls(log_dir):
    """Изолированный подкласс BaseAppLogger с конфигом по умолчанию из tmp_path.

    Конфиг по умолчанию можно менять в тесте через ``logger_cls.default_config``.
    """
    saved = {
        '_global_handlers': list(BaseAppLogger._global_handlers),
        '_disabled_loggers': list(BaseAppLogger._disabled_loggers),
        '_show_call_depth_global': BaseAppLogger._show_call_depth_global,
    }

    # Состояние стандартных логгеров до теста (уровень, propagate, disabled) — восстановить
    std_state = {
        name: (lg.level, lg.propagate, lg.disabled)
        for name, lg in logging.root.manager.loggerDict.items()
        if isinstance(lg, logging.Logger)
    }

    class IsolatedLogger(BaseAppLogger):
        _instances: Dict[str, BaseAppLogger] = {}
        default_config: Dict[str, Any] = make_config(log_dir)

        @classmethod
        def get_default_config(cls) -> Dict[str, Any]:
            return dict(cls.default_config)

    yield IsolatedLogger

    created: List[BaseAppLogger] = list(IsolatedLogger._instances.values())
    for inst in created:
        for handler in inst.logger.handlers[:]:
            try:
                handler.close()
            except Exception:
                pass
            inst.logger.removeHandler(handler)
        # 2026-10-16: имена изолированных логгеров ('system', 'user', 'gui' …) — те же
        # стандартные логгеры, что у приложения. Раньше оставались их уровень, propagate и
        # disabled: например, 'gui' без propagate глушил 'gui.PhotoService' в следующих
        # тестах (test_photo_service_missing_file_on_disk падал в полном наборе).
        state = std_state.get(inst.logger.name)
        if state is None:
            inst.logger.setLevel(logging.NOTSET)
            inst.logger.propagate = True
            inst.logger.disabled = False
        else:
            inst.logger.level, inst.logger.propagate, inst.logger.disabled = state
    IsolatedLogger._instances.clear()

    BaseAppLogger._global_handlers[:] = saved['_global_handlers']
    BaseAppLogger._disabled_loggers[:] = saved['_disabled_loggers']
    BaseAppLogger._show_call_depth_global = saved['_show_call_depth_global']


@pytest.fixture
def unique_name() -> Callable[[str], str]:
    """Генератор уникальных имён логгеров.

    logging.getLogger(name) глобален для процесса, поэтому одинаковые имена
    в разных тестах делили бы один logging.Logger.
    """
    def _make(prefix: str = 'lg') -> str:
        return f"{prefix}_{uuid.uuid4().hex[:8]}"
    return _make


@pytest.fixture
def make_logger(logger_cls, log_dir, unique_name):
    """Фабрика логгеров: ``make_logger(name=None, config=None, **get_instance_kwargs)``.

    По умолчанию создаёт логгер с файлом в log_dir и уникальным именем.
    """
    def _make(name: str = None, config: Dict[str, Any] = None, **kwargs) -> BaseAppLogger:
        if name is None:
            name = unique_name()
        if config is None and 'config' not in kwargs:
            config = make_config(log_dir)
        return logger_cls.get_instance(name=name, config=config, **kwargs)
    return _make


class ListHandler(logging.Handler):
    """Обработчик, собирающий отформатированные записи в список."""

    def __init__(self, level=logging.NOTSET):
        super().__init__(level)
        self.records: List[logging.LogRecord] = []
        self.setFormatter(logging.Formatter('%(levelname)s\t%(message)s'))

    def emit(self, record):
        self.records.append(record)

    @property
    def messages(self) -> List[str]:
        return [r.getMessage() for r in self.records]


@pytest.fixture
def list_handler():
    """Фабрика ListHandler."""
    return ListHandler
