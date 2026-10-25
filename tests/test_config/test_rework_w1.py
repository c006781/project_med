# tests/test_config/test_rework_w1.py

"""
Тесты захода М6 переработки (2026-10-25): К6, M6, M16, E5, M17.

Номера — журнал ``app/config/IMPLEMENTATION.md`` §6 («Заход М6»). Каждый тест исправления
проверен на старом коде (падал).
"""

import logging
import os
import subprocess
import sys

import pytest


# Корень проекта (папка с пакетом app)
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _run_python(
    code     : str,   # текст программы
    tmp_path : str,   # временная папка для .env и config.msgpack
) -> subprocess.CompletedProcess:
    """
    Запускает код в отдельном («чистом») процессе Python с временными настройками.

    ``PROJECT_MED_ENV_DIR`` и ``APP_CONFIG_PATH`` — во временной папке: импорт ``app``
    не трогает рабочие ``.env`` и ``config.msgpack``.

    Args:
        code: Текст программы.
        tmp_path: Временная папка.

    Returns:
        Результат ``subprocess.run`` (``stdout``, ``stderr``, ``returncode``).

    Пример:
        >>> _run_python('print(1)', str(tmp_path)).stdout.strip()
        '1'
    """
    env = dict(os.environ)
    env['PROJECT_MED_ENV_DIR'] = str(tmp_path)
    env['APP_CONFIG_PATH'] = os.path.join(
        str(tmp_path),       # временная папка
        'config.msgpack',    # файл настроек
    )
    env['PYTHONPATH'] = ROOT
    env['PYTHONIOENCODING'] = 'utf-8'
    return subprocess.run(
        [sys.executable, '-c', code],   # программа
        cwd            = str(tmp_path),  # текущая папка — временная
        env            = env,            # временные настройки
        capture_output = True,           # вывод — в результат
        text           = True,           # строки, а не байты
        encoding       = 'utf-8',        # вывод программы — utf-8
        timeout        = 120,            # страховка от зависания
    )


# ---------------------------------------------------------------------------
# К6: app.config не импортирует app.dependencies
# ---------------------------------------------------------------------------

def test_k6_config_package_does_not_import_dependencies(tmp_path):
    """К6: импорт всех модулей ``app.config`` в чистом процессе не тянет ``app.dependencies``.

    До 2026-10-25 ``config_applier`` импортировал ``app.dependencies`` (связь «снизу вверх»:
    настройки → сборка приложения → сервисы → база).
    """
    code = (
        "import sys\n"
        "import app.config, app.config.conf, app.config.config_manager\n"
        "import app.config.config_applier, app.config.logging_setup\n"
        "print('app.dependencies' in sys.modules, 'app.services' in sys.modules)\n"
    )
    result = _run_python(code, str(tmp_path))
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().splitlines()[-1] == 'False False'


def test_k6_applier_uses_passed_hooks():
    """К6: блоки database / photos / sync работают через переданные обработчики сервисов."""
    from app.config.config_applier import ConfigApplier, ServiceHooks

    reloaded, photo, sync = [], type('P', (), {})(), type('Y', (), {})()
    photo._ensure_storage_exists = lambda: None
    service = type('S', (), {'reload_config': lambda self: reloaded.append(1)})()
    hooks = ServiceHooks(
        service_providers = lambda: [lambda: service],   # один поставщик
        photo_service     = lambda: photo,               # сервис фото
        sync_service      = lambda: sync,                # сервис синхронизации
    )
    a = ConfigApplier.__new__(ConfigApplier)
    a.logger = logging.getLogger('test.applier')
    a.services = hooks

    old = {'database_local_path': 'a.db', 'PHOTOS_STORAGE_PATH': 'p1', 'YANDEX_TOKEN': 't1'}
    new = {'database_local_path': 'b.db', 'PHOTOS_STORAGE_PATH': 'p2', 'YANDEX_TOKEN': 't2'}
    assert a.apply_changes(old, new) == {'database', 'photos', 'sync'}
    assert a.errors == {}
    assert reloaded == [1]
    assert photo._storage_path == 'p2'
    assert (sync.token, sync.local_path) == ('t2', 'b.db')


