# tests/test_config/test_coverage_gaps.py

"""
Тесты мест модуля конфигурации, не покрытых остальными тестами (замер coverage
2026-10-15): ``logging_setup``, версия приложения, ветки ошибок ввода-вывода и
значения по умолчанию для пути к .env.
"""

import os

import msgpack
import pytest

import app.config as config_package
import app.config.conf.getenv as getenv_module
import app.config.config_manager.manager as manager_module
from app.config.conf.getenv import crete_env_file, save_env_file
from app.config.config_manager.manager import AppConfigManager


@pytest.fixture
def cfg_path(config_sandbox):
    """Путь к config.msgpack во временной папке теста."""
    return str(config_sandbox / 'config.msgpack')


# ---------------------------------------------------------------------------
# logging_setup
# ---------------------------------------------------------------------------

def test_setup_logging_passes_config_to_logger(cfg_path, monkeypatch):
    """setup_logging: конфиг из файла → AppLogger.configure; возвращается копия."""
    import app.config.logging_setup as ls
    with open(cfg_path, 'wb') as f:
        msgpack.pack({'LOG_LEVEL': 'WARNING'}, f)
    got = []
    monkeypatch.setattr(ls.AppLogger, 'configure', classmethod(lambda cls, cfg: got.append(cfg)))

    result = ls.setup_logging(config_path=cfg_path)

    assert len(got) == 1 and got[0]['LOG_LEVEL'] == 'WARNING'
    assert result == got[0] and result is not got[0]          # копия
    result['LOG_LEVEL'] = 'X'
    assert got[0]['LOG_LEVEL'] == 'WARNING'


def test_setup_logging_without_file_uses_defaults(cfg_path, monkeypatch):
    """Файла нет — логгеры получают значения по умолчанию, файл не создаётся."""
    import app.config.logging_setup as ls
    got = []
    monkeypatch.setattr(ls.AppLogger, 'configure', classmethod(lambda cls, cfg: got.append(cfg)))
    assert ls.setup_logging(config_path=cfg_path)['LOG_LEVEL'] == 'INFO'
    assert not os.path.exists(cfg_path)


def test_setup_logging_repeatable(cfg_path, monkeypatch):
    """Повторный вызов перечитывает и применяет конфиг снова."""
    import app.config.logging_setup as ls
    got = []
    monkeypatch.setattr(ls.AppLogger, 'configure', classmethod(lambda cls, cfg: got.append(cfg)))
    ls.setup_logging(config_path=cfg_path)
    ls.setup_logging(config_path=cfg_path)
    assert len(got) == 2


# ---------------------------------------------------------------------------
# app/config/__init__.py — версия
# ---------------------------------------------------------------------------

def test_version_read_from_file(monkeypatch, tmp_path):
    """VERSION читается из папки сборки (_MEIPASS) и обрезается."""
    (tmp_path / 'VERSION').write_text('2.3.4\n', encoding='utf-8')
    monkeypatch.setattr(config_package.sys, '_MEIPASS', str(tmp_path), raising=False)
    assert config_package._get_version() == '2.3.4'


def test_version_fallback_without_file(monkeypatch, tmp_path):
    """Нет файла VERSION — '0.0.0-dev', без исключения."""
    monkeypatch.setattr(config_package.sys, '_MEIPASS', str(tmp_path), raising=False)
    assert config_package._get_version() == '0.0.0-dev'


# ---------------------------------------------------------------------------
# getenv — ветки ошибок и путь по умолчанию
# ---------------------------------------------------------------------------

def test_key_in_file_unreadable_returns_false(env_file, monkeypatch):
    """_key_in_file: файл не читается — False (тогда ключ будет дописан)."""
    env_file.write_text("A='1'\n", encoding='utf-8')

    def boom(*args, **kwargs):
        raise PermissionError('locked')

    monkeypatch.setattr(getenv_module, 'dotenv_values', boom)
    assert getenv_module._key_in_file(str(env_file), 'A') is False


def test_key_in_file_missing_file():
    assert getenv_module._key_in_file('', 'A') is False
    assert getenv_module._key_in_file('no_such.env', 'A') is False


def test_crete_env_file_default_path(config_sandbox):
    """Без пути — .env в папке get_dotenv_path() (в тестах — tmp_path)."""
    crete_env_file()
    assert (config_sandbox / '.env').exists()


def test_crete_env_file_keeps_existing(env_file):
    """Существующий .env не обнуляется."""
    env_file.write_text("A='1'\n", encoding='utf-8')
    crete_env_file(str(env_file))
    assert env_file.read_text(encoding='utf-8') == "A='1'\n"


def test_save_env_file_default_path(config_sandbox):
    """save_env_file без пути пишет в .env из get_dotenv_path()."""
    (config_sandbox / '.env').write_text('', encoding='utf-8')
    save_env_file({'NEW_KEY': 'v'})
    assert "NEW_KEY='v'" in (config_sandbox / '.env').read_text(encoding='utf-8')
    assert os.environ['NEW_KEY'] == 'v'


# ---------------------------------------------------------------------------
# manager — ветки ошибок
# ---------------------------------------------------------------------------

def test_recover_when_new_file_cannot_be_saved(cfg_path, monkeypatch):
    """Битый файл переименован, а новый записать не удалось — сообщение об этом."""
    with open(cfg_path, 'wb') as f:
        f.write(b'\xc1')

    def fail_save(self):
        raise PermissionError('read-only')

    monkeypatch.setattr(AppConfigManager, 'save', fail_save)
    m = AppConfigManager.get_instance(config_path=cfg_path)
    assert m.broken_config_backup and os.path.exists(m.broken_config_backup)
    assert 'Создать новый файл не удалось' in m.broken_config_message
    assert m.get('LOG_LEVEL') == 'INFO'


def test_save_failure_temp_cleanup_error_ignored(cfg_path, monkeypatch):
    """Сбой записи + не удалось удалить временный файл — наружу исходная ошибка."""
    m = AppConfigManager.get_instance(config_path=cfg_path)

    def boom(obj, stream, **kwargs):
        raise OSError('disk full')

    def no_remove(path):
        raise PermissionError('locked')

    monkeypatch.setattr(manager_module.msgpack, 'pack', boom)
    monkeypatch.setattr(manager_module.os, 'remove', no_remove)
    with pytest.raises(OSError, match='disk full'):
        m.save()
