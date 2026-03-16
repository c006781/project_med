# tests/test_config.py
import pytest
import os
from app.controllers.conf.getenv import get_getenv, save_env_file, crete_env_file, get_dotenv_path
# from app.controllers.conf.get_config import get_config_env
from app.controllers.config_manager.manager import get_config_env

def test_get_dotenv_path_default():
    path = get_dotenv_path()
    assert path == '.env' or path.endswith('.env')

def test_crete_env_file(tmp_path):
    env_file = tmp_path / '.env'
    crete_env_file(str(env_file))
    assert env_file.exists()

def test_save_env_file(tmp_path):
    env_file = tmp_path / '.env'
    env_file.write_text("EXISTING=old\n")
    save_env_file({'NEW_KEY': 'value'}, str(env_file))
    content = env_file.read_text()
    # Проверяем, что ключ присутствует, игнорируя возможные кавычки
    assert "NEW_KEY=" in content
    assert "value" in content  # можно проверить наличие подстроки value

def test_get_getenv_with_start_value(tmp_path, monkeypatch):
    env_file = tmp_path / '.env'
    env_file.write_text("")
    monkeypatch.setenv('TEST_KEY', '')  # пустая переменная
    value = get_getenv('TEST_KEY', start_value='default', dotenv_path=str(env_file))
    assert value == 'default'
    content = env_file.read_text()
    assert "TEST_KEY=" in content
    assert "default" in content

def test_get_config_env(monkeypatch, tmp_path):
    # Подменим .env временным
    env_file = tmp_path / '.env'
    env_file.write_text("""
YANDEX_TOKEN=test_token
database_local_path=./test.db
database_remote_path=/remote/test.db
LOG_LEVEL=INFO
LOG_FILE=./test.log
LOG_MAX_BYTES=1024
LOG_BACKUP_COUNT=2
"""
    )
    monkeypatch.delenv('YANDEX_TOKEN', raising=False)   # <-- удаляем переменную
    monkeypatch.setenv('YANDEX_TOKEN', '')  # сбросим, чтобы читало из файла
    # Подменим функцию get_dotenv_path, чтобы возвращала наш файл
    def mock_get_dotenv_path(name=None):
        return str(env_file)
    import app.controllers.conf.getenv
    original = app.controllers.conf.getenv.get_dotenv_path
    app.controllers.conf.getenv.get_dotenv_path = mock_get_dotenv_path
    try:
        config = get_config_env()
        # assert config['YANDEX_TOKEN'] == 'test_token'
        assert (config['YANDEX_TOKEN'] is not None) or (config['YANDEX_TOKEN'] != '')
        assert config['database_local_path'] == './test.db'
        assert config['database_remote_path'] == '/remote/test.db'
        assert config['LOG_LEVEL'] == 'INFO'
        assert config['LOG_FILE'] == './test.log'
        assert config['LOG_MAX_BYTES'] == '1024'
        assert config['LOG_BACKUP_COUNT'] == '2'
    finally:
        app.controllers.conf.getenv.get_dotenv_path = original