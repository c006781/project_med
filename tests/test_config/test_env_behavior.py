# tests/test_config/test_env_behavior.py

"""
Поведение уровня .env (app/config/conf) «как есть» перед рефакторингом.

Известные проблемы — xfail(strict=True) с описанием желаемого поведения
(номера — app/config/IMPLEMENTATION.md §3.1).
"""

import os
import stat

import pytest

import app.config.conf.getenv as getenv_module
from app.config.conf.get_config import get_config_env as old_get_config_env
from app.config.conf.getenv import get_dotenv_path, get_getenv, save_env_file


def _write_env(env_file, text):
    env_file.write_text(text, encoding='utf-8')


# ---------------------------------------------------------------------------
# get_getenv
# ---------------------------------------------------------------------------

def test_existing_value_returned_without_write(env_file, set_key_calls):
    _write_env(env_file, "APP_CONFIG_PATH='my.msgpack'\n")
    assert get_getenv('APP_CONFIG_PATH', start_value='config.msgpack') == 'my.msgpack'
    assert set_key_calls == []


def test_missing_key_written_with_start_value(env_file, set_key_calls):
    _write_env(env_file, '')
    assert get_getenv('NEW_KEY', start_value='значение') == 'значение'
    assert len(set_key_calls) == 1
    assert 'NEW_KEY' in env_file.read_text(encoding='utf-8')


def test_missing_key_without_start_value_raises(env_file):
    _write_env(env_file, '')
    with pytest.raises(ValueError, match='NEW_KEY is required'):
        get_getenv('NEW_KEY')


def test_missing_env_file_is_created(config_sandbox):
    """E4: чтение создаёт .env в текущей папке, если его нет."""
    assert not (config_sandbox / '.env').exists()
    get_getenv('ANY', start_value='x')
    assert (config_sandbox / '.env').exists()


def test_empty_value_does_not_rewrite_env(env_file, set_key_calls):
    """E1: ключ с пустым значением есть в файле — .env не переписывается.

    До 2026-10-14 переписывался при каждом чтении (17 раз за старт GUI).
    """
    _write_env(env_file, "GITHUB_TOKEN=''\n")
    for _ in range(3):
        assert get_getenv('GITHUB_TOKEN', start_value='') == ''
    assert set_key_calls == []


def test_empty_value_returns_start_value(env_file, set_key_calls):
    """Пустое значение по-прежнему означает «взять значение по умолчанию» (без записи)."""
    _write_env(env_file, "APP_CONFIG_PATH=''\n")
    assert get_getenv('APP_CONFIG_PATH', start_value='config.msgpack') == 'config.msgpack'
    assert set_key_calls == []


def test_empty_process_env_var_but_missing_in_file_is_written(env_file, set_key_calls, monkeypatch):
    """Ключа нет в файле, а в окружении процесса он пустой — дописывается значение по умолчанию."""
    _write_env(env_file, '')
    monkeypatch.setenv('SOME_KEY', '')
    assert get_getenv('SOME_KEY', start_value='d') == 'd'
    assert [k for _, k, _ in set_key_calls] == ['SOME_KEY']


@pytest.mark.skipif(os.name != 'nt', reason='атрибут «только чтение» проверяется на Windows')
def test_readonly_env_does_not_crash(env_file):
    """E2: раньше PermissionError при чтении конфига — приложение не запускалось."""
    _write_env(env_file, "APP_CONFIG_PATH='config.msgpack'\nGITHUB_TOKEN=''\n")
    os.chmod(env_file, stat.S_IREAD)
    try:
        assert old_get_config_env()['GITHUB_TOKEN'] == ''
    finally:
        os.chmod(env_file, stat.S_IREAD | stat.S_IWRITE)


@pytest.mark.skipif(os.name != 'nt', reason='атрибут «только чтение» проверяется на Windows')
def test_readonly_env_missing_key_warns_and_uses_default(env_file, capsys):
    """E2: ключа нет, .env только для чтения — предупреждение, значение по умолчанию, без падения."""
    _write_env(env_file, "APP_CONFIG_PATH='config.msgpack'\n")
    os.chmod(env_file, stat.S_IREAD)
    try:
        assert get_getenv('NEW_KEY', start_value='по умолчанию') == 'по умолчанию'
    finally:
        os.chmod(env_file, stat.S_IREAD | stat.S_IWRITE)
    err = capsys.readouterr().err
    assert "не удалось записать 'NEW_KEY'" in err


