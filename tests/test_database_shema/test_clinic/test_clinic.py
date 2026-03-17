# tests/test_models/test_models.py


# Стандартные библиотеки Python
import os  # Импорт модуля os для работы с путями файлов и директориями (например, чтобы получить абсолютный путь к файлу).
import sys  # Импорт модуля sys для работы с системными параметрами, такими как sys.path (список путей для импорта модулей).

import tempfile
from datetime import date, time

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
#     from ...app.models.bd.models import Patient, Appointment, AppointmentNote, Photo
# except ImportError as e:
#     try:
#         # Попытка абсолютного импорта, если модуль запущен как скрипт
#         _add_package_name(file_module = __file__,levels_up = 3)
#         from ...app.models.bd.models import Patient, Appointment, AppointmentNote, Photo
#     except ImportError as e:
#         pass

from app.database.database_shema.clinic import Patient, Appointment, AppointmentNote, Photo

# Сторонние библиотеки
import pytest # pip install pytest

def test_patient_creation(db_session):
    """
    Проверка создания пациента.

    Создаём экземпляр класса Patient, добавляем его в сессию,
    commit'им сессию и проверяем, что id у пациента не None,
    и что поля first_name и last_name содержат ожидаемые значения.
    """
    # Создаём экземпляр класса Patient
    patient = Patient(first_name="Тест", last_name="Тестов")
    # Добавляем пациента в сессию
    db_session.add(patient)
    # Commit'им сессию
    db_session.commit()
    # Проверяем, что id у пациента не None
    assert patient.id is not None
    # Проверяем, что поля first_name и last_name содержат ожидаемые значения
    assert patient.first_name == "Тест"
    assert patient.last_name == "Тестов"
 
def test_patient_appointment_relationship(db_session, sample_patient):
    """Проверка связи пациент -> приёмы.

    Создаём заметку и добавляем ее в сессию.
    Создаём приём, связанный с заметкой и пациентом, и добавляем его в сессию.
    Commit'им сессию.
    Обновляем объект пациента, чтобы загрузить связь.
    Проверяем, что у пациента есть 1 приём, и что приём имеет ожидаемые значения.
    """
    # Создаём заметку
    note = AppointmentNote(text="Заметка")
    # Добавляем заметку в сессию
    db_session.add(note)
    # Commit'им сессию
    db_session.commit()

    # Создаём приём, связанный с заметкой и пациентом
    app = Appointment(
        patient_id=sample_patient.id,
        date=date.today(),
        time=time(10, 0),
        note_id=note.id
    )
    # Добавляем приём в сессию
    db_session.add(app)
    # Commit'им сессию
    db_session.commit()

    # Обновляем объект пациента, чтобы загрузить связь
    db_session.refresh(sample_patient)

    # Проверяем, что у пациента есть 1 приём
    assert len(sample_patient.appointments) == 1
    # Проверяем, что приём имеет ожидаемые значения
    assert sample_patient.appointments[0].id == app.id
    assert sample_patient.appointments[0].note.text == "Заметка"
