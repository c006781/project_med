# _dev/tools/schema_snapshot.py

"""
Снимок моделей, DTO и ``field_configs`` (как данные) — для проверки «сгенерированное из
описания таблицы совпадает с написанным вручную» (``app/schema``).

Как пользоваться при переводе таблицы на описание (`_dev/КАРТА.md` Ф1.3.2 — заметки):
    1. ДО переключения (пока классы написаны вручную) снять снимок:
       python -X utf8 _dev/tools/schema_snapshot.py AppointmentNote AppointmentNoteDTO NOTE_CONFIG \
           tests/test_schema/legacy_snapshot_notes.py
    2. Тест сравнивает со снимком то, что строит ``TableDef`` (образец —
       ``tests/test_schema/test_clinic_defs.py``: функции ``model_snapshot``,
       ``dto_snapshot``, ``config_snapshot`` — те же, что здесь).
    3. После переключения снимок НЕ пересоздавать — он фиксирует прежнее.

Аргументы: имена модели (``app.database.database_shema.clinic``), DTO (``app.dto.dto_all``),
настроек (``app.dto.field_configs``) и путь файла снимка. Временные ``.env``/конфиг — как у
тестов (рабочие файлы не трогаются).

Создан 2026-10-19 (снимок пациентов, приёмов, фото), обобщён и перенесён 2026-10-25.
"""

import os
import pprint
import sys
import tempfile
from typing import Any, Dict, List, Tuple

ROOT: str = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ['PROJECT_MED_ENV_DIR'] = tempfile.mkdtemp(prefix='schema_snapshot_')
os.environ['APP_CONFIG_PATH'] = os.path.join(os.environ['PROJECT_MED_ENV_DIR'], 'config.msgpack')
sys.path.insert(0, ROOT)

from app.database.database_shema import clinic as models  # noqa: E402
from app.dto import dto_all, field_configs  # noqa: E402


def model_snapshot(model: Any) -> Dict[str, Any]:
    """
    Схема модели как данные: таблица, комментарий, параметры диалекта, столбцы, индексы, связи.

    Args:
        model: Класс модели SQLAlchemy.

    Returns:
        Словарь для сравнения.

    Пример:
        >>> model_snapshot(models.Patient)['table']
        'patients'
    """
    table = model.__table__
    return {
        'table': table.name,
        'comment': table.comment,
        'dialect': dict(table.dialect_kwargs),
        'columns': [(c.name, repr(c.type), c.nullable, c.primary_key,
                     sorted(fk.target_fullname for fk in c.foreign_keys), c.comment, c.default is not None)
                    for c in table.columns],
        'indexes': sorted((i.name, tuple(c.name for c in i.columns), i.unique) for i in table.indexes),
        'relationships': sorted((r.key, r.mapper.class_.__name__, r.direction.name, str(sorted(r.cascade)),
                                 r.back_populates, tuple(sorted(c.name for c in r._calculated_foreign_keys)))
                                for r in model.__mapper__.relationships),
    }


def dto_snapshot(dto: Any) -> List[Tuple[str, str, str, Any]]:
    """
    Поля DTO как данные: имя, тип, умолчание, описание — в порядке объявления.

    Args:
        dto: Класс Pydantic.

    Returns:
        Список кортежей.

    Пример:
        >>> dto_snapshot(dto_all.PatientDTO)[0][0]
        'id'
    """
    return [(name, str(f.annotation).replace('typing.', ''), repr(f.default), f.description)
            for name, f in dto.model_fields.items()]


def config_snapshot(config: Dict[str, Any]) -> List[Tuple[str, Any]]:
    """
    Настройки полей как данные (функции заменяются на ``'<fn>'``), в порядке ключей.

    Args:
        config: Словарь ``field_configs``.

    Returns:
        Список «поле → настройки».

    Пример:
        >>> config_snapshot({'id': {'title': 'ID'}})
        [('id', {'title': 'ID'})]
    """
    def clean(value: Any) -> Any:
        """
        Заменяет функции на метку, словари — рекурсивно.

        Args:
            value: Значение настройки.

        Returns:
            Значение без функций.

        Пример:
            >>> clean(len)
            '<fn>'
        """
        if callable(value):
            return '<fn>'
        if isinstance(value, dict):
            return {k: clean(x) for k, x in value.items()}
        return value

    return [(k, clean(v)) for k, v in config.items()]


if __name__ == '__main__':
    if len(sys.argv) != 5:
        sys.exit('аргументы: <Модель> <DTO> <НАСТРОЙКИ> <файл снимка>')
    model_name, dto_name, config_name, out = sys.argv[1:]
    snapshot = {
        'models': {model_name: model_snapshot(getattr(models, model_name))},
        'dtos': {dto_name: dto_snapshot(getattr(dto_all, dto_name))},
        'configs': {config_name: config_snapshot(getattr(field_configs, config_name))},
    }
    with open(out, 'w', encoding='utf-8') as f:
        f.write(f'# {out}\n\n')
        f.write('"""\nСнимок написанных вручную модели, DTO и field_configs (_dev/tools/schema_snapshot.py).\n'
                'Сгенерированное из описания таблицы обязано с ним совпадать. Не пересоздавать.\n"""\n\n')
        f.write('SNAPSHOT = ' + pprint.pformat(snapshot, width=110, sort_dicts=False) + '\n')
    print('снимок:', out)
