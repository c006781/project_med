# tests/test_logger/test_logger_docs.py

"""
Документация пакета журналов (``app/utils/logger``) — сверка М2 (2026-10-25,
``_dev/ПЛАН.md`` Ф1.6.1).

Правило проекта: у каждой функции и метода — докстринг и аннотация возврата. Проверяется
по исходникам (``ast``), без импорта. К8: на уровне модуля ``logger.py`` — только
``AppLogger``; учебный класс примера живёт в блоке ``if __name__ == '__main__'``.
"""

import ast
import os

import pytest

PACKAGE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    'app',
    'utils',
    'logger',
)

MODULES = sorted(
    name for name in os.listdir(PACKAGE_DIR) if name.endswith('.py')
)


def _tree(name: str) -> ast.Module:
    """Дерево разбора модуля пакета."""
    with open(os.path.join(PACKAGE_DIR, name), encoding='utf-8') as f:
        return ast.parse(f.read())


@pytest.mark.parametrize('module', MODULES)
def test_functions_documented_and_typed(module):
    """У каждой функции модуля (включая вложенные и пример в __main__) — докстринг и тип возврата."""
    problems = []
    for node in ast.walk(_tree(module)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if ast.get_docstring(node) is None:
                problems.append(f'{node.name}:{node.lineno} — нет докстринга')
            if node.returns is None:
                problems.append(f'{node.name}:{node.lineno} — нет типа возврата')

    assert problems == []


def test_logger_module_classes():
    """К8: на уровне модуля logger.py — только AppLogger (учебный класс — в __main__)."""
    classes = [node.name for node in _tree('logger.py').body if isinstance(node, ast.ClassDef)]

    assert classes == ['AppLogger']
