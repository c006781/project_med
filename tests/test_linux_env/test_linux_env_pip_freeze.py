# tests/test_linux_env/test_linux_env_pip_freeze.py

"""
scripts/pip_freeze.sh: условия `; sys_platform == "win32"` у pyinstaller и его зависимостей.

Настоящий выпуск не запускается: скрипт копируется в tmp_path (``<проект>/scripts/``), вместо
``pip`` в PATH стоит заглушка, которая печатает заданный «вывод freeze» (или падает).
Тесты для Linux (bash, awk); на Windows пропускаются — там проверка вручную в Git Bash.
"""

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]            # корень проекта
SCRIPT = REPO_ROOT / 'scripts' / 'pip_freeze.sh'           # проверяемый скрипт
CONDITIONAL = ('altgraph', 'pyinstaller', 'pyinstaller-hooks-contrib')   # условные пакеты
COND = '; sys_platform == "win32"'                         # условие в файле

pytestmark = pytest.mark.skipif(
    os.name == 'nt' or shutil.which('bash') is None or shutil.which('awk') is None,
    reason='проверка bash-скрипта на Linux (на Windows — вручную в Git Bash)',
)

# Вывод freeze «Linux»: pyinstaller и его зависимостей нет, пакет проекта — editable
EGG = '-e git+ssh://git@github.com/c006781/project_med.git@abc#egg=project_med'
LINUX_FREEZE = (
    'alembic==1.18.4\n'
    'certifi==2099.1.1\n'
    'coverage==7.13.4\n'
    'packaging==26.0\n'
    f'{EGG}\n'
    'pydantic==2.12.5\n'
    'pydantic_core==2.41.5\n'
    'pytest==9.0.2\n'
    'pytest-cov==7.0.0\n'
    'PySide6==6.9.3\n'
    'yadisk==3.4.0\n'
)
OLD_PROD = (
    'alembic==1.18.4\n'
    'altgraph==0.17.5; sys_platform == "win32"\n'
    'certifi==2026.2.25\n'
    'pydantic==2.12.5\n'
    'pydantic_core==2.41.5\n'
    'pyinstaller==6.20.0; sys_platform == "win32"\n'
    'pyinstaller-hooks-contrib==2026.4; sys_platform == "win32"\n'
    'PySide6==6.9.3\n'
    'yadisk==3.4.0\n'
)
OLD_DEV = (
    'alembic==1.18.4\n'
    'altgraph==0.17.5; sys_platform == "win32"\n'
    'certifi==2026.2.25\n'
    'coverage==7.13.4\n'
    'packaging==26.0\n'
    f'{EGG}\n'
    'pydantic==2.12.5\n'
    'pydantic_core==2.41.5\n'
    'pyinstaller==6.20.0; sys_platform == "win32"\n'
    'pyinstaller-hooks-contrib==2026.4; sys_platform == "win32"\n'
    'pytest==9.0.2\n'
    'pytest-cov==7.0.0\n'
    'PySide6==6.9.3\n'
    'yadisk==3.4.0\n'
)


