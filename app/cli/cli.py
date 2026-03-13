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
import os  # Импорт модуля os для работы с путями файлов и директориями (например, чтобы получить абсолютный путь к файлу).
import sys  # Импорт модуля sys для работы с системными параметрами, такими как sys.path (список путей для импорта модулей).
from datetime import date, time
from typing import Optional


# Импорты модулей
def _add_package_name(
    file_module: str = None,
    levels_up: int = 3,           # <-- сколько уровней вверх до корня проекта
) -> None:
    
    """
    Что это (кратко): Добавляет корень проекта в sys.path и устанавливает правильный __package__.

    Что это (максимально подробно): Эта функция настраивает окружение Python таким образом, чтобы можно было использовать относительные импорты (например, from .module import something) без необходимости запускать скрипт с флагом "-m" (как модуль). Она работает только если скрипт запущен напрямую (не импортирован). Функция получает абсолютный путь к текущему файлу, добавляет родительскую директорию в sys.path (список путей для поиска модулей), и устанавливает глобальную переменную __package__ как имя текущей директории. Это полезно в проектах с nested папками, где импорты могут сломаться.

    Как работает: Сначала объявляется global __package__ для изменения системной переменной. Затем os.path.abspath(__file__) дает полный путь к скрипту, os.path.dirname убирает имя файла, оставляя папку. sys.path.append добавляет родительскую папку (dirname еще раз). Наконец, __package__ = basename(package_dir) — имя папки. Вызывается только в if __name__ == '__main__', чтобы не мешать, если скрипт импортирован.

    Примеры запуска:
    # В скрипте: if __name__ == '__main__': _add_package_name()
    # После вызова: sys.path включает родительскую папку (например, '/path/to/modules'), __package__ = 'parsers_sheregeh'. Теперь относительные импорты работают.
    # Если запустить как модуль (python -m script), функция не нужна, но она не навредит.
    # Если не вызвать: относительный импорт from .module... может вызвать ImportError as e: attempted relative import with no known parent package.

    :param file_module: (str) = обычно __file__  - указатель на путь к модулю, папку которого делаем пакетом для относительных импортов (содержит путь к текущему скрипту)
    :param levels_up: (int) - на сколько уровней подниматься вверх до корня проекта
                       (подберите под структуру вашего проекта)
                       Примеры:
                         2 → до папки app
    """
    if file_module is None:
        file_module = __file__

    # Получаем директорию текущего файла
    current_dir = os.path.dirname(os.path.abspath(file_module))

    # Поднимаемся на levels_up уровней вверх — это и будет корень проекта
    project_root = current_dir
    for _ in range(levels_up):
        project_root = os.path.dirname(project_root)

    # Добавляем корень проекта в начало sys.path (высокий приоритет)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    # Вычисляем правильное значение __package__
    # Пример: /project_med/app/models/bd → "app.models.bd"
    rel_path = os.path.relpath(current_dir, project_root)
    
    if rel_path == '.':
        package_name = ''
    else:
        package_name = rel_path.replace(os.sep, '.').strip('.')

    # Устанавливаем __package__
    global __package__
    if package_name:
        __package__ = package_name
    else:
        # Если мы в корне — можно оставить None или пустую строку
        __package__ = None

try:
    from ..utils.logger.logger import AppLogger
except ImportError as e:
    try:
        # Попытка абсолютного импорта, если модуль запущен как скрипт
        _add_package_name(file_module = __file__,levels_up = 2)
        from ..utils.logger.logger import AppLogger
    except ImportError as e:
        pass #  raise # e # pass

try:
    from ..backend.database import Database
except ImportError as e:
    try:
        # Попытка абсолютного импорта, если модуль запущен как скрипт
        _add_package_name(file_module = __file__,levels_up = 2)
        from ..backend.database import Database
    except ImportError as e:
        pass #  raise # e # pass

try:
    from ..backend.repositories import (
        PatientRepository,
        AppointmentRepository,
        AppointmentNoteRepository,
        PhotoRepository
    )

except ImportError as e:
    try:
        # Попытка абсолютного импорта, если модуль запущен как скрипт
        _add_package_name(file_module = __file__,levels_up = 2)
        from ..backend.repositories import (
            PatientRepository,
            AppointmentRepository,
            AppointmentNoteRepository,
            PhotoRepository
        )
    except ImportError as e:
        pass #  raise # e # pass

try:
    from ..controllers.conf.get_config import get_config_env
except ImportError as e:
    try:
        # Попытка абсолютного импорта, если модуль запущен как скрипт
        _add_package_name(file_module = __file__,levels_up = 2)
        from ..controllers.conf.get_config import get_config_env
    except ImportError as e:
        pass #  raise # e # pass

try:
    from ..services import (
        PatientService,
        AppointmentService,
        NoteService,
        PhotoService,
        SyncService
    )
except ImportError as e:
    try:
        # Попытка абсолютного импорта, если модуль запущен как скрипт
        _add_package_name(file_module = __file__,levels_up = 2)
        from ..services import (
            PatientService,
            AppointmentService,
            NoteService,
            PhotoService,
            SyncService
        )
    except ImportError as e:
        pass #  raise # e # pass

try:
    from ..dto import (
        PatientDTO,
        AppointmentDTO,
        AppointmentNoteDTO,
        PhotoDTO
    )
except ImportError as e:
    try:
        # Попытка абсолютного импорта, если модуль запущен как скрипт
        _add_package_name(file_module = __file__,levels_up = 2)
        from ..dto import (
            PatientDTO,
            AppointmentDTO,
            AppointmentNoteDTO,
            PhotoDTO
        )
    except ImportError as e:
        pass #  raise # e # pass

try:
    from ..exceptions import (
        PatientNotFoundError,
        PatientValidationError,
        AppointmentNotFoundError,
        AppointmentNoteNotFoundError,
        PhotoNotFoundError,
        PhotoFileError,
        DownloadError,
        UploadError
    )
