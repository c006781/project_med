# tests/test_ya_dop.py
import pytest
from unittest.mock import MagicMock, patch
from app.network.ya_dop import yadisk_download_file, yadisk_upload_file

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
    mock_y.mkdir.assert_called_once()
    mock_y.upload.assert_called_once_with(str(local_file), "/remote/upload.db", progress_callback=None)

@patch('app.network.ya_dop.yadisk.YaDisk')
def test_yadisk_upload_file_local_not_found(mock_yadisk):
    result = yadisk_upload_file("token", "nonexistent.db", "/remote/upload.db", if_err=False)
    assert result == -2