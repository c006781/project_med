# tests/test_linux_env/test_linux_env_scripts.py

"""
Скрипты scripts/*.sh на Linux: бит запуска, запуск из другой папки, путь с пробелом и кириллицей.

Всё во временных папках: копия файлов проекта с отдельным git (без remote), заглушка ``pip`` в
PATH, заглушка интерпретатора для ``setup_*.sh``. Настоящий выпуск и установка пакетов не
запускаются.
"""

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]   # корень проекта
SCRIPTS = REPO_ROOT / 'scripts'                    # папка скриптов
EXECUTABLE = ('pip_freeze.sh', 'pip_install_freeze.sh', 'release.sh', 'setup_dev.sh', 'setup_prod.sh')

pytestmark = pytest.mark.skipif(
    os.name == 'nt' or shutil.which('bash') is None or shutil.which('git') is None,
    reason='проверка bash-скриптов на Linux (на Windows — вручную в Git Bash)',
)


def _make_executable(path: Path, text: str) -> None:
    path.write_text(text, encoding='utf-8')
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


@pytest.mark.parametrize('name', EXECUTABLE)
def test_scripts_have_exec_bit_in_git_and_on_disk(name):
    """У скриптов запуска бит +x в индексе git и в рабочей копии (`./scripts/<имя>` работает)."""
    out = subprocess.run(
        ['git', 'ls-files', '-s', '--', f'scripts/{name}'],
        cwd=str(REPO_ROOT), capture_output=True, text=True,
    ).stdout
    assert out.startswith('100755'), out
    assert os.access(SCRIPTS / name, os.X_OK)


@pytest.fixture
def project(tmp_path):
    """Копия scripts/, requirements*.txt и VERSION в папке с пробелом и кириллицей, свой git."""
    root = tmp_path / 'Проект Мед' / 'копия'
    (root / 'scripts').mkdir(parents=True)
    for f in list(SCRIPTS.glob('*.sh')) + [SCRIPTS / 'version.py']:
        shutil.copy(f, root / 'scripts' / f.name)
    for name in ('requirements.txt', 'requirements-dev.txt', 'VERSION'):
        shutil.copy(REPO_ROOT / name, root / name)
    for f in (root / 'scripts').glob('*.sh'):   # бита запуска у копии нет: скрипты зовутся через bash
        f.chmod(0o644)
    env = dict(os.environ, GIT_CONFIG_GLOBAL='/dev/null')
    for cmd in (
        ['git', 'init', '-q'], ['git', 'config', 'user.email', 't@t'], ['git', 'config', 'user.name', 't'],
        ['git', 'add', '-A'], ['git', 'commit', '-qm', 'init'],
    ):
        subprocess.run(cmd, cwd=str(root), env=env, check=True)
    return root


@pytest.fixture
def stub_bin(tmp_path):
    """Папка с заглушкой pip: печатает заданный вывод freeze (файл в STUB_PIP_FREEZE)."""
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    _make_executable(bin_dir / 'pip', '#!/bin/bash\ncat "$STUB_PIP_FREEZE"\n')
    return bin_dir


