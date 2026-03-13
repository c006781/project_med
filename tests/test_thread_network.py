# tests/test_thread_network.py
import pytest
from unittest.mock import MagicMock, patch
from PySide6.QtCore import QThread
from app.network.thread_network import DownloadThread, UploadThread

@patch('app.network.thread_network.yadisk_download_file')
def test_download_thread_run(mock_download):
    thread = DownloadThread("token", "/remote", "/local")
    mock_download.return_value = 0
    thread.run()
    mock_download.assert_called_once_with(
        ya_token="token",
        ya_file_path="/remote",
        local_file_path="/local",
        if_err=True,
        progress_callback=thread._progress_callback
    )

@patch('app.network.thread_network.yadisk_upload_file')
def test_upload_thread_run(mock_upload):
    thread = UploadThread("token", "/local", "/remote")
    mock_upload.return_value = 0
    thread.run()
    mock_upload.assert_called_once_with(
        ya_token="token",
        local_file_path="/local",
        ya_file_path="/remote",
        if_err=True,
        progress_callback=thread._progress_callback
    )

def test_download_thread_signals():
    thread = DownloadThread("token", "/remote", "/local")
    assert hasattr(thread, 'progress')
    assert hasattr(thread, 'finished')
    assert hasattr(thread, 'error')

def test_upload_thread_signals():
    thread = UploadThread("token", "/local", "/remote")
    assert hasattr(thread, 'progress')
    assert hasattr(thread, 'finished')
    assert hasattr(thread, 'error')