# app/schema/clinic.py

"""
Таблицы клиники — одно описание на таблицу: из него модель SQLAlchemy, DTO,
``field_configs`` и наборы данных экрана (``app/tables``).

Описание повторяет таблицы, существовавшие до описаний, один в один (столбцы, типы,
комментарии, индексы, связи, поля и порядок DTO, настройки полей и их порядок) — это
проверяет тест ``tests/test_schema/test_clinic_defs.py``.

Добавить таблицу: описание ``TableDef`` здесь (поля — ``key``, ``column``, ``note``, ``fk``,
``children``, ``computed``, ``timestamp``) и строка в ``CLINIC_DEFS``. Модель, DTO,
настройки полей, миграция (автомиграции), черновики, наборы, экран — по описанию.

Общие заметки (``NOTES``) — тоже описание, но не в ``CLINIC_DEFS``: из него строятся модель,
DTO и настройки заметок; строки реестра наборов у заметок пока нет (ПЛАН Ф1.3.4).

Пример:
    >>> [d.name for d in CLINIC_DEFS]
    ['patients', 'appointments', 'photos']
    >>> NOTES.name
    'appointments_notes'
"""

from __future__ import annotations

import os
from typing import Any, Mapping, Optional

import sqlalchemy as sa

from .define import TableDef, children, column, computed, fk, key, note, timestamp
from .extras import calc, mark, total


def patient_full_name(patient: Any) -> str:
    """
    ФИО пациента из заполненных частей (для ``compute`` у приёма).

    Args:
        patient: Объект пациента.

    Returns:
        «Фамилия Имя Отчество» без пустых частей.

    Пример:
        >>> patient_full_name(SimpleNamespace(last_name='Петров', first_name='Иван', middle_name=None))
        'Петров Иван'
    """
    return " ".join(part for part in (patient.last_name, patient.first_name, patient.middle_name) if part)


def photo_count_text(count: Any) -> str:
    """
    Число фото у приёма текстом: «N фото» или «❌».

    Args:
        count: Число фото.

    Returns:
        Текст.

    Пример:
        >>> photo_count_text(3), photo_count_text(0)
        ('3 фото', '❌')
    """
    return f"{count} фото" if count else '❌'


def photo_image(row: Mapping[str, Any], service: Any) -> Optional[str]:
    """
    Полный путь снимка строки фото (для предпросмотра): в БД путь — относительно папки
    снимков сервиса; у нового фото (черновик) путь уже полный.

    Args:
        row: Строка фото.
        service: Сервис фото (его папка снимков).

    Returns:
        Путь или ``None``.

    Пример:
        >>> photo_image({'file_path': 'app_1/a.png'}, photo_service)
        'C:/data/photos/app_1/a.png'
    """
    path = row.get('file_path')
    if not path:
        return None
    if os.path.isabs(path):
        return path
    return os.path.join(getattr(service, '_storage_path', None) or '', path)


PATIENTS = TableDef(
    'patients', 'Patient', 'PatientDTO',
    doc='Пациент клиники.', comment='Таблица пациентов',
    entity='patient', title='Пациенты', label='Пациент',
    fields=(
        key('Уникальный идентификатор пациента', dto_desc='ID пациента (None для нового)', order=0),
        column('last_name', sa.String(50), 'Фамилия', nullable=False, index='ix_patient_last_name',
               comment='Фамилия пациента', dto_desc='Фамилия',
               editable=True, order=1, required=True, autocomplete=True),
        column('first_name', sa.String(50), 'Имя', nullable=False, comment='Имя пациента', dto_desc='Имя',
               editable=True, order=2, required=True, autocomplete=True),
        column('middle_name', sa.String(50), 'Отчество', comment='Отчество пациента', dto_desc='Отчество',
               editable=True, order=3, autocomplete=True),
        column('birth_date', sa.Date(), 'Дата рождения', comment='Дата рождения',
               dto_desc='Дата рождения (ГГГГ-ММ-ДД)',
               editable=True, widget_type='date', order=4),
        # ↑ до 2026-10-31 (ТД-14): required=True — создание пустую дату пропускало, изменение
        #   нет: пациента без даты нельзя было ни поправить, ни объединить. Решение владельца
        #   2026-10-31: дата пока необязательна (позже — маска ввода); в ключе дублей остаётся.
        column('phone', sa.String(20), 'Телефон', comment='Номер телефона', dto_desc='Номер телефона',
               editable=True, order=5, input_mask='+7 (999) 999-99-99'),
        note('description', 'Описание', comment='ID заметки с описанием пациента', id_title='ID описания',
             dto_desc='Описание пациента (виртуальное)', order=6),
        note('comment', 'Комментарий', comment='ID заметки с комментарием к пациенту',
             id_title='ID комментария', dto_desc='Комментарий к пациенту (виртуальное)', order=7),
        children('appointments', 'Appointment', 'patient', dto=False, config=False),
        timestamp('created_at', 'Дата создания'),
    ),
    column_order=('id', 'first_name', 'middle_name', 'last_name', 'birth_date', 'phone',
                  'description_id', 'comment_id', 'created_at'),
    dto_order=('id', 'first_name', 'middle_name', 'last_name', 'birth_date', 'phone',
               'description_text', 'comment_text', 'description_id', 'comment_id'),
    config_order=('id', 'last_name', 'first_name', 'middle_name', 'birth_date', 'phone',
                  'description_id', 'comment_id', 'description_text', 'comment_text'),
    order=('last_name', 'first_name', 'id'),
    columns=('mark', 'last_name', 'first_name', 'middle_name', 'birth_date', 'phone', 'visits'),
    form=('last_name', 'first_name', 'middle_name', 'birth_date', 'phone',
          'description_text', 'comment_text'),
    # итоги считает БД отдельным запросом (GROUP BY по подчинённой таблице)
    extras=(mark(), total('visits', 'Приёмов', 'appointments', by='sql')),
)