def test_k6_applier_without_hooks_reports_error():
    """К6: без обработчиков сервисов блоки, которым они нужны, — в ``errors`` (не молча)."""
    from app.config.config_applier import ConfigApplier

    a = ConfigApplier.__new__(ConfigApplier)
    a.logger = logging.getLogger('test.applier')
    a.apply_changes({'database_local_path': 'a.db'}, {'database_local_path': 'b.db'})
    assert set(a.errors) == {'database', 'sync'}
    assert 'обработчики сервисов' in str(a.errors['database'])


def test_k6_dependencies_creates_applier_with_hooks():
    """К6: ``app.dependencies.create_config_applier`` отдаёт обработчики сервисов приложения."""
    import app.dependencies as deps

    applier = deps.create_config_applier()
    assert applier.services.photo_service is deps.get_photo_service
    assert applier.services.sync_service is deps.get_sync_service
    assert list(applier.services.service_providers()) == list(deps._SERVICE_PROVIDERS)


@pytest.mark.parametrize(
    'rel',
    [
        'interfaces/gui/gui_window/pages/settings_page.py',
        'interfaces/cli/cli.py',
    ],
)
def test_k6_callers_use_dependencies_factory(rel):
    """К6: экран настроек и CLI создают применитель через ``create_config_applier()``."""
    text = open(
        os.path.join(ROOT, rel),   # файл вызывающего
        encoding = 'utf-8',
    ).read()
    code = '\n'.join(line for line in text.splitlines() if not line.strip().startswith('#'))
    assert 'create_config_applier()' in code
    assert 'ConfigApplier()' not in code


# ---------------------------------------------------------------------------
# M16: один экземпляр менеджера на файл, как бы ни был записан путь
# ---------------------------------------------------------------------------

def test_m16_same_file_different_spelling_one_instance(config_sandbox):
    """M16: ``config.msgpack``, ``./config.msgpack`` и абсолютный путь — один экземпляр.

    До 2026-10-25 ключ реестра — путь как передан: разные написания одного файла давали
    разные менеджеры, правки одного не видны другому.
    """
    from app.config.config_manager.manager import AppConfigManager

    a = AppConfigManager.get_instance(config_path='config.msgpack')
    assert AppConfigManager.get_instance(config_path=os.path.join('.', 'config.msgpack')) is a
    assert AppConfigManager.get_instance(config_path=str(config_sandbox / 'config.msgpack')) is a
    assert AppConfigManager.get_instance(config_path=os.path.join('sub', '..', 'config.msgpack')) is a


@pytest.mark.skipif(os.name != 'nt', reason='регистр имён не важен только на Windows')
def test_m16_case_insensitive_on_windows(config_sandbox):
    """M16: на Windows ``CONFIG.msgpack`` — тот же файл, что ``config.msgpack``."""
    from app.config.config_manager.manager import AppConfigManager

    a = AppConfigManager.get_instance(config_path='config.msgpack')
    assert AppConfigManager.get_instance(config_path='CONFIG.MSGPACK') is a


def test_m16_force_new_replaces_registered_instance(config_sandbox):
    """M16: ``force_new`` с другим написанием пути заменяет тот же экземпляр в реестре."""
    from app.config.config_manager.manager import AppConfigManager

    a = AppConfigManager.get_instance(config_path='config.msgpack')
    b = AppConfigManager.get_instance(
        config_path = os.path.join('.', 'config.msgpack'),   # другое написание
        force_new   = True,                                  # новый экземпляр
    )
    assert b is not a
    assert AppConfigManager.get_instance(config_path='config.msgpack') is b
    assert len(AppConfigManager._instances) == 1


# ---------------------------------------------------------------------------
# E5: чтение .env не загружает его ключи в os.environ
# ---------------------------------------------------------------------------

def test_e5_save_env_file_does_not_load_other_keys(env_file):
    """E5: запись ключа не загружает в os.environ остальные ключи .env."""
    from app.config.conf.getenv import save_env_file

    env_file.write_text("OTHER_SECRET=42\n", encoding='utf-8')
    save_env_file(
        {'NEW_KEY': 'v'},                # новый ключ
        dotenv_path = str(env_file),     # .env песочницы
    )
    assert os.environ['NEW_KEY'] == 'v'
    assert 'OTHER_SECRET' not in os.environ


