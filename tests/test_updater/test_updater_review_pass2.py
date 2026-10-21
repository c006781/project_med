# tests/test_updater/test_updater_review_pass2.py

"""
Тесты исправлений проверки модуля app.updater, проход 2 (2026-10-21).

Номера — журнал проверок в ``app/UPDATER.md``.
"""

from typing import List
from unittest.mock import patch

import app.updater as updater
from app.updater import UpdateApplier, select_release_asset


def test_u10_assets_null():
    """'assets': null в ответе GitHub — None, без TypeError."""
    assert select_release_asset(None, 'windows') is None


def test_u11_applier_without_release_data():
    """UpdateApplier(None).start() — сообщение об ошибке, без AttributeError."""
    applier = UpdateApplier(None)
    errors: List[str] = []
    applier.error.connect(errors.append)
    with patch.object(updater, 'UpdateDownloader') as downloader_cls, \
         patch.object(updater.sys, 'frozen', True, create=True), \
         patch.object(updater, 'current_system', return_value='windows'), \
         patch('app.config.conf.getenv.get_getenv', return_value=''):
        applier.start()
    downloader_cls.assert_not_called()
    assert errors == ['Не найден подходящий файл обновления для вашей ОС']


def test_u10_applier_assets_null():
    """Релиз с 'assets': null — сообщение об ошибке."""
    applier = UpdateApplier({'assets': None})
    errors: List[str] = []
    applier.error.connect(errors.append)
    with patch.object(updater, 'UpdateDownloader'), \
         patch.object(updater.sys, 'frozen', True, create=True), \
         patch.object(updater, 'current_system', return_value='windows'), \
         patch('app.config.conf.getenv.get_getenv', return_value=''):
        applier.start()
    assert errors == ['Не найден подходящий файл обновления для вашей ОС']
