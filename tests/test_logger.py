# tests/test_logger.py
import pytest
# import os
import logging
from app.utils.logger.logger import AppLogger
from app.utils.logger.base_logger import BaseAppLogger

def test_logger_get_instance():
    logger = AppLogger.get_instance('test')
    assert logger.name == 'test'
    assert isinstance(logger.logger, logging.Logger)

def test_logger_multiton():
    logger1 = AppLogger.get_instance('test')
    logger2 = AppLogger.get_instance('test')
    assert logger1 is logger2

def test_logger_different_names():
    logger1 = AppLogger.get_instance('test1')
    logger2 = AppLogger.get_instance('test2')
    assert logger1 is not logger2

def test_logger_file_creation(tmp_path):
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

def test_logger_levels():
    logger = AppLogger.get_instance('level_test', force_new=True, enable_file_logging=False)
    logger.setLevel(logging.ERROR)  
    
    # Требуется добавить:  проверим, что сообщения ниже уровня не попадают в лог
    # Это сложно без захвата вывода. Можно использовать caplog.
    pass

# def test_logger_decorator(caplog):

#     config = {
#         'LOG_LEVEL': 'DEBUG',
#         'LOG_FILE': '',  # не нужен
#         'LOG_MAX_BYTES': '0',
#         'LOG_BACKUP_COUNT': '0'
#     }

#     logger = AppLogger.get_instance('decorator_test', config=config, force_new=True, enable_file_logging=False)
#     @logger.log_execution_time(description="Тестовая функция")
#     def func():
#         return 42
#     with caplog.at_level(logging.DEBUG):
#         result = func()
#     assert result == 42
#     assert "Тестовая функция [Начало]" in caplog.text
#     assert "Тестовая функция [Завершение:" in caplog.text

def test_logger_decorator(capsys):   
    config = {
        'LOG_LEVEL': 'DEBUG',
        'LOG_FILE': '',
        'LOG_MAX_BYTES': '0',
        'LOG_BACKUP_COUNT': '0'
    }
    logger = AppLogger.get_instance('decorator_test', config=config, force_new=True, enable_file_logging=False)
    @logger.log_execution_time(description="Тестовая функция")
    def func():
        return 42
    result = func()
    captured = capsys.readouterr()
    assert "Тестовая функция [Начало]" in captured.err
    assert "Тестовая функция [Завершение:" in captured.err
    assert result == 42