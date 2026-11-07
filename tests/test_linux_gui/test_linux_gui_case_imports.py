# tests/test_linux_gui/test_linux_gui_case_imports.py
"""
Сверка регистра имён в импортах и путях-строках проекта (совместимость с Linux).

Windows и macOS не различают регистр имён файлов, поэтому ``from app.Utils import x`` при
файле ``app/utils`` там работает, а на Linux падает ``ModuleNotFoundError``. Тест читает
исходники как текст (AST), сами модули НЕ импортирует, сеть и БД не использует.

Источник списка файлов — ``git ls-files`` (в копии без ``.git`` — обход папки).

Проверяется:
    1. каждый импорт внутреннего пакета (``app``, ``interfaces``, ``parsers``, ``scripts``,
       ``tests``) совпадает с именами файлов и папок по регистру;
    2. в проекте нет двух путей, отличающихся только регистром;
    3. строковые литералы, похожие на путь к файлу ресурса из репозитория (``*.png``,
       ``*.qss`` …), совпадают с файлом по регистру, если такой файл есть вообще.
"""
import ast
import os
import subprocess
from typing import Dict, List, Set, Tuple

# корень проекта: tests/test_linux_gui/ -> ../..
ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, os.pardir),
)

# папки, которые не относятся к коду проекта
SKIP_DIRS = {'_dev', '.git', '__pycache__', 'venv', '.venv', 'node_modules', 'build', 'dist'}

# расширения файлов-ресурсов, строки с которыми сверяются по регистру
RESOURCE_EXTS = ('.png', '.jpg', '.jpeg', '.svg', '.ico', '.qss', '.css', '.ui', '.qrc',
                 '.json', '.ini', '.msgpack', '.mako', '.html', '.ttf')


# список файлов проекта (posix-пути от корня)
def list_project_files(
    root : str,  # корень проекта
) -> List[str]:
    """
    Возвращает файлы проекта относительно ``root`` с разделителем ``/``.

    Берёт ``git ls-files``; нет git или ``.git`` — обходит папку, пропуская ``SKIP_DIRS``.

    Args:
        root : (str) Корень проекта.

    Returns:
        (list[str]) Пути вида ``app/utils/x.py`` без служебных папок.

    Example:
        >>> list_project_files(
        ...     root   =   "/home/user/project_med",   # корень
        ... )[:1]
        ['.github/workflows/release.yml']
    """
    files: List[str] = []
    try:
        out = subprocess.run(
            ['git', '-c', 'core.quotepath=off', 'ls-files'],
            cwd              =   root,
            capture_output   =   True,
            text             =   True,
            encoding         =   'utf-8',
            timeout          =   30,
        )
        if out.returncode == 0 and out.stdout.strip():
            files = [line for line in out.stdout.splitlines() if line]
    except (OSError, subprocess.SubprocessError):
        files = []
    if not files:
        for folder, dirs, names in os.walk(root):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for name in names:
                rel = os.path.relpath(os.path.join(folder, name), root)
                files.append(rel.replace(os.sep, '/'))
    return [f for f in files if f.split('/')[0] not in SKIP_DIRS]


class PathIndex:
    """Индекс путей проекта: точный и без учёта регистра, для файлов и папок."""

    # строит индекс по списку файлов
    def __init__(
        self,
        files : List[str],  # файлы проекта (posix)
    ) -> None:
        self.exact : Set[str] = set()                 # все файлы и папки, точный регистр
        self.init_names : Dict[str, Set[str]] = {}    # папка пакета -> имена, заданные в её __init__.py
        self.lower : Dict[str, Set[str]] = {}         # нижний регистр -> варианты написания
        for f in files:
            parts = f.split('/')
            for i in range(1, len(parts) + 1):
                p = '/'.join(parts[:i])
                self.exact.add(p)
                self.lower.setdefault(p.lower(), set()).add(p)

    # есть ли путь с точным регистром
    def has(
        self,
        path : str,  # путь без расширения или с ним
    ) -> bool:
        """Возвращает True, если такой файл или папка есть с точным регистром."""
        return path in self.exact

    # варианты написания, отличающиеся только регистром
    def case_variants(
        self,
        path : str,  # путь, которого нет с точным регистром
    ) -> Set[str]:
        """Возвращает пути, совпадающие с ``path`` без учёта регистра."""
        return self.lower.get(path.lower(), set())


