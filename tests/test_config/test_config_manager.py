import pytest
import os
import msgpack
from app.config.config_manager.manager import AppConfigManager, get_config_env

def test_config_manager_create(tmp_path):
    """ 
    Тест для создания нового экземпляра AppConfigManager.

    AppConfigManager.get_instance должен возвращать новый экземпляр
    AppConfigManager, если файл конфигурации не существует.
    Новый экземпляр должен иметь значения по умолчанию.
    """
    config_path = tmp_path / "config.msgpack"
    manager = AppConfigManager.get_instance(config_path=str(config_path), force_new=True)
    # Проверяем, что значения по умолчанию загружены
    assert manager.get('YANDEX_TOKEN') == '----'
    assert manager.get('database_local_path') == './clinic.db'

def test_config_manager_save_load(tmp_path):
    """
    Тест для методов save и __init__ в AppConfigManager.

    Метод save должен сохранять конфигурацию в файл, а метод __init__
    должен загрузить конфигурацию из файла.

    Мы создаем экземпляр AppConfigManager, изменяем значения конфигурации,
    сохраняем конфигурацию и создаем новый экземпляр AppConfigManager.
    Новый экземпляр должен загрузить значения конфигурации из файла.
    """
    config_path = tmp_path / "config.msgpack"
    manager = AppConfigManager.get_instance(config_path=str(config_path), force_new=True)
    # Изменяем значения конфигурации
    manager.set('YANDEX_TOKEN', 'new_token')
    manager.set('LOG_LEVEL', 'ERROR')
    # Сохраняем конфигурацию
    manager.save()

    # Новый экземпляр, который загрузит из файла
    manager2 = AppConfigManager.get_instance(config_path=str(config_path), force_new=True)
    # Проверяем, что значения были загружены из файла
    assert manager2.get('YANDEX_TOKEN') == 'new_token'
    assert manager2.get('LOG_LEVEL') == 'ERROR'

def test_config_manager_reset_to_defaults(tmp_path):
    """
    Тест для метода reset_to_defaults в AppConfigManager.

    Метод reset_to_defaults должен сбрасывать все значения конфигурации до значений по умолчанию.
    """
    config_path = tmp_path / "config.msgpack"
    manager = AppConfigManager.get_instance(config_path=str(config_path), force_new=True)
    
    # Изменяем значение конфигурации
    manager.set('YANDEX_TOKEN', 'changed')
    
    # Сбрасываем конфигурацию до значения по умолчанию
    manager.reset_to_defaults()
    
    # Проверяем, что значение было сброшено до значения по умолчанию
    assert manager.get('YANDEX_TOKEN') == '----'

def test_config_manager_multiton(tmp_path):
    """
    Тест для проверки работы паттерна Multiton в AppConfigManager.

    AppConfigManager должен возвращать разные экземпляры для разных путей к файлам конфигурации.
    Должен возвращать тот же экземпляр, если указан тот же путь к файлу,
    но с параметром force_new=False.
    """
    path1 = tmp_path / "cfg1.msgpack"
    path2 = tmp_path / "cfg2.msgpack"
    m1 = AppConfigManager.get_instance(config_path=str(path1), force_new=True)
    m2 = AppConfigManager.get_instance(config_path=str(path2), force_new=True)
    m3 = AppConfigManager.get_instance(config_path=str(path1), force_new=False)
    assert m1 is m3
    assert m1 is not m2

# def test_config_manager_corrupted_file(tmp_path, caplog):
#     config_path = tmp_path / "config.msgpack"
#     # Записываем мусор
#     config_path.write_bytes(b"not msgpack")
#     # При создании менеджера должна быть ошибка чтения, но он должен создать пустой с дефолтами
#     manager = AppConfigManager.get_instance(config_path=str(config_path), force_new=True)
#     # Проверим, что дефолты загружены
#     assert manager.get('YANDEX_TOKEN') == '----'
#     # Проверим, что было залогировано предупреждение (если логгер подключён)
#     # Но в BaseConfigManager нет логирования, поэтому просто проверяем, что исключение не вылетело

def test_config_manager_corrupted_file(tmp_path):
    """
    Тест для AppConfigManager, когда он создается с файлом конфигурации,
    который не является валидным файлом MessagePack.
    
    AppConfigManager должен выбрасывать исключение, если файл конфигурации
    не является валидным файлом MessagePack.
    """
    config_path = tmp_path / "config.msgpack"
    # Записываем мусор в файл конфигурации
    config_path.write_bytes(b"not msgpack")
    # Ожидаем, что при создании менеджера будет исключение
    with pytest.raises((msgpack.exceptions.ExtraData, msgpack.exceptions.UnpackException)):
        AppConfigManager.get_instance(config_path=str(config_path), force_new=True)



def test_get_config_env(tmp_path):
    """
    Тест для get_config_env, который должен возвращать словарь из
    конфигурации, если файл конфигурации существует.
    """
    # Создаём временный конфиг
    config_path = tmp_path / "config.msgpack"
    manager = AppConfigManager.get_instance(config_path=str(config_path), force_new=True)
    manager.set('YANDEX_TOKEN', 'env_token')
    manager.save()

    # Подменяем путь через мок, чтобы get_config_env взял этот файл
    # get_config_env просто вызывает get_instance без аргументов,
    # а get_instance берёт путь из старой функции get_config_env().
    # Поэтому нужно замокать get_instance, чтобы он возвращал наш менеджер.
    with pytest.MonkeyPatch.context() as mp:
        # Мокаем метод get_instance, чтобы он возвращал наш manager
        def mock_get_instance(*args, **kwargs):
            return manager
        mp.setattr(AppConfigManager, 'get_instance', mock_get_instance)
        config = get_config_env()
        # Проверяем, что get_config_env возвращает словарь из менеджера
        assert config['YANDEX_TOKEN'] == 'env_token'