except ImportError as e:
    try:
        # Попытка абсолютного импорта, если модуль запущен как скрипт
        _add_package_name(file_module = __file__,levels_up = 2)
        from ..exceptions import (
            PatientNotFoundError,
            PatientValidationError,
            AppointmentNotFoundError,
            AppointmentNoteNotFoundError,
            PhotoNotFoundError,
            PhotoFileError,
            DownloadError,
            UploadError
        )
    except ImportError as e:
        pass #  raise # e # pass

try:
    # from ..models.bd.models import init_db  # для инициализации БД
    from ..models.bd.models import create_db, generate_test_data, Patient, Appointment, AppointmentNote, Photo
except ImportError as e:
    try:
        # Попытка абсолютного импорта, если модуль запущен как скрипт
        _add_package_name(file_module = __file__,levels_up = 2)
        # from ..models.bd.models import init_db  # для инициализации БД
        from ..models.bd.models import create_db, generate_test_data, Patient, Appointment, AppointmentNote, Photo
    except ImportError as e:
        pass #  raise # e # pass

# Сторонние библиотеки

import click # pip install click
from sqlalchemy.orm import sessionmaker  

# ------------------------------------------------------------------------------
# Инициализация общих объектов
# ------------------------------------------------------------------------------

def get_db() -> Database:
    """Возвращает экземпляр Database, сконфигурированный из .env."""
    config = get_config_env()
    db_path = config['database_local_path']

    AppLogger.get_instance(
        name = 'system'
    ).debug(
        f"Возвращает экземпляр Database, сконфигурированный из .env.: {db_path} ({os.path.abspath(db_path)})"
    )

    db_url = f"sqlite:///{config['database_local_path']}"
    return Database(db_url)

def get_patient_service() -> PatientService:
    return PatientService(get_db())

def get_appointment_service() -> AppointmentService:
    db = get_db()
    note_service = NoteService(db)
    return AppointmentService(db, note_service=note_service)
def get_note_service() -> NoteService:
    return NoteService(get_db())

def get_photo_service() -> PhotoService:
    config = get_config_env()
    photos_path = config.get('PHOTOS_STORAGE_PATH', './photos')
    return PhotoService(get_db(), photos_path)

def get_sync_service() -> SyncService:
    return SyncService()

# ------------------------------------------------------------------------------
# Группа команд для пациентов
# ------------------------------------------------------------------------------

@click.group()
def patient():
    """Управление пациентами."""
    pass

@patient.command('list')
@click.option('--filter', '-f', multiple=True, help='Фильтр в формате column:operator:value (например: last_name:like:Петров). Для нечеткого поиска: fuzzy:column:value')
@click.option('--fuzzy-threshold', default=60, type=int, help='Порог схожести для нечеткого поиска (0-100)')
def patient_list(filter, fuzzy_threshold):
    """Вывести список пациентов с возможностью фильтрации."""
    AppLogger.get_instance( name = 'system' ).debug( 
        f"Вывести список пациентов с возможностью фильтрации. filter={filter}, fuzzy_threshold={fuzzy_threshold}" 
    )
    service = get_patient_service()
    # print('filter', filter)
    # print('fuzzy_threshold', fuzzy_threshold)
    filters = []
    for f in filter:
        if f.startswith('fuzzy:'):
            parts = f.split(':', 2)
            if len(parts) != 3:
                click.echo("Неверный формат fuzzy-фильтра: fuzzy:column:value", err=True)
                return
            _, column, value = parts
            filters.append({'column': column, 'operator': 'fuzzy', 'value': value})
        else:
            parts = f.split(':', 2)
            if len(parts) != 3:
                click.echo(f"Неверный формат фильтра: {f}. Используйте column:operator:value", err=True)
                return
            column, op, value = parts
            filters.append({'column': column, 'operator': op, 'value': value})
    try:
        patients = service.get_patients_filtered(filters, fuzzy_threshold)
        if not patients:
            click.echo("Пациенты не найдены.")
            return
        for p in patients:
            click.echo(f"ID: {p.id}, ФИО: {p.last_name} {p.first_name}, "
                       f"Дата рождения: {p.birth_date}, Телефон: {p.phone}")
    except Exception as e:
        click.echo(f"Ошибка: {e}", err=True)

@patient.command('get')
@click.option('--id', required=True, type=int, help='ID пациента')
def patient_get(id):
    """Вывести информацию о пациенте по ID."""
    AppLogger.get_instance( name = 'system' ).debug( 
        f"Создвести информацию о пациенте по ID. id={id}" 
    )
    service = get_patient_service()
    try:
        p = service.get_patient_by_id(id)
        click.echo(f"ID: {p.id}")
        click.echo(f"Имя: {p.first_name}")
        click.echo(f"Фамилия: {p.last_name}")
        click.echo(f"Дата рождения: {p.birth_date}")
        click.echo(f"Телефон: {p.phone}")
        click.echo(f"Email: {p.email}")
    except PatientNotFoundError as e:
        click.echo(str(e), err=True)
    except Exception as e:
        click.echo(f"Ошибка: {e}", err=True)

@patient.command('create')
@click.option('--first-name', required=True, help='Имя')
@click.option('--last-name', required=True, help='Фамилия')
@click.option('--birth-date', help='Дата рождения (ГГГГ-ММ-ДД)')
@click.option('--phone', help='Телефон')
@click.option('--email', help='Email')
def patient_create(first_name, last_name, birth_date, phone, email):
    """Создать нового пациента."""
    AppLogger.get_instance( name = 'system' ).debug( 
        f"Создать нового пациента (указывайте только изменяемые поля). first_name={first_name}, last_name={last_name}, birth_date={birth_date}, phone={phone}, email={email}" 
    )
    service = get_patient_service()
    bd = None
    if birth_date:
        try:
            bd = date.fromisoformat(birth_date)
        except ValueError:
            click.echo("Неверный формат даты. Используйте ГГГГ-ММ-ДД.", err=True)
            return
    dto_in = PatientDTO(
        id=None,
        first_name=first_name,
        last_name=last_name,
        birth_date=bd,
        phone=phone,
        email=email
    )
    try:
        dto_out = service.create_patient(dto_in)
        click.echo(f"Пациент создан с ID: {dto_out.id}")
    except PatientValidationError as e:
        click.echo(f"Ошибка валидации: {e}", err=True)
    except Exception as e:
        click.echo(f"Ошибка: {e}", err=True)

