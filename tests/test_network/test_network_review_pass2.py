# tests/test_network/test_network_review_pass2.py

"""
Тесты исправлений проверки модуля app.network, проход 2 (2026-10-21).

Номера — журнал проверок в ``app/network/IMPLEMENTATION.md``.
"""

from unittest.mock import MagicMock, patch

import pytest
from yadisk.exceptions import DirectoryExistsError

import app.network.ya_dop as ya_module
from app.network.ya_dop import YaDiskResult, yadisk_upload_file


@pytest.fixture
def disk():
    """Подменённый клиент: токен действителен, папки на Диске есть."""
    client = MagicMock(name='YaDisk')
    client.check_token.return_value = True
    client.exists.return_value = True
    with patch.object(ya_module.yadisk, 'YaDisk', return_value=client):
        yield client


@pytest.fixture
def local_db(tmp_path):
    """Локальный файл БД."""
    path = tmp_path / 'clinic.db'
    path.write_bytes(b'data')
    return path


@pytest.mark.parametrize('overwrite', [False, True])
def test_n7_upload_onto_dir_returns_not_a_file(disk, local_db, overwrite):
    """По пути на Диске — папка: NOT_A_FILE (а не «файл уже есть»), при любом overwrite."""
    disk.upload.side_effect = DirectoryExistsError()
    result = yadisk_upload_file('t', str(local_db), '/Папка', overwrite=overwrite)
    assert result == YaDiskResult.NOT_A_FILE


def test_n7_upload_onto_dir_raises_is_a_directory(disk, local_db):
    """То же при if_err=True — IsADirectoryError с текстом про папку."""
    disk.upload.side_effect = DirectoryExistsError()
    with pytest.raises(IsADirectoryError, match='к папке'):
        yadisk_upload_file('t', str(local_db), '/Папка', if_err=True, overwrite=True)