def test_e5_save_env_file_sees_key_in_file_without_environ(env_file):
    """E5: ключ, который уже есть в файле (а в os.environ нет), без if_update не перезаписывается."""
    from app.config.conf.getenv import save_env_file

    env_file.write_text("K='old'\n", encoding='utf-8')
    save_env_file(
        {'K': 'new'},                    # ключ уже есть в файле
        dotenv_path = str(env_file),     # .env песочницы
    )
    assert "'old'" in env_file.read_text(encoding='utf-8')
    assert 'K' not in os.environ


def test_e5_environment_wins_even_if_empty(env_file, monkeypatch):
    """E5: пустая переменная окружения главнее файла (как с load_dotenv без override)."""
    from app.config.conf.getenv import get_getenv

    env_file.write_text("APP_CONFIG_PATH='from_file.msgpack'\n", encoding='utf-8')
    monkeypatch.setenv('APP_CONFIG_PATH', '')
    assert get_getenv('APP_CONFIG_PATH', start_value='default.msgpack') == 'default.msgpack'


def test_e5_environment_wins_for_config_manager(env_file, monkeypatch, tmp_path):
    """E5: ``APP_CONFIG_PATH`` из окружения главнее ``.env`` и для менеджера конфига."""
    from app.config.config_manager.manager import AppConfigManager

    env_file.write_text("APP_CONFIG_PATH='from_file.msgpack'\nGITHUB_TOKEN='t'\n", encoding='utf-8')
    monkeypatch.setenv('APP_CONFIG_PATH', 'from_env.msgpack')
    assert AppConfigManager.get_instance()._config_path == 'from_env.msgpack'
    assert 'GITHUB_TOKEN' not in os.environ


def test_e5_unreadable_env_does_not_crash(env_file, monkeypatch, capsys):
    """E5: .env есть, но не читается (заблокирован) — значение по умолчанию и предупреждение."""
    import app.config.conf.getenv as getenv_module
    from app.config.conf.getenv import get_getenv

    env_file.write_text("APP_CONFIG_PATH='a.msgpack'\n", encoding='utf-8')

    def boom(*args, **kwargs):
        raise PermissionError(13, 'файл заблокирован')

    monkeypatch.setattr(getenv_module, 'dotenv_values', boom)
    assert get_getenv('APP_CONFIG_PATH', start_value='config.msgpack') == 'config.msgpack'
    assert 'не удалось прочитать' in capsys.readouterr().err


# ---------------------------------------------------------------------------
# M6: умолчания правильных типов; старые строковые значения читаются без потерь
# ---------------------------------------------------------------------------

# Ключи с типами (bool / int) и их строковые значения из старых config.msgpack
OLD_STRING_VALUES = {
    'LOG_MAX_BYTES'          : ('10485760', 10485760),
    'LOG_BACKUP_COUNT'       : ('5', 5),
    'LOG_ARGS'               : ('False', False),
    'system_enabled'         : ('True', True),
    'system_console_enabled' : ('False', False),
    'system_file_enabled'    : ('true', True),
    'user_enabled'           : ('False', False),
    'user_console_enabled'   : ('1', True),
    'user_file_enabled'      : ('no', False),
    'enabled'                : ('True', True),
    'console_enabled'        : ('False', False),
    'file_enabled'           : ('True', True),
    'use_timestamp'          : ('False', False),
    'show_call_depth'        : ('True', True),
}


def _write_msgpack(
    path : str,              # путь к файлу
    data : dict,             # содержимое
) -> None:
    """
    Пишет словарь в файл MessagePack (как старый ``config.msgpack``).

    Args:
        path: Путь к файлу.
        data: Содержимое.

    Returns:
        None

    Пример:
        >>> _write_msgpack('config.msgpack', {'LOG_ARGS': 'False'})
    """
    import msgpack
    with open(path, 'wb') as f:
        msgpack.pack(data, f)


def test_m6_defaults_have_proper_types(config_sandbox):
    """M6: умолчания флагов — bool, чисел — int (до 2026-10-25 — строки 'False', '10485760')."""
    from app.config.config_manager.manager import AppConfigManager

    m = AppConfigManager.get_instance(config_path=str(config_sandbox / 'config.msgpack'))
    for key, (_, typed) in OLD_STRING_VALUES.items():
        assert type(m.get(key)) is type(typed), key
    assert m.get('LOG_MAX_BYTES') == 10 * 1024 * 1024
    assert m.get('LOG_BACKUP_COUNT') == 5
    assert m.get('enabled') is True and m.get('system_enabled') is False


