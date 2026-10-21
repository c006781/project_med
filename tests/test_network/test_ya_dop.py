# tests/test_ya_dop.py
import pytest
from unittest.mock import MagicMock, patch
from app.network.ya_dop import check_and_create_path, yadisk_download_file, yadisk_upload_file

@patch('app.network.ya_dop.yadisk.YaDisk')
def test_yadisk_download_file_success(mock_yadisk, tmp_path):
    mock_y = MagicMock()
    mock_y.check_token.return_value = True
    mock_y.exists.return_value = True
    mock_yadisk.return_value = mock_y

    local_file = tmp_path / "downloaded.db"
    result = yadisk_download_file("token", "/remote/path", str(local_file), if_err=False)
    assert result == 0
    mock_y.download.assert_called_once_with("/remote/path", str(local_file), progress_callback=None)

@patch('app.network.ya_dop.yadisk.YaDisk')
def test_yadisk_download_file_token_error(mock_yadisk):
    mock_y = MagicMock()
    mock_y.check_token.return_value = False
    mock_yadisk.return_value = mock_y
    result = yadisk_download_file("bad_token", "/remote/path", "local.db", if_err=False)
    assert result == -1

@patch('app.network.ya_dop.yadisk.YaDisk')
def test_yadisk_download_file_not_exists(mock_yadisk):
    mock_y = MagicMock()
    mock_y.check_token.return_value = True
    mock_y.exists.return_value = False
    mock_yadisk.return_value = mock_y
    result = yadisk_download_file("token", "/nonexistent", "local.db", if_err=False)
    assert result == -2

@patch('app.network.ya_dop.yadisk.YaDisk')
def test_yadisk_upload_file_success(mock_yadisk, tmp_path):
    mock_y = MagicMock()
    mock_y.check_token.return_value = True
    mock_y.exists.return_value = False  # для папки
    mock_yadisk.return_value = mock_y

    local_file = tmp_path / "upload.db"
    local_file.write_bytes(b"data")
    result = yadisk_upload_file("token", str(local_file), "/remote/upload.db", if_err=False)
    assert result == 0
    mock_y.makedirs.assert_called_once_with("/remote")
    mock_y.mkdir.assert_not_called()
    mock_y.upload.assert_called_once_with(str(local_file), "/remote/upload.db", progress_callback=None, overwrite=False)

@patch('app.network.ya_dop.yadisk.YaDisk')
def test_yadisk_upload_file_local_not_found(mock_yadisk):
    result = yadisk_upload_file("token", "nonexistent.db", "/remote/upload.db", if_err=False)
    assert result == -2

@patch('app.network.ya_dop.yadisk.YaDisk')
def test_yadisk_download_file_local_path_without_dir(mock_yadisk, tmp_path, monkeypatch):
    """Локальный путь без папки ('clinic.db') — скачивание без попытки makedirs('')."""
    mock_y = MagicMock()
    mock_y.check_token.return_value = True
    mock_y.exists.return_value = True
    mock_yadisk.return_value = mock_y
    monkeypatch.chdir(tmp_path)
    result = yadisk_download_file("token", "/remote/clinic.db", "clinic.db", if_err=True)
    assert result == 0
    mock_y.download.assert_called_once_with("/remote/clinic.db", "clinic.db", progress_callback=None)

@patch('app.network.ya_dop.yadisk.YaDisk')
def test_yadisk_upload_file_existing_parent_not_created(mock_yadisk, tmp_path):
    """Папка на Диске уже есть — makedirs не вызывается."""
    mock_y = MagicMock()
    mock_y.check_token.return_value = True
    mock_y.exists.return_value = True
    mock_yadisk.return_value = mock_y
    local_file = tmp_path / "upload.db"
    local_file.write_bytes(b"data")
    result = yadisk_upload_file("token", str(local_file), "/a/b/upload.db", if_err=False, overwrite=True)
    assert result == 0
    mock_y.makedirs.assert_not_called()
    mock_y.upload.assert_called_once_with(str(local_file), "/a/b/upload.db", progress_callback=None, overwrite=True)

@patch('app.network.ya_dop.yadisk.YaDisk')
def test_check_and_create_path_creates_with_parents(mock_yadisk):
    """Нет пути — создаётся makedirs (с родительскими папками), а не mkdir."""
    mock_y = MagicMock()
    mock_y.check_token.return_value = True
    mock_y.exists.return_value = False
    mock_yadisk.return_value = mock_y
    ok, msg = check_and_create_path("token", "/a/b/c", create_if_missing=True)
    assert ok is True
    mock_y.makedirs.assert_called_once_with("/a/b/c")
    mock_y.mkdir.assert_not_called()

@patch('app.network.ya_dop.yadisk.YaDisk')
def test_check_and_create_path_missing_no_create(mock_yadisk):
    """Нет пути и создавать не просили — (False, сообщение), ничего не создаётся."""
    mock_y = MagicMock()
    mock_y.check_token.return_value = True
    mock_y.exists.return_value = False
    mock_yadisk.return_value = mock_y
    ok, msg = check_and_create_path("token", "/a/b/c", create_if_missing=False)
    assert ok is False
    mock_y.makedirs.assert_not_called()