@patient.command('update')
@click.option('--id', required=True, type=int, help='ID пациента')
@click.option('--first-name', help='Имя')
@click.option('--last-name', help='Фамилия')
@click.option('--birth-date', help='Дата рождения (ГГГГ-ММ-ДД)')
@click.option('--phone', help='Телефон')
@click.option('--email', help='Email')
def patient_update(id, first_name, last_name, birth_date, phone, email):
    """Обновить данные пациента (указывайте только изменяемые поля)."""
    AppLogger.get_instance( name = 'system' ).debug( 
        f"Обновить данные пациента (указывайте только изменяемые поля). id={id}, ..." 
    )
    service = get_patient_service()
    try:
        existing = service.get_patient_by_id(id)
        if first_name is not None:
            existing.first_name = first_name
        if last_name is not None:
            existing.last_name = last_name
        if birth_date is not None:
            try:
                existing.birth_date = date.fromisoformat(birth_date)
            except ValueError:
                click.echo("Неверный формат даты.", err=True)
                return
        if phone is not None:
            existing.phone = phone
        if email is not None:
            existing.email = email
        updated = service.update_patient(existing)
        click.echo(f"Пациент ID {updated.id} обновлён.")
    except PatientNotFoundError as e:
        click.echo(str(e), err=True)
    except PatientValidationError as e:
        click.echo(f"Ошибка валидации: {e}", err=True)
    except Exception as e:
        click.echo(f"Ошибка: {e}", err=True)