def test_m6_old_string_values_read_without_loss(config_sandbox):
    """M6: старый ``config.msgpack`` со строковыми значениями читается: строки → bool / int."""
    from app.config.config_manager.manager import AppConfigManager

    path = str(config_sandbox / 'config.msgpack')
    old = {key: text for key, (text, _) in OLD_STRING_VALUES.items()}
    old.update({'LOG_LEVEL': 'DEBUG', 'YANDEX_TOKEN': 'tok', 'CUSTOM': 'False'})
    _write_msgpack(path, old)

    m = AppConfigManager.get_instance(config_path=path)
    for key, (_, typed) in OLD_STRING_VALUES.items():
        assert m.get(key) == typed and type(m.get(key)) is type(typed), key
    assert m.get('LOG_LEVEL') == 'DEBUG'          # строковые настройки — как есть
    assert m.get('YANDEX_TOKEN') == 'tok'
    assert m.get('CUSTOM') == 'False'             # неизвестный ключ не трогается
    assert m.broken_config_message is None


def test_m6_unparseable_string_kept_as_is(config_sandbox):
    """M6: строка, которую не перевести в тип умолчания, остаётся как есть (без потерь)."""
    from app.config.config_manager.manager import AppConfigManager

    path = str(config_sandbox / 'config.msgpack')
    _write_msgpack(path, {'LOG_MAX_BYTES': '10 МБ', 'use_timestamp': 'on'})

    m = AppConfigManager.get_instance(config_path=path)
    assert m.get('LOG_MAX_BYTES') == '10 МБ'
    assert m.get('use_timestamp') == 'on'


def test_m6_old_file_not_rewritten_on_read(config_sandbox):
    """M6: чтение старого файла его не переписывает (типы — в памяти; в файл — при save())."""
    import msgpack
    from app.config.config_manager.manager import AppConfigManager

    path = str(config_sandbox / 'config.msgpack')
    _write_msgpack(path, {'LOG_ARGS': 'False'})
    AppConfigManager.get_instance(config_path=path)
    with open(path, 'rb') as f:
        assert msgpack.unpack(f) == {'LOG_ARGS': 'False'}


def test_m6_typed_values_after_save_reload(config_sandbox):
    """M6: после save() и повторного чтения значения — тех же типов."""
    from app.config.config_manager.manager import AppConfigManager

    path = str(config_sandbox / 'config.msgpack')
    _write_msgpack(path, {'LOG_BACKUP_COUNT': '7', 'LOG_ARGS': 'True'})
    AppConfigManager.get_instance(config_path=path).save()
    again = AppConfigManager.get_instance(
        config_path = path,     # тот же файл
        force_new   = True,     # перечитать
    )
    assert again.get('LOG_BACKUP_COUNT') == 7
    assert again.get('LOG_ARGS') is True


def test_m6_settings_snapshot_no_false_logging_change(config_sandbox):
    """M6: старый файл со строками + экран сохраняет те же значения bool/int — блоки не «меняются».

    До 2026-10-25 'False' (файл) и False (экран) считались разными — логирование
    перенастраивалось при каждом первом сохранении настроек.
    """
    from app.config.config_applier import ConfigApplier
    from app.config.config_manager.manager import AppConfigManager

    path = str(config_sandbox / 'config.msgpack')
    _write_msgpack(path, {'system_enabled': 'False', 'LOG_MAX_BYTES': '10485760'})
    m = AppConfigManager.get_instance(config_path=path)
    old = m.get_all()
    m.set('system_enabled', False)                # как экран настроек: bool
    m.set('LOG_MAX_BYTES', 10485760)              # как экран настроек: int
    assert ConfigApplier.get_changed_blocks(old, m.get_all()) == set()


def test_m6_logger_config_same_for_strings_and_types():
    """M6: логгер понимает и строки, и типы — настройки логгера одинаковые."""
    from app.utils.logger.logger import AppLogger

    strings = {key: text for key, (text, _) in OLD_STRING_VALUES.items()}
    typed = {key: value for key, (_, value) in OLD_STRING_VALUES.items()}
    log = AppLogger.get_instance('test.m6.types')
    from_strings = log._get_config_with_inheritance(
        AppLogger.build_logger_config(strings),   # старый файл
        None,
        None,
    )
    from_typed = log._get_config_with_inheritance(
        AppLogger.build_logger_config(typed),     # новые типы
        None,
        None,
    )
    assert from_strings == from_typed
