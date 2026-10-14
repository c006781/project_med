# tests/test_logger/test_logging_setup.py

"""
app.config.logging_setup — передача конфига приложения в логгеры и порядок старта.
"""

import os
import subprocess
import sys

import pytest

import app.config.logging_setup as logging_setup
from app.utils.logger.logger import AppLogger

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_setup_logging_reads_config_and_configures(monkeypatch):
    seen = {}

    def fake_get_config_env(path=None):
        seen['path'] = path
        return {'LOG_LEVEL': 'ERROR'}

    monkeypatch.setattr(logging_setup, 'get_config_env', fake_get_config_env)
    monkeypatch.setattr(AppLogger, 'configure',
                        classmethod(lambda cls, cfg: seen.setdefault('cfg', dict(cfg))))
    result = logging_setup.setup_logging('some/config.msgpack')
    assert seen['path'] == 'some/config.msgpack'
    assert seen['cfg'] == {'LOG_LEVEL': 'ERROR'}
    assert result == {'LOG_LEVEL': 'ERROR'}


def test_setup_logging_returns_copy(monkeypatch):
    cfg = {'LOG_LEVEL': 'INFO'}
    monkeypatch.setattr(logging_setup, 'get_config_env', lambda path=None: cfg)
    monkeypatch.setattr(AppLogger, 'configure', classmethod(lambda cls, c: None))
    result = logging_setup.setup_logging()
    result['LOG_LEVEL'] = 'DEBUG'
    assert cfg['LOG_LEVEL'] == 'INFO'


@pytest.mark.parametrize('entry', ['main_gui_window.py', 'main_cli.py', 'pars_start.py'])
def test_entry_points_call_setup_logging_before_work(entry):
    """В точке входа setup_logging() вызывается внутри __main__ раньше основной работы."""
    src = open(os.path.join(PROJECT_ROOT, entry), encoding='utf-8').read()
    main_block = src[src.index("if __name__"):]
    work_call = {
        'main_gui_window.py': 'main_gui_window.main()',
        'main_cli.py': 'cli.start_cli(',
        'pars_start.py': 'pars_start_args(',
    }[entry]
    assert 'setup_logging()' in main_block
    assert main_block.index('setup_logging()') < main_block.index(work_call)


def test_full_startup_first_record_goes_to_file(tmp_path):
    """Чистый процесс как при старте GUI: импорты → setup_logging → первая запись в файл.

    Конфиг — отдельный msgpack в tmp_path с полным логированием system.
    """
    import msgpack
    log_dir = tmp_path / 'logs'
    config_path = tmp_path / 'config.msgpack'
    config = {
        'LOG_DIR': str(log_dir), 'LOG_LEVEL': 'DEBUG',
        'system_enabled': 'True', 'system_console_enabled': 'False',
        'system_file_enabled': 'True', 'system_LEVEL': 'DEBUG',
        'user_enabled': 'True', 'user_console_enabled': 'False',
        'user_file_enabled': 'True', 'user_LEVEL': 'DEBUG',
    }
    with open(config_path, 'wb') as f:
        msgpack.pack(config, f)

    code = f'''
import interfaces.gui.gui_window.main  # те же импорты, что в main_gui_window.py
from app.utils.logger.logger import AppLogger
from app.config.logging_setup import setup_logging

@AppLogger.get_instance(name='main.py', enable_file_logging='system').log_execution_time(description='main')
def fake_main():
    AppLogger.get_instance('gui', enable_file_logging='user').info('GUI приложение запущено')

setup_logging(config_path={str(config_path)!r})
fake_main()
'''
    out = subprocess.run(
        [sys.executable, '-c', code], cwd=str(tmp_path), capture_output=True, text=True,
        env={**os.environ, 'PYTHONPATH': PROJECT_ROOT, 'GITHUB_TOKEN': 'test-placeholder'},
        timeout=120,
    )
    assert out.returncode == 0, out.stderr
    content = (log_dir / 'app.log').read_text(encoding='utf-8')
    lines = content.splitlines()
    assert 'main [Начало]' in lines[0]
    assert 'GUI приложение запущено' in content
    assert 'main [Завершение' in lines[-1]