# найти несовпадения регистра в импортах одного файла
def check_imports_in_source(
    source   : str,        # текст модуля
    rel_path : str,        # путь модуля от корня (posix)
    index    : PathIndex,  # индекс путей проекта
    tops     : Set[str],   # имена внутренних пакетов верхнего уровня (точный регистр)
) -> List[str]:
    """
    Возвращает описания импортов, у которых регистр имени не совпадает с файлом или папкой.

    Импорт чужих пакетов (``os``, ``PySide6``) пропускается: проверяются только цепочки,
    начинающиеся с внутреннего пакета (в любом регистре). Имя после ``import`` в
    ``from p import name`` сверяется, только если у ``name`` есть файл или папка
    с другим регистром, но нет точного и ``name`` не задано в ``__init__.py`` пакета
    (``from app.database import Database`` — класс, а не модуль ``database.py``).

    Args:
        source   : (str) Исходный текст модуля.
        rel_path : (str) Путь модуля от корня проекта (для относительных импортов).
        index    : (PathIndex) Индекс файлов проекта.
        tops     : (set[str]) Внутренние пакеты верхнего уровня.

    Returns:
        (list[str]) Строки вида ``файл:строка: импорт``; пусто — проблем нет.

    Example:
        >>> check_imports_in_source(
        ...     source     =   "from app.Utils import x",     # опечатка в регистре
        ...     rel_path   =   "main.py",                     # модуль
        ...     index      =   PathIndex(['app/utils/x.py']), # файлы проекта
        ...     tops       =   {'app'},                       # внутренние пакеты
        ... )
        ['main.py:1: from app.Utils import x -> app/Utils (на диске: app/utils)']
    """
    problems: List[str] = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return problems
    tops_lower = {t.lower() for t in tops}
    pkg_parts = rel_path.split('/')[:-1]   # пакет, в котором лежит модуль

    # проверка цепочки имён: возвращает (проблема, дошли ли до конца без проблем)
    def walk_chain(
        base  : List[str],  # уже подтверждённая часть пути
        names : List[str],  # дальше по цепочке
        line  : int,        # строка импорта
        text  : str,        # текст импорта для сообщения
    ) -> None:
        cur = list(base)
        for n in names:
            cur.append(n)
            path = '/'.join(cur)
            if index.has(path) or index.has(path + '.py'):
                continue
            variants = index.case_variants(path) | index.case_variants(path + '.py')
            if variants:
                problems.append(f"{rel_path}:{line}: {text} -> {path} (на диске: {', '.join(sorted(variants))})")
            return  # дальше — атрибуты модуля или внешнее, не проверяем

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                parts = alias.name.split('.')
                if parts[0].lower() in tops_lower:
                    walk_chain([], parts, node.lineno, f"import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                up = node.level - 1
                base = pkg_parts[:len(pkg_parts) - up] if up else list(pkg_parts)
                mod_parts = node.module.split('.') if node.module else []
            else:
                base = []
                mod_parts = node.module.split('.') if node.module else []
                if not mod_parts or mod_parts[0].lower() not in tops_lower:
                    continue
            text = f"from {'.' * node.level}{node.module or ''} import ..."
            before = len(problems)
            walk_chain(base, mod_parts, node.lineno, text)
            if len(problems) != before:
                continue
            # имена после import: подмодули пакета (если рядом лежит такой файл или папка)
            mod_path = '/'.join(base + mod_parts)
            if mod_path and index.has(mod_path) and not index.has(mod_path + '.py'):
                for alias in node.names:
                    if alias.name == '*':
                        continue
                    sub = f"{mod_path}/{alias.name}"
                    if index.has(sub) or index.has(sub + '.py'):
                        continue
                    if alias.name in index.init_names.get(mod_path, set()): # имя — атрибут пакета, не модуль
                        continue
                    variants = index.case_variants(sub) | index.case_variants(sub + '.py')
                    if variants:
                        problems.append(
                            f"{rel_path}:{node.lineno}: {text} {alias.name} -> {sub} "
                            f"(на диске: {', '.join(sorted(variants))})"
                        )
    return problems


# пути-строки к ресурсам с другим регистром
def check_resource_strings(
    source   : str,        # текст модуля
    rel_path : str,        # путь модуля от корня
    index    : PathIndex,  # индекс путей
    names    : Dict[str, Set[str]],  # имя файла в нижнем регистре -> точные пути ресурсов
) -> List[str]:
    """
    Возвращает строковые литералы-пути, у которых регистр отличается от файла в репозитории.

    Берутся строки без пробелов-переносов, оканчивающиеся на расширение ресурса; сверяется
    хвост пути с реальным файлом (по имени и по последним компонентам). Если файла нет
    вообще (путь собирается во время работы, внешний ресурс) — не проблема.

    Args:
        source   : (str) Исходный текст модуля.
        rel_path : (str) Путь модуля от корня.
        index    : (PathIndex) Индекс путей.
        names    : (dict) Имя файла в нижнем регистре -> варианты точных путей.

    Returns:
        (list[str]) Описания находок; пусто — проблем нет.

    Example:
        >>> check_resource_strings(
        ...     source     =   "p = 'res/Logo.PNG'",             # литерал
        ...     rel_path   =   "ui.py",                          # модуль
        ...     index      =   PathIndex(['res/logo.png']),      # файлы
        ...     names      =   {'logo.png': {'res/logo.png'}},   # имена ресурсов
        ... )
        ["ui.py:1: 'res/Logo.PNG' -> res/logo.png"]
    """
    problems: List[str] = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return problems
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            continue
        s = node.value.strip()
        if not s or '\n' in s or len(s) > 200 or not s.lower().endswith(RESOURCE_EXTS):
            continue
        tail = s.replace('\\', '/').lstrip('./')
        base = tail.rsplit('/', 1)[-1]
        candidates = names.get(base.lower(), set())
        if not candidates:
            continue
        # точное совпадение хвоста пути с каким-либо файлом — всё в порядке
        if any(c == tail or c.endswith('/' + tail) for c in candidates):
            continue
        # то же без учёта регистра — значит, регистр разный
        low_tail = tail.lower()
        near = sorted(c for c in candidates if c.lower() == low_tail or c.lower().endswith('/' + low_tail))
        if near:
            problems.append(f"{rel_path}:{node.lineno}: {s!r} -> {', '.join(near)}")
    return problems


# имена, которые модуль задаёт на верхнем уровне (импорты, def, class, присваивания)
def _names_defined(
    source : str,  # текст модуля
) -> Set[str]:
    """Возвращает имена верхнего уровня модуля; при синтаксической ошибке — пустое множество."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    found: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            found |= {(a.asname or a.name).split('.')[0] for a in node.names}
        elif isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)):
            found.add(node.name)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            found.add(node.id)
    return found


# тексты модулей проекта
def _python_sources() -> Tuple[PathIndex, Dict[str, str], Set[str]]:
    files = list_project_files(ROOT)
    index = PathIndex(files)
    sources: Dict[str, str] = {}
    for f in files:
        if f.endswith('.py') and os.path.isfile(os.path.join(ROOT, f)):
            with open(os.path.join(ROOT, f), encoding='utf-8', errors='replace') as fh:
                sources[f] = fh.read()
    for rel, text in sources.items():
        if rel.endswith('/__init__.py'):
            index.init_names[rel[:-len('/__init__.py')]] = _names_defined(text)
    tops = {f.split('/')[0] for f in files if '/' in f and f.split('/')[0] not in SKIP_DIRS}
    tops |= {f[:-3] for f in files if '/' not in f and f.endswith('.py')}
    return index, sources, tops


def test_imports_match_filename_case():
    """Регистр имён во всех внутренних импортах совпадает с файлами и папками."""
    index, sources, tops = _python_sources()
    problems: List[str] = []
    for rel, text in sorted(sources.items()):
        problems += check_imports_in_source(text, rel, index, tops)
    assert not problems, "Регистр импорта не совпадает с диском (на Linux упадёт):\n" + "\n".join(problems)


def test_no_paths_differing_only_by_case():
    """В репозитории нет двух файлов или папок, отличающихся только регистром."""
    index, _, _ = _python_sources()
    clashes = [sorted(v) for v in index.lower.values() if len(v) > 1]
    assert not clashes, f"Пути, различающиеся только регистром (Windows склеит их): {clashes}"


def test_resource_strings_match_case():
    """Строки-пути к ресурсам репозитория совпадают с файлами по регистру."""
    index, sources, _ = _python_sources()
    names: Dict[str, Set[str]] = {}
    for p in index.exact:
        if p.lower().endswith(RESOURCE_EXTS) and index.has(p) and not p.endswith('/'):
            names.setdefault(p.rsplit('/', 1)[-1].lower(), set()).add(p)
    problems: List[str] = []
    for rel, text in sorted(sources.items()):
        problems += check_resource_strings(text, rel, index, names)
    assert not problems, "Регистр пути к ресурсу не совпадает с файлом:\n" + "\n".join(problems)


# ---- проверка самих проверок (синтетика) ----

def test_checker_detects_wrong_case_import():
    """Проверка ловит ``from app.Utils import x`` при папке ``app/utils``."""
    index = PathIndex(['app/__init__.py', 'app/utils/x.py'])
    found = check_imports_in_source('from app.Utils import x\n', 'main.py', index, {'app'})
    assert len(found) == 1 and 'app/utils' in found[0]


def test_checker_skips_package_attribute():
    """Класс, объявленный в ``__init__.py``, не принимается за модуль с другим регистром."""
    index = PathIndex(['app/db/__init__.py', 'app/db/database.py'])
    index.init_names['app/db'] = {'Database'}
    assert check_imports_in_source('from app.db import Database\n', 'main.py', index, {'app'}) == []


def test_checker_detects_wrong_case_submodule_name():
    """Проверка ловит ``from app.utils import X`` при файле ``x.py``."""
    index = PathIndex(['app/__init__.py', 'app/utils/__init__.py', 'app/utils/x.py'])
    found = check_imports_in_source('from app.utils import X\n', 'main.py', index, {'app'})
    assert len(found) == 1


def test_checker_accepts_correct_and_foreign_imports():
    """Верные и внешние импорты, атрибуты модуля и относительные импорты — без находок."""
    index = PathIndex(['app/__init__.py', 'app/utils/__init__.py', 'app/utils/x.py', 'app/utils/y.py'])
    src = (
        "import os\nfrom PySide6.QtCore import Qt\nfrom app.utils.x import SomeClass\n"
        "from app.utils import x\nfrom . import y\nfrom .x import Z\nimport app.utils.x\n"
    )
    assert check_imports_in_source(src, 'app/utils/y.py', index, {'app'}) == []


def test_checker_relative_import_case():
    """Относительный импорт с неверным регистром ловится."""
    index = PathIndex(['app/utils/__init__.py', 'app/utils/x.py'])
    found = check_imports_in_source('from .X import a\n', 'app/utils/y.py', index, {'app'})
    assert len(found) == 1


def test_resource_checker_detects_wrong_case():
    """Строка ``res/Logo.PNG`` при файле ``res/logo.png`` ловится; точная — нет."""
    index = PathIndex(['res/logo.png'])
    names = {'logo.png': {'res/logo.png'}}
    assert len(check_resource_strings("p = 'res/Logo.PNG'", 'ui.py', index, names)) == 1
    assert check_resource_strings("p = 'res/logo.png'", 'ui.py', index, names) == []
    assert check_resource_strings("p = 'other/none.png'", 'ui.py', index, names) == []


def test_list_project_files_without_git(tmp_path):
    """Без ``.git`` список строится обходом папки и пропускает ``_dev``."""
    (tmp_path / 'a').mkdir()
    (tmp_path / 'a' / 'm.py').write_text('x = 1\n', encoding='utf-8')
    (tmp_path / '_dev').mkdir()
    (tmp_path / '_dev' / 'z.py').write_text('x = 1\n', encoding='utf-8')
    files = list_project_files(str(tmp_path))
    assert files == ['a/m.py']