APPOINTMENTS = TableDef(
    'appointments', 'Appointment', 'AppointmentDTO',
    doc='Приём пациента.', comment='Таблица приёмов',
    entity='appointment', title='Приёмы', label='Приём',
    fields=(
        key('Уникальный идентификатор приёма', dto_desc='ID приёма (None для нового)'),
        fk('patient_id', 'patients', 'Patient', title='ID пациента', nullable=False, relation='patient',
           back='appointments', index='ix_patient_id', comment='ID пациента (внешний ключ)',
           dto_desc='ID пациента',
           editable=False, hidden=False, order=1, init_from_extra='patient_id', required=True,
           updatable=True),
        note('reason', 'Причина обращения', comment='ID заметки с причиной обращения',
             id_title='ID причины', dto_desc='Причина обращения'),
        note('procedure', 'Выполненная процедура', comment='ID заметки с выполненной процедурой',
             id_title='ID процедуры', dto_desc='Выполненная процедура'),
        note('recommendations', 'Рекомендации', comment='ID заметки с рекомендациями',
             id_title='ID рекомендаций', dto_desc='Рекомендации'),
        note('note', 'Примечание', comment='ID заметки с примечанием', id_title='ID примечания',
             relation='note', dto_desc='Примечание'),
        note('cost_procedure', 'Стоимость процедуры', comment='ID заметки со стоимостью процедуры',
             id_title='ID стоимости процедуры', dto_desc='Стоимость процедуры'),
        computed('patient_name', 'Пациент', dto_desc='Имя пациента',
                 editable=False, virtual=True, source_attr='patient',
                 compute={'func': patient_full_name, 'args': ['patient']}),
        column('date', sa.Date(), 'Дата приёма', nullable=False, index='ix_appointment_date',
               comment='Дата приёма', dto_desc='Дата приёма',
               editable=True, widget_type='date', required=True),
        column('date_next', sa.Date(), 'Дата следующего приёма', comment='Дата следующего приёма',
               dto_desc='Дата следующего приёма', editable=True, widget_type='date'),
        children('photos', 'Photo', 'appointment', child_dto='PhotoDTO', dto_desc='Фотографии приёма',
                 title='Фотографии', editable=True, virtual=True, widget_type='photo_uploader',
                 eager_load=False, eager_load_detail=True),
        computed('has_photos', 'Фото', dto_desc='Наличие фото',
                 editable=False, virtual=True, order=0, source_attr='photos', eager_load=False,
                 width={'fixed': 80},
                 sql_compute={'func': 'COUNT', 'relation': 'photos', 'result_type': 'int',
                              'extra_key': 'photo_count',
                              'formatter': lambda count: f"{count} фото" if count > 0 else '❌'}),
        timestamp('created_at', 'Дата и время создания записи'),
    ),
    column_order=('id', 'patient_id', 'date', 'reason_id', 'procedure_id', 'recommendations_id',
                  'date_next', 'note_id', 'cost_procedure_id', 'created_at'),
    dto_order=('id', 'patient_id', 'patient_name', 'date', 'date_next', 'reason_text', 'procedure_text',
               'recommendations_text', 'note_text', 'cost_procedure_text', 'reason_id', 'procedure_id',
               'recommendations_id', 'note_id', 'cost_procedure_id', 'photos', 'has_photos'),
    config_order=('id', 'patient_id', 'reason_id', 'procedure_id', 'recommendations_id', 'note_id',
                  'cost_procedure_id', 'patient_name', 'date', 'reason_text', 'procedure_text',
                  'recommendations_text', 'date_next', 'note_text', 'cost_procedure_text', 'photos',
                  'has_photos'),
    order=('-date', '-id'),
    columns=('mark', 'date', 'reason_text', 'date_next', 'photo_count'),
    form=('date', 'date_next', 'reason_text', 'procedure_text', 'recommendations_text',
          'note_text', 'cost_procedure_text'),
    extras=(mark(), total('photo_count', 'Фото', 'photos', display=photo_count_text, by='sql')),
    # has_photos (подзапрос в запросе приёмов) — для старых экранов; наборам — photo_count
    skip=('has_photos',),
)