def test_release_runs_from_other_folder_without_exec_bit(project, stub_bin, tmp_path):
    """release.sh без бита у pip_freeze.sh, из чужой папки: коммит зависимостей, версия, тег."""
    freeze = tmp_path / 'freeze.txt'
    freeze.write_text('alembic==1.18.4\ncertifi==2099.1.1\n', encoding='utf-8')
    env = dict(
        os.environ,
        PATH=f'{stub_bin}{os.pathsep}{os.environ["PATH"]}',
        STUB_PIP_FREEZE=str(freeze),
        PROJECT_MED_PYTHON=sys.executable,
    )
    env.pop('VIRTUAL_ENV', None)
    other = tmp_path / 'чужая папка'
    other.mkdir()
    result = subprocess.run(
        ['bash', str(project / 'scripts' / 'release.sh'), 'patch'],
        cwd=str(other), env=env, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    log = subprocess.run(
        ['git', 'log', '--format=%s'], cwd=str(project), capture_output=True, text=True,
    ).stdout.splitlines()
    assert log[:2] == ['Bump version to 1.0.1', 'Обновление зависимостей']
    tags = subprocess.run(['git', 'tag'], cwd=str(project), capture_output=True, text=True).stdout
    assert tags.split() == ['v1.0.1']
    assert (project / 'VERSION').read_text().strip() == '1.0.1'


def test_release_commits_both_requirement_files(project, stub_bin, tmp_path):
    """Коммит зависимостей содержит оба файла, рабочая копия после выпуска чистая."""
    freeze = tmp_path / 'freeze.txt'
    freeze.write_text('alembic==1.18.4\ncertifi==2099.1.1\n', encoding='utf-8')
    env = dict(
        os.environ,
        PATH=f'{stub_bin}{os.pathsep}{os.environ["PATH"]}',
        STUB_PIP_FREEZE=str(freeze),
        PROJECT_MED_PYTHON=sys.executable,
    )
    env.pop('VIRTUAL_ENV', None)
    result = subprocess.run(
        ['bash', str(project / 'scripts' / 'release.sh'), 'patch'],
        cwd=str(project), env=env, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    files = subprocess.run(
        ['git', 'show', '--name-only', '--format=', 'HEAD~1'],
        cwd=str(project), capture_output=True, text=True,
    ).stdout.split()
    assert files == ['requirements-dev.txt', 'requirements.txt']
    status = subprocess.run(
        ['git', 'status', '--porcelain'],
        cwd=str(project), capture_output=True, text=True,
    ).stdout
    assert status == ''


def test_release_rejects_unknown_part_before_any_commit(project, stub_bin, tmp_path):
    """Неверная часть версии — отказ до коммита зависимостей."""
    result = subprocess.run(
        ['bash', str(project / 'scripts' / 'release.sh'), 'foo'],
        cwd=str(project), capture_output=True, text=True,
    )
    assert result.returncode == 1
    log = subprocess.run(['git', 'log', '--format=%s'], cwd=str(project), capture_output=True, text=True)
    assert log.stdout.split('\n')[0] == 'init'


@pytest.fixture
def fake_python(tmp_path):
    """Заглушка интерпретатора: `-c` — успех, `--version`, `-m venv <папка>` — каркас venv с pip-заглушкой."""
    path = tmp_path / 'fakepython'
    _make_executable(path, '''#!/bin/bash
case "$1" in
  -c) exit 0 ;;
  --version) echo "Python 3.11.99 (stub)" ;;
  -m) mkdir -p "$3/bin"
      printf '#!/bin/bash\\necho "$*" >> "$(dirname "$BASH_SOURCE")/../pip.log"\\n' > "$3/bin/pip"
      chmod +x "$3/bin/pip"
      printf '#!/bin/bash\\nshift 2\\necho "$*" >> "$(dirname "$BASH_SOURCE")/../pip.log"\\n' > "$3/bin/python"
      chmod +x "$3/bin/python"
      printf 'export PATH="%s/bin:$PATH"\\n' "$3" > "$3/bin/activate" ;;
esac
''')
    return path


@pytest.mark.parametrize('script,installs', [
    ('setup_dev.sh', ['requirements.txt', 'requirements-dev.txt']),
    ('setup_prod.sh', ['requirements.txt']),
])
def test_setup_from_other_folder_uses_project_root(project, fake_python, tmp_path, script, installs):
    """setup_*.sh из чужой папки: venv и requirements — в корне проекта, не в текущей папке."""
    other = tmp_path / 'чужая папка'
    other.mkdir()
    result = subprocess.run(
        ['bash', str(project / 'scripts' / script), '--python', str(fake_python)],
        cwd=str(other), capture_output=True, text=True, input='',
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert (project / 'venv_project_med' / 'bin' / 'activate').exists()
    assert list(other.iterdir()) == []
    log = (project / 'venv_project_med' / 'pip.log').read_text(encoding='utf-8').splitlines()
    assert log[0] == 'install --upgrade pip'
    assert log[1:] == [f'install -r {project / name}' for name in installs]


def test_setup_prod_archive_layout(project, fake_python, tmp_path):
    """Архив: setup_prod.sh и find_python.sh лежат рядом с requirements.txt — venv создаётся там же."""
    archive = tmp_path / 'архив с пробелом'
    archive.mkdir()
    for name in ('setup_prod.sh', 'find_python.sh'):
        shutil.copy(SCRIPTS / name, archive / name)
    shutil.copy(REPO_ROOT / 'requirements.txt', archive / 'requirements.txt')
    result = subprocess.run(
        ['bash', str(archive / 'setup_prod.sh')],
        cwd=str(tmp_path), capture_output=True, text=True,
        env=dict(os.environ, PROJECT_MED_PYTHON=str(fake_python)),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert (archive / 'venv_project_med' / 'bin' / 'activate').exists()


def test_setup_prod_folder_with_dollar_in_name(fake_python, tmp_path):
    """Папка с $ в имени: пакеты ставит интерпретатор окружения, путь не разворачивается оболочкой."""
    archive = tmp_path / 'Папка $HOME'
    archive.mkdir()
    for name in ('setup_prod.sh', 'find_python.sh'):
        shutil.copy(SCRIPTS / name, archive / name)
    (archive / 'requirements.txt').write_text('', encoding='utf-8')
    result = subprocess.run(
        ['bash', str(archive / 'setup_prod.sh'), '--python', str(fake_python)],
        cwd=str(tmp_path), capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    log = (archive / 'venv_project_med' / 'pip.log').read_text(encoding='utf-8').splitlines()
    assert log == ['install --upgrade pip', f'install -r {archive / "requirements.txt"}']


def test_setup_prod_bad_python_fails_without_venv(project, tmp_path):
    """Неверный --python — ошибка с понятным сообщением и без venv."""
    result = subprocess.run(
        ['bash', str(project / 'scripts' / 'setup_prod.sh'), '--python', '/нет/такого'],
        cwd=str(tmp_path), capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert "интерпретатор '/нет/такого' не найден" in result.stderr
    assert not (project / 'venv_project_med').exists()
