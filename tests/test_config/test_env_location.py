# tests/test_config/test_env_location.py

"""
Где лежит .env (E3, решение владельца 2026-10-15).

Правило: ``$PROJECT_MED_ENV_DIR`` → папка собранной программы (exe/бинарник) → папка
запущенного скрипта (``__main__``) → текущая папка. Вверх по папкам не ищется.
Одинаково для Windows и Linux; модуль, запущенный напрямую для отладки, получает свой
.env рядом с собой, а не боевой.
"""

import os
import subprocess
import sys
import types

import pytest

import app.config.conf.getenv as getenv_module
from app.config.conf.getenv import ENV_DIR_VAR, get_dotenv_path, get_launch_dir

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def no_env_dir(monkeypatch):
    """Без переопределения папки — проверяем само правило «папка запуска»."""
    monkeypatch.delenv(ENV_DIR_VAR, raising=False)


def _fake_main(monkeypatch, file):
    """Подменяет модуль __main__ (file=None — интерактивный режим без файла)."""
    main = types.ModuleType('__main__')
    if file is not None:
        main.__file__ = file
    monkeypatch.setitem(sys.modules, '__main__', main)


def test_frozen_uses_executable_dir(no_env_dir, monkeypatch, tmp_path):
    """Собранная программа: папка exe — не текущая папка и не «рабочая папка» ярлыка."""
    exe = tmp_path / 'Clinic' / ('MedicalApp.exe' if os.name == 'nt' else 'MedicalApp')
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, 'executable', str(exe))
    monkeypatch.chdir(tmp_path)                        # ярлык с другой рабочей папкой
    assert get_launch_dir() == str(tmp_path / 'Clinic')
    assert get_dotenv_path() == os.path.join(str(tmp_path / 'Clinic'), '.env')


def test_main_script_dir(no_env_dir, monkeypatch, tmp_path):
    """Главный старт (main_gui_window.py): папка скрипта, независимо от текущей папки."""
    monkeypatch.delattr(sys, 'frozen', raising=False)
    _fake_main(monkeypatch, os.path.join(ROOT, 'main_gui_window.py'))
    monkeypatch.chdir(tmp_path)
    assert get_dotenv_path() == os.path.join(ROOT, '.env')


def test_module_run_directly_gets_own_env(no_env_dir, monkeypatch):
    """Модуль, запущенный напрямую (отладка), — .env рядом с модулем, не боевой."""
    monkeypatch.delattr(sys, 'frozen', raising=False)
    module = os.path.join(ROOT, 'app', 'services', 'sync_service.py')
    _fake_main(monkeypatch, module)
    path = get_dotenv_path()
    assert path == os.path.join(ROOT, 'app', 'services', '.env')
    assert path != os.path.join(ROOT, '.env')


def test_interactive_falls_back_to_cwd(no_env_dir, monkeypatch, tmp_path):
    """Нет файла __main__ (python -c, REPL) — текущая папка."""
    monkeypatch.delattr(sys, 'frozen', raising=False)
    _fake_main(monkeypatch, None)
    monkeypatch.chdir(tmp_path)
    assert get_launch_dir() == str(tmp_path)


def test_env_dir_var_has_priority(monkeypatch, tmp_path):
    """PROJECT_MED_ENV_DIR важнее папки запуска (тесты, отладка на нужном .env)."""
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, 'executable', str(tmp_path / 'x' / 'app'))
    monkeypatch.setenv(ENV_DIR_VAR, str(tmp_path / 'dbg'))
    assert get_dotenv_path() == os.path.join(str(tmp_path / 'dbg'), '.env')


def test_no_upward_search(no_env_dir, monkeypatch, tmp_path):
    """.env выше папки запуска не подхватывается (раньше find_dotenv искал вверх)."""
    (tmp_path / '.env').write_text("GITHUB_TOKEN='parent'\n", encoding='utf-8')
    child = tmp_path / 'child'
    child.mkdir()
    monkeypatch.delattr(sys, 'frozen', raising=False)
    _fake_main(monkeypatch, str(child / 'run.py'))
    assert get_dotenv_path() == os.path.join(str(child), '.env')
    called = []
    monkeypatch.setattr(getenv_module, 'find_dotenv', lambda *a, **k: called.append(1) or '')
    get_dotenv_path()
    assert called == []


def test_real_direct_module_run_isolated(tmp_path):
    """
    Настоящий прямой запуск модуля отдельным процессом: .env создаётся рядом с ним.

    Модуль-скрипт кладётся во временную папку (боевой .env проекта не трогается);
    текущая папка процесса — другая.
    """
    script = tmp_path / 'debug_module' / 'probe.py'
    script.parent.mkdir()
    script.write_text(
        "import sys\n"
        f"sys.path.insert(0, {ROOT!r})\n"
        "from app.config.conf.getenv import get_getenv\n"
        "print(get_getenv('APP_CONFIG_PATH', start_value='config.msgpack'))\n",
        encoding='utf-8',
    )
    cwd = tmp_path / 'elsewhere'
    cwd.mkdir()
    env = {k: v for k, v in os.environ.items() if k not in (ENV_DIR_VAR, 'APP_CONFIG_PATH')}
    result = subprocess.run([sys.executable, str(script)], cwd=str(cwd), env=env,
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    assert (script.parent / '.env').exists()
    assert not (cwd / '.env').exists()
