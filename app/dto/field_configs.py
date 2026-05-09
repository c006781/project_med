# app/dto/field_configs.py

"""
Общая конфигурация полей для форм и таблиц.

Содержит словари для каждой сущности, описывающие отображение, редактируемость,
виджеты, источники данных для выпадающих списков и т.д.

Структура словаря (каждый ключ – имя поля, значение – словарь с параметрами):
    - title (str): Заголовок поля в форме или таблице.
    - editable (bool): Можно ли редактировать поле.
    - hidden (bool): Скрыть поле в форме (но виджет остаётся).
    - order (int): Порядок колонки в таблице (сортировка).
    - required (bool): Обязательное поле (пока не используется).
    - widget_type (str): Тип виджета: 'date', 'time', 'textarea', 'completer', 'photo_uploader'.
    - virtual (bool): Виртуальное поле, не хранится в БД.
    - compute (dict): Настройка вычисления виртуального поля (функция, аргументы).
    - init_from_extra (str/True): Ключ в extra_data, из которого нужно взять значение при переходе.
    - choices (list): Список строк для выпадающего списка.
    - choices_provider (str): Имя провайдера для автодополнения (например, 'note_service.get_choices').
    - autocomplete (bool): Включает автодополнение в таблице и форме (для QLineEdit).

Пример:
    >>> from app.dto.field_configs import PATIENT_CONFIG
    >>> PATIENT_CONFIG['first_name']['title']
    'Имя'
"""


from typing import Dict, Any

# from app.dto.compute_fields import get_patient_full_name



# title	str	Заголовок поля в форме или таблице
# editable	bool	Можно ли редактировать поле
# hidden	bool	Скрыть поле в форме (но виджет остаётся)
# order	int	Порядок колонки в таблице (сортировка)
# required	bool	Обязательное ли поле (пока не используется)
# widget_type	str	Тип виджета: 'date', 'time', 'textarea', 'completer', 'completer_with_edit', 'photo_uploader'
# virtual	bool	Виртуальное поле, не хранится в БД
# compute	dict	Настройка вычисления виртуального поля (функция, аргументы)
# init_from_extra	str/True	Ключ в extra_data, из которого нужно взять значение при переходе на страницу
# choices	list	Список строк для выпадающего списка
# choices_provider	str	Имя провайдера для автодополнения (например, 'note_service.get_choices')
# source	str	(не используется) – для указания источника данных
# autocomplete  bool -  включает автодополнение в таблице и форме (lkz QLineEdit)
# Параметр 'widget_type':
#     'textarea' — создаёт QTextEdit для многострочного текста (вместо обычного QLineEdit).
#     'date' — используется как подсказка, чтобы создать QDateEdit (хотя тип поля datetime.date сам по себе ведёт к этому, но widget_type может явно указать виджет даты).
#     'time' — создаёт QTimeEdit для времени.
#     **'completer', 'completer_with_create', 'completer_with_edit'** — создают составной виджет CompleterEdit, состоящий из QLineEditс автодополнением и опциональной кнопки...`, которая открывает отдельное окно для создания/редактирования связанной сущности (например, заметки).
#     По умолчанию (widget_type не задан или 'text') создаётся QLineEdit для обычной строки.



