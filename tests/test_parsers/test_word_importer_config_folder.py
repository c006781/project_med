# tests/test_parsers/test_word_importer_config_folder.py

"""
``pars_start_args`` без ``--folder`` — папка из настройки «Папка документов Word» (Ф1.4.4).

Решение владельца 2026-10-25 (вариант В, ``_dev/ПЛАН.md`` Ф1.1.12): ключ
``WORD_DOCUMENTS_PATH`` в ``config.msgpack`` (умолчание — пусто); читается в момент вызова
через менеджер конфига; пусто — как раньше: «укажите --folder» и выход с кодом 2.
Командная строка и параметр вызова главнее настройки.
"""

import msgpack
import pytest

import parsers.word_importer as word_importer
from app.config.config_manager.manager import AppConfigManager, WORD_DOCUMENTS_PATH_KEY
from parsers.word_importer import pars_start_args


@pytest.fixture
def config_with(tmp_path, monkeypatch):
    """
    Временный ``config.msgpack`` как конфиг по умолчанию; возвращает функцию записи.

    Реестр менеджеров и запомненный путь подменяются — общий тестовый конфиг набора
    (``tests/conftest.py``) не трогается.

    Пример:
        >>> config_with({'WORD_DOCUMENTS_PATH': 'C:/Документы'})
    """
    path = str(tmp_path / 'config.msgpack')
    monkeypatch.setattr(AppConfigManager, '_instances', {})
    monkeypatch.setattr(AppConfigManager, '_resolved_default_path', path)

    def write(data):
        """Пишет настройки в файл (до первого чтения менеджером)."""
        with open(path, 'wb') as f:
            msgpack.pack(data, f)
    return write


@pytest.fixture
def captured_pars_start(monkeypatch):
    """Подмена pars_start: запоминает параметры вызова, в БД не пишет."""
    calls = []

    def fake_pars_start(**kwargs):
        """Запоминает параметры, возвращает пустые результаты."""
        calls.append(kwargs)
        return {}

    monkeypatch.setattr(word_importer, 'pars_start', fake_pars_start)
    return calls


def test_key_default_is_empty(config_with):
    """Ключ есть в умолчаниях менеджера и пуст."""
    assert AppConfigManager._defaults[WORD_DOCUMENTS_PATH_KEY] == ''
    assert AppConfigManager.get_instance().get(WORD_DOCUMENTS_PATH_KEY) == ''


def test_folder_from_config_without_argument(config_with, captured_pars_start, tmp_path):
    """Без --folder и без папки в вызове — папка из настройки."""
    docs = tmp_path / 'docs'
    docs.mkdir()
    config_with({WORD_DOCUMENTS_PATH_KEY: str(docs)})

    pars_start_args(argv=[])

    assert captured_pars_start[0]['folder'] == str(docs)


def test_command_line_and_call_win_over_config(config_with, captured_pars_start, tmp_path):
    """--folder и папка из вызова главнее настройки."""
    from_config, from_call, from_cli = (tmp_path / n for n in ('c', 'v', 'a'))
    for d in (from_config, from_call, from_cli):
        d.mkdir()
    config_with({WORD_DOCUMENTS_PATH_KEY: str(from_config)})

    pars_start_args(
        folder = str(from_call),                    # папка из вызова
        argv   = ['--folder', str(from_cli)],       # командная строка
    )
    pars_start_args(
        folder = str(from_call),                    # папка из вызова
        argv   = [],                                # без --folder
    )

    assert [c['folder'] for c in captured_pars_start] == [str(from_cli), str(from_call)]


def test_empty_config_exits_as_before(config_with, captured_pars_start, capsys):
    """Настройка пуста — «укажите папку … --folder» и выход с кодом 2 (как до ключа)."""
    config_with({WORD_DOCUMENTS_PATH_KEY: ''})

    with pytest.raises(SystemExit) as exc:
        pars_start_args(argv=[])

    assert exc.value.code == 2
    assert '--folder' in capsys.readouterr().err
    assert captured_pars_start == []


def test_config_folder_missing_exits(config_with, captured_pars_start, tmp_path, capsys):
    """Папки из настройки нет на диске — «папки нет» и выход с кодом 2."""
    config_with({WORD_DOCUMENTS_PATH_KEY: str(tmp_path / 'нет')})

    with pytest.raises(SystemExit) as exc:
        pars_start_args(argv=[])

    assert exc.value.code == 2
    assert 'папки нет' in capsys.readouterr().err
    assert captured_pars_start == []


def test_config_read_at_call_time(config_with, captured_pars_start, tmp_path):
    """Настройка читается в момент вызова: изменение в менеджере видно следующему вызову."""
    first, second = tmp_path / 'first', tmp_path / 'second'
    first.mkdir()
    second.mkdir()
    config_with({WORD_DOCUMENTS_PATH_KEY: str(first)})
    pars_start_args(argv=[])

    AppConfigManager.get_instance().set(WORD_DOCUMENTS_PATH_KEY, str(second))
    pars_start_args(argv=[])

    assert [c['folder'] for c in captured_pars_start] == [str(first), str(second)]
