# tests/test_linux_gui/test_linux_gui_open_folder.py
"""
Открытие папки в файловом менеджере: сообщение пользователю, когда не открылось (Linux).

Настоящие программы (``xdg-open``, файловый менеджер) не запускаются: ``QDesktopServices``,
``QProcess`` и ``shutil.which`` подменяются. Нужен только Qt (offscreen), без БД и сети.
"""
import os

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from interfaces.gui.gui_window.pages import settings_page as sp
from interfaces.gui.gui_window.widgets.delegate import photo_edit_dialog as ped


class _FakeDesktopServices:
    """Подмена ``QDesktopServices``: запоминает URL, возвращает заданный результат."""

    result = True
    urls : list = []

    @classmethod
    def openUrl(cls, url):
        cls.urls.append(url.toString())
        return cls.result


@pytest.fixture
def fake_ds(monkeypatch):
    _FakeDesktopServices.urls = []
    _FakeDesktopServices.result = True
    monkeypatch.setattr(ped, 'QDesktopServices', _FakeDesktopServices)
    return _FakeDesktopServices


def test_photo_folder_opened(fake_ds, tmp_path):
    """Папка есть и программа нашлась — ошибки нет, URL построен из пути."""
    folder = tmp_path / 'Фото пациента'
    folder.mkdir()
    assert ped.open_folder_in_file_manager(str(folder)) is None
    assert len(fake_ds.urls) == 1
    assert fake_ds.urls[0].startswith('file://')
    assert fake_ds.urls[0].endswith('Фото пациента')  # путь с кириллицей и пробелом передан целиком


def test_photo_folder_missing(fake_ds, tmp_path):
    """Папки нет — понятное сообщение, менеджер не вызывается."""
    error = ped.open_folder_in_file_manager(str(tmp_path / 'нет'))
    assert error and 'не найдена' in error
    assert fake_ds.urls == []


def test_photo_folder_no_program(fake_ds, tmp_path):
    """``openUrl`` вернул False (нет xdg-open) — сообщение с путём к папке."""
    fake_ds.result = False
    error = ped.open_folder_in_file_manager(str(tmp_path))
    assert error and 'Не удалось открыть папку' in error and str(tmp_path) in error


def test_photo_dialog_shows_warning_on_linux(fake_ds, tmp_path, monkeypatch):
    """Кнопка «открыть папку» на Linux показывает предупреждение, когда не открылось."""
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    photo = tmp_path / 'p.jpg'
    photo.write_bytes(b'x')
    fake_ds.result = False
    shown = []
    monkeypatch.setattr(ped.platform, 'system', lambda: 'Linux')
    monkeypatch.setattr(ped.QMessageBox, 'warning', lambda *a, **k: shown.append(a[1:]))
    dlg = ped.PhotoEditDialog(
        parent   =   None,
        current_path   =   str(photo),
        readonly   =   True,
    )
    dlg._open_photo_folder()
    assert shown and shown[0][0] == 'Не удалось открыть папку'
    dlg.deleteLater()


class _FakeProcess:
    """Подмена ``QProcess``: запоминает вызов, возвращает заданный результат."""

    result = (True, 123)
    calls : list = []

    @classmethod
    def startDetached(cls, program, args):
        cls.calls.append((program, args))
        return cls.result


@pytest.fixture
def fake_proc(monkeypatch):
    _FakeProcess.calls = []
    _FakeProcess.result = (True, 123)
    monkeypatch.setattr(sp, 'QProcess', _FakeProcess)
    return _FakeProcess


def test_log_folder_linux_started(fake_proc, monkeypatch):
    """Есть ``xdg-open`` — запускается он, путь с пробелом и кириллицей одним аргументом."""
    monkeypatch.setattr(sp.shutil, 'which', lambda name: '/usr/bin/' + name)
    folder = '/home/user/Журнал приёмов/logs/'
    assert sp.open_folder_detached(folder, platform='linux') is None
    assert fake_proc.calls == [('xdg-open', [folder])]


def test_log_folder_linux_no_xdg_open(fake_proc, monkeypatch):
    """Нет ``xdg-open`` — сообщение с путём, процесс не запускается."""
    monkeypatch.setattr(sp.shutil, 'which', lambda name: None)
    error = sp.open_folder_detached('/tmp/logs', platform='linux')
    assert error and 'xdg-open' in error and '/tmp/logs' in error
    assert fake_proc.calls == []


def test_log_folder_linux_start_failed(fake_proc, monkeypatch):
    """Программа найдена, но запуск не удался — сообщение."""
    monkeypatch.setattr(sp.shutil, 'which', lambda name: '/usr/bin/' + name)
    fake_proc.result = (False, -1)
    error = sp.open_folder_detached('/tmp/logs', platform='linux')
    assert error and 'Не удалось запустить' in error


def test_log_folder_bool_result_supported(fake_proc, monkeypatch):
    """Результат ``startDetached`` в виде простого bool тоже понимается."""
    monkeypatch.setattr(sp.shutil, 'which', lambda name: '/usr/bin/' + name)
    fake_proc.result = True
    assert sp.open_folder_detached('/tmp/logs', platform='linux') is None
    fake_proc.result = False
    assert sp.open_folder_detached('/tmp/logs', platform='linux')


@pytest.mark.parametrize('platform,program', [('win32', 'explorer'), ('darwin', 'open')])
def test_log_folder_other_platforms(fake_proc, monkeypatch, platform, program):
    """Windows и macOS — прежние программы (``explorer``, ``open``)."""
    monkeypatch.setattr(sp.shutil, 'which', lambda name: '/x/' + name)
    assert sp.open_folder_detached('/tmp/logs', platform=platform) is None
    assert fake_proc.calls[0][0] == program
