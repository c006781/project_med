# tests/test_main_window/test_main_window_docs.py
"""
Документация главного окна: описание модуля и классов, докстринг с примером и типы у каждой функции.

Проверяется по исходникам (``ast``), без импорта.
"""
import ast
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WINDOW_PATH = os.path.join(ROOT, 'interfaces', 'gui', 'gui_window', 'main_window.py')


# дерево разбора файла окна
def _tree() -> ast.Module:
    """Возвращает дерево разбора ``main_window.py``."""
    with open(WINDOW_PATH, encoding='utf-8') as source:
        return ast.parse(source.read())


def test_module_and_classes_documented():
    """У модуля и каждого класса есть описание."""
    tree = _tree()
    assert ast.get_docstring(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            assert ast.get_docstring(node), node.name


def test_functions_documented_and_typed():
    """У каждой функции — докстринг с примером, тип результата и типы параметров; формат Google."""
    problems = []
    for node in ast.walk(_tree()):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        doc = ast.get_docstring(node) or ''
        if 'Example:' not in doc:
            problems.append(f'{node.name}: нет примера')
        for old in (':param', 'Пример:', 'Параметры:', 'Аргументы:'):
            if old in doc:
                problems.append(f'{node.name}: старый формат {old}')
        if node.returns is None:
            problems.append(f'{node.name}: нет типа результата')
        for arg in [*node.args.args, *node.args.kwonlyargs]:
            if arg.arg not in ('self', 'cls') and arg.annotation is None:
                problems.append(f'{node.name}: нет типа у {arg.arg}')
    assert problems == []
