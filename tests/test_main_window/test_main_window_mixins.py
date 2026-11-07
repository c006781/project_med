# tests/test_main_window/test_main_window_mixins.py
"""
Миксины окна: имена не пересекаются, сообщения Диска и обновлений идут своими обработчиками.

Сеть не используется: потоки не запускаются.
"""
import itertools

import pytest

from app.network.ya_dop import YaDiskResult
from interfaces.gui.gui_window import main_window as mw

MIXINS = (
    mw.PagesCreationMixin,
    mw.ConnectionsMixin,
    mw.DeleteHandlersMixin,
    mw.NavigationMixin,
    mw.SyncMixin,
    mw.UpdateMixin,
)


# имена, определённые самим классом (без служебных Python)
def _own_names(cls: type) -> set:
    """Возвращает имена атрибутов класса без служебных."""
    return {name for name in vars(cls) if not (name.startswith('__') and name.endswith('__'))}


def test_mixins_have_no_common_names():
    """Одно имя в двух миксинах: сработал бы только первый по наследованию, молча."""
    for first, second in itertools.combinations(MIXINS, 2):
        common = _own_names(first) & _own_names(second)
        assert not common, f"{first.__name__} и {second.__name__}: {sorted(common)}"


def test_inheritance_order():
    """Порядок наследования не меняется незаметно: окно первым берёт QMainWindow."""
    bases = mw.MainWindow.__mro__
    assert bases[0] is mw.MainWindow
    positions = [bases.index(mixin) for mixin in MIXINS]
    assert positions == sorted(positions)


@pytest.mark.parametrize('name, owner', [
    ('_on_db_download_finished', mw.SyncMixin),
    ('_on_db_download_error', mw.SyncMixin),
    ('_on_update_download_finished', mw.UpdateMixin),
    ('_on_update_download_error', mw.UpdateMixin),
    ('_on_update_download_progress', mw.UpdateMixin),
    ('_on_update_download_warning', mw.UpdateMixin),
])
def test_handlers_resolve_to_own_mixin(name, owner):
    """Окно получает обработчик от своего миксина."""
    assert getattr(mw.MainWindow, name) is vars(owner)[name]


def test_old_shared_names_are_gone():
    """Прежних общих имён нет: подключить к ним сигнал по ошибке нельзя."""
    assert not hasattr(mw.MainWindow, '_on_download_finished')
    assert not hasattr(mw.MainWindow, '_on_download_error')
    assert not hasattr(mw.MainWindow, '_correct_remote_path')


@pytest.mark.parametrize('code', [
    YaDiskResult.NO_CONNECTION,
    YaDiskResult.FAILED,
    YaDiskResult.ALREADY_EXISTS,
])
def test_upload_code_is_explained(host, messages, code):
    """Код выгрузки показывается текстом, а не числом."""
    host._on_upload_finished(int(code))
    [(title, text)] = messages.texts('critical')
    assert title == 'Ошибка'
    assert text == code.message
    assert str(int(code)) not in text
