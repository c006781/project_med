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