# --- Пациенты ---
# Словарь, описывающий все поля для сущности "Пациент".
PATIENT_CONFIG: Dict[str, Dict[str, Any]] = {
    # Поле "id" – первичный ключ.
    'id': {
        'title': 'ID',               # Заголовок, который будет отображаться в таблице и форме.
        'editable': False,           # Поле нельзя редактировать (только для чтения).
        'hidden': True,              # Поле скрыто в формах (но может использоваться внутри).
        'order': 0,                  # Номер для сортировки колонок в таблице (чем меньше, тем левее).
    },
    # Поле "last_name" – фамилия пациента.
    'last_name': {
        'title': 'Фамилия',          # Отображаемый заголовок.
        'editable': True,            # Поле доступно для редактирования пользователем.
        'order': 1,                  # Сортировка: будет вторым столбцом после ID (если ID видим).
        'required': True,            # Поле обязательно для заполнения (валидация на стороне сервиса).
        'autocomplete': True,        # Включает автодополнение в таблице и форме (источник – уникальные значения столбца).
    },
    # Поле "first_name" – имя пациента.
    'first_name': {
        'title': 'Имя',              # Заголовок.
        'editable': True,            # Редактируемое.
        'order': 2,                  # Порядковый номер колонки.
        'required': True,            # Обязательное поле.
        'autocomplete': True,        # Автодополнение.
    },
    # Поле "middle_name" – отчество пациента.
    'middle_name': {
        'title': 'Отчество',         # Заголовок.
        'editable': True,            # Редактируемое.
        'order': 3,                  # Порядковый номер колонки.
        'autocomplete': True,        # Автодополнение.
    },
    # Поле "birth_date" – дата рождения.
    'birth_date': {
        'title': 'Дата рождения',    # Заголовок.
        'editable': True,            # Редактируемое.
        'widget_type': 'date',       # Тип виджета – календарь (QDateEdit).
        'order': 4,                  # Порядковый номер колонки.
    },
    # Поле "phone" – номер телефона.
    'phone': {
        'title': 'Телефон',          # Заголовок.
        'editable': True,            # Редактируемое.
        'order': 5,                  # Порядковый номер колонки.
        'input_mask': '+7 (999) 999-99-99',   #  маска заполнения данных
    },
    'description_id': {
    'title': 'ID описания',
    'hidden': True,
    },
    'comment_id': {
        'title': 'ID комментария',
        'hidden': True,
    },

    # Виртуальное поле "description" – описание пациента.
    # Не хранится в БД как отдельный столбец; значение берётся из связанной заметки.
    'description': {
        'title': 'Описание',                     # Заголовок.
        'editable': True,                        # Редактируемое.
        'virtual': True,                         # Помечаем как виртуальное (не сохраняется напрямую).
        'widget_type': 'textarea',               # Многострочный текстовый редактор.
        'order': 6,                              # Порядковый номер колонки.
        'source_attr': 'description_note',       # Имя атрибута в ORM-объекте, по которому можно получить связанную заметку.
        'compute': {                             # Настройка вычисления значения виртуального поля.
            'func': lambda note: note.text if note else None,  # Функция: берёт текст из заметки.
            'args': ['description_note'],        # Аргументы функции: имя атрибута, который будет передан в функцию.
        },
    },
    # Виртуальное поле "comment" – комментарий к пациенту.
    'comment': {
        'title': 'Комментарий',                  # Заголовок.
        'editable': True,                        # Редактируемое.
        'virtual': True,                         # Виртуальное.
        'widget_type': 'textarea',               # Многострочное поле.
        'order': 7,                              # Порядковый номер.
        'source_attr': 'comment_note',           # Атрибут ORM, ссылающийся на заметку.
        'compute': {
            'func': lambda note: note.text if note else None,
            'args': ['comment_note'],
        },
    },
}