PHOTOS = TableDef(
    'photos', 'Photo', 'PhotoDTO',
    doc='Фотография к приёму.', comment='Таблица фотографий приёмов',
    entity='photo', title='Фото', label='Фото',
    fields=(
        key('Уникальный идентификатор фотографии', dto_desc='ID фотографии'),
        fk('appointment_id', 'appointments', 'Appointment', title='ID приёма', nullable=False,
           relation='appointment', back='photos', index='ix_photo_appointment',
           comment='ID приёма, к которому относится фото', dto_desc='ID приёма, к которому относится фото',
           editable=False, hidden=True, required=True, updatable=True),
        column('file_path', sa.String(500), 'Файл', nullable=False,
               comment='Относительный путь к файлу на диске', dto_desc='Относительный путь к файлу',
               required=True, widget_type='image_thumbnail', description_field='description'),
        column('description', sa.String(200), 'Описание', comment='Описание фотографии',
               dto_desc='Описание фотографии',
               editable=True, updatable=True, widget_type='textarea', width={'stretch': True}),
        timestamp('uploaded_at', 'Дата и время загрузки'),
    ),
    order=('id',),
    columns=('mark', 'file_path', 'description'),
    form=('image', 'description'),
    extras=(mark(), calc('image', 'Снимок', photo_image, visible=False, widget='image')),
)

# Общие заметки: текст, на который ссылаются поля note() других таблиц (переиспользуемый).
# Совпадает с прежним AppointmentNote / AppointmentNoteDTO / NOTE_CONFIG один в один (снимок
# tests/test_schema/legacy_snapshot_notes.py).
NOTES = TableDef(
    'appointments_notes',                               # таблица (define.NOTES_TABLE)
    'AppointmentNote',                                  # модель (define.NOTES_MODEL)
    'AppointmentNoteDTO',                               # DTO
    doc         =   'Заметка: общий текст, на который ссылаются поля-заметки других таблиц.',
    comment     =   'Таблица заметок приёмов',          # комментарий таблицы в БД
    entity      =   'note',                             # тип записи (сервис — get_note_service)
    title       =   'Заметки',                          # заголовок экрана
    label       =   'Заметка',                          # одна запись
    fields      =   (
        key(
            'Уникальный идентификатор заметки',         # комментарий столбца
            dto_desc        =   'ID заметки (None для новой)',  # описание поля DTO
        ),
        column(
            'text',                                     # имя
            sa.Text(),                                  # тип
            'Текст заметки',                            # подпись
            nullable        =   False,                  # NOT NULL, обязательное поле DTO
            index           =   'ix_appointment_note_text',  # индекс по тексту (поиск повторов)
            comment         =   'Текст заметки',        # комментарий столбца
            dto_desc        =   'Содержимое заметки',   # описание поля DTO
            editable        =   True,                   # правится
            required        =   True,                   # обязательное (проверка сервисом)
            widget_type     =   'textarea',             # многострочный редактор
            init_from_extra =   'text',                 # значение при переходе на страницу
        ),
        timestamp(
            'created_at',                               # имя
            'Дата и время создания заметки',            # комментарий столбца
        ),
        children(
            'appointments',                             # приёмы, ссылающиеся на заметку
            'Appointment',                              # модель приёма
            'note',                                     # связь приёма с заметкой (поле note)
            cascade         =   None,                   # заметка — не владелец: без каскада удаления
            foreign_keys    =   '[Appointment.note_id]',  # из пяти ключей приёма на заметки — note_id
            dto             =   False,                  # не в DTO
            config          =   False,                  # не в настройках
        ),
    ),
)

# NOTES — НЕ в CLINIC_DEFS (решение 2026-10-30): CLINIC_DEFS — реестр наборов данных экранов
# (app/tables); заметки там станут ссылками в реестре черновиков — ПЛАН Ф1.3.4 (М15), тогда и
# решить, нужна ли заметкам строка реестра. Модель, DTO и настройки заметок строятся из NOTES
# напрямую (app/database/database_shema/clinic.py, app/dto).
CLINIC_DEFS = (PATIENTS, APPOINTMENTS, PHOTOS)
