# tests/test_settings_page/test_settings_page_docs.py
"""
Документация экрана настроек: описание модуля, докстринг и типы у каждой функции и метода.

Проверяется по исходникам (``ast``), без импорта.
"""
import ast
import os

PAGE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    'interfaces',
    'gui',
    'gui_window',
    'pages',
    'settings_page.py',
)


# дерево разбора файла экрана
def _tree() -> ast.Module:
    """Возвращает дерево разбора ``settings_page.py``."""
    with open(PAGE_PATH, encoding='utf-8') as source:
        return ast.parse(source.read())


def test_module_and_classes_documented():
    """У модуля и каждого класса есть описание."""
    tree = _tree()
    assert ast.get_docstring(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            assert ast.get_docstring(node), node.name


def test_functions_documented_and_typed():
    """У каждой функции — докстринг с примером, тип результата и типы параметров."""
    problems = []
    for node in ast.walk(_tree()):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        doc = ast.get_docstring(node) or ''
        if not doc:
            problems.append(f'{node.name}: нет докстринга')
        if 'Example:' not in doc:
            problems.append(f'{node.name}: нет примера')
        if ':param' in doc or 'Пример:' in doc:
            problems.append(f'{node.name}: старый формат докстринга')
        if node.returns is None:
            problems.append(f'{node.name}: нет типа результата')
        for arg in [*node.args.args, *node.args.kwonlyargs]:
            if arg.arg not in ('self', 'cls') and arg.annotation is None:
                problems.append(f'{node.name}: нет типа у {arg.arg}')
    assert problems == []
