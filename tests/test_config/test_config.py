# tests/test_config.py
import pytest
import os
from app.config.conf.getenv import get_getenv, save_env_file, crete_env_file, get_dotenv_path
# from app.controllers.conf.get_config import get_config_env
from app.config.config_manager.manager import get_config_env
def test_get_dotenv_path_default():
    """
    Проверка поведения функции get_dotenv_path() в случае, когда не передается аргументов.
    Функция должна возвращать путь к файлу .env в текущей директории или стандартный путь к файлу .env.
    """
    path = get_dotenv_path()
    assert path == '.env' or path.endswith('.env')

def test_crete_env_file(tmp_path):
    """
    Тест для функции crete_env_file.

    Функция crete_env_file должна создавать файл .env в указанной директории, если он не существует.
    """
    env_file = tmp_path / '.env'
    # Создаем файл .env, если его нет
    crete_env_file(str(env_file))
    # Проверяем, что файл существует
    assert env_file.exists()

def test_save_env_file(tmp_path):
    """
    Тест для функции save_env_file.

    Функция save_env_file должна записывать новые ключи в файл .env, если он существует.
    Если файл не существует, то функция должна создать его и записать новые ключи.
    """
    env_file = tmp_path / '.env'
    # Создаем файл .env, если его нет
    env_file.write_text("EXISTING=old\n")
    # Параметры для функции save_env_file
    env_key = {'NEW_KEY': 'value'}
    env_path = str(env_file)
    # Вызываем функцию save_env_file
    save_env_file(env_key, env_path)
    # Читаем содержимое файла
    content = env_file.read_text()
    # Проверяем, что ключ присутствует, игнорируя возможные кавычки
    assert "NEW_KEY=" in content
    assert "value" in content  # можно проверить наличие подстроки value

def test_get_getenv_with_start_value(tmp_path, monkeypatch):
    """
    Тест для функции get_getenv(), когда передается start_value.

    Функция get_getenv() должна возвращать значение переменной окружения, если она существует.
    Если переменной окружения нет, то функция должна возвращать start_value.
    """

    # Создаем файл .env, если его нет
    env_file = tmp_path / '.env'
    env_file.write_text("")

    # Удаляем пустую переменную окружения
    monkeypatch.setenv('TEST_KEY', '')  

    # Вызываем функцию get_getenv() с start_value
    value = get_getenv('TEST_KEY', start_value='default', dotenv_path=str(env_file))

    # Проверяем, что функция вернула start_value
    assert value == 'default'

    # Читаем содержимое файла
    content = env_file.read_text()

    # Проверяем, что TEST_KEY присутствует в файле
    assert "TEST_KEY=" in content

    # Проверяем, что value присутствует в файле
    assert "default" in content



def test_get_config_env(monkeypatch, tmp_path):
    """
    Тест для AppConfigManager, когда он получает путь к файлу конфигурации.

    AppConfigManager должен создать файл конфигурации, если его нет.
    Он должен корректно читать значения из файла конфигурации.
    """

    import msgpack
    msgpack_file = tmp_path / 'test_config.msgpack'

    # Создаём msgpack с нужным значением
    config_data = {'database_local_path': './test.db'}
    with open(msgpack_file, 'wb') as f:
        msgpack.pack(config_data, f)

    from app.config.config_manager.manager import AppConfigManager
    # Очищаем словарь экземпляров, чтобы не было конфликтов
    # между тестами
    AppConfigManager._instances.clear()

    # Создаём менеджер с явным путём
    manager = AppConfigManager.get_instance(config_path=str(msgpack_file), force_new=True)

    # Проверяем, что файл конфигурации существует
    assert manager.config_exists, "Файл конфигурации не найден"
    # Проверяем, что значение из файла конфигурации было прочитано
    assert manager.get('database_local_path') == './test.db'

def test_config_manager_uses_env_path(monkeypatch, tmp_path):
    """
    Тест для AppConfigManager, когда он использует путь к файлу конфигурации из .env.

    AppConfigManager должен использовать путь к файлу конфигурации из .env,
    если он не является None. AppConfigManager должен создать файл конфигурации,
    если его нет. Он должен корректно читать значения из файла конфигурации.
    """
    import msgpack
    msgpack_file = tmp_path / 'test_config.msgpack'

    # Подменяем _old_get_config_env, чтобы она возвращала путь к нашему msgpack-файлу
    def mock_old_get_config_env():
        """
        Мок для _old_get_config_env, который возвращает путь к нашему msgpack-файлу.
        """
        return {'APP_CONFIG_PATH': str(msgpack_file)}

    # Подменяем _old_get_config_env
    monkeypatch.setattr('app.config.config_manager.manager._old_get_config_env', mock_old_get_config_env)

    # Создаём msgpack-файл с тестовыми данными
    with open(msgpack_file, 'wb') as f:
        msgpack.pack({'database_local_path': './test.db'}, f)

    from app.config.config_manager.manager import AppConfigManager
    # Очищаем словарь экземпляров, чтобы не было конфликтов
    # между тестами
    AppConfigManager._instances.clear()

    # Создаём менеджер
    manager = AppConfigManager.get_instance()

    # Проверяем, что путь к файлу конфигурации равен пути к нашему msgpack-файлу
    assert manager._config_path == str(msgpack_file)
    # Проверяем, что файл конфигурации существует
    # assert manager.config_exists
    assert manager.config_exists, "Файл конфигурации не найден"
    # Проверяем, что значение из файла конфигурации было прочитано
    assert manager.get('database_local_path') == './test.db'
