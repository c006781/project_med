# tests/test_schema/test_schema_layers.py

"""
Сверка М7 (Ф1.6.5): описания таблиц (``app/schema``) — слой ниже моделей и DTO: не
импортируют ``app.database``, ``app.dto``, сборку приложения, сервисы и наборы экранов
(``app/schema/IMPLEMENTATION.md`` §4: модуль моделей импортирует описания — иначе цикл).
Проверка — разбором исходников (``ast``), закомментированное не считается.
"""

import ast
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCHEMA_DIR = os.path.join(ROOT, 'app', 'schema')
FORBIDDEN = ('app.database', 'app.dto', 'app.dependencies', 'app.services', 'app.repositories',
             'app.tables', 'app.dataset_app')


def _schema_files():
    return sorted(f for f in os.listdir(SCHEMA_DIR) if f.endswith('.py'))


@pytest.mark.parametrize('name', _schema_files())
def test_schema_module_does_not_import_upper_layers(name):
    path = os.path.join(SCHEMA_DIR, name)
    with open(path, encoding='utf-8') as f:
        tree = ast.parse(f.read(), filename=path)
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    bad = [m for m in imported if m.startswith(FORBIDDEN)]
    assert bad == [], f'app/schema/{name} импортирует верхние слои: {bad}'