class Project:
    """Временный «проект»: scripts/pip_freeze.sh, requirements*.txt и заглушка pip."""

    def __init__(self, root: Path):
        self.root = root
        (root / 'scripts').mkdir()
        shutil.copy(SCRIPT, root / 'scripts' / 'pip_freeze.sh')
        (root / 'bin').mkdir()
        self.freeze_file = root / 'freeze_out.txt'
        pip = root / 'bin' / 'pip'
        pip.write_text(
            '#!/bin/bash\n'
            '[ -n "$STUB_PIP_FAIL" ] && { echo "pip: boom" >&2; exit 3; }\n'
            'cat "$STUB_PIP_FREEZE"\n'
        )
        pip.chmod(pip.stat().st_mode | stat.S_IXUSR)

    def write(self, name: str, text: str, newline: str = '\n') -> None:
        """Пишет файл проекта байтами (окончания строк — как задано)."""
        (self.root / name).write_bytes(text.replace('\n', newline).encode('utf-8'))

    def read(self, name: str) -> str:
        return (self.root / name).read_text(encoding='utf-8')

    def run(self, freeze: str = LINUX_FREEZE, fail: bool = False, cwd=None, newline: str = '\n'):
        """Запускает скрипт; ``freeze`` — вывод заглушки pip, ``fail`` — pip падает."""
        self.freeze_file.write_bytes(freeze.replace('\n', newline).encode('utf-8'))
        env = dict(os.environ)
        env['PATH'] = f"{self.root / 'bin'}{os.pathsep}{env['PATH']}"
        env['STUB_PIP_FREEZE'] = str(self.freeze_file)
        env['STUB_PIP_FAIL'] = '1' if fail else ''
        return subprocess.run(
            ['bash', str(self.root / 'scripts' / 'pip_freeze.sh')],
            cwd=str(cwd or self.root), env=env, capture_output=True, text=True,
        )


@pytest.fixture
def proj(tmp_path):
    root = tmp_path / 'проект с пробелом'
    root.mkdir()
    p = Project(root)
    p.write('requirements.txt', OLD_PROD)
    p.write('requirements-dev.txt', OLD_DEV)
    return p


def _names(text: str) -> list:
    return [line.split('==')[0].split(';')[0].strip() for line in text.splitlines()]


def test_missing_in_freeze_keeps_line_version_and_condition(proj):
    """Linux: pyinstaller не установлен — строки с версией и условием сохраняются в обоих файлах."""
    result = proj.run()
    assert result.returncode == 0, result.stderr
    for name in ('requirements.txt', 'requirements-dev.txt'):
        text = proj.read(name)
        assert f'altgraph==0.17.5{COND}\n' in text
        assert f'pyinstaller==6.20.0{COND}\n' in text
        assert f'pyinstaller-hooks-contrib==2026.4{COND}\n' in text
    assert 'certifi==2099.1.1' in proj.read('requirements.txt')   # остальное — из freeze


def test_lines_stay_in_alphabetical_place(proj):
    """Сохранённые строки стоят там, где их поставил бы pip freeze (стабильный diff)."""
    proj.run()
    names = _names(proj.read('requirements.txt'))
    assert names == [
        'alembic', 'altgraph', 'certifi', 'pydantic', 'pydantic_core',
        'pyinstaller', 'pyinstaller-hooks-contrib', 'PySide6', 'yadisk',
    ]


def test_present_in_freeze_updates_version_and_sets_condition(proj):
    """Windows: пакет есть во freeze — версия новая, условие поставлено (даже если не было)."""
    freeze = LINUX_FREEZE.replace(
        'pydantic==2.12.5\n',
        'altgraph==0.18.0\npydantic==2.12.5\n',
    ).replace(
        'PySide6==6.9.3\n',
        'pyinstaller==7.0.0\npyinstaller-hooks-contrib==2027.1\nPySide6==6.9.3\n',
    )
    proj.write('requirements.txt', OLD_PROD.replace(COND, ''))   # старый файл — без условий
    assert proj.run(freeze=freeze).returncode == 0
    for name in ('requirements.txt', 'requirements-dev.txt'):
        text = proj.read(name)
        assert f'altgraph==0.18.0{COND}\n' in text
        assert f'pyinstaller==7.0.0{COND}\n' in text
        assert f'pyinstaller-hooks-contrib==2027.1{COND}\n' in text
        assert '0.17.5' not in text and '6.20.0' not in text


