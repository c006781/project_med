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
