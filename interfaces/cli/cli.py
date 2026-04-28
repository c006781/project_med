#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Консольный интерфейс для управления данными приложения.

Используется библиотека click. Все команды обращаются к существующим сервисам,
что гарантирует единую логику с GUI.

Примеры использования:
    python -m app.cli patient list
    python -m app.cli patient get --id 1
    python -m app.cli patient create --first-name Иван --last-name Петров
    python -m app.cli sync download
"""


# Стандартные библиотеки Python
# import os  # Импорт модуля os для работы с путями файлов и директориями (например, чтобы получить абсолютный путь к файлу).
import sys  # Импорт модуля sys для работы с системными параметрами, такими как sys.path (список путей для импорта модулей).
from datetime import date, time
from typing import Optional


# # Импорты модулей
# def _add_package_name(
#     file_module: str = None,
#     levels_up: int = 3,           # <-- сколько уровней вверх до корня проекта
# ) -> None:
    
#     """
#     Что это (кратко): Добавляет корень проекта в sys.path и устанавливает правильный __package__.

#     Что это (максимально подробно): Эта функция настраивает окружение Python таким образом, чтобы можно было использовать относительные импорты (например, from .module import something) без необходимости запускать скрипт с флагом "-m" (как модуль). Она работает только если скрипт запущен напрямую (не импортирован). Функция получает абсолютный путь к текущему файлу, добавляет родительскую директорию в sys.path (список путей для поиска модулей), и устанавливает глобальную переменную __package__ как имя текущей директории. Это полезно в проектах с nested папками, где импорты могут сломаться.

#     Как работает: Сначала объявляется global __package__ для изменения системной переменной. Затем os.path.abspath(__file__) дает полный путь к скрипту, os.path.dirname убирает имя файла, оставляя папку. sys.path.append добавляет родительскую папку (dirname еще раз). Наконец, __package__ = basename(package_dir) — имя папки. Вызывается только в if __name__ == '__main__', чтобы не мешать, если скрипт импортирован.

#     Примеры запуска:
#     # В скрипте: if __name__ == '__main__': _add_package_name()
#     # После вызова: sys.path включает родительскую папку (например, '/path/to/modules'), __package__ = 'parsers_sheregeh'. Теперь относительные импорты работают.
#     # Если запустить как модуль (python -m script), функция не нужна, но она не навредит.
#     # Если не вызвать: относительный импорт from .module... может вызвать ImportError as e: attempted relative import with no known parent package.

#     :param file_module: (str) = обычно __file__  - указатель на путь к модулю, папку которого делаем пакетом для относительных импортов (содержит путь к текущему скрипту)
#     :param levels_up: (int) - на сколько уровней подниматься вверх до корня проекта
#                        (подберите под структуру вашего проекта)
#                        Примеры:
#                          2 → до папки app
#     """
#     if file_module is None:
#         file_module = __file__

#     # Получаем директорию текущего файла
#     current_dir = os.path.dirname(os.path.abspath(file_module))

#     # Поднимаемся на levels_up уровней вверх — это и будет корень проекта
#     project_root = current_dir
#     for _ in range(levels_up):
#         project_root = os.path.dirname(project_root)

#     # Добавляем корень проекта в начало sys.path (высокий приоритет)
#     if project_root not in sys.path:
#         sys.path.insert(0, project_root)

#     # Вычисляем правильное значение __package__
#     # Пример: /project_med/app/models/bd → "app.models.bd"
#     rel_path = os.path.relpath(current_dir, project_root)
    
#     if rel_path == '.':
#         package_name = ''
#     else:
#         package_name = rel_path.replace(os.sep, '.').strip('.')

#     # Устанавливаем __package__
#     global __package__
#     if package_name:
#         __package__ = package_name
#     else:
#         # Если мы в корне — можно оставить None или пустую строку
#         __package__ = None

# try:
from app.utils.logger.logger import AppLogger
# except ImportError as e:
#     try:
#         # Попытка абсолютного импорта, если модуль запущен как скрипт
#         _add_package_name(file_module = __file__,levels_up = 2)
#         from ..app.utils.logger.logger import AppLogger
#     except ImportError as e:
#         pass #  raise # e # pass

# try:
# from app.backend.database import Database
# except ImportError as e:
#     try:
#         # Попытка абсолютного импорта, если модуль запущен как скрипт
#         _add_package_name(file_module = __file__,levels_up = 2)
#         from ..app.backend.database import Database
#     except ImportError as e:
#         pass #  raise # e # pass

# try:
# from app.backend.repositories import (
#         PatientRepository,
#         AppointmentRepository,
#         AppointmentNoteRepository,
#         PhotoRepository
#     )

# except ImportError as e:
    # try:
    #     # Попытка абсолютного импорта, если модуль запущен как скрипт
    #     _add_package_name(file_module = __file__,levels_up = 2)
    #     from ..app.backend.repositories import (
    #         PatientRepository,
    #         AppointmentRepository,
    #         AppointmentNoteRepository,
    #         PhotoRepository
    #     )
    # except ImportError as e:
    #     pass #  raise # e # pass

# try:
#     # from ..controllers.conf.get_config import get_config_env
#     from ..controllers.config_manager.manager import get_config_env
# except ImportError as e:
#     try:
#         # Попытка абсолютного импорта, если модуль запущен как скрипт
#         _add_package_name(file_module = __file__,levels_up = 2)
#         # from ..controllers.conf.get_config import get_config_env
#         from ..controllers.config_manager.manager import get_config_env
#     except ImportError as e:
#         pass #  raise # e # pass

# try:
# from app.services import (
#         PatientService,
#         AppointmentService,
#         NoteService,
#         PhotoService,
#         SyncService
#     )
# except ImportError as e:
#     try:
#         # Попытка абсолютного импорта, если модуль запущен как скрипт
#         _add_package_name(file_module = __file__,levels_up = 2)
#         from ..app.services import (
#             PatientService,
#             AppointmentService,
#             NoteService,
#             PhotoService,
#             SyncService
#         )
#     except ImportError as e:
#         pass #  raise # e # pass

# try:
from app.dto import (
        PatientDTO,
        AppointmentDTO,
        AppointmentNoteDTO,
        PhotoDTO
    )
# except ImportError as e:
#     try:
#         # Попытка абсолютного импорта, если модуль запущен как скрипт
#         _add_package_name(file_module = __file__,levels_up = 2)
#         from ..app.dto import (
#             PatientDTO,
#             AppointmentDTO,
#             AppointmentNoteDTO,
#             PhotoDTO
#         )
#     except ImportError as e:
#         pass #  raise # e # pass

# try:
from app.exceptions import (
        PatientNotFoundError,
        PatientValidationError,
        AppointmentNotFoundError,
        AppointmentNoteNotFoundError,
        PhotoNotFoundError,
        PhotoFileError,
        DownloadError,
        UploadError
    )
# except ImportError as e:
#     try:
#         # Попытка абсолютного импорта, если модуль запущен как скрипт
#         _add_package_name(file_module = __file__,levels_up = 2)
#         from ..app.exceptions import (
#             PatientNotFoundError,
#             PatientValidationError,
#             AppointmentNotFoundError,
#             AppointmentNoteNotFoundError,
#             PhotoNotFoundError,
#             PhotoFileError,
#             DownloadError,
#             UploadError
#         )
#     except ImportError as e:
#         pass #  raise # e # pass

# try:
    # from ..models.bd.models import init_db  # для инициализации БД
# from app.backend.bd.clinic import create_db, generate_test_data, Patient, Appointment, AppointmentNote, Photo
from app.database.database_shema.clinic import Patient, Appointment, AppointmentNote, Photo
# except ImportError as e:
#     try:
#         # Попытка абсолютного импорта, если модуль запущен как скрипт
#         _add_package_name(file_module = __file__,levels_up = 2)
#         # from ..models.bd.models import init_db  # для инициализации БД
#         from ..app.backend.bd.clinic import create_db, generate_test_data, Patient, Appointment, AppointmentNote, Photo
#     except ImportError as e:
#         pass #  raise # e # pass

# try:
from app.dependencies import (
        get_db,
        get_patient_service,
        get_appointment_service,
        get_note_service,
        get_photo_service,
        get_sync_service,
        init_db as init_db_deps,
        # get_key_value_dto,
        get_text_echo,
        create_click_options,
        collect_dto_from_input,
        get_dto_fields,
    )
# except ImportError:
#     # fallback с _add_package_name
#     _add_package_name(file_module=__file__, levels_up=2)
#     from ..app.dependencies import (
#         get_db,
#         get_patient_service,
#         get_appointment_service,
#         get_note_service,
#         get_photo_service,
#         get_sync_service,
#         init_db,
#     )


# Сторонние библиотеки

import click # pip install click
# from sqlalchemy.orm import sessionmaker  



# ------------------------------------------------------------------------------
# Инициализация общих объектов
# ------------------------------------------------------------------------------

