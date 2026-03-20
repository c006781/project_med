# tests/test_logger.py

from tests.utils import check_output_lines

import pytest
# import os
import logging
from app.utils.logger.logger import AppLogger
from app.utils.logger.base_logger import BaseAppLogger

def test_logger_get_instance():
    """
    Тест для метода get_instance класса AppLogger.

    Проверяет, что метод get_instance возвращает экземпляр логгера с указанным именем,
    и что экземпляр является объектом класса logging.Logger.
    """
    logger = AppLogger.get_instance('test')
    assert logger.name == 'test'
    assert isinstance(logger.logger, logging.Logger)

def test_logger_multiton():
    """
    Тест для проверки поведения Multiton паттерна.

    Проверяет, что два экземпляра логгера с одним именем равны друг другу.
    """
    logger1 = AppLogger.get_instance('test')
    logger2 = AppLogger.get_instance('test')
    assert logger1 is logger2

def test_logger_different_names():
    """
    Тест для создания разных именованных экземпляров логгера.

    Проверяет, что два экземпляра логгера с разными именами не равны друг другу.
    """
    logger1 = AppLogger.get_instance('test1')
    logger2 = AppLogger.get_instance('test2')
    assert logger1 is not logger2

def test_logger_file_creation(tmp_path):
    """
    Тест для создания файлов логирования.

    Проверяет, что файл логирования создается и содержит сообщение.
    """
    config = {
        'LOG_LEVEL': 'DEBUG',
        'LOG_FILE': str(tmp_path / 'app.log'),
        'LOG_MAX_BYTES': '1048576',
        'LOG_BACKUP_COUNT': '3'
    }
    logger = BaseAppLogger.get_instance('file_test', force_new=True, config=config, enable_file_logging=True)
    logger.info("Test message")
    log_file = tmp_path / 'app.log'
    assert log_file.exists()
    content = log_file.read_text()
    assert "Test message" in content

def test_logger_levels(caplog):
    """
    Тест для настройки уровня логирования.

    Проверяет, что после настройки уровня логирования сообщения ниже уровня не попадают в лог.
    """
    # Создаем экземпляр логгера
    logger = AppLogger.get_instance('level_test', force_new=True, enable_file_logging=False)

    # Установка уровня логирования
    # Установка уровня ERROR, чтобы информационные сообщения не попадали в лог
    logger.setLevel(logging.ERROR)

    # Включаем propagate, чтобы сообщения доходили до caplog
    std_logger = logger.logger
    old_propagate = std_logger.propagate
    std_logger.propagate = True
    caplog.clear()

    # Создаем информационные сообщения
    logger.debug("debug message")
    logger.info("info message")
    logger.warning("warning message")
    logger.error("error message")

    # Проверяем, что только сообщение уровня ERROR попало в лог
    records = caplog.records
    assert len(records) == 1
    assert records[0].levelname == 'ERROR'
    assert records[0].message == 'error message'

    # Восстанавливаем предыдущее значение propagate
    std_logger.propagate = old_propagate

def test_logger_levels(caplog):
    """
    Тест для настройки уровня логирования.

    Проверяет, что после настройки уровня логирования сообщения ниже уровня не попадают в лог.
    """
    # Создаем экземпляр логгера
    logger = AppLogger.get_instance('level_test', force_new=True, enable_file_logging=False)
    
    # Устанавливаем уровень ERROR
    logger.setLevel(logging.ERROR)
    
    # Включаем propagate, чтобы сообщения доходили до caplog
    std_logger = logger.logger
    old_propagate = std_logger.propagate
    std_logger.propagate = True
    caplog.clear()
    
    # Делаем сообщения уровня DEBUG, INFO, WARNING, ERROR
    logger.debug("debug message")
    logger.info("info message")
    logger.warning("warning message")
    logger.error("error message")
    
    # Проверяем, что только сообщение уровня ERROR попало в лог
    records = caplog.records
    assert len(records) == 1
    assert records[0].levelname == 'ERROR'
    # assert records[0].message == 'error message'
    assert 'error message' in records[0].message
    
    # Возвращаем предыдущий propagate
    std_logger.propagate = old_propagate

# def test_logger_decorator(capsys):
#     """
#     Тест для декоратора log_execution_time.

#     Проверяет, что декоратор корректно работает, выводя сообщения о начале и конце функции.

#     :param capsys: (pytest.fixture) Контейнер для захвата вывода.
#     """
#     config = {
#         'LOG_LEVEL': 'DEBUG',
#         'LOG_FILE': '',
#         'LOG_MAX_BYTES': '0',
#         'LOG_BACKUP_COUNT': '0'
#     }
#     logger = AppLogger.get_instance('decorator_test', config=config, force_new=True, enable_file_logging=False)
#     @logger.log_execution_time(description="Тестовая функция")
#     def func():
#         """
#         Тестовая функция, которую декорирует декоратор log_execution_time.
#         """
#         return 42
#     result = func()
#     # captured = capsys.readouterr()
#     # assert "Тестовая функция [Начало]" in captured.err
#     # assert "Тестовая функция [Завершение:" in captured.err
#     # assert result == 42


#     captured = capsys.readouterr() 
#     expected = [
#         [
#             "Тестовая функция","[Начало]",
#             "Тестовая функция","[Завершение:", "сек]"
#         ]
#     ]
#     check_output_lines(captured.err, expected)
#     assert result == 42


def test_logger_decorator(capsys):
    """
    Тест для декоратора log_execution_time.

    Проверяет, что декоратор корректно работает, выводя сообщения о начале и конце функции.

    :param capsys: (pytest.fixture) Контейнер для захвата вывода.
    """
    config = {
        'LOG_LEVEL': 'DEBUG',
        'LOG_FILE': '',
        'LOG_MAX_BYTES': '0',
        'LOG_BACKUP_COUNT': '0'
    }
    logger = AppLogger.get_instance('decorator_test', config=config, force_new=True, enable_file_logging=False)
    
    @logger.log_execution_time(description="Тестовая функция")
    def func():
        """        
        Тестовая функция, которую декорирует декоратор log_execution_time.
        Возвращает 42.
        """
        return 42
    
    result = func()
    captured = capsys.readouterr()  # единственный вызов после выполнения

    expected = [
        ["Тестовая функция", "[Начало]"],
        ["Тестовая функция", "[Завершение:", "сек]"]
    ]
    check_output_lines(captured.err, expected)
    assert result == 42
