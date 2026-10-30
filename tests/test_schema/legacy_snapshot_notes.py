# tests/test_schema/legacy_snapshot_notes.py

"""
Снимок написанных вручную модели, DTO и field_configs (_dev/tools/schema_snapshot.py).
Сгенерированное из описания таблицы обязано с ним совпадать. Не пересоздавать.
"""

SNAPSHOT = {'models': {'AppointmentNote': {'table': 'appointments_notes',
                                'comment': 'Таблица заметок приёмов',
                                'dialect': {'sqlite_autoincrement': True},
                                'columns': [('id',
                                             'Integer()',
                                             False,
                                             True,
                                             [],
                                             'Уникальный идентификатор заметки',
                                             False),
                                            ('text', 'Text()', False, False, [], 'Текст заметки', False),
                                            ('created_at',
                                             'DateTime()',
                                             True,
                                             False,
                                             [],
                                             'Дата и время создания заметки',
                                             True)],
                                'indexes': [('ix_appointment_note_text', ('text',), False)],
                                'relationships': [('appointments',
                                                   'Appointment',
                                                   'ONETOMANY',
                                                   "['merge', 'save-update']",
                                                   'note',
                                                   ('note_id',))]}},
 'dtos': {'AppointmentNoteDTO': [('id', 'Optional[int]', 'None', 'ID заметки (None для новой)'),
                                 ('text', "<class 'str'>", 'PydanticUndefined', 'Содержимое заметки')]},
 'configs': {'NOTE_CONFIG': [('id', {'title': 'ID', 'editable': False, 'hidden': True, 'updatable': False}),
                             ('text',
                              {'title': 'Текст заметки',
                               'editable': True,
                               'required': True,
                               'widget_type': 'textarea',
                               'init_from_extra': 'text'})]}}