@patient.command('delete')
@click.option('--id', required=True, type=int, help='ID пациента')
def patient_delete(id):
    """Удалить пациента по ID."""
    AppLogger.get_instance( name = 'system' ).debug( 
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

@click.group()
def appointment():
    """Управление приёмами."""
    pass

@appointment.command('list')
@click.option('--patient-id', type=int, help='ID пациента (если не указан, выводятся все приёмы)')
@click.option('--filter', '-f', multiple=True, help='Фильтр в формате column:operator:value (например: date:gt:2025-01-01). Для нечеткого поиска: fuzzy:note_text:значение')
@click.option('--fuzzy-threshold', default=60, type=int, help='Порог схожести для нечеткого поиска (0-100)')
def appointment_list(patient_id, filter, fuzzy_threshold):
    """Вывести список приёмов с возможностью фильтрации."""
    AppLogger.get_instance( name = 'system' ).debug( 
        f"Вывести список приёмов с возможностью фильтрации patient_id={patient_id}, filter={filter}, fuzzy_threshold={fuzzy_threshold}" 
    )
    service = get_appointment_service()
    filters = []

    for f in filter:
        if f.startswith('fuzzy:'):
            parts = f.split(':', 2)
            if len(parts) != 3:
                click.echo("Неверный формат fuzzy-фильтра: fuzzy:column:value", err=True)
                return
            _, column, value = parts
            # Для fuzzy поиска по тексту заметки нужно указать column='note_text' (виртуальное поле)
            filters.append({'column': column, 'operator': 'fuzzy', 'value': value})
        else:
            parts = f.split(':', 2)
            if len(parts) != 3:
                click.echo(f"Неверный формат фильтра: {f}. Используйте column:operator:value", err=True)
                return
            column, op, value = parts
            filters.append({'column': column, 'operator': op, 'value': value})
    try:
        if patient_id and not filters:

            # print('get_appointments_by_patient')
            apps = service.get_appointments_by_patient(patient_id)
        elif filters:
            # print('get_filtered')
            apps = service.get_filtered(filters, fuzzy_threshold)
        else:
            # print('get_all')
            apps = service.get_all()
        if not apps:
            click.echo("Приёмы не найдены.")
            return
        
        for a in apps:
            # Если есть заметка, покажем её текст (обрезанный)
            note_text = a.note_text[:50] + "..." if a.note_text else ""
            click.echo(f"ID: {a.id}, Пациент ID: {a.patient_id}, "
                       f"Дата: {a.date}, Время: {a.time}, Заметка: {note_text}")
    except Exception as e:
        click.echo(f"Ошибка: {e}", err=True)

@appointment.command('get')
@click.option('--id', required=True, type=int, help='ID приёма')
def appointment_get(id):
    """Вывести информацию о приёме."""
    AppLogger.get_instance( name = 'system' ).debug( f"Вывести информацию о приёме id={id}, ..." )
    service = get_appointment_service()
    try:
        a = service.get_appointment(id)
        click.echo(f"ID: {a.id}")
        click.echo(f"Пациент ID: {a.patient_id}")
        click.echo(f"Дата: {a.date}")
        click.echo(f"Время: {a.time}")
        click.echo(f"Заметка ID: {a.note_id}")
        if a.note:
            click.echo(f"Текст заметки: {a.note.text}")
    except AppointmentNotFoundError as e:
        click.echo(str(e), err=True)
    except Exception as e:
        click.echo(f"Ошибка: {e}", err=True)

# @appointment.command('create')
# @click.option('--patient-id', required=True, type=int, help='ID пациента')
# @click.option('--date', required=True, help='Дата приёма (ГГГГ-ММ-ДД)')
# @click.option('--time', 'time_str', help='Время (ЧЧ:ММ)')
# # @click.option('--note-id', type=int, help='ID существующей заметки')
# @click.option('--note-text', help='Текст новой заметки (если указан, создаётся новая заметка)')
# def appointment_create(patient_id, date, time_str, note_id, note_text):
#     """Создать новый приём."""
#     service = get_appointment_service()
#     try:
#         app_date = date.fromisoformat(date)
#     except ValueError:
#         click.echo("Неверный формат даты. Используйте ГГГГ-ММ-ДД.", err=True)
#         return
#     app_time = None
#     if time_str:
#         try:
#             h, m = map(int, time_str.split(':'))
#             app_time = time(h, m)
#         except:
#             click.echo("Неверный формат времени. Используйте ЧЧ:ММ.", err=True)
#             return
#     dto_in = AppointmentDTO(
#         id=None,
#         patient_id=patient_id,
#         date=app_date,
#         time=app_time,
#         note_id=note_id
#     )
#     try:
#         dto_out = service.create_appointment(dto_in, note_text=note_text)
#         click.echo(f"Приём создан с ID: {dto_out.id}")
#     except PatientNotFoundError as e:
#         click.echo(str(e), err=True)
#     except Exception as e:
#         click.echo(f"Ошибка: {e}", err=True)

@appointment.command('create')
@click.option('--patient-id', required=True, type=int, help='ID пациента')
@click.option('--date', 'date_str', required=True, help='Дата приёма (ГГГГ-ММ-ДД)')  # переименовано
@click.option('--time', 'time_str', help='Время (ЧЧ:ММ)')
@click.option('--note-text', help='Текст заметки (будет создана или использована существующая)')
def appointment_create(patient_id, date_str, time_str, note_text):
    """Создать новый приём. Заметка будет найдена или создана автоматически."""
    AppLogger.get_instance( name = 'system' ).debug( f"Создать новый приём. Заметка будет найдена или создана автоматически patient_id={patient_id}, ..." )
    service = get_appointment_service()
    try:
        app_date = date.fromisoformat(date_str)   # используем date_str
    except ValueError:
        click.echo("Неверный формат даты. Используйте ГГГГ-ММ-ДД.", err=True)
        return

    app_time = None
    if time_str:
        try:
            h, m = map(int, time_str.split(':'))
            app_time = time(h, m)
        except:
            click.echo("Неверный формат времени. Используйте ЧЧ:ММ.", err=True)
            return

    dto_in = AppointmentDTO(
        id=None,
        patient_id=patient_id,
        date=app_date,
        time=app_time,
        note_id=None
    )
    try:
        dto_out = service.create_appointment(dto_in, note_text=note_text)
        click.echo(f"Приём создан с ID: {dto_out.id}")
    except PatientNotFoundError as e:
        click.echo(str(e), err=True)
    except Exception as e:
        click.echo(f"Ошибка: {e}", err=True)


# @appointment.command('update')
# @click.option('--id', required=True, type=int, help='ID приёма')
# @click.option('--date', help='Новая дата (ГГГГ-ММ-ДД)')
# @click.option('--time', 'time_str', help='Новое время (ЧЧ:ММ)')
# @click.option('--note-id', type=int, help='Новый ID существующей заметки')
# @click.option('--note-text', help='Текст новой заметки (если указан, заменяет заметку)')
# def appointment_update(id, date, time_str, note_id, note_text):
#     """Обновить приём."""
#     AppLogger.get_instance( name = 'system' ).debug( f"Обновить приём id={id}, ..." )
#     service = get_appointment_service()
#     try:
#         existing = service.get_appointment(id)
#         if date:
#             try:
#                 existing.date = date.fromisoformat(date)
#             except ValueError:
#                 click.echo("Неверный формат даты.", err=True)
#                 return
#         if time_str:
#             try:
#                 h, m = map(int, time_str.split(':'))
#                 existing.time = time(h, m)
#             except:
#                 click.echo("Неверный формат времени.", err=True)
#                 return
#         # Передаём note_id или note_text в метод update
#         dto_in = existing
#         if note_id is not None:
#             dto_in.note_id = note_id
#         updated = service.update_appointment(dto_in, note_text=note_text)
#         click.echo(f"Приём ID {updated.id} обновлён.")
#     except AppointmentNotFoundError as e:
#         click.echo(str(e), err=True)
#     except Exception as e:
#         click.echo(f"Ошибка: {e}", err=True)

@appointment.command('update')
@click.option('--id', required=True, type=int, help='ID приёма')
@click.option('--date', 'date_str', help='Новая дата (ГГГГ-ММ-ДД)')  # переименовано
@click.option('--time', 'time_str', help='Новое время (ЧЧ:ММ)')
@click.option('--note-id', type=int, help='Новый ID существующей заметки')
@click.option('--note-text', help='Текст новой заметки (если указан, заменяет заметку)')
def appointment_update(id, date_str, time_str, note_id, note_text):
    """Обновить приём."""
    AppLogger.get_instance(name='system').debug(f"Обновить приём id={id}, ...")

    date_str = date_str if date_str else None
    time_str = time_str if time_str else None

    service = get_appointment_service()
    try:

        existing = service.get_appointment(id)

        if date_str:
            try:
                existing.date = date.fromisoformat(date_str)  # используем date из импорта
            except ValueError:
                click.echo("Неверный формат даты.", err=True)
                return
        if time_str:
            try:
                h, m = map(int, time_str.split(':'))
                existing.time = time(h, m)  # time из импорта
            except:
                click.echo("Неверный формат времени.", err=True)
                return

        dto_in = existing
        if note_id is not None:
            dto_in.note_id = note_id
        updated = service.update_appointment(dto_in, note_text=note_text)
        click.echo(f"Приём ID {updated.id} обновлён.")
    except AppointmentNotFoundError as e:
        click.echo(str(e), err=True)
    except Exception as e:
        click.echo(f"Ошибка: {e}", err=True)

@appointment.command('delete')
@click.option('--id', required=True, type=int, help='ID приёма')
def appointment_delete(id):
    """Удалить приём."""
    AppLogger.get_instance( name = 'system' ).debug( f"Удалить приём id={id}" )
    service = get_appointment_service()
    try:
        service.delete_appointment(id)
        click.echo(f"Приём ID {id} удалён.")
    except AppointmentNotFoundError as e:
        click.echo(str(e), err=True)
    except Exception as e:
        click.echo(f"Ошибка: {e}", err=True)

# ------------------------------------------------------------------------------
# Группа команд для заметок
# ------------------------------------------------------------------------------

@click.group()
def note():
    """Управление заметками приёмов."""
    pass

@note.command('list')
def note_list():
    """Вывести все заметки."""
    # print('1')

    AppLogger.get_instance( name = 'system' ).debug( f"Вывести все заметки" )
    service = get_note_service()
    try:
        # print('2')
        notes = service.get_all()
        # print('3')
        if not notes:
            click.echo("Заметки не найдены.")
            return
        for n in notes:
            # print('3')
            click.echo(f"ID: {n.id}, Текст: {n.text[:50]}...")
    except Exception as e:
        click.echo(f"Ошибка: {e}", err=True)

@note.command('get')
@click.option('--id', required=True, type=int, help='ID заметки')
def note_get(id):
    """Показать заметку."""
    AppLogger.get_instance( name = 'system' ).debug( f"Показать заметку id={id}" )
    service = get_note_service()
    try:
        n = service.get_note(id)
        click.echo(f"ID: {n.id}")
        click.echo(f"Текст:\n{n.text}")
    except AppointmentNoteNotFoundError as e:
        click.echo(str(e), err=True)
    except Exception as e:
        click.echo(f"Ошибка: {e}", err=True)

@note.command('create')
@click.argument('text')
def note_create(text):
    """Создать заметку (текст передаётся как аргумент)."""
    AppLogger.get_instance( name = 'system' ).debug( f"Создать заметку (текст передаётся как аргумент) text={text}" )
    service = get_note_service()
    try:
        dto = service.create_note(text)
        click.echo(f"Заметка создана с ID: {dto.id}")
    except Exception as e:
        click.echo(f"Ошибка: {e}", err=True)

@note.command('create-from-file')
@click.option('--file', type=click.Path(exists=True, readable=True), required=True, help='Файл с текстом заметки')
def note_create_from_file(file):
    """Создать заметку из текстового файла."""
    AppLogger.get_instance( name = 'system' ).debug( f"Создать заметку из текстового файла" )
    try:
        with open(file, 'r', encoding='utf-8') as f:
            text = f.read()
    except Exception as e:
        click.echo(f"Ошибка чтения файла: {e}", err=True)
        return
    service = get_note_service()
    try:
        dto = service.create_note(text)
        click.echo(f"Заметка создана с ID: {dto.id}")
    except Exception as e:
        click.echo(f"Ошибка: {e}", err=True)

@note.command('update')
@click.option('--id', required=True, type=int, help='ID заметки')
@click.argument('text')
def note_update(id, text):
    """Обновить текст заметки."""
    AppLogger.get_instance( name = 'system' ).debug( f"Обновить текст заметки id={id}, text={text}" )
    service = get_note_service()
    try:
        dto = service.update_note(id, text)
        click.echo(f"Заметка ID {dto.id} обновлена.")
    except AppointmentNoteNotFoundError as e:
        click.echo(str(e), err=True)
    except Exception as e:
        click.echo(f"Ошибка: {e}", err=True)

@note.command('delete')
@click.option('--id', required=True, type=int, help='ID заметки')
def note_delete(id):
    """Удалить заметку."""
    AppLogger.get_instance( name = 'system' ).debug( f"Удалить заметку id={id}" )
    service = get_note_service()
    try:
        service.delete_note(id)
        click.echo(f"Заметка ID {id} удалена.")
    except AppointmentNoteNotFoundError as e:
        click.echo(str(e), err=True)
    except Exception as e:
        click.echo(f"Ошибка: {e}", err=True)

# ------------------------------------------------------------------------------
# Группа команд для фото
# ------------------------------------------------------------------------------

@click.group()
def photo():
    """Управление фотографиями приёмов."""
    pass

# @photo.command('list')
# @click.option('--appointment-id', required=True, type=int, help='ID приёма')
# def photo_list(appointment_id):
#     """Список фото для приёма."""
#     AppLogger.get_instance( name = 'system' ).debug( f"Список фото для приёма appointment_id={appointment_id}" )
#     service = get_photo_service()
#     try:
#         photos = service.get_photos_for_appointment(appointment_id)
#         if not photos:
#             click.echo("Фото не найдены.")
#             return
#         for p in photos:
#             click.echo(f"ID: {p.id}, Файл: {p.file_path}, Описание: {p.description}")
#     except Exception as e:
#         click.echo(f"Ошибка: {e}", err=True)

@photo.command('list')
@click.option('--appointment-id', type=int, help='ID приёма (если не указан, выводятся все фото)')
def photo_list(appointment_id):
    """Список фотографий. Если указан appointment-id, показываются фото только этого приёма."""
    AppLogger.get_instance(name='system').debug(f"Запрос списка фото, appointment_id={appointment_id}")
    service = get_photo_service()
    try:
        if appointment_id is not None:
            photos = service.get_photos_for_appointment(appointment_id)
        else:
            photos = service.get_all()  # используем унаследованный метод из BaseService
        if not photos:
            click.echo("Фото не найдены.")
            return
        for p in photos:
            # Выводим информацию о каждом фото
            click.echo(f"ID: {p.id}, Приём ID: {p.appointment_id}, Файл: {p.file_path}, Описание: {p.description}")
    except Exception as e:
        click.echo(f"Ошибка: {e}", err=True)

@photo.command('add')
@click.option('--appointment-id', required=True, type=int, help='ID приёма')
@click.option('--file', required=True, type=click.Path(exists=True), help='Путь к файлу изображения')
@click.option('--description', default='', help='Описание')
def photo_add(appointment_id, file, description):
    """Добавить фото к приёму."""
    AppLogger.get_instance( name = 'system' ).debug( f"Добавить фото к приёму appointment_id={appointment_id}, description={description}" )
    service = get_photo_service()
    try:
        dto = service.add_photo_to_appointment(appointment_id, file, description)
        click.echo(f"Фото добавлено с ID: {dto.id}")
    except (AppointmentNotFoundError, PhotoFileError) as e:
        click.echo(str(e), err=True)
    except Exception as e:
        click.echo(f"Ошибка: {e}", err=True)

@photo.command('delete')
@click.option('--id', required=True, type=int, help='ID фото')
def photo_delete(id):
    """Удалить фото (файл и запись)."""
    AppLogger.get_instance( name = 'system' ).debug( f"Удалить фото (файл и запись) id={id}" )
    service = get_photo_service()
    try:
        service.delete_photo(id)
        click.echo(f"Фото ID {id} удалено.")
    except PhotoNotFoundError as e:
        click.echo(str(e), err=True)
    except PhotoFileError as e:
        click.echo(f"Ошибка при удалении файла: {e}", err=True)
    except Exception as e:
        click.echo(f"Ошибка: {e}", err=True)

# ------------------------------------------------------------------------------
# Команды инициализации, синхронизации и статистики
# ------------------------------------------------------------------------------

@click.command()
@click.option('--recreate/--no-recreate', default=False, help='Пересоздать БД (удалить существующую)')
@click.option('--test-data/--no-test-data', default=True, help='Заполнить тестовыми данными')
def init_db(recreate, test_data):
    """Инициализировать базу данных (создать таблицы, опционально тестовые данные)."""
    config = get_config_env()
    db_path = config['database_local_path']
    AppLogger.get_instance(
        name = 'system'
    ).debug(
        f"Инициализировать базу данных (создать таблицы, опционально тестовые данные): {db_path} ({os.path.abspath(db_path)})"
    )
    try:
        # Создаём движок и таблицы
        engine = create_db(db_path, recreate=recreate)
        if test_data:
            generate_test_data(db_path)
            # Создаём сессию и заполняем тестовыми данными
            # Session = sessionmaker(bind=engine)
            # session = Session()
            # generate_test_data(session)
            # session.close()
            click.echo("Тестовые данные добавлены.")
        click.echo(f"База данных инициализирована: {db_path} ({os.path.abspath(db_path)})")
    except Exception as e:
        click.echo(f"Ошибка инициализации БД: {e}", err=True)

@click.command()
def sync_download():
    """Скачать базу данных с Яндекс.Диска (асинхронно с отображением прогресса)."""
    AppLogger.get_instance(
        name = 'system'
    ).debug(
        f"Скачать базу данных с Яндекс.Диска (асинхронно с отображением прогресса))"
    )

    service = get_sync_service()
    click.echo("Начинаем скачивание...")
    # thread = service.prepare_download()

    # def progress_callback(current, total):
    #     percent = (current / total) * 100 if total else 0
    #     click.echo(f"\rПрогресс: {current}/{total} ({percent:.1f}%)", nl=False)

    # def on_finished(code):
    #     if code == 0:
    #         click.echo("\nСкачивание успешно завершено.")
    #     else:
    #         click.echo(f"\nСкачивание завершилось с ошибкой (код {code})")

    # thread.progress.connect(progress_callback)
    # thread.finished.connect(on_finished)
    # thread.error.connect(lambda msg: click.echo(f"\nОшибка: {msg}", err=True))
    # thread.start()

    # from PySide6.QtCore import QEventLoop
    # loop = QEventLoop()
    # thread.finished.connect(loop.quit)
    # thread.error.connect(loop.quit)
    # loop.exec()

    def progress_callback(current, total):
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

@click.command()
def sync_upload():
    """Загрузить локальную базу данных на Яндекс.Диск."""

    AppLogger.get_instance(
        name = 'system'
    ).debug(
        f"Загрузить локальную базу данных на Яндекс.Диск"
    )

    service = get_sync_service()
    click.echo("Начинаем загрузку...")

    # thread = service.prepare_upload()
    # def progress_callback(current, total):
    #     percent = (current / total) * 100 if total else 0
    #     click.echo(f"\rПрогресс: {current}/{total} ({percent:.1f}%)", nl=False)

    # def on_finished(code):
    #     if code == 0:
    #         click.echo("\nЗагрузка успешно завершена.")
    #     else:
    #         click.echo(f"\nЗагрузка завершилась с ошибкой (код {code})")

    # thread.progress.connect(progress_callback)
    # thread.finished.connect(on_finished)
    # thread.error.connect(lambda msg: click.echo(f"\nОшибка: {msg}", err=True))
    # thread.start()

    # from PySide6.QtCore import QEventLoop
    # loop = QEventLoop()
    # thread.finished.connect(loop.quit)
    # thread.error.connect(loop.quit)
    # loop.exec()

    def progress_callback(current, total):
        percent = (current / total) * 100 if total else 0
        click.echo(f"\rПрогресс: {current}/{total} ({percent:.1f}%)", nl=False)

    try:
        result = service.upload_sync(progress_callback=progress_callback)
        click.echo()
        if result == 0:
            click.echo("Загрузка успешно завершена.")
        else:
            click.echo(f"Загрузка завершилась с ошибкой (код {result})")
    except Exception as e:
        click.echo(f"\nОшибка: {e}", err=True)

# @click.command()
# def stats():
#     """Показать статистику по базе данных."""
#     db = get_db()
#     try:
#         with db.session_scope() as session:
#             patient_count = session.query(PatientRepository.model).count()
#             app_count = session.query(AppointmentRepository.model).count()
#             note_count = session.query(AppointmentNoteRepository.model).count()
#             photo_count = session.query(PhotoRepository.model).count()
#         click.echo(f"Пациентов: {patient_count}")
#         click.echo(f"Приёмов: {app_count}")
#         click.echo(f"Заметок: {note_count}")
#         click.echo(f"Фотографий: {photo_count}")
#     except Exception as e:
#         click.echo(f"Ошибка получения статистики: {e}", err=True)

@click.command()
def stats():
    """Показать статистику по базе данных."""
    AppLogger.get_instance(
        name = 'system'
    ).debug(
        f"Показать статистику по базе данных"
    )
    db = get_db()
    try:
        with db.session_scope() as session:
            patient_count = session.query(Patient).count()
            app_count = session.query(Appointment).count()
            note_count = session.query(AppointmentNote).count()
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

@click.group()
def cli():
    """Медицинское приложение - управление данными из консоли."""
    AppLogger.get_instance(
        name = 'system'
    ).debug(
        f"Медицинское приложение - управление данными из консоли"
    )
    pass

cli.add_command(patient)
cli.add_command(appointment)
cli.add_command(note)
cli.add_command(photo)
cli.add_command(init_db)
cli.add_command(sync_download)
cli.add_command(sync_upload)
cli.add_command(stats)


# ------------------------------------------------------------------------------
# Интерактивный режим (меню)
# ------------------------------------------------------------------------------

def patient_menu():
    """Меню управления пациентами."""
    while True:
        click.clear()
        click.echo("=== Управление пациентами ===")
        click.echo("1. Список всех пациентов")
        click.echo("2. Просмотр пациента по ID")
        click.echo("3. Создать нового пациента")
        click.echo("4. Обновить данные пациента")
        click.echo("5. Удалить пациента")
        click.echo("6. Поиск пациентов с фильтрами")
        click.echo("0. Вернуться в главное меню")
        choice = click.prompt("Выберите действие", type=int)

        AppLogger.get_instance( name = 'system' ).debug( f"Меню управления пациентами: choice={choice}" )

        ctx = click.get_current_context()

        if choice == 1:
            ctx.invoke(patient_list)
            click.pause()
        elif choice == 2:
            pid = click.prompt("Введите ID пациента", type=int)
            ctx.invoke(patient_get, id=pid)
            click.pause()
        elif choice == 3:
            first_name = click.prompt("Имя", type=str)
            last_name = click.prompt("Фамилия", type=str)
            birth_date = click.prompt("Дата рождения (ГГГГ-ММ-ДД, оставьте пустым)", default="")
            phone = click.prompt("Телефон (оставьте пустым)", default="")
            email = click.prompt("Email (оставьте пустым)", default="")
            ctx.invoke(
                patient_create,
                first_name=first_name,
                last_name=last_name,
                birth_date=birth_date if birth_date else None,
                phone=phone if phone else None,
                email=email if email else None
            )
            click.pause()
        elif choice == 4:
            pid = click.prompt("ID пациента для обновления", type=int)
            # Можно показать текущие данные (дополнительно)
            click.echo("Оставьте поле пустым, если не хотите его менять.")
            first_name = click.prompt("Новое имя", default="")
            last_name = click.prompt("Новая фамилия", default="")
            birth_date = click.prompt("Новая дата рождения", default="")
            phone = click.prompt("Новый телефон", default="")
            email = click.prompt("Новый email", default="")
            kwargs = {}
            if first_name:
                kwargs['first_name'] = first_name
            if last_name:
                kwargs['last_name'] = last_name
            if birth_date:
                kwargs['birth_date'] = birth_date
            if phone:
                kwargs['phone'] = phone
            if email:
                kwargs['email'] = email
            ctx.invoke(patient_update, id=pid, **kwargs)
            click.pause()
        elif choice == 5:
            pid = click.prompt("ID пациента для удаления", type=int)
            ctx.invoke(patient_delete, id=pid)
            click.pause()
        elif choice == 6:
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
            break
        else:
            click.echo("Неверный выбор. Нажмите Enter для продолжения.")
            click.pause()


def appointment_menu():
    """Меню управления приёмами."""
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

        AppLogger.get_instance( name = 'system' ).debug( f"Меню управления приёмами: choice={choice}" )

        ctx = click.get_current_context()

        if choice == 1:
            ctx.invoke(appointment_list)
            click.pause()
        elif choice == 2:
            pid = click.prompt("Введите ID пациента", type=int)
            ctx.invoke(appointment_list, patient_id=pid)
            click.pause()
        elif choice == 3:
            aid = click.prompt("Введите ID приёма", type=int)
            ctx.invoke(appointment_get, id=aid)
            click.pause()
        elif choice == 4:
            patient_id = click.prompt("ID пациента", type=int)
            date_str = click.prompt("Дата (ГГГГ-ММ-ДД)", type=str)
            time_str = click.prompt("Время (ЧЧ:ММ, оставьте пустым)", default="")
            # note_id = click.prompt("ID существующей заметки (оставьте пустым, если нет)", default="", type=int)
            note_text = click.prompt("Текст заметки (оставьте пустым, если нет)", default="")
            # note_text = click.prompt("Текст новой заметки (если нужно создать новую)", default="")
            # ctx.invoke(
            #     appointment_create,
            #     patient_id=patient_id,
            #     date=date_str,
            #     time=time_str if time_str else None,
            #     # note_id=note_id if note_id else None,
            #     note_text=note_text if note_text else None
            # )
            ctx.invoke(
                appointment_create,
                patient_id=patient_id,
                date_str=date_str if date_str else None,
                time_str=time_str if time_str else None,   # <-- исправлено имя
                note_text=note_text if note_text else None
            )
            click.pause()
        # elif choice == 5:
        #     aid = click.prompt("ID приёма для обновления", type=int)
        #     date_str = click.prompt("Новая дата (оставьте пустым)", default="")
        #     time_str = click.prompt("Новое время (оставьте пустым)", default="")
        #     note_id = click.prompt("Новый ID заметки (оставьте пустым)", default="", type=int)
        #     note_text = click.prompt("Текст новой заметки (если нужно создать новую)", default="")
        #     kwargs = {}
        #     if date_str:
        #         kwargs['date'] = date_str
        #     if time_str:
        #         kwargs['time'] = time_str
        #     if note_id:
        #         kwargs['note_id'] = note_id
        #     if note_text:
        #         kwargs['note_text'] = note_text
        #     ctx.invoke(appointment_update, id=aid, **kwargs)
        #     click.pause()

        elif choice == 5:
            aid = click.prompt("ID приёма для обновления", type=int)
            # Получаем текущие данные приёма
            service = get_appointment_service()
            try:
                current_app = service.get_appointment(aid)
            except Exception as e:
                click.echo(f"Ошибка: {e}")
                click.pause()
                continue

            click.echo("\n--- Текущие данные приёма ---")
            click.echo(f"Дата: {current_app.date}")
            click.echo(f"Время: {current_app.time or 'не указано'}")
            if current_app.note_text:
                click.echo(f"Заметка: {current_app.note_text}")
            else:
                click.echo("Заметка: отсутствует")
            click.echo("-----------------------------\n")

            # Ввод новых значений (если пусто – оставляем старое)
            date_str = click.prompt("Новая дата (ГГГГ-ММ-ДД)", default=str(current_app.date))
            time_str = click.prompt("Новое время (ЧЧ:ММ)", default=str(current_app.time) if current_app.time else "")
            note_text = click.prompt(
                "Новый текст заметки (Enter – оставить текущую, новый текст – заменить)",
                default=""
            )

            kwargs = {}
            # Если дата изменилась – передаём
            if date_str != str(current_app.date):
                # kwargs['date'] = date_str
                kwargs['date_str'] = date_str
            # Если время изменилось – передаём (учитываем, что может быть пустым)
            new_time = time_str if time_str else None
            old_time = str(current_app.time) if current_app.time else ""
            if new_time != old_time:
                # kwargs['time'] = time_str if time_str else None  # передаём пустую строку или None
                kwargs['time_str'] = time_str if time_str else None  # передаём пустую строку или None
            # Если введён новый текст заметки – передаём note_text
            if note_text:
                kwargs['note_text'] = note_text
            # Если не введён, но была заметка – оставляем старую (ничего не передаём)
            # Если не введён и не было заметки – тоже ничего

            ctx.invoke(appointment_update, id=aid, **kwargs)
            click.pause()
        elif choice == 6:
            aid = click.prompt("ID приёма для удаления", type=int)
            ctx.invoke(appointment_delete, id=aid)
            click.pause()
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
    """Меню управления заметками."""
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

        AppLogger.get_instance( name = 'system' ).debug( f"Меню управления заметками: choice={choice}" )

        ctx = click.get_current_context()

        if choice == 1:
            ctx.invoke(note_list)
            click.pause()
        elif choice == 2:
            nid = click.prompt("Введите ID заметки", type=int)
            ctx.invoke(note_get, id=nid)
            click.pause()
        elif choice == 3:
            text = click.prompt("Введите текст заметки", type=str)
            ctx.invoke(note_create, text=text)
            click.pause()
        elif choice == 4:
            file_path = click.prompt("Путь к файлу", type=click.Path(exists=True))
            ctx.invoke(note_create_from_file, file=file_path)
            click.pause()
        elif choice == 5:
            nid = click.prompt("ID заметки для обновления", type=int)
            text = click.prompt("Новый текст заметки", type=str)
            ctx.invoke(note_update, id=nid, text=text)
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
    """Меню управления фотографиями."""
    while True:
        click.clear()
        click.echo("=== Управление фотографиями ===")
        click.echo("1. Список фото для приёма")
        click.echo("2. Добавить фото к приёму")
        click.echo("3. Удалить фото")
        click.echo("0. Вернуться в главное меню")
        choice = click.prompt("Выберите действие", type=int)
        
        AppLogger.get_instance( name = 'system' ).debug( f"Меню управления фотографиями: choice={choice}" )

        ctx = click.get_current_context()

        if choice == 1:
            aid = click.prompt("Введите ID приёма", type=int)
            ctx.invoke(photo_list, appointment_id=aid)
            click.pause()
        elif choice == 2:
            aid = click.prompt("ID приёма", type=int)
            file_path = click.prompt("Путь к файлу изображения", type=click.Path(exists=True))
            desc = click.prompt("Описание (оставьте пустым)", default="")
            ctx.invoke(photo_add, appointment_id=aid, file=file_path, description=desc)
            click.pause()
        elif choice == 3:
            pid = click.prompt("ID фото для удаления", type=int)
            ctx.invoke(photo_delete, id=pid)
            click.pause()
        elif choice == 0:
            break
        else:
            click.echo("Неверный выбор.")
            click.pause()


def db_menu():
    """Меню управления базой данных."""
    while True:
        click.clear()
        click.echo("=== Управление базой данных ===")
        click.echo("1. Инициализировать БД (создать таблицы)")
        click.echo("2. Статистика")
        click.echo("0. Вернуться в главное меню")
        choice = click.prompt("Выберите действие", type=int)
        
        AppLogger.get_instance( name = 'system' ).debug( f"Меню управления базой данных: choice={choice}" )

        ctx = click.get_current_context()

        if choice == 1:
            recreate = click.confirm("Пересоздать БД (удалить все данные)?", default=False)
            test_data = click.confirm("Заполнить тестовыми данными?", default=True)
            ctx.invoke(init_db, recreate=recreate, test_data=test_data)
            click.pause()
        elif choice == 2:
            ctx.invoke(stats)
            click.pause()
        elif choice == 0:
            break
        else:
            click.echo("Неверный выбор.")
            click.pause()


def sync_menu():
    """Меню синхронизации."""
    while True:
        click.clear()
        click.echo("=== Синхронизация с Яндекс.Диском ===")
        click.echo("1. Скачать базу данных")
        click.echo("2. Загрузить базу данных")
        click.echo("0. Вернуться в главное меню")
        choice = click.prompt("Выберите действие", type=int)
        
        AppLogger.get_instance( name = 'system' ).debug( f"Меню синхронизации: choice={choice}" )

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
    """Интерактивный режим с выбором действия по номеру."""
    while True:
        click.clear()
        click.echo("=== Медицинское приложение (интерактивный режим) ===")
        click.echo("Выберите категорию:")
        click.echo("1. Пациенты")
        click.echo("2. Приёмы")
        click.echo("3. Заметки")
        click.echo("4. Фотографии")
        click.echo("5. Управление базой данных")
        click.echo("6. Синхронизация")
        click.echo("0. Выход")
        choice = click.prompt("Ваш выбор", type=int)

        AppLogger.get_instance( name = 'system' ).debug( f"Интерактивный режим с выбором действия по номеру: choice={choice}" )

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




if __name__ == '__main__':
    if len(sys.argv) == 1:
        # Если аргументы не переданы, запускаем интерактивное меню
        menu()
    else:
        cli()