def test_unwritable_env_dir_does_not_crash(config_sandbox, monkeypatch, capsys):
    """E2: .env нельзя создать (нет прав на папку) — чтение не падает."""
    import builtins
    real_open = builtins.open

    def deny(path, mode='r', *a, **k):
        if str(path).endswith('.env') and 'w' in mode:
            raise PermissionError('нет прав')
        return real_open(path, mode, *a, **k)

    monkeypatch.setattr(builtins, 'open', deny)
    assert get_getenv('ANY', start_value='x') == 'x'
    assert 'не удалось создать' in capsys.readouterr().err


def test_values_loaded_into_os_environ(env_file):
    """E5: load_dotenv кладёт в os.environ все ключи .env, а не только запрошенный."""
    _write_env(env_file, "APP_CONFIG_PATH='a.msgpack'\nOTHER_SECRET=42\n")
    get_getenv('APP_CONFIG_PATH', start_value='x')
    assert os.environ.get('OTHER_SECRET') == '42'


def test_environment_variable_wins_over_env_file(env_file, monkeypatch):
    """load_dotenv не переопределяет уже заданные переменные окружения."""
    _write_env(env_file, "APP_CONFIG_PATH='from_file.msgpack'\n")
    monkeypatch.setenv('APP_CONFIG_PATH', 'from_env.msgpack')
    assert get_getenv('APP_CONFIG_PATH', start_value='x') == 'from_env.msgpack'


# ---------------------------------------------------------------------------
# get_dotenv_path / save_env_file
# ---------------------------------------------------------------------------

# def test_get_dotenv_path_falls_back_to_cwd_name(config_sandbox):
#     assert get_dotenv_path() == '.env'
#     assert get_dotenv_path('custom.env') == 'custom.env'
# ↑ до E3 (2026-10-15): без найденного .env возвращалось относительное имя (текущая папка).

def test_get_dotenv_path_in_env_dir(config_sandbox):
    """E3: .env — в папке из PROJECT_MED_ENV_DIR (песочница задаёт tmp_path)."""
    assert get_dotenv_path() == os.path.join(str(config_sandbox), '.env')
    assert get_dotenv_path('custom.env') == os.path.join(str(config_sandbox), 'custom.env')


# def test_real_find_dotenv_searches_from_module_dir(monkeypatch):
#     """E3: настоящий find_dotenv ищет от папки МОДУЛЯ вверх — находит .env проекта,
#     даже когда текущая папка другая (здесь — tmp_path без .env)."""
#     ...
# ↑ характеризовал проблему E3 (поиск от папки модуля вверх); с E3 find_dotenv не
#   используется — новые проверки в test_env_location.py.


def test_save_env_file_keeps_existing_without_update(env_file):
    _write_env(env_file, "K='old'\n")
    save_env_file({'K': 'new'}, dotenv_path=str(env_file))
    assert "'old'" in env_file.read_text(encoding='utf-8')


def test_save_env_file_update_overwrites(env_file):
    _write_env(env_file, "K='old'\n")
    save_env_file({'K': 'new'}, dotenv_path=str(env_file), if_update=True)
    assert 'new' in env_file.read_text(encoding='utf-8')
    assert os.environ['K'] == 'new'


# ---------------------------------------------------------------------------
# get_config (старый уровень)
# ---------------------------------------------------------------------------

def test_old_get_config_env_defaults_written(env_file):
    """Пустой .env: оба ключа дописываются значениями по умолчанию."""
    _write_env(env_file, '')
    cfg = old_get_config_env()
    assert cfg == {'APP_CONFIG_PATH': 'config.msgpack', 'GITHUB_TOKEN': ''}
    text = env_file.read_text(encoding='utf-8')
    assert 'APP_CONFIG_PATH' in text and 'GITHUB_TOKEN' in text


def test_old_get_config_env_custom_default_path(env_file):
    _write_env(env_file, '')
    assert old_get_config_env('x/conf.msgpack')['APP_CONFIG_PATH'] == 'x/conf.msgpack'


def test_old_get_config_env_does_not_rewrite(env_file, set_key_calls):
    """E1: при пустом GITHUB_TOKEN .env больше не переписывается (раньше — на каждом вызове)."""
    _write_env(env_file, "APP_CONFIG_PATH='config.msgpack'\nGITHUB_TOKEN=''\n")
    old_get_config_env()
    old_get_config_env()
    assert set_key_calls == []
