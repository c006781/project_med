# tests/test_main_window/test_main_window_startup.py
"""
Тесты запуска: настоящее окно и точки входа в подпроцессе на временных настройках, базе и журналах.

Точки входа сразу настраивают журналы, поэтому только подпроцесс с копией окружения тестов: иначе тест
писал бы в рабочие журналы и настройки. Сеть в подпроцессе запрещена на уровне сокетов
(``window_scenario.py``), каждая попытка записывается и проверяется здесь.
"""
import json
import os
import subprocess
import sys
from typing import Any, Dict, Optional

import msgpack

SCENARIO = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'window_scenario.py')


# сценарий в подпроцессе на временных путях
def _run(
    tmp_path : Any,                                 # временная папка
    scenario : str,                                 # имя сценария
    settings : Optional[Dict[str, Any]] = None,     # дополнительные настройки
    env      : Optional[Dict[str, str]] = None,     # дополнительное окружение
) -> Dict[str, Any]:
    """
    Запускает сценарий окна в подпроцессе и возвращает его итог.

    Args:
        tmp_path : (Path) Временная папка: настройки, база, фото, журналы, копии.
        scenario : (str) Имя сценария.
        settings : (dict/None) Дополнительные настройки.
        env      : (dict/None) Дополнительное окружение.

    Returns:
        (dict) Итог сценария; ``stdout`` — полный вывод.

    Example:
        >>> _run(tmp_path, 'start')['network']  # doctest: +SKIP
        []
    """
    work = str(tmp_path)
    data_dir = tmp_path / 'data'
    data_dir.mkdir(exist_ok=True)
    config = tmp_path / 'config.msgpack'
    with open(config, 'wb') as file:
        msgpack.pack(
            {
                'database_local_path' : str(data_dir / 'clinic.db'),    # временная база
                'PHOTOS_STORAGE_PATH' : str(tmp_path / 'photos'),       # временные фото
                'LOG_DIR'             : str(tmp_path / 'logs'),         # журналы
                'BACKUP_PATH'         : str(tmp_path / 'копии'),        # копии базы
                'YANDEX_TOKEN'        : 'токен-проверки',               # не настоящий
                **(settings or {}),
            },
            file,
        )
    process_env = {
        **os.environ,
        'APP_CONFIG_PATH'       : str(config),      # настройки
        'PROJECT_MED_ENV_DIR'   : work,             # .env
        'QT_QPA_PLATFORM'       : 'offscreen',      # без экрана
        **(env or {}),
    }
    completed = subprocess.run(
        [sys.executable, '-X', 'utf8', SCENARIO, scenario, work],   # команда
        cwd             =   work,                                   # не рабочая папка проекта
        env             =   process_env,                            # копия окружения тестов
        capture_output  =   True,                                   # вывод — в итог
        text            =   True,                                   # строки
        encoding        =   'utf-8',                                # кодировка
        timeout         =   120,                                    # зависание — падение теста
    )
    assert completed.returncode == 0, completed.stderr[-3000:]
    result = json.loads(completed.stdout.strip().splitlines()[-1])
    result['stdout'] = completed.stdout
    return result


def test_window_starts_without_network_when_env_set(tmp_path):
    """Окно стартует на временных настройках и базе; переменная выключает проверку; сети нет."""
    result = _run(tmp_path, 'start', env={'PROJECT_MED_NO_UPDATE_CHECK': '1'})
    assert result['network'] == []
    assert result['reachable'] == 0
    assert result['check'] == 0
    assert result['db_is_temp'] is True
    assert result['page'] == 'patient_list'
    assert result['closed'] is True


def test_window_setting_off_no_check(tmp_path):
    """Настройка выключена: таймер срабатывает, проверки нет, сети нет."""
    result = _run(tmp_path, 'start', settings={'UPDATE_CHECK_ON_START': False})
    assert result['network'] == []
    assert result['check'] == 0
    assert result['reachable'] == 0


def test_window_setting_on_checks_once_without_reachable(tmp_path):
    """Настройка включена: одна проверка через модуль (подменён), без запроса в потоке окна."""
    result = _run(tmp_path, 'start', settings={'UPDATE_CHECK_ON_START': True})
    assert result['network'] == []
    assert result['check'] == 1
    assert result['reachable'] == 0


def test_entry_point_runs(tmp_path):
    """Настоящая точка входа окна: без ошибок и сети."""
    result = _run(tmp_path, 'entry_point', env={'PROJECT_MED_NO_UPDATE_CHECK': '1'})
    assert result['code'] == 0
    assert result['network'] == []


def test_cli_help(tmp_path):
    """``main_cli.py --help`` — без ошибок и сети, с описанием команд."""
    result = _run(tmp_path, 'cli_help')
    assert result['code'] == 0
    assert result['network'] == []
    assert 'sync' in result['stdout'].lower()


def test_broken_download_then_replace_on_real_window(tmp_path):
    """Готово: обрыв не портит рабочую базу, старая в копии; успех заменяет базу на ходу."""
    result = _run(tmp_path, 'db_replace')
    assert result['network'] == []
    assert result['after_break'] == ['Локальный']
    assert result['break_files'] == ['clinic.db']
    assert result['break_title'] == 'База не скачана'
    assert result['break_backups'] == 1
    assert result['after_replace'] == ['СДиска']
    assert result['in_copy'] == ['Локальный']
    assert result['backups'] == 2
    assert 'СДиска' in result['table_text']
    assert 'Локальный' not in result['table_text']
    assert 'clinic.db' in result['files']
    assert not [name for name in result['files'] if name.endswith('.part')]
    assert result['closed'] is True


def test_downloaded_db_too_new_keeps_old(tmp_path):
    """Скачанная база новее программы: прежняя возвращена и записывает дальше."""
    result = _run(tmp_path, 'db_newer_revision')
    assert result['network'] == []
    assert 'База не заменена' in result['titles']
    assert result['patients'] == ['Локальный', 'ПослеОтката']
    assert not [name for name in result['files'] if name.endswith('.part')]
    assert result['closed'] is True
