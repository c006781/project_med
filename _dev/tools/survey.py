"""Опись кода project_med для карты: модули, строки, классы, функции, импорты между пакетами.

Только чтение исходников (ast); вывод — _dev/tmp/survey.json и сводка в консоль.
Запуск из корня: .venv310/Scripts/python.exe -I -X utf8 _dev/tools/survey.py
"""
import ast
import json
import os
import subprocess
from collections import defaultdict

ROOT = os.getcwd()
files = subprocess.run(['git', 'ls-files', '*.py'], capture_output=True, text=True,
                       encoding='utf-8').stdout.split()
files = [f for f in files if not f.startswith('tests/')]


def package_of(module: str) -> str:
    parts = module.split('.')
    if parts[0] == 'interfaces' and len(parts) > 3:
        return '.'.join(parts[:4])
    if parts[0] == 'app' and len(parts) > 2 and parts[1] == 'utils':
        return '.'.join(parts[:3])
    return '.'.join(parts[:2]) if len(parts) > 1 else parts[0]


result = {}
edges = defaultdict(set)
for f in files:
    src = open(f, encoding='utf-8-sig').read()
    lines = src.count('\n') + 1
    code = sum(1 for l in src.splitlines() if l.strip() and not l.strip().startswith('#'))
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        result[f] = {'lines': lines, 'error': str(e)}
        continue
    mod = f[:-3].replace('/', '.').removesuffix('.__init__')
    classes, funcs, nodoc, untyped = [], [], [], []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            classes.append(node.name)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            funcs.append(node.name)
            if not ast.get_docstring(node):
                nodoc.append(node.name)
            if node.returns is None and node.name != '__init__':
                untyped.append(node.name)
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level:
                base = mod.split('.')
                if not f.endswith('__init__.py'):
                    base = base[:-1]
                base = base[:len(base) - node.level + 1]
                name = '.'.join(base + ([node.module] if node.module else []))
            else:
                name = node.module or ''
            imports.add(name)
        elif isinstance(node, ast.Import):
            imports.update(a.name for a in node.names)
    internal = sorted(i for i in imports if i.split('.')[0] in ('app', 'interfaces', 'parsers'))
    for i in internal:
        if package_of(i) != package_of(mod):
            edges[package_of(mod)].add(package_of(i))
    result[f] = {'lines': lines, 'code': code, 'classes': classes, 'functions': len(funcs),
                 'no_docstring': len(nodoc), 'no_return_type': len(untyped),
                 'module_doc': bool(ast.get_docstring(tree)), 'imports': internal}

json.dump({'files': result, 'edges': {k: sorted(v) for k, v in edges.items()}},
          open('_dev/tmp/survey.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

by_pkg = defaultdict(lambda: [0, 0, 0, 0, 0])
for f, r in result.items():
    if 'error' in r:
        print('SYNTAX', f, r['error'])
        continue
    p = package_of(f[:-3].replace('/', '.'))
    s = by_pkg[p]
    s[0] += 1; s[1] += r['lines']; s[2] += r['functions']; s[3] += r['no_docstring']; s[4] += r['no_return_type']
print(f"{'пакет':45} файлов строк функций без_докстр без_типа_возврата")
for p in sorted(by_pkg):
    print(f'{p:45}', *by_pkg[p])
print('\nСВЯЗИ ПАКЕТОВ (кто → кого импортирует):')
for k in sorted(edges):
    print(f'{k} → {", ".join(sorted(edges[k]))}')
