import pytest
import logging
import os
from app.utils.logger.logger import AppLogger
from app.utils.logger.base_logger import BaseAppLogger

def test_logger_rotation(tmp_path):
    """
    Тест для ротации лог-файлов.

    Создаём логгер с маленьким размером файла (100 байт) и проверяем, 
    что при превышении лимита создается файл с суффиксом .1, .2 и т.д.
    """
    log_file = tmp_path / "app.log"
    config = {
        # Уровень логирования
        'LOG_LEVEL': 'DEBUG',
        # Путь к файлу логов
        'LOG_FILE': str(log_file),
        # Максимальный размер файла (100 байт)
        'LOG_MAX_BYTES': '100',
        # Количество бэкапов (2)
        'LOG_BACKUP_COUNT': '2'
    }
    # Создаём логгер с настройками
    logger = BaseAppLogger.get_instance(
        'rotation_test', 
        force_new=True, 
        config=config, 
        enable_file_logging = True
    )
    # Пишем много сообщений, чтобы превысить лимит
    for i in range(50):
        logger.debug(f"Message {i} with enough length to exceed limit quickly")
    # Проверяем, что файл существует и есть backup
    assert log_file.exists()
    # Ротация создаёт файлы с суффиксами .1, .2 и т.д.
    backups = list(tmp_path.glob("app.log.*"))
    assert len(backups) > 0

def test_logger_close_all():
    """
    Тест для закрытия всех логгеров.

    Создаём два логгера, проверяем, что они добавляются в словарь экземпляров.
    Затем, вызываем close_all() и проверяем, что словарь экземпляров стал пустым.
    Наконец, проверяем, что можно создать новый логгер.
    """
    # Создаём два логгера
    logger1 = AppLogger.get_instance(
        'close_test1', 
        force_new=True, 
        enable_file_logging = False
        )
    logger2 = AppLogger.get_instance(
        'close_test2', 
        force_new=True, 
        enable_file_logging = False
        )
    # Проверяем, что они добавляются в словарь экземпляров
    assert len(AppLogger._instances) >= 2
    # Закрываем все логгеры
    AppLogger.close_all()
    # Проверяем, что словарь экземпляров стал пустым
    assert len(AppLogger._instances) == 0
    # Проверяем, что после закрытия можно создать новые
    logger3 = AppLogger.get_instance('close_test3')
    assert logger3 is not None

def test_logger_different_levels(tmp_path):
    """
    Тест для логгеров с разными уровнями логирования.

    Создаём два логгера - debug и info, каждый со своим уровнем логирования.
    Затем, проверяем, что debug-сообщение попадает в файл debug, а info-сообщение попадает в файл info.
    """
    log_file = tmp_path / "app.log"
    config_debug = {
        'LOG_LEVEL': 'DEBUG',
        'LOG_FILE': str(log_file),
        'LOG_MAX_BYTES': '1048576',
        'LOG_BACKUP_COUNT': '1'
    }
    config_info = {
        'LOG_LEVEL': 'INFO',
        'LOG_FILE': str(log_file.with_suffix('.info.log')),
        'LOG_MAX_BYTES': '1048576',
        'LOG_BACKUP_COUNT': '1'
    }
    debug_logger = BaseAppLogger.get_instance(
        'debug_logger', 
        force_new=True,
          config=config_debug, 
          enable_file_logging = True
        )
    info_logger = BaseAppLogger.get_instance(
        'info_logger', 
        force_new=True, 
        config=config_info, 
        enable_file_logging = True
    )

    debug_logger.debug("This is debug")
    debug_logger.info("This is info")
    info_logger.debug("Should not appear")
    info_logger.info("This is info2")

    # Проверяем, что в файле debug есть debug-сообщение
    with open(log_file) as f:
        content = f.read()
        assert "This is debug" in content
        assert "This is info" in content
    # В info-файле не должно быть debug
    with open(log_file.with_suffix('.info.log')) as f:
        content = f.read()
        assert "Should not appear" not in content
        assert "This is info2" in content

def test_logger_without_file(capsys):
    """
    Тест для логгера без файла.

    Создаём логгер без файлового логирования и проверяем, что сообщения попадают в stderr.
    """
    logger = AppLogger.get_instance('console_only', force_new=True, enable_file_logging = False)
    logger.info("Console message")
    captured = capsys.readouterr()
    assert "Console message" in captured.err  # логи идут в stderr 