# --- Приёмы ---
# Словарь для сущности "Приём".
APPOINTMENT_CONFIG: Dict[str, Dict[str, Any]] = {
    # Поле "id" – первичный ключ приёма.
    'id': {
        'title': 'ID',               # Заголовок.
        'editable': False,           # Не редактируется.
        'hidden': True,              # Скрыто в формах.
    },
    'patient_id': {
        'title': 'ID пациента',
        'editable': False,      # запрещаем редактирование
        # 'hidden': True,       # можно также скрыть поле, если не нужно показывать ID
    },
    'reason_id': {
        'title': 'ID причины',
        'hidden': True,
    },
    'procedure_id': {
        'title': 'ID процедуры',
        'hidden': True,
    },
    'recommendations_id': {
        'title': 'ID рекомендаций',
        'hidden': True,
    },
    'note_id': {
        'title': 'ID примечания',
        'hidden': True,
    },
    'cost_procedure_id': {
        'title': 'ID стоимости процедуры',
        'hidden': True,
    },

    # Виртуальное поле "patient_name" – ФИО пациента (вычисляется).
    'patient_name': {
        'title': 'Пациент',          # Заголовок.
        'editable': False,           # Нельзя редактировать, только отображение.
        'virtual': True,             # Виртуальное.
        'source_attr': 'patient',    # Атрибут ORM, содержащий объект пациента.
        'compute': {                 # Вычисление: формирует строку "Фамилия Имя".
            'func': lambda patient: " ".join([patient.last_name, patient.first_name, patient.middle_name]).strip(),
            'args': ['patient'],
        },
    },
    # Поле "date" – дата приёма.
    'date': {
        'title': 'Дата приёма',      # Заголовок.
        'editable': True,            # Редактируемое.
        'widget_type': 'date',       # Виджет выбора даты.
    },
    # Виртуальное поле "reason" – причина обращения.
    'reason_text': {
        'title': 'Причина обращения',
        'editable': True,
        'virtual': True,
        'widget_type': 'textarea',
        'source_attr': 'reason_note',
        'compute': {
            'func': lambda note: note.text if note else None,
            'args': ['reason_note'],
        },
    },
    # Виртуальное поле "procedure" – выполненная процедура.
    'procedure_text': {
        'title': 'Выполненная процедура',
        'editable': True,
        'virtual': True,
        'widget_type': 'textarea',
        'source_attr': 'procedure_note',
        'compute': {
            'func': lambda note: note.text if note else None,
            'args': ['procedure_note'],
        },
    },
    # Виртуальное поле "recommendations" – рекомендации.
    'recommendations_text': {
        'title': 'Рекомендации',
        'editable': True,
        'virtual': True,
        'widget_type': 'textarea',
        'source_attr': 'recommendations_note',
        'compute': {
            'func': lambda note: note.text if note else None,
            'args': ['recommendations_note'],
        },
    },
    # Поле "date_next" – дата следующего приёма.
    'date_next': {
        'title': 'Дата следующего приёма',
        'editable': True,
        'widget_type': 'date',       # Виджет даты.
    },
    # Виртуальное поле "note" – примечание (основная заметка).
    'note_text': {
        'title': 'Примечание',
        'editable': True,
        'virtual': True,
        'widget_type': 'textarea',
        'source_attr': 'note',       # ORM-связь с заметкой (Appointment.note).
        'compute': {
            'func': lambda note: note.text if note else None,
            'args': ['note'],
        },
    },
    # Виртуальное поле "cost_procedure" – стоимость процедуры.
    'cost_procedure_text': {
        'title': 'Стоимость процедуры',
        'editable': True,
        'virtual': True,
        'widget_type': 'textarea',
        'source_attr': 'cost_procedure_note',
        'compute': {
            'func': lambda note: note.text if note else None,
            'args': ['cost_procedure_note'],
        },
    },
    # Поле "photos" – список фотографий (не хранится в БД, только ссылка на связанные объекты).
    'photos': {
        'title': 'Фотографии',
        'editable': True,            # Можно редактировать (добавлять/удалять фото).
        'virtual': True,             # Виртуальное – обрабатывается специальным виджетом PhotoUploaderWidget.
        'widget_type': 'photo_uploader',  # Кастомный виджет для работы с фото.
    },
    # Виртуальное поле "has_photos" – индикатор наличия фото (для отображения в таблице).
    'has_photos': {
        'title': 'Фото',
        'editable': False,           # Только для чтения.
        'virtual': True,
        'order': 0,                  # Делаем эту колонку самой левой (необязательно).
        'source_attr': 'photos',     # Атрибут ORM, содержащий список фото.
        'compute': {                 # Вычисляем: возвращает текст "3 фото" или "❌".
            'func': lambda photo_count: f"{photo_count} фото" if photo_count > 0 else '❌',
            'args': ['photo_count'], # Аргумент – количество фото (подставляется отдельно).
        },
    },
}

# --- Заметки ---
NOTE_CONFIG: Dict[str, Dict[str, Any]] = {
    'id': {
        'title'         : 'ID',     # заголовок колонки
        'editable'      : False,    # редактируемый ли
        'hidden'        : True,     # скрываем ли его объект
    },
    'text': {
        'title'         : 'Текст заметки',  # заголовок колонки
        'editable'      : True,             # редактируемый ли
        'widget_type'   : 'textarea',       # виджет (указатель на тип виджета) # какой именно виджет Qt следует использовать для редактирования или отображения этого поля в динамической форме
        'init_from_extra': 'text',          # ключ в extra_data
    },
}

# --- Фотографии ---
PHOTO_CONFIG: Dict[str, Dict[str, Any]] = {
    'id': {
        'title'     : 'ID',     # заголовок колонки
        'editable'  : False,    # редактируемый ли
        'hidden'    : True,     # скрываем ли его объект
    },
    'appointment_id': {
        'title'     : 'ID приёма',  # заголовок колонки
        'editable'  : False,        # редактируемый ли
        'hidden'    : True,         # скрываем ли его объект
    },
    'file_path': {
        'title'     : 'Файл',   # заголовок колонки
        'editable'  : False,    # редактируемый ли
    },
    'description': {
        'title'             : 'Описание',   # заголовок колонки
        'editable'          : True,         # редактируемый ли
        'autocomplete'      : True,         # включает автодополнение в таблице и форме
    },
}