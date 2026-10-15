# tests/test_config/conftest.py

"""
Изоляция тестов конфигурации от .env и config.msgpack проекта.

Для каждого теста (autouse):
    * текущая папка — tmp_path (относительные пути 'config.msgpack', '.env' — туда);
    * ``find_dotenv`` в ``app.config.conf.getenv`` ищет только ``tmp_path/.env``
      (настоящий ищет от папки модуля вверх и находит .env проекта — проблема E3);
    * ``os.environ`` восстанавливается после теста (``load_dotenv`` пишет туда всё
      содержимое .env — E5); заглушка GITHUB_TOKEN из корневого conftest убирается,
      чтобы тесты видели настоящее поведение;
    * реестр ``AppConfigManager._instances`` и слушатели ``_listeners`` — пустые свои.

Фикстура ``set_key_calls`` считает перезаписи .env.
"""

import os

import pytest

import app.config.conf.getenv as getenv_module
from app.config.config_manager.manager import AppConfigManager, BaseConfigManager


@pytest.fixture(autouse=True)
def config_sandbox(tmp_path, monkeypatch):
    saved_environ = dict(os.environ)
    monkeypatch.chdir(tmp_path)
    env_file = tmp_path / '.env'

    def fake_find_dotenv(*args, **kwargs):
        return str(env_file) if env_file.exists() else ''

    monkeypatch.setattr(getenv_module, 'find_dotenv', fake_find_dotenv)
    # ↑ до E3 изоляция шла через find_dotenv; оставлено на случай старых вызовов.
    # С E3 папку .env задаёт переменная окружения (см. getenv.get_dotenv_path):
    monkeypatch.setenv(getenv_module.ENV_DIR_VAR, str(tmp_path))
    for key in ('GITHUB_TOKEN', 'APP_CONFIG_PATH'):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(AppConfigManager, '_instances', {})
    monkeypatch.setattr(AppConfigManager, '_resolved_default_path', None)  # E6: путь запоминается
    monkeypatch.setattr(BaseConfigManager, '_listeners', [])

    yield tmp_path

    os.environ.clear()
    os.environ.update(saved_environ)


@pytest.fixture
def env_file(config_sandbox):
    """Путь к .env в песочнице (файл не создаётся)."""
    return config_sandbox / '.env'


@pytest.fixture
def set_key_calls(monkeypatch):
    """Список вызовов set_key (перезаписей .env): [(путь, ключ, значение), ...]."""
    calls = []
    real = getenv_module.set_key

    def spy(dotenv_path, key_to_set, value_to_set, *args, **kwargs):
        calls.append((dotenv_path, key_to_set, value_to_set))
        return real(dotenv_path, key_to_set, value_to_set, *args, **kwargs)

    monkeypatch.setattr(getenv_module, 'set_key', spy)
    return calls