def test_windows_only_dependencies_get_condition(proj):
    """pefile и pywin32-ctypes из freeze на Windows записываются с условием; потом Linux их не стирает."""
    proj.write('requirements.txt', OLD_PROD)
    proj.write('requirements-dev.txt', OLD_DEV)
    windows_freeze = LINUX_FREEZE + 'pefile==2024.8.26\npywin32-ctypes==0.2.3\n'
    assert proj.run(freeze = windows_freeze).returncode == 0
    assert f'pefile==2024.8.26{COND}' in proj.read('requirements.txt')
    assert f'pywin32-ctypes==0.2.3{COND}' in proj.read('requirements.txt')
    assert proj.run().returncode == 0
    assert f'pefile==2024.8.26{COND}' in proj.read('requirements.txt')
    assert f'pywin32-ctypes==0.2.3{COND}' in proj.read('requirements-dev.txt')


def test_condition_added_to_legacy_line_missing_in_freeze(proj):
    """В прежнем файле строки без условия, во freeze их нет — условие дописывается, версия цела."""
    proj.write('requirements.txt', OLD_PROD.replace(COND, ''))
    proj.write('requirements-dev.txt', OLD_DEV.replace(COND, ''))
    proj.run()
    assert f'pyinstaller==6.20.0{COND}\n' in proj.read('requirements.txt')
    assert f'pyinstaller==6.20.0{COND}\n' in proj.read('requirements-dev.txt')


def test_editable_line_kept_in_dev_and_dropped_in_prod(proj):
    """`-e git+ssh://…` остаётся в requirements-dev.txt как есть и не попадает в requirements.txt."""
    proj.run()
    assert EGG + '\n' in proj.read('requirements-dev.txt')
    assert 'git+ssh' not in proj.read('requirements.txt')
    assert 'project_med' not in proj.read('requirements.txt')


def test_excluded_by_name_not_by_substring(proj):
    """Тестовые пакеты и плагины pytest не в requirements.txt; чужой пакет с подстрокой — остаётся."""
    freeze = LINUX_FREEZE + 'mypackaging-tools==1.0\nmycoverage-helper==1.0\npytest-xdist==3.0\n'
    proj.run(freeze=freeze)
    prod = proj.read('requirements.txt')
    for gone in ('coverage==', 'packaging==26', 'pytest==', 'pytest-cov', 'pytest-xdist'):
        assert gone not in prod
    assert 'mypackaging-tools==1.0' in prod
    assert 'mycoverage-helper==1.0' in prod
    dev = proj.read('requirements-dev.txt')
    assert 'pytest-xdist==3.0' in dev and 'coverage==7.13.4' in dev


def test_pip_failure_leaves_files_untouched(proj):
    """pip freeze упал — оба файла как были, остатков во временных файлах нет, код возврата не 0."""
    before = {n: (proj.root / n).read_bytes() for n in ('requirements.txt', 'requirements-dev.txt')}
    result = proj.run(fail=True)
    assert result.returncode != 0
    assert {n: (proj.root / n).read_bytes() for n in before} == before
    assert sorted(p.name for p in proj.root.iterdir() if p.name.startswith('.')) == []


def test_empty_freeze_leaves_files_untouched(proj):
    """Пустой вывод pip freeze — ошибка, файлы не тронуты (раньше requirements.txt становился пустым)."""
    before = {n: (proj.root / n).read_bytes() for n in ('requirements.txt', 'requirements-dev.txt')}
    result = proj.run(freeze='')
    assert result.returncode != 0
    assert {n: (proj.root / n).read_bytes() for n in before} == before


def test_second_run_gives_same_files(proj):
    """Повторный запуск (и запуск на результате) даёт те же байты."""
    proj.run()
    first = {n: (proj.root / n).read_bytes() for n in ('requirements.txt', 'requirements-dev.txt')}
    proj.run()
    second = {n: (proj.root / n).read_bytes() for n in first}
    assert first == second


