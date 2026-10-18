# tests/test_dataset_app/test_sources_compile.py

"""
Весь код программы компилируется (2026-10-18): синтаксическая ошибка в файле, который не
импортирует ни один тест (например, главное окно), иначе нашлась бы только при запуске.
"""

import os
import py_compile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _sources():
    for top in ('app', 'interfaces', 'parsers', 'scripts'):
        for folder, dirs, files in os.walk(os.path.join(ROOT, top)):
            dirs[:] = [d for d in dirs if d != '__pycache__']
            for name in files:
                if name.endswith('.py'):
                    yield os.path.join(folder, name)
    for name in os.listdir(ROOT):
        if name.endswith('.py'):
            yield os.path.join(ROOT, name)


@pytest.mark.parametrize('path', sorted(_sources()), ids=lambda p: os.path.relpath(p, ROOT))
def test_compiles(path, tmp_path):
    py_compile.compile(path, cfile=str(tmp_path / 'x.pyc'), doraise=True)
