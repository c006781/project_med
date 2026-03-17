# tests/test_services/test_patient_service.py


# Стандартные библиотеки Python
# import os  # Импорт модуля os для работы с путями файлов и директориями (например, чтобы получить абсолютный путь к файлу).
# import sys  # Импорт модуля sys для работы с системными параметрами, такими как sys.path (список путей для импорта модулей).



# Импорты модулей
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
#     # Если не вызвать: относительный импорт from .module... может вызвать ImportError: attempted relative import with no known parent package.

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
#     from ...app.dto import PatientDTO
# except ImportError as e:
#     try:
#         # Попытка абсолютного импорта, если модуль запущен как скрипт
#         _add_package_name(file_module = __file__,levels_up = 3)
#         from ...app.dto import PatientDTO
#     except ImportError as e:
#         pass

# try:
#     from ...app.exceptions import PatientNotFoundError, PatientValidationError
# except ImportError as e:
#     try:
#         # Попытка абсолютного импорта, если модуль запущен как скрипт
#         _add_package_name(file_module = __file__,levels_up = 3)
#         from ...app.exceptions import PatientNotFoundError, PatientValidationError
#     except ImportError as e:
#         pass

from app.dto import PatientDTO
from app.exceptions import PatientNotFoundError, PatientValidationError

# Сторонние библиотеки

import pytest # pip install pytest

def test_get_all_patients(patient_service, sample_patient):
    """
    Тестирование функции get_all_patients сервиса PatientService.

    Ожидаем, что функция get_all_patients возвращает список всех пациентов,
    а также что в этом списке есть пациент с идентификатором sample_patient.id.
    """
    patients = patient_service.get_all_patients()
    assert len(patients) >= 1
    assert any(p.id == sample_patient.id for p in patients)

def test_get_patient_by_id_found(patient_service, sample_patient):
    """
    Тестирование функции get_patient_by_id сервиса PatientService в случае
    наличия пациента с указанным идентификатором.

    Ожидаем, что функция get_patient_by_id возвращает объект PatientDTO
    с данными пациента, соответствующими переданному идентификатору.
    """
    dto = patient_service.get_patient_by_id(sample_patient.id)
    assert dto.id == sample_patient.id
    assert dto.first_name == sample_patient.first_name

def test_get_patient_by_id_not_found(patient_service):
    """
    Тестирование функции get_patient_by_id сервиса PatientService в случае
    отсутствия пациента с указанным идентификатором.

    Ожидаем, что функция get_patient_by_id выбрасывает исключение
    PatientNotFoundError, если пациент с указанным идентификатором
    не найден в базе данных.
    """
    # Ожидаем, что функция get_patient_by_id выбрасывает исключение
    # PatientNotFoundError, если пациент с указанным идентификатором
    # не найден в базе данных
    with pytest.raises(PatientNotFoundError):
        patient_service.get_patient_by_id(9999)

def test_create_patient(patient_service):
    """
    Тестирование функции create_patient сервиса PatientService.

    Создаём тестовый DTO с данными и попытаемся создать нового пациента.
    Проверяет, что функция create_patient возвращает DTO с заполненными полями и correct ID.

    DTO с данными:
        * id - None (будет автоматически заполнен)
        * first_name - "Анна"
        * last_name - "Смирнова"
        * birth_date - None
        * phone - ""
        * email - ""
    """
    dto_in = PatientDTO(
        id=None,
        first_name="Анна",
        last_name="Смирнова",
        birth_date=None,
        phone="",
        email=""
    )
    dto_out = patient_service.create_patient(dto_in)
    assert dto_out.id is not None, "ID should be assigned"
    assert dto_out.first_name == "Анна", "First name should be 'Анна'"
    assert dto_out.last_name == "Смирнова", "Last name should be 'Смирнова'"
    assert dto_out.birth_date is None, "Birth date should be None"
    assert dto_out.phone == "", "Phone should be empty"
    assert dto_out.email == "", "Email should be empty"

def test_create_patient_validation_error(patient_service):
    """
    Тестирование функции create_patient сервиса PatientService.
    
    Создаём тестового DTO с пустыми полями и попытаемся создать пациента.
    Проверяет, что функция create_patient выбрасывает исключение PatientValidationError.
    """
    with pytest.raises(PatientValidationError):
        patient_service.create_patient(PatientDTO(
            id=None, first_name="", last_name="", birth_date=None, phone="", email=""
        ))

def test_update_patient(patient_service, sample_patient):
    """
    Тестирование функции update_patient сервиса PatientService.
    
    Создаёт тестового пациента и обновляет его данные.
    Проверяет, что обновлённый пациент соответствует ожидаемым данным.
    """
    dto_update = PatientDTO(
        id=sample_patient.id,
        first_name="Пётр",
        last_name="Петров",
        birth_date=None,
        phone="+79999999999",
        email="petr@test.ru"
    )
    updated = patient_service.update_patient(dto_update)
    assert updated.first_name == "Пётр"
    assert updated.phone == "+79999999999"

def test_delete_patient(patient_service, sample_patient, db_session):
    """
    Тестирование функции delete_patient сервиса PatientService.

    Ожидаем, что функция delete_patient удаляет пациента из базы данных
    и выбрасывает исключение PatientNotFoundError, если попытаться получить
    удалённого пациента.
    """
    patient_service.delete_patient(sample_patient.id)
    db_session.commit()  # фиксируем удаление
    db_session.expire_all()  # чтобы сбросить кэш сессии
    with pytest.raises(PatientNotFoundError):
        patient_service.get_patient_by_id(sample_patient.id)