# def get_db() -> Database:
#     """Возвращает экземпляр Database, сконфигурированный из .env."""
#     config = get_config_env()
#     db_path = config['database_local_path']

#     AppLogger.get_instance(
#         name = 'system'
#     ).debug(
#         f"Возвращает экземпляр Database, сконфигурированный из .env.: {db_path} ({os.path.abspath(db_path)})"
#     )

#     db_url = f"sqlite:///{config['database_local_path']}"
#     return Database(db_url)

# def get_patient_service() -> PatientService:
#     return PatientService(get_db())

# def get_appointment_service() -> AppointmentService:
#     db = get_db()
#     note_service = NoteService(db)
#     return AppointmentService(db, note_service=note_service)
# def get_note_service() -> NoteService:
#     return NoteService(get_db())

# def get_photo_service() -> PhotoService:
#     config = get_config_env()
#     photos_path = config.get('PHOTOS_STORAGE_PATH', './photos')
#     return PhotoService(get_db(), photos_path)

# def get_sync_service() -> SyncService:
#     return SyncService()


# ----------------------------------------------------------------------
# Функция-фабрика, создающая группу команд
# ----------------------------------------------------------------------
@AppLogger.get_instance(
    name = 'system'
).log_execution_time(
    level=AppLogger._parse_log_level('DEBUG')
)  
def create_cli():
    """
    Создаёт и возвращает группу команд Click для CLI.
    Внутри определяются все подгруппы и команды.
    """

    @click.group()
    def cli():
        """
        Медицинское приложение - управление данными из консоли.

        Это - основная точка входа в приложение.
        Она группирует все команды, доступные из консоли.
        """
        AppLogger.get_instance(
            name = 'cli',
            enable_file_logging = 'user',
           use_name_in_filename =  False, #  True, # 'user',
        ).debug(
            f"Медицинское приложение - управление данными из консоли"
        )
        pass
        
    # ------------------------------------------------------------------------------
    # Группа команд для пациентов
    # ------------------------------------------------------------------------------

    # @click.group()
    @cli.group()
    def patient():
        """Управление пациентами."""
        pass

    @patient.command('list')
    @click.option('--filter', '-f', multiple=True, help='Фильтр в формате column:operator:value (например: last_name:like:Петров). Для нечеткого поиска: fuzzy:column:value')
    @click.option('--fuzzy-threshold', default=60, type=int, help='Порог схожести для нечеткого поиска (0-100)')
    def patient_list(filter, fuzzy_threshold):
        """
        Вывести список пациентов с возможностью фильтрации.

        filter - список строк, каждая из которых имеет формат "column:operator:value".
        fuzzy_threshold - порог схожести для нечеткого поиска (0-100)

        Функция работает следующим образом:
        1. Создаем список словарей filters, где каждый словарь содержит информацию о фильтре:
            - column: имя столбца (строка)
            - operator: оператор из FilterOperator
            - value: значение для сравнения (зависит от оператора)
        2. Создаем экземпляр PatientService
        3. Вызываем метод get_patients_filtered у PatientService, передавая туда полученный список фильтров и порог схожести
        4. Выводим список пациентов, если он не пустой
        """
        AppLogger.get_instance(
            name = 'cli',
            enable_file_logging = 'user',
           use_name_in_filename =  False, #  True, # 'user',
        ).debug( 
            f"Вывести список пациентов с возможностью фильтрации. filter={filter}, fuzzy_threshold={fuzzy_threshold}" 
        )

        # Создаем список словарей filters, где каждый словарь содержит информацию о фильтре
        filters = []
        for f in filter:
            if f.startswith('fuzzy:'):
                # Если фильтр имеет формат "fuzzy:column:value", то создаем словарь с соответствующими значениями
                parts = f.split(':', 2)
                if len(parts) != 3:
                    click.echo("Неверный формат fuzzy-фильтра: fuzzy:column:value", err=True)
                    raise click.Abort()  
                _, column, value = parts
                filters.append({'column': column, 'operator': 'fuzzy', 'value': value})
            else:
                # Если фильтр имеет формат "column:operator:value", то создаем словарь с соответствующими значениями
                parts = f.split(':', 2)
                if len(parts) != 3:
                    click.echo(f"Неверный формат фильтра: {f}. Используйте column:operator:value", err=True)
                    raise click.Abort()  
                column, op, value = parts
                filters.append({'column': column, 'operator': op, 'value': value})

        # Создаем экземпляр PatientService
        service = get_patient_service()

        try:
            # Вызываем метод get_patients_filtered у PatientService, передавая туда полученный список фильтров и порог схожести
            patients = service.get_patients_filtered(filters, fuzzy_threshold)

            # Выводим список пациентов, если он не пустой

            if not patients:
                click.echo("Пациенты не найдены.")
                return
            
            rename_map_patients = {
                'id': 'ID',
                'first_name': 'Имя',
                'last_name': 'Фамилия',
                'birth_date': 'Дата рождения',
                'phone': 'Телефон',
                'email': 'Email'
            }
           
            for text_echo in get_text_echo(
                patients,
                exclude_fields=[
                    # 'Note Id'
                    # 'note_id'
                ],
                rename_map = rename_map_patients,
            ):
                click.echo(text_echo)

            # for p in patients:
            #     click.echo(f"ID: {p.id}, ФИО: {p.last_name} {p.first_name}, "
            #             f"Дата рождения: {p.birth_date}, Телефон: {p.phone}")
        except Exception as e:
            click.echo(f"Ошибка: {e}", err=True)

    @patient.command('get')
    @click.option('--id', required=True, type=int, help='ID пациента')
    def patient_get(id):
        """Вывести информацию о пациенте по ID."""
        AppLogger.get_instance( 
            name = 'cli',
            enable_file_logging = 'user',
           use_name_in_filename =  False, #  True, # 'user',
        ).debug( 
            f"Создвести информацию о пациенте по ID. id={id}" 
        )
        service = get_patient_service()
        try:
            p = service.get_patient_by_id(id)
            data = p.model_dump(exclude_none=True)

            rename_map_patients = {
                'id': 'ID',
                'first_name': 'Имя',
                'last_name': 'Фамилия',
                'birth_date': 'Дата рождения',
                'phone': 'Телефон',
                'email': 'Email'
            }   
            
            for text_echo in get_text_echo(
                data,
                exclude_fields=[
                    # 'Note Id'
                    # 'note_id'
                ],
                rename_map = rename_map_patients,
            ):
                click.echo(text_echo)



            # click.echo(f"ID: {p.id}")
            # click.echo(f"Имя: {p.first_name}")
            # click.echo(f"Фамилия: {p.last_name}")
            # click.echo(f"Дата рождения: {p.birth_date}")
            # click.echo(f"Телефон: {p.phone}")
            # click.echo(f"Email: {p.email}")
        except PatientNotFoundError as e:
            click.echo(str(e), err=True)
        except Exception as e:
            click.echo(f"Ошибка: {e}", err=True)



    @patient.command('create')
    # @click.option('--first-name', required=True, help='Имя')
    # @click.option('--last-name', required=True, help='Фамилия')
    # @click.option('--birth-date', help='Дата рождения (ГГГГ-ММ-ДД)')
    # @click.option('--phone', help='Телефон')
    # @click.option('--email', help='Email')
    @create_click_options(PatientDTO, action='create')
    def patient_create(**kwargs):
        """Создать нового пациента."""
        AppLogger.get_instance(
            name = 'cli',
            enable_file_logging = 'user',
           use_name_in_filename =  False, #  True, # 'user',
        ).debug(f"Создание пациента: {kwargs}")
        service = get_patient_service()
        # Преобразуем дату, если передана строка
        if kwargs.get('birth_date'):
            try:
                kwargs['birth_date'] = date.fromisoformat(kwargs['birth_date'])
            except ValueError:
                click.echo("Неверный формат даты. Используйте ГГГГ-ММ-ДД.", err=True)
                return
        dto_in = PatientDTO(**kwargs)
        try:
            dto_out = service.create_patient(dto_in)
            click.echo(f"Пациент создан с ID: {dto_out.id}")
        except PatientValidationError as e:
            click.echo(f"Ошибка валидации: {e}", err=True)
        except Exception as e:
            click.echo(f"Ошибка: {e}", err=True)

    @patient.command('update')
    # @click.option('--id', required=True, type=int, help='ID пациента')
    # @click.option('--id', required=True, type=int, help='ID пациента')
    # @click.option('--first-name', help='Имя')
    # @click.option('--last-name', help='Фамилия')
    # @click.option('--birth-date', help='Дата рождения (ГГГГ-ММ-ДД)')
    # @click.option('--phone', help='Телефон')
    # @click.option('--email', help='Email')
    @create_click_options(PatientDTO, action='update')
    def patient_update( **kwargs):
        """Обновить данные пациента (указывайте только изменяемые поля)."""

        id = kwargs.pop('id', None)
        if id is None:
            click.echo("Ошибка: не указан ID пациента", err=True)
            return
        id = int(id)
        
        service = get_patient_service()
        try:
            existing = service.get_patient_by_id(id)
            # Обновляем только переданные поля
            for key, value in kwargs.items():
                if value is not None:  # опциональные поля могут быть None
                    if key == 'birth_date' and isinstance(value, str):
                        try:
                            value = date.fromisoformat(value)
                        except ValueError:
                            click.echo("Неверный формат даты.", err=True)
                            return
                    setattr(existing, key, value)
            updated = service.update_patient(existing)
            click.echo(f"Пациент ID {updated.id} обновлён.")
        except PatientNotFoundError as e:
            click.echo(str(e), err=True)
        except Exception as e:
            click.echo(f"Ошибка: {e}", err=True)

    @patient.command('delete')
    @click.option('--id', required=True, type=int, help='ID пациента')
    def patient_delete(id):
        """Удалить пациента по ID."""
        AppLogger.get_instance( 
            name = 'cli',
            enable_file_logging = 'user',
           use_name_in_filename =  False, #  True, # 'user',
        ).debug( 
            f"Удалить пациента по ID id={id}" 
        )
        service = get_patient_service()
        try:
            service.delete_patient(id)
            click.echo(f"Пациент ID {id} удалён.")
        except PatientNotFoundError as e:
            click.echo(str(e), err=True)
        except Exception as e:
            click.echo(f"Ошибка: {e}", err=True)

    # ------------------------------------------------------------------------------
    # Группа команд для приёмов
    # ------------------------------------------------------------------------------

    # @click.group()
    @cli.group()
    def appointment():
        """Управление приёмами."""
        pass

    @appointment.command('list')
    @click.option('--patient-id', type=int, help='ID пациента (если не указан, выводятся все приёмы)')
    @click.option('--filter', '-f', multiple=True, help='Фильтр в формате column:operator:value (например: date:gt:2025-01-01). Для нечеткого поиска: fuzzy:note_text:значение')
    @click.option('--fuzzy-threshold', default=60, type=int, help='Порог схожести для нечеткого поиска (0-100)')
    def appointment_list(patient_id, filter, fuzzy_threshold):
        """
        Вывести список приёмов с возможностью фильтрации.

        Если указан patient_id, то выводятся все приёмы пациента с подгруженными связями.
        Если указаны фильтры, то выводятся приёмы, соответствующие этим фильтрам.
        Если не указаны ни patient_id, ни фильтры, то выводятся все приёмы.

        Фильтры могут быть двух типов:
            - column:operator:value (например: date:gt:2025-01-01)
            - fuzzy:note_text:значение (для нечеткого поиска по тексту заметки)

        Порог схожести для нечеткого поиска указывается в fuzzy_threshold (0-100).
        """
        AppLogger.get_instance( 
            name = 'cli',
            enable_file_logging = 'user',
           use_name_in_filename =  False, #  True, # 'user',
        ).debug( 
            f"Вывести список приёмов с возможностью фильтрации patient_id={patient_id}, filter={filter}, fuzzy_threshold={fuzzy_threshold}" 
        )
        service = get_appointment_service()
        filters = []

        # Обрабатываем фильтры
        for f in filter:
            if f.startswith('fuzzy:'):
                # Если фильтр имеет формат "fuzzy:column:value", то создаем словарь с соответствующими значениями
                parts = f.split(':', 2)
                if len(parts) != 3:
                    click.echo("Неверный формат fuzzy-фильтра: fuzzy:column:value", err=True)
                    return
                _, column, value = parts
                # Для fuzzy поиска по тексту заметки нужно указать column='note_text' (виртуальное поле)
                filters.append({'column': column, 'operator': 'fuzzy', 'value': value})
            else:
                # Если фильтр имеет формат "column:operator:value", то создаем словарь с соответствующими значениями
                parts = f.split(':', 2)
                if len(parts) != 3:
                    click.echo(f"Неверный формат фильтра: {f}. Используйте column:operator:value", err=True)
                    return
                column, op, value = parts
                filters.append({'column': column, 'operator': op, 'value': value})

        try:
            if patient_id and not filters:
                # Если указан patient_id и не указаны фильтры, то выводятся все приёмы пациента
                apps = service.get_appointments_by_patient(patient_id)
            elif filters:
                # Если указаны фильтры, то выводятся приёмы, соответствующие этим фильтрам
                apps = service.get_filtered(filters, fuzzy_threshold)
            else:
                # Если не указаны ни patient_id, ни фильтры, то выводятся все приёмы
                apps = service.get_all()

            if not apps:
                click.echo("Приёмы не найдены.")
                return

            rename_map_appointments = {
                'id': 'ID',
                'patient_id': 'ID пациента',
                'date': 'Дата',
                'time': 'Время',
                'note_id': 'ID заметки',
                'patient_name': 'Пациент',
                'note_text': 'Заметка'
            }   

            for text_echo in get_text_echo(
                apps,
                exclude_fields=[
                    # 'Note Id'
                    'note_id'
                ],
                rename_map = rename_map_appointments,
            ):
                click.echo(text_echo)
                
        except Exception as e:
            click.echo(f"Ошибка: {e}", err=True)

    @appointment.command('get')
    @click.option('--id', required=True, type=int, help='ID приёма')
    def appointment_get(id):
        """
        Вывести информацию о приёме.
        
        id - ID приёма, информацию о котором нужно вывести.
        """
        AppLogger.get_instance( 
            name = 'cli',
            enable_file_logging = 'user',
           use_name_in_filename =  False, #  True, # 'user',
        ).debug( f"Вывести информацию о приёме id={id}, ..." )

        service = get_appointment_service()
        try:
            # Получаем информацию о приёме с указанным ID
            a = service.get_appointment(id)
            data = a.model_dump(exclude_none=True)
            # for title, value in get_key_value_dto(
            #     data, 
            #     exclude_fields=['patient_id', 'note_id'] # можно исключить, если не нужны
            # ).items():
            #     click.echo(f"{title}: {value}")

            rename_map_appointments = {
                'id': 'ID',
                'patient_id': 'ID пациента',
                'date': 'Дата',
                'time': 'Время',
                'note_id': 'ID заметки',
                'patient_name': 'Пациент',
                'note_text': 'Заметка'
            }   

            for text_echo in get_text_echo(
                data,
                exclude_fields=[
                    'patient_id', 'note_id'
                ],
                rename_map = rename_map_appointments,
            ):
                click.echo(text_echo)

            # Выводим полученную информацию
            # click.echo(f"ID: {a.id}")
            # click.echo(f"Пациент ID: {a.patient_id}")
            # click.echo(f"Дата: {a.date}")
            # click.echo(f"Время: {a.time}")
            # click.echo(f"Заметка ID: {a.note_id}")
            
            # Если к приёму прикреплена заметка, то вывести ее текст
            # if a.note_text:
            #     click.echo(f"Текст заметки: {a.note_text}")
        except AppointmentNotFoundError as e:
            # Если приём с указанным ID не найден, то вывести ошибку
            click.echo(str(e), err=True)
        except Exception as e:
            # Если произошла какая-то другая ошибка, то вывести ее текст
            click.echo(f"Ошибка: {e}", err=True)


    @appointment.command('create')
    # @click.option('--patient-id', required=True, type=int, help='ID пациента')
    # @click.option('--date', 'date_str', required=True, help='Дата приёма (ГГГГ-ММ-ДД)')  # переименовано
    # @click.option('--time', 'time_str', help='Время (ЧЧ:ММ)')
    # @click.option('--note-text', help='Текст заметки (будет создана или использована существующая)')
    @create_click_options(AppointmentDTO, action='create')
    def appointment_create(**kwargs):
        """
        Создать новый приём. Заметка будет найдена или создана автоматически.

        1. Берем ID пациента из kwargs и создаем DTO для приема.
        2. Если передана дата или время, преобразуем их в datetime.date и datetime.time.
        3. Если передан текст заметки, то создаем новую заметку или используем существующую.
        4. Создаем новый приём с помощью сервиса.
        5. Выводим ID созданного приема.
        """
        """Создать новый приём. Заметка будет найдена или создана автоматически."""
        AppLogger.get_instance(
            name = 'cli',
            enable_file_logging = 'user',
           use_name_in_filename =  False, #  True, # 'user',
        ).debug(f"Создание приёма: {kwargs}")
        service = get_appointment_service()

        # Преобразование даты и времени
        if 'date' in kwargs and isinstance(kwargs['date'], str):
            try:
                # Преобразуем строку в datetime.date
                kwargs['date'] = date.fromisoformat(kwargs['date'])
            except ValueError:
                # Если не удалось преобразовать, выводим ошибку
                click.echo("Неверный формат даты. Используйте ГГГГ-ММ-ДД.", err=True)
                return
        if 'time' in kwargs and kwargs['time'] and  isinstance(kwargs['time'], str):
            try:
                # Преобразуем строку в datetime.time
                h, m = map(int, kwargs['time'].split(':'))
                kwargs['time'] = time(h, m)
            except:
                # Если не удалось преобразовать, выводим ошибку
                click.echo("Неверный формат времени. Используйте ЧЧ:ММ.", err=True)
                return

        # Извлекаем note_text, если передан (это виртуальное поле, не в DTO)
        note_text = kwargs.pop('note_text', None)
        dto_in = AppointmentDTO(**kwargs)
        try:
            # Создаем новый приём с помощью сервиса
            dto_out = service.create_appointment(dto_in, note_text=note_text)
            # Выводим ID созданного приема
            click.echo(f"Приём создан с ID: {dto_out.id}")
        except PatientNotFoundError as e:
            # Если пациент с указанным ID не найден, то вывести ошибку
            click.echo(str(e), err=True)
        except Exception as e:
            # Если произошла какая-то другая ошибка, то вывести ее текст
            click.echo(f"Ошибка: {e}", err=True)

    @appointment.command('update')
    # @click.option('--id', required=True, type=int, help='ID приёма')
    # @click.option('--date', 'date_str', help='Новая дата (ГГГГ-ММ-ДД)')  # переименовано
    # @click.option('--time', 'time_str', help='Новое время (ЧЧ:ММ)')
    # @click.option('--note-id', type=int, help='Новый ID существующей заметки')
    # @click.option('--note-text', help='Текст новой заметки (если указан, заменяет заметку)')
    # @click.option('--id', required=True, type=int, help='ID приёма')
    @create_click_options(AppointmentDTO, action='update')
    def appointment_update(**kwargs):
        """
        Обновить приём.

        Обновляет данные приёма с указанным ID.
        Если приём с указанным ID существует, то он будет обновлён.
        Если приём с указанным ID не существует, то будет выведена ошибка.
        """
        # Получаем ID приёма из аргументов
        id = kwargs.pop('id', None)
        if id is None:
            click.echo("Ошибка: не указан ID приёма", err=True)
            return
        # Преобразуем ID в int
        id = int(id)

        # Создаем сервис для работы с приёмами
        service = get_appointment_service()
        try:
            # Получаем существующий приём по ID
            existing = service.get_appointment(id)

            # Преобразование даты/времени, если переданы
            # if 'date' in kwargs and kwargs['date']:
            #     try:
            #         kwargs['date'] = date.fromisoformat(kwargs['date'])
            #     except ValueError:
            #         click.echo("Неверный формат даты.", err=True)
            #         return
            # if 'time' in kwargs and kwargs['time']:
            #     try:
            #         h, m = map(int, kwargs['time'].split(':'))
            #         kwargs['time'] = time(h, m)
            #     except:
            #         click.echo("Неверный формат времени.", err=True)
            #         return
            
            # Получаем текст новой заметки
            note_text = kwargs.pop('note_text', None)

            # Обновляем существующий DTO
            for key, value in kwargs.items():
                if value is not None:
                    # Если поле не является None, то обновляем его
                    setattr(existing, key, value)
            # Обновляем приём с помощью сервиса
            updated = service.update_appointment(existing, note_text=note_text)
            # Выводим ID обновлённого приема
            click.echo(f"Приём ID {updated.id} обновлён.")
        except AppointmentNotFoundError as e:
            # Если приём с указанным ID не существует, то выводим ошибку
            click.echo(str(e), err=True)
        except Exception as e:
            # Если произошла какая-то другая ошибка, то выводим ее текст
            click.echo(f"Ошибка: {e}", err=True)

    @appointment.command('delete')
    @click.option('--id', required=True, type=int, help='ID приёма')
    def appointment_delete(id):
        """
        Удаляет приём с указанным ID.

        Если приём с указанным ID существует, то он будет удалён.
        Если приём с указанным ID не существует, то будет выведена ошибка.

        :param id: ID приёма
        :return: None
        """
        AppLogger.get_instance( 
            name = 'cli',
            enable_file_logging = 'user',
           use_name_in_filename =  False, #  True, # 'user',
        ).debug( f"Удалить приём id={id}" )
        service = get_appointment_service()
        try:
            # Получаем приём с указанным ID
            appointment = service.get_appointment(id)
            
            # Удаляем приём
            service.delete_appointment(id)
            
            # Выводим сообщение об успешном удалении
            click.echo(f"Приём ID {id} удалён.")
        except AppointmentNotFoundError as e:
            # Если приём с указанным ID не существует, то вывести ошибку
            click.echo(str(e), err=True)
        except Exception as e:
            # Если произошла какая-то другая ошибка, то вывести ее текст
            click.echo(f"Ошибка: {e}", err=True)

    # ------------------------------------------------------------------------------
    # Группа команд для заметок
    # ------------------------------------------------------------------------------

    # @click.group()
    @cli.group()
    def note():
        """
        Группа команд для управления заметками приёмов.
        
        В ней содержатся команды для создания, удаления, просмотра и редактирования заметок.
        """
        pass

    @note.command('list')
    def note_list():
        """Вывести все заметки.

        Это функция выводит список всех заметок, которые есть в базе данных.
        Она использует сервис get_note_service() для доступа к заметкам.
        Если какая-то ошибка происходит при попытке получения списка заметок, то она выводится на экран.
        """
        # print('1')

        AppLogger.get_instance( 
            name = 'cli',
            enable_file_logging = 'user',
           use_name_in_filename =  False, #  True, # 'user',
        ).debug( f"Вывести все заметки" )
        service = get_note_service()
        try:
            # print('2')
            notes = service.get_all()
            # print('3')
            if not notes:
                click.echo("Заметки не найдены.")
                return
            
            rename_map_note = {
                'id': 'ID',
                'text': 'Текст заметки'
            }  

            for text_echo in get_text_echo(
                notes,
                exclude_fields=[
                    # 'Note Id'
                    # 'note_id'
                ],
                rename_map = rename_map_note,
            ):
                click.echo(text_echo)
            # for n in notes:
            #     # print('3')
            #     click.echo(f"ID: {n.id}, Текст: {n.text[:50]}...")
        except Exception as e:
            click.echo(f"Ошибка: {e}", err=True)

    @note.command('get')
    @click.option('--id', required=True, type=int, help='ID заметки')
    def note_get(id):
        """
        Команда для вывода информации о заметке.

        Она использует сервис get_note_service() для доступа к заметкам.
        Если какая-то ошибка происходит при попытке получить информацию о заметке, то она выводится на экран.

        :param id: ID заметки
        :return: None
        """
        # Логирование
        AppLogger.get_instance( 
            name = 'cli',
            enable_file_logging = 'user',
           use_name_in_filename =  False, #  True, # 'user',
        ).debug( f"Показать заметку id={id}" )

        # Получаем сервис для работы с заметками
        service = get_note_service()

        try:
            # Получаем информацию о заметке с указанным ID
            n = service.get_note(id)
            data = n.model_dump(exclude_none=True)

            # Выводим полученную информацию
            # for title, value in get_key_value_dto(
            #     data, 
            #      # можно исключить, если не нужны
            # ).items():
            #     click.echo(f"{title}: {value}")


            rename_map_note = {
                'id': 'ID',
                'text': 'Текст заметки'
            }   

            for text_echo in get_text_echo(
                data,
                exclude_fields=[
                    # 'Note Id'
                    # 'note_id'
                ],
                rename_map = rename_map_note,
            ):
                click.echo(text_echo)


            # click.echo(f"ID: {n.id}")
            # click.echo(f"Текст:\n{n.text}")
        except AppointmentNoteNotFoundError as e:
            # Если заметки с указанным ID не существует, то вывести ошибку
            click.echo(str(e), err=True)
        except Exception as e:
            # Если произошла какая-то другая ошибка, то вывести ее текст
            click.echo(f"Ошибка: {e}", err=True)

    @note.command('create')
    # @click.argument('text')
    @create_click_options(AppointmentNoteDTO, action='create')
    def note_create(**kwargs):
        """Создать заметку."""
        service = get_note_service()
        try:
            dto = service.create_note(kwargs['text'])
            click.echo(f"Заметка создана с ID: {dto.id}")
        except Exception as e:
            click.echo(f"Ошибка: {e}", err=True)

    # @note.command('create')
    # @create_click_options(AppointmentNoteDTO, action='create')
    # def note_create(**kwargs):
    #     service = get_note_service()
    #     dto = service.create_note(kwargs['text'])
    #     click.echo(f"Заметка создана с ID: {dto.id}")

    
    @note.command('create-from-file')
    @click.option('--file', type=click.Path(exists=True, readable=True), required=True, help='Файл с текстом заметки')
    def note_create_from_file(file):
        """
        Создать заметку из текстового файла.

        Это функция использует сервис get_note_service() для доступа к заметкам.
        Она создает новую заметку, читая текст из указанного файла.
        Если какая-то ошибка происходит при попытке создания заметки, то она выводится на экран.
        """
        service = get_note_service()
        try:
            # Создаем новую заметку, читая текст из указанного файла
            dto = service.create_note_from_file(file)
            
            # Выводим созданную заметку
            click.echo(f"Заметка создана с ID: {dto.id}")
        except Exception as e:
            # Если произошла какая-то ошибка, то вывести ее текст
            click.echo(f"Ошибка: {e}", err=True)

    @note.command('update')
    # @click.option('--id', required=True, type=int, help='ID заметки')
    # @click.argument('text')
    @create_click_options(AppointmentNoteDTO, action='update')
    def note_update( **kwargs):
        id = kwargs.pop('id', None)
        if id is None:
            click.echo("Ошибка: не указан ID заметки", err=True)
            return
        id = int(id)
        
        """Обновить текст заметки."""
        service = get_note_service()
        try:
            updated = service.update_note(id, kwargs['text'])
            click.echo(f"Заметка ID {updated.id} обновлена.")
        except AppointmentNoteNotFoundError as e:
            click.echo(str(e), err=True)
        except Exception as e:
            click.echo(f"Ошибка: {e}", err=True)


    @note.command('delete')
    @click.option('--id', required=True, type=int, help='ID заметки')
    def note_delete(id):
        """
        Команда для удаления заметки.

        Она использует сервис get_note_service() для доступа к заметкам.
        Она удаляет заметку с указанным ID.
        Если какая-то ошибка происходит при попытке удаления заметки, то она выводится на экран.
        """
        AppLogger.get_instance( 
            name = 'cli',
            enable_file_logging = 'user',
           use_name_in_filename =  False, #  True, # 'user',
        ).debug( f"Удалить заметку id={id}" )
        service = get_note_service()
        try:
            # Удаляем заметку с указанным ID
            service.delete_note(id)
            
            # Выводим сообщение об успешном удалении
            click.echo(f"Заметка ID {id} удалена.")
        except AppointmentNoteNotFoundError as e:
            # Если заметки с указанным ID не существует, то вывести ошибку
            click.echo(str(e), err=True)
        except Exception as e:
            # Если произошла какая-то другая ошибка, то вывести ее текст
            click.echo(f"Ошибка: {e}", err=True)

    # ------------------------------------------------------------------------------
    # Группа команд для фото
    # ------------------------------------------------------------------------------

    # @click.group()
    @cli.group()
    def photo():
        """
        Группа команд для управления фотографиями приёмов.

        Содержит команды для создания, удаления, просмотра и редактирования фотографий.
        """
        pass

    @photo.command('list')
    @click.option('--appointment-id', type=int, help='ID приёма (если не указан, выводятся все фото)')
    def photo_list(appointment_id):
        """
        Команда для вывода списка фотографий.

        Если указан ID приёма, то выводятся только фото этого приёма.
        Если не указан, то выводятся все фото.
        """
        AppLogger.get_instance(
            name = 'cli',
            enable_file_logging = 'user',
           use_name_in_filename =  False, #  True, # 'user',
        ).debug(f"Запрос списка фото, appointment_id={appointment_id}")

        # Получаем сервис для работы с фотографиями
        service = get_photo_service()
        try:
            # Если указан ID приёма, то получаем фото только этого приёма
            if appointment_id is not None:
                photos = service.get_photos_for_appointment(appointment_id)
            # Если не указан, то получаем все фото
            else:
                photos = service.get_all()  # используем унаследованный метод из BaseService
            
            # Если не найдено ни одного фото, то выводим сообщение
            if not photos:
                click.echo("Фото не найдены.")
                return
            
            # Выводим информацию о каждом фото
            # for p in photos:
            #     click.echo(f"ID: {p.id}, Приём ID: {p.appointment_id}, Файл: {p.file_path}, Описание: {p.description}")
            
            rename_map_photo = {
                'id': 'ID',
                'appointment_id': 'ID приёма',
                'file_path': 'Путь к файлу',
                'description': 'Описание',
            }     
            
            for text_echo in get_text_echo(
                photos,
                exclude_fields=[
                    # 'Note Id'
                    'appointment_id'
                ],
                rename_map = rename_map_photo,
            ):
                click.echo(text_echo)
        
        except Exception as e:
            click.echo(f"Ошибка: {e}", err=True)

    @photo.command('add')
    @click.option('--appointment-id', required=True, type=int, help='ID приёма')
    @click.option('--file', required=True, type=click.Path(exists=True), help='Путь к файлу изображения')
    @click.option('--description', default='', help='Описание')
    def photo_add(**kwargs):
        """Добавить фото к приёму."""
        service = get_photo_service()
        appointment_id = kwargs['appointment_id']
        file_path = kwargs['file']          # исправлено: было kwargs['file_path']
        description = kwargs.get('description', '')
        try:
            dto = service.add_photo_to_appointment(appointment_id, file_path, description)
            click.echo(f"Фото добавлено с ID: {dto.id}")
        except (AppointmentNotFoundError, PhotoFileError) as e:
            click.echo(str(e), err=True)
        except Exception as e:
            click.echo(f"Ошибка: {e}", err=True)

    @photo.command('delete')
    @click.option('--id', required=True, type=int, help='ID фото')
    def photo_delete(id):
        """
        Удаляет фото (файл и запись).

        1. Получает сервис для работы с фотографиями.
        2. Пытается удалить запись о фотографии с указанным ID.
        3. Если запись существует, то пытается удалить файл фотографии.
        4. Если файл не удалился, то логируется ошибка.
        5. Если запись не существует, то выводится ошибка.
        6. Если произошла какая-то другая ошибка, то выводится ее текст.
        """
        AppLogger.get_instance( 
            name = 'cli',
            enable_file_logging = 'user',
           use_name_in_filename =  False, #  True, # 'user',
        ).debug( f"Удалить фото (файл и запись) id={id}" )
        service = get_photo_service()
        try:
            # Удаляем запись о фотографии с указанным ID
            service.delete_photo(id)

            # Выводим сообщение об успешном удалении
            click.echo(f"Фото ID {id} удалено.")
        except PhotoNotFoundError as e:
            # Если записи о фотографии не существует, то выводим ошибку
            click.echo(str(e), err=True)
        except PhotoFileError as e:
            # Если файл не удалился, то логируется ошибка
            click.echo(f"Ошибка при удалении файла: {e}", err=True)
        except Exception as e:
            # Если произошла какая-то другая ошибка, то выводится ее текст
            click.echo(f"Ошибка: {e}", err=True)

    # ------------------------------------------------------------------------------
    # Команды инициализации, синхронизации и статистики
    # ------------------------------------------------------------------------------

    # @click.command()
    # @click.option('--recreate/--no-recreate', default=False, help='Пересоздать БД (удалить существующую)')
    # @click.option('--test-data/--no-test-data', default=True, help='Заполнить тестовыми данными')
    # def init_db(recreate, test_data):
    #     """Инициализировать базу данных (создать таблицы, опционально тестовые данные)."""
    #     config = get_config_env()
    #     db_path = config['database_local_path']
    #     AppLogger.get_instance(
    #         name = 'system'
    #     ).debug(
    #         f"Инициализировать базу данных (создать таблицы, опционально тестовые данные): {db_path} ({os.path.abspath(db_path)})"
    #     )
    #     try:
    #         # Создаём движок и таблицы
    #         engine = create_db(db_path, recreate=recreate)
    #         if test_data:
    #             generate_test_data(db_path)
    #             # Создаём сессию и заполняем тестовыми данными
    #             # Session = sessionmaker(bind=engine)
    #             # session = Session()
    #             # generate_test_data(session)
    #             # session.close()
    #             click.echo("Тестовые данные добавлены.")
    #         click.echo(f"База данных инициализирована: {db_path} ({os.path.abspath(db_path)})")
    #     except Exception as e:
    #         click.echo(f"Ошибка инициализации БД: {e}", err=True)

    # @click.command()
    @cli.command()
    @click.option('--recreate/--no-recreate', default=False, help='Пересоздать БД (удалить существующую)')
    @click.option('--test-data/--no-test-data', default=True, help='Заполнить тестовыми данными')
    def init_db(recreate, test_data):
        """
        Инициализировать базу данных (создать таблицы, опционально тестовые данные).

        Это функция вызывает init_db_deps из dependencies, который инициализирует базу данных.

        Параметры:
            recreate - если True, то удалить существующую базу данных перед инициализацией.
            test_data - если True, то заполнить тестовыми данными.

        Возвращает:
            Ничего не возвращает, но может вывести ошибку, если произошла какая-то ошибка.

        Исключения:
            Exception - если произошла какая-то ошибка при инициализации базы данных.
        """
        AppLogger.get_instance(
            name = 'cli',
            enable_file_logging = 'user',
           use_name_in_filename =  False, #  True, # 'user',
        ).debug(
            f"Инициализировать базу данных (создать таблицы, опционально тестовые данные)"
        )
        try:
            # Вызываем init_db_deps из dependencies, который инициализирует базу данных
            init_db_deps(recreate=recreate, test_data=test_data)
            click.echo("База данных инициализирована.")
            # click.echo(f"База данных инициализирована: {db_path} ({os.path.abspath(db_path)})")
        except Exception as e:
            # Если произошла какая-то ошибка, то выводим ее текст
            click.echo(f"Ошибка инициализации БД: {e}", err=True)


    # @click.command()
    @cli.command()
    def sync_download():
        """
        Скачать базу данных с Яндекс.Диска (асинхронно с отображением прогресса).

        1. Получаем сервис для работы с синхронизацией.
        2. Выводим сообщение о начале скачивания.
        3. Определяем колбэк для передачи прогресса скачивания файла с Яндекс.Диска.
        4. Пытаемся скачать файл с помощью сервиса.
        5. Если скачивание успешно, то выводим сообщение об успешном завершении.
        6. Если скачивание завершилось с ошибкой, то выводим ее текст.
        """

        AppLogger.get_instance(
            name = 'cli',
            enable_file_logging = 'user',
           use_name_in_filename =  False, #  True, # 'user',
        ).debug(
            f"Скачать базу данных с Яндекс.Диска (асинхронно с отображением прогресса))"
        )

        service = get_sync_service()
        click.echo("Начинаем скачивание...")

        def progress_callback(current, total):
            """
            Колбэк для передачи прогресса скачивания файла с Яндекс.Диска.
            Он будет вызываться изнутри функции run в потоке DownloadThread.

            :param current: (int) Текущее значение прогресса (например, количество байт, уже переданных на Диск).
            :param total: (int) Общее количество байт, которое будет передано на Диск.
            """
            percent = (current / total) * 100 if total else 0
            # Используем \r для обновления строки
            click.echo(f"\rПрогресс: {current}/{total} ({percent:.1f}%)", nl=False)

        try:
            result = service.download_sync(progress_callback=progress_callback)
            click.echo()  # перевод строки после завершения
            if result == 0:
                click.echo("Скачивание успешно завершено.")
            else:
                click.echo(f"Скачивание завершилось с ошибкой (код {result})")
        except Exception as e:
            click.echo(f"\nОшибка: {e}", err=True)

    # @click.command()
    @cli.command()
    def sync_upload():
        """
        Загрузить локальную базу данных на Яндекс.Диск.

        1. Получаем сервис для работы с синхронизацией.
        2. Выводим сообщение о начале загрузки.
        3. Определяем колбэк для передачи прогресса загрузки файла на Яндекс.Диск.
        4. Пытаемся загрузить файл с помощью сервиса.
        5. Если загрузка успешна, то выводим сообщение об успешном завершении.
        6. Если загрузка завершилась с ошибкой, то выводим ее текст.
        """

        AppLogger.get_instance(
            name = 'cli',
            enable_file_logging = 'user',
           use_name_in_filename =  False, #  True, # 'user',
        ).debug(
            f"Загрузить локальную базу данных на Яндекс.Диск"
        )

        service = get_sync_service()
        click.echo("Начинаем загрузку...")

        def progress_callback(current, total):
            """
            Колбэк для передачи прогресса загрузки файла на Яндекс.Диск.
            Он будет вызываться изнутри функции run в потоке DownloadThread.

            :param current: (int) Текущее значение прогресса (например, количество байт, уже переданных на Диск).
            :param total: (int) Общее количество байт, которое будет передано на Диск.
            """
            percent = (current / total) * 100 if total else 0
            # Используем \r для обновления строки
            click.echo(f"\rПрогресс: {current}/{total} ({percent:.1f}%)", nl=False)

        try:
            result = service.upload_sync(progress_callback=progress_callback)
            click.echo()  # перевод строки после завершения
            if result == 0:
                click.echo("Загрузка успешно завершена.")
            else:
                click.echo(f"Загрузка завершилась с ошибкой (код {result})")
        except Exception as e:
            click.echo(f"\nОшибка: {e}", err=True)

    # @click.command()
    @cli.command()
    def stats():
        """
        Показать статистику по базе данных.

        Она содержит информацию о количестве пациентов, приёмов, заметок и фотографий в базе данных.
        """
        AppLogger.get_instance(
            name = 'cli',
            enable_file_logging = 'user',
           use_name_in_filename =  False, #  True, # 'user',
        ).debug(
            f"Показать статистику по базе данных"
        )
        db = get_db()
        try:
            with db.session_scope() as session:
                # Получаем количество пациентов
                patient_count = session.query(Patient).count()
                # Получаем количество приёмов
                app_count = session.query(Appointment).count()
                # Получаем количество заметок
                note_count = session.query(AppointmentNote).count()
                # Получаем количество фотографий
                photo_count = session.query(Photo).count()
            click.echo(f"Пациентов: {patient_count}")
            click.echo(f"Приёмов: {app_count}")
            click.echo(f"Заметок: {note_count}")
            click.echo(f"Фотографий: {photo_count}")
        except Exception as e:
            click.echo(f"Ошибка получения статистики: {e}", err=True)

    # ------------------------------------------------------------------------------
    # Главная группа команд
    # ------------------------------------------------------------------------------

    # @click.group()
    # def cli():
    #     """Медицинское приложение - управление данными из консоли."""
    #     AppLogger.get_instance(
    #         name = 'system'
    #     ).debug(
    #         f"Медицинское приложение - управление данными из консоли"
    #     )
    #     pass

    # cli.add_command(patient)
    # cli.add_command(appointment)
    # cli.add_command(note)
    # cli.add_command(photo)
    # cli.add_command(init_db)
    # cli.add_command(sync_download)
    # cli.add_command(sync_upload)
    # cli.add_command(stats)


    # ------------------------------------------------------------------------------
    # Интерактивный режим (меню)
    # ------------------------------------------------------------------------------

    def patient_menu():
        """
        Меню управления пациентами.

        В этом меню можно просмотреть список всех пациентов, просмотреть информацию о пациенте по ID,
        создать нового пациента, обновить данные пациента, удалить пациента, а также поискать пациентов
        с фильтрами.
        """
        rename_map_patients = {
            'id': 'ID',
            'first_name': 'Имя',
            'last_name': 'Фамилия',
            'birth_date': 'Дата рождения (ГГГГ-ММ-ДД)',
            'phone': 'Телефон',
            'email': 'Email'
        }
        while True:
            click.clear()
            click.echo("=== Управление пациентами ===")
            click.echo("1. Список всех пациентов")
            # Выводит список всех пациентов
            click.echo("2. Просмотр пациента по ID")
            # Выводит информацию о пациенте по ID
            click.echo("3. Создать нового пациента")
            # Создать нового пациента
            click.echo("4. Обновить данные пациента")
            # Обновить данные пациента
            click.echo("5. Удалить пациента")
            # Удалить пациента
            click.echo("6. Поиск пациентов с фильтрами")
            # Поискать пациентов с фильтрами
            click.echo("0. Вернуться в главное меню")
            # Вернуться в главное меню
            choice = click.prompt("Выберите действие", type=int)

            AppLogger.get_instance( 
                name = 'cli',
                enable_file_logging = 'user',
               use_name_in_filename =  False, #  True, # 'user',
            ).debug( f"Меню управления пациентами: choice={choice}" )

            ctx = click.get_current_context()

            if choice == 1:
                # Выводит список всех пациентов
                ctx.invoke(patient_list)
                click.pause()
            elif choice == 2:
                # Выводит информацию о пациенте по ID
                pid = click.prompt("Введите ID пациента", type=int)
                ctx.invoke(patient_get, id=pid)
                click.pause()
            elif choice == 3:
                # Создать нового пациента
                # rename_map_patients = {
                #     'id': 'ID',
                #     'first_name': 'Имя',
                #     'last_name': 'Фамилия',
                #     'birth_date': 'Дата рождения (ГГГГ-ММ-ДД)',
                #     'phone': 'Телефон',
                #     'email': 'Email'
                # }
                data = collect_dto_from_input(
                    PatientDTO, 
                    exclude=['id'], 
                    rename_map = rename_map_patients
                )
                ctx.invoke(patient_create, **data)
                click.pause()

                # # Создать нового пациента

            elif choice == 4:
                pid = click.prompt("ID пациента для обновления", type=int)
                service = get_patient_service()
                try:
                    current = service.get_patient_by_id(pid)
                    click.echo("\n--- Текущие данные ---")

                    # Выводим текущие данные с русскими названиями
                    for line in get_text_echo(
                        current, 
                        rename_map=rename_map_patients
                    ):
                        click.echo(line)
                    click.echo("----------------------\n")
                except PatientNotFoundError as e:
                    click.echo(str(e))
                    click.pause()
                    continue

                # Собираем новые значения (пустые строки игнорируем)
                fields = get_dto_fields(PatientDTO, exclude=['id'])
                update_data = {}
                for f in fields:
                    # Используем русское название из rename_map, если есть
                    display_name = rename_map_patients.get(f['name'], f['description'])
                    prompt = f"Новое значение для '{display_name}' (Enter - оставить текущее)"
                    val = click.prompt(prompt, default="")
                    if val:
                        # Преобразование типа
                        if f['type'] == int:
                            update_data[f['name']] = int(val)
                        elif f['type'] == date:
                            try:
                                update_data[f['name']] = date.fromisoformat(val)
                            except ValueError:
                                click.echo("Неверный формат даты. Пропускаем поле.")
                        # elif f['type'] == str:
                        else:
                            update_data[f['name']] = val
                        # 0==0
                        # при необходимости добавьте другие типы

                ctx.invoke(patient_update, id=pid, **update_data)
                
                click.pause()
           
            elif choice == 5:
                # Удалить пациента
                pid = click.prompt("ID пациента для удаления", type=int)
                ctx.invoke(patient_delete, id=pid)
                click.pause()
            elif choice == 6:
                # Поискать пациентов с фильтрами
                filters = []
                click.echo("Введите условия фильтрации. Для завершения ввода оставьте название столбца пустым.")
                while True:
                    column = click.prompt("Столбец (например: last_name, birth_date)", default="")
                    if not column:
                        break
                    op = click.prompt("Оператор (eq, ne, gt, ge, lt, le, like, ilike, fuzzy)", default="eq")
                    value = click.prompt("Значение", default="")
                    filters.append(f"{column}:{op}:{value}")
                threshold = click.prompt("Порог нечеткого поиска (0-100)", default=60, type=int)
                ctx.invoke(patient_list, filter=tuple(filters), fuzzy_threshold=threshold)
                click.pause()
            elif choice == 0:
                # Вернуться в главное меню
                break
            else:
                click.echo("Неверный выбор. Нажмите Enter для продолжения.")
                click.pause()


    def appointment_menu():
        """Меню управления приёмами."""
        rename_map_appointments = {
            'id': 'ID',
            'patient_id': 'ID пациента',
            'date': 'Дата (ГГГГ-ММ-ДД)',
            'time': 'Время (ЧЧ:MM)',
            'note_id': 'ID заметки',
            'patient_name': 'Пациент',
            'note_text': 'Заметка'
        }
        while True:
            click.clear()
            click.echo("=== Управление приёмами ===")
            click.echo("1. Список всех приёмов")
            click.echo("2. Список приёмов пациента")
            click.echo("3. Просмотр приёма по ID")
            click.echo("4. Создать новый приём")
            click.echo("5. Обновить приём")
            click.echo("6. Удалить приём")
            click.echo("7. Поиск приёмов с фильтрами")
            click.echo("0. Вернуться в главное меню")
            choice = click.prompt("Выберите действие", type=int)

            AppLogger.get_instance( 
                name = 'cli',
                enable_file_logging = 'user',
               use_name_in_filename =  False, #  True, # 'user',
            ).debug( f"Меню управления приёмами: choice={choice}" )

            ctx = click.get_current_context()

            # 1. Список всех приёмов
            if choice == 1:
                ctx.invoke(appointment_list)
                click.pause()

            # 2. Список приёмов пациента
            elif choice == 2:
                pid = click.prompt("Введите ID пациента", type=int)
                ctx.invoke(appointment_list, patient_id=pid)
                click.pause()

            # 3. Просмотр приёма по ID
            elif choice == 3:
                aid = click.prompt("Введите ID приёма", type=int)
                ctx.invoke(appointment_get, id=aid)
                click.pause()

            # 4. Создать новый приём
            elif choice == 4:

                # rename_map_appointments = {
                #     'id': 'ID',
                #     'patient_id': 'ID пациента',
                #     'date': 'Дата (ГГГГ-ММ-ДД)',
                #     'time': 'Время (ЧЧ:MM)',
                #     'note_id': 'ID заметки',
                #     'patient_name': 'Пациент',
                #     'note_text': 'Заметка'
                # }
                data = collect_dto_from_input(
                    AppointmentDTO,
                    exclude=[
                        'id', 
                        'patient_name', 
                        'note_id',
                        'note_text'
                    ],
                    rename_map=rename_map_appointments
                )
                note_text = click.prompt("Текст заметки (оставьте пустым, если нет)", default="")
                if note_text:
                    data['note_text'] = note_text
                ctx.invoke(appointment_create, **data)
                click.pause()
            # 5. Обновить приём
            elif choice == 5:
                # appointment_update_set
                # rename_map_appointments = {
                #     'id': 'ID',
                #     'patient_id': 'ID пациента',
                #     'date': 'Дата (ГГГГ-ММ-ДД)',
                #     'time': 'Время (ЧЧ:MM)',
                #     'note_id': 'ID заметки',
                #     'patient_name': 'Пациент',
                #     'note_text': 'Заметка'
                # }
                aid = click.prompt("ID приёма для обновления", type=int)
                try:
                    current = get_appointment_service().get_appointment(aid)
                    click.echo("\n--- Текущие данные приёма ---")
                    for line in get_text_echo(current, rename_map=rename_map_appointments):
                        click.echo(line)
                    click.echo("-----------------------------\n")
                except AppointmentNotFoundError as e:
                    click.echo(str(e))
                    click.pause()
                    continue

                fields = get_dto_fields(AppointmentDTO, exclude=['id', 'patient_name', 'note_text'])
                update_data = {}
                for f in fields:
                    display_name = rename_map_appointments.get(f['name'], f['description'])
                    prompt = f"Новое значение для '{display_name}' (Enter - оставить текущее)"
                    val = click.prompt(prompt, default="")
                    if val:
                        if f['type'] == int:
                            update_data[f['name']] = int(val)
                        elif f['type'] == date:
                            try:
                                update_data[f['name']] = date.fromisoformat(val)
                            except ValueError:
                                click.echo("Неверный формат даты. Пропускаем поле.")
                        elif f['type'] == time:
                            try:
                                h, m = map(int, val.split(':'))
                                update_data[f['name']] = time(h, m)
                            except:
                                click.echo("Неверный формат времени. Пропускаем поле.")
                        else:
                            update_data[f['name']] = val
                note_text = click.prompt("Новый текст заметки (Enter - оставить текущую)", default="")
                if note_text:
                    update_data['note_text'] = note_text
                ctx.invoke(appointment_update, id=aid, **update_data)
                click.pause()

            

            # 6. Удалить приём
            elif choice == 6:
                aid = click.prompt("ID приёма для удаления", type=int)
                ctx.invoke(appointment_delete, id=aid)
                click.pause()

            # 7. Поиск приёмов с фильтрами
            elif choice == 7:
                filters = []
                click.echo("Введите условия фильтрации. Для завершения ввода оставьте название столбца пустым.")
                while True:
                    column = click.prompt("Столбец (например: date, patient_id)", default="")
                    if not column:
                        break
                    op = click.prompt("Оператор (eq, ne, gt, ge, lt, le, like, ilike, fuzzy)", default="eq")
                    value = click.prompt("Значение", default="")
                    filters.append(f"{column}:{op}:{value}")
                threshold = click.prompt("Порог нечеткого поиска (0-100)", default=60, type=int)
                ctx.invoke(appointment_list, filter=tuple(filters), fuzzy_threshold=threshold)
                click.pause()

            elif choice == 0:
                break
            else:
                click.echo("Неверный выбор.")
                click.pause()

    def note_menu():
        """
        Меню управления заметками.

        В этом меню доступны следующие действия:
        1. Вывести список всех заметок
        2. Просмотр заметки по ID
        3. Создать заметку (ввод текста)
        4. Создать заметку из файла
        5. Обновить заметку
        6. Удалить заметку
        0. Вернуться в главное меню
        """
        rename_map_note = {
            'id': 'ID',
            'text': 'Текст заметки'
        }
        while True:
            click.clear()
            click.echo("=== Управление заметками ===")
            click.echo("1. Список всех заметок")
            click.echo("2. Просмотр заметки по ID")
            click.echo("3. Создать заметку (ввод текста)")
            click.echo("4. Создать заметку из файла")
            click.echo("5. Обновить заметку")
            click.echo("6. Удалить заметку")
            click.echo("0. Вернуться в главное меню")
            choice = click.prompt("Выберите действие", type=int)

            AppLogger.get_instance(
                name = 'cli',
                enable_file_logging = 'user',
               use_name_in_filename =  False, #  True, # 'user',
            ).debug(f"Меню управления заметками: choice={choice}")
            ctx = click.get_current_context()

            if choice == 1:
                ctx.invoke(note_list)
                click.pause()
            elif choice == 2:
                nid = click.prompt("Введите ID заметки", type=int)
                ctx.invoke(note_get, id=nid)
                click.pause()
            elif choice == 3:
                data = collect_dto_from_input(
                    AppointmentNoteDTO,
                    exclude=['id'],
                    rename_map=rename_map_note
                )
                ctx.invoke(note_create, **data)
                click.pause()
            elif choice == 4:
                file_path = click.prompt("Путь к файлу", type=click.Path(exists=True))
                ctx.invoke(note_create_from_file, file=file_path)
                click.pause()
            elif choice == 5:
                nid = click.prompt("ID заметки для обновления", type=int)
                try:
                    current = get_note_service().get_note(nid)
                    click.echo("\n--- Текущие данные заметки ---")
                    for line in get_text_echo(current, rename_map=rename_map_note):
                        click.echo(line)
                    click.echo("-----------------------------\n")
                except AppointmentNoteNotFoundError as e:
                    click.echo(str(e))
                    click.pause()
                    continue

                # Собираем новые значения (пустые строки игнорируем)
                fields = get_dto_fields(AppointmentNoteDTO, exclude=['id'])
                update_data = {}
                for f in fields:
                    display_name = rename_map_note.get(f['name'], f['description'])
                    prompt = f"Новое значение для '{display_name}' (Enter - оставить текущее)"
                    val = click.prompt(prompt, default="")
                    if val:
                        if f['type'] == str:
                            update_data[f['name']] = val
                        # при необходимости добавьте другие типы
                ctx.invoke(note_update, id=nid, **update_data)
                click.pause()
            elif choice == 6:
                nid = click.prompt("ID заметки для удаления", type=int)
                ctx.invoke(note_delete, id=nid)
                click.pause()
            elif choice == 0:
                break
            else:
                click.echo("Неверный выбор.")
                click.pause()

    def photo_menu():
        """
        Меню управления фотографиями.

        В этом меню доступны следующие действия:
        1. Вывести список фото для приёма
        2. Добавить фото к приёму
        3. Удалить фото
        0. Вернуться в главное меню
        """
        while True:
            click.clear()
            click.echo("=== Управление фотографиями ===")
            click.echo("1. Список фото для приёма")
            click.echo("2. Добавить фото к приёму")
            click.echo("3. Удалить фото")
            click.echo("0. Вернуться в главное меню")
            choice = click.prompt("Выберите действие", type=int)
            
            AppLogger.get_instance( 
                name = 'cli',
                enable_file_logging = 'user',
               use_name_in_filename =  False, #  True, # 'user',
            ).debug( f"Меню управления фотографиями: choice={choice}" )

            ctx = click.get_current_context()

            # Вывести список фото для приёма
            if choice == 1:
                appointment_id = click.prompt("Введите ID приёма", type=int)
                ctx.invoke(photo_list, appointment_id=appointment_id)
                click.pause()
            # Добавить фото к приёму
            elif choice == 2:
                appointment_id = click.prompt("ID приёма", type=int)
                file_path = click.prompt("Путь к файлу изображения", type=click.Path(exists=True))
                description = click.prompt("Описание (оставьте пустым)", default="")
                ctx.invoke(photo_add, appointment_id=appointment_id, file=file_path, description=description)
                click.pause()
            # Удалить фото
            elif choice == 3:
                photo_id = click.prompt("ID фото для удаления", type=int)
                ctx.invoke(photo_delete, id=photo_id)
                click.pause()
            # Вернуться в главное меню
            elif choice == 0:
                break
            else:
                click.echo("Неверный выбор.")
                click.pause()


    def db_menu():
        """
        Меню управления базой данных.

        В этом меню доступны следующие действия:
        1. Инициализировать БД (создать таблицы)
        2. Показать статистику
        0. Вернуться в главное меню
        """
        while True:
            click.clear()
            click.echo("=== Управление базой данных ===")
            click.echo("1. Инициализировать БД (создать таблицы)")
            click.echo("   - Удаляет существующие таблицы и создает новые")
            click.echo("   - Очищает тестовые данные")
            click.echo("2. Показать статистику")
            click.echo("   - Выводит информацию о количестве пациентов, приёмов, заметок и фотографий в базе данных")
            click.echo("0. Вернуться в главное меню")
            choice = click.prompt("Выберите действие", type=int)
            
            AppLogger.get_instance( 
                name = 'cli',
                enable_file_logging = 'user',
               use_name_in_filename =  False, #  True, # 'user',
            ).debug( f"Меню управления базой данных: choice={choice}" )

            ctx = click.get_current_context()

            # Инициализировать БД (создать таблицы)
            if choice == 1:
                recreate = click.confirm("Пересоздать БД (удалить все данные)?", default=False)
                test_data = click.confirm("Заполнить тестовыми данными?", default=True)
                ctx.invoke(init_db, recreate=recreate, test_data=test_data)
                click.pause()
            # Показать статистику
            elif choice == 2:
                ctx.invoke(stats)
                click.pause()
            # Вернуться в главное меню
            elif choice == 0:
                break
            else:
                click.echo("Неверный выбор.")
                click.pause()


    def sync_menu():
        """
        Меню для работы с синхронизацией с Яндекс.Диском.

        В этом меню доступны следующие действия:
        1. Скачать базу данных - скачивает локальную базу данных с Яндекс.Диск
        2. Загрузить базу данных - загружает локальную базу данных на Яндекс.Диск
        0. Вернуться в главное меню - возвращает в главное меню
        """
        while True:
            click.clear()
            click.echo("=== Синхронизация с Яндекс.Диском ===")
            click.echo("1. Скачать базу данных")
            click.echo("   - Скачивает локальную базу данных с Яндекс.Диск")
            click.echo("2. Загрузить базу данных")
            click.echo("   - Загружает локальную базу данных на Яндекс.Диск")
            click.echo("0. Вернуться в главное меню")
            click.echo("   - Возвращает в главное меню")
            choice = click.prompt("Выберите действие", type=int)
            
            AppLogger.get_instance( 
                name = 'cli',
                enable_file_logging = 'user',
               use_name_in_filename =  False, #  True, # 'user',
            ).debug( f"Меню синхронизации: choice={choice}" )

            ctx = click.get_current_context()

            if choice == 1:
                ctx.invoke(sync_download)
                click.pause()
            elif choice == 2:
                ctx.invoke(sync_upload)
                click.pause()
            elif choice == 0:
                break
            else:
                click.echo("Неверный выбор.")
                click.pause()


    @cli.command()
    def menu():
        """
        Интерактивный режим с выбором действия по номеру.
        
        В этом режиме пользователь может выбрать категорию для работы с данными.
        """
        while True:
            click.clear()
            click.echo("=== Медицинское приложение (интерактивный режим) ===")
            click.echo("Выберите категорию:")
            
            # Пациенты
            click.echo("1. Пациенты")
            
            # Приёмы
            click.echo("2. Приёмы")
            
            # Заметки
            click.echo("3. Заметки")
            
            # Фотографии
            click.echo("4. Фотографии")
            
            # Управление базой данных
            click.echo("5. Управление базой данных")
            
            # Синхронизация
            click.echo("6. Синхронизация")
            
            # Выход
            click.echo("0. Выход")
            choice = click.prompt("Ваш выбор", type=int)

            AppLogger.get_instance( 
                name = 'cli',
                enable_file_logging = 'user',
               use_name_in_filename =  False, #  True, # 'user',
            ).debug( f"Интерактивный режим с выбором действия по номеру: choice={choice}" )

            if choice == 1:
                patient_menu()
            elif choice == 2:
                appointment_menu()
            elif choice == 3:
                note_menu()
            elif choice == 4:
                photo_menu()
            elif choice == 5:
                db_menu()
            elif choice == 6:
                sync_menu()
            elif choice == 0:
                click.echo("До свидания!")
                break
            else:
                click.echo("Неверный выбор, попробуйте снова.")
                click.pause()
    return cli

def start_cli(
        if_len_sys_argv_1 : bool = True    
):
    """
    Функция для запуска интерактивного меню или консольного интерфейса в зависимости от переданных аргументов.

    Если аргумент не передан, или его значение равно True, то запускается интерактивное меню.
    В противном случае, запускается консольный интерфейс.

    :param if_len_sys_argv_1: bool
        Если аргумент не передан, или его значение равно True, то запускается интерактивное меню.
    """
    # cli = create_cli()
    # if if_len_sys_argv_1:
    #     # Если аргументы не переданы, запускаем интерактивное меню
    #     menu()
    # else:
    #     # Если аргумент передан, запускаем консольный интерфейс
    #     cli()
    cli = create_cli()
    if if_len_sys_argv_1:
        # Запуск интерактивного меню
        ctx = click.Context(cli, info_name=cli.name)
        menu_cmd = cli.get_command(ctx, 'menu')
        if menu_cmd is None:
            click.echo("Ошибка: команда 'menu' не найдена", err=True)
            return
        ctx.invoke(menu_cmd)
    else:
        # Обычный запуск с аргументами командной строки
        cli()

if __name__ == '__main__':
    start_cli(len(sys.argv) == 1)