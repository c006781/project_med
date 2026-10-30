# tests/test_dto_layers.py

"""
Слои без связей «снизу вверх» (Ф1.7.2, Ф1.7.3): модули ``app.dto`` не импортируют модели
(``app.database``), сборку приложения (``app.dependencies``) и сервисы — ни на уровне
модуля, ни внутри функций. Проверка — разбором исходников (``ast``), без импорта кода:
закомментированный старый код не считается.
"""

import ast
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DTO_DIR = os.path.join(ROOT, 'app', 'dto')
FORBIDDEN = ('app.database', 'app.dependencies', 'app.services')

# Ф1.7.2 (compute_fields.py) — следующим шагом М7; до него модуль в проверку не входит
PENDING = {'compute_fields.py'}


def _dto_files():
    return sorted(f for f in os.listdir(DTO_DIR) if f.endswith('.py') and f not in PENDING)


def _imported_modules(path):
    """Имена модулей всех ``import`` / ``from … import`` файла (в том числе внутри функций)."""
    with open(path, encoding='utf-8') as f:
        tree = ast.parse(f.read(), filename=path)
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


@pytest.mark.parametrize('name', _dto_files())
def test_dto_module_does_not_import_upper_layers(name):
    imported = _imported_modules(os.path.join(DTO_DIR, name))
    bad = [m for m in imported if m.startswith(FORBIDDEN)]
    assert bad == [], f'app/dto/{name} импортирует верхние слои: {bad}'


def test_model_config_map_removed():
    """``MODEL_CONFIG_MAP`` убран (Ф1.3.3): карту никто не читал, ради неё импортировались модели."""
    from app.dto import field_configs
    assert not hasattr(field_configs, 'MODEL_CONFIG_MAP')
    assert field_configs.get_note_fields(field_configs.APPOINTMENT_CONFIG) == [
        'reason_id', 'procedure_id', 'recommendations_id', 'note_id', 'cost_procedure_id']