def test_runs_from_any_folder_and_leaves_no_temp_files(proj, tmp_path):
    """Запуск из чужой папки пишет в корень проекта (рядом со scripts/), мусора не остаётся."""
    other = tmp_path / 'другая папка'
    other.mkdir()
    assert proj.run(cwd=other).returncode == 0
    assert 'certifi==2099.1.1' in proj.read('requirements.txt')
    assert list(other.iterdir()) == []
    assert sorted(p.name for p in proj.root.iterdir() if p.name.startswith('.')) == []


def test_crlf_freeze_gives_lf_files(proj):
    """pip freeze с CRLF (Windows) — в файлах только LF."""
    assert proj.run(newline='\r\n').returncode == 0
    for name in ('requirements.txt', 'requirements-dev.txt'):
        assert b'\r' not in (proj.root / name).read_bytes()
    assert 'certifi==2099.1.1\n' in proj.read('requirements.txt')


def test_crlf_old_file_condition_lines_kept(proj):
    """Прежний файл с CRLF: сохранённые строки — без \\r."""
    proj.write('requirements.txt', OLD_PROD, newline='\r\n')
    proj.run()
    assert b'\r' not in (proj.root / 'requirements.txt').read_bytes()
    assert f'pyinstaller==6.20.0{COND}\n' in proj.read('requirements.txt')


def test_no_old_files_ok(proj):
    """Файлов requirements ещё нет — создаются из freeze (условных строк нет, ошибки нет)."""
    (proj.root / 'requirements.txt').unlink()
    (proj.root / 'requirements-dev.txt').unlink()
    assert proj.run().returncode == 0
    assert 'alembic==1.18.4' in proj.read('requirements.txt')
    assert 'pyinstaller' not in proj.read('requirements.txt')


def test_conditions_parse_as_pep508_markers(proj):
    """Условия разбираются как PEP 508: на win32 пакет нужен, на linux — нет."""
    requirements = pytest.importorskip('packaging.requirements')
    proj.run()
    for name in ('requirements.txt', 'requirements-dev.txt'):
        found = {}
        for line in proj.read(name).splitlines():
            if line.startswith('-e'):
                continue
            req = requirements.Requirement(line)
            found[req.name] = req
        for pkg in CONDITIONAL:
            marker = found[pkg].marker
            assert marker is not None
            assert marker.evaluate({'sys_platform': 'win32'}) is True
            assert marker.evaluate({'sys_platform': 'linux'}) is False
        assert found['alembic'].marker is None


def test_repo_requirements_have_conditions():
    """Настоящие requirements проекта: условные пакеты с условием, остальные — без."""
    requirements = pytest.importorskip('packaging.requirements')
    for name in ('requirements.txt', 'requirements-dev.txt'):
        for line in (REPO_ROOT / name).read_text(encoding='utf-8').splitlines():
            if line.startswith('-e'):
                continue
            req = requirements.Requirement(line)
            if req.name.lower() in CONDITIONAL:
                assert str(req.marker) == 'sys_platform == "win32"', (name, line)
            else:
                assert req.marker is None, (name, line)
        text = (REPO_ROOT / name).read_text(encoding='utf-8')
        for pkg in CONDITIONAL:
            assert f'\n{pkg}==' in '\n' + text


def test_repo_requirements_are_fixed_point(proj):
    """Freeze, собранный из настоящего dev-файла без условных пакетов, возвращает тот же файл."""
    proj.write('requirements.txt', (REPO_ROOT / 'requirements.txt').read_text(encoding='utf-8'))
    proj.write('requirements-dev.txt', (REPO_ROOT / 'requirements-dev.txt').read_text(encoding='utf-8'))
    freeze = ''.join(
        line.split(';')[0] + '\n'
        for line in (REPO_ROOT / 'requirements-dev.txt').read_text(encoding='utf-8').splitlines()
        if not line.startswith(('pyinstaller', 'altgraph'))
    )
    assert proj.run(freeze=freeze).returncode == 0
    assert proj.read('requirements-dev.txt') == (REPO_ROOT / 'requirements-dev.txt').read_text(encoding='utf-8')
