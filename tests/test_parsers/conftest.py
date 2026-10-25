# tests/test_parsers/conftest.py

"""
Фикстуры тестов импорта из Word (``parsers/word_importer.py``).

Сервисы и БД — из ``tests/conftest.py`` (БД в памяти, хранилище фото — ``tmp_path``).
"""

import pytest


@pytest.fixture
def services(database, patient_service, appointment_service, photo_service):
    """
    Сервисы и БД для импорта — как их собирает приложение; передаются в
    ``batch_parse(**services)``.

    Пример:
        >>> results, log_dir = batch_parse(str(tmp_path), **services)
    """
    return {
        'db'                  : database,
        'patient_service'     : patient_service,
        'appointment_service' : appointment_service,
        'photo_service'       : photo_service,
    }
