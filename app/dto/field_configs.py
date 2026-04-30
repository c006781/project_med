# app/dto/field_configs.py

"""
Общая конфигурация полей для форм и таблиц.
Содержит словари для каждой сущности, описывающие отображение, редактируемость,
виджеты, источники данных для выпадающих списков и т.д.
"""

from typing import Dict, Any

from app.dto.compute_fields import get_patient_full_name



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
PATIENT_CONFIG: Dict[str, Dict[str, Any]] = {
    'id': {
        'title'         : 'ID',     # заголовок колонки
        'editable'      : False,    # не редактируемый
        'hidden'        : True,     # скрываем ли его объект
        'order'         : 0,        # сортировка
    },
    'first_name': {
        'title'         : 'Имя',    # заголовок колонки
        'editable'      : True,     # редактируемый ли
        'autocomplete'  : True,         # включает автодополнение в таблице и форме
        'order'         : 1,        # сортировка
        'required'      : True,     # обязательное поле для заполнения ли
    },
    'last_name': {
        'title'         : 'Фамилия',    # заголовок колонки
        'editable'      : True,         # редактируемый ли
        'autocomplete'  : True,         # включает автодополнение в таблице и форме
        'order'         : 2,            # сортировка
        'required'      : True,         # обязательное поле для заполнения ли
    },
    'birth_date': {
        'title'         : 'Дата рождения',  # заголовок колонки
        'editable'      : True,             # редактируемый ли
        'widget_type'   : 'date',           # виджет (указатель на тип виджета)
        'order'         : 3,                # сортировка
    },
    'phone': {
        'title'         : 'Телефон',    # заголовок колонки
        'editable'      : True,         # редактируемый ли
        'order'         : 4,            # сортировка
    },
    'email': {
        'title'         : 'Email',  # заголовок колонки
        'editable'      : True,     # редактируемый ли
        'order'         : 5,        # сортировка
    },
}

# --- Приёмы ---
APPOINTMENT_CONFIG: Dict[str, Dict[str, Any]] = {
    'id': {
        'title'             : 'ID',     # заголовок колонки
        'editable'          : False,    # редактируемый ли
        'hidden'            : True,     # скрываем ли его объект
    },
    'patient_id': {
        'title'             : 'ID пациента',    # заголовок колонки
        'editable'          : False,            # редактируемый ли
        'hidden'            : True,             # скрываем ли его объект
        'init_from_extra'   : 'patient_id',     # ключ в extra_data # указывает, что при входе на страницу редактирования (в методе _init_from_extra) значение для этого поля должно быть автоматически взято из словаря extra_data и установлено в соответствующий виджет формы.
    },
    'patient_name': {
        'title'             : 'Пациент',    # заголовок колонки
        'editable'          : False,        # редактируемый ли
        'virtual'           : True,         # виртуальное ли поле
        'source'            : 'patient.full_name',   # как получить из связанного объекта
        'source_attr'       : 'patient',    # ключ для extra_data (из DTO) - указывает, из какого атрибута ORM-объекта брать данные
        'compute'           : {             # как вычислить
            # оставить так, что бы в редакторе появлялось...
            # 'func'      : get_patient_full_name, # функция вычисления
            # 'args'      : ['patient_id',],   # имена аргументов, которые нужно передать в функцию
            'func'      : lambda patient: f"{patient.last_name} {patient.first_name}" if patient else "", # функция вычисления
            'args'      : ['patient',],   # имена аргументов, которые нужно передать в функцию
        }
    },
    'date': {
        'title'             : 'Дата',   # заголовок колонки
        'editable'          : True,     # редактируемый ли
        'widget_type'       : 'date',   # виджет (указатель на тип виджета)
    },
    'time': {
        'title'             : 'Время',  # заголовок колонки
        'editable'          : True,     # редактируемый ли
        'widget_type'       : 'time',   # виджет (указатель на тип виджета)
    },
    'note_text': {
        'title'             : 'Заметка',    # заголовок колонки
        'editable'          : True,         # редактируемый ли
        'virtual'           : True,         # виртуальное ли поле
        'source_attr'       : 'note',       # ключ для extra_data (из DTO) - указывает, из какого атрибута ORM-объекта брать данные
        # 'widget_type'       : 'completer_with_edit', # виджет (указатель на тип виджета) # какой именно виджет Qt следует использовать для редактирования или отображения этого поля в динамической форме
        'widget_type'       : 'textarea',   # виджет (указатель на тип виджета) # какой именно виджет Qt следует использовать для редактирования или отображения этого поля в динамической форме
        'choices_provider'  : 'note_service.get_choices', # как получить список строк
        'compute': {
            'func'  : lambda note: note.text if note else None,  # функция вычисления
            'args'  : ['note'],  # имена аргументов, которые нужно передать в функцию
        },
    },
    'note_id': {
        'title'         : 'ID заметки', # заголовок колонки
        'editable'      : False,        # редактируемый ли
        'hidden'        : True,         # скрываем ли его объект
    },
    'photos': {
        'title'         : 'Фотографии',     # заголовок колонки 
        'editable'      : True,             # редактируемый ли
        'virtual'       : True,             # виртуальное ли поле
        'source_attr'   : 'photos',         # ключ для extra_data (из DTO) - указывает, из какого атрибута ORM-объекта брать данные      
        'widget_type'   : 'photo_uploader', # кастомный виджет
        # 'compute': {
        #     'func': lambda photos: [PhotoDTO.model_validate(p) for p in photos] if photos else [],
        #     'args': ['photos'],
        # }
        # 'hidden': True, # скрываем ли его объект - True нельзя, так как не будет отображаться в Редакторе приёма
    },
    'has_photos': {
        'title'         : 'Фото',       # заголовок колонки
        'editable'      : False,        # редактируемый ли
        'virtual'       : True,         # виртуальное ли поле
        'source_attr'   : 'photos',     # ключ для extra_data (из DTO) - указывает, из какого атрибута ORM-объекта брать данные
        'order'         : 0,            # порядок в таблице
        'compute': {  # как вычислить
            'func'  : lambda photos: f"{len(photos)} фото" if photos else '❌',  # или 'Да'/'Нет'
            'args'  : ['photos'],
        }
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