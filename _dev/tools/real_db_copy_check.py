# _dev/tools/real_db_copy_check.py

"""
Сверка моделей программы со схемой КОПИИ рабочей базы и пробная миграция этой копии.

Рабочая ``clinic.db`` только копируется (чтение); всё остальное — с копией во временной
папке: различия «модели ↔ база» (Alembic ``compare_metadata``), миграция копии
(``upgrade_database``), различия после миграции, изменения моделей без миграции, число
записей до и после. Нужна перед первым запуском новой версии на рабочей базе
(`_dev/КАРТА.md` Ф3.6) и после правок моделей.

Запуск (из корня проекта):
    Windows: .venv310/Scripts/python.exe -X utf8 _dev/tools/real_db_copy_check.py [путь к базе]
    Linux:   <venv>/bin/python -X utf8 _dev/tools/real_db_copy_check.py [путь к базе]
По умолчанию — ``clinic.db`` в корне проекта.

Ожидаемо: «различий после: 0», «изменения моделей без миграции: 0», числа записей до и
после совпадают. Создан 2026-10-19 (сессия Windows), перенесён в _dev/tools 2026-10-25.
"""

import os
import shutil
import sys
import tempfile
from typing import Dict

ROOT: str = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
source: str = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'clinic.db')

# Временные настройки — ДО импорта приложения
work: str = tempfile.mkdtemp(prefix='db_copy_check_')
os.environ['PROJECT_MED_ENV_DIR'] = work
os.environ['APP_CONFIG_PATH'] = os.path.join(work, 'config.msgpack')
sys.path.insert(0, ROOT)
copy: str = os.path.join(work, 'clinic.db')
shutil.copy(source, copy)

import sqlalchemy as sa  # noqa: E402
from alembic.autogenerate import compare_metadata  # noqa: E402
from alembic.migration import MigrationContext  # noqa: E402

from app.database.database_shema.clinic import Base  # noqa: E402
from app.database.migrate import pending_model_changes, schema_differences, upgrade_database  # noqa: E402


def counts(engine: sa.engine.Engine) -> Dict[str, int]:
    """
    Число записей в основных таблицах.

    Args:
        engine: Движок копии базы.

    Returns:
        Словарь «таблица → число строк».

    Пример:
        >>> counts(engine)
        {'patients': 20, 'appointments': 47, 'photos': 21, 'appointments_notes': 495}
    """
    with engine.connect() as conn:
        return {
            table: conn.execute(sa.text(f'select count(*) from {table}')).scalar()
            for table in ('patients', 'appointments', 'photos', 'appointments_notes')
        }


engine = sa.create_engine(f'sqlite:///{copy}')
before = counts(engine)
with engine.connect() as conn:
    ctx = MigrationContext.configure(conn, opts={'compare_type': True})
    diff = [
        d for d in compare_metadata(ctx, Base.metadata)
        if not (isinstance(d, tuple) and d[0] == 'remove_table' and d[1].name == 'alembic_version')
    ]
print('копия:', copy)
print('различий до миграции:', len(diff))
for d in diff:
    print('  ', d)
print('ревизия после миграции копии:', upgrade_database(engine, backup=False))
print('различий после:', len(schema_differences(engine)))
print('изменения моделей без миграции:', len(pending_model_changes()))
after = counts(engine)
print('записей до:', before)
print('записей после:', after, '| совпадают:', before == after)
