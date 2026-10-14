# tests/test_logger/test_portability.py

"""
Переносимость модуля логирования в другие проекты.

Модуль должен работать, если его просто скопировать:
    * пакет app/utils/logger/ под любым именем, используется только ядро (BaseAppLogger);
    * тот же пакет с AppLogger.

До 2026-10-14 ядро было одним файлом base_logger.py и копировалось отдельно; после
разбиения на модули единица переноса — папка пакета.

Каждый сценарий — отдельный чистый процесс (``python -I``: без PYTHONPATH, без
текущей папки в sys.path), в котором проект project_med недоступен.
"""

import os
import shutil
import subprocess
import sys
import textwrap

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LOGGER_DIR = os.path.join(PROJECT_ROOT, 'app', 'utils', 'logger')


def _run(script_path, cwd):
    """Запускает скрипт в изолированном интерпретаторе; возвращает CompletedProcess."""
    env = {k: v for k, v in os.environ.items() if k != 'PYTHONPATH'}
    return subprocess.run(
        # -X utf8: вывод дочернего процесса в UTF-8 (-I игнорирует PYTHONIOENCODING)
        [sys.executable, '-I', '-X', 'utf8', script_path], cwd=cwd, capture_output=True,
        text=True, encoding='utf-8', env=env, timeout=60,
    )


def _check_line(line, script_path, func):
    assert f'File "{script_path}"' in line or os.path.normcase(script_path) in os.path.normcase(line), line
    assert f'in <{func}>' in line, line


def test_core_from_copied_package(tmp_path):
    """Пакет, скопированный под именем corelog; используется только ядро BaseAppLogger."""
    shutil.copytree(LOGGER_DIR, tmp_path / 'corelog',
                    ignore=shutil.ignore_patterns('__pycache__', '*.md'))
    script = tmp_path / 'use_core.py'
    log_dir = tmp_path / 'logs'
    script.write_text(textwrap.dedent(f'''
        import os, sys
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from corelog.base_logger import BaseAppLogger

        class MyLogger(BaseAppLogger):
            _instances = {{}}

            @classmethod
            def get_default_config(cls):
                return {{'LOG_LEVEL': 'DEBUG', 'LOG_FILE': {str(log_dir) + os.sep!r},
                        'LOG_MAX_BYTES': 1000000, 'LOG_BACKUP_COUNT': 1,
                        'console_enabled': 'False', 'file_enabled': 'True'}}

        log = MyLogger.get_instance('core')

        @log.log_execution_time(description='работа')
        def worker():
            log.info('из worker')
            try:
                raise ValueError('x')
            except ValueError:
                log.exception('ошибка')

        worker()
        print('project loaded:', any(m == 'app' or m.startswith('app.') for m in sys.modules))
    '''), encoding='utf-8')

    out = _run(str(script), str(tmp_path))
    assert out.returncode == 0, out.stderr
    assert 'project loaded: False' in out.stdout

    lines = [l for l in (log_dir / 'app.log').read_text(encoding='utf-8').splitlines() if '\t[core]\t' in l]
    info = next(l for l in lines if 'из worker' in l)
    exc = next(l for l in lines if 'ошибка' in l)
    _check_line(info, str(script), 'worker')
    _check_line(exc, str(script), 'worker')
    assert any('работа [Начало]' in l for l in lines)


def test_whole_package_with_app_logger(tmp_path):
    """Весь пакет под именем mylogging: AppLogger.configure() без конфига project_med."""
    shutil.copytree(LOGGER_DIR, tmp_path / 'mylogging',
                    ignore=shutil.ignore_patterns('__pycache__', '*.md'))
    script = tmp_path / 'use_pkg.py'
    log_dir = tmp_path / 'logs'
    script.write_text(textwrap.dedent(f'''
        import os, sys
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from mylogging import AppLogger

        AppLogger.configure({{'LOG_DIR': {str(log_dir)!r}, 'system_LEVEL': 'DEBUG',
                              'system_console_enabled': 'False', 'system_file_enabled': 'True'}})
        from mylogging import CallableHandler
        svc = AppLogger.get_instance('svc', enable_file_logging='system')
        sent = []
        out = svc.add_output(sent.append, formatter='%(plain_message)s')
        assert isinstance(out, CallableHandler)

        def handler_func():
            svc.debug('из сервиса')

        handler_func()
        print('sent:', sent)
        print('project loaded:', any(m == 'app' or m.startswith('app.') for m in sys.modules))
    '''), encoding='utf-8')

    out = _run(str(script), str(tmp_path))
    assert out.returncode == 0, out.stderr
    assert 'project loaded: False' in out.stdout
    assert "sent: ['из сервиса']" in out.stdout
    line = next(l for l in (log_dir / 'app.log').read_text(encoding='utf-8').splitlines()
                if 'из сервиса' in l)
    _check_line(line, str(script), 'handler_func')


@pytest.mark.parametrize('module', ['base_logger.py', 'logger.py', '__init__.py'])
def test_no_absolute_project_imports(module):
    """В пакете нет импортов вида ``app.…`` — только стандартная библиотека и относительные."""
    import ast
    tree = ast.parse(open(os.path.join(LOGGER_DIR, module), encoding='utf-8').read())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            assert not node.module.split('.')[0] == 'app', node.module
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.split('.')[0] == 'app', alias.name
