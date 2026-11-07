# tests/test_linux_env/test_linux_env_readonly_env.py

"""
.env только для чтения на Linux (права POSIX) — замена пропущенных на Linux проверок
``tests/test_config/test_env_behavior.py`` (``test_readonly_env_does_not_crash``,
``test_readonly_env_missing_key_warns_and_uses_default``: там атрибут «только чтение» Windows).

Права — ``chmod 0o400`` (владелец только читает). Под root права не действуют (root пишет в любой
файл), поэтому тесты пропускаются при ``os.geteuid() == 0``. Изоляция от .env и config.msgpack
проекта — как в ``tests/test_config/conftest.py`` (свои фикстуры, не autouse).
"""

import os
import stat

import pytest

import app.config.conf.getenv as getenv_module
from app.config.conf.get_config import get_config_env
from app.config.conf.getenv import get_getenv

pytestmark = pytest.mark.skipif(
    os.name == 'nt' or (hasattr(os, 'geteuid') and os.geteuid() == 0),
    reason='права POSIX; под root (и на Windows) запись в файл «только для чтения» не блокируется',
)


@pytest.fixture
def env_file(tmp_path, monkeypatch):
    """Путь к .env в песочнице: текущая папка и папка .env — tmp_path, окружение процесса чистое."""
    saved_environ = dict(os.environ)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(getenv_module.ENV_DIR_VAR, str(tmp_path))
    for key in ('GITHUB_TOKEN', 'APP_CONFIG_PATH', 'NEW_KEY'):
        monkeypatch.delenv(key, raising=False)
    yield tmp_path / '.env'
    os.environ.clear()
    os.environ.update(saved_environ)


def _make_readonly(env_file) -> None:
    os.chmod(env_file, stat.S_IRUSR)   # 0o400


def _restore(env_file) -> None:
    os.chmod(env_file, stat.S_IRUSR | stat.S_IWUSR)   # чтобы pytest мог удалить tmp_path


def test_readonly_env_does_not_crash(env_file):
    """E2: раньше PermissionError при чтении конфига — приложение не запускалось (права 0o400)."""
    env_file.write_text("APP_CONFIG_PATH='config.msgpack'\nGITHUB_TOKEN=''\n", encoding='utf-8')
    _make_readonly(env_file)
    try:
        assert not os.access(env_file, os.W_OK)   # права сработали (иначе тест ничего не проверяет)
        assert get_config_env()['GITHUB_TOKEN'] == ''
    finally:
        _restore(env_file)


def test_readonly_env_missing_key_does_not_crash_and_returns_default(env_file, capsys):
    """E2: ключа нет, .env только для чтения (0o400) в доступной для записи папке — без падения.

    В отличие от Windows (атрибут «только чтение» не даёт заменить файл — предупреждение),
    на POSIX права файла не мешают: python-dotenv пишет во временный файл рядом и переименовывает
    его поверх .env, поэтому ключ дописывается без предупреждения, права 0o400 сохраняются.
    """
    env_file.write_text("APP_CONFIG_PATH='config.msgpack'\n", encoding='utf-8')
    _make_readonly(env_file)
    try:
        assert not os.access(env_file, os.W_OK)
        assert get_getenv('NEW_KEY', start_value='по умолчанию') == 'по умолчанию'
        assert stat.S_IMODE(os.stat(env_file).st_mode) == stat.S_IRUSR
    finally:
        _restore(env_file)
    assert capsys.readouterr().err == ''
    assert "NEW_KEY" in env_file.read_text(encoding='utf-8')


def test_readonly_env_in_readonly_dir_warns_and_uses_default(env_file, capsys):
    """E2: .env только для чтения В папке без права записи (как в Program Files) — предупреждение,
    значение по умолчанию, файл не тронут. Это аналог Windows-проверки «нельзя записать» на POSIX."""
    env_file.write_text("APP_CONFIG_PATH='config.msgpack'\n", encoding='utf-8')
    _make_readonly(env_file)
    folder = env_file.parent
    os.chmod(folder, stat.S_IRUSR | stat.S_IXUSR)
    try:
        assert not os.access(folder, os.W_OK)
        assert get_getenv('NEW_KEY', start_value='по умолчанию') == 'по умолчанию'
    finally:
        os.chmod(folder, stat.S_IRWXU)
        _restore(env_file)
    assert "не удалось записать 'NEW_KEY'" in capsys.readouterr().err
    assert env_file.read_text(encoding='utf-8') == "APP_CONFIG_PATH='config.msgpack'\n"


def test_readonly_env_existing_key_read_without_warning(env_file, capsys):
    """Ключ есть, .env только для чтения — значение читается из файла, предупреждений нет."""
    env_file.write_text("APP_CONFIG_PATH='my.msgpack'\n", encoding='utf-8')
    _make_readonly(env_file)
    try:
        assert get_getenv('APP_CONFIG_PATH', start_value='config.msgpack') == 'my.msgpack'
    finally:
        _restore(env_file)
    assert capsys.readouterr().err == ''


def test_unwritable_env_dir_does_not_crash(env_file, capsys):
    """Папка без права записи (0o500), .env нет: чтение ключа не падает, значение по умолчанию."""
    folder = env_file.parent
    os.chmod(folder, stat.S_IRUSR | stat.S_IXUSR)
    try:
        assert not os.access(folder, os.W_OK)
        assert get_getenv('NEW_KEY', start_value='d') == 'd'
    finally:
        os.chmod(folder, stat.S_IRWXU)
    assert "не удалось записать 'NEW_KEY'" in capsys.readouterr().err   # .env создать нельзя
    assert not env_file.exists()
