# tests/test_database_shema/test_orm_only.py

"""
Р-1 (Ф1.6.7г): изменения данных — только через ORM. Массовые запросы мимо ORM
(``query(...).delete()`` / ``.update()``, ``sqlalchemy.delete/update/insert``, ``bulk_*``,
сырой ``DELETE`` / ``UPDATE`` / ``INSERT``) не вызывают события таблиц: строка исчезнет, а
действия (сборщик мусора, удаление файла фото) не сработают. Тест ищет такие вызовы в коде
программы; миграции — исключение (у них свои правила, модели не импортируются).
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Где искать и что пропускать
SOURCES = ('app', 'parsers', 'interfaces')
ALLOWED = (
    'app/database/migrate.py',          # миграции: DDL и служебные запросы
    'app/database/migrations/',         # файлы миграций
)

PATTERNS = (
    re.compile(r'\.query\(.*\)\.(delete|update)\('),                      # Query.delete / update
    re.compile(r'\b(sa|sqlalchemy)\.(delete|update|insert)\('),           # sa.delete(...)
    re.compile(r'from\s+sqlalchemy\s+import\s+[^\n]*\b(delete|update|insert)\b'),
    re.compile(r'\bbulk_(save|insert|update)_'),                          # Session.bulk_*
    re.compile(r'["\']\s*(DELETE\s+FROM|UPDATE\s+\w+\s+SET|INSERT\s+INTO)\b', re.I),  # сырой SQL
)


def _code_lines(path: Path):
    """
    Строки кода без комментариев (закомментированный старый код — не в счёт) и без строк
    примеров докстрингов (``>>>`` / ``...``).
    """
    for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        if line.lstrip().startswith(('>>>', '...')):
            continue
        stripped = line.split('#', 1)[0] if not line.lstrip().startswith('#') else ''
        if stripped.strip():
            yield number, stripped


def test_no_data_changes_bypassing_orm():
    found = []
    for source in SOURCES:
        for path in (ROOT / source).rglob('*.py'):
            relative = path.relative_to(ROOT).as_posix()
            if any(relative.startswith(allowed) for allowed in ALLOWED):
                continue
            for number, line in _code_lines(path):
                if any(pattern.search(line) for pattern in PATTERNS):
                    found.append(f"{relative}:{number}: {line.strip()}")
    assert not found, 'изменения мимо ORM (события таблиц не сработают):\n' + '\n'.join(found)


def test_patterns_catch_known_bypasses():
    samples = (
        'session.query(Note).filter(Note.id == 1).delete()',
        'session.query(Note).update({"text": ""})',
        'session.execute(sa.delete(Note))',
        'from sqlalchemy import select, delete',
        'session.bulk_save_objects(rows)',
        'conn.execute(text("DELETE FROM appointments_notes"))',
        "conn.exec_driver_sql('UPDATE patients SET phone = NULL')",
    )
    for sample in samples:
        assert any(pattern.search(sample) for pattern in PATTERNS), sample
