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

def _dto_files():
    return sorted(f for f in os.listdir(DTO_DIR) if f.endswith('.py'))


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


def test_patient_full_name_takes_service_parameter():
    """Ф1.7.2: сервис пациентов — параметр (раньше брался из app.dependencies)."""
    import inspect
    from types import SimpleNamespace
    from app.dto import compute_fields
    assert list(inspect.signature(compute_fields.get_patient_full_name).parameters) == [
        'patient_id', 'patient_service']
    service = SimpleNamespace(get_patient_by_id=lambda pid: SimpleNamespace(
        last_name='Петров', first_name='Иван', middle_name=None))
    assert compute_fields.get_patient_full_name(1, service) == 'Петров Иван'
    assert not hasattr(compute_fields, 'get_patient_service')


def test_import_app_dto_loads_no_upper_layers(tmp_path):
    """Критерий М7: ``import app.dto`` (с зависимостями) не загружает модели, сборку, сервисы.

    Отдельный процесс: в процессе pytest эти модули уже загружены другими тестами.
    Настройки — временные (импорт ``app`` пишет ``.env``).
    """
    import subprocess
    import sys
    code = ("import sys, app.dto; "
            "print(sorted(m for m in sys.modules if m.startswith(%r)))" % (FORBIDDEN + ('app.repositories',),))
    env = dict(os.environ,
               PROJECT_MED_ENV_DIR=str(tmp_path),
               APP_CONFIG_PATH=str(tmp_path / 'config.msgpack'),
               PYTHONIOENCODING='utf-8')
    result = subprocess.run([sys.executable, '-c', code], cwd=ROOT, env=env,
                            capture_output=True, text=True, encoding='utf-8', timeout=60)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == '[]'
